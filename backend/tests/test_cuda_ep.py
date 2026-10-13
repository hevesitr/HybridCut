"""CUDA EP plugin registration (`2026-10-11-cuda-restore`).

Listed CUDAExecutionProvider ≠ registered plugin EP. Missing plugin must force
CPU ORT before RVM inference (no gray-slab CUDA path).
"""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

BACKEND = Path(__file__).resolve().parents[1]
ROOT = BACKEND.parent
sys.path.insert(0, str(BACKEND))

SYNC = ROOT / "SYNC_VERSION.txt"
FEATURE = ROOT / "backend" / "hybrid_editor" / "FEATURE_CUDA_RESTORE.txt"
FEATURE_EP = ROOT / "backend" / "hybrid_editor" / "FEATURE_CUDA_EP.txt"
RESTART = ROOT / "docs" / "cuda-restore-restart.md"
START = ROOT / "start_hybrid_cuda.ps1"
PROBE = ROOT / "scripts" / "probe_cuda_ep.py"
ORT_VER = ROOT / "scripts" / "ort_version.py"
REQ_GPU = ROOT / "backend" / "requirements-gpu.txt"
APP = ROOT / "frontend" / "src" / "App.tsx"


def test_stamp_and_docs():
    tip = SYNC.read_text(encoding="utf-8").strip()
    assert tip == "2026-10-13-matte-safe"
    assert FEATURE.read_text(encoding="utf-8").strip() == "2026-10-13-matte-safe"
    assert FEATURE_EP.read_text(encoding="utf-8").strip() == "2026-10-13-matte-safe"
    text = RESTART.read_text(encoding="utf-8")
    assert "No registered plugin EP" in text
    assert "CPU ORT" in text
    assert "onnxruntime-gpu==1.30.0" in text
    assert "probe_cuda_ep.py" in text
    start = START.read_text(encoding="utf-8")
    assert "probe_cuda_ep.py" in start
    assert "-c $probePy" not in start
    assert "RESULT: OK" in start and "RESULT: FAIL" in start
    assert "HYBRID_ORT_PROVIDER" in start
    assert "1.30.0" in start
    assert "rvm-back" in start
    assert 'HYBRID_ORT_PROVIDER = "cpu"' in start or "CPU-first" in start
    assert PROBE.is_file()
    assert ORT_VER.is_file()
    assert "onnxruntime-gpu==1.30.0" in REQ_GPU.read_text(encoding="utf-8")
    app = APP.read_text(encoding="utf-8")
    assert "CPU ORT" in app
    assert "cuda_ep_registered" in app
    assert "1.30.0" in app


def test_plugin_ep_missing_text():
    from hybrid_editor.cuda_path import is_cudnn_or_cuda_ep_error, is_plugin_ep_missing_text

    msg = (
        "[W:onnxruntime:Default, onnxruntime_pybind_state.cc:855] "
        "No registered plugin EP device found for 'CUDAExecutionProvider' with device_id=0"
    )
    assert is_plugin_ep_missing_text(msg)
    assert is_cudnn_or_cuda_ep_error(RuntimeError(msg))


def test_probe_fails_when_cuda_not_listed(monkeypatch: pytest.MonkeyPatch):
    import hybrid_editor.cuda_path as cp

    cp.clear_cuda_ep_probe_cache()

    class FakeOrt:
        @staticmethod
        def get_available_providers():
            return ["CPUExecutionProvider"]

    ok, detail = cp.probe_cuda_ep_usable(FakeOrt(), use_cache=False)
    assert ok is False
    assert "CUDAExecutionProvider" in detail or "CPU ORT" in detail


def test_probe_fails_on_plugin_ep_warning(monkeypatch: pytest.MonkeyPatch):
    import hybrid_editor.cuda_path as cp

    cp.clear_cuda_ep_probe_cache()

    class FakeSess:
        def get_providers(self):
            return ["CUDAExecutionProvider"]

    class FakeOrt:
        GraphOptimizationLevel = SimpleNamespace(ORT_ENABLE_BASIC=1, ORT_ENABLE_ALL=99)

        class SessionOptions:
            def __init__(self):
                self.graph_optimization_level = None
                self.log_severity_level = 3

        @staticmethod
        def get_available_providers():
            return ["CUDAExecutionProvider", "CPUExecutionProvider"]

        @staticmethod
        def InferenceSession(model, sess_options=None, providers=None):
            # Simulate ORT stderr warning while still returning a session that
            # claims CUDA — catcher must still reject.
            sys.stderr.write(
                "No registered plugin EP device found for 'CUDAExecutionProvider' "
                "with device_id=0\n"
            )
            return FakeSess()

    ok, detail = cp.probe_cuda_ep_usable(FakeOrt(), use_cache=False)
    assert ok is False
    assert "plugin EP" in detail or "CPU ORT" in detail


def test_session_skips_cuda_when_plugin_missing(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    import hybrid_editor.cuda_path as cp
    import hybrid_editor.engines.fast_rvm as fr

    cp.clear_cuda_ep_probe_cache()
    model = tmp_path / "rvm_resnet50_fp32.onnx"
    model.write_bytes(b"fake")

    class FakeSess:
        def __init__(self, providers):
            self._providers = providers

        def get_providers(self):
            return list(self._providers)

        def get_inputs(self):
            return [
                SimpleNamespace(name="src", type="tensor(float)", shape=[1, 3, "h", "w"])
            ]

    calls: list[list] = []

    class FakeOrt:
        GraphOptimizationLevel = SimpleNamespace(ORT_ENABLE_ALL=99, ORT_ENABLE_BASIC=1)

        class SessionOptions:
            def __init__(self):
                self.graph_optimization_level = None
                self.log_severity_level = 3

        @staticmethod
        def get_available_providers():
            return ["CUDAExecutionProvider", "CPUExecutionProvider"]

        @staticmethod
        def InferenceSession(path, sess_options=None, providers=None):
            calls.append(list(providers or []))
            # Probe uses CUDA-only; claim fail via active CPU
            names = []
            for p in providers or []:
                names.append(p[0] if isinstance(p, tuple) else p)
            if names == ["CUDAExecutionProvider"] or (
                len(names) == 1 and names[0] == "CUDAExecutionProvider"
            ):
                # Probe: pretend session activates CPU (plugin missing)
                return FakeSess(["CPUExecutionProvider"])
            return FakeSess(names or ["CPUExecutionProvider"])

    monkeypatch.setenv("HYBRID_ORT_PROVIDER", "cuda")
    monkeypatch.setattr(fr, "acquire_cuda", lambda *a, **k: None)
    monkeypatch.setattr(fr, "release_cuda", lambda *a, **k: None)
    monkeypatch.setitem(sys.modules, "onnxruntime", FakeOrt)
    monkeypatch.setattr(cp, "inject_nvidia_pip_libs", lambda: [])
    monkeypatch.setattr(cp, "pip_cudnn_present", lambda: (True, "cudnn ok"))
    monkeypatch.setattr(
        "hybrid_editor.cuda_path.inject_nvidia_pip_libs",
        lambda: [],
    )
    monkeypatch.setattr(
        "hybrid_editor.cuda_path.pip_cudnn_present",
        lambda: (True, "cudnn ok"),
    )

    sess = fr._OrtRvmSession(model)
    assert sess.provider == "CPUExecutionProvider"
    assert sess._uses_cuda is False
    assert sess.fallback_note and (
        "CUDA→CPU" in sess.fallback_note or "CPU ORT" in sess.fallback_note
    )
    # Final RVM session must be CPU-only (no CUDA EP in provider list)
    assert calls, "expected InferenceSession calls"
    last = calls[-1]
    assert last == ["CPUExecutionProvider"] or (
        len(last) == 1 and last[0] == "CPUExecutionProvider"
    )
    assert monkeypatch is not None
    import os

    assert os.environ.get("HYBRID_ORT_PROVIDER") == "cpu"


def test_probe_ort_runtime_honest_cuda_ep(monkeypatch: pytest.MonkeyPatch):
    import hybrid_editor.cuda_path as cp
    import hybrid_editor.engines.fast_rvm as fr

    cp.clear_cuda_ep_probe_cache()
    monkeypatch.setenv("HYBRID_ORT_PROVIDER", "cpu")
    monkeypatch.delenv("HYBRID_RVM_ONNX", raising=False)
    info = fr.probe_ort_runtime()
    assert info.get("ort_label_hu") == "CPU ORT" or info.get("prefer") == "cpu"
    assert info.get("cuda_ep") is False


def test_probe_script_emits_ok_keys():
    """scripts/probe_cuda_ep.py must print OK=/RESULT= without SyntaxError."""
    import subprocess

    env = dict(**{k: v for k, v in __import__("os").environ.items()})
    env["HYBRID_ROOT"] = str(ROOT)
    env["PYTHONPATH"] = str(BACKEND)
    proc = subprocess.run(
        [sys.executable, str(PROBE)],
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr
    out = proc.stdout
    assert "OK=" in out
    assert "RESULT=" in out
    assert "PIN=1.30.0" in out or "PIN=" in out


def test_preferred_ort_pin():
    from hybrid_editor.cuda_path import PREFERRED_ORT_GPU_VERSION, ort_gpu_pin_ok

    assert PREFERRED_ORT_GPU_VERSION == "1.30.0"
    ok, detail = ort_gpu_pin_ok()
    assert isinstance(ok, bool)
    assert "1.30.0" in detail
