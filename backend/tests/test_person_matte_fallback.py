"""Max without MatAnyone2 weights → RVM/heuristic person matte must be non-empty."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import cv2
import numpy as np
import pytest

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

from hybrid_editor.engines.factory import create_engine
from hybrid_editor.engines.max_quality import MaxQualityEngine
from hybrid_editor.engines.matanyone2_adapter import probe_matanyone2
from hybrid_editor.media.video_io import is_matte_empty
from hybrid_editor.session import EditorSession


def _synthetic_person_bgr(h: int = 160, w: int = 120) -> np.ndarray:
    """Person-ish figure: warm skin oval + torso on cool background."""
    bgr = np.zeros((h, w, 3), np.uint8)
    bgr[:] = (90, 70, 40)  # cool BG
    # Torso
    cv2.rectangle(bgr, (w // 2 - 22, h // 2 - 5), (w // 2 + 22, h - 12), (40, 55, 160), -1)
    # Head (skin)
    cv2.ellipse(bgr, (w // 2, h // 2 - 28), (18, 22), 0, 0, 360, (90, 140, 210), -1)
    # Soft noise so GrabCut/RVM have texture
    noise = np.random.default_rng(0).integers(0, 18, size=bgr.shape, dtype=np.uint8)
    bgr = cv2.add(bgr, noise)
    return bgr


def _write_person_clip(path: Path, n: int = 6) -> None:
    w, h = 160, 120
    writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"mp4v"), 10, (w, h))
    for i in range(n):
        frame = _synthetic_person_bgr(h, w)
        # Slight motion
        shift = i * 2
        M = np.float32([[1, 0, shift], [0, 1, 0]])
        frame = cv2.warpAffine(frame, M, (w, h), borderMode=cv2.BORDER_REPLICATE)
        writer.write(frame)
    writer.release()


def test_matanyone2_probe_missing_weights_by_default(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("HYBRID_MATANYONE2_WEIGHTS", raising=False)
    st = probe_matanyone2()
    assert st.available is False
    assert "HYBRID_MATANYONE2_WEIGHTS" in st.reason or "not shipped" in st.reason.lower()


def test_max_without_weights_uses_quality_pipeline_label():
    eng = create_engine("max")
    assert isinstance(eng, MaxQualityEngine)
    assert eng.person_matte_info()["matanyone2_active"] is False
    assert "RVM" in eng.person_matte_label()
    assert "MatAnyone2 nincs" in eng.person_matte_label()
    caps = eng.capabilities()
    assert "quality-pipeline" in caps.backend or "matanyone2" in caps.backend
    # Without user weights we must NOT pretend MatAnyone2 is the live matte path.
    if not eng._adapter.available:
        assert caps.backend.startswith("quality-pipeline")


def test_max_polish_nonempty_on_synthetic_person():
    eng = MaxQualityEngine()
    bgr = _synthetic_person_bgr()
    alpha = eng._polish(bgr, warmup=True)
    assert alpha.shape == bgr.shape[:2]
    assert not is_matte_empty(alpha), (
        f"expected person matte, got max={float(alpha.max()):.4f} "
        f"cover={float((alpha > 0.15).mean()):.4f} mean={float(alpha.mean()):.4f}"
    )


def test_small_manual_seed_does_not_wipe_auto_person_matte():
    """Regression: tiny lasso blob used to BG-clamp the whole frame via trimap."""
    eng = MaxQualityEngine()
    bgr = _synthetic_person_bgr()
    auto = eng._base_alpha(bgr)
    assert not is_matte_empty(auto)

    tiny = np.zeros(bgr.shape[:2], np.float32)
    tiny[70:85, 70:85] = 1.0  # small yellow-blob stand-in
    eng.set_user_seed(tiny)
    polished = eng._polish(bgr, warmup=True)
    assert not is_matte_empty(polished)
    # Auto person coverage must largely survive (union seed, not replace).
    auto_cover = float((auto > 0.35).mean())
    polished_cover = float((polished > 0.35).mean())
    assert polished_cover >= min(auto_cover * 0.55, 0.08)


def test_session_max_preview_person_matte(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("HYBRID_MATANYONE2_WEIGHTS", raising=False)
    # Force no ONNX so CI stays deterministic on heuristic path if RVM absent.
    monkeypatch.delenv("HYBRID_RVM_ONNX", raising=False)
    monkeypatch.delenv("VIDEOEDITOR_RVM_ONNX", raising=False)

    sample = tmp_path / "person.mp4"
    _write_person_clip(sample, n=6)

    session = EditorSession()
    st = session.set_mode("max")
    assert st.get("matanyone2_active") is False
    assert "RVM" in (st.get("person_matte_label_hu") or "")

    session.open_media(sample)
    prev = session.preview(0.1)
    assert prev.engine == "MaxQualityEngine"
    assert prev.meta.get("matanyone2_active") is False
    assert "RVM" in (prev.meta.get("person_matte_label_hu") or "")
    # Preview pair may mark empty only if alpha truly useless — synthetic person should pass.
    assert prev.meta.get("matte_empty") is False or prev.alpha_png_b64
    # Decode alpha from a direct polish for a hard assert
    eng = session.engine
    assert isinstance(eng, MaxQualityEngine)
    bgr = _synthetic_person_bgr()
    a = eng._polish(bgr, warmup=True)
    assert not is_matte_empty(a)
