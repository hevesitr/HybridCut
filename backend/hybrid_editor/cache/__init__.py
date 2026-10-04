"""Cache helpers: MaskStore, FrameCache, scrub prefetch, proxy lanes.

Note: SparseAnalyser is imported lazily via hybrid_editor.cache.analyse to avoid
circular imports (analyse → video_io → engines → fast_rvm → cache).
"""

from hybrid_editor.cache.frame_cache import FrameCache
from hybrid_editor.cache.mask_store import MASK_RATE, REACH_MS, MaskStore, mask_dir, media_key
from hybrid_editor.cache.proxy_lanes import Lane, ProxyLaneCache
from hybrid_editor.cache.scrub_prefetch import AHEAD, ScrubPrefetcher

__all__ = [
    "AHEAD",
    "FrameCache",
    "Lane",
    "MASK_RATE",
    "MaskStore",
    "ProxyLaneCache",
    "REACH_MS",
    "ScrubPrefetcher",
    "mask_dir",
    "media_key",
]


def __getattr__(name: str):
    if name == "SparseAnalyser":
        from hybrid_editor.cache.analyse import SparseAnalyser

        return SparseAnalyser
    raise AttributeError(name)
