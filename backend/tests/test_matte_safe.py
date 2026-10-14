"""matte-safe — never ship vertical strip / sliver person mattes."""

from __future__ import annotations

import sys
from pathlib import Path

import cv2
import numpy as np

BACKEND = Path(__file__).resolve().parents[1]
ROOT = BACKEND.parent
sys.path.insert(0, str(BACKEND))

STAMP = "2026-10-14-restore-rvm-fast2"


def test_stamp():
    assert (ROOT / "SYNC_VERSION.txt").read_text(encoding="utf-8").strip() == STAMP
    assert (ROOT / "backend/hybrid_editor/FEATURE_MATTE_SAFE.txt").read_text(
        encoding="utf-8"
    ).strip() == STAMP
    gh = ROOT / "PASTE_MATTE_SAFE_GITHUB.ps1"
    assert gh.is_file()
    assert all(b < 128 for b in gh.read_bytes())


def test_is_matte_sliver_detects_strip():
    from hybrid_editor.media.video_io import is_matte_sliver

    h, w = 480, 854
    a = np.zeros((h, w), np.float32)
    a[40 : h - 40, w // 2 - 28 : w // 2 + 28] = 0.9
    assert is_matte_sliver(a)
    # Wide person is not a sliver
    b = np.zeros((h, w), np.float32)
    cv2.ellipse(b, (w // 2, h // 2), (200, 220), 0, 0, 360, 0.9, -1)
    assert not is_matte_sliver(b)


def test_crush_keeps_soft_body_not_ridge_strip():
    from hybrid_editor.engines.max_quality import MaxQualityEngine
    from hybrid_editor.media.video_io import is_matte_empty, is_matte_sliver

    h, w = 720, 1280
    a = np.zeros((h, w), np.float32)
    cv2.ellipse(a, (w // 2, h // 2 + 20), (260, 300), 0, 0, 360, 0.26, -1)
    a = cv2.GaussianBlur(a, (0, 0), 18)
    cv2.rectangle(a, (w // 2 - 40, h // 8), (w // 2 + 40, 7 * h // 8), 0.42, -1)
    a = cv2.GaussianBlur(a, (0, 0), 6)
    out = MaxQualityEngine._crush_soft_shadow_alpha(a)
    assert not is_matte_empty(out)
    assert not is_matte_sliver(out)
    ys, xs = np.where(out > 0.15)
    assert xs.size > 0
    width_frac = (xs.max() - xs.min() + 1) / float(w)
    assert width_frac >= 0.20
    assert float((out > 0.15).mean()) >= 0.10
