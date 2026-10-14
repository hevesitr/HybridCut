"""full-body-fast — hole-fill heads + CPU Max ~45s bake path."""

from __future__ import annotations

import sys
from pathlib import Path

import cv2
import numpy as np
import pytest

BACKEND = Path(__file__).resolve().parents[1]
ROOT = BACKEND.parent
sys.path.insert(0, str(BACKEND))

STAMP = "2026-10-14-restore-rvm-fast"


def test_stamp():
    assert (ROOT / "SYNC_VERSION.txt").read_text(encoding="utf-8").strip() == STAMP
    assert (ROOT / "backend/hybrid_editor/FEATURE_FULL_BODY_FAST.txt").read_text(
        encoding="utf-8"
    ).strip() == STAMP
    paste = ROOT / "PASTE_FULL_BODY_FAST_INSTALL.ps1"
    assert paste.is_file()
    assert STAMP in paste.read_text(encoding="utf-8")


def test_fill_person_holes_closes_crown_gap():
    from hybrid_editor.engines.videoeditor_polish import fill_person_holes

    h, w = 200, 160
    a = np.zeros((h, w), np.float32)
    cv2.ellipse(a, (w // 2, h // 2 + 10), (50, 80), 0, 0, 360, 0.95, -1)
    # Hole in top of head
    cv2.circle(a, (w // 2, h // 2 - 50), 18, 0.0, -1)
    assert float(a[h // 2 - 50, w // 2]) < 0.1
    out = fill_person_holes(a, min_fg=0.2, close_px=15, fill_value=0.9)
    assert float(out[h // 2 - 50, w // 2]) > 0.5


def test_crush_keeps_soft_hair_band():
    from hybrid_editor.engines.max_quality import MaxQualityEngine

    h, w = 240, 180
    a = np.zeros((h, w), np.float32)
    # Solid body
    cv2.ellipse(a, (w // 2, h // 2 + 30), (55, 90), 0, 0, 360, 0.9, -1)
    # Soft hair crown (would be killed by old crush hard>=0.55)
    cv2.ellipse(a, (w // 2, h // 2 - 55), (40, 35), 0, 0, 360, 0.42, -1)
    out = MaxQualityEngine._crush_soft_shadow_alpha(a)
    # Crown center should survive
    assert float(out[h // 2 - 55, w // 2]) > 0.25


def test_crush_keeps_body_not_sliver():
    """matte-safe: prefer full body over aggressive ghost kill that ate silhouettes."""
    from hybrid_editor.engines.max_quality import MaxQualityEngine
    from hybrid_editor.media.video_io import is_matte_sliver

    h, w = 240, 220
    a = np.zeros((h, w), np.float32)
    cv2.ellipse(a, (70, h // 2), (40, 70), 0, 0, 360, 0.95, -1)
    # Soft body aura (must remain part of person, not crushed to a strip)
    cv2.ellipse(a, (70, h // 2), (55, 85), 0, 0, 360, 0.24, 8)
    out = MaxQualityEngine._crush_soft_shadow_alpha(a)
    assert float(out[h // 2, 70]) > 0.8
    assert not is_matte_sliver(out)
    ys, xs = np.where(out > 0.15)
    assert (xs.max() - xs.min() + 1) / float(w) >= 0.25


def test_cpu_max_fast_when_env_cpu(monkeypatch: pytest.MonkeyPatch):
    from hybrid_editor.engines.max_quality import MaxQualityEngine

    monkeypatch.setenv("HYBRID_ORT_PROVIDER", "cpu")
    monkeypatch.delenv("HYBRID_CPU_MAX_FULLRES", raising=False)
    eng = MaxQualityEngine()
    # Even if live session claims CUDA, prefer=cpu must force fast path.
    eng._fast._rvm = type(
        "R",
        (),
        {"_uses_cuda": True, "provider": "CUDAExecutionProvider"},
    )()
    assert eng._cpu_max_fast_enabled() is True


def test_eta_cpu_max_still_near_45s():
    from hybrid_editor.eta import estimate_bake_sec

    cpu = estimate_bake_sec(10.0, 24.0, 1920, 1080, "max", cpu_ort=True)
    assert 35 <= cpu <= 90


def test_ui_keeps_preview_on_mode_reclick():
    """Regression: Max/Gyors re-click must not setPreview(null) / blank Cutout."""
    app = (ROOT / "frontend/src/App.tsx").read_text(encoding="utf-8")
    mode = (ROOT / "frontend/src/components/ModeSwitcher.tsx").read_text(encoding="utf-8")
    assert "lastGoodPreview" in app
    assert "previewGen" in app
    assert "setPreview(null)" in app  # still used for new project
    # Mode change path must not blank before re-matte
    assert "Clear stale empty matte" not in app
    assert 'if (mode !== "max") onChange("max")' in mode or "mode !== \"max\"" in mode
    assert "PASTE_FULL_BODY_FAST_GITHUB.ps1" in (ROOT / "PASTE_FULL_BODY_FAST_GITHUB.ps1").read_text(
        encoding="utf-8"
    ) or (ROOT / "PASTE_FULL_BODY_FAST_GITHUB.ps1").is_file()
