"""Max accuracy — residual BG islands + cyan fringe decontam (2026-10-05-max-accuracy)."""

from __future__ import annotations

import sys
from pathlib import Path

import cv2
import numpy as np
import pytest

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

from hybrid_editor.engines.fast_rvm import FastEngine
from hybrid_editor.engines.max_quality import MaxQualityEngine
from hybrid_editor.engines.videoeditor_polish import (
    BEST_SPEC,
    apply_color_polish,
    decontaminate_fringe,
    polish_videoeditor,
    suppress_color_spill,
    suppress_residual_bg,
)


def _person_with_residual_bg(h: int = 160, w: int = 120) -> tuple[np.ndarray, np.ndarray]:
    """Synthetic: solid person + large soft BG island near neck/shoulder (screenshot failure)."""
    bgr = np.zeros((h, w, 3), np.uint8)
    bgr[:] = (40, 110, 50)  # greenish BG
    # Person torso + head
    cv2.ellipse(bgr, (w // 2, h // 2 + 10), (32, 48), 0, 0, 360, (70, 90, 200), -1)
    cv2.circle(bgr, (w // 2, h // 2 - 42), 22, (90, 140, 190), -1)
    alpha = np.zeros((h, w), np.float32)
    cv2.ellipse(alpha, (w // 2, h // 2 + 10), (32, 48), 0, 0, 360, 1.0, -1)
    cv2.circle(alpha, (w // 2, h // 2 - 42), 22, 1.0, -1)
    # Soft bridge + residual BG chunk near right shoulder (connected via mid-alpha)
    cv2.ellipse(alpha, (w // 2 + 38, h // 2 - 8), (18, 14), 0, 0, 360, 0.42, -1)
    cv2.circle(alpha, (w // 2 + 48, h // 2 - 18), 12, 0.55, -1)
    # Far disconnected island
    cv2.rectangle(alpha, (4, 4), (22, 28), 0.48, -1)
    alpha = cv2.GaussianBlur(alpha, (0, 0), sigmaX=1.2)
    return bgr, alpha


def _cyan_fringe_frame(h: int = 96, w: int = 80) -> tuple[np.ndarray, np.ndarray]:
    """Red tank top with cyan edge fringe in semi-transparent band."""
    bgr = np.zeros((h, w, 3), np.uint8)
    bgr[:] = (40, 40, 40)
    # Red torso (B,G,R)
    cv2.rectangle(bgr, (24, 28), (56, 78), (40, 40, 200), -1)
    alpha = np.zeros((h, w), np.float32)
    cv2.rectangle(alpha, (24, 28), (56, 78), 1.0, -1)
    alpha = cv2.GaussianBlur(alpha, (0, 0), sigmaX=1.8)
    # Paint cyan onto the soft edge AFTER blur (matches real spill leftover)
    band = (alpha > 0.12) & (alpha < 0.82)
    bgr[band] = (220, 230, 50)  # bright cyan fringe on tank edge
    # Keep solid interior red
    solid = alpha > 0.92
    bgr[solid] = (40, 40, 200)
    return bgr, alpha


def test_suppress_residual_bg_kills_shoulder_island():
    bgr, alpha = _person_with_residual_bg()
    _ = bgr
    before_island = float(alpha[10:26, 6:20].mean())
    assert before_island > 0.15, "fixture must have residual island"
    # Soft bridge region near shoulder should exist before polish
    shoulder = float(alpha[60:80, 85:110].mean())
    assert shoulder > 0.12

    cleaned = suppress_residual_bg(alpha, hard_thresh=0.52, halo_px=7)
    # Far island gone
    assert float(cleaned[10:26, 6:20].mean()) < 0.05
    # Person core survives
    assert float(cleaned[90, 60]) > 0.7
    assert float(cleaned[40, 60]) > 0.5


def test_polish_videoeditor_removes_residual_bg_islands():
    bgr, alpha = _person_with_residual_bg()
    out = polish_videoeditor(alpha, bgr, spec=BEST_SPEC)
    # Far BG island
    assert float(out[8:24, 6:18].mean()) < 0.06
    # Soft shoulder residual crushed vs raw
    raw_shoulder = float(alpha[58:78, 88:112].mean())
    out_shoulder = float(out[58:78, 88:112].mean())
    assert out_shoulder < raw_shoulder * 0.55 + 0.02
    # Core person intact
    assert float(out[95, 60]) > 0.75
    assert float(out[38, 60]) > 0.55


def test_decontaminate_and_despill_reduce_cyan_fringe():
    bgr, alpha = _cyan_fringe_frame()
    # Measure cyan-ness on edge band: B and G vs R
    a = alpha
    band = (a > 0.15) & (a < 0.85)
    assert band.any()
    b0 = float(bgr[:, :, 0][band].mean())
    g0 = float(bgr[:, :, 1][band].mean())
    r0 = float(bgr[:, :, 2][band].mean())
    cyan0 = (b0 + g0) * 0.5 - r0
    assert cyan0 > 20, f"fixture cyan delta too weak: {cyan0}"

    cleaned = apply_color_polish(bgr, alpha, decontaminate=0.75, despill=0.70)
    b1 = float(cleaned[:, :, 0][band].mean())
    g1 = float(cleaned[:, :, 1][band].mean())
    r1 = float(cleaned[:, :, 2][band].mean())
    cyan1 = (b1 + g1) * 0.5 - r1
    assert cyan1 < cyan0 * 0.72, f"cyan fringe not reduced: {cyan0:.1f} → {cyan1:.1f}"

    # Direct helpers also move colors toward FG
    d = decontaminate_fringe(bgr, alpha, strength=0.8)
    s = suppress_color_spill(bgr, alpha, strength=0.8)
    assert float(np.mean(np.abs(d.astype(np.float32) - bgr.astype(np.float32)))) > 0.5
    assert float(np.mean(np.abs(s.astype(np.float32) - bgr.astype(np.float32)))) > 0.5


def test_max_engine_full_res_rvm_default():
    eng = MaxQualityEngine()
    assert eng._fast._prefer_quality is True
    assert eng._fast._full_res_matte is True
    fake = np.zeros((1080, 1920, 3), np.uint8)
    assert eng._fast._downsample_for(fake) == 1.0


def test_fast_quality_downsample_respects_env(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("HYBRID_MAX_RVM_LONG", "768")
    eng = FastEngine(prefer_quality=True)
    assert eng._full_res_matte is False
    assert eng._matte_target_long == 768
    fake = np.zeros((1080, 1920, 3), np.uint8)
    ds = eng._downsample_for(fake)
    assert 0.35 < ds < 0.75


def test_max_polish_path_kills_residual_on_engine():
    eng = MaxQualityEngine()
    bgr, soft = _person_with_residual_bg(128, 96)
    eng._base_alpha = lambda _b: soft.copy()  # type: ignore[method-assign]
    eng._seed = None
    out = eng._polish(bgr, warmup=False)
    assert float(out[6:18, 4:16].mean()) < 0.08
    assert float(out[70, 48]) > 0.65
