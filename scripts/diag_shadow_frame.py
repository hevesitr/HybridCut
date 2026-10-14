#!/usr/bin/env python3
"""Offline shadow-fringe dump for one media frame (Windows / local).

Usage (from Videoeditor\\hybrid_cut with PYTHONPATH=backend)::

    set HYBRID_DIAG_SHADOW=1
    set HYBRID_DIAG_DIR=%USERPROFILE%\\Documents\\HybridCut_diag
    .venv\\Scripts\\python.exe ..\\HybridCut\\scripts\\diag_shadow_frame.py --media clip.mp4 --t 1.0

Or from HybridCut repo root with backend on PYTHONPATH.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path


def main() -> int:
    ap = argparse.ArgumentParser(description="Dump shadow-fringe diagnostics for one frame")
    ap.add_argument("--media", required=True, help="Video path")
    ap.add_argument("--t", type=float, default=0.0, help="Time seconds")
    ap.add_argument("--mode", choices=("gyors", "max"), default="gyors")
    args = ap.parse_args()

    os.environ.setdefault("HYBRID_DIAG_SHADOW", "1")

    root = Path(__file__).resolve().parents[1]
    backend = root / "backend"
    if str(backend) not in sys.path:
        sys.path.insert(0, str(backend))

    from hybrid_editor.engines.fast_rvm import FastEngine
    from hybrid_editor.engines.max_quality import MaxQualityEngine
    from hybrid_editor.media.video_io import read_frame_at

    media = Path(args.media)
    if not media.is_file():
        print(f"media not found: {media}", file=sys.stderr)
        return 2

    eng: FastEngine | MaxQualityEngine
    if args.mode == "max":
        eng = MaxQualityEngine()
    else:
        eng = FastEngine(prefer_quality=False)
    try:
        eng.open_media(media)
        bgr, t = read_frame_at(media, float(args.t))
        if bgr is None:
            print("failed to decode frame", file=sys.stderr)
            return 3
        if args.mode == "gyors":
            alpha = eng._matte(bgr)  # noqa: SLF001
            cut = eng._cutout_bgr(bgr, alpha)  # noqa: SLF001
            eng._maybe_diag_shadow(  # noqa: SLF001
                tag="cli_gyors",
                t_sec=t,
                src_bgr=bgr,
                alpha=alpha,
                fg_used=cut,
                extra={"cli": True, "mode": args.mode},
            )
        else:
            # Max: polish then fgr blend via preview path side effect
            frame = eng.preview_frame(float(args.t))
            print("max preview meta:", frame.meta)
            # Also dump explicitly if fgr available
            from hybrid_editor.diag_shadow_fringe import dump_shadow_fringe_frame

            rvm = getattr(getattr(eng, "_fast", None), "_rvm", None)
            fgr = getattr(rvm, "last_fgr_bgr", None) if rvm else None
            alpha = None
            # Re-read via fast matte for dump
            if hasattr(eng, "_fast") and eng._fast is not None:
                alpha = eng._fast._matte(bgr)  # noqa: SLF001
            dump_shadow_fringe_frame(
                tag="cli_max",
                t_sec=float(t),
                src_bgr=bgr,
                raw_alpha=alpha,
                fgr_bgr=fgr,
                fg_used_bgr=fgr if fgr is not None else bgr,
                extra={"cli": True, "mode": args.mode},
            )
        diag = os.environ.get("HYBRID_DIAG_DIR") or "(default temp hybridcut_diag)"
        print(f"OK — check {diag}\\shadow_fringe\\")
        return 0
    finally:
        try:
            eng.close()
        except Exception:
            pass


if __name__ == "__main__":
    raise SystemExit(main())
