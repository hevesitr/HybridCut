"""Shadow / dark-rim / BG-residue diagnostics for cutout compositing.

Gated by ``HYBRID_DIAG_SHADOW=1`` (off by default).

For one problem frame, dumps under ``HYBRID_DIAG_DIR/shadow_fringe/<tag>/``:

- ``00_src_rgb.png`` — original BGR frame
- ``01_raw_alpha.png`` — RVM / engine alpha (0–255 gray)
- ``02_post_alpha.png`` — postprocessed alpha when distinct
- ``03_fgr_rgb.png`` — RVM ``fgr`` tensor (if any)
- ``04_fg_used_rgb.png`` — RGB actually fed to checker / BGRA
- ``05..07_comp_src_on_{white,black,magenta}.png`` — source×α over fixed BG
- ``08..10_comp_fgr_on_{white,black,magenta}.png`` — fgr×α over fixed BG
- ``11..13_comp_used_on_{white,black,magenta}.png`` — fg_used×α over fixed BG
- ``14_bg_residue_mask.png`` — mid-α pixels whose RGB ≈ estimated BG (blotch candidates)
- ``metrics.json`` — ROI α / residue / premul scores (isolate birth site)

Windows::

    $env:HYBRID_DIAG_SHADOW='1'
    $env:HYBRID_DIAG_DIR="$env:USERPROFILE\\Documents\\HybridCut_diag"
    # scrub to the bad frame, or bake one clip — dumps appear under shadow_fringe/

Interpretation (do **not** raise crush first):

1. If ``comp_src_on_white`` shows a dark rim but ``comp_fgr_on_white`` does not
   → shadow is born in **FG RGB** (source still has BG in soft α), not in α crush.
2. If raw and post α look clean but ``comp_used`` is dark → wrong FG / double-multiply.
3. If ``premul_score`` high and used RGB is dark in soft band → treat as premultiplied.
"""

from __future__ import annotations

import json
import logging
import os
import time
from pathlib import Path
from typing import Any, Optional

import numpy as np

logger = logging.getLogger("hybrid_editor.diag_shadow_fringe")


def _flag(name: str) -> bool:
    raw = (os.environ.get(name) or "").strip().lower()
    return raw in {"1", "true", "yes", "on"}


def diag_shadow_enabled() -> bool:
    return _flag("HYBRID_DIAG_SHADOW")


def diag_dir() -> Path:
    from hybrid_editor.diag_matte import diag_dir as _base

    return _base()


def _as_hw_float(alpha: Optional[np.ndarray], shape: Optional[tuple[int, int]] = None) -> Optional[np.ndarray]:
    if alpha is None:
        return None
    a = np.asarray(alpha)
    if a.ndim == 3:
        a = a[..., -1]
    a = a.astype(np.float32)
    if a.size and float(a.max()) > 1.5:
        a = a / 255.0
    a = np.clip(a, 0.0, 1.0)
    if shape is not None and a.shape[:2] != shape:
        import cv2

        a = cv2.resize(a, (shape[1], shape[0]), interpolation=cv2.INTER_LINEAR)
    return a


def _alpha_png(alpha: np.ndarray) -> np.ndarray:
    a = _as_hw_float(alpha)
    assert a is not None
    return (np.clip(a, 0.0, 1.0) * 255.0).astype(np.uint8)


def composite_over_solid(
    bgr: np.ndarray,
    alpha: np.ndarray,
    bg_bgr: tuple[int, int, int],
) -> np.ndarray:
    """Straight-alpha Porter-Duff over a solid BGR plate (no checker)."""
    a = _as_hw_float(alpha, bgr.shape[:2])
    assert a is not None
    bg = np.empty_like(bgr, dtype=np.float32)
    bg[:] = bg_bgr
    a3 = a[..., None]
    out = bgr.astype(np.float32) * a3 + bg * (1.0 - a3)
    return np.clip(out, 0, 255).astype(np.uint8)


def rim_darkness_score(
    bgr: np.ndarray,
    alpha: np.ndarray,
    *,
    bg_bgr: tuple[int, int, int] = (255, 255, 255),
) -> dict[str, float]:
    """How dark the soft-α band looks when composited on ``bg_bgr``.

    Higher ``rim_mean_deficit`` ⇒ darker fringe vs solid FG (classic shadow rim).
    """
    a = _as_hw_float(alpha, bgr.shape[:2])
    assert a is not None
    comp = composite_over_solid(bgr, a, bg_bgr).astype(np.float32)
    luma = (
        0.114 * comp[:, :, 0] + 0.587 * comp[:, :, 1] + 0.299 * comp[:, :, 2]
    )
    soft = (a > 0.12) & (a < 0.88)
    solid = a >= 0.95
    if not soft.any():
        return {
            "rim_mean_luma": 0.0,
            "solid_mean_luma": float(luma[solid].mean()) if solid.any() else 0.0,
            "rim_mean_deficit": 0.0,
            "soft_cover": 0.0,
        }
    rim = float(luma[soft].mean())
    sol = float(luma[solid].mean()) if solid.any() else float(luma.mean())
    return {
        "rim_mean_luma": round(rim, 2),
        "solid_mean_luma": round(sol, 2),
        "rim_mean_deficit": round(sol - rim, 2),
        "soft_cover": round(float(soft.mean()), 4),
    }


def premul_likelihood(fgr_bgr: np.ndarray, alpha: np.ndarray) -> dict[str, float]:
    """Heuristic: soft-band RGB much darker than solid FG after /α ⇒ likely premul."""
    a = _as_hw_float(alpha, fgr_bgr.shape[:2])
    assert a is not None
    f = fgr_bgr.astype(np.float32)
    luma = 0.114 * f[:, :, 0] + 0.587 * f[:, :, 1] + 0.299 * f[:, :, 2]
    soft = (a > 0.20) & (a < 0.80)
    solid = a >= 0.97
    if not soft.any() or not solid.any():
        return {"premul_score": 0.0, "soft_luma": 0.0, "solid_luma": 0.0, "unpremul_soft_luma": 0.0}
    soft_l = float(luma[soft].mean())
    solid_l = float(luma[solid].mean())
    a_soft = np.maximum(a[soft], 1e-3)
    unpre = float((luma[soft] / a_soft).mean())
    # If raw soft is much darker than solid but unpremul recovers → premul-ish.
    score = 0.0
    if solid_l > 1.0:
        score = max(0.0, (solid_l - soft_l) / solid_l)
        if unpre > soft_l * 1.25:
            score = min(1.0, score + 0.25)
    return {
        "premul_score": round(float(score), 3),
        "soft_luma": round(soft_l, 2),
        "solid_luma": round(solid_l, 2),
        "unpremul_soft_luma": round(unpre, 2),
    }


def estimate_bg_bgr(src_bgr: np.ndarray, alpha: Optional[np.ndarray] = None) -> np.ndarray:
    """Border / low-α median as BG plate color (light greenish-grey walls, etc.)."""
    h, w = src_bgr.shape[:2]
    b = max(2, min(h, w) // 20)
    samples = [
        src_bgr[:b, :].reshape(-1, 3),
        src_bgr[-b:, :].reshape(-1, 3),
        src_bgr[:, :b].reshape(-1, 3),
        src_bgr[:, -b:].reshape(-1, 3),
    ]
    a = _as_hw_float(alpha, (h, w)) if alpha is not None else None
    if a is not None:
        low = a < 0.08
        if float(low.mean()) > 0.02:
            samples.append(src_bgr[low].reshape(-1, 3))
    stack = np.concatenate(samples, axis=0).astype(np.float32)
    return np.median(stack, axis=0)


def bg_residue_mask(
    src_bgr: np.ndarray,
    alpha: np.ndarray,
    *,
    color_thr: float = 28.0,
    a_lo: float = 0.12,
    a_hi: float = 0.85,
) -> tuple[np.ndarray, dict[str, float]]:
    """Mid-α pixels whose RGB ≈ estimated BG — hair-edge strips / face-side blotches.

    Answers protocol step 2: is raw α already too high in those BG-looking regions?
    """
    a = _as_hw_float(alpha, src_bgr.shape[:2])
    assert a is not None
    bg = estimate_bg_bgr(src_bgr, a)
    dist = np.sqrt(((src_bgr.astype(np.float32) - bg) ** 2).sum(axis=2))
    mask = (a >= float(a_lo)) & (a <= float(a_hi)) & (dist <= float(color_thr))
    # Exclude solid person cores so hair-on-skin is not flagged as residue.
    core = a >= 0.92
    if core.any():
        try:
            import cv2

            dil = cv2.dilate(core.astype(np.uint8), np.ones((5, 5), np.uint8), iterations=1)
            # Keep residue only outside a tight core (far blotch) OR on the soft rim
            # that still matches BG color (edge strip). Rim kept; deep core dropped.
            deep = dil > 0
            # Face-side blotch often sits just outside core — keep those.
            # Only drop where α is very high AND deep inside.
            mask = mask & ~((a >= 0.92) & deep)
        except Exception:  # noqa: BLE001
            pass
    cover = float(mask.mean()) if mask.size else 0.0
    mean_a = float(a[mask].mean()) if mask.any() else 0.0
    return mask.astype(bool), {
        "residue_cover": round(cover, 4),
        "residue_mean_alpha": round(mean_a, 4),
        "bg_bgr": [round(float(x), 1) for x in bg.tolist()],
        "raw_alpha_too_high_in_bg": bool(mean_a >= 0.28 and cover >= 0.004),
    }


def dump_shadow_fringe_frame(
    *,
    tag: str,
    t_sec: float,
    src_bgr: np.ndarray,
    raw_alpha: Optional[np.ndarray],
    post_alpha: Optional[np.ndarray] = None,
    fgr_bgr: Optional[np.ndarray] = None,
    fg_used_bgr: Optional[np.ndarray] = None,
    extra: Optional[dict[str, Any]] = None,
) -> Optional[Path]:
    """Write one problem-frame dump folder. Returns folder path or None if disabled."""
    if not diag_shadow_enabled():
        return None
    try:
        import cv2
    except Exception:  # noqa: BLE001
        logger.warning("DIAG_SHADOW: OpenCV unavailable")
        return None

    src = np.asarray(src_bgr)
    if src.ndim != 3 or src.shape[2] < 3:
        logger.warning("DIAG_SHADOW: bad src_bgr shape %s", getattr(src, "shape", None))
        return None
    h, w = int(src.shape[0]), int(src.shape[1])
    stamp = f"{tag}_t{float(t_sec):.3f}".replace(".", "p")
    out = diag_dir() / "shadow_fringe" / stamp
    out.mkdir(parents=True, exist_ok=True)

    def _write(name: str, img: np.ndarray) -> None:
        path = out / name
        cv2.imwrite(str(path), img)

    _write("00_src_rgb.png", src)
    raw_a = _as_hw_float(raw_alpha, (h, w))
    post_a = _as_hw_float(post_alpha, (h, w)) if post_alpha is not None else None
    if raw_a is not None:
        _write("01_raw_alpha.png", _alpha_png(raw_a))
    if post_a is not None:
        _write("02_post_alpha.png", _alpha_png(post_a))
    a_use = post_a if post_a is not None else raw_a

    fgr = None
    if fgr_bgr is not None:
        fgr = np.asarray(fgr_bgr)
        if fgr.shape[:2] != (h, w):
            fgr = cv2.resize(fgr, (w, h), interpolation=cv2.INTER_LINEAR)
        if fgr.dtype != np.uint8:
            ff = fgr.astype(np.float32)
            if float(np.max(ff)) <= 1.5:
                ff = ff * 255.0
            fgr = np.clip(ff, 0, 255).astype(np.uint8)
        _write("03_fgr_rgb.png", fgr)

    used = fg_used_bgr if fg_used_bgr is not None else src
    used = np.asarray(used)
    if used.shape[:2] != (h, w):
        used = cv2.resize(used, (w, h), interpolation=cv2.INTER_LINEAR)
    _write("04_fg_used_rgb.png", used)

    plates = {
        "white": (255, 255, 255),
        "black": (0, 0, 0),
        "magenta": (255, 0, 255),  # BGR magenta — light BG strips pop vs checker
    }
    metrics: dict[str, Any] = {
        "tag": tag,
        "t_sec": round(float(t_sec), 3),
        "shape": [h, w],
        "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "has_fgr": fgr is not None,
        "alpha_source": "post" if post_a is not None else ("raw" if raw_a is not None else None),
    }
    if a_use is not None:
        # Protocol step 2: mid-α + BG-colored ROIs (hair-edge strip / face blotch).
        res_mask, res_stats = bg_residue_mask(src, a_use)
        metrics["bg_residue"] = res_stats
        _write(
            "14_bg_residue_mask.png",
            (res_mask.astype(np.uint8) * 255),
        )
        if raw_a is not None and post_a is not None:
            raw_m, raw_s = bg_residue_mask(src, raw_a)
            post_m, post_s = bg_residue_mask(src, post_a)
            metrics["bg_residue_raw"] = raw_s
            metrics["bg_residue_post"] = post_s
            metrics["post_vs_raw_residue_delta_cover"] = round(
                float(post_s["residue_cover"]) - float(raw_s["residue_cover"]), 4
            )
            _ = raw_m, post_m

        idx = 5
        for kind, plate in plates.items():
            _write(f"{idx:02d}_comp_src_on_{kind}.png", composite_over_solid(src, a_use, plate))
            metrics[f"src_on_{kind}"] = rim_darkness_score(src, a_use, bg_bgr=plate)
            idx += 1
        if fgr is not None:
            for kind, plate in plates.items():
                _write(f"{idx:02d}_comp_fgr_on_{kind}.png", composite_over_solid(fgr, a_use, plate))
                metrics[f"fgr_on_{kind}"] = rim_darkness_score(fgr, a_use, bg_bgr=plate)
                idx += 1
            metrics["fgr_premul"] = premul_likelihood(fgr, a_use)
        for kind, plate in plates.items():
            _write(f"{idx:02d}_comp_used_on_{kind}.png", composite_over_solid(used, a_use, plate))
            metrics[f"used_on_{kind}"] = rim_darkness_score(used, a_use, bg_bgr=plate)
            idx += 1

        # Birth-site protocol (user visual: light BG strips on checker, not total α fail).
        src_def = float(metrics.get("src_on_white", {}).get("rim_mean_deficit", 0.0))
        fgr_def = float(metrics.get("fgr_on_white", {}).get("rim_mean_deficit", src_def))
        used_def = float(metrics.get("used_on_white", {}).get("rim_mean_deficit", src_def))
        res_cover = float(res_stats.get("residue_cover", 0.0))
        res_mean_a = float(res_stats.get("residue_mean_alpha", 0.0))
        premul = float(metrics.get("fgr_premul", {}).get("premul_score", 0.0))
        post_grew = float(metrics.get("post_vs_raw_residue_delta_cover", 0.0))

        if res_cover >= 0.004 and res_mean_a >= 0.28 and post_grew <= 0.001:
            # Mid-α already high on BG-colored pixels in raw → α fog / soft RVM leftover
            hint = "raw_alpha_bg_residue"
        elif res_cover >= 0.004 and post_grew > 0.002:
            hint = "post_alpha_grew_residue"  # feather/blur/dilate/temporal
        elif fgr is not None and src_def - fgr_def > 8.0 and res_mean_a < 0.35:
            hint = "fg_rgb_source_spill"  # soft hair OK; source RGB still has BG
        elif premul >= 0.55 and used_def > src_def + 5.0:
            hint = "premul_double_multiply"
        elif used_def > src_def + 5.0:
            hint = "fg_used_worse_than_source"
        elif res_cover < 0.002 and src_def < 6.0:
            hint = "alpha_or_elsewhere"
        else:
            hint = "mixed_soft_band_spill"
        metrics["birth_site_hint"] = hint
        metrics["src_minus_fgr_deficit_white"] = round(src_def - fgr_def, 2)

    if extra:
        metrics["extra"] = extra
    (out / "metrics.json").write_text(json.dumps(metrics, indent=2), encoding="utf-8")
    logger.info(
        "DIAG_SHADOW wrote %s hint=%s src_def=%.1f fgr_def=%.1f",
        out,
        metrics.get("birth_site_hint"),
        float(metrics.get("src_on_white", {}).get("rim_mean_deficit", 0.0)),
        float(metrics.get("fgr_on_white", {}).get("rim_mean_deficit", 0.0)),
    )
    return out
