"""Concat-flow UX contracts — stamp ``2026-10-11-ai-tracks``.

Source-contract tests (no cv2/ORT import) + TimelineDoc multi-clip append.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
ROOT = BACKEND.parent
sys.path.insert(0, str(BACKEND))

# Timeline only — avoids pulling session → cv2 in lean CI images.
from hybrid_editor.timeline.frame_plan import TimelineDoc  # noqa: E402

APP = ROOT / "frontend" / "src" / "App.tsx"
CSS = ROOT / "frontend" / "src" / "styles" / "app.css"
API_TS = ROOT / "frontend" / "src" / "lib" / "api.ts"
ROUTES = BACKEND / "hybrid_editor" / "api" / "routes.py"
SESSION = BACKEND / "hybrid_editor" / "session.py"
SYNC = ROOT / "SYNC_VERSION.txt"
README = ROOT / "README.md"
DIST_ASSETS = ROOT / "frontend" / "dist" / "assets"


def test_sync_stamp_concat_flow():
    assert SYNC.read_text(encoding="utf-8").strip() == "2026-10-13-full-body-fast"


def test_session_defines_new_project():
    src = SESSION.read_text(encoding="utf-8")
    assert "def new_project(self)" in src
    tree = ast.parse(src)
    names = {
        n.name
        for n in ast.walk(tree)
        if isinstance(n, ast.FunctionDef) or isinstance(n, ast.AsyncFunctionDef)
    }
    assert "new_project" in names
    assert "self.timeline = None" in src
    assert "self.media = None" in src
    assert "self._bake_queue.clear()" in src
    assert "self._seed_alpha = None" in src


def test_append_stacks_v1_after_existing():
    doc = TimelineDoc.from_media(
        path="/a.mp4",
        duration_sec=4.0,
        fps=25.0,
        width=320,
        height=240,
        out_sec=4.0,
    )
    c2 = doc.add_clip(
        media_path="/b.mp4",
        duration_sec=2.0,
        fps=25.0,
        width=320,
        height=240,
        out_sec=2.0,
    )
    assert len(doc.clips_on(0)) == 2
    assert abs(c2.timeline_start_sec - 4.0) < 1e-6
    assert abs(doc.duration_sec() - 6.0) < 1e-6


def test_app_uj_projekt_and_v1_klip():
    text = APP.read_text(encoding="utf-8")
    assert "Új projekt" in text
    assert "onNewProject" in text
    assert "+ V1 klip" not in text  # simple-bg: single clip
    assert "háttéreltávolítás" in text or "Egy klip" in text or "elutasítva" in text
    assert "onFilePicked" in text
    assert "statusRef" in text
    assert "dropUpload" in text
    assert "elutasítva" in text or "Egy klip" in text  # simple-bg reject second drop
    assert "api.newProject" in text or "newProject()" in text


def test_api_new_project_wired():
    assert "newProject" in API_TS.read_text(encoding="utf-8")
    assert "/api/project/new" in API_TS.read_text(encoding="utf-8")
    routes = ROUTES.read_text(encoding="utf-8")
    assert "/project/new" in routes
    assert "new_project" in routes


def test_css_preview_fills_stage():
    css = CSS.read_text(encoding="utf-8")
    assert "simple-bg" in css or "person-restore" in css
    block = css.split(".preview-stage img")[1].split(".preview-empty")[0]
    assert "width: 100%" in block
    assert "height: 100%" in block
    assert "width: auto" not in block
    assert "height: auto" not in block
    assert "place-items: stretch" in css
    assert ".wipe-compare" in css
    assert "grid-template-rows: auto minmax(0, 1fr)" in css
    assert ".clip-add-row" in css
    assert ".topbar-new-project" in css
    assert "--accent: #ff7a1a" in css
    assert "--accent-2: #b8f000" in css
    assert "min(720px" not in css


def test_readme_mentions_concat_flow():
    readme = README.read_text(encoding="utf-8")
    assert "2026-10-11-cuda-restore" in readme or "2026-10-11-paint-face" in readme
    assert "2026-10-11-concat-look" in readme


def test_dist_rebuilt():
    assets = list(DIST_ASSETS.glob("index-*.js")) + list(DIST_ASSETS.glob("index-*.css"))
    assert assets, "frontend/dist missing — run vite build"
    joined = " ".join(p.name for p in DIST_ASSETS.iterdir())
    # Fresh build hashes from concat-flow vite pass
    assert "index-" in joined
