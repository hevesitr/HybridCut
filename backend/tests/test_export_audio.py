"""Phase 4: FFmpeg audio mux onto preview.mp4."""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

import cv2
import numpy as np
import pytest

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

from hybrid_editor.export.composer import (  # noqa: E402
    AudioSegment,
    media_has_audio,
    mux_audio_onto_video,
    write_preview_mp4,
)


def _make_silent_video(path: Path, *, n: int = 12, fps: float = 12.0, with_tone: bool = False) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    w, h = 160, 120
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    writer = cv2.VideoWriter(str(path), fourcc, fps, (w, h))
    for i in range(n):
        frame = np.zeros((h, w, 3), np.uint8)
        frame[:] = (30, 80, 40)
        cv2.circle(frame, (40 + i * 4, 60), 20, (40, 50, 200), -1)
        writer.write(frame)
    writer.release()
    if with_tone and shutil.which("ffmpeg"):
        out = path.with_name(path.stem + "_a.mp4")
        # 440 Hz tone under the video
        cmd = [
            "ffmpeg",
            "-y",
            "-i",
            str(path),
            "-f",
            "lavfi",
            "-i",
            f"sine=frequency=440:duration={n / fps:.3f}",
            "-shortest",
            "-c:v",
            "copy",
            "-c:a",
            "aac",
            str(out),
        ]
        subprocess.run(cmd, check=True, capture_output=True, timeout=60)
        path.unlink(missing_ok=True)
        out.rename(path)
    return path


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="ffmpeg required")
def test_write_preview_mp4_muxes_audio(tmp_path: Path):
    src = _make_silent_video(tmp_path / "src.mp4", with_tone=True)
    assert media_has_audio(src)

    frames_bgr = []
    frames_alpha = []
    for i in range(8):
        bgr = np.zeros((90, 120, 3), np.uint8)
        bgr[:] = (20, 60, 30)
        a = np.ones((90, 120), np.float32) * (0.4 + 0.05 * (i % 3))
        frames_bgr.append(bgr)
        frames_alpha.append(a)

    out = tmp_path / "preview.mp4"
    result = write_preview_mp4(
        frames_bgr,
        frames_alpha,
        out,
        fps=12.0,
        audio_segments=[AudioSegment(path=str(src), in_sec=0.0, out_sec=0.6)],
        audio_duration_sec=0.6,
    )
    assert result is not None
    assert Path(result).is_file()
    assert media_has_audio(result)


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="ffmpeg required")
def test_mux_audio_onto_video_simple(tmp_path: Path):
    src = _make_silent_video(tmp_path / "clip.mp4", with_tone=True)
    # Silent composed video
    silent = _make_silent_video(tmp_path / "silent.mp4", with_tone=False)
    out = tmp_path / "muxed.mp4"
    got = mux_audio_onto_video(
        silent,
        out,
        [AudioSegment(path=str(src), in_sec=0.0, out_sec=0.5)],
    )
    assert got is not None
    assert media_has_audio(out)
