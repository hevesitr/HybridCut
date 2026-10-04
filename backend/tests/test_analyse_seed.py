"""Sparse analyse + seed mask wiring."""

from __future__ import annotations

import sys
import time
from pathlib import Path

import cv2
import numpy as np
import pytest

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

from hybrid_editor import ROOT
from hybrid_editor.cache.analyse import SparseAnalyser
from hybrid_editor.cache.mask_store import MASK_RATE, MaskStore, mask_dir
from hybrid_editor.cache.seed_mask import decode_alpha_png_b64, encode_alpha_png_b64
from hybrid_editor.engines.max_quality import MaxQualityEngine
from hybrid_editor.session import EditorSession


def _tiny_mp4(path: Path, n: int = 12, fps: float = 12.0) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    w, h = 160, 120
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    writer = cv2.VideoWriter(str(path), fourcc, fps, (w, h))
    for i in range(n):
        frame = np.zeros((h, w, 3), np.uint8)
        frame[:] = (30, 80, 40)
        cv2.circle(frame, (40 + i * 4, 60), 28, (40, 50, 200), -1)
        writer.write(frame)
    writer.release()


def test_mask_rate_constant():
    assert MASK_RATE == 10


def test_sparse_analyse_writes_masks(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    media = tmp_path / "clip.mp4"
    _tiny_mp4(media)
    monkeypatch.setattr("hybrid_editor.cache.analyse.mask_dir", lambda root, p, subject="person": tmp_path / "masks")

    analyser = SparseAnalyser()

    def matte(bgr):
        a = np.zeros(bgr.shape[:2], np.float32)
        a[20:80, 20:80] = 0.8
        return a

    st = analyser.start(
        root=tmp_path,
        media_path=media,
        duration_sec=1.0,
        matte_fn=matte,
        mask_rate=5,
        in_sec=0.0,
        out_sec=0.8,
    )
    assert st["analyse_running"] is True
    deadline = time.time() + 8.0
    while analyser.state.running and time.time() < deadline:
        time.sleep(0.05)
    assert not analyser.state.running
    assert analyser.state.masks_written >= 3
    store = MaskStore(tmp_path / "masks")
    hit = store.get_alpha(0.2)
    assert hit is not None


def test_seed_roundtrip_and_max_engine():
    a = np.zeros((48, 64), np.float32)
    a[10:40, 10:50] = 1.0
    b64 = encode_alpha_png_b64(a)
    back = decode_alpha_png_b64(b64)
    assert back.shape == (48, 64)
    assert float(back[25, 30]) > 0.9

    eng = MaxQualityEngine()
    eng.set_user_seed(a)
    assert eng.user_seed is not None
    eng.clear_user_seed()
    assert eng.user_seed is None


def test_session_timeline_actions(tmp_path: Path):
    media = tmp_path / "s.mp4"
    _tiny_mp4(media, n=18, fps=12)
    session = EditorSession()
    st = session.open_media(media)
    assert st["timeline"] is not None
    assert len(st["timeline"]["clips"]) == 1
    st2 = session.timeline_action("duplicate")
    assert len(st2["timeline"]["clips"]) == 2
    session.update_timeline(playhead_sec=0.4)
    st3 = session.timeline_action("cut", t_sec=0.4)
    assert len(st3["timeline"]["clips"]) >= 2

    # Seed via session
    seed = np.zeros((40, 40), np.float32)
    seed[5:35, 5:35] = 0.95
    session.set_mode("max")
    st4 = session.set_seed_mask(encode_alpha_png_b64(seed))
    assert st4["seed_mask"] is True
    g = session.get_seed_mask()
    assert g["seed_mask"] is True
    session.clear_seed_mask()
    assert session.get_seed_mask()["seed_mask"] is False
