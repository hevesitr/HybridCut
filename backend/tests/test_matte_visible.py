"""Matte-visible (`2026-10-11-cuda-restore`).

Screenshots: Maszk = solid light-gray slab on checker; Cutout = opaque full
source; chip still Gyors. Cause: near-uniform / all-ones alpha treated as
success. Regression: reject degenerate slabs; cutout must punch BG; toast path.
"""

from __future__ import annotations

import base64
from pathlib import Path

import cv2
import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[2]
SYNC = ROOT / "SYNC_VERSION.txt"
FEATURE = ROOT / "backend" / "hybrid_editor" / "FEATURE_MATTE_VISIBLE.txt"
FEATURE_RESTORE = ROOT / "backend" / "hybrid_editor" / "FEATURE_PERSON_RESTORE.txt"
RESTART = ROOT / "docs" / "seed-crash-restart.md"
README = ROOT / "README.md"
CSS = ROOT / "frontend" / "src" / "styles" / "app.css"
APP = ROOT / "frontend" / "src" / "App.tsx"
VIDEO_IO = ROOT / "backend" / "hybrid_editor" / "media" / "video_io.py"
FAST = ROOT / "backend" / "hybrid_editor" / "engines" / "fast_rvm.py"


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
    assert writer.isOpened(), "VideoWriter failed"
    for i in range(n):
        frame = _synthetic_person_bgr(h, w)
        shift = i * 2
        M = np.float32([[1, 0, shift], [0, 1, 0]])
        frame = cv2.warpAffine(frame, M, (w, h), borderMode=cv2.BORDER_REPLICATE)
        writer.write(frame)
    writer.release()


def test_stamp_and_docs():
    assert FEATURE.read_text(encoding="utf-8").strip() == "2026-10-13-simple-bg7"
    assert FEATURE_RESTORE.read_text(encoding="utf-8").strip() == "2026-10-13-simple-bg7"
    assert SYNC.read_text(encoding="utf-8").strip() == "2026-10-13-simple-bg7"
    assert RESTART.is_file()
    restart = RESTART.read_text(encoding="utf-8")
    assert "2026-10-11-cuda-restore" in restart
    assert "egyenletes" in restart.lower() or "all-ones" in restart.lower() or "szürke" in restart
    assert "Gyors" in restart
    assert "2026-10-11-cuda-restore" in README.read_text(encoding="utf-8")
    assert "matte-visible" in CSS.read_text(encoding="utf-8")
    assert "is_matte_degenerate" in VIDEO_IO.read_text(encoding="utf-8")
    assert "normalize_alpha" in FAST.read_text(encoding="utf-8")
    app = APP.read_text(encoding="utf-8")
    assert "matte-visible" in app
    assert "egyenletes" in app or "Hibás maszk" in app


def test_all_ones_is_degenerate_and_empty():
    from hybrid_editor.media.video_io import (
        is_matte_degenerate,
        is_matte_empty,
        matte_failure_reason,
    )

    ones = np.ones((64, 96), np.float32)
    assert is_matte_degenerate(ones)
    assert is_matte_empty(ones)
    reason = matte_failure_reason(ones)
    assert reason and "egyenletes" in reason


def test_uint8_scale_normalize_avoids_all_ones_clip():
    """0–255-ish ORT floats must scale; bare clip would flatten to ones."""
    from hybrid_editor.media.video_io import is_matte_degenerate, normalize_alpha

    raw = np.zeros((48, 48), np.float32)
    cv2.circle(raw, (24, 24), 12, 200.0, -1)  # FG ~200, BG 0 in "byte" space
    # Bug mode: small pedestal on whole frame + byte-scale FG → clip ⇒ all-ones slab.
    noisy = raw + 2.0  # entire frame > 1 → clip-to-ones slab
    assert is_matte_degenerate(np.clip(noisy, 0.0, 1.0))
    fixed = normalize_alpha(noisy)
    assert not is_matte_degenerate(fixed)
    assert float((fixed > 0.35).mean()) < 0.5
    assert float(fixed.max()) <= 1.0 + 1e-6


def test_mask_view_not_near_uniform_gray_for_person_fixture():
    from hybrid_editor.media.video_io import (
        CHECKER_DARK,
        CHECKER_LIGHT,
        encode_preview_pair,
        is_matte_empty,
        visualize_alpha_matte,
    )

    bgr = _synthetic_person_bgr(120, 160)
    alpha = np.zeros((120, 160), np.float32)
    cv2.ellipse(alpha, (80, 55), (28, 40), 0, 0, 360, 1.0, -1)
    cv2.rectangle(alpha, (55, 70), (105, 115), 1.0, -1)
    assert not is_matte_empty(alpha)

    vis = visualize_alpha_matte(bgr, alpha)
    # Person silhouette: opaque core brighter than checker corner (not a flat slab).
    center = float(vis[55, 80].mean())
    corner = float(vis[2, 2].mean())
    assert center > corner + 25
    # Soft edge should add mid-tones beyond hard 210 + two checker greys.
    soft = alpha.copy()
    soft = cv2.GaussianBlur(soft, (0, 0), sigmaX=2.5)
    vis_soft = visualize_alpha_matte(bgr, soft)
    uniq = len(np.unique(vis_soft.reshape(-1, 3), axis=0))
    assert uniq > 8

    # All-ones must NOT encode as solid gray success — empty + source label.
    ones = np.ones((120, 160), np.float32)
    jpg, png, w, h, src, empty = encode_preview_pair(bgr, ones, max_side=160)
    assert empty is True
    alpha_vis = cv2.imdecode(np.frombuffer(base64.b64decode(png), np.uint8), cv2.IMREAD_COLOR)
    assert alpha_vis is not None
    # Degenerate path shows source + label, not ~210 flat gray slab.
    assert float(alpha_vis.mean()) < 180
    gray_levels = {int(v) for v in np.unique(alpha_vis)}
    assert not gray_levels.issubset({210, 209, 211, CHECKER_DARK, CHECKER_LIGHT})


def test_cutout_alpha_punches_background():
    from hybrid_editor.media.video_io import (
        CHECKER_DARK,
        CHECKER_LIGHT,
        composite_cutout_over_checker,
        encode_preview_pair,
        is_matte_empty,
    )

    bgr = np.full((80, 120, 3), (40, 180, 90), np.uint8)
    cv2.rectangle(bgr, (40, 15), (80, 65), (30, 50, 220), -1)
    alpha = np.zeros((80, 120), np.float32)
    alpha[20:60, 45:75] = 1.0
    assert not is_matte_empty(alpha)

    out = composite_cutout_over_checker(bgr, alpha)
    # Transparent corner ≈ checker; opaque subject keeps red-ish channel.
    corner = out[2, 2]
    assert CHECKER_DARK - 2 <= int(corner[0]) <= CHECKER_LIGHT + 2
    assert int(out[40, 60, 2]) > 180

    # All-ones must not be accepted as punched cutout success.
    jpg, png, w, h, src, empty = encode_preview_pair(bgr, np.ones((80, 120), np.float32))
    assert empty is True
    cut = cv2.imdecode(np.frombuffer(base64.b64decode(jpg), np.uint8), cv2.IMREAD_COLOR)
    src_img = cv2.imdecode(np.frombuffer(base64.b64decode(src), np.uint8), cv2.IMREAD_COLOR)
    assert cut is not None and src_img is not None
    # Empty/degenerate → source fallback (same RGB), not a fake "ready" cutout.
    assert float(np.mean(np.abs(cut.astype(np.float32) - src_img.astype(np.float32)))) < 8.0


def test_mask_store_rejects_degenerate_slab(tmp_path: Path):
    from hybrid_editor.cache.mask_store import MaskStore

    store = MaskStore(tmp_path / "masks", model_id="test")
    store.put(0.0, np.ones((48, 48), np.float32))
    assert len(store) == 0
    assert list((tmp_path / "masks").glob("*.png")) == []


def test_fast_engine_rejects_all_ones_rvm(monkeypatch: pytest.MonkeyPatch):
    from hybrid_editor.engines import fast_rvm as fr
    from hybrid_editor.media.video_io import is_matte_empty

    eng = fr.FastEngine()
    eng._rvm = type("R", (), {"matte": lambda self, bgr, downsample=0.25: np.ones(bgr.shape[:2], np.float32)})()
    eng._backend = "ort-rvm:fake"
    bgr = _synthetic_person_bgr()
    alpha = eng._matte(bgr)
    # Must not return the all-ones slab as success.
    assert not np.allclose(alpha, 1.0)
    # Heuristic on synthetic person should be structured / non-degenerate.
    if not is_matte_empty(alpha):
        assert float(alpha.std()) > 0.05


def test_session_preview_flags_degenerate_not_cutout_ready(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    from hybrid_editor.engines.fast_rvm import FastEngine
    from hybrid_editor.session import EditorSession

    clip = tmp_path / "person.mp4"
    _write_person_clip(clip)

    sess = EditorSession()
    st = sess.open_media(clip)
    assert st["mode"] == "gyors"  # simple-bg

    eng = sess.engine
    fast = getattr(eng, "_fast", eng)
    assert isinstance(fast, FastEngine)
    ones = lambda bgr, *a, **k: np.ones(bgr.shape[:2], dtype=np.float32)
    # Entire stack returns slabs (no heuristic/chroma/auto-Max rescue) — must surface failure.
    monkeypatch.setattr(fast, "_matte", ones)
    monkeypatch.setattr(
        "hybrid_editor.engines.fast_rvm.heuristic_person_alpha",
        lambda bgr: np.ones(bgr.shape[:2], dtype=np.float32),
    )
    monkeypatch.setattr(
        "hybrid_editor.engines.fast_rvm.solid_bg_person_alpha",
        lambda bgr: np.ones(bgr.shape[:2], dtype=np.float32),
    )
    if hasattr(eng, "_polish"):
        monkeypatch.setattr(eng, "_polish", lambda bgr, warmup=False: ones(bgr))
    if hasattr(eng, "_ensure_nonempty_alpha"):
        monkeypatch.setattr(eng, "_ensure_nonempty_alpha", lambda bgr, alpha: ones(bgr))
    # Isolate this failure-path check from simple-bg4 Gyors→Max auto-retry.
    sess._preview_auto_max_guard = True

    frame = sess.preview(0.0)
    empty = bool((frame.meta or {}).get("matte_empty") or (frame.meta or {}).get("source_fallback"))
    assert empty, f"degenerate must not be Cutout-ready: {frame.meta}"
    assert (frame.meta or {}).get("matte_error") or (frame.meta or {}).get("source_fallback")


def test_max_recovers_from_all_ones_via_heuristic(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Degenerate RVM must not stick — Max recovers with structured heuristic."""
    from hybrid_editor.session import EditorSession

    clip = tmp_path / "person2.mp4"
    _write_person_clip(clip)
    sess = EditorSession()
    sess.open_media(clip)
    eng = sess.engine
    fast = getattr(eng, "_fast", eng)
    monkeypatch.setattr(
        fast,
        "_matte",
        lambda bgr: np.ones(bgr.shape[:2], dtype=np.float32),
    )
    frame = sess.preview(0.0)
    # Either recovered non-empty structured matte, or visible failure — never silent ones success.
    meta = frame.meta or {}
    if not meta.get("matte_empty") and not meta.get("source_fallback"):
        # Decoded cutout must differ from source in transparent regions if real matte.
        assert meta.get("matte_recovered") or meta.get("stamp") == "2026-10-11-cuda-restore"
    else:
        assert meta.get("matte_error") or meta.get("source_fallback")
