"""Videoeditor-compatible bake output paths — ``C:\\bgcut\\{stem}_full_nobg.mov``."""

from __future__ import annotations

import os
import sys
from pathlib import Path


DEFAULT_WIN_BGCUT = Path(r"C:\bgcut")
SCOPE_FULL = "full"


def default_bgcut_dir() -> Path:
    """Default export directory (create on write).

    Order: ``HYBRID_BGCUT_DIR`` → ``C:\\bgcut`` on Windows → ``$TMPDIR/bgcut`` elsewhere.
    """
    env = (os.environ.get("HYBRID_BGCUT_DIR") or "").strip()
    if env:
        return Path(env)
    if sys.platform.startswith("win"):
        return DEFAULT_WIN_BGCUT
    tmp = Path(os.environ.get("TMPDIR") or os.environ.get("TEMP") or "/tmp")
    return tmp / "bgcut"


def nobg_stem(media_stem: str, scope: str = SCOPE_FULL) -> str:
    """``29308762a_full_nobg`` from media stem + matte scope."""
    stem = (media_stem or "clip").strip() or "clip"
    # Strip accidental prior suffixes so re-exports stay clean
    for suffix in ("_full_nobg", "_nobg", "_preview"):
        if stem.endswith(suffix):
            stem = stem[: -len(suffix)]
    sc = (scope or SCOPE_FULL).strip() or SCOPE_FULL
    return f"{stem}_{sc}_nobg"


def nobg_mov_path(media_stem: str, *, out_dir: Path | None = None, scope: str = SCOPE_FULL) -> Path:
    """``C:\\bgcut\\{stem}_full_nobg.mov`` (dir created by caller/writer)."""
    base = Path(out_dir) if out_dir is not None else default_bgcut_dir()
    return base / f"{nobg_stem(media_stem, scope)}.mov"


def nobg_preview_path(media_stem: str, *, out_dir: Path | None = None, scope: str = SCOPE_FULL) -> Path:
    """Companion H.264: ``{stem}_full_nobg_preview.mp4`` (Videoeditor open-output pattern)."""
    base = Path(out_dir) if out_dir is not None else default_bgcut_dir()
    return base / f"{nobg_stem(media_stem, scope)}_preview.mp4"


def ensure_bgcut_dir(out_dir: Path | None = None) -> Path:
    d = Path(out_dir) if out_dir is not None else default_bgcut_dir()
    d.mkdir(parents=True, exist_ok=True)
    return d
