"""Peak-cutout refinements (2026-10-13-peak-cutout).

Practical upgrades inspired by open-source video-matting work — OpenCV/numpy only,
no new model downloads. Licenses of the *ideas* we adapt:

- PeterL1n/RobustVideoMatting (GPL-3.0 model; we only follow documented
  downsample_ratio guidance for ONNX we already ship — no RVM source vendored)
- Guided filter edge-aware upsample (He et al.; OpenCV ximgproc / bilateral fallback)
  — same family as atilimcetin/guided-filter (MIT) and RVM Deep Guided Filter stage
- Optical-flow temporal alpha smooth (Alpha-Flow / TemporalConsistency *idea* —
  Farneback warp + EMA; our clean reimplementation, Apache/MIT-safe)
- Color decontamination / despill already in videoeditor_polish (CapCut-parity)

Keep HybridCut single-V1 + automatic person matte.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Tuple

import cv2
import numpy as np


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


def rvm_auto_downsample_ratio(
    height: int,
    width: int,
    *,
    full_body: bool = True,
    target_long: float = 432.0,
) -> float:
    """PeterL1n RVM guidance: downsampled long side in ~256–512.

    Full-body shots need a higher ratio than portrait (official table).
    Defaults bias toward full-body so hands/feet stay in the matte.
    """
    h, w = max(1, int(height)), max(1, int(width))
    long = float(max(h, w))
    if long <= 512:
        return 1.0
    # Portrait table ≈ 0.25 @1080; full-body ≈ 0.4 @1080.
    target = float(np.clip(target_long, 256.0, 512.0))
    if full_body:
        target = min(512.0, target * 1.15)
    ds = target / long
    return float(min(1.0, max(0.125, ds)))


def guided_upsample_alpha(
    alpha_lo: np.ndarray,
    guide_bgr: np.ndarray,
    *,
    radius: int = 4,
) -> np.ndarray:
    """Edge-aware alpha upsample to guide resolution (RVM DGF-style, OpenCV).

    Bilinear alone softens hair into a gray halo; guided/joint-bilateral uses
    full-res luminance edges so silhouette snaps to the person.
    """
    guide = np.asarray(guide_bgr)
    if guide.ndim != 3:
        raise ValueError("guide_bgr must be HxWx3")
    h, w = int(guide.shape[0]), int(guide.shape[1])
    a = _as_hw_float(alpha_lo)
    if a.shape[:2] != (h, w):
        a = cv2.resize(a, (w, h), interpolation=cv2.INTER_LINEAR)
    a8 = (np.clip(a, 0.0, 1.0) * 255.0).astype(np.uint8)
    gray = cv2.cvtColor(guide, cv2.COLOR_BGR2GRAY)
    r = max(1, int(radius))
    try:
        refined = cv2.ximgproc.guidedFilter(gray, a8, radius=r, eps=1e-3)
    except Exception:
        try:
            refined = cv2.ximgproc.jointBilateralFilter(
                gray, a8, d=max(5, r * 2 + 1), sigma_color=14, sigma_space=max(3, r)
            )
        except Exception:
            refined = cv2.bilateralFilter(
                a8, d=max(5, r * 2 + 1), sigmaColor=22, sigmaSpace=max(3, r)
            )
    # Keep bilinear base for solid FG; guided only blends uncertain band.
    base = a
    guided = refined.astype(np.float32) / 255.0
    band = ((base > 0.08) & (base < 0.92)).astype(np.float32)
    band = cv2.GaussianBlur(band, (0, 0), sigmaX=0.8)
    out = base * (1.0 - 0.72 * band) + guided * (0.72 * band)
    return np.clip(out, 0.0, 1.0).astype(np.float32)


def peak_edge_crisp(alpha: np.ndarray, *, strength: float = 0.42) -> np.ndarray:
    """Local mid-band unsharp — needle silhouette without widening BG fog."""
    a = _as_hw_float(alpha)
    s = float(np.clip(strength, 0.0, 1.0))
    if s < 0.01:
        return a
    blur = cv2.GaussianBlur(a, (0, 0), sigmaX=0.9)
    hi = a - blur
    band = ((a > 0.12) & (a < 0.88)).astype(np.float32)
    band = cv2.GaussianBlur(band, (0, 0), sigmaX=0.6)
    out = a + hi * (1.35 * s) * band
    # Soft crush far lows so crisp does not revive shadow plate.
    out = np.where(out < 0.06, out * 0.35, out)
    return np.clip(out, 0.0, 1.0).astype(np.float32)


def _fgr_as_u8(fgr_bgr: np.ndarray, shape_hw: tuple[int, int]) -> np.ndarray:
    """Normalize RVM ``fgr`` to BGR uint8 at ``shape_hw`` (float 0–1 or 0–255)."""
    fgr = np.asarray(fgr_bgr)
    h, w = int(shape_hw[0]), int(shape_hw[1])
    if fgr.shape[:2] != (h, w):
        fgr = cv2.resize(fgr, (w, h), interpolation=cv2.INTER_LINEAR)
    if fgr.dtype == np.uint8:
        return fgr
    ff = fgr.astype(np.float32)
    if float(np.max(ff)) <= 1.5:
        ff = ff * 255.0
    return np.clip(ff, 0, 255).astype(np.uint8)


def ensure_straight_fgr_bgr(
    fgr_bgr: np.ndarray,
    alpha: np.ndarray,
    *,
    premul_score_gate: float = 0.55,
) -> np.ndarray:
    """If ``fgr`` looks black-premultiplied in the soft band, un-premultiply once.

    PeterL1n RVM ``fgr`` is straight RGB; some ORT exports / prior composites may
    already be associated. Un-premultiply only when the soft band is clearly dark
    vs solid FG and recovers after /α — never invent a second multiply.
    """
    fgr = _fgr_as_u8(fgr_bgr, alpha.shape[:2] if alpha.ndim >= 2 else fgr_bgr.shape[:2])
    a = _as_hw_float(alpha, fgr.shape[:2])
    soft = (a > 0.20) & (a < 0.80)
    solid = a >= 0.97
    if not soft.any() or not solid.any():
        return fgr
    luma = (
        0.114 * fgr[:, :, 0].astype(np.float32)
        + 0.587 * fgr[:, :, 1].astype(np.float32)
        + 0.299 * fgr[:, :, 2].astype(np.float32)
    )
    soft_l = float(luma[soft].mean())
    solid_l = float(luma[solid].mean())
    if solid_l < 1.0:
        return fgr
    score = (solid_l - soft_l) / solid_l
    a_soft = np.maximum(a[soft], 1e-3)
    unpre_l = float((luma[soft] / a_soft).mean())
    if score < float(premul_score_gate) or unpre_l < soft_l * 1.2:
        return fgr
    # Un-premultiply in soft + mid band only; solid FG stays as-is.
    out = fgr.astype(np.float32)
    band = (a > 0.05) & (a < 0.98)
    aa = np.maximum(a, 1e-3)[..., None]
    unpre = np.clip(out / aa, 0, 255)
    out = np.where(band[..., None], unpre, out)
    return np.clip(out, 0, 255).astype(np.uint8)


def composite_with_fgr(
    frame_bgr: np.ndarray,
    alpha: np.ndarray,
    fgr_bgr: Optional[np.ndarray],
    *,
    mix: float = 0.72,
    ensure_straight: bool = True,
) -> np.ndarray:
    """Prefer RVM foreground RGB near edges (cleaner than source*alpha alone).

    PeterL1n RVM emits ``fgr`` already decontaminated; blend it into the cutout
    RGB inside the person / fringe band when available.

    Soft hair α is unchanged — only the **RGB** under soft α is repaired. Using
    source RGB here leaves original BG color in the soft band → dark rim / residue
    on white/checker (classic shadow fringe birth site).
    """
    a = _as_hw_float(alpha, frame_bgr.shape[:2])
    base = np.asarray(frame_bgr, dtype=np.uint8)
    if fgr_bgr is None:
        return base
    fgr = _fgr_as_u8(fgr_bgr, base.shape[:2])
    if ensure_straight:
        try:
            fgr = ensure_straight_fgr_bgr(fgr, a)
        except Exception:  # noqa: BLE001
            pass
    m = float(np.clip(mix, 0.0, 1.0))
    # Stronger fgr near soft edge; solid FG can keep source texture.
    w = np.clip(a, 0.0, 1.0)
    edge = ((w > 0.08) & (w < 0.92)).astype(np.float32)
    edge = cv2.GaussianBlur(edge, (0, 0), sigmaX=1.0)
    blend = (m * (0.45 + 0.55 * edge))[..., None]
    out = base.astype(np.float32) * (1.0 - blend) + fgr.astype(np.float32) * blend
    return np.clip(out, 0, 255).astype(np.uint8)


def cutout_rgb_for_alpha(
    frame_bgr: np.ndarray,
    alpha: np.ndarray,
    fgr_bgr: Optional[np.ndarray],
    *,
    mix: float = 0.82,
    decontaminate: float = 0.55,
) -> np.ndarray:
    """Straight FG RGB for checker / BGRA — RVM ``fgr`` when present, else source.

    Does **not** multiply by α (no premultiply). Caller composites with straight α.
    Light CapCut fringe decontam after fgr kills greenish-grey BG color in soft hair
    without changing α (two-person silhouettes stay intact).
    """
    base = np.asarray(frame_bgr, dtype=np.uint8)
    if fgr_bgr is not None:
        out = composite_with_fgr(
            base, alpha, fgr_bgr, mix=float(mix), ensure_straight=True
        )
    else:
        out = base
    if float(decontaminate) > 0.01:
        try:
            from hybrid_editor.engines.videoeditor_polish import (
                decontaminate_fringe,
                suppress_color_spill,
            )

            out = decontaminate_fringe(out, alpha, strength=float(decontaminate))
            out = suppress_color_spill(out, alpha, strength=float(decontaminate) * 0.85)
        except Exception:  # noqa: BLE001
            pass
    return out


@dataclass
class FlowTemporalSmoother:
    """Optical-flow-lite temporal alpha smooth (Farneback warp + EMA).

    Reduces flicker without new models. On large motion, trust the current frame
    more so hands do not smear.
    """

    momentum: float = 0.35
    flow_pyr_scale: float = 0.5
    flow_levels: int = 2
    flow_winsize: int = 15
    _prev_gray: Optional[np.ndarray] = None
    _prev_alpha: Optional[np.ndarray] = None

    def reset(self) -> None:
        self._prev_gray = None
        self._prev_alpha = None

    def update(self, alpha: np.ndarray, frame_bgr: np.ndarray) -> np.ndarray:
        a = _as_hw_float(alpha, frame_bgr.shape[:2])
        gray = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2GRAY)
        if self._prev_gray is None or self._prev_alpha is None:
            self._prev_gray = gray
            self._prev_alpha = a.copy()
            return a
        if self._prev_gray.shape != gray.shape:
            self._prev_gray = cv2.resize(self._prev_gray, (gray.shape[1], gray.shape[0]))
        if self._prev_alpha.shape != a.shape:
            self._prev_alpha = cv2.resize(
                self._prev_alpha, (a.shape[1], a.shape[0]), interpolation=cv2.INTER_LINEAR
            )
        try:
            flow = cv2.calcOpticalFlowFarneback(
                self._prev_gray,
                gray,
                None,
                self.flow_pyr_scale,
                self.flow_levels,
                self.flow_winsize,
                2,
                5,
                1.1,
                0,
            )
        except Exception:  # noqa: BLE001
            # Fallback: plain EMA (TemporalMattingSmoother-style).
            m = float(np.clip(self.momentum, 0.0, 0.85))
            out = (1.0 - m) * a + m * self._prev_alpha
            self._prev_gray = gray
            self._prev_alpha = np.clip(out, 0.0, 1.0)
            return self._prev_alpha.copy()

        h, w = a.shape
        grid_x, grid_y = np.meshgrid(np.arange(w, dtype=np.float32), np.arange(h, dtype=np.float32))
        map_x = grid_x + flow[..., 0]
        map_y = grid_y + flow[..., 1]
        warped = cv2.remap(
            self._prev_alpha,
            map_x,
            map_y,
            interpolation=cv2.INTER_LINEAR,
            borderMode=cv2.BORDER_REPLICATE,
        )
        mag = np.sqrt(flow[..., 0] ** 2 + flow[..., 1] ** 2)
        # Large motion → trust current alpha (avoid ghost limbs).
        motion = np.clip(mag / 12.0, 0.0, 1.0)
        m = float(np.clip(self.momentum, 0.0, 0.85))
        w_prev = m * (1.0 - 0.75 * motion)
        out = (1.0 - w_prev) * a + w_prev * warped
        out = np.clip(out, 0.0, 1.0).astype(np.float32)
        self._prev_gray = gray
        self._prev_alpha = out.copy()
        return out


def peak_refine_alpha(
    alpha: np.ndarray,
    frame_bgr: np.ndarray,
    *,
    temporal: Optional[FlowTemporalSmoother] = None,
    edge_crisp: float = 0.40,
) -> np.ndarray:
    """Post-polish peak pass: optional flow temporal + edge crisp."""
    a = _as_hw_float(alpha, frame_bgr.shape[:2])
    if temporal is not None:
        a = temporal.update(a, frame_bgr)
    if edge_crisp > 0.01:
        a = peak_edge_crisp(a, strength=edge_crisp)
    return a


def preview_boost_person_alpha(alpha: np.ndarray) -> np.ndarray:
    """Gyors/Előnézet: make the person silhouette pop on checker instantly.

    Soft MobileNet mattes can look like a faint ghost. Mild mid-band lift +
    edge crisp for *display only* — bake still uses the raw/polished matte path.

    full-body-fast: do not crush soft hair/crown (old far_soft kill punched holes).
    """
    a = _as_hw_float(alpha)
    if float(a.max()) < 0.05:
        return a
    try:
        from hybrid_editor.engines.videoeditor_polish import fill_person_holes

        a = fill_person_holes(a, min_fg=0.16, close_px=11, fill_value=0.90)
    except Exception:  # noqa: BLE001
        pass
    # Halo from *pre-boost* core so corner fog is not absorbed into hair band.
    hard0 = (a >= 0.28).astype(np.uint8)
    try:
        near0 = cv2.dilate(hard0, np.ones((9, 9), np.uint8), iterations=2)
    except Exception:  # noqa: BLE001
        near0 = hard0
    out = a.copy()
    # Crush far fog BEFORE mid-band lift — soft dust must not jump past the crush band.
    far_soft = (out > 0.04) & (out < 0.32) & (near0 == 0)
    out[far_soft] *= 0.15
    # Lift soft person body only near the silhouette (blur bleed masked to halo).
    body = ((out > 0.14) & (near0 > 0)).astype(np.float32)
    body = cv2.GaussianBlur(body, (0, 0), sigmaX=1.2)
    body = body * (near0 > 0).astype(np.float32)
    out = np.clip(out + body * 0.22 * (1.0 - out), 0.0, 1.0)
    return peak_edge_crisp(out, strength=0.28)


def extract_fgr_bgr(outs: list, session: object, h: int, w: int) -> Optional[np.ndarray]:
    """Pull RVM ``fgr`` RGB→BGR uint8 when present (PeterL1n layout)."""
    try:
        metas = list(session.get_outputs())  # type: ignore[attr-defined]
    except Exception:
        metas = []
    fgr = None
    names = [str(getattr(m, "name", "") or "").lower() for m in metas]
    if outs and names and names[0] in {"fgr", "foreground", ""} and isinstance(outs[0], np.ndarray):
        fgr = outs[0]
    if fgr is None:
        for meta, o in zip(metas, outs):
            name = str(getattr(meta, "name", "") or "").lower()
            if name in {"fgr", "foreground"} and isinstance(o, np.ndarray):
                fgr = o
                break
    if fgr is None:
        return None
    arr = np.asarray(fgr, dtype=np.float32)
    if arr.ndim == 4:
        rgb = arr[0]
        if rgb.shape[0] in (3, 4):
            rgb = np.transpose(rgb[:3], (1, 2, 0))
        else:
            rgb = rgb[..., :3]
    elif arr.ndim == 3 and arr.shape[0] == 3:
        rgb = np.transpose(arr, (1, 2, 0))
    else:
        rgb = np.squeeze(arr)
        if rgb.ndim != 3:
            return None
    if rgb.shape[:2] != (h, w):
        rgb = cv2.resize(rgb, (w, h), interpolation=cv2.INTER_LINEAR)
    if float(np.max(rgb)) <= 1.5:
        rgb = rgb * 255.0
    bgr = rgb[..., ::-1]
    return np.clip(bgr, 0, 255).astype(np.uint8)
