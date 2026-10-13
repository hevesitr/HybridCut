"""Person-auto contracts superseded by ``2026-10-11-cuda-restore``.

Full-person auto RVM only — no session face wand.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[2]
SYNC = ROOT / "SYNC_VERSION.txt"
SEED = ROOT / "frontend" / "src" / "components" / "SeedPaint.tsx"
APP = ROOT / "frontend" / "src" / "App.tsx"
CSS = ROOT / "frontend" / "src" / "styles" / "app.css"
API_TS = ROOT / "frontend" / "src" / "lib" / "api.ts"
MAX_Q = ROOT / "backend" / "hybrid_editor" / "engines" / "max_quality.py"
SESSION = ROOT / "backend" / "hybrid_editor" / "session.py"
POLISH = ROOT / "backend" / "hybrid_editor" / "engines" / "videoeditor_polish.py"
README = ROOT / "README.md"
RESTART = ROOT / "docs" / "seed-crash-restart.md"


def test_sync_stamp_auto_person():
    assert SYNC.read_text(encoding="utf-8").strip() == "2026-10-13-matte-safe"


def test_default_seed_is_union_full_person():
    from hybrid_editor.engines.max_quality import MaxQualityEngine

    eng = MaxQualityEngine()
    h, w = 48, 48
    auto = np.ones((h, w), dtype=np.float32)
    bgr = np.zeros((h, w, 3), dtype=np.uint8)
    out = eng._seed_for(bgr, auto)  # noqa: SLF001
    assert float((out > 0.5).mean()) > 0.9
    assert eng.seed_mode == "union"
    assert eng.user_seed is None
    assert eng.person_matte_info().get("full_person_default") is True
    assert eng.person_matte_info().get("auto_person_matte") is True


def test_replace_face_ignored_auto_only():
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
    assert eng.person_matte_info().get("full_person_default") is True


def test_open_and_select_purge_any_disk_seed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    from hybrid_editor.cache.seed_mask import save_seed
    from hybrid_editor.session import EditorSession

    sess = EditorSession()
    face = np.zeros((40, 40), dtype=np.float32)
    face[5:18, 12:28] = 1.0
    seed_png = tmp_path / "clip.seed.png"
    save_seed(seed_png, face, mode="union", part=None)
    monkeypatch.setattr(sess, "_seed_path", lambda: seed_png)
    sess._load_seed_for_selection()
    assert not seed_png.is_file()
    assert sess._seed_alpha is None
    assert sess.status().get("full_person_matte") is True


def test_fresh_open_auto_person_matte_without_wand():
    import cv2

    from hybrid_editor.engines.max_quality import MaxQualityEngine
    from hybrid_editor.media.video_io import is_matte_empty

    eng = MaxQualityEngine()
    h, w = 160, 120
    bgr = np.zeros((h, w, 3), dtype=np.uint8)
    bgr[:] = (90, 70, 40)
    cv2.rectangle(bgr, (w // 2 - 22, h // 2 - 5), (w // 2 + 22, h - 12), (40, 55, 160), -1)
    cv2.ellipse(bgr, (w // 2, h // 2 - 28), (18, 22), 0, 0, 360, (90, 140, 210), -1)
    assert eng.user_seed is None
    alpha = eng._polish(bgr, warmup=True)  # noqa: SLF001
    assert not is_matte_empty(alpha)
    assert float((alpha > 0.35).mean()) > 0.02


def test_reconnect_and_multi_person_keep_limbs():
    import cv2

    from hybrid_editor.engines.videoeditor_polish import (
        APEX_SPEC,
        keep_person_instances_soft,
        polish_videoeditor,
        reconnect_body_parts,
    )

    h, w = 180, 220
    bgr = np.zeros((h, w, 3), dtype=np.uint8)
    bgr[:] = (40, 90, 40)
    alpha = np.zeros((h, w), dtype=np.float32)
    cv2.ellipse(alpha, (60, 90), (30, 50), 0, 0, 360, 1.0, -1)
    cv2.circle(alpha, (95, 70), 8, 1.0, -1)
    cv2.ellipse(alpha, (160, 95), (22, 42), 0, 0, 360, 1.0, -1)
    cv2.rectangle(alpha, (4, 4), (16, 18), 0.55, -1)

    bridged = reconnect_body_parts(alpha, gap_px=9)
    assert float(bridged[70, 88:96].max()) > 0.3
    kept = keep_person_instances_soft(alpha, min_area_frac=0.005, relative_frac=0.12)
    assert float(kept[90, 60]) > 0.7
    assert float(kept[95, 160]) > 0.65
    out = polish_videoeditor(alpha, bgr, spec=APEX_SPEC)
    assert float(out[90, 60]) > 0.65
    assert float(out[95, 160]) > 0.55


def test_ui_auto_only_no_wand():
    assert not SEED.is_file()
    app = APP.read_text(encoding="utf-8")
    api = API_TS.read_text(encoding="utf-8")
    session = SESSION.read_text(encoding="utf-8")
    css = CSS.read_text(encoding="utf-8")
    polish = POLISH.read_text(encoding="utf-8")
    assert "Varázsceruza" not in app
    assert "full_person_matte" in session
    assert "_purge_seed_disk" in session
    assert "reconnect_body_parts" in polish
    assert "full_person_matte" in api
    assert "person-restore" in css or "auto-person" in css
    assert RESTART.is_file()
    assert "2026-10-11-cuda-restore" in README.read_text(encoding="utf-8")
    assert (
        "person-restore" in MAX_Q.read_text(encoding="utf-8")
        or "auto-person" in MAX_Q.read_text(encoding="utf-8")
        or "No-op" in MAX_Q.read_text(encoding="utf-8")
    )
