"""Small LRU for decoded proxy BGR frames (scrub path)."""

from __future__ import annotations

import threading
from collections import OrderedDict
from typing import Optional

import numpy as np

_DEFAULT_CAP = 48


class FrameCache:
    def __init__(self, capacity: int = _DEFAULT_CAP) -> None:
        self.capacity = max(4, int(capacity))
        self._lock = threading.RLock()
        self._items: OrderedDict[tuple, np.ndarray] = OrderedDict()

    def get(self, key: tuple) -> Optional[np.ndarray]:
        with self._lock:
            hit = self._items.get(key)
            if hit is None:
                return None
            self._items.move_to_end(key)
            return hit

    def put(self, key: tuple, frame: np.ndarray) -> None:
        if frame is None or getattr(frame, "size", 0) == 0:
            return
        with self._lock:
            self._items[key] = frame
            self._items.move_to_end(key)
            while len(self._items) > self.capacity:
                self._items.popitem(last=False)

    def clear(self) -> None:
        with self._lock:
            self._items.clear()

    def __len__(self) -> int:
        with self._lock:
            return len(self._items)
