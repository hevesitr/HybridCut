"""Max multi-person cutout — keep secondary subjects (2026-10-10-continue)."""

from __future__ import annotations

import sys
from pathlib import Path

import cv2
import numpy as np

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

from hybrid_editor.engines.videoeditor_polish import (
    BEST_SPEC,
    keep_largest_person_soft,
    keep_person_instances_soft,
    polish_videoeditor,
    suppress_residual_bg,
)


def _two_people_plus_island(h: int = 160, w: int = 200) -> tuple[np.ndarray, np.ndarray]:
    """Two solid people + a small residual BG island (must not wipe person B)."""
    bgr = np.zeros((h, w, 3), np.uint8)
    bgr[:] = (35, 90, 40)
    alpha = np.zeros((h, w), np.float32)

    # Person A (left, larger)
    cv2.ellipse(bgr, (55, h // 2 + 8), (28, 46), 0, 0, 360, (80, 100, 190), -1)
    cv2.circle(bgr, (55, h // 2 - 40), 18, (95, 145, 185), -1)
    cv2.ellipse(alpha, (55, h // 2 + 8), (28, 46), 0, 0, 360, 1.0, -1)
    cv2.circle(alpha, (55, h // 2 - 40), 18, 1.0, -1)

    # Person B (right, ~70% of A — still a real subject)
    cv2.ellipse(bgr, (150, h // 2 + 12), (22, 40), 0, 0, 360, (70, 95, 180), -1)
    cv2.circle(bgr, (150, h // 2 - 34), 15, (90, 140, 180), -1)
    cv2.ellipse(alpha, (150, h // 2 + 12), (22, 40), 0, 0, 360, 1.0, -1)
    cv2.circle(alpha, (150, h // 2 - 34), 15, 1.0, -1)

    # Tiny far BG island
    cv2.rectangle(alpha, (4, 4), (18, 22), 0.5, -1)
    alpha = cv2.GaussianBlur(alpha, (0, 0), sigmaX=0.8)
    return bgr, alpha


def test_keep_person_instances_retains_second_subject():
    _bgr, alpha = _two_people_plus_island()
    out = keep_person_instances_soft(alpha, min_area_frac=0.008, relative_frac=0.20)
    # Both people survive
    assert float(out[90, 55]) > 0.7
    assert float(out[92, 150]) > 0.7
    # Island gone
    assert float(out[8:20, 6:16].mean()) < 0.08


def test_keep_largest_alias_is_multi_instance():
    _bgr, alpha = _two_people_plus_island()
    a = keep_largest_person_soft(alpha)
    b = keep_person_instances_soft(alpha)
    assert np.allclose(a, b)
    assert float(b[92, 150]) > 0.7


def test_suppress_residual_bg_keeps_both_people():
    _bgr, alpha = _two_people_plus_island()
    cleaned = suppress_residual_bg(alpha, hard_thresh=0.52, halo_px=7, relative_frac=0.20)
    assert float(cleaned[90, 55]) > 0.7
    assert float(cleaned[92, 150]) > 0.7
    assert float(cleaned[8:20, 6:16].mean()) < 0.06


def test_polish_videoeditor_multi_person_no_solid_bg_on_b():
    bgr, alpha = _two_people_plus_island()
    out = polish_videoeditor(alpha, bgr, spec=BEST_SPEC)
    # Person B core must remain cutout (not crushed to solid BG plate)
    assert float(out[92, 150]) > 0.65
    assert float(out[90, 55]) > 0.7
    assert float(out[8:20, 6:16].mean()) < 0.06
