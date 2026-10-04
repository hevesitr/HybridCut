"""MatAnyone2 local adapter — loads user-provided weights only.

IMPORTANT LICENSE:
  MatAnyone2 (pq-yang/MatAnyone2) and its checkpoints are under
  **S-Lab License 1.0 (non-commercial)**.
  This project does NOT redistribute weights or claim redistributable rights.
  Point HYBRID_MATANYONE2_WEIGHTS at a locally obtained .pth if your use allows it.

We never vendor MatAnyone2 source. Integration is optional/dynamic import or
documented sidecar. When weights/package are missing, callers use QualityPipeline.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

import numpy as np

logger = logging.getLogger(__name__)

LICENSE_NOTE = (
    "MatAnyone2 weights: S-Lab License 1.0 — NON-COMMERCIAL. "
    "Not redistributed by Hybrid Editor. User must supply local path."
)


@dataclass(frozen=True)
class MatAnyone2Status:
    available: bool
    weights_path: Optional[str]
    reason: str
    license_note: str = LICENSE_NOTE
    vram_hint_gb: float = 5.5


def resolve_weights_path() -> Optional[Path]:
    raw = os.environ.get("HYBRID_MATANYONE2_WEIGHTS", "").strip()
    if not raw:
        return None
    p = Path(raw).expanduser()
    return p if p.is_file() else None


def probe_matanyone2() -> MatAnyone2Status:
    weights = resolve_weights_path()
    if weights is None:
        return MatAnyone2Status(
            available=False,
            weights_path=None,
            reason="Set HYBRID_MATANYONE2_WEIGHTS to a local matanyone2.pth (not shipped).",
        )
    try:
        import torch  # noqa: F401
    except ImportError:
        return MatAnyone2Status(
            available=False,
            weights_path=str(weights),
            reason="PyTorch not installed — required for MatAnyone2 adapter.",
        )
    # Optional: user-installed package on PYTHONPATH (never vendored here)
    try:
        import importlib

        importlib.import_module("matanyone2")
        return MatAnyone2Status(
            available=True,
            weights_path=str(weights),
            reason="Weights + matanyone2 package detected.",
        )
    except ImportError:
        return MatAnyone2Status(
            available=False,
            weights_path=str(weights),
            reason=(
                "Weights found but matanyone2 package not importable. "
                "Install upstream MatAnyone2 into a local env (do not copy into this repo), "
                "or rely on QualityPipeline fallback."
            ),
        )


class MatAnyone2Adapter:
    """Thin wrapper; real inference only if user env provides MatAnyone2."""

    def __init__(self) -> None:
        self.status = probe_matanyone2()
        self._core: Any = None
        self._device = "cpu"

    @property
    def available(self) -> bool:
        return bool(self.status.available)

    def load(self) -> None:
        if not self.available:
            raise RuntimeError(self.status.reason)
        import torch

        self._device = "cuda" if torch.cuda.is_available() else "cpu"
        # Dynamic import — never a static dependency of the hybrid tree
        from matanyone2.inference_core import InferenceCore  # type: ignore

        weights = resolve_weights_path()
        assert weights is not None
        self._core = InferenceCore(str(weights), device=self._device)
        logger.info("MatAnyone2 adapter loaded on %s (%s)", self._device, weights)

    def reset(self) -> None:
        if self._core is not None and hasattr(self._core, "clear_memory"):
            self._core.clear_memory()

    def unload(self) -> None:
        self._core = None
        try:
            import torch

            if torch.cuda.is_available():
                torch.cuda.empty_cache()
        except Exception:  # noqa: BLE001
            pass

    def matte_sequence(
        self,
        frames_rgb: list[np.ndarray],
        seed_mask: np.ndarray,
        *,
        n_warmup: int = 10,
    ) -> list[np.ndarray]:
        """Return soft alpha list. Requires successful load()."""
        if self._core is None:
            self.load()
        # Best-effort API — upstream may differ; keep adapter boundary honest
        if hasattr(self._core, "process_video_frames"):
            return list(self._core.process_video_frames(frames_rgb, seed_mask, n_warmup=n_warmup))
        raise RuntimeError(
            "Installed matanyone2 package API mismatch — "
            "use QualityPipeline or adjust adapter to your local checkout."
        )
