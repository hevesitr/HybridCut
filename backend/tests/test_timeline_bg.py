"""Timeline + BG remove + nobg-layer contracts — stamp ``2026-10-11-ai-tracks``.

Source-contract + TimelineDoc drag/trim/track + composite helper (no ORT).
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

BACKEND = Path(__file__).resolve().parents[1]
ROOT = BACKEND.parent
sys.path.insert(0, str(BACKEND))

from hybrid_editor.media.video_io import composite_overlay_layers  # noqa: E402
from hybrid_editor.timeline.frame_plan import TimelineDoc, plan_frame  # noqa: E402

APP = ROOT / "frontend" / "src" / "App.tsx"
TL = ROOT / "frontend" / "src" / "components" / "TimelineTrack.tsx"
SEED = ROOT / "frontend" / "src" / "components" / "SeedPaint.tsx"
CSS = ROOT / "frontend" / "src" / "styles" / "app.css"
API_TS = ROOT / "frontend" / "src" / "lib" / "api.ts"
SESSION = BACKEND / "hybrid_editor" / "session.py"
SYNC = ROOT / "SYNC_VERSION.txt"
README = ROOT / "README.md"
DIST_ASSETS = ROOT / "frontend" / "dist" / "assets"


def test_sync_stamp_timeline_bg():
    assert SYNC.read_text(encoding="utf-8").strip() == "2026-10-11-rvm-matte"


def test_remove_extra_v1_and_v2():
    doc = TimelineDoc.from_media(
        path="/a.mp4",
        duration_sec=4.0,
        fps=25.0,
        width=100,
        height=100,
        out_sec=4.0,
    )
    v1b = doc.add_clip(
        media_path="/b.mp4",
        duration_sec=3.0,
        fps=25.0,
        width=100,
        height=100,
        out_sec=3.0,
    )
    v2 = doc.add_clip(
        media_path="/c.mp4",
        duration_sec=2.0,
        fps=25.0,
        width=100,
        height=100,
        out_sec=2.0,
        track=1,
        timeline_start_sec=0.5,
    )
    assert doc.remove_clip(v2.clip_id)
    assert all(int(c.track) == 0 for c in doc.clips)
    assert doc.remove_clip(v1b.clip_id)
    assert len(doc.clips) == 1
    # auto-person: last V1 may also be deleted (empty timeline)
    assert doc.remove_clip(doc.clips[0].clip_id)
    assert doc.clips == []


def test_playhead_preserves_selection():
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
    doc.select_clip(c2.clip_id)
    doc.set_playhead(0.5)
    assert doc.selected_clip_id == c2.clip_id
    assert abs(doc.playhead_sec - 0.5) < 1e-6


def test_set_track_and_place_v2():
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
    assert abs(c2.timeline_start_sec - 1.0) < 1e-6
    assert len(doc.clips_on(0)) == 1
    plan = plan_frame(doc, 1.5)
    assert len(plan.layers) == 2
    assert plan.layers[0].track == 0
    assert plan.layers[1].track == 1


def test_trim_edge_be_ki():
    doc = TimelineDoc.from_media(
        path="/a.mp4",
        duration_sec=10.0,
        fps=25.0,
        width=100,
        height=100,
        in_sec=0.0,
        out_sec=8.0,
    )
    cid = doc.clips[0].clip_id
    # Drag out handle to timeline t=5 → source out=5
    assert doc.trim_edge(cid, edge="out", timeline_t=5.0)
    assert abs(doc.clips[0].out_sec - 5.0) < 1e-6
    assert abs(doc.duration_sec() - 5.0) < 1e-6
    # Drag in handle to timeline t=1 → source in=1, duration 4
    assert doc.trim_edge(cid, edge="in", timeline_t=1.0)
    assert abs(doc.clips[0].in_sec - 1.0) < 1e-6
    assert abs(doc.duration_sec() - 4.0) < 1e-6


def test_v1_place_reorders():
    doc = TimelineDoc.from_media(
        path="/a.mp4",
        duration_sec=2.0,
        fps=25.0,
        width=80,
        height=80,
        out_sec=2.0,
    )
    c2 = doc.add_clip(
        media_path="/b.mp4",
        duration_sec=2.0,
        fps=25.0,
        width=80,
        height=80,
        out_sec=2.0,
    )
    first = doc.clips[0].clip_id
    # Drop c2 near start → becomes first
    assert doc.set_timeline_start(c2.clip_id, 0.1)
    assert doc.clips_on(0)[0].clip_id == c2.clip_id
    assert doc.clips_on(0)[1].clip_id == first


def test_composite_overlay_layers_blend():
    base = np.zeros((40, 40, 3), np.uint8)
    base[:] = (10, 200, 10)
    alpha = np.ones((40, 40), np.float32)
    ov = np.zeros((40, 40, 3), np.uint8)
    ov[:] = (200, 20, 20)
    out, a = composite_overlay_layers(base, alpha, [(ov, 0.5)])
    # Mid blend green/red
    assert int(out[20, 20, 0]) > 80
    assert float(a[20, 20]) >= 0.5


def test_session_preview_composite_and_seed_per_clip():
    src = SESSION.read_text(encoding="utf-8")
    assert "timeline_composite" in src
    assert "composite_overlay_layers" in src
    assert "def _seed_media_path" in src
    assert "_load_seed_for_selection" in src
    assert 'act in {"trim_edge", "trim"}' in src or 'trim_edge' in src
    assert "set_track" in src


def test_ui_timeline_drag_trim_wand():
    tl = TL.read_text(encoding="utf-8")
    assert "onTrimEdge" in tl
    assert "onSetTrack" in tl
    assert "tl-handle" in tl
    assert "V1" in tl and ("AI sáv" in tl or "V2" in tl)
    assert "onPolish" in tl or "Polírozás" in tl
    app = APP.read_text(encoding="utf-8")
    assert "trim_edge" in app
    assert "set_track" in app
    assert "ai_polish" in app or "runAiPolish" in app
    assert "selectedId={selected}" in app
    assert "isTypingTarget" in app
    assert "clip-bin-del" in app
    assert "canRemoveClip" in app
    assert 'runAction("remove"' in app or "runAction(\"remove\"" in app
    assert "clip-tools" in app
    assert "deleteSelectedClip" in app
    assert "concat-workspace" in app
    assert "topbar-export" in app
    assert "details-tabs" in app
    assert "Nincs tartalom a lejátszási fej alatt" in app
    assert "formatTimecode" in tl
    assert "tl-chrome-bar" in tl
    assert "tl-lane-toggles" in tl
    assert not SEED.is_file(), "SeedPaint removed in auto-person"
    app2 = APP.read_text(encoding="utf-8")
    assert "SeedPaint" not in app2
    assert "Varázsceruza" not in app2
    api = API_TS.read_text(encoding="utf-8")
    assert "trim_edge" in api
    assert "set_track" in api
    css = CSS.read_text(encoding="utf-8")
    assert "person-restore" in css or "auto-person" in css or "person-fix2" in css or "look-peak" in css or "ai-tracks" in css
    assert ".clip-bin-del" in css
    assert ".tl-handle" in css
    assert ".tl-chrome-bar" in css
    assert ".details-tabs" in css
    assert "--accent: #ff7a1a" in css
    assert "--accent-2: #b8f000" in css


def test_readme_and_dist():
    readme = README.read_text(encoding="utf-8")
    assert "2026-10-11-rvm-matte" in readme or "2026-10-11-paint-face" in readme
    assert "2026-10-11-concat-look" in readme
    assert "concat-look" in readme
    assets = list(DIST_ASSETS.glob("index-*.js")) + list(DIST_ASSETS.glob("index-*.css"))
    assert assets, "frontend/dist missing — run vite build"
