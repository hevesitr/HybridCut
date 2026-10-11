"""Paint-face contracts (kept under person-auto stamp).

Radír timeline isolation + Varázsceruza face-only nobg (replace seed mode).
Full-person default restored in ``2026-10-11-ai-tracks``.
"""

from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[2]
SYNC = ROOT / "SYNC_VERSION.txt"
SEED = ROOT / "frontend" / "src" / "components" / "SeedPaint.tsx"
APP = ROOT / "frontend" / "src" / "App.tsx"
CSS = ROOT / "frontend" / "src" / "styles" / "app.css"
API_TS = ROOT / "frontend" / "src" / "lib" / "api.ts"
MAX_Q = ROOT / "backend" / "hybrid_editor" / "engines" / "max_quality.py"
FACE = ROOT / "backend" / "hybrid_editor" / "cache" / "face_pick.py"
ROUTES = ROOT / "backend" / "hybrid_editor" / "api" / "routes.py"
SESSION = ROOT / "backend" / "hybrid_editor" / "session.py"
README = ROOT / "README.md"
RESTART = ROOT / "docs" / "look-peak-restart.md"
PAINT_RESTART = ROOT / "docs" / "paint-face-restart.md"


def test_sync_stamp_paint_face():
    # Superseded tip stamp; paint-face contracts still required.
    assert SYNC.read_text(encoding="utf-8").strip() == "2026-10-11-look-peak"


def test_face_pick_ellipse_on_synthetic_portrait():
    from hybrid_editor.cache.face_pick import pick_part_matte

    h, w = 240, 180
    bgr = np.full((h, w, 3), (40, 90, 30), dtype=np.uint8)
    # Skin-tone oval head in upper frame
    cv2.ellipse(bgr, (w // 2, 70), (38, 48), 0, 0, 360, (160, 180, 220), -1)
    # Torso below (should NOT dominate alpha after face pick)
    cv2.rectangle(bgr, (40, 130), (w - 40, h - 10), (50, 60, 140), -1)

    # Inject a Haar-like box via click center of head — flood/skin path if Haar misses
    result = pick_part_matte(bgr, 0.5, 0.28, erase=False)
    alpha = result["alpha"]
    assert alpha.shape == (h, w)
    assert int(result["pixels"]) > 80
    # Coverage must stay compact (not whole person / frame)
    frac = float((alpha > 0.2).mean())
    assert frac < 0.35, f"part matte too large: {frac}"
    # Upper half should hold most of the mass
    upper = float((alpha[: h // 2] > 0.2).sum())
    lower = float((alpha[h // 2 :] > 0.2).sum())
    assert upper > lower * 1.2


def test_seed_replace_mode_gates_full_person():
    from hybrid_editor.engines.max_quality import MaxQualityEngine

    eng = MaxQualityEngine()
    h, w = 64, 64
    auto = np.ones((h, w), dtype=np.float32)  # full-frame person
    face = np.zeros((h, w), dtype=np.float32)
    face[8:28, 20:44] = 1.0
    eng.set_user_seed(face, mode="replace", part="face")
    bgr = np.zeros((h, w, 3), dtype=np.uint8)
    out = eng._seed_for(bgr, auto)  # noqa: SLF001
    assert float((out > 0.2).mean()) < 0.25
    assert float(out[18, 32]) > 0.5
    assert float(out[50, 32]) < 0.15
    assert eng.seed_mode == "replace"
    assert eng.seed_part == "face"

    eng.set_user_seed(face, mode="union", part=None)
    uni = eng._seed_for(bgr, auto)  # noqa: SLF001
    assert float((uni > 0.5).mean()) > 0.9


def test_ui_radir_timeline_isolation():
    seed = SEED.read_text(encoding="utf-8")
    app = APP.read_text(encoding="utf-8")
    css = CSS.read_text(encoding="utf-8")
    assert "insideMaskSurface" in seed
    assert "stopPropagation" in seed
    assert "onPaintGesture" in seed
    assert 'data-paint-surface="1"' in seed
    assert "Radír" in seed
    assert "timeline-dock--paint-locked" in app
    assert "paint-gesture" in app
    assert "paint-tools-on" in app
    assert "timeline-dock--paint-locked" in css
    assert "overflow: hidden" in css
    assert "seed-mask--passthrough" in css
    assert "z-index: 20" in css or "z-index:20" in css.replace(" ", "")


def test_ui_varazsceruza_face_pick_wire():
    seed = SEED.read_text(encoding="utf-8")
    app = APP.read_text(encoding="utf-8")
    api = API_TS.read_text(encoding="utf-8")
    routes = ROUTES.read_text(encoding="utf-8")
    session = SESSION.read_text(encoding="utf-8")
    face = FACE.read_text(encoding="utf-8")
    max_q = MAX_Q.read_text(encoding="utf-8")

    assert "onWandPick" in seed
    assert "Varázsceruza" in seed
    assert "arcra" in seed.lower() or "Arc" in seed
    assert "seedPick" in api
    assert "/seed/pick" in api
    assert "seed/pick" in routes
    assert "pick_seed_part" in session
    assert "pick_part_matte" in face
    assert 'PART_FACE = "face"' in face
    assert '_seed_mode' in max_q
    assert 'replace' in max_q
    assert "onWandPick={onWandPick}" in app
    # Overlay Mozgatás not regresssed — paint passthrough when moveMode
    assert "moveMode" in app
    assert "seed-mask--passthrough" in seed or "pointerEvents" in seed


def test_readme_restart_stamp():
    readme = README.read_text(encoding="utf-8")
    assert "2026-10-11-ai-tracks" in readme
    assert "2026-10-11-paint-face" in readme
    assert RESTART.is_file()
    restart = RESTART.read_text(encoding="utf-8")
    assert "2026-10-11-ai-tracks" in restart
    assert "Varázsceruza" in restart
    assert "Teljes ember" in restart
    assert PAINT_RESTART.is_file()
    css = CSS.read_text(encoding="utf-8")
    assert "person-fix2" in css or "look-peak" in css or "ai-tracks" in css


def test_nobg_layer_transform_still_present():
    """Do not regress movable nobg overlay from prior stamp."""
    app = APP.read_text(encoding="utf-8")
    assert "set_transform" in app
    assert "Mozgatás" in app or "moveMode" in app
    assert "transform-drag-layer" in app
    assert "onNobgToTimeline" in app or "Nobg a timeline" in app
