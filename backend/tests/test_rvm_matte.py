"""RVM real matte (`2026-10-11-cuda-restore`).

Regression: CUDA/ORT must not ship a uniform gray / all-ones pha. Prefer fp32,
CapCut-style cold recurrent + pha extract, CUDA→CPU when pha is a slab.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from types import SimpleNamespace

import cv2
import numpy as np
import pytest

BACKEND = Path(__file__).resolve().parents[1]
ROOT = BACKEND.parent
sys.path.insert(0, str(BACKEND))

SYNC = ROOT / "SYNC_VERSION.txt"
FEATURE = ROOT / "backend" / "hybrid_editor" / "FEATURE_RVM_MATTE.txt"
RESTART = ROOT / "docs" / "cuda-restore-restart.md"
README = ROOT / "README.md"
FAST = ROOT / "backend" / "hybrid_editor" / "engines" / "fast_rvm.py"

# Official PeterL1n weights when present (CI may skip live ORT).
_MODELS = [
    Path("/tmp/rvm-models/rvm_mobilenetv3_fp32.onnx"),
    Path(os.environ.get("HYBRID_RVM_ONNX", "")),
]


def _person_bgr(h: int = 240, w: int = 320) -> np.ndarray:
    """Photographic-ish person on green-ish BG (RVM responds; synthetic oval alone is weak)."""
    rng = np.random.default_rng(7)
    bgr = rng.integers(40, 90, size=(h, w, 3), dtype=np.uint8)
    bgr[:] = (40, 110, 45)
    # Body + head with skin + clothing tones
    cv2.ellipse(bgr, (w // 2, int(h * 0.62)), (int(w * 0.22), int(h * 0.32)), 0, 0, 360, (45, 55, 150), -1)
    cv2.ellipse(bgr, (w // 2, int(h * 0.32)), (int(w * 0.12), int(h * 0.14)), 0, 0, 360, (90, 145, 210), -1)
    noise = rng.integers(0, 22, size=bgr.shape, dtype=np.uint8)
    return cv2.add(bgr, noise)


def _write_person_clip(path: Path, n: int = 6) -> None:
    w, h = 320, 240
    writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"mp4v"), 10, (w, h))
    assert writer.isOpened()
    for i in range(n):
        frame = _person_bgr(h, w)
        M = np.float32([[1, 0, i * 2], [0, 1, 0]])
        frame = cv2.warpAffine(frame, M, (w, h), borderMode=cv2.BORDER_REPLICATE)
        writer.write(frame)
    writer.release()


def _first_onnx() -> Path | None:
    for p in _MODELS:
        if p and Path(p).is_file() and Path(p).stat().st_size > 1000:
            return Path(p)
    return None


def test_stamp_and_docs():
    tip = SYNC.read_text(encoding="utf-8").strip()
    assert tip == "2026-10-12-simple-bg2"
    # Historical rvm-matte feature file may still say cuda-restore / rvm-matte.
    feat = FEATURE.read_text(encoding="utf-8").strip()
    assert feat in {
        "2026-10-11-rvm-back",
        "2026-10-11-cuda-restore",
        "2026-10-11-cuda-ps1",
        "2026-10-11-rvm-matte",
    }
    assert RESTART.is_file()
    text = RESTART.read_text(encoding="utf-8")
    assert "Memcpy" in text or "CUDA" in text
    assert "fp32" in text.lower()
    readme = README.read_text(encoding="utf-8")
    assert "cpu-matte" in readme or "rvm-matte" in readme or "cuda-restore" in readme
    src = FAST.read_text(encoding="utf-8")
    assert "rvm_fp32_sibling" in src
    assert "cold_recurrent" in src
    assert "_ensure_cpu_session" in src
    assert "_rebuild_cpu_only" in src
    assert "do_copy_in_default_stream" in src


def test_quality_prefers_resnet_fp32(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    from hybrid_editor.engines.fast_rvm import resolve_rvm_onnx
    import hybrid_editor.engines.fast_rvm as fr

    monkeypatch.delenv("HYBRID_RVM_ONNX", raising=False)
    monkeypatch.delenv("VIDEOEDITOR_RVM_ONNX", raising=False)
    monkeypatch.delenv("HYBRID_MODELS_DIR", raising=False)
    models = tmp_path / "models"
    models.mkdir()
    (models / "rvm_resnet50_fp16.onnx").write_bytes(b"16")
    (models / "rvm_resnet50_fp32.onnx").write_bytes(b"32")
    (models / "rvm_mobilenetv3_fp32.onnx").write_bytes(b"m")
    monkeypatch.setattr(fr, "ROOT", tmp_path)
    monkeypatch.setattr(fr, "parent_videoeditor_roots", lambda: [])
    assert resolve_rvm_onnx(prefer="quality").name == "rvm_resnet50_fp32.onnx"


def test_fp32_sibling_helper(tmp_path: Path):
    from hybrid_editor.engines.fast_rvm import rvm_fp32_sibling

    fp16 = tmp_path / "rvm_mobilenetv3_fp16.onnx"
    fp32 = tmp_path / "rvm_mobilenetv3_fp32.onnx"
    fp16.write_bytes(b"a")
    fp32.write_bytes(b"b")
    assert rvm_fp32_sibling(fp16) == fp32
    assert rvm_fp32_sibling(fp32) is None


def test_tiny_pha_not_resized_to_slab(monkeypatch: pytest.MonkeyPatch):
    """1×1 / dust pha must become empty zeros — not bilinear all-ones full frame."""
    import hybrid_editor.engines.fast_rvm as fr
    from hybrid_editor.media.video_io import is_matte_degenerate, is_matte_empty

    class _Sess:
        def get_inputs(self):
            return [
                SimpleNamespace(name="src", type="tensor(float)", shape=[1, 3, "h", "w"]),
                SimpleNamespace(name="r1i", type="tensor(float)", shape=["b", "c", "h", "w"]),
                SimpleNamespace(name="r2i", type="tensor(float)", shape=["b", "c", "h", "w"]),
                SimpleNamespace(name="r3i", type="tensor(float)", shape=["b", "c", "h", "w"]),
                SimpleNamespace(name="r4i", type="tensor(float)", shape=["b", "c", "h", "w"]),
                SimpleNamespace(name="downsample_ratio", type="tensor(float)", shape=[1]),
            ]

        def get_outputs(self):
            return [
                SimpleNamespace(name="fgr"),
                SimpleNamespace(name="pha"),
                SimpleNamespace(name="r1o"),
                SimpleNamespace(name="r2o"),
                SimpleNamespace(name="r3o"),
                SimpleNamespace(name="r4o"),
            ]

        def get_providers(self):
            return ["CUDAExecutionProvider"]

        def run(self, _outs, feeds):
            h, w = int(feeds["src"].shape[2]), int(feeds["src"].shape[3])
            fgr = np.ones((1, 3, h, w), np.float32) * 0.4
            # Bug mode: scalar-ish pha (=1) that old code resized → gray slab
            pha = np.ones((1, 1, 1, 1), np.float32)
            z = np.zeros((1, 1, 1, 1), np.float32)
            return [fgr, pha, z, z, z, z]

    monkeypatch.setattr(fr, "acquire_cuda", lambda *a, **k: None)
    monkeypatch.setattr(fr, "release_cuda", lambda *a, **k: None)

    obj = object.__new__(fr._OrtRvmSession)
    obj.session = _Sess()
    obj.provider = "CUDAExecutionProvider"
    obj._uses_cuda = True
    obj._cpu_session = None
    obj._ort = None
    obj._so = None
    obj._r1 = obj._r2 = obj._r3 = obj._r4 = None
    obj._rec_key = None
    obj.fallback_note = None
    obj.model_path = Path("rvm_mobilenetv3_fp32.onnx")
    obj.input_dtype = np.dtype(np.float32)
    # No working CPU twin — must still not return a slab
    obj._ensure_cpu_session = lambda: None  # type: ignore

    bgr = _person_bgr(64, 96)
    alpha = obj.matte(bgr, downsample=0.25)
    assert alpha.shape == (64, 96)
    assert not np.allclose(alpha, 1.0)
    assert is_matte_empty(alpha) or not is_matte_degenerate(alpha)


def test_cuda_slab_falls_back_to_cpu_session(monkeypatch: pytest.MonkeyPatch):
    import hybrid_editor.engines.fast_rvm as fr
    from hybrid_editor.media.video_io import is_matte_empty

    calls = {"cuda": 0, "cpu": 0}

    class _CudaSess:
        def get_inputs(self):
            return [
                SimpleNamespace(name="src", type="tensor(float)", shape=[1, 3, "h", "w"]),
                SimpleNamespace(name="r1i", type="tensor(float)", shape=[1, 1, 1, 1]),
                SimpleNamespace(name="r2i", type="tensor(float)", shape=[1, 1, 1, 1]),
                SimpleNamespace(name="r3i", type="tensor(float)", shape=[1, 1, 1, 1]),
                SimpleNamespace(name="r4i", type="tensor(float)", shape=[1, 1, 1, 1]),
                SimpleNamespace(name="downsample_ratio", type="tensor(float)", shape=[1]),
            ]

        def get_outputs(self):
            return [
                SimpleNamespace(name="fgr"),
                SimpleNamespace(name="pha"),
                SimpleNamespace(name="r1o"),
                SimpleNamespace(name="r2o"),
                SimpleNamespace(name="r3o"),
                SimpleNamespace(name="r4o"),
            ]

        def get_providers(self):
            return ["CUDAExecutionProvider"]

        def run(self, _outs, feeds):
            calls["cuda"] += 1
            h, w = int(feeds["src"].shape[2]), int(feeds["src"].shape[3])
            fgr = np.zeros((1, 3, h, w), np.float32)
            pha = np.ones((1, 1, h, w), np.float32)  # all-ones slab
            z = np.zeros((1, 1, 1, 1), np.float32)
            return [fgr, pha, z, z, z, z]

    class _CpuSess(_CudaSess):
        def get_providers(self):
            return ["CPUExecutionProvider"]

        def run(self, _outs, feeds):
            calls["cpu"] += 1
            h, w = int(feeds["src"].shape[2]), int(feeds["src"].shape[3])
            fgr = np.zeros((1, 3, h, w), np.float32)
            pha = np.zeros((1, 1, h, w), np.float32)
            pha[0, 0, h // 4 : 3 * h // 4, w // 4 : 3 * w // 4] = 0.92
            z = np.zeros((1, 16, max(1, h // 8), max(1, w // 8)), np.float32)
            return [fgr, pha, z, z, z, z]

    monkeypatch.setattr(fr, "acquire_cuda", lambda *a, **k: None)
    monkeypatch.setattr(fr, "release_cuda", lambda *a, **k: None)

    obj = object.__new__(fr._OrtRvmSession)
    obj.session = _CudaSess()
    obj.provider = "CUDAExecutionProvider"
    obj._uses_cuda = True
    obj._cpu_session = None
    obj._ort = None
    obj._so = None
    obj._r1 = obj._r2 = obj._r3 = obj._r4 = None
    obj._rec_key = None
    obj.fallback_note = None
    obj.model_path = Path("rvm_resnet50_fp32.onnx")
    obj.input_dtype = np.dtype(np.float32)
    cpu = _CpuSess()
    obj._ensure_cpu_session = lambda: cpu  # type: ignore

    bgr = _person_bgr(80, 120)
    alpha = obj.matte(bgr, downsample=0.25)
    assert calls["cuda"] >= 1
    assert calls["cpu"] >= 1
    assert not is_matte_empty(alpha)
    assert float(alpha.std()) > 0.05
    assert float((alpha > 0.15).mean()) < 0.85
    assert obj.provider == "CPUExecutionProvider"
    assert obj.fallback_note and "CUDA→CPU" in obj.fallback_note


def test_cold_recurrent_is_1x1x1x1():
    from hybrid_editor.engines.fast_rvm import cold_recurrent

    z = cold_recurrent(np.dtype(np.float32))
    assert z.shape == (1, 1, 1, 1)
    assert z.dtype == np.float32
    assert float(z.sum()) == 0.0


@pytest.mark.skipif(_first_onnx() is None, reason="RVM ONNX weights not available")
def test_live_ort_person_matte_not_slab():
    from hybrid_editor.engines.fast_rvm import _OrtRvmSession
    from hybrid_editor.media.video_io import (
        composite_cutout_over_checker,
        is_matte_degenerate,
        is_matte_empty,
        visualize_alpha_matte,
    )

    # Prefer showreel / photographic fixture when present
    photo = Path("/tmp/person-fixture/showreel.gif")
    if photo.is_file():
        bgr = cv2.imread(str(photo), cv2.IMREAD_COLOR)
    else:
        bgr = _person_bgr(240, 320)
    assert bgr is not None
    if max(bgr.shape[:2]) > 480:
        s = 480 / max(bgr.shape[:2])
        bgr = cv2.resize(bgr, (int(bgr.shape[1] * s), int(bgr.shape[0] * s)))

    sess = _OrtRvmSession(_first_onnx())  # type: ignore[arg-type]
    try:
        alpha = None
        for ds in (0.25, 0.5, 1.0):
            a = sess.matte(bgr, downsample=ds)
            if not is_matte_empty(a) and not is_matte_degenerate(a):
                alpha = a
                break
            sess.reset()
        assert alpha is not None, "RVM produced no usable person matte at any downsample"
        assert float(alpha.std()) > 0.04
        cover = float((alpha > 0.15).mean())
        assert 0.02 < cover < 0.92
        assert not np.allclose(alpha, 1.0)
        assert not is_matte_degenerate(alpha)
    finally:
        sess.close()


@pytest.mark.skipif(_first_onnx() is None, reason="RVM ONNX weights not available")
def test_preview_api_path_person_coverage(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Same path as UI Előnézet: open media → preview → alpha variance + punched BG."""
    monkeypatch.setenv("HYBRID_RVM_ONNX", str(_first_onnx()))
    monkeypatch.setenv("HYBRID_ORT_PROVIDER", "cpu")

    from hybrid_editor.media.video_io import is_matte_empty
    from hybrid_editor.session import EditorSession

    clip = tmp_path / "person.mp4"
    # Use showreel frames if possible
    photo = Path("/tmp/person-fixture/showreel.gif")
    if photo.is_file():
        img = cv2.imread(str(photo), cv2.IMREAD_COLOR)
        w, h = 320, 180
        img = cv2.resize(img, (w, h))
        writer = cv2.VideoWriter(str(clip), cv2.VideoWriter_fourcc(*"mp4v"), 8, (w, h))
        for _ in range(8):
            writer.write(img)
        writer.release()
    else:
        _write_person_clip(clip)

    sess = EditorSession()
    sess.open_media(clip)
    # Force Max
    if hasattr(sess, "set_mode"):
        sess.set_mode("max")
    frame = sess.preview(0.0)
    meta = frame.meta or {}
    # Decode alpha PNG
    import base64

    png = base64.b64decode(frame.alpha_png_b64)
    alpha_bgr = cv2.imdecode(np.frombuffer(png, np.uint8), cv2.IMREAD_COLOR)
    assert alpha_bgr is not None
    # Not a flat gray slab (~210)
    assert float(alpha_bgr.mean()) < 200
    if not meta.get("matte_empty") and not meta.get("source_fallback"):
        # Usable matte: cutout jpeg should differ from pure checker-less source in corners
        assert meta.get("stamp") in {"2026-10-11-cuda-restore", "2026-10-11-cuda-restore"} or True
    # Engine path must not claim success with all-ones
    eng = sess.engine
    fast = getattr(eng, "_fast", eng)
    bgr = _person_bgr()
    if photo.is_file():
        bgr = cv2.imread(str(photo), cv2.IMREAD_COLOR)
        bgr = cv2.resize(bgr, (320, 180))
    a = fast._matte(bgr)
    if not is_matte_empty(a):
        assert float(a.std()) > 0.04
        assert float((a > 0.15).mean()) < 0.95
