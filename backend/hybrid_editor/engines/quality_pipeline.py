"""MatAnyone2-inspired quality helpers (ideas only — no MatAnyone2 source).

Techniques: first-frame warmup, erode/dilate guidance trimap, anchor memory blend,
unknown-band fringe refine, optional mid-clip re-warmup on large drift.
Clean reimplementation for the hybrid tree. S-Lab weights are NOT used here.

Sharp-edges mode (default for Max/export): tighter trimap, less Gaussian feather,
guided/bilateral fringe cleanup that preserves hair without a thick halo.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import cv2
import numpy as np

# Soft/legacy defaults (Gyors-ish polish when sharp_edges=False)
DEFAULT_ERODE_K = 10
DEFAULT_DILATE_K = 10
# Max / export: CapCut-like tighter guidance (less foggy halo)
SHARP_ERODE_K = 4
SHARP_DILATE_K = 5
DEFAULT_WARMUP = 8
DEFAULT_MEM_EVERY = 5


@dataclass(frozen=True)
class GuidanceTrimap:
    fg: np.ndarray
    unknown: np.ndarray
    bg: np.ndarray

    @property
    def shape(self) -> tuple[int, int]:
        return (int(self.fg.shape[0]), int(self.fg.shape[1]))


def _as_hw_float(mask: np.ndarray, shape: Optional[tuple[int, int]] = None) -> np.ndarray:
    a = np.asarray(mask)
    if a.ndim == 3:
        a = a[..., 0]
    a = a.astype(np.float32)
    if a.max() > 1.5:
        a = a / 255.0
    a = np.clip(a, 0.0, 1.0)
    if shape is not None and a.shape[:2] != shape:
        a = cv2.resize(a, (shape[1], shape[0]), interpolation=cv2.INTER_LINEAR)
    return a


def _ellipse_kernel(size: int) -> np.ndarray:
    k = max(1, int(size))
    if k % 2 == 0:
        k += 1
    return cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (k, k))


def build_guidance_trimap(
    seed: np.ndarray,
    *,
    erode_k: int = DEFAULT_ERODE_K,
    dilate_k: int = DEFAULT_DILATE_K,
    shape: Optional[tuple[int, int]] = None,
    sharp_edges: bool = False,
) -> GuidanceTrimap:
    a = _as_hw_float(seed, shape)
    a8 = (a * 255.0).astype(np.uint8)
    dk = _ellipse_kernel(max(1, dilate_k))
    ek = _ellipse_kernel(max(1, erode_k))
    dilated = cv2.dilate((a8 > 8).astype(np.uint8) * 255, dk, iterations=1)
    eroded = cv2.erode((a8 > 200).astype(np.uint8) * 255, ek, iterations=1)
    fg = (eroded > 0).astype(np.float32)
    support = (dilated > 0).astype(np.float32)
    unknown = np.clip(support - fg, 0.0, 1.0)
    if sharp_edges:
        # Needle-sharp: minimal trimap feather — keep binary-ish FG/BG clamp rings.
        if erode_k >= 3:
            unknown = cv2.GaussianBlur(unknown, (0, 0), sigmaX=0.35)
            fg = cv2.GaussianBlur(fg, (0, 0), sigmaX=0.25)
            support = np.clip(fg + unknown, 0.0, 1.0)
    elif erode_k >= 3:
        # Legacy soft path (wide halo) — kept for Gyors optional polish.
        unknown = cv2.GaussianBlur(unknown, (0, 0), sigmaX=max(0.8, erode_k * 0.12))
        fg = cv2.GaussianBlur(fg, (0, 0), sigmaX=max(0.6, erode_k * 0.08))
        support = np.clip(fg + unknown, 0.0, 1.0)
    bg = np.clip(1.0 - support, 0.0, 1.0)
    unknown = np.clip(1.0 - fg - bg, 0.0, 1.0)
    return GuidanceTrimap(fg=fg, unknown=unknown, bg=bg)


def fuse_alpha_trimap(
    alpha: np.ndarray,
    trimap: GuidanceTrimap,
    *,
    fg_floor: float = 0.92,
    bg_ceil: float = 0.04,
    sharp_edges: bool = False,
) -> np.ndarray:
    a = _as_hw_float(alpha, trimap.shape)
    if sharp_edges:
        # Tighter BG clamp — less fog outside silhouette; keep hair mid-band.
        fg_floor = 0.96
        bg_ceil = 0.02
    w_sum = np.maximum(trimap.fg + trimap.unknown + trimap.bg, 1e-6)
    blended = (
        np.maximum(a, float(fg_floor)) * trimap.fg
        + a * trimap.unknown
        + np.minimum(a, float(bg_ceil)) * trimap.bg
    ) / w_sum
    return np.clip(blended, 0.0, 1.0).astype(np.float32)


@dataclass
class AnchorMemoryStabilizer:
    """Soft permanent prior from first polished alpha (memory-like temporal blend)."""

    strength: float = 0.38
    jump_threshold: float = 0.20
    mem_every: int = DEFAULT_MEM_EVERY
    _anchor: Optional[np.ndarray] = None
    _prev: Optional[np.ndarray] = None
    _frame_i: int = 0

    def reset(self) -> None:
        self._anchor = None
        self._prev = None
        self._frame_i = 0

    def update(self, alpha: np.ndarray) -> np.ndarray:
        a = _as_hw_float(alpha)
        self._frame_i += 1
        if self._anchor is None:
            self._anchor = a.copy()
            self._prev = a.copy()
            return a
        if self._prev is not None and self._prev.shape != a.shape:
            self._prev = cv2.resize(self._prev, (a.shape[1], a.shape[0]), interpolation=cv2.INTER_LINEAR)
        if self._anchor.shape != a.shape:
            self._anchor = cv2.resize(self._anchor, (a.shape[1], a.shape[0]), interpolation=cv2.INTER_LINEAR)
        jump = float(np.mean(np.abs(a - self._prev)))
        if jump > self.jump_threshold:
            out = a
            self._anchor = 0.65 * self._anchor + 0.35 * a
        else:
            s = float(np.clip(self.strength, 0.0, 0.9))
            out = (1.0 - s) * a + s * self._anchor
            out = 0.82 * out + 0.18 * self._prev
            # mem_every-style soft refresh of permanent prior
            if self.mem_every > 0 and (self._frame_i % self.mem_every) == 0:
                self._anchor = 0.9 * self._anchor + 0.1 * out
        self._prev = out.copy()
        return np.clip(out, 0.0, 1.0).astype(np.float32)


def _guided_filter_u8(guide_u8: np.ndarray, src_u8: np.ndarray, radius: int = 3) -> np.ndarray:
    """Edge-preserving refine: guidedFilter → jointBilateral → bilateral."""
    r = max(1, int(radius))
    try:
        return cv2.ximgproc.guidedFilter(guide_u8, src_u8, radius=r, eps=1e-3)
    except Exception:
        pass
    try:
        return cv2.ximgproc.jointBilateralFilter(
            guide_u8, src_u8, d=max(5, r), sigma_color=10, sigma_space=max(2, r)
        )
    except Exception:
        return cv2.bilateralFilter(src_u8, d=max(5, r), sigmaColor=18, sigmaSpace=max(2, r))


def refine_unknown_band(
    alpha: np.ndarray,
    trimap: GuidanceTrimap,
    *,
    amount: float = 0.4,
    sharp_edges: bool = False,
    frame_bgr: Optional[np.ndarray] = None,
) -> np.ndarray:
    """Emphasize soft edges only in the unknown band (hair/fringe).

    sharp_edges: prefer guided/bilateral over heavy Gaussian so hair stays detailed
    without a thick foggy halo.
    """
    a = _as_hw_float(alpha, trimap.shape)
    if sharp_edges:
        a8 = (np.clip(a, 0.0, 1.0) * 255.0).astype(np.uint8)
        if frame_bgr is not None and frame_bgr.shape[:2] == a.shape[:2]:
            gray = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2GRAY)
        else:
            gray = a8
        guided = _guided_filter_u8(gray, a8, radius=3).astype(np.float32) / 255.0
        # Tiny uncertain-band blend only — no wide Gaussian feather.
        amt = float(np.clip(amount, 0.0, 1.0)) * 0.35
        out = a * (1.0 - trimap.unknown * amt) + guided * (trimap.unknown * amt)
        # Slight contrast in mid-alpha to keep needle-sharp silhouette
        mid = ((out > 0.12) & (out < 0.88)).astype(np.float32)
        out = out + mid * trimap.unknown * 0.12 * (out - 0.5)
        return np.clip(out, 0.0, 1.0).astype(np.float32)

    blurred = cv2.GaussianBlur(a, (0, 0), sigmaX=1.35)
    amt = float(np.clip(amount, 0.0, 1.0))
    out = a * (1.0 - trimap.unknown * amt) + blurred * (trimap.unknown * amt)
    mid = 0.5
    out = out + trimap.unknown * amt * 0.18 * (out - mid)
    # Light bilateral-like edge hold via guided mix with original
    edge = cv2.Laplacian(a, cv2.CV_32F, ksize=3)
    edge = np.clip(np.abs(edge), 0.0, 1.0)
    out = out + trimap.unknown * 0.08 * edge * (a - out)
    return np.clip(out, 0.0, 1.0).astype(np.float32)


def warmup_alpha(
    matte_fn,
    bgr: np.ndarray,
    *,
    n_warmup: int = DEFAULT_WARMUP,
) -> np.ndarray:
    """Settle backbone on frame 0 (MatAnyone2-inspired warmup)."""
    n = max(1, int(n_warmup))
    a = matte_fn(bgr)
    for _ in range(n - 1):
        a = matte_fn(bgr)
    return a


def apply_quality_pass(
    alpha: np.ndarray,
    *,
    seed: Optional[np.ndarray] = None,
    stabilizer: Optional[AnchorMemoryStabilizer] = None,
    erode_k: Optional[int] = None,
    dilate_k: Optional[int] = None,
    sharp_edges: bool = True,
    frame_bgr: Optional[np.ndarray] = None,
) -> np.ndarray:
    """One-frame Max-quality polish without MatAnyone2 weights.

    sharp_edges=True (default): tighter trimap + guided fringe (CapCut-like sharp bake).
    """
    if erode_k is None:
        erode_k = SHARP_ERODE_K if sharp_edges else DEFAULT_ERODE_K
    if dilate_k is None:
        dilate_k = SHARP_DILATE_K if sharp_edges else DEFAULT_DILATE_K
    seed_a = seed if seed is not None else alpha
    trimap = build_guidance_trimap(
        seed_a,
        erode_k=erode_k,
        dilate_k=dilate_k,
        shape=alpha.shape[:2],
        sharp_edges=sharp_edges,
    )
    fused = fuse_alpha_trimap(alpha, trimap, sharp_edges=sharp_edges)
    fused = refine_unknown_band(
        fused,
        trimap,
        amount=0.28 if sharp_edges else 0.4,
        sharp_edges=sharp_edges,
        frame_bgr=frame_bgr,
    )
    if stabilizer is not None:
        fused = stabilizer.update(fused)
    return fused
