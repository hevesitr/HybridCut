"""Disk-backed soft-alpha MaskStore (Concat-inspired ideas, our implementation).

- Persist alpha PNG under media-hash directory
- Nearest lookup within REACH_MS
- Decoded LRU for scrub revisit without re-running ORT
"""

from __future__ import annotations

import hashlib
import logging
import threading
from collections import OrderedDict
from pathlib import Path
from typing import Optional

import cv2
import numpy as np

logger = logging.getLogger(__name__)

# Sparse pre-analyse density (masks per second of media). REACH covers nearest scrub hit.
MASK_RATE = 10
REACH_MS = max(50, int(2500 / MASK_RATE))  # 250 ms at MASK_RATE=10
_DECODED_LRU = 96


def media_key(media_path: Path | str) -> str:
    path = Path(media_path)
    try:
        st = path.stat()
        raw = f"{path.resolve().as_posix()}|{st.st_size}|{st.st_mtime_ns}"
    except OSError:
        raw = str(path)
    return hashlib.sha1(raw.encode("utf-8", errors="replace")).hexdigest()[:16]


def mask_dir(root: Path, media_path: Path | str, *, subject: str = "person") -> Path:
    return Path(root) / "cache" / "masks" / f"{media_key(media_path)}-{subject}"


def millis_for_seconds(seconds: float) -> int:
    return int(round(max(0.0, float(seconds)) * 1000.0))


def mask_filename(millis: int) -> str:
    return f"{int(millis):09d}.png"


class MaskStore:
    """One media file's soft-alpha masks on disk + decoded LRU."""

    def __init__(self, directory: Path, *, model_id: str = "hybrid-fast") -> None:
        self.dir = Path(directory)
        self.model_id = str(model_id or "hybrid-fast")
        self._lock = threading.RLock()
        self._times: list[int] = []
        self._decoded: OrderedDict[int, np.ndarray] = OrderedDict()
        self._writer: Optional[threading.Thread] = None
        self._pending: list[tuple[int, np.ndarray]] = []
        self._cancel = False
        self.open()

    def open(self) -> None:
        with self._lock:
            self._times = []
            self._decoded.clear()
            if not self.dir.is_dir():
                return
            times: list[int] = []
            for entry in self.dir.iterdir():
                if not entry.is_file() or entry.suffix.lower() != ".png":
                    continue
                try:
                    times.append(int(entry.stem))
                except ValueError:
                    continue
            times.sort()
            out: list[int] = []
            for t in times:
                if not out or out[-1] != t:
                    out.append(t)
            self._times = out

    def ensure_dir(self) -> None:
        self.dir.mkdir(parents=True, exist_ok=True)
        model_file = self.dir / "model"
        try:
            if not model_file.is_file():
                model_file.write_text(self.model_id + "\n", encoding="utf-8")
        except OSError as exc:
            logger.debug("mask store model tag: %s", exc)

    def __len__(self) -> int:
        with self._lock:
            return len(self._times)

    def nearest_millis(self, seconds: float, *, reach_ms: int = REACH_MS) -> Optional[int]:
        with self._lock:
            times = self._times
            if not times:
                return None
            wanted = millis_for_seconds(seconds)
            lo, hi = 0, len(times)
            while lo < hi:
                mid = (lo + hi) // 2
                if times[mid] < wanted:
                    lo = mid + 1
                else:
                    hi = mid
            candidates: list[int] = []
            if lo < len(times):
                candidates.append(times[lo])
            if lo > 0:
                candidates.append(times[lo - 1])
            best = min(candidates, key=lambda at: abs(at - wanted))
            if abs(best - wanted) > int(reach_ms):
                return None
            return best

    def get_alpha(
        self,
        seconds: float,
        *,
        reach_ms: int = REACH_MS,
        shape: Optional[tuple[int, int]] = None,
    ) -> Optional[np.ndarray]:
        millis = self.nearest_millis(seconds, reach_ms=reach_ms)
        if millis is None:
            return None
        with self._lock:
            hit = self._decoded.get(millis)
            if hit is not None:
                self._decoded.move_to_end(millis)
                alpha = hit
            else:
                alpha = None
        if alpha is None:
            path = self.dir / mask_filename(millis)
            if not path.is_file():
                return None
            gray = cv2.imread(str(path), cv2.IMREAD_GRAYSCALE)
            if gray is None or gray.size == 0:
                return None
            alpha = (gray.astype(np.float32) / 255.0).clip(0.0, 1.0)
            with self._lock:
                self._decoded[millis] = alpha
                self._decoded.move_to_end(millis)
                while len(self._decoded) > _DECODED_LRU:
                    self._decoded.popitem(last=False)
        if shape is not None and alpha.shape[:2] != shape:
            h, w = shape
            alpha = cv2.resize(alpha, (w, h), interpolation=cv2.INTER_LINEAR)
        return alpha

    def put(self, seconds: float, alpha: np.ndarray) -> None:
        if alpha is None or getattr(alpha, "size", 0) == 0:
            return
        millis = millis_for_seconds(seconds)
        self.ensure_dir()
        gray = np.clip(np.asarray(alpha, dtype=np.float32) * 255.0, 0, 255).astype(np.uint8)
        path = self.dir / mask_filename(millis)
        try:
            ok = cv2.imwrite(str(path), gray)
        except Exception as exc:  # noqa: BLE001
            logger.debug("mask store write failed: %s", exc)
            return
        if not ok:
            return
        with self._lock:
            if millis not in self._times:
                lo, hi = 0, len(self._times)
                while lo < hi:
                    mid = (lo + hi) // 2
                    if self._times[mid] < millis:
                        lo = mid + 1
                    else:
                        hi = mid
                self._times.insert(lo, millis)
            self._decoded[millis] = np.asarray(alpha, dtype=np.float32)
            self._decoded.move_to_end(millis)
            while len(self._decoded) > _DECODED_LRU:
                self._decoded.popitem(last=False)

    def put_async(self, seconds: float, alpha: np.ndarray) -> None:
        if alpha is None or getattr(alpha, "size", 0) == 0:
            return
        millis = millis_for_seconds(seconds)
        payload = np.asarray(alpha, dtype=np.float32).copy()
        with self._lock:
            self._pending.append((millis, payload))
            if self._writer is not None and self._writer.is_alive():
                return
            self._writer = threading.Thread(
                target=self._drain_writes, daemon=True, name="hybrid-mask-store"
            )
            self._writer.start()

    def _drain_writes(self) -> None:
        while True:
            with self._lock:
                if not self._pending or self._cancel:
                    return
                millis, alpha = self._pending.pop(0)
            try:
                self.put(millis / 1000.0, alpha)
            except Exception as exc:  # noqa: BLE001
                logger.debug("mask store async put: %s", exc)

    def clear_memory(self) -> None:
        with self._lock:
            self._decoded.clear()
            self._pending.clear()
