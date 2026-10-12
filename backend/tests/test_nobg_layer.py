"""Nobg movable transparent layer — stamp ``2026-10-11-ai-tracks``.

Research subset shipped: CapCut overlay cutout on V2, position X/Y, scale,
alpha preserve, reset, result-card → timeline. No keyframes / rotation / blend modes.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

BACKEND = Path(__file__).resolve().parents[1]
ROOT = BACKEND.parent
sys.path.insert(0, str(BACKEND))

from hybrid_editor.media.video_io import (  # noqa: E402
    OverlayFrame,
    composite_overlay_layers,
    looks_like_alpha_media,
    place_layer_on_canvas,
)
from hybrid_editor.timeline.frame_plan import TimelineDoc, plan_frame  # noqa: E402

APP = ROOT / "frontend" / "src" / "App.tsx"
CSS = ROOT / "frontend" / "src" / "styles" / "app.css"
API_TS = ROOT / "frontend" / "src" / "lib" / "api.ts"
SESSION = BACKEND / "hybrid_editor" / "session.py"
VIDEO_IO = BACKEND / "hybrid_editor" / "media" / "video_io.py"
SYNC = ROOT / "SYNC_VERSION.txt"
README = ROOT / "README.md"
RESTART = ROOT / "docs" / "nobg-layer-restart.md"
DIST_ASSETS = ROOT / "frontend" / "dist" / "assets"


def test_sync_stamp_nobg_layer():
    assert SYNC.read_text(encoding="utf-8").strip() == "2026-10-12-simple-bg2"


def test_looks_like_alpha_media():
    assert looks_like_alpha_media(r"C:\bgcut\upload_full_nobg.mov")
    assert looks_like_alpha_media("/tmp/foo_nobg.webm")
    assert looks_like_alpha_media("clip.webm")
    assert not looks_like_alpha_media("plain.mp4")


def test_place_and_composite_transform_alpha():
    canvas = np.zeros((100, 200, 3), np.uint8)
    canvas[:] = (20, 20, 20)
    base_a = np.ones((100, 200), np.float32)
    layer = np.zeros((40, 40, 3), np.uint8)
    layer[:] = (0, 0, 255)  # red in BGR
    la = np.ones((40, 40), np.float32)
    # Slide right (+pos_x) + scale down
    placed_bgr, placed_a = place_layer_on_canvas(
        100, 200, layer, la, pos_x=0.25, pos_y=0.0, scale=0.5
    )
    assert float(placed_a.max()) > 0.5
    # Center of placed blob should be right of canvas center
    ys, xs = np.where(placed_a > 0.5)
    assert xs.mean() > 100  # canvas center x=100
    out, a = composite_overlay_layers(
        canvas,
        base_a,
        [
            OverlayFrame(
                bgr=layer,
                opacity=1.0,
                alpha=la,
                pos_x=0.25,
                pos_y=0.0,
                scale=0.5,
            )
        ],
    )
    assert int(out[ys[0], xs[0], 2]) > 200  # red channel


def test_legacy_overlay_tuple_still_works():
    base = np.zeros((40, 40, 3), np.uint8)
    base[:] = (10, 200, 10)
    alpha = np.ones((40, 40), np.float32)
    ov = np.zeros((40, 40, 3), np.uint8)
    ov[:] = (200, 20, 20)
    out, a = composite_overlay_layers(base, alpha, [(ov, 0.5)])
    assert int(out[20, 20, 0]) > 80
    assert float(a[20, 20]) >= 0.5


def test_timeline_transform_and_nobg_plan():
    doc = TimelineDoc.from_media(
        path="/a.mp4",
        duration_sec=4.0,
        fps=25.0,
        width=320,
        height=240,
        out_sec=4.0,
    )
    nobg = doc.add_broll(
        media_path=r"C:\bgcut\upload_full_nobg.mov",
        duration_sec=2.0,
        fps=25.0,
        width=320,
        height=240,
        out_sec=2.0,
        has_alpha=True,
        label="nobg",
    )
    assert nobg.has_alpha
    assert abs(nobg.opacity - 1.0) < 1e-6
    assert doc.set_transform(nobg.clip_id, pos_x=0.3, pos_y=-0.1, scale=0.6)
    assert abs(nobg.pos_x - 0.3) < 1e-6
    assert abs(nobg.scale - 0.6) < 1e-6
    plan = plan_frame(doc, 0.5)
    assert len(plan.layers) == 2
    top = plan.layers[1]
    assert top.has_alpha
    assert abs(top.pos_x - 0.3) < 1e-6
    assert doc.reset_transform(nobg.clip_id)
    assert abs(nobg.pos_x) < 1e-6 and abs(nobg.scale - 1.0) < 1e-6
    d = doc.to_dict()
    clip = next(c for c in d["clips"] if c["clip_id"] == nobg.clip_id)
    assert clip["has_alpha"] is True
    assert "pos_x" in clip and "scale" in clip


def test_session_has_decode_and_transform_actions():
    src = SESSION.read_text(encoding="utf-8")
    assert "def _decode_layer_pixels" in src
    assert "as_nobg" in src
    assert "set_transform" in src
    assert "reset_transform" in src
    assert "read_frame_bgra" in src
    assert "OverlayFrame" in src
    vio = VIDEO_IO.read_text(encoding="utf-8")
    assert "def looks_like_alpha_media" in vio
    assert "def place_layer_on_canvas" in vio
    assert "def read_frame_bgra" in vio


def test_ui_pozicio_nobg_timeline():
    app = APP.read_text(encoding="utf-8")
    assert "Pozíció" in app
    assert "Méretérték" in app
    assert "Nobg a timeline-ra" in app
    assert "onNobgToTimeline" in app
    assert "set_transform" in app
    assert "reset_transform" in app
    assert "Mozgatás" not in app  # simple-bg stripped
    assert "Visszaállítás" in app
    assert "transform-drag-layer" in app
    api = API_TS.read_text(encoding="utf-8")
    assert "as_nobg" in api
    assert "pos_x" in api
    assert "has_alpha" in api
    css = CSS.read_text(encoding="utf-8")
    assert "person-restore" in css or "auto-person" in css or "person-fix2" in css or "look-peak" in css or "ai-tracks" in css
    assert ".transform-drag-layer" in css
    assert ".transform-block" in css


def test_readme_restart_dist():
    readme = README.read_text(encoding="utf-8")
    assert "2026-10-11-cuda-restore" in readme or "2026-10-11-paint-face" in readme
    assert RESTART.is_file()
    restart = RESTART.read_text(encoding="utf-8")
    assert "2026-10-11-paint-face" in restart or "nobg-layer" in restart or "auto-person" in restart
    assert "Research" in restart or "Kutatás" in restart or "researched" in restart.lower()
    assets = list(DIST_ASSETS.glob("index-*.js")) + list(DIST_ASSETS.glob("index-*.css"))
    assert assets, "frontend/dist missing — run vite build"
