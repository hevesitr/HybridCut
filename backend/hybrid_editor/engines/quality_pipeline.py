"""MatAnyone2-inspired quality helpers (ideas only — no MatAnyone2 source).

Techniques: first-frame warmup, erode/dilate guidance trimap, anchor memory blend,
unknown-band fringe refine, optional mid-clip re-warmup on large drift.
Clean reimplementation for the hybrid tree. S-Lab weights are NOT used here.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import cv2
import numpy as np

DEFAULT_ERODE_K = 10
DEFAULT_DILATE_K = 10
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
    if erode_k >= 3:
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
) -> np.ndarray:
    a = _as_hw_float(alpha, trimap.shape)
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


def refine_unknown_band(alpha: np.ndarray, trimap: GuidanceTrimap, *, amount: float = 0.4) -> np.ndarray:
    """Emphasize soft edges only in the unknown band (hair/fringe)."""
    a = _as_hw_float(alpha, trimap.shape)
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
    erode_k: int = DEFAULT_ERODE_K,
    dilate_k: int = DEFAULT_DILATE_K,
) -> np.ndarray:
    """One-frame Max-quality polish without MatAnyone2 weights."""
    seed_a = seed if seed is not None else alpha
    trimap = build_guidance_trimap(seed_a, erode_k=erode_k, dilate_k=dilate_k, shape=alpha.shape[:2])
    fused = fuse_alpha_trimap(alpha, trimap)
    fused = refine_unknown_band(fused, trimap)
    if stabilizer is not None:
        fused = stabilizer.update(fused)
    return fused
