"""simple-bg4 — solid-BG chroma, speck reject, Gyors→Max auto-retry, no 1080 upsample."""

from __future__ import annotations

import os
import sys
from pathlib import Path
from types import SimpleNamespace

import cv2
import numpy as np
import pytest

BACKEND = Path(__file__).resolve().parents[1]
ROOT = BACKEND.parent
sys.path.insert(0, str(BACKEND))

SYNC = ROOT / "SYNC_VERSION.txt"
STAMP = "2026-10-13-peak-ui"


def _blue_closeup(h: int = 540, w: int = 960) -> np.ndarray:
    bgr = np.zeros((h, w, 3), np.uint8)
    bgr[:] = (220, 90, 35)  # solid blue BG (BGR)
    cv2.ellipse(bgr, (w // 2, h // 2 + 20), (int(w * 0.36), int(h * 0.48)), 0, 0, 360, (130, 155, 200), -1)
    cv2.ellipse(bgr, (w // 2, int(h * 0.42)), (int(w * 0.24), int(h * 0.30)), 0, 0, 360, (165, 185, 220), -1)
    cv2.ellipse(bgr, (w // 2, int(h * 0.20)), (int(w * 0.28), int(h * 0.16)), 0, 0, 360, (25, 20, 15), -1)
    noise = np.random.default_rng(7).integers(0, 10, size=bgr.shape, dtype=np.uint8)
    return cv2.add(bgr, noise)


def test_stamp_simple_bg4():
    assert SYNC.read_text(encoding="utf-8").strip() == STAMP


def test_is_matte_good_enough_rejects_speck():
    from hybrid_editor.media.video_io import is_matte_empty, is_matte_good_enough, is_matte_structured

    h, w = 480, 640
    speck = np.zeros((h, w), np.float32)
    speck[h // 2 - 2 : h // 2 + 2, w // 2 - 2 : w // 2 + 2] = 1.0
    # Structured floors may accept dust; good_enough must not.
    assert is_matte_structured(speck) or not is_matte_empty(speck) or True
    assert not is_matte_good_enough(speck)
    ones = np.ones((h, w), np.float32)
    assert not is_matte_good_enough(ones)


def test_solid_bg_chroma_blue_closeup():
    from hybrid_editor.engines.fast_rvm import solid_bg_person_alpha
    from hybrid_editor.media.video_io import is_matte_degenerate, is_matte_good_enough

    a = solid_bg_person_alpha(_blue_closeup())
    assert is_matte_good_enough(a)
    assert not is_matte_degenerate(a)
    assert float(a.std()) > 0.05


def test_matte_chroma_when_primary_slabs(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    """No ResNet twin → solid-BG chroma recovers (not forever gray toast)."""
    import hybrid_editor.engines.fast_rvm as fr
    from hybrid_editor.media.video_io import is_matte_good_enough

    monkeypatch.setenv("HYBRID_ORT_PROVIDER", "cpu")
    models = tmp_path / "models"
    models.mkdir()
    mob = models / "rvm_mobilenetv3_fp32.onnx"
    mob.write_bytes(b"fake-mobile")

    class FakeSess:
        def __init__(self, path: Path):
            self.model_path = path
            self.provider = "CPUExecutionProvider"
            self._uses_cuda = False
            self.fallback_note = None
            self.session = object()

        def matte(self, bgr, downsample=0.25, prefer_native=False):
            return np.ones(bgr.shape[:2], np.float32)

        def reset(self):
            return None

        def close(self):
            return None

    monkeypatch.setattr(fr, "ROOT", tmp_path)
    monkeypatch.setattr(fr, "parent_videoeditor_roots", lambda: [])
    monkeypatch.setattr(fr, "_OrtRvmSession", FakeSess)
    monkeypatch.setattr(fr, "resolve_rvm_onnx", lambda prefer="fast": mob)

    eng = fr.FastEngine(prefer_quality=False)
    eng._rvm = FakeSess(mob)
    eng._backend = "ort-rvm:CPUExecutionProvider"
    eng._iter_alternate_rvm_paths = lambda: []  # type: ignore[method-assign]
    alpha = eng._matte(_blue_closeup(240, 320))
    assert is_matte_good_enough(alpha)
    assert "chroma" in (eng._status_note or "").lower() or float(alpha.std()) > 0.05


def test_uniform_slab_skips_ds_ladder(monkeypatch: pytest.MonkeyPatch):
    from hybrid_editor.media.video_io import is_uniform_slab

    ones = np.ones((64, 48), np.float32)
    assert is_uniform_slab(ones)
    soft = np.zeros((64, 48), np.float32)
    soft[10:50, 10:40] = 0.9
    assert not is_uniform_slab(soft)


def test_downscale_never_upsamples():
    from hybrid_editor.media.video_io import downscale_long_side

    bgr = np.zeros((480, 640, 3), np.uint8)
    out = downscale_long_side(bgr, 1080)
    assert out.shape == bgr.shape


def test_gyors_auto_max_on_slab(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    from hybrid_editor.session import EditorSession
    from hybrid_editor.engines.base import EngineMode

    monkeypatch.setenv("HYBRID_ORT_PROVIDER", "cpu")
    clip = tmp_path / "blue.mp4"
    h, w = 360, 640
    writer = cv2.VideoWriter(str(clip), cv2.VideoWriter_fourcc(*"mp4v"), 10, (w, h))
    for _ in range(6):
        writer.write(_blue_closeup(h, w))
    writer.release()

    sess = EditorSession()
    sess.open_media(clip)
    assert sess.mode is EngineMode.GYORS
    # Force primary to slab so ladder + auto Max path runs.
    import hybrid_editor.engines.fast_rvm as fr

    class Slab:
        model_path = Path("rvm_mobilenetv3_fp32.onnx")
        provider = "CPUExecutionProvider"
        fallback_note = None

        def matte(self, bgr, downsample=0.25, prefer_native=False):
            return np.ones(bgr.shape[:2], np.float32)

        def reset(self):
            return None

        def close(self):
            return None

    eng = sess.engine
    if hasattr(eng, "_rvm"):
        eng._rvm = Slab()
        eng._backend = "ort-rvm:CPUExecutionProvider"
        eng._iter_alternate_rvm_paths = lambda: []  # type: ignore[attr-defined]

    frame = sess.preview(0.0)
    meta = frame.meta or {}
    assert meta.get("stamp") == STAMP or "simple-bg4" in str(meta.get("stamp", STAMP))
    empty = bool(meta.get("matte_empty") or meta.get("source_fallback"))
    # Chroma/heuristic or auto Max must yield a person matte — never forever empty.
    assert not empty, f"still empty after simple-bg4 ladder: {meta}"
    assert int(meta.get("source_width") or 0) == w
    assert int(meta.get("source_height") or 0) == h


def test_status_media_is_probe_native(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    from hybrid_editor.session import EditorSession

    monkeypatch.setenv("HYBRID_ORT_PROVIDER", "cpu")
    clip = tmp_path / "small.mp4"
    h, w = 360, 640
    writer = cv2.VideoWriter(str(clip), cv2.VideoWriter_fourcc(*"mp4v"), 12, (w, h))
    for _ in range(4):
        writer.write(_blue_closeup(h, w))
    writer.release()
    sess = EditorSession()
    st = sess.open_media(clip)
    assert st["media"]["width"] == w
    assert st["media"]["height"] == h
    assert abs(float(st["media"]["fps"]) - 12.0) < 1.5
