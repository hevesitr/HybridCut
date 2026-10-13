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

STAMP = "2026-10-13-full-body-fast"


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


def test_crush_kills_soft_rim_and_ghost():
    from hybrid_editor.engines.max_quality import MaxQualityEngine

    h, w = 240, 200
    a = np.zeros((h, w), np.float32)
    cv2.ellipse(a, (70, h // 2), (40, 70), 0, 0, 360, 0.95, -1)
    # Milky shoulder halo (grey shadow on checker)
    cv2.ellipse(a, (70, h // 2), (52, 82), 0, 0, 360, 0.22, 10)
    # Detached ghost duplicate
    cv2.ellipse(a, (160, h // 2), (28, 50), 0, 0, 360, 0.28, -1)
    out = MaxQualityEngine._crush_soft_shadow_alpha(a)
    assert float(out[h // 2, 160]) < 0.05  # ghost gone
    # Soft rim outside solid body crushed (not milky grey)
    rim_x = 70 + 48
    assert float(out[h // 2, rim_x]) < 0.15
    # Solid body still opaque
    assert float(out[h // 2, 70]) > 0.8


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
