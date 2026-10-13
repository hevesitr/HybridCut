"""preview-fast — Gyors always shows cutout; soft MobileNet crush never wipes."""

from __future__ import annotations

import sys
from pathlib import Path

import cv2
import numpy as np
import pytest

BACKEND = Path(__file__).resolve().parents[1]
ROOT = BACKEND.parent
sys.path.insert(0, str(BACKEND))

STAMP = "2026-10-13-preview-fast"


def test_stamp():
    assert (ROOT / "SYNC_VERSION.txt").read_text(encoding="utf-8").strip() == STAMP
    assert (ROOT / "backend/hybrid_editor/FEATURE_PREVIEW_FAST.txt").read_text(
        encoding="utf-8"
    ).strip() == STAMP
    assert (ROOT / "PASTE_PREVIEW_FAST_GITHUB.ps1").is_file()
    assert (ROOT / "PASTE_PREVIEW_FAST_INSTALL.ps1").is_file()


def test_crush_keeps_soft_mobilenet_matte():
    """Regression: peak~0.32 MobileNet must not become all-zero after crush."""
    from hybrid_editor.engines.max_quality import MaxQualityEngine
    from hybrid_editor.media.video_io import is_matte_empty

    h, w = 360, 640
    a = np.zeros((h, w), np.float32)
    cv2.ellipse(a, (w // 3, h // 2), (70, 140), 0, 0, 360, 0.30, -1)
    cv2.ellipse(a, (2 * w // 3, h // 2), (70, 140), 0, 0, 360, 0.28, -1)
    a = cv2.GaussianBlur(a, (0, 0), 6)
    assert float(a.max()) < 0.36
    out = MaxQualityEngine._crush_soft_shadow_alpha(a)
    assert not is_matte_empty(out)
    assert float(out.max()) > 0.2
    assert float((out > 0.15).mean()) > 0.05


def test_gyors_preview_recovers_slab(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("HYBRID_ORT_PROVIDER", "cpu")
    from hybrid_editor.session import EditorSession

    rng = np.random.default_rng(11)
    h, w = 480, 854
    bgr = np.clip(
        np.full((h, w, 3), (42, 58, 95), np.int16) + rng.integers(-16, 16, (h, w, 3), dtype=np.int16),
        0,
        255,
    ).astype(np.uint8)
    cv2.rectangle(bgr, (0, h // 2), (w, h), (60, 75, 115), -1)
    for cx, body, head in (
        (w // 3, (55, 85, 195), (95, 145, 215)),
        (2 * w // 3, (75, 65, 155), (65, 95, 185)),
    ):
        cv2.ellipse(bgr, (cx, h // 2 + 30), (70, 160), 0, 0, 360, body, -1)
        cv2.ellipse(bgr, (cx, h // 2 - 100), (42, 55), 0, 0, 360, head, -1)
    out = tmp_path / "indoor2.mp4"
    vw = cv2.VideoWriter(str(out), cv2.VideoWriter_fourcc(*"mp4v"), 24, (w, h))
    for _ in range(4):
        vw.write(bgr)
    vw.release()

    sess = EditorSession()
    sess.open_media(out)
    sess._suppress_auto_max = True
    # Force soft-slab RVM (the MobileNet failure mode).
    sess.engine._matte = lambda frame: np.full(frame.shape[:2], 0.55, np.float32)  # type: ignore[method-assign]
    fr = sess.preview(0.0)
    assert fr.meta.get("matte_empty") is False, fr.meta
    assert not fr.meta.get("matte_error"), fr.meta
    assert fr.jpeg_b64 and len(fr.jpeg_b64) > 1000


def test_proxy_long_default_fast():
    from hybrid_editor.engines.fast_rvm import FastEngine

    eng = FastEngine(prefer_quality=False)
    assert eng._proxy_long <= 540  # noqa: SLF001


def test_ui_no_gray_slab_toast_wording():
    app = (ROOT / "frontend/src/App.tsx").read_text(encoding="utf-8")
    # Old scary toast must not be the primary copy anymore.
    assert "egyenletes szürke lap" not in app or "automatikus javítás" in app
