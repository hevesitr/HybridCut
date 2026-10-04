"""Hybrid Videoeditor — greenfield host + matting engines."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SYNC_VERSION = (ROOT / "SYNC_VERSION.txt").read_text(encoding="utf-8").strip()

__version__ = SYNC_VERSION
