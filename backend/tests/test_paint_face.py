"""Paint-face removed under ``2026-10-11-cuda-restore``.

Contracts assert Varázsceruza / Ecset / Radír / face_pick are gone;
nobg-layer transform + auto person remain.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
SYNC = ROOT / "SYNC_VERSION.txt"
SEED = ROOT / "frontend" / "src" / "components" / "SeedPaint.tsx"
APP = ROOT / "frontend" / "src" / "App.tsx"
FACE = ROOT / "backend" / "hybrid_editor" / "cache" / "face_pick.py"
ROUTES = ROOT / "backend" / "hybrid_editor" / "api" / "routes.py"
SESSION = ROOT / "backend" / "hybrid_editor" / "session.py"
MAX_Q = ROOT / "backend" / "hybrid_editor" / "engines" / "max_quality.py"
RESTART = ROOT / "docs" / "seed-crash-restart.md"


def test_sync_stamp_auto_person():
    assert SYNC.read_text(encoding="utf-8").strip() == "2026-10-12-simple-bg2"


def test_face_pick_and_seedpaint_gone():
    assert not FACE.is_file()
    assert not SEED.is_file()
    app = APP.read_text(encoding="utf-8")
    assert "Varázsceruza" not in app
    assert "SeedPaint" not in app
    assert "onWandPick" not in app
    routes = ROUTES.read_text(encoding="utf-8")
    assert "eltávolítva" in routes or "410" in routes
    session = SESSION.read_text(encoding="utf-8")
    assert "from hybrid_editor.cache.face_pick" not in session


def test_seed_replace_mode_no_longer_gates():
    from hybrid_editor.engines.max_quality import MaxQualityEngine

    eng = MaxQualityEngine()
    h, w = 64, 64
    auto = np.ones((h, w), dtype=np.float32)
    face = np.zeros((h, w), dtype=np.float32)
    face[8:28, 20:44] = 1.0
    eng.set_user_seed(face, mode="replace", part="face")
    bgr = np.zeros((h, w, 3), dtype=np.uint8)
    out = eng._seed_for(bgr, auto)  # noqa: SLF001
    assert eng.user_seed is None
    assert eng.seed_mode == "union"
    assert float((out > 0.5).mean()) > 0.9
    assert "auto-person" in MAX_Q.read_text(encoding="utf-8") or "No-op" in MAX_Q.read_text(
        encoding="utf-8"
    )


def test_nobg_layer_transform_still_present():
    app = APP.read_text(encoding="utf-8")
    assert "set_transform" in app
    assert "Mozgatás" not in app  # simple-bg stripped or "moveMode" in app
    assert "transform-drag-layer" in app
    assert "onNobgToTimeline" in app or "Nobg a timeline" in app
    assert RESTART.is_file()
