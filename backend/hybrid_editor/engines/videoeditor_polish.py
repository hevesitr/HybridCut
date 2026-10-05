"""Videoeditor CapCut-parity alpha polish (ported ideas from docs/capcut-features/rvm_alpha).

Used by HybridCut Max / Éles szélek for Előnézet Cutout + bake.
Avoids MatAnyone2-style wide trimap fuse (that caused thick halo / hair holes).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import cv2
import numpy as np


@dataclass(frozen=True)
class VideoeditorPolishSpec:
    """Mirrors CapCut RECOMMENDED / BEST profile knobs (RTX 3060)."""

    edge_feather: float = 0.36
    fg_threshold: float = 0.97
    bg_threshold: float = 0.018
    morph_open: int = 0  # open eats hair — CapCut bake disables aggressive open
    morph_close: int = 2
    guided_radius: int = 7
    hair_boost: float = 0.58
    # RVM long-side target (CapCut BEST=768)
    target_long_side: float = 768.0


# CapCut BEST-like defaults for Max / export
BEST_SPEC = VideoeditorPolishSpec()
# Slightly lighter for Max preview if needed
RECOMMENDED_SPEC = VideoeditorPolishSpec(
    edge_feather=0.40,
    fg_threshold=0.972,
    bg_threshold=0.020,
    morph_open=0,
    morph_close=1,
    guided_radius=8,
    hair_boost=0.64,
    target_long_side=640.0,
)


def _as_hw_float(alpha: np.ndarray, shape: Optional[tuple[int, int]] = None) -> np.ndarray:
    a = np.asarray(alpha)
    if a.ndim == 3:
        a = a[..., 0]
    a = a.astype(np.float32)
    if a.size and float(a.max()) > 1.5:
        a = a / 255.0
    a = np.clip(a, 0.0, 1.0)
    if shape is not None and a.shape[:2] != shape:
        a = cv2.resize(a, (shape[1], shape[0]), interpolation=cv2.INTER_LINEAR)
    return a


def _guided_filter_alpha(gray_u8: np.ndarray, alpha_u8: np.ndarray, radius: int = 5) -> np.ndarray:
    r = max(1, int(radius))
    try:
        return cv2.ximgproc.guidedFilter(gray_u8, alpha_u8, radius=r, eps=1e-3)
    except Exception:
        pass
    try:
        return cv2.ximgproc.jointBilateralFilter(
            gray_u8, alpha_u8, d=max(5, r), sigma_color=12, sigma_space=max(3, r)
        )
    except Exception:
        return cv2.bilateralFilter(alpha_u8, d=max(5, r), sigmaColor=25, sigmaSpace=max(3, r))


def boost_hair_detail(
    alpha: np.ndarray,
    frame_bgr: np.ndarray,
    strength: float = 0.58,
) -> np.ndarray:
    """Restore mid-tone alpha (hair / wisps) via multi-scale luminance HF — fills holes."""
    strength = float(np.clip(strength, 0.0, 1.0))
    if strength < 0.01:
        return np.clip(alpha.astype(np.float32), 0.0, 1.0)

    a = np.clip(alpha.astype(np.float32), 0.0, 1.0)
    gray = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2GRAY).astype(np.float32) / 255.0
    hf_fine = gray - cv2.GaussianBlur(gray, (0, 0), sigmaX=1.0)
    hf_coarse = gray - cv2.GaussianBlur(gray, (0, 0), sigmaX=2.2)
    hf = hf_fine * 0.65 + hf_coarse * 0.35
    band = ((a > 0.06) & (a < 0.94)).astype(np.float32)
    band = cv2.GaussianBlur(band, (0, 0), sigmaX=1.1)
    # Positive HF lifts wisps; damp negative to avoid punching new holes
    lift = np.clip(hf * 2.05, -0.12, 0.40) * strength * band
    return np.clip(a + lift, 0.0, 1.0).astype(np.float32)


def keep_largest_person_soft(alpha: np.ndarray, min_area_frac: float = 0.008) -> np.ndarray:
    """Kill BG islands; keep largest FG + tight soft halo (hair fringe, not thick smudge)."""
    a = _as_hw_float(alpha)
    h, w = a.shape
    mask = (a > 0.28).astype(np.uint8) * 255
    if int(mask.max()) < 1:
        return a
    n, labels, stats, _ = cv2.connectedComponentsWithStats(mask, connectivity=8)
    if n <= 2:
        return a
    min_area = max(48, int(h * w * float(min_area_frac)))
    best_i, best_area = 0, 0
    for i in range(1, n):
        area = int(stats[i, cv2.CC_STAT_AREA])
        if area > best_area:
            best_area = area
            best_i = i
    if best_i <= 0 or best_area < min_area:
        return a
    keep = (labels == best_i).astype(np.uint8) * 255
    # Tighter halo than CapCut default (9×9×2 + σ2.2) — less shoulder fog
    k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
    halo = cv2.dilate(keep, k, iterations=1)
    halo_f = cv2.GaussianBlur(halo.astype(np.float32) / 255.0, (0, 0), sigmaX=1.1)
    return np.clip(a * np.clip(halo_f, 0.0, 1.0), 0.0, 1.0).astype(np.float32)


def fill_hair_holes(alpha: np.ndarray, *, close_iters: int = 2) -> np.ndarray:
    """Morph-close mid/high alpha to fill speck holes inside hair without expanding BG."""
    a = _as_hw_float(alpha)
    if close_iters <= 0:
        return a
    a8 = (np.clip(a, 0, 1) * 255.0).astype(np.uint8)
    k3 = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
    closed = cv2.morphologyEx(a8, cv2.MORPH_CLOSE, k3, iterations=int(close_iters))
    # Only fill where we already had some FG signal (avoid growing silhouette)
    support = cv2.dilate((a8 > 40).astype(np.uint8) * 255, k3, iterations=1)
    filled = np.where(support > 0, np.maximum(a8, closed), a8)
    return (filled.astype(np.float32) / 255.0).astype(np.float32)


def harden_foggy_halo(alpha: np.ndarray, *, lo: float = 0.32, hi: float = 0.68) -> np.ndarray:
    """Collapse thick Gaussian fog into a thinner edge band (CapCut sharp silhouette).

    Keeps restored hair/mid detail above ``lo`` while crushing shoulder smudge toward 0/1.
    """
    a = _as_hw_float(alpha)
    lo_f = float(np.clip(lo, 0.05, 0.49))
    hi_f = float(np.clip(hi, 0.51, 0.95))
    # Quadratic crush lows; complementary crush highs — shrinks (0.05, 0.95) mid-band.
    low = a < lo_f
    high = a > hi_f
    mid = (~low) & (~high)
    out = a.copy()
    out = np.where(low, np.clip((a / lo_f) ** 2.15 * lo_f * 0.55, 0.0, lo_f), out)
    out = np.where(high, 1.0 - np.clip(((1.0 - a) / (1.0 - hi_f)) ** 2.15 * (1.0 - hi_f) * 0.55, 0.0, 1.0 - hi_f), out)
    # Mild S-curve on remaining uncertain band (no re-blur)
    if mid.any():
        x = out[mid]
        centered = (x - 0.5) * 2.35
        out[mid] = np.clip(0.5 + 0.5 * np.tanh(centered), 0.0, 1.0)
    return out.astype(np.float32)


def refine_alpha_matte(
    alpha: np.ndarray,
    frame_bgr: np.ndarray,
    spec: Optional[VideoeditorPolishSpec] = None,
) -> np.ndarray:
    """CapCut-like refine: clamp → close holes → guided → hair lift → light band feather."""
    spec = spec or BEST_SPEC
    a = _as_hw_float(alpha, frame_bgr.shape[:2])
    fg_threshold = float(spec.fg_threshold)
    bg_threshold = float(spec.bg_threshold)
    edge_feather = float(spec.edge_feather)
    guided_radius = int(spec.guided_radius)
    hair_boost = float(spec.hair_boost)

    # Soft clamp — continuous 0–1
    a = np.where(a < bg_threshold, 0.0, a)
    a = np.where(a > fg_threshold, 1.0, a)

    # Protect thin hair/fingers before morph
    thin_protect = ((a > 0.18) & (a < 0.92)).astype(np.float32)
    thin_protect = cv2.GaussianBlur(thin_protect, (0, 0), sigmaX=0.9)
    raw = a.copy()

    a8 = np.clip(a * 255.0, 0, 255).astype(np.uint8)
    k3 = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
    # Prefer close (fill hair holes) — open eats wisps
    if spec.morph_open > 0:
        a8 = cv2.morphologyEx(a8, cv2.MORPH_OPEN, k3, iterations=int(spec.morph_open))
    if spec.morph_close > 0:
        a8 = cv2.morphologyEx(a8, cv2.MORPH_CLOSE, k3, iterations=int(spec.morph_close))

    gray = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2GRAY)
    a8 = _guided_filter_alpha(gray, a8, radius=guided_radius)
    a = a8.astype(np.float32) / 255.0

    # Restore protected mid-band after morph
    a = np.maximum(a, thin_protect * raw * 0.85)
    a = fill_hair_holes(a, close_iters=max(1, int(spec.morph_close)))

    # Kill distant BG islands (bleeding alpha)
    a = keep_largest_person_soft(a, min_area_frac=0.008)

    if hair_boost > 0.01:
        a = boost_hair_detail(a, frame_bgr, strength=hair_boost)

    # Feather ONLY uncertain band — tiny sigma (no thick smudge)
    if edge_feather > 0.01:
        soft = cv2.GaussianBlur(a, (0, 0), sigmaX=0.45)
        band = ((a > (bg_threshold + 0.035)) & (a < (fg_threshold - 0.035))).astype(np.float32)
        band = cv2.GaussianBlur(band, (0, 0), sigmaX=0.55)
        mix = float(np.clip(edge_feather, 0.0, 1.0)) * 0.40 * band  # less mix than CapCut soft preview
        a = a * (1.0 - mix) + soft * mix

    # Collapse foggy halo after hair lift (guided/HF can re-widen mid-band)
    a = harden_foggy_halo(a, lo=0.30, hi=0.70)

    # Final BG kill outside person — hardens silhouette vs foggy bleed
    a = keep_largest_person_soft(a, min_area_frac=0.008)
    a = np.where(a < bg_threshold, 0.0, a)
    a = np.where(a > fg_threshold, 1.0, a)
    return np.clip(a, 0.0, 1.0).astype(np.float32)


def polish_videoeditor(
    alpha: np.ndarray,
    frame_bgr: np.ndarray,
    *,
    spec: Optional[VideoeditorPolishSpec] = None,
    seed: Optional[np.ndarray] = None,
) -> np.ndarray:
    """Full Max polish: optional seed union + CapCut refine (no wide trimap).

    Never wipe a usable person matte: if refine empties a non-empty input, return
    the pre-refine alpha (seed-unioned). Empty-in → empty-out is fine (caller retries).
    """
    a = _as_hw_float(alpha, frame_bgr.shape[:2])
    if seed is not None:
        s = _as_hw_float(seed, frame_bgr.shape[:2])
        if float(s.max()) >= 0.05:
            a = np.maximum(a, s * 0.92)
    before = a.copy()
    out = refine_alpha_matte(a, frame_bgr, spec=spec or BEST_SPEC)
    # Guard: aggressive BG clamp / keep_largest must not erase auto RVM.
    before_cover = float((before > 0.15).mean())
    out_cover = float((out > 0.15).mean())
    if before_cover >= 0.04 and (out_cover < 0.02 or float(out.max()) < 0.05):
        return before
    return out
