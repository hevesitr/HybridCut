"""Tests for disk MaskStore + scrub prefetcher."""

from __future__ import annotations

import sys
import time
from pathlib import Path

import numpy as np

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

from hybrid_editor.cache.mask_store import REACH_MS, MaskStore
from hybrid_editor.cache.scrub_prefetch import AHEAD, ScrubPrefetcher


def test_mask_store_put_nearest(tmp_path: Path):
    store = MaskStore(tmp_path / "masks", model_id="test")
    a = np.zeros((32, 32), np.float32)
    a[8:24, 8:24] = 0.9
    store.put(0.5, a)
    assert len(store) == 1
    hit = store.get_alpha(0.52, reach_ms=REACH_MS)
    assert hit is not None
    assert hit.shape == (32, 32)
    assert float(hit[16, 16]) > 0.5
    miss = store.get_alpha(5.0, reach_ms=100)
    assert miss is None


def test_mask_store_async_and_resize(tmp_path: Path):
    store = MaskStore(tmp_path / "masks2")
    a = np.ones((40, 40), np.float32) * 0.7
    store.put_async(1.0, a)
    deadline = time.time() + 2.0
    while len(store) < 1 and time.time() < deadline:
        time.sleep(0.05)
    assert len(store) == 1
    hit = store.get_alpha(1.0, shape=(20, 20))
    assert hit is not None
    assert hit.shape == (20, 20)


def test_scrub_prefetch_ahead():
    seen: list[int] = []

    def read_frame(idx: int, max_long: int):
        seen.append(idx)
        return np.zeros((8, 8, 3), np.uint8)

    pref = ScrubPrefetcher(ahead=AHEAD)
    pref.bind(read_frame, frame_count=30, max_long=720)
    pref.nudge(5, direction=1)
    deadline = time.time() + 2.0
    while len(seen) < AHEAD and time.time() < deadline:
        time.sleep(0.05)
    pref.shutdown()
    assert len(seen) >= AHEAD
    assert seen[:AHEAD] == list(range(6, 6 + AHEAD))
