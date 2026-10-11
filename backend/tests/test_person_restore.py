"""Person-restore (`2026-10-11-rvm-matte`).

Root cause: wand-era face mattes in MaskStore disk poisoned Gyors preview
(skip ORT → empty cover → source-only UI). Restore: purge on open + Max
full-person path without re-adding paint/wand.
"""

from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[2]
SYNC = ROOT / "SYNC_VERSION.txt"
FEATURE = ROOT / "backend" / "hybrid_editor" / "FEATURE_PERSON_RESTORE.txt"
FEATURE_AUTO = ROOT / "backend" / "hybrid_editor" / "FEATURE_AUTO_PERSON.txt"
SESSION = ROOT / "backend" / "hybrid_editor" / "session.py"
MASK_STORE = ROOT / "backend" / "hybrid_editor" / "cache" / "mask_store.py"
FAST = ROOT / "backend" / "hybrid_editor" / "engines" / "fast_rvm.py"
MAX_Q = ROOT / "backend" / "hybrid_editor" / "engines" / "max_quality.py"
RESTART = ROOT / "docs" / "rvm-matte-restart.md"
RESTART_PRIOR = ROOT / "docs" / "person-restore-restart.md"
README = ROOT / "README.md"
CSS = ROOT / "frontend" / "src" / "styles" / "app.css"
SEED_UI = ROOT / "frontend" / "src" / "components" / "SeedPaint.tsx"
APP = ROOT / "frontend" / "src" / "App.tsx"


def _synthetic_person_bgr(h: int = 160, w: int = 120) -> np.ndarray:
    bgr = np.zeros((h, w, 3), np.uint8)
    bgr[:] = (90, 70, 40)
    cv2.rectangle(bgr, (w // 2 - 22, h // 2 - 5), (w // 2 + 22, h - 12), (40, 55, 160), -1)
    cv2.ellipse(bgr, (w // 2, h // 2 - 28), (18, 22), 0, 0, 360, (90, 140, 210), -1)
    noise = np.random.default_rng(1).integers(0, 18, size=bgr.shape, dtype=np.uint8)
    return cv2.add(bgr, noise)


def _write_person_clip(path: Path, n: int = 8) -> None:
    w, h = 160, 120
    writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"mp4v"), 10, (w, h))
    assert writer.isOpened(), "VideoWriter failed"
    for i in range(n):
        frame = _synthetic_person_bgr(h, w)
        shift = i * 2
        M = np.float32([[1, 0, shift], [0, 1, 0]])
        frame = cv2.warpAffine(frame, M, (w, h), borderMode=cv2.BORDER_REPLICATE)
        writer.write(frame)
    writer.release()


def test_stamp_and_docs():
    assert FEATURE.read_text(encoding="utf-8").strip() == "2026-10-11-rvm-matte"
    assert FEATURE_AUTO.read_text(encoding="utf-8").strip() == "2026-10-11-rvm-matte"
    assert SYNC.read_text(encoding="utf-8").strip() == "2026-10-11-rvm-matte"
    assert RESTART.is_file() and RESTART_PRIOR.is_file()
    restart = RESTART.read_text(encoding="utf-8")
    prior = RESTART_PRIOR.read_text(encoding="utf-8")
    assert "2026-10-11-rvm-matte" in restart
    assert "MaskStore" in prior or "cache" in prior.lower()
    assert "Varázsceruza" in prior
    assert "Delete" in prior or "Backspace" in prior or "Delete" in restart
    assert "2026-10-11-rvm-matte" in README.read_text(encoding="utf-8")
    css = CSS.read_text(encoding="utf-8")
    assert "matte-visible" in css or "person-restore" in css
    assert "def purge" in MASK_STORE.read_text(encoding="utf-8")
    assert "_purge_mask_store" in SESSION.read_text(encoding="utf-8")
    assert "_ensure_full_person_max" in SESSION.read_text(encoding="utf-8")
    assert "purge()" in FAST.read_text(encoding="utf-8")
    maxq = MAX_Q.read_text(encoding="utf-8")
    assert "matte-visible" in maxq or "person-restore" in maxq


def test_wand_paint_still_absent():
    assert not SEED_UI.is_file()
    app = APP.read_text(encoding="utf-8")
    assert "Varázsceruza" not in app
    assert "SeedPaint" not in app
    assert "Ecset" not in app


def test_set_user_seed_noop_keeps_auto_guidance():
    from hybrid_editor.engines.max_quality import MaxQualityEngine

    eng = MaxQualityEngine()
    auto = np.ones((40, 40), dtype=np.float32)
    eng._seed = auto.copy()  # noqa: SLF001
    eng.set_user_seed(np.ones((40, 40), dtype=np.float32), mode="replace", part="face")
    assert eng.user_seed is None
    assert eng.seed_mode == "union"
    # Auto guidance prior must survive set_user_seed no-op (was cleared too aggressively).
    assert eng._seed is not None  # noqa: SLF001
    assert float(eng._seed.mean()) > 0.9  # noqa: SLF001


def test_mask_store_purge_wipes_disk(tmp_path: Path):
    from hybrid_editor.cache.mask_store import MaskStore

    store = MaskStore(tmp_path / "masks", model_id="test")
    face = np.zeros((48, 48), dtype=np.float32)
    face[8:20, 18:30] = 1.0  # tiny face scrap
    store.put(0.0, face)
    assert any(tmp_path.joinpath("masks").glob("*.png"))
    store.purge()
    assert list((tmp_path / "masks").glob("*.png")) == []
    assert store.get_alpha(0.0) is None


def test_open_purges_poisoned_maskstore_and_elevates_max(tmp_path: Path):
    from hybrid_editor.cache.mask_store import MaskStore, mask_dir
    from hybrid_editor import ROOT as HE_ROOT
    from hybrid_editor.engines import EngineMode
    from hybrid_editor.media.video_io import is_matte_empty
    from hybrid_editor.session import EditorSession

    clip = tmp_path / "person.mp4"
    _write_person_clip(clip)

    # Pre-poison MaskStore like wand-era face-only cache
    store_dir = mask_dir(HE_ROOT, str(clip.resolve()), subject="person")
    store_dir.mkdir(parents=True, exist_ok=True)
    poison = MaskStore(store_dir, model_id="poison")
    face = np.zeros((120, 160), dtype=np.float32)
    face[20:40, 60:90] = 1.0  # ~2% cover — fails EMPTY_ALPHA_COVER when served alone
    poison.put(0.0, face)
    assert any(store_dir.glob("*.png"))

    sess = EditorSession()
    assert sess.mode is EngineMode.GYORS
    st = sess.open_media(clip)
    assert st["mode"] == "max"
    assert st.get("full_person_matte") is True
    assert st.get("sharp_edges") is not False
    # Disk scraps gone after open
    assert not any(store_dir.glob("*.png"))

    frame = sess.preview(0.0)
    empty = bool((frame.meta or {}).get("matte_empty") or (frame.meta or {}).get("source_fallback"))
    assert not empty, f"preview still empty: {frame.meta}"
    assert frame.jpeg_b64
    # Live polish path also non-empty
    from hybrid_editor.media.video_io import read_frame_at

    bgr, _ = read_frame_at(clip, 0.0)
    alpha = sess._matte_bgr(bgr, warmup=True)  # noqa: SLF001
    assert not is_matte_empty(alpha)
    assert float((alpha > 0.35).mean()) > 0.02


def test_max_polish_nonempty_person_fixture():
    from hybrid_editor.engines.max_quality import MaxQualityEngine
    from hybrid_editor.media.video_io import is_matte_empty

    eng = MaxQualityEngine()
    alpha = eng._polish(_synthetic_person_bgr(), warmup=True)  # noqa: SLF001
    assert not is_matte_empty(alpha)
    assert float((alpha > 0.35).mean()) > 0.02


def test_delete_key_still_wired():
    app = APP.read_text(encoding="utf-8")
    assert "isTypingTarget" in app
    assert "Delete" in app and "Backspace" in app
