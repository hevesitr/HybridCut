"""Videoeditor CapCut-parity alpha polish (ported ideas from docs/capcut-features/rvm_alpha).

Used by HybridCut Max / Éles szélek for Előnézet Cutout + bake.
Avoids MatAnyone2-style wide trimap fuse (that caused thick halo / hair holes).

2026-10-05-max-accuracy: residual-BG island kill, full CapCut fringe decontam /
cyan spill suppress on cutout RGB (not alpha-only).

2026-10-10-continue: multi-person keep — keep all person-sized instances, not only
the single largest CC (secondary subjects were left as solid BG plate).

2026-10-10-peak: PEAK_SPEC, unknown-band hair refine (tight trimap ideas without
wide fuse), bright/white fringe kill, edge-gradient sharpen, edge metrics vs
CapCut left-side bar.

2026-10-10-apex: APEX_SPEC (Max default on top of peak) — stronger hair strand
recover, dual residual pass, micro-edge despill, multi-person keep retained.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Tuple

import cv2
import numpy as np


@dataclass(frozen=True)
class VideoeditorPolishSpec:
    """Mirrors CapCut RECOMMENDED / BEST / PEAK / APEX profile knobs (RTX 3060)."""

    edge_feather: float = 0.34
    fg_threshold: float = 0.975
    bg_threshold: float = 0.022
    morph_open: int = 0  # open eats hair — CapCut bake disables aggressive open
    morph_close: int = 2
    guided_radius: int = 7
    hair_boost: float = 0.55
    # CapCut BEST long-side hint (preview); Max bake overrides to full-res separately.
    target_long_side: float = 768.0
    # Color fringe polish (cyan / white edge on tank top + hair)
    decontaminate: float = 0.68
    despill: float = 0.62
    # Residual BG island kill (shoulder/neck chunks)
    residual_hard_thresh: float = 0.52
    residual_halo_px: int = 7
    # Peak/Apex: unknown-band hair lift + bright fringe + edge sharpen
    unknown_hair: float = 0.0
    bright_fringe: float = 0.0
    edge_sharpen: float = 0.0
    # Apex-only: recover thin hair strands after residual kill
    hair_strand: float = 0.0
    micro_despill: float = 0.0


# CapCut BEST-like defaults (compat / soft Max)
BEST_SPEC = VideoeditorPolishSpec()
# World-class Max + Éles szélek (2026-10-10-peak) — kept for regression tests
PEAK_SPEC = VideoeditorPolishSpec(
    edge_feather=0.26,
    fg_threshold=0.978,
    bg_threshold=0.016,
    morph_open=0,
    morph_close=2,
    guided_radius=7,
    hair_boost=0.64,
    target_long_side=0.0,  # full-res (Max bake / sharp preview)
    decontaminate=0.80,
    despill=0.74,
    residual_hard_thresh=0.50,
    residual_halo_px=8,
    unknown_hair=0.55,
    bright_fringe=0.70,
    edge_sharpen=0.42,
)
# Apex Max default (2026-10-10-apex) — on top of PEAK_SPEC
APEX_SPEC = VideoeditorPolishSpec(
    edge_feather=0.22,
    fg_threshold=0.980,
    bg_threshold=0.014,
    morph_open=0,
    morph_close=2,
    guided_radius=7,
    hair_boost=0.72,
    target_long_side=0.0,
    decontaminate=0.88,
    despill=0.82,
    residual_hard_thresh=0.48,
    residual_halo_px=9,
    unknown_hair=0.68,
    bright_fringe=0.82,
    edge_sharpen=0.52,
    hair_strand=0.62,
    micro_despill=0.45,
)
# Slightly lighter for Max preview if needed
RECOMMENDED_SPEC = VideoeditorPolishSpec(
    edge_feather=0.38,
    fg_threshold=0.972,
    bg_threshold=0.024,
    morph_open=0,
    morph_close=1,
    guided_radius=6,
    hair_boost=0.50,
    target_long_side=640.0,
    decontaminate=0.58,
    despill=0.52,
    residual_hard_thresh=0.50,
    residual_halo_px=6,
    unknown_hair=0.0,
    bright_fringe=0.0,
    edge_sharpen=0.0,
    hair_strand=0.0,
    micro_despill=0.0,
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


def _expand_mask_hwc(mask: np.ndarray) -> np.ndarray:
    """HxW or HxWx1 → HxWx1 float for broadcasting against BGR."""
    m = np.asarray(mask, dtype=np.float32)
    if m.ndim == 2:
        return m[..., None]
    if m.ndim == 3 and m.shape[2] == 1:
        return m
    return m[..., :1]


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
    strength: float = 0.55,
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


def _person_instance_ids(
    labels: np.ndarray,
    stats: np.ndarray,
    n: int,
    *,
    min_area: int,
    relative_frac: float = 0.20,
) -> list[int]:
    """Keep every person-sized CC: area >= min_area and >= relative_frac * largest.

    Tiny BG speckles / residual islands fall below the relative floor; a second
    (or third) subject near the primary size is retained.
    """
    if n <= 1:
        return []
    areas = [(i, int(stats[i, cv2.CC_STAT_AREA])) for i in range(1, n)]
    if not areas:
        return []
    best_area = max(a for _, a in areas)
    if best_area < min_area:
        return []
    floor = max(min_area, int(best_area * float(np.clip(relative_frac, 0.05, 0.9))))
    return [i for i, area in areas if area >= floor]


def keep_person_instances_soft(
    alpha: np.ndarray,
    min_area_frac: float = 0.008,
    *,
    relative_frac: float = 0.20,
) -> np.ndarray:
    """Kill BG islands; keep all person-sized FG instances + tight soft halo.

    Replaces single-CC keep-largest so 2+ people in frame do not leave secondary
    subjects as a solid background plate.
    """
    a = _as_hw_float(alpha)
    h, w = a.shape
    mask = (a > 0.28).astype(np.uint8) * 255
    if int(mask.max()) < 1:
        return a
    n, labels, stats, _ = cv2.connectedComponentsWithStats(mask, connectivity=8)
    if n <= 2:
        return a
    min_area = max(48, int(h * w * float(min_area_frac)))
    keep_ids = _person_instance_ids(
        labels, stats, n, min_area=min_area, relative_frac=relative_frac
    )
    if not keep_ids:
        return a
    keep = np.zeros((h, w), dtype=np.uint8)
    for i in keep_ids:
        keep = cv2.bitwise_or(keep, (labels == i).astype(np.uint8) * 255)
    # Tighter halo than CapCut default (9×9×2 + σ2.2) — less shoulder fog
    k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
    halo = cv2.dilate(keep, k, iterations=1)
    halo_f = cv2.GaussianBlur(halo.astype(np.float32) / 255.0, (0, 0), sigmaX=1.1)
    return np.clip(a * np.clip(halo_f, 0.0, 1.0), 0.0, 1.0).astype(np.float32)


def keep_largest_person_soft(alpha: np.ndarray, min_area_frac: float = 0.008) -> np.ndarray:
    """Compat alias → multi-instance person keep (secondary subjects retained)."""
    return keep_person_instances_soft(alpha, min_area_frac=min_area_frac)


def suppress_residual_bg(
    alpha: np.ndarray,
    *,
    hard_thresh: float = 0.52,
    halo_px: int = 7,
    min_area_frac: float = 0.006,
    relative_frac: float = 0.20,
) -> np.ndarray:
    """Kill large soft BG leftovers near neck/shoulders without CapCut-style thick morph.

    Soft residual islands often stay *connected* to the person via mid-alpha bridges, so a
    single low-threshold CC keep-largest misses them. Build support from a **hard** FG core
    (severs soft bridges), keep all person-sized cores (multi-person), dilate a modest hair
    halo, then crush alpha outside that support.
    """
    a = _as_hw_float(alpha)
    h, w = a.shape
    hard_t = float(np.clip(hard_thresh, 0.35, 0.85))
    hard = (a >= hard_t).astype(np.uint8) * 255
    if int(hard.max()) < 1:
        # Fallback: slightly softer core
        hard = (a >= max(0.35, hard_t - 0.12)).astype(np.uint8) * 255
    if int(hard.max()) < 1:
        return a

    n, labels, stats, _ = cv2.connectedComponentsWithStats(hard, connectivity=8)
    min_area = max(32, int(h * w * float(min_area_frac)))
    keep_ids = _person_instance_ids(
        labels, stats, n, min_area=min_area, relative_frac=relative_frac
    )
    if not keep_ids:
        return keep_person_instances_soft(
            a, min_area_frac=min_area_frac, relative_frac=relative_frac
        )

    core = np.zeros((h, w), dtype=np.uint8)
    for i in keep_ids:
        core = cv2.bitwise_or(core, (labels == i).astype(np.uint8) * 255)
    # Hair / finger halo — modest, not MatAnyone2-wide
    px = max(3, int(halo_px))
    if px % 2 == 0:
        px += 1
    k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (px, px))
    support = cv2.dilate(core, k, iterations=1)
    # Also keep thin mid-alpha wisps already attached to core (hair), but not far islands.
    soft_near = ((a > 0.12) & (a < hard_t)).astype(np.uint8) * 255
    soft_near = cv2.bitwise_and(soft_near, cv2.dilate(core, k, iterations=2))
    support = cv2.bitwise_or(support, soft_near)
    support_f = cv2.GaussianBlur(support.astype(np.float32) / 255.0, (0, 0), sigmaX=0.9)
    out = a * np.clip(support_f, 0.0, 1.0)
    # Hard-zero far residual (checker islands)
    out = np.where(support_f < 0.08, 0.0, out)
    return np.clip(out, 0.0, 1.0).astype(np.float32)


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
    out = np.where(
        high,
        1.0
        - np.clip(((1.0 - a) / (1.0 - hi_f)) ** 2.15 * (1.0 - hi_f) * 0.55, 0.0, 1.0 - hi_f),
        out,
    )
    # Mild S-curve on remaining uncertain band (no re-blur)
    if mid.any():
        x = out[mid]
        centered = (x - 0.5) * 2.35
        out[mid] = np.clip(0.5 + 0.5 * np.tanh(centered), 0.0, 1.0)
    return out.astype(np.float32)


def decontaminate_fringe(
    frame_bgr: np.ndarray,
    alpha: np.ndarray,
    strength: float = 0.68,
) -> np.ndarray:
    """Pull semi-transparent edge colors toward local eroded FG (halo / fringe kill).

    CapCut-like fringe clean — local interior color beats global mean (avoids skin→hair wash).
    """
    strength = float(np.clip(strength, 0.0, 1.0))
    if strength < 0.01:
        return frame_bgr

    h, w = frame_bgr.shape[:2]
    a = _as_hw_float(alpha, (h, w))
    band = (a > 0.04) & (a < 0.90)
    if not np.any(band):
        return frame_bgr

    a8 = (a * 255.0).astype(np.uint8)
    k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
    core = cv2.erode(a8, k, iterations=2)
    solid = core > 200
    if not np.any(solid):
        solid = a8 > 220
    if not np.any(solid):
        return frame_bgr

    src = frame_bgr.astype(np.float32)
    solid_f = _expand_mask_hwc(solid.astype(np.float32))
    blurred = cv2.GaussianBlur(src * solid_f, (0, 0), sigmaX=4.0)
    weight = _expand_mask_hwc(cv2.GaussianBlur(solid_f, (0, 0), sigmaX=4.0))
    denom = np.maximum(weight, 1e-3)
    local_fg = np.where(weight > 1e-3, blurred / denom, src)
    fg_mean = src[solid].mean(axis=0).reshape(1, 1, 3)
    local_ok = _expand_mask_hwc((weight[..., 0] > 0.05).astype(np.float32))
    fg_ref = np.where(local_ok > 0.5, local_fg, fg_mean)

    wgt = (1.0 - np.abs(a - 0.45) * 1.55).clip(0.0, 1.0) * strength
    wgt = _expand_mask_hwc(np.where(band, wgt, 0.0).astype(np.float32))
    out = src * (1.0 - wgt) + fg_ref * wgt
    return np.clip(out, 0, 255).astype(np.uint8)


def suppress_color_spill(
    frame_bgr: np.ndarray,
    alpha: np.ndarray,
    strength: float = 0.62,
) -> np.ndarray:
    """Reduce green/blue (cyan) spill on semi-transparent edges — tank-top fringe."""
    strength = float(np.clip(strength, 0.0, 1.0))
    if strength < 0.01:
        return frame_bgr

    out = frame_bgr.astype(np.float32)
    a = _as_hw_float(alpha, frame_bgr.shape[:2])
    band = (a > 0.05) & (a < 0.92)
    if not np.any(band):
        return frame_bgr

    b, g, r = out[:, :, 0], out[:, :, 1], out[:, :, 2]
    avg_rb = (r + b) * 0.5
    green_spill = (g > avg_rb + 8) & band
    if np.any(green_spill):
        g2 = np.minimum(g, avg_rb + (g - avg_rb) * (1.0 - 0.70 * strength))
        g_hard = np.minimum(g, avg_rb + 6.0 * (1.0 - 0.5 * strength))
        g = np.where(green_spill, np.minimum(g2, g_hard), g)

    avg_rg = (r + g) * 0.5
    blue_spill = (b > avg_rg + 10) & band
    if np.any(blue_spill):
        b2 = np.minimum(b, avg_rg + (b - avg_rg) * (1.0 - 0.60 * strength))
        b_hard = np.minimum(b, avg_rg + 8.0 * (1.0 - 0.5 * strength))
        b = np.where(blue_spill, np.minimum(b2, b_hard), b)

    # Cyan = both G and B high vs R — extra clamp on the uncertain band
    cyan = (b > r + 12) & (g > r + 8) & band
    if np.any(cyan):
        tgt = (r + np.minimum(g, b)) * 0.5
        b = np.where(cyan, np.minimum(b, tgt + (b - tgt) * (1.0 - 0.75 * strength)), b)
        g = np.where(cyan, np.minimum(g, tgt + (g - tgt) * (1.0 - 0.75 * strength)), g)

    out[:, :, 0] = b
    out[:, :, 1] = g
    out[:, :, 2] = r
    return np.clip(out, 0, 255).astype(np.uint8)


def suppress_bright_fringe(
    frame_bgr: np.ndarray,
    alpha: np.ndarray,
    strength: float = 0.70,
) -> np.ndarray:
    """Kill white / over-bright halo on hair & shoulders (CapCut left-bar look).

    Bright fringe often survives cyan despill — pull luminous edge pixels toward
    local eroded FG luminance while preserving chroma of the subject.
    """
    strength = float(np.clip(strength, 0.0, 1.0))
    if strength < 0.01:
        return frame_bgr

    h, w = frame_bgr.shape[:2]
    a = _as_hw_float(alpha, (h, w))
    band = (a > 0.06) & (a < 0.88)
    if not np.any(band):
        return frame_bgr

    src = frame_bgr.astype(np.float32)
    a8 = (a * 255.0).astype(np.uint8)
    k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
    core = cv2.erode(a8, k, iterations=2)
    solid = core > 200
    if not np.any(solid):
        solid = a8 > 220
    if not np.any(solid):
        return frame_bgr

    solid_f = _expand_mask_hwc(solid.astype(np.float32))
    blurred = cv2.GaussianBlur(src * solid_f, (0, 0), sigmaX=3.5)
    weight = _expand_mask_hwc(cv2.GaussianBlur(solid_f, (0, 0), sigmaX=3.5))
    local_fg = np.where(weight > 1e-3, blurred / np.maximum(weight, 1e-3), src)

    lum = src.mean(axis=2)
    fg_lum = local_fg.mean(axis=2)
    bright = band & (lum > fg_lum + 18.0) & (lum > 140.0)
    if not np.any(bright):
        return frame_bgr

    # Stronger pull near mid-alpha (classic fringe zone)
    wgt = (1.0 - np.abs(a - 0.42) * 1.7).clip(0.0, 1.0) * strength
    wgt = _expand_mask_hwc(np.where(bright, wgt, 0.0).astype(np.float32))
    out = src * (1.0 - wgt) + local_fg * wgt
    return np.clip(out, 0, 255).astype(np.uint8)


def build_tight_unknown_band(alpha: np.ndarray, *, erode_px: int = 3, dilate_px: int = 4) -> np.ndarray:
    """MatAnyone2-inspired unknown ring — tight, no wide fuse (hair-safe)."""
    a = _as_hw_float(alpha)
    a8 = (a * 255.0).astype(np.uint8)
    ek = max(1, int(erode_px))
    dk = max(1, int(dilate_px))
    if ek % 2 == 0:
        ek += 1
    if dk % 2 == 0:
        dk += 1
    ke = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (ek, ek))
    kd = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (dk, dk))
    fg = cv2.erode((a8 > 200).astype(np.uint8) * 255, ke, iterations=1)
    support = cv2.dilate((a8 > 12).astype(np.uint8) * 255, kd, iterations=1)
    unknown = cv2.bitwise_and(support, cv2.bitwise_not(fg)).astype(np.float32) / 255.0
    # Also keep soft mid-alpha as unknown (hair wisps inside silhouette)
    mid = ((a > 0.10) & (a < 0.90)).astype(np.float32)
    unknown = np.clip(np.maximum(unknown, mid * 0.85), 0.0, 1.0)
    return cv2.GaussianBlur(unknown, (0, 0), sigmaX=0.45)


def refine_unknown_hair(
    alpha: np.ndarray,
    frame_bgr: np.ndarray,
    strength: float = 0.55,
) -> np.ndarray:
    """Hair/fringe lift only in a tight unknown band — no BG clamp fuse.

    MatAnyone2 idea: trust model in unknown, lock FG/BG elsewhere *softly*
    without the wide erode/dilate that punched hair holes.
    """
    strength = float(np.clip(strength, 0.0, 1.0))
    if strength < 0.01:
        return _as_hw_float(alpha, frame_bgr.shape[:2])

    a = _as_hw_float(alpha, frame_bgr.shape[:2])
    unknown = build_tight_unknown_band(a)
    if float(unknown.max()) < 0.05:
        return a

    # Guided refine only where unknown — preserves solid FG/BG
    a8 = (np.clip(a, 0, 1) * 255.0).astype(np.uint8)
    gray = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2GRAY)
    guided = _guided_filter_alpha(gray, a8, radius=4).astype(np.float32) / 255.0
    amt = strength * 0.55
    out = a * (1.0 - unknown * amt) + guided * (unknown * amt)
    # Extra HF hair lift masked by unknown
    out = boost_hair_detail(out, frame_bgr, strength=0.35 * strength)
    # Soft FG floor / BG ceil *only* outside unknown (no hard wipe of wisps)
    solid_fg = (unknown < 0.15) & (a > 0.88)
    solid_bg = (unknown < 0.12) & (a < 0.08)
    out = np.where(solid_fg, np.maximum(out, 0.96), out)
    out = np.where(solid_bg, np.minimum(out, 0.02), out)
    return np.clip(out, 0.0, 1.0).astype(np.float32)


def sharpen_edge_gradient(alpha: np.ndarray, strength: float = 0.42) -> np.ndarray:
    """Needle-sharp silhouette: S-curve on the edge band (CapCut left-bar)."""
    strength = float(np.clip(strength, 0.0, 1.0))
    if strength < 0.01:
        return _as_hw_float(alpha)
    a = _as_hw_float(alpha)
    # Edge band via morphological gradient
    a8 = (a * 255.0).astype(np.uint8)
    k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
    grad = cv2.morphologyEx(a8, cv2.MORPH_GRADIENT, k).astype(np.float32) / 255.0
    edge = cv2.GaussianBlur(grad, (0, 0), sigmaX=0.6)
    edge = np.clip(edge * 3.2, 0.0, 1.0)
    mid = ((a > 0.12) & (a < 0.88)).astype(np.float32)
    w = edge * mid * strength
    # S-curve toward 0/1 on edge pixels only
    centered = (a - 0.5) * (1.0 + 1.85 * w)
    sharp = np.clip(0.5 + 0.5 * np.tanh(centered * 1.15), 0.0, 1.0)
    out = a * (1.0 - w) + sharp * w
    return np.clip(out, 0.0, 1.0).astype(np.float32)


def recover_hair_strands(
    alpha: np.ndarray,
    frame_bgr: np.ndarray,
    prior: np.ndarray,
    strength: float = 0.62,
) -> np.ndarray:
    """Apex: restore thin hair wisps killed by residual BG pass.

    Uses a high-frequency prior (pre-residual alpha) masked by local luminance
    detail near the silhouette — CapCut left-bar hair recovery idea.
    """
    strength = float(np.clip(strength, 0.0, 1.0))
    if strength < 0.01:
        return _as_hw_float(alpha, frame_bgr.shape[:2])
    a = _as_hw_float(alpha, frame_bgr.shape[:2])
    p = _as_hw_float(prior, frame_bgr.shape[:2])
    # Candidate strands: prior mid-alpha that current pass crushed
    lost = np.clip(p - a, 0.0, 1.0)
    strand = (lost > 0.08) & (p > 0.12) & (p < 0.85) & (a < 0.55)
    if not np.any(strand):
        return a
    gray = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2GRAY).astype(np.float32)
    blur = cv2.GaussianBlur(gray, (0, 0), sigmaX=1.2)
    detail = np.abs(gray - blur)
    detail = detail / max(float(detail.max()), 1e-3)
    # Prefer textured (hair) over flat BG plate
    w = (detail * 0.75 + 0.25) * strength
    w = np.where(strand, w, 0.0).astype(np.float32)
    # Soft dilation so wisps reconnect to silhouette
    a8 = (a * 255.0).astype(np.uint8)
    k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
    near = cv2.dilate((a8 > 40).astype(np.uint8), k, iterations=2) > 0
    w = np.where(near, w, w * 0.15)
    out = a * (1.0 - w) + np.maximum(a, p * 0.92) * w
    return np.clip(out, 0.0, 1.0).astype(np.float32)


def micro_edge_despill(
    frame_bgr: np.ndarray,
    alpha: np.ndarray,
    strength: float = 0.45,
) -> np.ndarray:
    """Apex: second-pass micro despill on 1–2px hair edge (after bright fringe)."""
    strength = float(np.clip(strength, 0.0, 1.0))
    if strength < 0.01:
        return frame_bgr
    h, w = frame_bgr.shape[:2]
    a = _as_hw_float(alpha, (h, w))
    a8 = (a * 255.0).astype(np.uint8)
    k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
    grad = cv2.morphologyEx(a8, cv2.MORPH_GRADIENT, k)
    rim = (grad > 8) & (a > 0.08) & (a < 0.92)
    if not np.any(rim):
        return frame_bgr
    src = frame_bgr.astype(np.float32)
    b, g, r = src[:, :, 0], src[:, :, 1], src[:, :, 2]
    # Pull cyan/green rim toward local FG mean
    solid = a8 > 210
    if not np.any(solid):
        return frame_bgr
    solid_f = _expand_mask_hwc(solid.astype(np.float32))
    blurred = cv2.GaussianBlur(src * solid_f, (0, 0), sigmaX=2.2)
    weight = _expand_mask_hwc(cv2.GaussianBlur(solid.astype(np.float32), (0, 0), sigmaX=2.2))
    local = np.where(weight > 1e-3, blurred / np.maximum(weight, 1e-3), src)
    cyanish = ((b + g) * 0.5 - r) > 8.0
    mask = rim & cyanish
    if not np.any(mask):
        return frame_bgr
    wgt = strength * (1.0 - np.abs(a - 0.45) * 1.4).clip(0.0, 1.0)
    wgt = _expand_mask_hwc(np.where(mask, wgt, 0.0).astype(np.float32))
    out = src * (1.0 - wgt) + local * wgt
    return np.clip(out, 0, 255).astype(np.uint8)


@dataclass(frozen=True)
class PeakEdgeMetrics:
    """Self-test metrics vs CapCut left-side quality bar."""

    mid_band_frac: float
    residual_bg_frac: float
    person_cover: float
    cyan_edge_delta: float
    bright_edge_delta: float


def peak_edge_metrics(
    frame_bgr: np.ndarray,
    alpha: np.ndarray,
) -> PeakEdgeMetrics:
    """Quantify soft-halo / residual BG / color fringe for regression tests."""
    a = _as_hw_float(alpha, frame_bgr.shape[:2])
    mid = float(((a > 0.12) & (a < 0.88)).mean())
    # Residual: soft alpha far from hard cores
    hard = (a >= 0.55).astype(np.uint8) * 255
    if int(hard.max()) > 0:
        k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (11, 11))
        near = cv2.dilate(hard, k, iterations=1)
        residual = ((a > 0.08) & (near == 0)).mean()
    else:
        residual = float((a > 0.08).mean())
    person = float((a > 0.35).mean())
    band = (a > 0.12) & (a < 0.85)
    if np.any(band):
        b = frame_bgr[:, :, 0].astype(np.float32)
        g = frame_bgr[:, :, 1].astype(np.float32)
        r = frame_bgr[:, :, 2].astype(np.float32)
        cyan = float(((b[band] + g[band]) * 0.5 - r[band]).mean())
        bright = float(frame_bgr.astype(np.float32).mean(axis=2)[band].mean())
    else:
        cyan = 0.0
        bright = 0.0
    return PeakEdgeMetrics(
        mid_band_frac=mid,
        residual_bg_frac=float(residual),
        person_cover=person,
        cyan_edge_delta=cyan,
        bright_edge_delta=bright,
    )


def apply_color_polish(
    frame_bgr: np.ndarray,
    alpha: np.ndarray,
    *,
    decontaminate: float = 0.68,
    despill: float = 0.62,
    bright_fringe: float = 0.0,
    micro_despill: float = 0.0,
) -> np.ndarray:
    """CapCut fringe + spill (+ peak bright halo + apex micro rim) on cutout RGB."""
    out = frame_bgr
    if float(decontaminate) > 0.01:
        out = decontaminate_fringe(out, alpha, strength=float(decontaminate))
    if float(despill) > 0.01:
        out = suppress_color_spill(out, alpha, strength=float(despill))
    if float(bright_fringe) > 0.01:
        out = suppress_bright_fringe(out, alpha, strength=float(bright_fringe))
    if float(micro_despill) > 0.01:
        out = micro_edge_despill(out, alpha, strength=float(micro_despill))
    return out


def refine_alpha_matte(
    alpha: np.ndarray,
    frame_bgr: np.ndarray,
    spec: Optional[VideoeditorPolishSpec] = None,
) -> np.ndarray:
    """CapCut-like refine: clamp → close holes → guided → hair lift → residual BG kill."""
    spec = spec or APEX_SPEC
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
    # Prefer close (fill hair holes) — open eats wisps / can create BG islands
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

    # Classic soft island kill, then hard-core residual BG suppress (neck/shoulder chunks)
    a = keep_largest_person_soft(a, min_area_frac=0.008)
    a = suppress_residual_bg(
        a,
        hard_thresh=float(spec.residual_hard_thresh),
        halo_px=int(spec.residual_halo_px),
        min_area_frac=0.006,
    )
    hair_prior = a.copy()

    if hair_boost > 0.01:
        a = boost_hair_detail(a, frame_bgr, strength=hair_boost)

    # Peak/Apex: MatAnyone2-inspired unknown-band hair refine (no wide trimap fuse)
    if float(spec.unknown_hair) > 0.01:
        a = refine_unknown_hair(a, frame_bgr, strength=float(spec.unknown_hair))
        hair_prior = np.maximum(hair_prior, a)

    # Feather ONLY uncertain band — tiny sigma (no thick smudge)
    if edge_feather > 0.01:
        soft = cv2.GaussianBlur(a, (0, 0), sigmaX=0.40)
        band = ((a > (bg_threshold + 0.035)) & (a < (fg_threshold - 0.035))).astype(np.float32)
        band = cv2.GaussianBlur(band, (0, 0), sigmaX=0.50)
        mix = float(np.clip(edge_feather, 0.0, 1.0)) * 0.34 * band
        a = a * (1.0 - mix) + soft * mix

    # Collapse foggy halo after hair lift (guided/HF can re-widen mid-band)
    a = harden_foggy_halo(a, lo=0.24, hi=0.76)

    # Peak/Apex: needle-sharp edge gradient (CapCut left-bar silhouette)
    if float(spec.edge_sharpen) > 0.01:
        a = sharpen_edge_gradient(a, strength=float(spec.edge_sharpen))

    # Final BG kill outside person — hardens silhouette vs foggy bleed
    a = suppress_residual_bg(
        a,
        hard_thresh=float(spec.residual_hard_thresh),
        halo_px=max(5, int(spec.residual_halo_px) - 1),
        min_area_frac=0.006,
    )
    # Apex: recover thin strands lost to residual kill
    if float(spec.hair_strand) > 0.01:
        a = recover_hair_strands(a, frame_bgr, hair_prior, strength=float(spec.hair_strand))
        # Light second residual so recovered strands don't reintroduce islands
        a = suppress_residual_bg(
            a,
            hard_thresh=min(0.55, float(spec.residual_hard_thresh) + 0.04),
            halo_px=max(4, int(spec.residual_halo_px) - 2),
            min_area_frac=0.007,
        )
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

    Default spec is APEX_SPEC (2026-10-10-apex). Never wipe a usable person matte:
    if refine empties a non-empty input, return the pre-refine alpha (seed-unioned).
    Empty-in → empty-out is fine (caller retries).
    """
    a = _as_hw_float(alpha, frame_bgr.shape[:2])
    if seed is not None:
        s = _as_hw_float(seed, frame_bgr.shape[:2])
        if float(s.max()) >= 0.05:
            a = np.maximum(a, s * 0.92)
    before = a.copy()
    out = refine_alpha_matte(a, frame_bgr, spec=spec or APEX_SPEC)
    # Guard: aggressive BG clamp / keep_largest must not erase auto RVM.
    before_cover = float((before > 0.15).mean())
    out_cover = float((out > 0.15).mean())
    if before_cover >= 0.04 and (out_cover < 0.02 or float(out.max()) < 0.05):
        return before
    return out


def polish_cutout_pair(
    frame_bgr: np.ndarray,
    alpha: np.ndarray,
    *,
    spec: Optional[VideoeditorPolishSpec] = None,
    seed: Optional[np.ndarray] = None,
) -> Tuple[np.ndarray, np.ndarray]:
    """Alpha refine + RGB fringe/spill polish for checker cutout / bake BGRA."""
    spec = spec or APEX_SPEC
    a = polish_videoeditor(alpha, frame_bgr, spec=spec, seed=seed)
    bgr = apply_color_polish(
        frame_bgr,
        a,
        decontaminate=float(spec.decontaminate),
        despill=float(spec.despill),
        bright_fringe=float(spec.bright_fringe),
        micro_despill=float(spec.micro_despill),
    )
    return bgr, a
