"""HybridCut pip cuDNN PATH inject + CUDA EP soft fallback."""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace

import pytest

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

import hybrid_editor.cuda_path as cp  # noqa: E402
from hybrid_editor.engines import fast_rvm as fr  # noqa: E402


def test_finds_simulated_windows_cudnn_bin() -> None:
    with tempfile.TemporaryDirectory() as td:
        site = Path(td) / "Lib" / "site-packages"
        bin_dir = site / "nvidia" / "cudnn" / "bin"
        bin_dir.mkdir(parents=True)
        (bin_dir / "cudnn64_9.dll").write_bytes(b"fake")
        cublas = site / "nvidia" / "cublas" / "bin"
        cublas.mkdir(parents=True)
        (cublas / "cublas64_12.dll").write_bytes(b"x")

        old = cp._site_package_roots
        prev_dll = set(cp._DLL_DIRS_ADDED)
        try:
            cp._site_package_roots = lambda: [site]  # type: ignore[assignment]
            cp._DLL_DIRS_ADDED.clear()
            dirs = list(cp.iter_nvidia_lib_dirs())
            assert any("cudnn" in str(p) and p.name == "bin" for p in dirs), dirs
            files = cp.find_cudnn_files()
            assert files and files[0].name == "cudnn64_9.dll"
            added = cp.inject_nvidia_pip_libs()
            assert any("cudnn" in a.lower() for a in added), added
            # On Linux cloud: PATH/LD_LIBRARY_PATH prepend; on Windows also add_dll_directory.
            assert str(bin_dir) in os.environ.get("PATH", "") or any(
                Path(a) == bin_dir for a in added
            )
            ok, detail = cp.pip_cudnn_present()
            assert ok, detail
            assert "cudnn64_9.dll" in detail
        finally:
            cp._site_package_roots = old  # type: ignore[assignment]
            cp._DLL_DIRS_ADDED.clear()
            cp._DLL_DIRS_ADDED.update(prev_dll)


def test_path_hit_counts_as_present() -> None:
    with tempfile.TemporaryDirectory() as td:
        d = Path(td) / "manual"
        d.mkdir()
        (d / "cudnn64_9.dll").write_bytes(b"x")
        prev = os.environ.get("PATH", "")
        old = cp._site_package_roots
        try:
            cp._site_package_roots = lambda: [Path(td) / "empty"]  # type: ignore[assignment]
            (Path(td) / "empty").mkdir(exist_ok=True)
            os.environ["PATH"] = str(d) + os.pathsep + prev
            ok, detail = cp.pip_cudnn_present()
            assert ok, detail
        finally:
            cp._site_package_roots = old  # type: ignore[assignment]
            os.environ["PATH"] = prev


def test_is_cudnn_or_cuda_ep_error() -> None:
    assert cp.is_cudnn_or_cuda_ep_error(
        RuntimeError("LoadLibrary failed for cudnn64_9.dll with error 2")
    )
    assert cp.is_cudnn_or_cuda_ep_error(
        RuntimeError("cuDNN is unavailable or disabled for CUDA Execution Provider")
    )
    assert not cp.is_cudnn_or_cuda_ep_error(RuntimeError("INVALID_ARGUMENT float vs float16"))


def test_ort_session_soft_fallback_to_cpu(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    model = tmp_path / "rvm_mobilenetv3_fp32.onnx"
    model.write_bytes(b"fake")

    class FakeSess:
        def __init__(self, providers):
            self._providers = providers

        def get_providers(self):
            return list(self._providers)

        def get_inputs(self):
            return [SimpleNamespace(name="src", type="tensor(float)", shape=[1, 3, "h", "w"])]

    calls: list[list[str]] = []

    class FakeOrt:
        GraphOptimizationLevel = SimpleNamespace(ORT_ENABLE_ALL=99)

        class SessionOptions:
            def __init__(self):
                self.graph_optimization_level = None

        @staticmethod
        def get_available_providers():
            return ["CUDAExecutionProvider", "CPUExecutionProvider"]

        @staticmethod
        def InferenceSession(path, sess_options=None, providers=None):
            calls.append(list(providers or []))
            if providers and providers[0] == "CUDAExecutionProvider":
                raise RuntimeError(
                    "LoadLibrary failed for cudnn64_9.dll with error 2. "
                    "cuDNN is unavailable or disabled for CUDA Execution Provider"
                )
            return FakeSess(["CPUExecutionProvider"])

    monkeypatch.setenv("HYBRID_ORT_PROVIDER", "cuda")
    monkeypatch.setattr(fr, "acquire_cuda", lambda *a, **k: None)
    monkeypatch.setattr(fr, "release_cuda", lambda *a, **k: None)
    monkeypatch.setitem(sys.modules, "onnxruntime", FakeOrt)
    monkeypatch.setattr(cp, "inject_nvidia_pip_libs", lambda: [])
    monkeypatch.setattr(cp, "pip_cudnn_present", lambda: (False, "missing cudnn"))

    # Re-import path used inside _OrtRvmSession
    monkeypatch.setattr(
        "hybrid_editor.cuda_path.inject_nvidia_pip_libs",
        lambda: [],
    )
    monkeypatch.setattr(
        "hybrid_editor.cuda_path.pip_cudnn_present",
        lambda: (False, "missing cudnn"),
    )

    sess = fr._OrtRvmSession(model)
    assert sess.provider == "CPUExecutionProvider"
    assert sess.fallback_note and "CUDA" in sess.fallback_note
    assert calls[0][0] == "CUDAExecutionProvider"
    assert calls[1] == ["CPUExecutionProvider"]


def test_probe_includes_cudnn_fields(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("HYBRID_RVM_ONNX", raising=False)
    info = fr.probe_ort_runtime()
    assert "cudnn_ok" in info
    assert "cudnn_detail" in info
    assert "cuda_fallback" in info
