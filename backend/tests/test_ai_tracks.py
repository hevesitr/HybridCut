"""AI sáv + Polírozás on stack — stamp ``2026-10-11-matte-visible`` (AI sáv kept)."""

from __future__ import annotations

import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
ROOT = BACKEND.parent
sys.path.insert(0, str(BACKEND))

from hybrid_editor.timeline.frame_plan import TimelineDoc, plan_frame  # noqa: E402

SYNC = ROOT / "SYNC_VERSION.txt"
APP = ROOT / "frontend" / "src" / "App.tsx"
TL = ROOT / "frontend" / "src" / "components" / "TimelineTrack.tsx"
API_TS = ROOT / "frontend" / "src" / "lib" / "api.ts"
SESSION = BACKEND / "hybrid_editor" / "session.py"
CSS = ROOT / "frontend" / "src" / "styles" / "app.css"
README = ROOT / "README.md"
RESTART = ROOT / "docs" / "ai-tracks-restart.md"
DIST_ASSETS = ROOT / "frontend" / "dist" / "assets"


def test_sync_stamp_ai_tracks():
    assert SYNC.read_text(encoding="utf-8").strip() == "2026-10-11-matte-visible"


def test_stack_marks_ai_lane_pending():
    doc = TimelineDoc.from_media(
        path="/a.mp4",
        duration_sec=4.0,
        fps=25.0,
        width=100,
        height=100,
        out_sec=4.0,
    )
    c2 = doc.add_clip(
        media_path="/b.mp4",
        duration_sec=3.0,
        fps=25.0,
        width=100,
        height=100,
        out_sec=3.0,
    )
    assert doc.set_track(c2.clip_id, 1, timeline_start_sec=1.0)
    assert int(c2.track) == 1
    assert c2.ai_lane is True
    assert c2.ai_polish == "pending"
    assert c2.track_label().startswith("AI sáv")
    d = doc.to_dict()
    assert d["tracks"][1]["label"] == "AI sáv"
    row = next(c for c in d["clips"] if c["clip_id"] == c2.clip_id)
    assert row["ai_polish"] == "pending"
    assert "Polírozás" in (row.get("ai_polish_label_hu") or "")


def test_add_broll_pending_ai_polish():
    doc = TimelineDoc.from_media(
        path="/a.mp4",
        duration_sec=2.0,
        fps=25.0,
        width=80,
        height=80,
        out_sec=2.0,
    )
    b = doc.add_broll(
        media_path="/b.mp4",
        duration_sec=1.5,
        fps=25.0,
        width=80,
        height=80,
        out_sec=1.5,
    )
    assert int(b.track) == 1
    assert b.ai_lane is True
    assert b.ai_polish == "pending"
    plan = plan_frame(doc, 0.5)
    assert len(plan.layers) == 2


def test_session_ai_polish_action_wired():
    src = SESSION.read_text(encoding="utf-8")
    assert "def polish_ai_clip" in src
    assert "ai_polish" in src
    assert "_status_with_ai_polish" in src
    assert "Polírozás" in src
    # auto-person: AI Polírozás always full-person RVM (no paint/wand seed)
    assert "full-person" in src.lower() or "full_person" in src or "auto-person" in src
    assert "_preview_matte_long" in src
    assert "_apply_seed_to_engine(None)" in src or "clear_user_seed" in src


def test_ui_ai_sav_labels_and_auto_polish():
    tl = TL.read_text(encoding="utf-8")
    app = APP.read_text(encoding="utf-8")
    api = API_TS.read_text(encoding="utf-8")
    css = CSS.read_text(encoding="utf-8")
    assert "AI sáv" in tl
    assert "onPolish" in tl
    assert "tl-polish-btn" in tl
    assert "runAiPolish" in app
    assert "ai_polish_recommended" in app or "ai_polish" in app
    assert "Polírozás" in app
    assert '"ai_polish"' in api or "ai_polish" in api
    assert "2026-10-11-matte-visible" in css
    assert "2026-10-11-ai-tracks" in css or "look-peak" in css  # prior retained
    assert ".tl-polish-btn" in css
    assert ".tl-lane.ai" in css or "tl-lane.ai" in css


def test_readme_restart_dist():
    readme = README.read_text(encoding="utf-8")
    assert "2026-10-11-matte-visible" in readme
    assert "2026-10-11-ai-tracks" in readme
    assert RESTART.is_file()
    restart = RESTART.read_text(encoding="utf-8")
    assert "AI sáv" in restart
    assert "Polírozás" in restart
    assets = list(DIST_ASSETS.glob("index-*.js")) + list(DIST_ASSETS.glob("index-*.css"))
    assert assets, "frontend/dist missing — run vite build"
