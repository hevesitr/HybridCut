"""Sparse MaskStore pre-analyse (Concat-inspired MASK_RATE≈10).

Runs off the UI thread: sample every 1/MASK_RATE seconds, write soft alphas
to disk MaskStore. Scrub then hits nearest lookup within REACH_MS.
"""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

import numpy as np

from hybrid_editor.cache.mask_store import MASK_RATE, MaskStore, mask_dir

logger = logging.getLogger(__name__)

ProgressCb = Callable[[float, str], None]
MatteFn = Callable[[np.ndarray], np.ndarray]


@dataclass
class AnalyseStatus:
    running: bool = False
    progress: float = 0.0
    status: str = ""
    masks_written: int = 0
    media_path: str = ""
    cancelled: bool = False

    def to_dict(self) -> dict:
        return {
            "analyse_running": self.running,
            "analyse_progress": self.progress,
            "analyse_status": self.status,
            "analyse_masks": self.masks_written,
            "analyse_media": self.media_path,
        }


class SparseAnalyser:
    """Background sparse MaskStore fill — never blocks the FastAPI event loop."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._thread: Optional[threading.Thread] = None
        self._cancel = threading.Event()
        self.state = AnalyseStatus()

    def status(self) -> dict:
        with self._lock:
            return self.state.to_dict()

    def cancel(self) -> None:
        self._cancel.set()

    def start(
        self,
        *,
        root: Path,
        media_path: Path,
        duration_sec: float,
        matte_fn: MatteFn,
        model_id: str = "hybrid-analyse",
        mask_rate: float = MASK_RATE,
        proxy_long: int = 720,
        in_sec: float = 0.0,
        out_sec: Optional[float] = None,
        progress: Optional[ProgressCb] = None,
    ) -> dict:
        with self._lock:
            if self.state.running:
                raise RuntimeError("Analyse already running")
            self._cancel.clear()
            self.state = AnalyseStatus(
                running=True,
                progress=0.0,
                status="Analyse indul…",
                media_path=str(media_path),
            )

        store = MaskStore(mask_dir(root, media_path, subject="person"), model_id=model_id)

        def _run() -> None:
            # Lazy import avoids cache ↔ engines circular import at module load
            from hybrid_editor.media.video_io import downscale_long_side, read_frame_at

            start = max(0.0, float(in_sec))
            end = float(out_sec) if out_sec is not None and out_sec > 0 else float(duration_sec)
            end = max(start, end)
            rate = max(1.0, float(mask_rate))
            step = 1.0 / rate
            times = []
            t = start
            while t <= end + 1e-9:
                times.append(t)
                t += step
            if not times:
                times = [start]
            total = len(times)
            written = 0
            try:
                for i, ts in enumerate(times):
                    if self._cancel.is_set():
                        with self._lock:
                            self.state.cancelled = True
                            self.state.status = "Analyse megszakítva"
                            self.state.progress = written / max(total, 1)
                        return
                    try:
                        bgr, _ = read_frame_at(Path(media_path), ts)
                        bgr = downscale_long_side(bgr, proxy_long)
                        alpha = matte_fn(bgr)
                        store.put(ts, alpha)
                        written += 1
                    except Exception as exc:  # noqa: BLE001
                        logger.debug("analyse frame %.3f: %s", ts, exc)
                    pct = (i + 1) / max(total, 1)
                    msg = f"Sparse analyse {written}/{total} (MASK_RATE={rate:g})"
                    with self._lock:
                        self.state.progress = pct
                        self.state.masks_written = written
                        self.state.status = msg
                    if progress:
                        progress(pct, msg)
                with self._lock:
                    self.state.progress = 1.0
                    self.state.masks_written = written
                    self.state.status = f"Analyse kész · {written} mask (MASK_RATE={rate:g})"
            finally:
                with self._lock:
                    self.state.running = False

        self._thread = threading.Thread(target=_run, daemon=True, name="hybrid-analyse")
        self._thread.start()
        return self.status()
