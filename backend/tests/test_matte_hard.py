"""matte-hard — never leave CPU Gyors on gray-slab toast; auto preview on open."""

from __future__ import annotations

import sys
from pathlib import Path

import cv2
import numpy as np
import pytest

BACKEND = Path(__file__).resolve().parents[1]
ROOT = BACKEND.parent
sys.path.insert(0, str(BACKEND))

STAMP = "2026-10-14-restore-rvm-fast2"
SYNC = ROOT / "SYNC_VERSION.txt"
FEATURE = ROOT / "backend" / "hybrid_editor" / "FEATURE_MATTE_HARD.txt"
PASTE = ROOT / "PASTE_MATTE_HARD_INSTALL.ps1"
APP = ROOT / "frontend" / "src" / "App.tsx"


def test_stamp():
    assert SYNC.read_text(encoding="utf-8").strip() == STAMP
    assert FEATURE.read_text(encoding="utf-8").strip() == STAMP
    assert PASTE.is_file()
    assert STAMP in PASTE.read_text(encoding="utf-8")


def test_rim_slab_rejected():
    from hybrid_editor.media.video_io import (
        is_closeup_person_matte,
        is_matte_degenerate,
        is_matte_good_enough,
    )

    a = np.full((480, 640), 0.78, np.float32)
    a[:3] *= 0.15
    a[-3:] *= 0.15
    a[:, :3] *= 0.15
    a[:, -3:] *= 0.15
    assert not is_closeup_person_matte(a)
    assert is_matte_degenerate(a)
    assert not is_matte_good_enough(a)


def test_hard_person_alpha_two_people_textured():
    from hybrid_editor.engines.fast_rvm import hard_person_alpha
    from hybrid_editor.media.video_io import is_matte_degenerate, is_matte_empty

    rng = np.random.default_rng(3)
    h, w = 480, 640
    bgr = rng.integers(0, 255, (h, w, 3), dtype=np.uint8)
    for cx in (w // 3, 2 * w // 3):
        cv2.ellipse(bgr, (cx, h // 2 + 20), (70, 150), 0, 0, 360, (45, 65, 145), -1)
        cv2.ellipse(bgr, (cx, h // 2 - 80), (40, 48), 0, 0, 360, (100, 150, 210), -1)
    a = hard_person_alpha(bgr)
    assert not is_matte_empty(a)
    assert not is_matte_degenerate(a)
    assert float(a.max()) > 0.4


def test_preview_salvages_slab_when_gyors_locked(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Regression: Gyors locked + RVM all-ones must NOT toast egyenletes — hard salvage."""
    monkeypatch.setenv("HYBRID_ORT_PROVIDER", "cpu")
    from hybrid_editor.session import EditorSession

    rng = np.random.default_rng(4)
    h, w = 360, 640
    bgr = rng.integers(0, 255, (h, w, 3), dtype=np.uint8)
    for cx in (w // 3, 2 * w // 3):
        cv2.ellipse(bgr, (cx, h // 2 + 10), (55, 120), 0, 0, 360, (50, 70, 150), -1)
        cv2.ellipse(bgr, (cx, h // 2 - 70), (35, 40), 0, 0, 360, (100, 150, 210), -1)
    out = tmp_path / "two.mp4"
    vw = cv2.VideoWriter(str(out), cv2.VideoWriter_fourcc(*"mp4v"), 10, (w, h))
    for _ in range(4):
        vw.write(bgr)
    vw.release()

    sess = EditorSession()
    st = sess.open_media(out)
    assert st.get("auto_preview_recommended") is True
    sess._suppress_auto_max = True
    sess.engine._matte = lambda frame: np.ones(frame.shape[:2], np.float32)  # type: ignore[method-assign]
    fr = sess.preview(0.0)
    assert fr.meta.get("matte_empty") is False
    assert not fr.meta.get("matte_error")
    assert fr.meta.get("matte_recovered") is True


def test_ui_auto_preview_retry():
    app = APP.read_text(encoding="utf-8")
    assert "retryOnEmpty" in app
    assert "auto Cutout" in app or "auto-run" in app.lower() or "retryOnEmpty: true" in app
