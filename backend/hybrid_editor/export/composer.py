"""Compose cutout preview MP4 (H.264) from BGR + alpha sequences.

ProRes 4444 with alpha is attempted when ffmpeg supports `prores_ks`;
Windows-openable H.264 companion (`preview.mp4`) is always preferred for UI.
Phase 4: mux original (or timeline) audio onto preview via FFmpeg AAC.
"""

from __future__ import annotations

import logging
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Sequence

import cv2
import numpy as np

logger = logging.getLogger(__name__)


@dataclass
class ExportResult:
    ok: bool
    preview_mp4: Optional[str]
    prores_mov: Optional[str]
    frames: int
    message: str


@dataclass(frozen=True)
class AudioSegment:
    """One source media slice to place on the export audio timeline."""

    path: str
    in_sec: float
    out_sec: float
    timeline_start_sec: float = 0.0

    def duration(self) -> float:
        return max(0.0, float(self.out_sec) - float(self.in_sec))


def _checker_composite(bgr: np.ndarray, alpha: np.ndarray) -> np.ndarray:
    h, w = bgr.shape[:2]
    a = alpha.astype(np.float32)
    if a.max() > 1.5:
        a = a / 255.0
    a = np.clip(a, 0.0, 1.0)
    if a.ndim == 3:
        a = a[..., 0]
    tile = 16
    yy, xx = np.mgrid[0:h, 0:w]
    checker = (((xx // tile) + (yy // tile)) % 2).astype(np.float32)
    bg = (checker * 220 + (1.0 - checker) * 40).astype(np.uint8)
    bg = np.stack([bg, bg, bg], axis=-1)
    a3 = a[..., None]
    return (bgr.astype(np.float32) * a3 + bg.astype(np.float32) * (1.0 - a3)).astype(np.uint8)


def media_has_audio(path: Path | str) -> bool:
    """Best-effort probe: True if ffmpeg sees an audio stream."""
    ffmpeg = shutil.which("ffmpeg")
    ffprobe = shutil.which("ffprobe")
    p = Path(path)
    if not p.is_file():
        return False
    if ffprobe:
        cmd = [
            ffprobe,
            "-v",
            "error",
            "-select_streams",
            "a:0",
            "-show_entries",
            "stream=codec_type",
            "-of",
            "csv=p=0",
            str(p),
        ]
        try:
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=20)
            return "audio" in (r.stdout or "").lower()
        except Exception as exc:  # noqa: BLE001
            logger.debug("ffprobe audio check failed: %s", exc)
    if ffmpeg:
        cmd = [ffmpeg, "-i", str(p)]
        try:
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=20)
            blob = (r.stderr or "") + (r.stdout or "")
            return ("Audio:" in blob) or ("Audio" in blob and "Stream #" in blob)
        except Exception as exc:  # noqa: BLE001
            logger.debug("ffmpeg audio check failed: %s", exc)
    return False


def mux_audio_onto_video(
    video_path: Path | str,
    out_path: Path | str,
    segments: Sequence[AudioSegment],
    *,
    total_duration_sec: Optional[float] = None,
) -> Optional[str]:
    """Mux AAC audio from source segment(s) onto an existing video file.

    Single segment: trim source audio to [in,out] and map onto video.
    Multi segment: build a silent bed + delayed overlays, then mux.
    Returns out_path on success, None if ffmpeg missing / no usable audio.
    """
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        return None
    video_path = Path(video_path)
    out_path = Path(out_path)
    if not video_path.is_file():
        return None
    usable = [s for s in segments if Path(s.path).is_file() and s.duration() > 1e-3]
    if not usable:
        return None
    # Drop segments with no audio stream
    usable = [s for s in usable if media_has_audio(s.path)]
    if not usable:
        logger.info("No audio streams in source segment(s) — keeping silent preview")
        return None

    out_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_out = out_path.with_suffix(".audio.tmp.mp4")

    try:
        if len(usable) == 1 and abs(usable[0].timeline_start_sec) < 1e-6:
            seg = usable[0]
            # Simple path: video + trimmed source audio
            cmd = [
                ffmpeg,
                "-y",
                "-i",
                str(video_path),
                "-ss",
                f"{float(seg.in_sec):.6f}",
                "-to",
                f"{float(seg.out_sec):.6f}",
                "-i",
                str(seg.path),
                "-map",
                "0:v:0",
                "-map",
                "1:a:0?",
                "-c:v",
                "copy",
                "-c:a",
                "aac",
                "-b:a",
                "192k",
                "-shortest",
                "-movflags",
                "+faststart",
                str(tmp_out),
            ]
            subprocess.run(cmd, check=True, capture_output=True, timeout=180)
        else:
            # Multi-clip / delayed: concat trimmed AAC pieces then mux
            with tempfile.TemporaryDirectory(prefix="hybrid-audio-") as td:
                td_path = Path(td)
                parts: list[Path] = []
                for i, seg in enumerate(usable):
                    part = td_path / f"a{i:02d}.m4a"
                    # Pad leading silence when clip starts later on timeline
                    delay_ms = max(0, int(round(float(seg.timeline_start_sec) * 1000)))
                    af = f"atrim=start={float(seg.in_sec):.6f}:end={float(seg.out_sec):.6f},asetpts=PTS-STARTPTS"
                    if delay_ms > 0:
                        af = f"{af},adelay={delay_ms}|{delay_ms}"
                    cmd_a = [
                        ffmpeg,
                        "-y",
                        "-i",
                        str(seg.path),
                        "-vn",
                        "-af",
                        af,
                        "-c:a",
                        "aac",
                        "-b:a",
                        "192k",
                        str(part),
                    ]
                    subprocess.run(cmd_a, check=True, capture_output=True, timeout=120)
                    if part.is_file() and part.stat().st_size > 0:
                        parts.append(part)
                if not parts:
                    return None
                if len(parts) == 1:
                    mixed = parts[0]
                else:
                    # amix all parts onto one bed
                    mixed = td_path / "mixed.m4a"
                    cmd_m = [ffmpeg, "-y"]
                    for p in parts:
                        cmd_m += ["-i", str(p)]
                    n = len(parts)
                    filt = "".join(f"[{i}:a]" for i in range(n)) + f"amix=inputs={n}:duration=longest:dropout_transition=0[a]"
                    cmd_m += [
                        "-filter_complex",
                        filt,
                        "-map",
                        "[a]",
                        "-c:a",
                        "aac",
                        "-b:a",
                        "192k",
                        str(mixed),
                    ]
                    subprocess.run(cmd_m, check=True, capture_output=True, timeout=180)
                cmd = [
                    ffmpeg,
                    "-y",
                    "-i",
                    str(video_path),
                    "-i",
                    str(mixed),
                    "-map",
                    "0:v:0",
                    "-map",
                    "1:a:0",
                    "-c:v",
                    "copy",
                    "-c:a",
                    "aac",
                    "-b:a",
                    "192k",
                    "-shortest",
                    "-movflags",
                    "+faststart",
                    str(tmp_out),
                ]
                if total_duration_sec is not None and total_duration_sec > 0:
                    cmd.extend(["-t", f"{float(total_duration_sec):.6f}"])
                subprocess.run(cmd, check=True, capture_output=True, timeout=180)

        if not tmp_out.is_file() or tmp_out.stat().st_size <= 0:
            return None
        try:
            tmp_out.replace(out_path)
        except OSError:
            shutil.copy2(tmp_out, out_path)
            tmp_out.unlink(missing_ok=True)
        return str(out_path.resolve())
    except Exception as exc:  # noqa: BLE001
        logger.warning("Audio mux failed (%s) — keeping silent video", exc)
        tmp_out.unlink(missing_ok=True)
        return None


def write_preview_mp4(
    frames_bgr: list[np.ndarray],
    frames_alpha: list[np.ndarray],
    out_path: Path,
    *,
    fps: float = 25.0,
    audio_segments: Optional[Sequence[AudioSegment]] = None,
    audio_duration_sec: Optional[float] = None,
) -> Optional[str]:
    """Write checkerboard cutout preview as H.264-friendly mp4; optional audio mux."""
    if not frames_bgr or len(frames_bgr) != len(frames_alpha):
        return None
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    h, w = frames_bgr[0].shape[:2]
    tmp = out_path.with_suffix(".tmp.mp4")
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    writer = cv2.VideoWriter(str(tmp), fourcc, float(fps) or 25.0, (w, h))
    if not writer.isOpened():
        return None
    try:
        for bgr, alpha in zip(frames_bgr, frames_alpha):
            if bgr.shape[:2] != (h, w):
                bgr = cv2.resize(bgr, (w, h), interpolation=cv2.INTER_AREA)
            if alpha.shape[:2] != (h, w):
                alpha = cv2.resize(alpha, (w, h), interpolation=cv2.INTER_LINEAR)
            writer.write(_checker_composite(bgr, alpha))
    finally:
        writer.release()

    ffmpeg = shutil.which("ffmpeg")
    silent = out_path.with_suffix(".silent.mp4")
    encoded: Optional[Path] = None
    if ffmpeg:
        # Re-encode to yuv420p H.264 for broad Windows playback
        cmd = [
            ffmpeg,
            "-y",
            "-i",
            str(tmp),
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-crf",
            "18",
            "-movflags",
            "+faststart",
            str(silent),
        ]
        try:
            subprocess.run(cmd, check=True, capture_output=True, timeout=120)
            tmp.unlink(missing_ok=True)
            encoded = silent
        except Exception as exc:  # noqa: BLE001
            logger.warning("ffmpeg H.264 remux failed (%s) — keeping OpenCV mp4v", exc)
            encoded = None

    if encoded is None:
        try:
            tmp.replace(silent)
        except OSError:
            shutil.copy2(tmp, silent)
            tmp.unlink(missing_ok=True)
        encoded = silent

    # Optional audio
    if audio_segments:
        muxed = mux_audio_onto_video(
            encoded,
            out_path,
            audio_segments,
            total_duration_sec=audio_duration_sec,
        )
        if muxed:
            if encoded.resolve() != Path(out_path).resolve():
                encoded.unlink(missing_ok=True)
            return muxed

    # No audio — place silent file at out_path
    try:
        if encoded.resolve() != out_path.resolve():
            encoded.replace(out_path)
    except OSError:
        shutil.copy2(encoded, out_path)
        encoded.unlink(missing_ok=True)
    return str(out_path.resolve())


def write_windows_companion(
    preview_mp4: Optional[str],
    out_dir: Path,
    *,
    stem: str = "HybridCut_preview",
) -> Optional[str]:
    """Copy preview next to bake as a clear Windows Films&TV / VLC companion name."""
    if not preview_mp4:
        return None
    src = Path(preview_mp4)
    if not src.is_file():
        return None
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    dest = out_dir / f"{stem}.mp4"
    try:
        if src.resolve() != dest.resolve():
            shutil.copy2(src, dest)
        return str(dest.resolve())
    except OSError as exc:
        logger.debug("windows companion copy: %s", exc)
        return str(src.resolve())


def try_prores_alpha(
    frames_bgra: list[np.ndarray],
    out_path: Path,
    *,
    fps: float = 25.0,
) -> Optional[str]:
    """Best-effort ProRes 4444 with alpha via ffmpeg image pipe. Optional."""
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg or not frames_bgra:
        return None
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    h, w = frames_bgra[0].shape[:2]
    # Write PNG sequence then encode — more reliable than raw pipe on Windows
    seq = out_path.parent / "_prores_seq"
    seq.mkdir(parents=True, exist_ok=True)
    try:
        for i, bgra in enumerate(frames_bgra):
            cv2.imwrite(str(seq / f"{i:06d}.png"), bgra)
        cmd = [
            ffmpeg,
            "-y",
            "-framerate",
            str(float(fps) or 25.0),
            "-i",
            str(seq / "%06d.png"),
            "-c:v",
            "prores_ks",
            "-profile:v",
            "4444",
            "-pix_fmt",
            "yuva444p10le",
            str(out_path),
        ]
        subprocess.run(cmd, check=True, capture_output=True, timeout=180)
        if out_path.is_file() and out_path.stat().st_size > 0:
            return str(out_path.resolve())
    except Exception as exc:  # noqa: BLE001
        logger.info("ProRes alpha export unavailable (%s)", exc)
    finally:
        for p in seq.glob("*.png"):
            p.unlink(missing_ok=True)
        try:
            seq.rmdir()
        except OSError:
            pass
    return None
