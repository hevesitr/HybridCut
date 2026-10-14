"""Optional diagnostics for weak/empty mattes and slow export.

Gated by env (all off by default — reversible):

- ``HYBRID_DIAG_MATTE=1`` — log trigger values when UI would show
  "Maszk gyenge" / empty person preview (degenerate or empty matte).
- ``HYBRID_DIAG_ALPHA_DUMP=1`` — write raw vs post-encode alpha PNG dumps
  under ``HYBRID_DIAG_DIR`` (default: temp ``hybridcut_diag/``).
- ``HYBRID_DIAG_EXPORT_TIMING=1`` — log bake/export stage wall times.

No secrets, no model weights, no video payloads in logs — stats only.
"""

from __future__ import annotations

import logging
import os
import time
from pathlib import Path
from typing import Any, Optional

import numpy as np

logger = logging.getLogger("hybrid_editor.diag_matte")

# Frontend toast "Maszk gyenge" keys off matte_error matching these (App.tsx).
_MASZK_GYENGE_RE = ("egyenletes", "teljes-keret", "0–255", "0-255")


def _flag(name: str) -> bool:
    raw = (os.environ.get(name) or "").strip().lower()
    return raw in {"1", "true", "yes", "on"}


def diag_matte_enabled() -> bool:
    return _flag("HYBRID_DIAG_MATTE")


def diag_alpha_dump_enabled() -> bool:
    return _flag("HYBRID_DIAG_ALPHA_DUMP")


def diag_export_timing_enabled() -> bool:
    return _flag("HYBRID_DIAG_EXPORT_TIMING")


def diag_dir() -> Path:
    env = (os.environ.get("HYBRID_DIAG_DIR") or "").strip()
    if env:
        p = Path(env)
    else:
        tmp = Path(os.environ.get("TMPDIR") or os.environ.get("TEMP") or "/tmp")
        p = tmp / "hybridcut_diag"
    p.mkdir(parents=True, exist_ok=True)
    return p


def alpha_stats(alpha: Optional[np.ndarray]) -> dict[str, Any]:
    """Compact numeric summary — safe for logs."""
    if alpha is None:
        return {"present": False}
    a = np.asarray(alpha, dtype=np.float32)
    if a.size == 0:
        return {"present": True, "size": 0}
    if a.ndim == 3:
        a = a[..., -1]
    if a.max() > 1.5:
        a = a / 255.0
    cover = float((a > 0.15).mean())
    return {
        "present": True,
        "shape": [int(a.shape[0]), int(a.shape[1])],
        "min": round(float(a.min()), 4),
        "max": round(float(a.max()), 4),
        "mean": round(float(a.mean()), 4),
        "std": round(float(a.std()), 4),
        "cover_gt_015": round(cover, 4),
        "opaque_ge_099": round(float((a >= 0.99).mean()), 4),
    }


def would_trigger_maszk_gyenge(matte_error: Optional[str]) -> bool:
    """Mirror frontend App.tsx degenerate toast gate (ASCII/Unicode variants)."""
    if not matte_error:
        return False
    low = str(matte_error).lower()
    return any(k.lower() in low for k in _MASZK_GYENGE_RE)


def log_matte_trigger(
    *,
    where: str,
    t_sec: float,
    matte_error: Optional[str],
    matte_empty: bool,
    recovered: bool,
    alpha: Optional[np.ndarray] = None,
    extra: Optional[dict[str, Any]] = None,
) -> None:
    """Log when empty preview or Maszk-gyenge condition is met."""
    if not diag_matte_enabled():
        return
    gyenge = would_trigger_maszk_gyenge(matte_error)
    if not (matte_empty or gyenge):
        return
    payload: dict[str, Any] = {
        "where": where,
        "t_sec": round(float(t_sec), 3),
        "matte_empty": bool(matte_empty),
        "matte_recovered": bool(recovered),
        "maszk_gyenge_toast": gyenge,
        "matte_error": (matte_error or "")[:240],
        "alpha": alpha_stats(alpha),
    }
    if extra:
        payload.update(extra)
    logger.warning("DIAG_MATTE_WEAK %s", payload)


def maybe_dump_alpha_pair(
    *,
    tag: str,
    t_sec: float,
    raw_alpha: Optional[np.ndarray],
    post_alpha: Optional[np.ndarray] = None,
) -> None:
    """Write raw / post alpha PNGs when ``HYBRID_DIAG_ALPHA_DUMP=1``."""
    if not diag_alpha_dump_enabled():
        return
    try:
        import cv2  # local import — keep module light when unused
    except Exception:  # noqa: BLE001
        logger.warning("DIAG_ALPHA_DUMP: OpenCV unavailable")
        return
    out = diag_dir() / "alpha"
    out.mkdir(parents=True, exist_ok=True)
    stamp = f"{tag}_t{float(t_sec):.3f}".replace(".", "p")

    def _write(name: str, alpha: Optional[np.ndarray]) -> None:
        if alpha is None:
            return
        a = np.asarray(alpha, dtype=np.float32)
        if a.ndim == 3:
            a = a[..., -1]
        if a.max() <= 1.5:
            a8 = (np.clip(a, 0, 1) * 255).astype(np.uint8)
        else:
            a8 = np.clip(a, 0, 255).astype(np.uint8)
        path = out / f"{stamp}_{name}.png"
        cv2.imwrite(str(path), a8)
        logger.info("DIAG_ALPHA_DUMP wrote %s %s", path, alpha_stats(alpha))

    _write("raw", raw_alpha)
    if post_alpha is not None:
        _write("post", post_alpha)


class ExportStageTimer:
    """Wall-clock stages for bake/export — enabled by ``HYBRID_DIAG_EXPORT_TIMING``."""

    def __init__(self, label: str) -> None:
        self.label = label
        self.enabled = diag_export_timing_enabled()
        self._t0 = time.perf_counter()
        self._last = self._t0
        self.stages: list[tuple[str, float]] = []

    def mark(self, stage: str) -> None:
        if not self.enabled:
            return
        now = time.perf_counter()
        dt = now - self._last
        self.stages.append((stage, dt))
        self._last = now
        logger.info(
            "DIAG_EXPORT_TIMING %s stage=%s dt_s=%.3f total_s=%.3f",
            self.label,
            stage,
            dt,
            now - self._t0,
        )

    def finish(self) -> dict[str, float]:
        if not self.enabled:
            return {}
        self.mark("done")
        summary = {name: round(dt, 3) for name, dt in self.stages}
        summary["total_s"] = round(time.perf_counter() - self._t0, 3)
        logger.info("DIAG_EXPORT_TIMING %s summary=%s", self.label, summary)
        return summary
