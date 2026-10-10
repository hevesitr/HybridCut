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
    from hybrid_editor.media.video_io import composite_cutout_over_checker

    return composite_cutout_over_checker(bgr, alpha)


def media_has_audio(path: Path | str) -> bool:
    """Best-effort probe: True if ffmpeg sees an audio stream."""
    from hybrid_editor.export.ffmpeg_bin import resolve_ffmpeg

    ffmpeg = resolve_ffmpeg("ffmpeg")
    ffprobe = resolve_ffmpeg("ffprobe")
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
    from hybrid_editor.export.ffmpeg_bin import resolve_ffmpeg

    ffmpeg = resolve_ffmpeg("ffmpeg")
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

    from hybrid_editor.export.ffmpeg_bin import resolve_ffmpeg

    ffmpeg = resolve_ffmpeg("ffmpeg")
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
    """Copy preview next to bake as a clear Windows Films&TV / VLC companion name.

    Prefer Videoeditor naming: pass ``stem="{media}_full_nobg_preview"`` so the
    file lands as ``{stem}.mp4`` (e.g. ``29308762a_full_nobg_preview.mp4``).
    """
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


def _uniform_bgra_size(frames_bgra: list[np.ndarray]) -> tuple[int, int, list[np.ndarray]]:
    """Force all frames to the first frame's HxW (BGRA uint8)."""
    h, w = frames_bgra[0].shape[:2]
    out: list[np.ndarray] = []
    for fr in frames_bgra:
        if fr.ndim != 3 or fr.shape[2] < 4:
            raise ValueError(f"BGRA frame invalid: shape={getattr(fr, 'shape', None)}")
        if fr.shape[0] != h or fr.shape[1] != w:
            fr = cv2.resize(fr, (w, h), interpolation=cv2.INTER_AREA)
        if fr.dtype != np.uint8:
            fr = np.clip(fr, 0, 255).astype(np.uint8)
        if not fr.flags["C_CONTIGUOUS"] or fr.shape[2] != 4:
            bgra = np.empty((h, w, 4), dtype=np.uint8)
            bgra[:, :, :3] = fr[:, :, :3]
            bgra[:, :, 3] = fr[:, :, 3] if fr.shape[2] >= 4 else 255
            fr = bgra
        out.append(fr)
    return w, h, out


def _pipe_bgra_mov(
    frames_bgra: list[np.ndarray],
    out_path: Path,
    *,
    fps: float,
    ffmpeg: str,
    vcodec_args: list[str],
    label: str,
) -> Optional[str]:
    """Stream raw BGRA frames into ffmpeg (Videoeditor ``*_full_nobg.mov`` path)."""
    if not frames_bgra:
        return None
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    if out_path.is_file():
        try:
            out_path.unlink()
        except OSError:
            pass
    w, h, frames = _uniform_bgra_size(frames_bgra)
    n = len(frames)
    timeout = max(180.0, 2.5 * n + 90.0)
    cmd = [
        ffmpeg,
        "-y",
        "-hide_banner",
        "-loglevel",
        "error",
        "-f",
        "rawvideo",
        "-pix_fmt",
        "bgra",
        "-s",
        f"{w}x{h}",
        "-r",
        str(float(fps) or 25.0),
        "-i",
        "-",
        "-an",
        *vcodec_args,
        "-f",
        "mov",
        str(out_path),
    ]
    try:
        proc = subprocess.Popen(
            cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        assert proc.stdin is not None
        try:
            for fr in frames:
                proc.stdin.write(fr.tobytes())
            proc.stdin.close()
        except BrokenPipeError:
            pass
        try:
            _stdout, stderr = proc.communicate(timeout=timeout)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.communicate(timeout=15)
            logger.info("%s alpha MOV timed out after %.0fs", label, timeout)
            return None
        if proc.returncode != 0:
            err = (stderr or b"").decode("utf-8", errors="replace")[-500:]
            logger.info("%s alpha MOV failed: %s", label, err)
            return None
        if out_path.is_file() and out_path.stat().st_size > 256:
            return str(out_path.resolve())
    except Exception as exc:  # noqa: BLE001
        logger.info("%s alpha MOV unavailable (%s)", label, exc)
    return None


def _png_seq_mov(
    frames_bgra: list[np.ndarray],
    out_path: Path,
    *,
    fps: float,
    ffmpeg: str,
    vcodec_args: list[str],
    label: str,
) -> Optional[str]:
    """Fallback: write PNG sequence then mux (when raw pipe is awkward)."""
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    seq = out_path.parent / f"_{label}_seq"
    seq.mkdir(parents=True, exist_ok=True)
    n = len(frames_bgra)
    timeout = max(180.0, 2.0 * n + 60.0)
    try:
        for i, bgra in enumerate(frames_bgra):
            cv2.imwrite(str(seq / f"{i:06d}.png"), bgra)
        cmd = [
            ffmpeg,
            "-y",
            "-hide_banner",
            "-loglevel",
            "error",
            "-framerate",
            str(float(fps) or 25.0),
            "-i",
            str(seq / "%06d.png"),
            *vcodec_args,
            str(out_path),
        ]
        subprocess.run(cmd, check=True, capture_output=True, timeout=timeout)
        if out_path.is_file() and out_path.stat().st_size > 256:
            return str(out_path.resolve())
    except Exception as exc:  # noqa: BLE001
        logger.info("%s PNG-seq alpha MOV unavailable (%s)", label, exc)
    finally:
        for p in seq.glob("*.png"):
            p.unlink(missing_ok=True)
        try:
            seq.rmdir()
        except OSError:
            pass
    return None


def try_prores_alpha_from_png_dir(
    seq_dir: Path,
    out_path: Path,
    *,
    fps: float = 25.0,
    n_frames: int = 0,
) -> Optional[str]:
    """Mux ``%06d.png`` BGRA sequence → ``*_full_nobg.mov`` (peak streaming bake).

    Avoids holding full-res BGRA in RAM on RTX 3060 / long clips.
    """
    from hybrid_editor.export.ffmpeg_bin import resolve_ffmpeg

    ffmpeg = resolve_ffmpeg("ffmpeg")
    if not ffmpeg:
        logger.warning(
            "FFmpeg not found — cannot write *_full_nobg.mov. Install ffmpeg or set FFMPEG_PATH."
        )
        return None
    seq_dir = Path(seq_dir)
    pattern = seq_dir / "%06d.png"
    if not (seq_dir / "000000.png").is_file():
        return None
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    n = int(n_frames) if n_frames > 0 else len(list(seq_dir.glob("*.png")))
    timeout = max(180.0, 2.5 * max(n, 1) + 90.0)
    attempts = [
        (
            "ProRes",
            [
                "-c:v",
                "prores_ks",
                "-profile:v",
                "4444",
                "-pix_fmt",
                "yuva444p10le",
                "-vendor",
                "apl0",
                "-alpha_bits",
                "16",
            ],
        ),
        ("qtrle", ["-c:v", "qtrle", "-pix_fmt", "argb"]),
        ("png", ["-c:v", "png", "-pix_fmt", "rgba"]),
    ]
    for label, vcodec_args in attempts:
        try:
            if out_path.is_file():
                out_path.unlink()
        except OSError:
            pass
        cmd = [
            ffmpeg,
            "-y",
            "-hide_banner",
            "-loglevel",
            "error",
            "-framerate",
            str(float(fps) or 25.0),
            "-i",
            str(pattern),
            *vcodec_args,
            "-f",
            "mov",
            str(out_path),
        ]
        try:
            subprocess.run(cmd, check=True, capture_output=True, timeout=timeout)
            if out_path.is_file() and out_path.stat().st_size > 256:
                return str(out_path.resolve())
        except Exception as exc:  # noqa: BLE001
            logger.info("%s from PNG dir failed: %s", label, exc)
    return None


def try_prores_alpha(
    frames_bgra: list[np.ndarray],
    out_path: Path,
    *,
    fps: float = 25.0,
) -> Optional[str]:
    """Mux Videoeditor-style ``*_full_nobg.mov`` (ProRes → qtrle → png).

    Uses robust ffmpeg resolution (not PATH-only) and raw BGRA pipe like CapCut export.
    """
    from hybrid_editor.export.ffmpeg_bin import resolve_ffmpeg

    ffmpeg = resolve_ffmpeg("ffmpeg")
    if not ffmpeg or not frames_bgra:
        if not frames_bgra:
            return None
        logger.warning(
            "FFmpeg not found — cannot write *_full_nobg.mov (alpha PNG dumps alone are not the deliverable). "
            "Install ffmpeg or set FFMPEG_PATH."
        )
        return None

    out_path = Path(out_path)
    # 1) ProRes 4444 (best match to Videoeditor CapCut export)
    prores_args = [
        "-c:v",
        "prores_ks",
        "-profile:v",
        "4444",
        "-pix_fmt",
        "yuva444p10le",
        "-vendor",
        "apl0",
        "-alpha_bits",
        "16",
    ]
    got = _pipe_bgra_mov(
        frames_bgra, out_path, fps=fps, ffmpeg=ffmpeg, vcodec_args=prores_args, label="ProRes"
    )
    if got:
        return got
    got = _png_seq_mov(
        frames_bgra, out_path, fps=fps, ffmpeg=ffmpeg, vcodec_args=prores_args, label="prores"
    )
    if got:
        return got

    # 2) QuickTime Animation
    qtrle_args = ["-c:v", "qtrle", "-pix_fmt", "argb"]
    got = _pipe_bgra_mov(
        frames_bgra, out_path, fps=fps, ffmpeg=ffmpeg, vcodec_args=qtrle_args, label="qtrle"
    )
    if got:
        return got
    got = _png_seq_mov(
        frames_bgra, out_path, fps=fps, ffmpeg=ffmpeg, vcodec_args=qtrle_args, label="qtrle"
    )
    if got:
        return got

    # 3) PNG codec inside MOV (true alpha, widely supported by VLC/CapCut)
    png_args = ["-c:v", "png", "-pix_fmt", "rgba"]
    got = _pipe_bgra_mov(
        frames_bgra, out_path, fps=fps, ffmpeg=ffmpeg, vcodec_args=png_args, label="png"
    )
    if got:
        return got
    got = _png_seq_mov(
        frames_bgra, out_path, fps=fps, ffmpeg=ffmpeg, vcodec_args=png_args, label="png"
    )
    if got:
        return got

    logger.warning("All alpha MOV mux attempts failed for %s", out_path)
    return None


def try_qtrle_alpha(
    frames_bgra: list[np.ndarray],
    out_path: Path,
    *,
    fps: float = 25.0,
) -> Optional[str]:
    """Fallback QuickTime Animation (qtrle) alpha MOV when ProRes mux is hard."""
    from hybrid_editor.export.ffmpeg_bin import resolve_ffmpeg

    ffmpeg = resolve_ffmpeg("ffmpeg")
    if not ffmpeg or not frames_bgra:
        return None
    qtrle_args = ["-c:v", "qtrle", "-pix_fmt", "argb"]
    got = _pipe_bgra_mov(
        frames_bgra, out_path, fps=fps, ffmpeg=ffmpeg, vcodec_args=qtrle_args, label="qtrle"
    )
    if got:
        return got
    return _png_seq_mov(
        frames_bgra, out_path, fps=fps, ffmpeg=ffmpeg, vcodec_args=qtrle_args, label="qtrle"
    )


def _checker_preview_from_bgra(
    frames_bgra: list[np.ndarray],
    out_path: Path,
    *,
    fps: float,
) -> Optional[str]:
    """Build checkerboard H.264 preview directly from baked BGRA (no silent alpha-only)."""
    if not frames_bgra:
        return None
    frames_bgr: list[np.ndarray] = []
    frames_alpha: list[np.ndarray] = []
    for fr in frames_bgra:
        if fr.ndim != 3 or fr.shape[2] < 4:
            continue
        frames_bgr.append(fr[:, :, :3].copy())
        frames_alpha.append((fr[:, :, 3].astype(np.float32) / 255.0))
    if not frames_bgr:
        return None
    return write_preview_mp4(frames_bgr, frames_alpha, out_path, fps=fps)


def finalize_bgcut_exports(
    *,
    media_stem: str,
    out_dir: Path,
    preview_mp4: Optional[str],
    frames_bgra: list[np.ndarray],
    fps: float,
    scope: str = "full",
) -> tuple[Optional[str], Optional[str]]:
    """Write Videoeditor-style ``{stem}_full_nobg.mov`` + companion ``_preview.mp4``.

    Returns ``(prores_or_qtrle_or_png_mov, companion_preview_mp4)``.
    Primary deliverable is the ``.mov`` — not ``alpha/*.png``.
    When an in-memory preview path is missing, synthesizes the checker companion
    from ``frames_bgra`` so the UI never ends with MOV-only / silent alpha dumps.
    """
    from hybrid_editor.export.bgcut import ensure_bgcut_dir, nobg_mov_path, nobg_preview_path, nobg_stem

    out_dir = ensure_bgcut_dir(out_dir)
    mov = nobg_mov_path(media_stem, out_dir=out_dir, scope=scope)
    expected = nobg_preview_path(media_stem, out_dir=out_dir, scope=scope)
    prores = try_prores_alpha(frames_bgra, mov, fps=fps) if frames_bgra else None
    if frames_bgra and not prores:
        logger.error(
            "MUX FAIL: cannot write %s (ffmpeg/ProRes/qtrle/png). "
            "Do not use alpha/ PNG dumps as the deliverable — set FFMPEG_PATH and re-export.",
            mov,
        )
    # Companion preview next to the MOV (Videoeditor open-output pattern)
    companion_stem = f"{nobg_stem(media_stem, scope)}_preview"
    companion = write_windows_companion(
        preview_mp4,
        out_dir,
        stem=companion_stem,
    )
    if companion and Path(companion).is_file() and Path(companion).resolve() != expected.resolve():
        try:
            shutil.copy2(companion, expected)
            companion = str(expected.resolve())
        except OSError:
            pass
    # Guarantee checker _preview.mp4 whenever we have baked frames (UI + Films&TV).
    if (not companion or not Path(companion).is_file()) and frames_bgra:
        logger.info("Synthesizing checker companion preview → %s", expected)
        companion = _checker_preview_from_bgra(frames_bgra, expected, fps=fps)
    if prores and (not companion or not Path(str(companion)).is_file()):
        logger.error(
            "PREVIEW MISSING after bake: %s exists but checker %s was not written",
            prores,
            expected,
        )
    if not prores and frames_bgra:
        # Never report success on alpha-only leftovers — companion alone is not the master.
        logger.error(
            "PRIMARY OUTPUT MISSING: %s — alpha PNG dumps (if any) are debug-only",
            mov,
        )
    return prores, companion
