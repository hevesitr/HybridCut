"""FastEngine RVM ORT input dtype: fp16 models must not get float32 feeds."""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

import numpy as np

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

from hybrid_editor.engines.fast_rvm import resolve_rvm_input_dtype  # noqa: E402


class _FakeInput:
    def __init__(self, name: str, typ: str) -> None:
        self.name = name
        self.type = typ


class _FakeSession:
    def __init__(self, src_type: str) -> None:
        self._inputs = [
            _FakeInput("src", src_type),
            _FakeInput("r1i", src_type),
            _FakeInput("downsample_ratio", "tensor(float)"),
        ]

    def get_inputs(self):
        return self._inputs


def test_resolve_dtype_from_ort_float16_meta():
    sess = _FakeSession("tensor(float16)")
    assert resolve_rvm_input_dtype(sess, Path("ignored_fp32.onnx")) == np.dtype(np.float16)


def test_resolve_dtype_from_ort_float32_meta():
    sess = _FakeSession("tensor(float)")
    assert resolve_rvm_input_dtype(sess, Path("rvm_mobilenetv3_fp16.onnx")) == np.dtype(
        np.float32
    )


def test_resolve_dtype_filename_fp16_fallback():
    assert resolve_rvm_input_dtype(None, Path("rvm_mobilenetv3_fp16.onnx")) == np.dtype(
        np.float16
    )


def test_resolve_dtype_filename_fp32_fallback():
    assert resolve_rvm_input_dtype(None, Path("rvm_mobilenetv3_fp32.onnx")) == np.dtype(
        np.float32
    )


def test_resolve_dtype_default_float32():
    assert resolve_rvm_input_dtype(None, Path("rvm_custom.onnx")) == np.dtype(np.float32)


def test_matte_feed_cast_fp16(monkeypatch):
    """_OrtRvmSession.matte must cast src/recurrent to float16 for fp16 graphs."""
    import hybrid_editor.engines.fast_rvm as fr

    captured: dict = {}

    class _Sess:
        def get_inputs(self):
            return [
                SimpleNamespace(name="src", type="tensor(float16)", shape=[1, 3, "h", "w"]),
                SimpleNamespace(name="r1i", type="tensor(float16)", shape=[1, 1, 1, 1]),
                SimpleNamespace(name="r2i", type="tensor(float16)", shape=[1, 1, 1, 1]),
                SimpleNamespace(name="r3i", type="tensor(float16)", shape=[1, 1, 1, 1]),
                SimpleNamespace(name="r4i", type="tensor(float16)", shape=[1, 1, 1, 1]),
                SimpleNamespace(
                    name="downsample_ratio", type="tensor(float)", shape=[1]
                ),
            ]

        def get_providers(self):
            return ["CPUExecutionProvider"]

        def run(self, _outs, feeds):
            captured["feeds"] = feeds
            # fgr, pha, r1..r4
            pha = np.ones((1, 1, 8, 8), dtype=np.float16) * 0.5
            fgr = np.zeros((1, 3, 8, 8), dtype=np.float16)
            z = np.zeros((1, 1, 1, 1), dtype=np.float16)
            return [fgr, pha, z, z, z, z]

    monkeypatch.setattr(fr, "acquire_cuda", lambda *a, **k: None)
    monkeypatch.setattr(fr, "release_cuda", lambda *a, **k: None)

    # Bypass real ORT import / session create
    obj = object.__new__(fr._OrtRvmSession)
    obj.session = _Sess()
    obj.provider = "CPUExecutionProvider"
    obj._uses_cuda = False
    obj._r1 = obj._r2 = obj._r3 = obj._r4 = None
    obj.model_path = Path("rvm_mobilenetv3_fp16.onnx")
    obj.input_dtype = resolve_rvm_input_dtype(obj.session, obj.model_path)

    bgr = np.zeros((32, 32, 3), dtype=np.uint8)
    alpha = obj.matte(bgr, downsample=0.25)
    assert alpha.shape == (32, 32)
    assert captured["feeds"]["src"].dtype == np.float16
    assert captured["feeds"]["r1i"].dtype == np.float16
    assert captured["feeds"]["downsample_ratio"].dtype == np.float32
