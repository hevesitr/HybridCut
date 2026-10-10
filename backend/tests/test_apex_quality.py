"""Apex cutout quality — APEX_SPEC on top of peak (2026-10-10-apex)."""

from __future__ import annotations

import sys
from pathlib import Path

import cv2
import numpy as np

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

from hybrid_editor.engines.max_quality import MaxQualityEngine
from hybrid_editor.engines.videoeditor_polish import (
    APEX_SPEC,
    PEAK_SPEC,
    apply_color_polish,
    peak_edge_metrics,
    polish_cutout_pair,
    polish_videoeditor,
    recover_hair_strands,
)


def _hair_person_with_fringe(h: int = 180, w: int = 140) -> tuple[np.ndarray, np.ndarray]:
    bgr = np.zeros((h, w, 3), np.uint8)
    bgr[:] = (45, 100, 55)
    alpha = np.zeros((h, w), np.float32)
    cv2.ellipse(bgr, (w // 2, h // 2 + 12), (34, 50), 0, 0, 360, (70, 95, 195), -1)
    cv2.circle(bgr, (w // 2, h // 2 - 44), 24, (95, 145, 185), -1)
    cv2.ellipse(alpha, (w // 2, h // 2 + 12), (34, 50), 0, 0, 360, 1.0, -1)
    cv2.circle(alpha, (w // 2, h // 2 - 44), 24, 1.0, -1)
    for dx, dy in ((-28, -50), (-22, -58), (26, -52), (32, -48), (-18, -62)):
        cv2.ellipse(alpha, (w // 2 + dx, h // 2 + dy), (10, 16), 25, 0, 360, 0.42, -1)
    cv2.ellipse(alpha, (w // 2 + 40, h // 2 - 6), (16, 12), 0, 0, 360, 0.40, -1)
    cv2.rectangle(alpha, (4, 4), (20, 24), 0.50, -1)
    alpha = cv2.GaussianBlur(alpha, (0, 0), sigmaX=1.1)
    band = (alpha > 0.12) & (alpha < 0.82)
    bgr[band] = (210, 225, 60)
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


def test_apex_spec_stronger_than_peak():
    assert APEX_SPEC.hair_boost > PEAK_SPEC.hair_boost
    assert APEX_SPEC.decontaminate > PEAK_SPEC.decontaminate
    assert APEX_SPEC.despill > PEAK_SPEC.despill
    assert APEX_SPEC.unknown_hair > PEAK_SPEC.unknown_hair
    assert APEX_SPEC.bright_fringe > PEAK_SPEC.bright_fringe
    assert APEX_SPEC.edge_sharpen > PEAK_SPEC.edge_sharpen
    assert APEX_SPEC.hair_strand > 0.3
    assert APEX_SPEC.micro_despill > 0.2


def test_apex_polish_beats_peak_on_residual_and_mid():
    bgr, alpha = _hair_person_with_fringe()
    peak = polish_videoeditor(alpha, bgr, spec=PEAK_SPEC)
    apex = polish_videoeditor(alpha, bgr, spec=APEX_SPEC)
    mp = peak_edge_metrics(bgr, peak)
    ma = peak_edge_metrics(bgr, apex)
    assert ma.residual_bg_frac <= mp.residual_bg_frac + 0.01
    assert ma.mid_band_frac <= mp.mid_band_frac + 0.02
    assert float(apex[100, 70]) > 0.75
    assert float(apex[8:20, 6:16].mean()) < 0.06


def test_apex_color_polish_kills_cyan_bright():
    bgr, alpha = _hair_person_with_fringe()
    band = (alpha > 0.15) & (alpha < 0.80)
    cyan0 = float(
        (
            (bgr[:, :, 0].astype(np.float32)[band] + bgr[:, :, 1].astype(np.float32)[band]) * 0.5
            - bgr[:, :, 2].astype(np.float32)[band]
        ).mean()
    )
    cleaned = apply_color_polish(
        bgr,
        alpha,
        decontaminate=float(APEX_SPEC.decontaminate),
        despill=float(APEX_SPEC.despill),
        bright_fringe=float(APEX_SPEC.bright_fringe),
        micro_despill=float(APEX_SPEC.micro_despill),
    )
    cyan1 = float(
        (
            (cleaned[:, :, 0].astype(np.float32)[band] + cleaned[:, :, 1].astype(np.float32)[band])
            * 0.5
            - cleaned[:, :, 2].astype(np.float32)[band]
        ).mean()
    )
    assert cyan0 > 15
    assert cyan1 < cyan0 * 0.65


def test_apex_multi_person_both_survive():
    bgr, alpha = _two_people()
    _b, out_a = polish_cutout_pair(bgr, alpha, spec=APEX_SPEC)
    assert float(out_a[90, 60]) > 0.65
    assert float(out_a[92, 165]) > 0.65
    assert float(out_a[6:16, 4:14].mean()) < 0.08


def test_recover_hair_strands_restores_wisps():
    bgr, prior = _hair_person_with_fringe()
    crushed = prior.copy()
    crushed[prior < 0.55] *= 0.15
    out = recover_hair_strands(crushed, bgr, prior, strength=0.7)
    # Global lift vs crushed mid-band (wisps near silhouette)
    mid_prior = (prior > 0.15) & (prior < 0.70)
    assert float(out[mid_prior].mean()) > float(crushed[mid_prior].mean()) + 0.01
    assert float(out.max()) >= float(crushed.max()) - 1e-6


def test_max_engine_uses_apex_meta():
    eng = MaxQualityEngine()
    assert eng.sharp_edges is True
    bgr, soft = _hair_person_with_fringe(128, 96)
    eng._base_alpha = lambda _b: soft.copy()  # type: ignore[method-assign]
    eng._seed = None
    out = eng._polish(bgr, warmup=False)
    assert float(out[6:16, 4:14].mean()) < 0.08
    assert float(out[70, 48]) > 0.60
