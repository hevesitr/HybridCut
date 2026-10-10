"""Bake / háttéreltávolítás ETA helpers — RTX 3060-class calibration.

Used by UI (mirrored in frontend/src/lib/eta.ts) and tests.
Estimates wall-clock seconds for Gyors vs Max background removal bake.
"""

from __future__ import annotations

import math
import re
from typing import Literal, Optional

Mode = Literal["gyors", "max"]

# Calibrated sec/frame @ 1920×1080, CUDA ORT RVM on RTX 3060 8GB-class.
# Gyors: MobileNet + ~720 long-side proxy path.
# Max: ResNet50 full-res + APEX polish + BGRA stream + mux.
GYORS_SEC_PER_FRAME_1080P = 0.028
MAX_SEC_PER_FRAME_1080P = 0.165
REF_PIXELS = 1920 * 1080
MUX_FIXED_SEC = 2.8
MUX_PER_VIDEO_SEC = 0.035

_FRAME_RE = re.compile(r"(\d+)\s*/\s*(\d+)\s*frame", re.IGNORECASE)


def clip_duration_sec(in_sec: float, out_sec: float, fallback: float = 0.0) -> float:
    """Active In→Out span; non-positive falls back."""
    d = float(out_sec) - float(in_sec)
    if d > 1e-6:
        return d
    return max(0.0, float(fallback))


def frame_count(duration_sec: float, fps: float) -> int:
    f = float(fps) if fps and fps > 1e-6 else 25.0
    d = max(0.0, float(duration_sec))
    return max(1, int(round(d * f))) if d > 1e-6 else 0


def resolution_factor(width: int, height: int, mode: Mode) -> float:
    """Scale sec/frame by megapixels vs 1080p. Gyors softens (proxy path)."""
    w = max(1, int(width or 1920))
    h = max(1, int(height or 1080))
    mp = (w * h) / REF_PIXELS
    if mode == "gyors":
        # Proxy long-side ~720 → resolution impact is muted.
        return 0.42 + 0.58 * min(1.4, max(0.35, mp**0.62))
    return min(2.4, max(0.5, mp**0.88))


def sec_per_frame(width: int, height: int, mode: Mode) -> float:
    base = GYORS_SEC_PER_FRAME_1080P if mode == "gyors" else MAX_SEC_PER_FRAME_1080P
    return base * resolution_factor(width, height, mode)


def estimate_bake_sec(
    duration_sec: float,
    fps: float,
    width: int,
    height: int,
    mode: Mode,
) -> float:
    """Estimated wall-clock seconds for háttéreltávolítás bake (+ light mux)."""
    n = frame_count(duration_sec, fps)
    if n <= 0:
        return 0.0
    matte = n * sec_per_frame(width, height, mode)
    mux = MUX_FIXED_SEC + MUX_PER_VIDEO_SEC * max(0.0, float(duration_sec))
    return matte + mux


def format_eta_hu(seconds: float) -> str:
    """Hungarian approximate duration: „Kb. 12 mp” / „Kb. 1 perc 20 mp”."""
    if seconds is None or not math.isfinite(seconds) or seconds <= 0:
        return "Kb. —"
    s = int(round(float(seconds)))
    if s < 1:
        s = 1
    if s < 60:
        return f"Kb. {s} mp"
    mins, rem = divmod(s, 60)
    if mins < 60:
        if rem == 0:
            return f"Kb. {mins} perc"
        return f"Kb. {mins} perc {rem} mp"
    hours, mins = divmod(mins, 60)
    if mins == 0 and rem == 0:
        return f"Kb. {hours} óra"
    if rem == 0:
        return f"Kb. {hours} óra {mins} perc"
    return f"Kb. {hours} óra {mins} perc {rem} mp"


def parse_bake_frames(bake_status: str) -> Optional[tuple[int, int]]:
    """Parse ``Max bake 12/300 frame`` → (done, total)."""
    if not bake_status:
        return None
    m = _FRAME_RE.search(str(bake_status))
    if not m:
        return None
    done, total = int(m.group(1)), int(m.group(2))
    if total <= 0:
        return None
    return max(0, done), total


def remaining_bake_sec(
    *,
    duration_sec: float,
    fps: float,
    width: int,
    height: int,
    mode: Mode,
    bake_progress: float = 0.0,
    bake_status: str = "",
) -> float:
    """Remaining ETA while bake runs — prefer frame counters, else progress."""
    total = estimate_bake_sec(duration_sec, fps, width, height, mode)
    parsed = parse_bake_frames(bake_status)
    if parsed:
        done, n = parsed
        left = max(0, n - done)
        spf = sec_per_frame(width, height, mode)
        # After last frame, mux still remains (progress often jumps near 0.88+).
        mux = MUX_FIXED_SEC + MUX_PER_VIDEO_SEC * max(0.0, float(duration_sec))
        if left <= 0:
            prog = max(0.0, min(1.0, float(bake_progress or 0.0)))
            if prog >= 0.99:
                return 0.0
            return mux * max(0.05, 1.0 - prog)
        return left * spf + mux * 0.85

    prog = max(0.0, min(1.0, float(bake_progress or 0.0)))
    if prog <= 0.01:
        return total
    if prog >= 0.99:
        return 0.0
    return total * (1.0 - prog)


def both_mode_etas(
    duration_sec: float,
    fps: float,
    width: int,
    height: int,
) -> dict[str, dict[str, float | str]]:
    """Convenience: Gyors + Max estimates with HU labels."""
    out: dict[str, dict[str, float | str]] = {}
    for mode in ("gyors", "max"):
        sec = estimate_bake_sec(duration_sec, fps, width, height, mode)  # type: ignore[arg-type]
        out[mode] = {"seconds": sec, "label_hu": format_eta_hu(sec)}
    return out
