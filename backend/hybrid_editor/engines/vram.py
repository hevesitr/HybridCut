"""VRAM / CUDA session budget for RTX 3060 8GB.

Never hold FastEngine ORT CUDA and Max MatAnyone2 CUDA at the same time.
Heuristic / CPU paths do not take the CUDA slot.
"""

from __future__ import annotations

import logging
import os
import threading
from typing import Literal, Optional

logger = logging.getLogger(__name__)

CudaSlot = Literal["fast-ort", "max-matanyone2", "none"]

_lock = threading.RLock()
_holder: CudaSlot = "none"
_detail: str = ""


def vram_budget_gb() -> float:
    raw = os.environ.get("HYBRID_VRAM_GB", "8").strip()
    try:
        return max(1.0, float(raw))
    except ValueError:
        return 8.0


def cuda_holder() -> CudaSlot:
    with _lock:
        return _holder


def acquire_cuda(slot: CudaSlot, *, detail: str = "") -> None:
    """Claim exclusive CUDA consumer. Raises if another heavy consumer holds it."""
    global _holder, _detail
    if slot == "none":
        return
    with _lock:
        if _holder not in ("none", slot):
            raise RuntimeError(
                f"VRAM guard: CUDA held by {_holder!r} ({_detail}); "
                f"cannot load {slot!r}. Unload the other engine first (8GB budget)."
            )
        _holder = slot
        _detail = detail or slot
        logger.info("CUDA slot acquired: %s (%s)", _holder, _detail)


def release_cuda(slot: CudaSlot) -> None:
    global _holder, _detail
    with _lock:
        if _holder == slot:
            logger.info("CUDA slot released: %s", slot)
            _holder = "none"
            _detail = ""


def force_release_all() -> None:
    global _holder, _detail
    with _lock:
        _holder = "none"
        _detail = ""


def status() -> dict:
    with _lock:
        return {
            "cuda_holder": _holder,
            "detail": _detail,
            "vram_budget_gb": vram_budget_gb(),
            "policy": "Never Fast ORT CUDA + Max MatAnyone2 CUDA together on 8GB.",
        }
