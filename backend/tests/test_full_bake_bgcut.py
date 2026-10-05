"""Full-duration bake + Videoeditor C:\\bgcut\\*_full_nobg.mov path template."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import cv2
import numpy as np
import pytest

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

from hybrid_editor.export.bgcut import (
    default_bgcut_dir,
    ensure_bgcut_dir,
    nobg_mov_path,
    nobg_preview_path,
    nobg_stem,
)
from hybrid_editor.session import EditorSession


def _write_sample(path: Path, *, seconds: float = 2.0, fps: float = 24.0, size=(160, 90)) -> None:
    w, h = size
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    writer = cv2.VideoWriter(str(path), fourcc, fps, (w, h))
    n = max(1, int(round(seconds * fps)))
    for i in range(n):
        frame = np.zeros((h, w, 3), np.uint8)
        frame[:] = (20, 80, 30)
        cv2.circle(frame, (30 + (i % 40), 45), 18, (40, 50, 200), -1)
        writer.write(frame)
    writer.release()


def test_nobg_path_template_matches_videoeditor(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("HYBRID_BGCUT_DIR", str(tmp_path / "bgcut"))
    d = default_bgcut_dir()
    assert d == tmp_path / "bgcut"
    ensure_bgcut_dir(d)
    assert d.is_dir()

    assert nobg_stem("29308762a") == "29308762a_full_nobg"
    assert nobg_stem("29308762a_full_nobg") == "29308762a_full_nobg"
    mov = nobg_mov_path("29308762a", out_dir=d)
    assert mov == d / "29308762a_full_nobg.mov"
    prev = nobg_preview_path("29308762a", out_dir=d)
    assert prev == d / "29308762a_full_nobg_preview.mp4"


def test_win_default_bgcut_is_c_drive(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("HYBRID_BGCUT_DIR", raising=False)
    monkeypatch.setattr(sys, "platform", "win32")
    assert default_bgcut_dir() == Path(r"C:\bgcut")


def test_bake_default_max_frames_is_full_duration(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Export must not cap at 48 preview frames — duration ≈ source In/Out."""
    monkeypatch.setenv("HYBRID_BGCUT_DIR", str(tmp_path / "bgcut"))
    sample = tmp_path / "29308762a.mp4"
    fps = 24.0
    seconds = 2.0
    _write_sample(sample, seconds=seconds, fps=fps)

    session = EditorSession()
    session.set_mode("gyors")
    session.open_media(sample)
    # Explicit full range (matches UI In 0 / Out ~duration)
    session.update_timeline(in_sec=0.0, out_sec=seconds, playhead_sec=0.0)

    out = tmp_path / "bgcut"
    # max_frames=None — the Exportálás hanggal contract (was wrongly 48)
    result = session.bake(out, max_frames=None, async_job=False)
    assert result.ok
    expected = int(round(seconds * fps))
    # Allow ±2 frames for seek/EOF edge
    assert abs(result.frames_written - expected) <= 2, (
        f"frames_written={result.frames_written} expected~{expected} "
        f"(cap bug would yield 48 or less on longer clips)"
    )
    br = result.bake_range or {}
    assert br.get("max_frames_cap") is None
    assert abs(float(br.get("duration_sec", 0)) - seconds) < 0.15

    mov = out / "29308762a_full_nobg.mov"
    prev = out / "29308762a_full_nobg_preview.mp4"
    # ProRes/qtrle may be unavailable in CI — path template + companion still required intent
    if result.prores_mov:
        assert Path(result.prores_mov).name == "29308762a_full_nobg.mov"
        assert Path(result.prores_mov).is_file()
    assert result.preview_mp4
    assert "full_nobg" in Path(result.preview_mp4).name or Path(result.preview_mp4).is_file()
    # Companion naming preferred
    if prev.is_file():
        assert Path(result.preview_mp4).resolve() == prev.resolve() or Path(result.preview_mp4).is_file()


def test_bake_body_default_is_none():
    """API BakeBody must default max_frames to None (not the old 48 preview sample)."""
    routes_py = Path(__file__).resolve().parents[1] / "hybrid_editor" / "api" / "routes.py"
    text = routes_py.read_text(encoding="utf-8")
    assert "max_frames: Optional[int] = None" in text
    assert "max_frames: Optional[int] = 48" not in text
    api_ts = (
        Path(__file__).resolve().parents[2]
        / "frontend"
        / "src"
        / "lib"
        / "api.ts"
    )
    api_text = api_ts.read_text(encoding="utf-8")
    assert "max_frames: number | null = null" in api_text
    assert "max_frames = 48" not in api_text
    app_tsx = Path(__file__).resolve().parents[2] / "frontend" / "src" / "App.tsx"
    app_text = app_tsx.read_text(encoding="utf-8")
    assert "api.bake(null," in app_text
    assert "api.bake(48," not in app_text


def test_api_default_out_dir_is_bgcut(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("HYBRID_BGCUT_DIR", str(tmp_path / "bgcut"))
    from hybrid_editor.export.bgcut import default_bgcut_dir

    assert default_bgcut_dir() == tmp_path / "bgcut"
