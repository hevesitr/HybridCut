"""Person-fix2 contracts folded into ``2026-10-11-cuda-restore``.

Locks full-person auto RVM, multi-person/limb keep, 4K long-side helpers.
Wand/paint permanently removed.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[2]
SYNC = ROOT / "SYNC_VERSION.txt"
FEATURE = ROOT / "backend" / "hybrid_editor" / "FEATURE_PERSON_FIX2.txt"
FEATURE_AUTO = ROOT / "backend" / "hybrid_editor" / "FEATURE_AUTO_PERSON.txt"
SESSION = ROOT / "backend" / "hybrid_editor" / "session.py"
POLISH = ROOT / "backend" / "hybrid_editor" / "engines" / "videoeditor_polish.py"
CSS = ROOT / "frontend" / "src" / "styles" / "app.css"
README = ROOT / "README.md"
RESTART = ROOT / "docs" / "seed-crash-restart.md"
AI_RESTART = ROOT / "docs" / "ai-tracks-restart.md"


def test_feature_docs_and_stamp_string():
    assert FEATURE.read_text(encoding="utf-8").strip() == "2026-10-13-preview-fast"
    assert FEATURE_AUTO.read_text(encoding="utf-8").strip() == "2026-10-13-preview-fast"
    tip = SYNC.read_text(encoding="utf-8").strip()
    assert tip == "2026-10-13-preview-fast"
    assert RESTART.is_file()
    restart = RESTART.read_text(encoding="utf-8")
    assert "2026-10-11-cuda-restore" in restart
    assert AI_RESTART.is_file()
    ai = AI_RESTART.read_text(encoding="utf-8")
    assert "simple-bg" in (ROOT / "docs" / "simple-bg-restart.md").read_text(encoding="utf-8")
    assert "2026-10-11-cuda-restore" in README.read_text(encoding="utf-8")
    css = CSS.read_text(encoding="utf-8")
    assert "person-restore" in css or "auto-person" in css
    session = SESSION.read_text(encoding="utf-8")
    assert "_purge_seed_disk" in session
    assert "def polish_ai_clip" in session
    assert "full-person" in session.lower() or "full_person" in session or "auto-person" in session
    assert "reconnect_body_parts" in POLISH.read_text(encoding="utf-8")


def test_default_full_person_auto():
    from hybrid_editor.engines.max_quality import MaxQualityEngine

    eng = MaxQualityEngine()
    auto = np.ones((48, 48), dtype=np.float32)
    bgr = np.zeros((48, 48, 3), dtype=np.uint8)
    out = eng._seed_for(bgr, auto)  # noqa: SLF001
    assert float((out > 0.5).mean()) > 0.9
    assert eng.seed_mode == "union"
    assert eng.person_matte_info()["full_person_default"] is True
    assert eng.person_matte_info()["auto_person_matte"] is True
    assert eng.person_matte_info().get("multi_person") is True


def test_wand_seed_ignored():
    from hybrid_editor.engines.max_quality import MaxQualityEngine

    eng = MaxQualityEngine()
    auto = np.ones((64, 64), dtype=np.float32)
    face = np.zeros((64, 64), dtype=np.float32)
    face[8:28, 20:44] = 1.0
    eng.set_user_seed(face, mode="replace", part="face")
    out = eng._seed_for(np.zeros((64, 64, 3), dtype=np.uint8), auto)  # noqa: SLF001
    assert eng.user_seed is None
    assert eng.seed_mode == "union"
    assert float((out > 0.5).mean()) > 0.9


def test_select_and_open_purge_replace_disk(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
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
    assert sess._seed_mode == "union"
    assert sess.status()["full_person_matte"] is True


def test_replace_not_persisted(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
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
    assert sess._seed_mode == "union"
    assert sess._seed_alpha is None
    assert not seed_png.is_file()
    assert sess.status()["full_person_matte"] is True


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
