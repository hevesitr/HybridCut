"""simple-bg (`2026-10-12-simple-bg5`) — one V1 clip + BG remove only."""

from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
SYNC = ROOT / "SYNC_VERSION.txt"
FEATURE = BACKEND / "hybrid_editor" / "FEATURE_SIMPLE_BG.txt"
SESSION = BACKEND / "hybrid_editor" / "session.py"
APP = ROOT / "frontend" / "src" / "App.tsx"
TL = ROOT / "frontend" / "src" / "components" / "TimelineTrack.tsx"
CSS = ROOT / "frontend" / "src" / "styles" / "app.css"
RESTART = ROOT / "docs" / "simple-bg-restart.md"
README = ROOT / "README.md"
STAMP = "2026-10-12-simple-bg5"


def _synthetic_person_bgr(h: int = 160, w: int = 120) -> np.ndarray:
    bgr = np.zeros((h, w, 3), np.uint8)
    bgr[:] = (90, 70, 40)
    cv2.rectangle(bgr, (w // 2 - 22, h // 2 - 5), (w // 2 + 22, h - 12), (40, 55, 160), -1)
    cv2.ellipse(bgr, (w // 2, h // 2 - 28), (18, 22), 0, 0, 360, (90, 140, 210), -1)
    noise = np.random.default_rng(2).integers(0, 18, size=bgr.shape, dtype=np.uint8)
    return cv2.add(bgr, noise)


def _write_person_clip(path: Path, n: int = 8) -> None:
    w, h = 160, 120
    writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"mp4v"), 10, (w, h))
    assert writer.isOpened()
    for i in range(n):
        frame = _synthetic_person_bgr(h, w)
        shift = i * 2
        M = np.float32([[1, 0, shift], [0, 1, 0]])
        frame = cv2.warpAffine(frame, M, (w, h), borderMode=cv2.BORDER_REPLICATE)
        writer.write(frame)
    writer.release()


def test_stamp_docs_and_ui():
    assert SYNC.read_text(encoding="utf-8").strip() == STAMP
    assert FEATURE.read_text(encoding="utf-8").strip() == STAMP
    assert RESTART.is_file()
    restart = RESTART.read_text(encoding="utf-8")
    assert STAMP in restart
    assert "háttéreltávolítás" in restart.lower() or "Háttéreltávolítás" in restart
    assert "AI sáv" in restart  # documented as removed
    assert "one V1" in restart or "Egy klip" in restart or "One timeline" in restart
    readme = README.read_text(encoding="utf-8")
    assert STAMP in readme
    css = CSS.read_text(encoding="utf-8")
    assert "simple-bg" in css
    assert STAMP in css
    app = APP.read_text(encoding="utf-8")
    assert "Varázsceruza" not in app
    assert "+ V1 klip" not in app
    assert "+ B-roll" not in app
    assert "→ B-roll" not in app
    assert "Mozgatás" not in app
    assert "ensureMaxWhenCudaUnusable" not in app
    assert "Második videó elutasítva" in app or "elutasítva" in app
    tl = TL.read_text(encoding="utf-8")
    assert "renderLane(v2" not in tl
    assert "AI sáv" not in tl  # lane label removed from UI
    assert "tl-polish-btn" not in tl
    sess = SESSION.read_text(encoding="utf-8")
    assert "_ensure_full_person_gyors" in sess
    assert "one V1 clip only" in sess
    assert STAMP in sess


def test_open_stays_gyors_single_clip(tmp_path: Path):
    from hybrid_editor.engines import EngineMode
    from hybrid_editor.session import EditorSession

    clip_a = tmp_path / "a.mp4"
    clip_b = tmp_path / "b.mp4"
    _write_person_clip(clip_a)
    _write_person_clip(clip_b)

    sess = EditorSession()
    assert sess.mode is EngineMode.GYORS
    st = sess.open_media(clip_a)
    assert st["mode"] == "gyors"
    assert st.get("full_person_matte") is True
    assert (st.get("intelligence") or {}).get("simple_bg") is True
    assert (st.get("intelligence") or {}).get("broll_track") is False
    clips = (st.get("timeline") or {}).get("clips") or []
    assert len(clips) == 1
    assert int(clips[0].get("track", 0)) == 0

    # append / broll flags ignored — still one V1 (replace)
    st2 = sess.open_media(clip_b, append=True, as_broll=True)
    assert st2["mode"] == "gyors"
    clips2 = (st2.get("timeline") or {}).get("clips") or []
    assert len(clips2) == 1
    assert clips2[0]["media_path"].endswith("b.mp4") or "b.mp4" in clips2[0]["media_path"]


def test_preview_not_gray_slab_when_heuristic_ok(tmp_path: Path):
    """Without ORT weights CI uses heuristic — must not claim gray-slab success wrongly."""
    from hybrid_editor.media.video_io import is_matte_degenerate, is_matte_empty
    from hybrid_editor.session import EditorSession

    clip = tmp_path / "person.mp4"
    _write_person_clip(clip)
    sess = EditorSession()
    sess.open_media(clip)
    frame = sess.preview(0.0)
    assert frame.jpeg_b64
    meta = frame.meta or {}
    # If matte present and non-empty, must not be degenerate slab
    if not meta.get("matte_empty") and not meta.get("source_fallback"):
        from hybrid_editor.media.video_io import read_frame_at

        bgr, _ = read_frame_at(clip, 0.0)
        alpha = sess._matte_bgr(bgr, warmup=True)  # noqa: SLF001
        assert not is_matte_degenerate(alpha)
        assert not is_matte_empty(alpha)
    # Sticky gray toast recovery flag when good
    if meta.get("matte_recovered"):
        assert not meta.get("matte_error")


def test_wand_still_absent():
    assert "Varázsceruza" not in APP.read_text(encoding="utf-8")
    assert not (ROOT / "frontend" / "src" / "components" / "SeedPaint.tsx").is_file()
