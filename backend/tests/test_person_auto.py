"""Person-matte + look-peak tip — stamp ``2026-10-11-ai-tracks``.

Full-person auto RVM is the default. Face-only (Varázsceruza replace) is
session-scoped opt-in and must never stick across select / reopen / disk.
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
RESTART = ROOT / "docs" / "look-peak-restart.md"


def test_sync_stamp_person_fix2():
    assert SYNC.read_text(encoding="utf-8").strip() == "2026-10-11-look-peak"


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


def test_replace_face_optional_then_clear_restores_full():
    from hybrid_editor.engines.max_quality import MaxQualityEngine

    eng = MaxQualityEngine()
    h, w = 64, 64
    auto = np.ones((h, w), dtype=np.float32)
    face = np.zeros((h, w), dtype=np.float32)
    face[8:28, 20:44] = 1.0
    eng.set_user_seed(face, mode="replace", part="face")
    bgr = np.zeros((h, w, 3), dtype=np.uint8)
    gated = eng._seed_for(bgr, auto)  # noqa: SLF001
    assert float((gated > 0.2).mean()) < 0.25
    assert eng.person_matte_info().get("full_person_default") is False

    eng.clear_user_seed()
    restored = eng._seed_for(bgr, auto)  # noqa: SLF001
    assert eng.seed_mode == "union"
    assert float((restored > 0.5).mean()) > 0.9
    assert eng.person_matte_info().get("full_person_default") is True


def test_near_empty_replace_seed_drops_to_union():
    from hybrid_editor.engines.max_quality import MaxQualityEngine

    eng = MaxQualityEngine()
    tiny = np.zeros((32, 32), dtype=np.float32)
    tiny[0, 0] = 0.02
    eng.set_user_seed(tiny, mode="replace", part="face")
    assert eng.user_seed is None
    assert eng.seed_mode == "union"


def test_open_and_select_skip_persisted_replace(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Disk replace must not sticky-gate after Megnyitás or clip select."""
    from hybrid_editor.cache.seed_mask import load_seed, load_seed_meta, save_seed
    from hybrid_editor.session import EditorSession

    sess = EditorSession()
    face = np.zeros((40, 40), dtype=np.float32)
    face[5:18, 12:28] = 1.0
    seed_png = tmp_path / "clip.seed.png"
    save_seed(seed_png, face, mode="replace", part="face")
    monkeypatch.setattr(sess, "_seed_path", lambda: seed_png)

    loaded = load_seed(seed_png)
    assert loaded is not None
    meta = load_seed_meta(seed_png)
    assert meta.get("mode") == "replace"
    mode = str(meta.get("mode") or "union").lower()
    if mode == "replace":
        sess._purge_seed_disk(seed_png)
    else:
        sess._apply_seed_to_engine(loaded, mode="union", part=meta.get("part"))
    assert not seed_png.is_file()
    assert sess._seed_alpha is None
    assert sess._seed_mode == "union"
    assert sess.status().get("full_person_matte") is True

    save_seed(seed_png, face, mode="replace", part="face")
    sess._load_seed_for_selection()
    assert not seed_png.is_file()
    assert sess._seed_alpha is None
    assert sess._seed_mode == "union"
    assert sess.status().get("full_person_matte") is True


def test_replace_pick_does_not_persist_to_disk(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Varázsceruza replace stays in RAM — no sticky PNG for next Megnyitás."""
    from hybrid_editor.cache.seed_mask import encode_alpha_png_b64
    from hybrid_editor.engines.base import MediaInfo
    from hybrid_editor.session import EditorSession

    sess = EditorSession()
    seed_png = tmp_path / "wand.seed.png"
    monkeypatch.setattr(sess, "_seed_path", lambda: seed_png)
    media_path = tmp_path / "clip.mp4"
    media_path.write_bytes(b"")
    sess.media = MediaInfo(
        path=str(media_path),
        duration_sec=1.0,
        fps=25.0,
        width=64,
        height=64,
        frame_count=25,
    )
    face = np.zeros((64, 64), dtype=np.float32)
    face[10:30, 18:46] = 1.0
    sess.set_seed_mask(encode_alpha_png_b64(face), mode="replace", part="face")
    assert sess._seed_mode == "replace"
    assert sess._seed_alpha is not None
    assert not seed_png.is_file()
    assert sess.status().get("full_person_matte") is False

    sess.clear_seed_mask()
    assert sess._seed_mode == "union"
    assert sess._seed_alpha is None
    assert sess.status().get("full_person_matte") is True


def test_fresh_open_auto_person_matte_without_wand():
    """Simulate Előnézet Cutout: no wand → full-person polish non-empty."""
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
    assert eng.seed_mode == "union"
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
    assert float(kept[8:16, 6:14].mean()) < 0.1

    out = polish_videoeditor(alpha, bgr, spec=APEX_SPEC)
    assert float(out[90, 60]) > 0.65
    assert float(out[95, 160]) > 0.55


def test_session_preview_bake_long_helpers():
    from hybrid_editor.engines import EngineMode
    from hybrid_editor.session import EditorSession

    sess = EditorSession()
    sess.mode = EngineMode.MAX
    sess.sharp_edges = True
    assert sess._preview_matte_long() >= 1440
    assert sess._bake_matte_long() >= 1920
    sess.mode = EngineMode.GYORS
    assert sess._preview_matte_long() == 960
    assert sess._bake_matte_long() == 720


def test_ui_full_person_escape_hatch():
    seed = SEED.read_text(encoding="utf-8")
    app = APP.read_text(encoding="utf-8")
    api = API_TS.read_text(encoding="utf-8")
    session = SESSION.read_text(encoding="utf-8")
    css = CSS.read_text(encoding="utf-8")
    polish = POLISH.read_text(encoding="utf-8")

    assert "Teljes ember" in seed
    assert "onRestoreFullPerson" in seed
    assert "seed-mode-banner" in seed
    assert "full_person_matte" in session
    assert "_purge_seed_disk" in session
    assert "_load_seed_for_selection" in session
    assert (
        "session-scoped" in session
        or "session RAM" in session
        or "never write replace" in session
    )
    assert "reconnect_body_parts" in polish
    assert "onRestoreFullPerson" in app
    assert "full_person_matte" in api
    assert "person-fix2" in css or "look-peak" in css or "ai-tracks" in css
    assert "seed-mode-banner" in css


def test_paint_face_contracts_still_present():
    seed = SEED.read_text(encoding="utf-8")
    max_q = MAX_Q.read_text(encoding="utf-8")
    assert "Varázsceruza" in seed
    assert "onWandPick" in seed
    assert "insideMaskSurface" in seed
    assert "_seed_mode" in max_q
    assert "replace" in max_q


def test_readme_restart_stamp():
    readme = README.read_text(encoding="utf-8")
    assert "2026-10-11-ai-tracks" in readme
    assert RESTART.is_file()
    restart = RESTART.read_text(encoding="utf-8")
    assert "2026-10-11-ai-tracks" in restart
    assert "Teljes ember" in restart
    assert "Varázsceruza" in restart
    assert "person-auto" in restart.lower() or "incomplete" in restart.lower()
