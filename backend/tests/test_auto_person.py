"""Auto-person only (feature ``2026-10-11-cuda-restore``).

Paint/wand removed. Full-person RVM is the sole selection path.
Delete/Backspace removes any selected timeline clip (V1 / AI sáv).
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[2]
SYNC = ROOT / "SYNC_VERSION.txt"
FEATURE = ROOT / "backend" / "hybrid_editor" / "FEATURE_AUTO_PERSON.txt"
SESSION = ROOT / "backend" / "hybrid_editor" / "session.py"
MAX_Q = ROOT / "backend" / "hybrid_editor" / "engines" / "max_quality.py"
FACE = ROOT / "backend" / "hybrid_editor" / "cache" / "face_pick.py"
SEED_UI = ROOT / "frontend" / "src" / "components" / "SeedPaint.tsx"
APP = ROOT / "frontend" / "src" / "App.tsx"
TL = ROOT / "frontend" / "src" / "components" / "TimelineTrack.tsx"
API_TS = ROOT / "frontend" / "src" / "lib" / "api.ts"
ROUTES = ROOT / "backend" / "hybrid_editor" / "api" / "routes.py"
FRAME_PLAN = ROOT / "backend" / "hybrid_editor" / "timeline" / "frame_plan.py"
RESTART = ROOT / "docs" / "seed-crash-restart.md"
README = ROOT / "README.md"
CSS = ROOT / "frontend" / "src" / "styles" / "app.css"


def test_stamp_and_docs():
    assert FEATURE.read_text(encoding="utf-8").strip() == "2026-10-12-simple-bg2"
    assert SYNC.read_text(encoding="utf-8").strip() == "2026-10-12-simple-bg2"
    assert RESTART.is_file()
    restart = RESTART.read_text(encoding="utf-8")
    assert "2026-10-11-cuda-restore" in restart
    assert "Delete" in restart or "Backspace" in restart
    assert "Varázsceruza" in restart  # documented as removed
    assert "2026-10-11-cuda-restore" in README.read_text(encoding="utf-8")
    css = CSS.read_text(encoding="utf-8")
    assert "person-restore" in css or "auto-person" in css


def test_manual_tools_removed():
    assert not FACE.is_file()
    assert not SEED_UI.is_file()
    app = APP.read_text(encoding="utf-8")
    assert "SeedPaint" not in app
    assert "Varázsceruza" not in app
    assert "Ecset" not in app
    assert "Radír" not in app
    assert "Lasszó" not in app
    assert "onWandPick" not in app
    # Seed modal leftovers must never throw into Assist status (seed-crash).
    assert "showLargeSeed" not in app
    assert "setShowLargeSeed" not in app
    routes = ROUTES.read_text(encoding="utf-8")
    assert "410" in routes or "eltávolítva" in routes
    session = SESSION.read_text(encoding="utf-8")
    assert "face_pick" in session  # mention in removed docstring only
    assert "from hybrid_editor.cache.face_pick" not in session
    api = API_TS.read_text(encoding="utf-8")
    assert "eltávolítva" in api or "Removed" in api


def test_seed_crash_stamp_and_max_polish_guard():
    feature = ROOT / "backend" / "hybrid_editor" / "FEATURE_SEED_CRASH.txt"
    assert feature.read_text(encoding="utf-8").strip() == "2026-10-12-simple-bg2"
    max_q = MAX_Q.read_text(encoding="utf-8")
    assert "is_matte_degenerate" in max_q
    assert "keeping base RVM/heuristic alpha" in max_q
    dist_js = list((ROOT / "frontend" / "dist" / "assets").glob("index-*.js"))
    assert dist_js, "frontend dist missing — run npm run build"
    bundled = dist_js[0].read_text(encoding="utf-8", errors="ignore")
    assert "setShowLargeSeed" not in bundled
    assert "showLargeSeed" not in bundled


def test_delete_key_ux_wired():
    app = APP.read_text(encoding="utf-8")
    tl = TL.read_text(encoding="utf-8")
    fp = FRAME_PLAN.read_text(encoding="utf-8")
    assert "isTypingTarget" in app
    assert 'e.key !== "Delete"' in app or 'e.key === "Delete"' in app
    assert "Backspace" in app
    assert "canRemoveClip" in app
    assert "onDelete" in tl
    assert "Delete" in tl or "Backspace" in tl
    assert "shellRef.current?.focus" in tl
    assert "tabIndex={0}" in tl
    # Last V1 may be removed
    assert "len(v1) <= 1" not in fp
    assert "including the last V1" in fp or "Any selected" in fp


def test_last_v1_clip_can_be_removed():
    from hybrid_editor.timeline import TimelineDoc

    doc = TimelineDoc.from_media(
        path="/a.mp4",
        duration_sec=2.0,
        fps=25.0,
        width=100,
        height=100,
        out_sec=2.0,
    )
    cid = doc.clips[0].clip_id
    assert doc.remove_clip(cid)
    assert doc.clips == []


def test_set_user_seed_is_noop_auto_only():
    from hybrid_editor.engines.max_quality import MaxQualityEngine

    eng = MaxQualityEngine()
    face = np.zeros((48, 48), dtype=np.float32)
    face[8:28, 20:44] = 1.0
    eng.set_user_seed(face, mode="replace", part="face")
    assert eng.user_seed is None
    assert eng.seed_mode == "union"
    auto = np.ones((48, 48), dtype=np.float32)
    out = eng._seed_for(np.zeros((48, 48, 3), dtype=np.uint8), auto)  # noqa: SLF001
    assert float((out > 0.5).mean()) > 0.9
    assert eng.person_matte_info()["full_person_default"] is True
    assert eng.person_matte_info()["auto_person_matte"] is True


def test_disk_seed_purged_on_select(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    from hybrid_editor.cache.seed_mask import save_seed
    from hybrid_editor.session import EditorSession

    sess = EditorSession()
    face = np.zeros((40, 40), dtype=np.float32)
    face[5:18, 12:28] = 1.0
    seed_png = tmp_path / "clip.seed.png"
    save_seed(seed_png, face, mode="replace", part="face")
    monkeypatch.setattr(sess, "_seed_path", lambda: seed_png)
    sess._load_seed_for_selection()
    assert not seed_png.is_file()
    assert sess._seed_alpha is None
    assert sess._seed_mode == "union"
    assert sess.status()["full_person_matte"] is True


def test_set_seed_mask_clears_instead_of_applying(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
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
        width=64,
        height=64,
        fps=25.0,
        frame_count=25,
        duration_sec=1.0,
    )
    face = np.zeros((64, 64), dtype=np.float32)
    face[10:30, 18:46] = 1.0
    sess.set_seed_mask(encode_alpha_png_b64(face), mode="replace", part="face")
    assert sess._seed_alpha is None
    assert sess._seed_mode == "union"
    assert sess.status()["full_person_matte"] is True


def test_pick_seed_part_raises_gone():
    from hybrid_editor.session import EditorSession

    sess = EditorSession()
    with pytest.raises(RuntimeError, match="eltávolítva"):
        sess.pick_seed_part(x=0.5, y=0.3)


def test_fresh_preview_matte_without_wand():
    import cv2

    from hybrid_editor.engines.max_quality import MaxQualityEngine
    from hybrid_editor.media.video_io import is_matte_empty

    eng = MaxQualityEngine()
    h, w = 160, 120
    bgr = np.zeros((h, w, 3), dtype=np.uint8)
    bgr[:] = (90, 70, 40)
    cv2.rectangle(bgr, (w // 2 - 22, h // 2 - 5), (w // 2 + 22, h - 12), (40, 55, 160), -1)
    cv2.ellipse(bgr, (w // 2, h // 2 - 28), (18, 22), 0, 0, 360, (90, 140, 210), -1)
    alpha = eng._polish(bgr, warmup=True)  # noqa: SLF001
    assert not is_matte_empty(alpha)
    assert float((alpha > 0.35).mean()) > 0.02


def test_multi_person_and_limb_reconnect():
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
    assert float(reconnect_body_parts(alpha, gap_px=9)[70, 88:96].max()) > 0.3
    kept = keep_person_instances_soft(alpha, min_area_frac=0.005, relative_frac=0.12)
    assert float(kept[90, 60]) > 0.7
    assert float(kept[95, 160]) > 0.65
    out = polish_videoeditor(alpha, bgr, spec=APEX_SPEC)
    assert float(out[90, 60]) > 0.65
    assert float(out[95, 160]) > 0.55


def test_max_long_side_helpers():
    from hybrid_editor.engines import EngineMode
    from hybrid_editor.session import EditorSession

    sess = EditorSession()
    sess.mode = EngineMode.MAX
    sess.sharp_edges = True
    assert sess._preview_matte_long() >= 1440
    assert sess._bake_matte_long() >= 1920
