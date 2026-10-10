"""Primary bgcut deliverable is ``*_full_nobg.mov`` (not ``alpha/`` PNG dumps)."""

from __future__ import annotations

import sys
from pathlib import Path

import cv2
import numpy as np
import pytest

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

from hybrid_editor.export.bgcut import (
    dump_alpha_frames_enabled,
    nobg_mov_path,
    nobg_stem,
)
from hybrid_editor.export.composer import finalize_bgcut_exports, try_prores_alpha
from hybrid_editor.export.ffmpeg_bin import resolve_ffmpeg


def test_path_template_ends_with_full_nobg_mov(tmp_path: Path):
    assert nobg_stem("29308762a").endswith("_full_nobg")
    mov = nobg_mov_path("29308762a", out_dir=tmp_path)
    assert str(mov).endswith("_full_nobg.mov")
    assert mov.name == "29308762a_full_nobg.mov"


def test_dump_alpha_off_by_default(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("HYBRID_BGCUT_DUMP_ALPHA", raising=False)
    assert dump_alpha_frames_enabled() is False
    monkeypatch.setenv("HYBRID_BGCUT_DUMP_ALPHA", "1")
    assert dump_alpha_frames_enabled() is True


@pytest.mark.skipif(resolve_ffmpeg("ffmpeg") is None, reason="ffmpeg required for MOV mux")
def test_try_prores_writes_mov(tmp_path: Path):
    frames = []
    for i in range(4):
        bgra = np.zeros((48, 64, 4), dtype=np.uint8)
        bgra[:, :, 0] = 40
        bgra[:, :, 1] = 80
        bgra[:, :, 2] = 200
        bgra[:, :, 3] = 200 if i % 2 == 0 else 40
        frames.append(bgra)
    out = tmp_path / "sample_full_nobg.mov"
    got = try_prores_alpha(frames, out, fps=12.0)
    assert got is not None
    assert Path(got).is_file()
    assert Path(got).stat().st_size > 256
    assert Path(got).name.endswith("_full_nobg.mov")


@pytest.mark.skipif(resolve_ffmpeg("ffmpeg") is None, reason="ffmpeg required for MOV mux")
def test_finalize_bgcut_primary_mov(tmp_path: Path):
    frames = []
    for _ in range(3):
        bgra = np.zeros((32, 48, 4), dtype=np.uint8)
        bgra[:, :, 2] = 180
        bgra[:, :, 3] = 220
        frames.append(bgra)
    mov, prev = finalize_bgcut_exports(
        media_stem="29308762a",
        out_dir=tmp_path,
        preview_mp4=None,
        frames_bgra=frames,
        fps=10.0,
    )
    assert mov is not None
    assert Path(mov).name == "29308762a_full_nobg.mov"
    assert Path(mov).is_file()
    # Checker companion always synthesized when preview_mp4 was missing
    assert prev is not None
    assert Path(prev).is_file()
    assert Path(prev).name == "29308762a_full_nobg_preview.mp4"
    # alpha/ not created by finalize
    assert not (tmp_path / "alpha").exists()
