"""AI sáv removed from default flow — stamp ``2026-10-12-simple-bg2``.

Backend TimelineDoc may still model track>=1 for tests; UI default flow does not.
"""

from __future__ import annotations

import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
ROOT = BACKEND.parent
sys.path.insert(0, str(BACKEND))

SYNC = ROOT / "SYNC_VERSION.txt"
APP = ROOT / "frontend" / "src" / "App.tsx"
TL = ROOT / "frontend" / "src" / "components" / "TimelineTrack.tsx"
CSS = ROOT / "frontend" / "src" / "styles" / "app.css"
README = ROOT / "README.md"
RESTART = ROOT / "docs" / "simple-bg-restart.md"
STAMP = "2026-10-12-simple-bg2"


def test_sync_stamp_simple_bg():
    assert SYNC.read_text(encoding="utf-8").strip() == STAMP


def test_ui_no_ai_sav_polish_in_default_flow():
    tl = TL.read_text(encoding="utf-8")
    app = APP.read_text(encoding="utf-8")
    css = CSS.read_text(encoding="utf-8")
    assert "renderLane(v2" not in tl
    assert "tl-polish-btn" not in tl
    assert "runAiPolish" not in app
    assert "+ B-roll" not in app
    assert "→ B-roll" not in app
    assert "simple-bg" in css
    assert STAMP in css or "simple-bg" in css


def test_readme_restart():
    readme = README.read_text(encoding="utf-8")
    assert STAMP in readme
    assert RESTART.is_file()
    restart = RESTART.read_text(encoding="utf-8")
    assert "AI sáv" in restart  # documented removed
    assert "Polírozás" in restart or "háttéreltávolítás" in restart.lower()
