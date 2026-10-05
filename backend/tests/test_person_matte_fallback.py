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
    assert prev.meta.get("matte_empty") is False
    assert "RVM" in (prev.meta.get("person_matte_label_hu") or "")
    # Decode alpha from a direct polish for a hard assert
    eng = session.engine
    assert isinstance(eng, MaxQualityEngine)
    bgr = _synthetic_person_bgr()
    a = eng._polish(bgr, warmup=True)
    assert not is_matte_empty(a)
    assert float(a.mean()) >= 0.05
    assert float((a > 0.15).mean()) >= 0.08


def test_max_empty_rvm_still_yields_person_via_heuristic():
    """Regression: Max polish used to call _matte without heuristic retry → empty mask."""
    from hybrid_editor.engines.fast_rvm import FastEngine

    eng = MaxQualityEngine()

    class _EmptyRvm:
        model_path = Path("empty.onnx")
        provider = "CPU"

        def matte(self, bgr, downsample=0.25):  # noqa: ANN001
            return np.zeros(bgr.shape[:2], np.float32)

        def reset(self) -> None:
            return None

        def close(self) -> None:
            return None

    eng._fast._rvm = _EmptyRvm()  # type: ignore[assignment]
    eng._fast._backend = "ort-rvm:CPU"
    bgr = _synthetic_person_bgr()
    base = eng._base_alpha(bgr)
    assert not is_matte_empty(base), "base alpha must heuristic-recover from empty ORT"
    polished = eng._polish(bgr, warmup=True)
    assert not is_matte_empty(polished)
    assert float(polished.mean()) >= 0.04
    assert float((polished > 0.15).mean()) >= 0.06
    # FastEngine._matte itself must also recover (Max + Gyors share this path).
    fe = FastEngine(prefer_quality=True)
    fe._rvm = _EmptyRvm()  # type: ignore[assignment]
    fe._backend = "ort-rvm:CPU"
    assert not is_matte_empty(fe._matte(bgr))


def test_max_mode_switch_clears_near_empty_seed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("HYBRID_MATANYONE2_WEIGHTS", raising=False)
    sample = tmp_path / "person.mp4"
    _write_person_clip(sample, n=4)
    session = EditorSession()
    session.open_media(sample)
    tiny = np.zeros((120, 160), np.float32)
    tiny[10:12, 10:12] = 1.0
    session._seed_alpha = tiny
    st = session.set_mode("max")
    assert session._seed_alpha is None
    assert st.get("auto_preview_recommended") is True
    prev = session.preview(0.0)
    assert prev.meta.get("matte_empty") is False
    assert "RVM" in (prev.meta.get("person_matte_label_hu") or "")


class _PersonOrtSession:
    """Stand-in for _OrtRvmSession when a real ONNX file exists but is not loadable."""

    def __init__(self, model_path: Path) -> None:
        self.model_path = Path(model_path)
        self.provider = "CPUExecutionProvider"
        self.fallback_note = None

    def matte(self, bgr, downsample=0.25):  # noqa: ANN001
        h, w = bgr.shape[:2]
        a = np.zeros((h, w), np.float32)
        cv2.ellipse(a, (w // 2, h // 2), (max(12, w // 5), max(18, h // 3)), 0, 0, 360, 0.94, -1)
        return a

    def reset(self) -> None:
        return None

    def close(self) -> None:
        return None


def test_max_session_nonempty_when_rvm_onnx_present(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Cloud has no real RVM weights; still prove ORT path + Max session with ONNX present."""
    monkeypatch.delenv("HYBRID_MATANYONE2_WEIGHTS", raising=False)
    onnx = tmp_path / "rvm_resnet50_fp32.onnx"
    onnx.write_bytes(b"fake-onnx")
    monkeypatch.setenv("HYBRID_RVM_ONNX", str(onnx))

    import hybrid_editor.engines.fast_rvm as fr

    monkeypatch.setattr(fr, "_OrtRvmSession", _PersonOrtSession)

    sample = tmp_path / "person.mp4"
    _write_person_clip(sample, n=5)
    session = EditorSession()
    st = session.set_mode("max")
    assert st.get("matanyone2_active") is False
    session.open_media(sample)
    eng = session.engine
    assert isinstance(eng, MaxQualityEngine)
    assert eng._fast._rvm is not None
    assert Path(eng._fast._rvm.model_path).name == "rvm_resnet50_fp32.onnx"
    assert "ort-rvm" in eng._fast.capabilities().backend
    prev = session.preview(0.1)
    assert prev.engine == "MaxQualityEngine"
    assert prev.meta.get("matte_empty") is False
    assert prev.meta.get("source_fallback") is not True
    assert "RVM" in (prev.meta.get("person_matte_label_hu") or "")
    assert float((eng._base_alpha(_synthetic_person_bgr()) > 0.15).mean()) >= 0.08


def test_max_onnx_present_empty_ort_still_recovers(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """ONNX file found but ORT returns zeros — Max must still ship a person matte."""
    monkeypatch.delenv("HYBRID_MATANYONE2_WEIGHTS", raising=False)
    onnx = tmp_path / "rvm_mobilenetv3_fp32.onnx"
    onnx.write_bytes(b"fake-onnx")
    monkeypatch.setenv("HYBRID_RVM_ONNX", str(onnx))

    class _ZeroOrt(_PersonOrtSession):
        def matte(self, bgr, downsample=0.25):  # noqa: ANN001
            return np.zeros(bgr.shape[:2], np.float32)

    import hybrid_editor.engines.fast_rvm as fr

    monkeypatch.setattr(fr, "_OrtRvmSession", _ZeroOrt)

    sample = tmp_path / "person.mp4"
    _write_person_clip(sample, n=4)
    session = EditorSession()
    session.set_mode("max")
    session.open_media(sample)
    prev = session.preview(0.0)
    assert prev.meta.get("matte_empty") is False
    bgr = _synthetic_person_bgr()
    a = session.engine._base_alpha(bgr)  # type: ignore[union-attr]
    assert not is_matte_empty(a)
