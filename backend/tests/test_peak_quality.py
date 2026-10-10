"""Peak cutout quality — PEAK_SPEC, multi-person, edge metrics (2026-10-10-peak)."""

from __future__ import annotations

import sys
from pathlib import Path

import cv2
import numpy as np

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

from hybrid_editor.engines.max_quality import MaxQualityEngine
from hybrid_editor.engines.quality_pipeline import DEFAULT_WARMUP
from hybrid_editor.engines.videoeditor_polish import (
    BEST_SPEC,
    PEAK_SPEC,
    apply_color_polish,
    peak_edge_metrics,
    polish_cutout_pair,
    polish_videoeditor,
    suppress_bright_fringe,
)


def _hair_person_with_fringe(h: int = 180, w: int = 140) -> tuple[np.ndarray, np.ndarray]:
    """Person + soft hair wisps + cyan/white fringe + residual BG island."""
    bgr = np.zeros((h, w, 3), np.uint8)
    bgr[:] = (45, 100, 55)
    alpha = np.zeros((h, w), np.float32)
    # Torso + head
    cv2.ellipse(bgr, (w // 2, h // 2 + 12), (34, 50), 0, 0, 360, (70, 95, 195), -1)
    cv2.circle(bgr, (w // 2, h // 2 - 44), 24, (95, 145, 185), -1)
    cv2.ellipse(alpha, (w // 2, h // 2 + 12), (34, 50), 0, 0, 360, 1.0, -1)
    cv2.circle(alpha, (w // 2, h // 2 - 44), 24, 1.0, -1)
    # Soft hair wisps (mid-alpha)
    for dx, dy in ((-28, -50), (-22, -58), (26, -52), (32, -48)):
        cv2.ellipse(alpha, (w // 2 + dx, h // 2 + dy), (10, 16), 25, 0, 360, 0.45, -1)
    # Soft shoulder residual bridge + far island
    cv2.ellipse(alpha, (w // 2 + 40, h // 2 - 6), (16, 12), 0, 0, 360, 0.40, -1)
    cv2.rectangle(alpha, (4, 4), (20, 24), 0.50, -1)
    alpha = cv2.GaussianBlur(alpha, (0, 0), sigmaX=1.1)
    # Cyan + bright fringe on edge band
    band = (alpha > 0.12) & (alpha < 0.82)
    bgr[band] = (210, 225, 60)
    # Extra white bright halo on outer edge
    outer = (alpha > 0.08) & (alpha < 0.35)
    bgr[outer] = (235, 240, 245)
    solid = alpha > 0.92
    bgr[solid] = (70, 95, 195)
    return bgr, alpha


def _two_people(h: int = 160, w: int = 220) -> tuple[np.ndarray, np.ndarray]:
    bgr = np.zeros((h, w, 3), np.uint8)
    bgr[:] = (30, 80, 40)
    alpha = np.zeros((h, w), np.float32)
    cv2.ellipse(bgr, (60, h // 2 + 8), (28, 46), 0, 0, 360, (80, 100, 190), -1)
    cv2.circle(bgr, (60, h // 2 - 40), 18, (95, 145, 185), -1)
    cv2.ellipse(alpha, (60, h // 2 + 8), (28, 46), 0, 0, 360, 1.0, -1)
    cv2.circle(alpha, (60, h // 2 - 40), 18, 1.0, -1)
    cv2.ellipse(bgr, (165, h // 2 + 10), (24, 42), 0, 0, 360, (75, 100, 185), -1)
    cv2.circle(bgr, (165, h // 2 - 36), 16, (90, 140, 180), -1)
    cv2.ellipse(alpha, (165, h // 2 + 10), (24, 42), 0, 0, 360, 1.0, -1)
    cv2.circle(alpha, (165, h // 2 - 36), 16, 1.0, -1)
    cv2.rectangle(alpha, (4, 4), (16, 18), 0.48, -1)
    alpha = cv2.GaussianBlur(alpha, (0, 0), sigmaX=0.9)
    return bgr, alpha


def test_peak_spec_stronger_than_best():
    assert PEAK_SPEC.hair_boost > BEST_SPEC.hair_boost
    assert PEAK_SPEC.decontaminate > BEST_SPEC.decontaminate
    assert PEAK_SPEC.despill > BEST_SPEC.despill
    assert PEAK_SPEC.unknown_hair > 0.3
    assert PEAK_SPEC.bright_fringe > 0.3
    assert PEAK_SPEC.edge_sharpen > 0.2
    assert DEFAULT_WARMUP >= 10


def test_peak_polish_kills_residual_keeps_hair_core():
    bgr, alpha = _hair_person_with_fringe()
    out = polish_videoeditor(alpha, bgr, spec=PEAK_SPEC)
    m = peak_edge_metrics(bgr, out)
    # Far residual BG crushed
    assert float(out[8:20, 6:16].mean()) < 0.06
    assert m.residual_bg_frac < 0.04
    # Person core intact
    assert float(out[100, 70]) > 0.75
    assert m.person_cover > 0.12
    # Mid-band tighter than raw (peak sharp)
    raw_mid = float(((alpha > 0.12) & (alpha < 0.88)).mean())
    assert m.mid_band_frac < raw_mid * 0.92 + 0.02


def test_peak_color_polish_beats_cyan_and_bright():
    bgr, alpha = _hair_person_with_fringe()
    band = (alpha > 0.15) & (alpha < 0.80)
    cyan0 = float(
        (
            (bgr[:, :, 0].astype(np.float32)[band] + bgr[:, :, 1].astype(np.float32)[band]) * 0.5
            - bgr[:, :, 2].astype(np.float32)[band]
        ).mean()
    )
    bright0 = float(bgr.astype(np.float32).mean(axis=2)[band].mean())
    assert cyan0 > 15
    assert bright0 > 150

    cleaned = apply_color_polish(
        bgr,
        alpha,
        decontaminate=float(PEAK_SPEC.decontaminate),
        despill=float(PEAK_SPEC.despill),
        bright_fringe=float(PEAK_SPEC.bright_fringe),
    )
    cyan1 = float(
        (
            (cleaned[:, :, 0].astype(np.float32)[band] + cleaned[:, :, 1].astype(np.float32)[band])
            * 0.5
            - cleaned[:, :, 2].astype(np.float32)[band]
        ).mean()
    )
    bright1 = float(cleaned.astype(np.float32).mean(axis=2)[band].mean())
    assert cyan1 < cyan0 * 0.70
    assert bright1 < bright0 * 0.92

    bright_only = suppress_bright_fringe(bgr, alpha, strength=0.8)
    assert float(np.mean(np.abs(bright_only.astype(np.float32) - bgr.astype(np.float32)))) > 0.5


def test_peak_multi_person_both_survive():
    bgr, alpha = _two_people()
    out_bgr, out_a = polish_cutout_pair(bgr, alpha, spec=PEAK_SPEC)
    _ = out_bgr
    assert float(out_a[90, 60]) > 0.65
    assert float(out_a[92, 165]) > 0.65
    assert float(out_a[6:16, 4:14].mean()) < 0.08


def test_max_engine_uses_peak_meta():
    eng = MaxQualityEngine()
    assert eng.sharp_edges is True
    bgr, soft = _hair_person_with_fringe(128, 96)
    eng._base_alpha = lambda _b: soft.copy()  # type: ignore[method-assign]
    eng._seed = None
    out = eng._polish(bgr, warmup=False)
    assert float(out[6:16, 4:14].mean()) < 0.08
    assert float(out[70, 48]) > 0.60
