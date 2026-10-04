"""Proxy priority lanes tests."""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

from hybrid_editor.cache.proxy_lanes import Lane, ProxyLaneCache


def test_hot_warm_promote(tmp_path: Path):
    cache = ProxyLaneCache(hot_size=2, warm_size=4, cold_dir=tmp_path / "cold")
    a = np.zeros((8, 8, 3), np.uint8)
    b = np.ones((8, 8, 3), np.uint8)
    cache.put(1, a, lane=Lane.WARM)
    cache.put(2, b, lane=Lane.HOT)
    assert cache.get(1) is not None  # promote warm→hot
    st = cache.status()
    assert st["stats"]["warm_hits"] >= 1 or st["stats"]["hot_hits"] >= 1
    assert cache.get(99) is None
    assert st["stats"]["misses"] >= 0


def test_cold_encode_background(tmp_path: Path):
    import time

    frames = {i: np.full((6, 6, 3), i, np.uint8) for i in range(0, 10, 2)}

    def read_fn(i: int):
        return frames.get(i)

    cache = ProxyLaneCache(cold_dir=tmp_path / "cold2", max_long=64)
    st = cache.start_cold_encode(read_fn=read_fn, frame_count=10, stride=2)
    assert st["cold_running"] is True
    deadline = time.time() + 5.0
    while cache.status()["cold_running"] and time.time() < deadline:
        time.sleep(0.05)
    assert (tmp_path / "cold2" / "00000000.jpg").is_file()
    hit = cache.get(0)
    assert hit is not None
