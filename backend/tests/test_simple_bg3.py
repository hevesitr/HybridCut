"""simple-bg3 — close-up CPU matte + MobileNet→ResNet auto-switch."""

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
STAMP = "2026-10-13-peak-cutout"


def _closeup_bgr(h: int = 540, w: int = 960) -> np.ndarray:
    bgr = np.zeros((h, w, 3), np.uint8)
    bgr[:] = (40, 35, 30)
    cv2.ellipse(bgr, (w // 2, h // 2), (int(w * 0.42), int(h * 0.48)), 0, 0, 360, (90, 80, 70), -1)
    cv2.ellipse(
        bgr, (w // 2, int(h * 0.45)), (int(w * 0.28), int(h * 0.32)), 0, 0, 360, (190, 170, 155), -1
    )
    noise = np.random.default_rng(3).integers(0, 18, size=bgr.shape, dtype=np.uint8)
    return cv2.add(bgr, noise)


def test_stamp_simple_bg3():
    assert SYNC.read_text(encoding="utf-8").strip() == STAMP


def test_closeup_not_false_degenerate():
    from hybrid_editor.media.video_io import (
        is_closeup_person_matte,
        is_matte_degenerate,
        is_matte_empty,
    )

    h, w = 480, 640
    a = np.zeros((h, w), np.float32)
    cv2.ellipse(a, (w // 2, h // 2), (int(w * 0.42), int(h * 0.48)), 0, 0, 360, 1.0, -1)
    a = cv2.GaussianBlur(a, (0, 0), 6)
    assert float((a > 0.15).mean()) > 0.5
    assert is_closeup_person_matte(a)
    assert not is_matte_degenerate(a)
    assert not is_matte_empty(a)
    ones = np.ones((h, w), np.float32)
    assert is_matte_degenerate(ones) and is_matte_empty(ones)


def test_heuristic_closeup_usable():
    from hybrid_editor.engines.fast_rvm import heuristic_person_alpha
    from hybrid_editor.media.video_io import is_matte_degenerate, is_matte_empty

    a = heuristic_person_alpha(_closeup_bgr())
    assert not is_matte_empty(a)
    assert not is_matte_degenerate(a)
    assert float(a.std()) > 0.04


def test_matte_auto_switches_when_primary_slabs(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    """MobileNet-like session slabs → promote ResNet twin from models/."""
    import hybrid_editor.engines.fast_rvm as fr
    from hybrid_editor.media.video_io import is_matte_empty

    monkeypatch.setenv("HYBRID_ORT_PROVIDER", "cpu")
    models = tmp_path / "models"
    models.mkdir()
    mob = models / "rvm_mobilenetv3_fp32.onnx"
    res = models / "rvm_resnet50_fp32.onnx"
    mob.write_bytes(b"fake-mobile")
    res.write_bytes(b"fake-resnet")

    class FakeSess:
        def __init__(self, path: Path):
            self.model_path = path
            self.provider = "CPUExecutionProvider"
            self._uses_cuda = False
            self.fallback_note = None
            self.session = object()

        def matte(self, bgr, downsample=0.25, prefer_native=False):
            del prefer_native
            h, w = bgr.shape[:2]
            if "mobilenet" in self.model_path.name.lower():
                return np.ones((h, w), np.float32)  # gray slab
            a = np.zeros((h, w), np.float32)
            cv2.ellipse(a, (w // 2, h // 2), (w // 5, h // 3), 0, 0, 360, 0.92, -1)
            return a

        def reset(self):
            return None

        def close(self):
            return None

    monkeypatch.setattr(fr, "ROOT", tmp_path)
    monkeypatch.setattr(fr, "parent_videoeditor_roots", lambda: [])
    monkeypatch.setattr(fr, "_OrtRvmSession", FakeSess)
    monkeypatch.setattr(fr, "resolve_rvm_onnx", lambda prefer="fast": mob)

    eng = fr.FastEngine(prefer_quality=False)
    # Inject primary MobileNet slabber (bypass real ORT load).
    eng._rvm = FakeSess(mob)
    eng._backend = "ort-rvm:CPUExecutionProvider"
    alpha = eng._matte(_closeup_bgr(240, 320))
    assert not is_matte_empty(alpha)
    assert "resnet" in Path(eng._rvm.model_path).name.lower()


def test_max_preview_closeup_not_slab_toast(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    from hybrid_editor.session import EditorSession

    monkeypatch.setenv("HYBRID_ORT_PROVIDER", "cpu")
    clip = tmp_path / "close.mp4"
    h, w = 360, 640
    writer = cv2.VideoWriter(str(clip), cv2.VideoWriter_fourcc(*"mp4v"), 10, (w, h))
    for i in range(6):
        writer.write(_closeup_bgr(h, w))
    writer.release()

    sess = EditorSession()
    sess.open_media(clip)
    sess.set_mode("max")
    frame = sess.preview(0.0)
    meta = frame.meta or {}
    assert meta.get("stamp") == STAMP
    empty = bool(meta.get("matte_empty") or meta.get("source_fallback"))
    err = str(meta.get("matte_error") or "")
    assert not empty, f"close-up Max preview still empty/slab: {meta}"
    assert "egyenletes" not in err
