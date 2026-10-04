"""Proxy encode priority lanes (Concat-inspired — our code).

HOT: frames under / near playhead (immediate scrub).
WARM: ahead prefetch lane (AHEAD window).
COLD: background proxy file encode for long revisit (optional).
Never runs ORT — decode/resize/optional disk proxy only.
"""

from __future__ import annotations

import logging
import os
import threading
from collections import OrderedDict
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Callable, Optional

import cv2
import numpy as np

logger = logging.getLogger(__name__)

ReadFn = Callable[[int], Optional[np.ndarray]]


class Lane(str, Enum):
    HOT = "hot"
    WARM = "warm"
    COLD = "cold"


@dataclass
class LaneStats:
    hot_hits: int = 0
    warm_hits: int = 0
    cold_hits: int = 0
    misses: int = 0
    cold_encoded: int = 0

    def to_dict(self) -> dict:
        return {
            "hot_hits": self.hot_hits,
            "warm_hits": self.warm_hits,
            "cold_hits": self.cold_hits,
            "misses": self.misses,
            "cold_encoded": self.cold_encoded,
        }


class ProxyLaneCache:
    """In-memory HOT/WARM proxy frames + optional COLD disk lane."""

    def __init__(
        self,
        *,
        hot_size: int = 16,
        warm_size: int = 64,
        cold_dir: Optional[Path] = None,
        max_long: int = 720,
    ) -> None:
        self.hot_size = max(2, int(hot_size))
        self.warm_size = max(self.hot_size, int(warm_size))
        self.cold_dir = Path(cold_dir) if cold_dir else None
        self.max_long = int(max_long)
        self._hot: OrderedDict[int, np.ndarray] = OrderedDict()
        self._warm: OrderedDict[int, np.ndarray] = OrderedDict()
        self._lock = threading.RLock()
        self.stats = LaneStats()
        self._cold_thread: Optional[threading.Thread] = None
        self._cold_cancel = threading.Event()
        self._cold_running = False

    def clear(self) -> None:
        with self._lock:
            self._hot.clear()
            self._warm.clear()
            self.stats = LaneStats()

    def put(self, idx: int, frame: np.ndarray, *, lane: Lane = Lane.WARM) -> None:
        if frame is None:
            return
        with self._lock:
            if lane is Lane.HOT:
                self._hot[idx] = frame
                self._hot.move_to_end(idx)
                while len(self._hot) > self.hot_size:
                    self._hot.popitem(last=False)
                # Mirror into warm
                self._warm[idx] = frame
                self._warm.move_to_end(idx)
            else:
                self._warm[idx] = frame
                self._warm.move_to_end(idx)
            while len(self._warm) > self.warm_size:
                self._warm.popitem(last=False)

    def get(self, idx: int) -> Optional[np.ndarray]:
        with self._lock:
            if idx in self._hot:
                self._hot.move_to_end(idx)
                self.stats.hot_hits += 1
                return self._hot[idx]
            if idx in self._warm:
                self._warm.move_to_end(idx)
                # Promote to hot
                frame = self._warm[idx]
                self._hot[idx] = frame
                self._hot.move_to_end(idx)
                while len(self._hot) > self.hot_size:
                    self._hot.popitem(last=False)
                self.stats.warm_hits += 1
                return frame
        # Cold disk
        if self.cold_dir is not None:
            path = self.cold_dir / f"{int(idx):08d}.jpg"
            if path.is_file():
                img = cv2.imread(str(path), cv2.IMREAD_COLOR)
                if img is not None:
                    with self._lock:
                        self.stats.cold_hits += 1
                        self.put(idx, img, lane=Lane.HOT)
                    return img
        with self._lock:
            self.stats.misses += 1
        return None

    def start_cold_encode(
        self,
        *,
        read_fn: ReadFn,
        frame_count: int,
        stride: int = 2,
    ) -> dict:
        """Background COLD lane: sparse JPEG proxies on disk (non-blocking)."""
        if self.cold_dir is None:
            return {"cold_running": False, "detail": "no cold_dir"}
        if os.environ.get("HYBRID_PROXY_COLD", "1").strip() in {"0", "false", "no"}:
            return {"cold_running": False, "detail": "HYBRID_PROXY_COLD disabled"}
        with self._lock:
            if self._cold_running:
                return {"cold_running": True, "detail": "already running"}
            self._cold_running = True
            self._cold_cancel.clear()
        self.cold_dir.mkdir(parents=True, exist_ok=True)

        def _run() -> None:
            encoded = 0
            try:
                step = max(1, int(stride))
                for i in range(0, max(0, int(frame_count)), step):
                    if self._cold_cancel.is_set():
                        break
                    path = self.cold_dir / f"{i:08d}.jpg"
                    if path.is_file():
                        continue
                    frame = read_fn(i)
                    if frame is None:
                        continue
                    try:
                        cv2.imwrite(str(path), frame, [int(cv2.IMWRITE_JPEG_QUALITY), 82])
                        encoded += 1
                        with self._lock:
                            self.stats.cold_encoded = encoded
                    except Exception as exc:  # noqa: BLE001
                        logger.debug("cold proxy %s: %s", i, exc)
            finally:
                with self._lock:
                    self._cold_running = False

        self._cold_thread = threading.Thread(target=_run, daemon=True, name="hybrid-proxy-cold")
        self._cold_thread.start()
        return {"cold_running": True, "detail": "cold lane encoding"}

    def cancel_cold(self) -> None:
        self._cold_cancel.set()

    def status(self) -> dict:
        with self._lock:
            return {
                "hot_size": len(self._hot),
                "warm_size": len(self._warm),
                "cold_running": self._cold_running,
                "cold_dir": str(self.cold_dir) if self.cold_dir else None,
                "stats": self.stats.to_dict(),
                "max_long": self.max_long,
            }
