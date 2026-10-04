"""Playhead-ahead decode prefetch (Concat idea AHEAD≈8 — our code).

Warms proxy-sized BGR frames ahead of the scrub cursor.
Cancel on seek via generation bump. Decode only — never ORT.
"""

from __future__ import annotations

import logging
import threading
from typing import Callable, Optional

logger = logging.getLogger(__name__)

AHEAD = 8


class ScrubPrefetcher:
    def __init__(
        self,
        *,
        ahead: int = AHEAD,
        read_frame: Optional[Callable[[int, int], Optional[object]]] = None,
    ) -> None:
        self.ahead = max(1, int(ahead))
        self._read_frame = read_frame
        self._lock = threading.Lock()
        self._cv = threading.Condition(self._lock)
        self._gen = 0
        self._cursor = 0
        self._direction = 1
        self._max_long = 720
        self._frame_count = 0
        self._worker: Optional[threading.Thread] = None
        self._stop = False

    def bind(
        self,
        read_frame: Callable[[int, int], Optional[object]],
        *,
        frame_count: int,
        max_long: int = 720,
    ) -> None:
        with self._lock:
            self._read_frame = read_frame
            self._frame_count = max(0, int(frame_count))
            self._max_long = int(max_long)
            self._gen += 1
            self._cursor = 0
            self._direction = 1
            self._ensure_worker()
            self._cv.notify_all()

    def reset(self) -> None:
        with self._lock:
            self._gen += 1
            self._cursor = 0
            self._frame_count = 0
            self._cv.notify_all()

    def nudge(
        self,
        frame_idx: int,
        *,
        direction: int = 1,
        max_long: Optional[int] = None,
    ) -> None:
        with self._lock:
            self._gen += 1
            self._cursor = max(0, int(frame_idx))
            self._direction = 1 if int(direction) >= 0 else -1
            if max_long is not None:
                self._max_long = int(max_long)
            self._ensure_worker()
            self._cv.notify_all()

    def shutdown(self) -> None:
        with self._lock:
            self._stop = True
            self._gen += 1
            self._cv.notify_all()

    def _ensure_worker(self) -> None:
        if self._worker is not None and self._worker.is_alive():
            return
        self._stop = False
        self._worker = threading.Thread(
            target=self._run, daemon=True, name="hybrid-scrub-prefetch"
        )
        self._worker.start()

    def _plan(self, cursor: int, direction: int, frame_count: int) -> list[int]:
        if frame_count <= 0:
            return []
        out: list[int] = []
        step = 1 if direction >= 0 else -1
        i = cursor + step
        while len(out) < self.ahead:
            if i < 0 or i >= frame_count:
                break
            out.append(i)
            i += step
        return out

    def _run(self) -> None:
        while True:
            with self._cv:
                if self._stop:
                    return
                if self._read_frame is None or self._frame_count <= 0:
                    self._cv.wait(timeout=0.5)
                    continue
                gen = self._gen
                cursor = self._cursor
                direction = self._direction
                max_long = self._max_long
                frame_count = self._frame_count
                read_frame = self._read_frame
                plan = self._plan(cursor, direction, frame_count)
                if not plan:
                    self._cv.wait(timeout=0.25)
                    continue
            for idx in plan:
                with self._lock:
                    if self._stop or gen != self._gen:
                        break
                try:
                    read_frame(idx, max_long)
                except Exception as exc:  # noqa: BLE001
                    logger.debug("scrub prefetch idx=%s: %s", idx, exc)
                    break
            with self._cv:
                if gen == self._gen and not self._stop:
                    self._cv.wait(timeout=0.5)
