"""AI sáv removed from default flow — stamp ``2026-10-12-simple-bg3``.

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
STAMP = "2026-10-12-simple-bg3"


def test_sync_stamp_simple_bg():
    assert SYNC.read_text(encoding="utf-8").strip() == STAMP


def test_ui_no_ai_sav_polish_in_default_flow():
    tl = TL.read_text(encoding="utf-8")
    app = APP.read_text(encoding="utf-8")
    css = CSS.read_text(encoding="utf-8")
    assert "renderLane(v2" not in tl
    assert "tl-polish-btn" not in tl
    assert "tl-polish-btn" not in css
    assert ".tl-lane.ai" not in css
    assert "runAiPolish" not in app
    assert "+ V1 klip" not in app
    assert "+ B-roll" not in app
    assert "→ B-roll" not in app
    assert "AI sáv" not in tl
    assert "AI SÁV" not in tl
    assert "húzd egymás" not in app.lower()
    assert "simple-bg" in css
    assert STAMP in css or "simple-bg" in css
    # Built dist must also be clean (install refuses otherwise).
    dist = ROOT / "frontend" / "dist" / "assets"
    if dist.is_dir():
        for js in dist.glob("*.js"):
            txt = js.read_text(encoding="utf-8", errors="replace")
            assert "AI sáv" not in txt and "AI SÁV" not in txt
            assert "+ V1 klip" not in txt
            assert "+ B-roll" not in txt
        for cssf in dist.glob("*.css"):
            ctxt = cssf.read_text(encoding="utf-8", errors="replace")
            assert "tl-polish-btn" not in ctxt
            assert ".tl-lane.ai" not in ctxt


def test_readme_restart():
    readme = README.read_text(encoding="utf-8")
    assert STAMP in readme
    assert RESTART.is_file()
    restart = RESTART.read_text(encoding="utf-8")
    assert "AI sáv" in restart  # documented removed
    assert "Polírozás" in restart or "háttéreltávolítás" in restart.lower()
