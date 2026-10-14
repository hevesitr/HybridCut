"""restore-rvm / oss-fast-matte — Gyors trusts soft RVM pha like PeterL1n/rembg."""

from __future__ import annotations

import sys
from pathlib import Path

import cv2
import numpy as np
import pytest

BACKEND = Path(__file__).resolve().parents[1]
ROOT = BACKEND.parent
sys.path.insert(0, str(BACKEND))

STAMP = "2026-10-14-restore-rvm-fast2"


def test_stamp_and_ascii_paste():
    assert (ROOT / "SYNC_VERSION.txt").read_text(encoding="utf-8").strip() == STAMP
    assert (ROOT / "backend/hybrid_editor/FEATURE_RESTORE_RVM.txt").read_text(
        encoding="utf-8"
    ).strip() == STAMP
    for name in ("PASTE_RESTORE_RVM_GITHUB.ps1", "PASTE_RESTORE_RVM_INSTALL.ps1"):
        p = ROOT / name
        assert p.is_file()
        raw = p.read_bytes()
        assert all(b < 128 for b in raw), name
        assert STAMP in p.read_text(encoding="utf-8")


def test_matte_trusts_soft_mobilenet_without_good_enough(monkeypatch: pytest.MonkeyPatch):
    """Soft peak~0.32 person must be accepted (OSS path) — not laddered away."""
    monkeypatch.setenv("HYBRID_ORT_PROVIDER", "cpu")
    from hybrid_editor.engines.fast_rvm import FastEngine
    from hybrid_editor.media.video_io import is_matte_empty, is_matte_good_enough

    eng = FastEngine(prefer_quality=False)
    h, w = 360, 640
    soft = np.zeros((h, w), np.float32)
    cv2.ellipse(soft, (w // 2, h // 2), (90, 160), 0, 0, 360, 0.32, -1)
    soft = cv2.GaussianBlur(soft, (0, 0), 5)
    assert float(soft.max()) < 0.36
    # May or may not pass good_enough depending on cover — still must be trusted.
    eng._rvm = type("S", (), {"matte": lambda *a, **k: soft, "reset": lambda *a, **k: None})()
    eng._backend = "ort-rvm:CPU"
    eng._try_alternate_rvm = lambda bgr: None  # type: ignore[method-assign]
    bgr = np.zeros((h, w, 3), np.uint8)
    out = eng._matte(bgr)
    assert not is_matte_empty(out)
    assert float(out.max()) > 0.2
    assert abs(float(out.max()) - float(soft.max())) < 0.05


def test_preview_meta_oss_fast(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("HYBRID_ORT_PROVIDER", "cpu")
    from hybrid_editor.session import EditorSession

    rng = np.random.default_rng(9)
    h, w = 360, 640
    bgr = np.clip(
        np.full((h, w, 3), (40, 55, 90), np.int16)
        + rng.integers(-12, 12, (h, w, 3), dtype=np.int16),
        0,
        255,
    ).astype(np.uint8)
    cv2.ellipse(bgr, (w // 2, h // 2 + 20), (70, 150), 0, 0, 360, (50, 70, 160), -1)
    cv2.ellipse(bgr, (w // 2, h // 2 - 90), (40, 48), 0, 0, 360, (100, 150, 210), -1)
    out = tmp_path / "p.mp4"
    vw = cv2.VideoWriter(str(out), cv2.VideoWriter_fourcc(*"mp4v"), 12, (w, h))
    for _ in range(4):
        vw.write(bgr)
    vw.release()

    soft = np.zeros((h, w), np.float32)
    cv2.ellipse(soft, (w // 2, h // 2), (80, 150), 0, 0, 360, 0.30, -1)
    soft = cv2.GaussianBlur(soft, (0, 0), 4)

    sess = EditorSession()
    sess.open_media(out)
    sess._suppress_auto_max = True
    sess.engine._matte = lambda frame: soft[: frame.shape[0], : frame.shape[1]].copy()  # type: ignore[method-assign]
    fr = sess.preview(0.0)
    assert fr.meta.get("stamp") == STAMP
    assert fr.meta.get("oss_fast_matte") is True
    assert fr.meta.get("preview_boost") is False
    assert fr.meta.get("matte_empty") is False
    assert fr.jpeg_b64 and len(fr.jpeg_b64) > 800


def test_cpu_rvm_min_ds_default_no_floor():
    from hybrid_editor.engines.fast_rvm import FastEngine

    eng = FastEngine(prefer_quality=False)
    # Proxy-sized frame: PeterL1n auto ~1.0; no forced 0.5 floor.
    bgr = np.zeros((480, 854, 3), np.uint8)
    ds = eng._downsample_for(bgr)  # noqa: SLF001
    assert ds >= 0.5  # 512/854ish or 1.0 on short proxy
