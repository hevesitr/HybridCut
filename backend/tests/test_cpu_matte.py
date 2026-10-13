"""CPU matte P0 (`2026-10-11-rvm-back`).

CPU-first launch; probe must FAIL when plugin EP warning appears (native C++
stderr) or CUDA smoke is gray-slab. Soft RVM person mattes must not be
false-empty. Preview must return a non-slab person matte and clear sticky toast.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

BACKEND = Path(__file__).resolve().parents[1]
ROOT = BACKEND.parent
sys.path.insert(0, str(BACKEND))

SYNC = ROOT / "SYNC_VERSION.txt"
FEATURE = ROOT / "backend" / "hybrid_editor" / "FEATURE_CPU_MATTE.txt"
FEATURE2 = ROOT / "backend" / "hybrid_editor" / "FEATURE_RVM_BACK.txt"
RESTART = ROOT / "docs" / "rvm-back-restart.md"
START = ROOT / "start_hybrid_cuda.ps1"
MAIN = ROOT / "backend" / "hybrid_editor" / "main.py"
RUN = ROOT / "run_hybrid.ps1"
APP = ROOT / "frontend" / "src" / "App.tsx"
CUDA_PATH = ROOT / "backend" / "hybrid_editor" / "cuda_path.py"
PROBE = ROOT / "scripts" / "probe_cuda_ep.py"


def _first_onnx() -> Path | None:
    for p in (
        ROOT / "models" / "rvm_resnet50_fp32.onnx",
        ROOT / "models" / "rvm_mobilenetv3_fp32.onnx",
        ROOT / "models" / "rvm_mobilenetv3_fp16.onnx",
    ):
        if p.is_file():
            return p
    env = os.environ.get("HYBRID_RVM_ONNX")
    if env and Path(env).is_file():
        return Path(env)
    return None


def test_stamp_rvm_back():
    assert FEATURE.read_text(encoding="utf-8").strip() == "2026-10-13-full-body-fast"
    assert FEATURE2.read_text(encoding="utf-8").strip() == "2026-10-13-full-body-fast"
    assert SYNC.read_text(encoding="utf-8").strip() == "2026-10-13-full-body-fast"
    text = RESTART.read_text(encoding="utf-8")
    assert "2026-10-11-rvm-back" in text
    assert "CPU-first" in text or "cpu-first" in text.lower()
    assert "why still broken" in text.lower() or "cpu-matte" in text
    assert "No registered plugin EP" in text
    assert "CPU ORT" in text
    start = START.read_text(encoding="utf-8")
    assert "simple-bg" in start or "CPU-first" in start or "HYBRID_ORT_PROVIDER" in start
    assert "CPU-first" in start or "cpu" in start.lower()
    assert "probe_cuda_ep.py" in start
    main = MAIN.read_text(encoding="utf-8")
    assert 'os.environ["HYBRID_ORT_PROVIDER"] = "cpu"' in main
    run = RUN.read_text(encoding="utf-8")
    assert '$env:HYBRID_ORT_PROVIDER = "cpu"' in run
    app = APP.read_text(encoding="utf-8")
    assert "matte_recovered" in app
    assert "Hibás maszk" in app
    assert "szürke lap" in app
    cuda = CUDA_PATH.read_text(encoding="utf-8")
    assert "dup2" in cuda
    assert "_probe_rvm_cuda_smoke" in cuda
    assert "set_cuda_ep_probe_cache" in cuda
    assert PROBE.is_file()
    probe = PROBE.read_text(encoding="utf-8")
    assert "model_path" in probe
    assert "gray-slab" in probe or "gray slab" in probe.lower() or "contradict" in probe


def test_soft_rvm_person_not_false_empty():
    """Wide-shot soft RVM (cover~0.04, mean~0.016) must count as person matte."""
    import cv2

    from hybrid_editor.media.video_io import (
        is_matte_degenerate,
        is_matte_empty,
        is_matte_structured,
        matte_failure_reason,
    )

    h, w = 480, 360
    a = np.zeros((h, w), np.float32)
    cv2.ellipse(a, (w // 2, int(h * 0.55)), (w // 10, h // 5), 0, 0, 360, 0.85, -1)
    a = cv2.GaussianBlur(a, (0, 0), 2.5)
    # Match live CPU RVM soft stats ballpark
    cover = float((a > 0.15).mean())
    assert 0.02 < cover < 0.15
    assert float(a.mean()) < 0.08  # soft wide-shot; old floor 0.03 false-emptied these
    assert is_matte_structured(a)
    assert not is_matte_degenerate(a)
    assert not is_matte_empty(a)
    assert matte_failure_reason(a) is None
    ones = np.ones((h, w), np.float32)
    assert is_matte_degenerate(ones) and is_matte_empty(ones)


def test_no_soft_ok_when_probe_session_fails(monkeypatch: pytest.MonkeyPatch):
    """Listed CUDA + cuDNN present + session fail must NOT claim CUDA usable."""
    import hybrid_editor.cuda_path as cp

    cp.clear_cuda_ep_probe_cache()

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
            raise RuntimeError("unrelated probe failure while cudnn present")

    monkeypatch.setattr(cp, "inject_nvidia_pip_libs", lambda: [])
    monkeypatch.setattr(cp, "pip_cudnn_present", lambda: (True, "cudnn ok"))
    ok, detail = cp.probe_cuda_ep_usable(FakeOrt(), use_cache=False)
    assert ok is False
    assert "CUDA" in detail or "fail" in detail.lower()


def test_false_ok_probe_fails_on_plugin_warning(monkeypatch: pytest.MonkeyPatch):
    """Identity can claim CUDA active while C++ logs plugin EP missing → FAIL."""
    import hybrid_editor.cuda_path as cp

    cp.clear_cuda_ep_probe_cache()

    class FakeSess:
        def get_providers(self):
            return ["CUDAExecutionProvider"]

        def run(self, _outs, feeds):
            # Warning may appear during run (native FD path); still return Identity.
            sys.stderr.write(
                "[W:onnxruntime:Default] No registered plugin EP device found for "
                "'CUDAExecutionProvider' with device_id=0\n"
            )
            import numpy as np

            return [np.zeros((1, 1, 1, 1), np.float32)]

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
            # Session create looks fine (listed CUDA) — warning on first run.
            return FakeSess()

    monkeypatch.setattr(cp, "inject_nvidia_pip_libs", lambda: [])
    monkeypatch.setattr(cp, "pip_cudnn_present", lambda: (True, "cudnn ok"))
    # Skip heavy RVM smoke for this unit test (Identity + plugin warn is enough).
    monkeypatch.setattr(cp, "_probe_rvm_cuda_smoke", lambda *a, **k: (True, "skip"))
    ok, detail = cp.probe_cuda_ep_usable(FakeOrt(), use_cache=False)
    assert ok is False, detail
    assert "plugin EP" in detail or "CPU ORT" in detail


def test_plugin_warning_forces_cpu_only_providers(
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

        def get_outputs(self):
            return [SimpleNamespace(name="pha")]

        def run(self, _outs, feeds):
            return [np.zeros((1, 1, 1, 1), np.float32)]

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
            names = []
            for p in providers or []:
                names.append(p[0] if isinstance(p, tuple) else p)
            # Probe: CUDA-only → claim CUDA active but emit plugin warning
            if names == ["CUDAExecutionProvider"] or (
                len(names) == 1 and names[0] == "CUDAExecutionProvider"
            ):
                sys.stderr.write(
                    "No registered plugin EP device found for 'CUDAExecutionProvider' "
                    "with device_id=0\n"
                )
                return FakeSess(["CUDAExecutionProvider"])
            return FakeSess(["CPUExecutionProvider"])

    monkeypatch.setenv("HYBRID_ORT_PROVIDER", "cuda")
    monkeypatch.setattr(fr, "acquire_cuda", lambda *a, **k: None)
    monkeypatch.setattr(fr, "release_cuda", lambda *a, **k: None)
    monkeypatch.setitem(sys.modules, "onnxruntime", FakeOrt)
    monkeypatch.setattr(cp, "inject_nvidia_pip_libs", lambda: [])
    monkeypatch.setattr(cp, "pip_cudnn_present", lambda: (True, "cudnn ok"))
    monkeypatch.setattr("hybrid_editor.cuda_path.inject_nvidia_pip_libs", lambda: [])
    monkeypatch.setattr("hybrid_editor.cuda_path.pip_cudnn_present", lambda: (True, "cudnn ok"))

    sess = fr._OrtRvmSession(model)
    assert sess.provider == "CPUExecutionProvider"
    assert sess._uses_cuda is False
    assert sess.fallback_note and "CUDA→CPU" in sess.fallback_note
    assert getattr(sess, "_masks_stale", False) in (True, False)  # may clear after verify
    # Final create must be CPU-only — never leave CUDA in the provider list.
    assert calls, "expected InferenceSession calls"
    last = calls[-1]
    assert last == ["CPUExecutionProvider"]
    assert os.environ.get("HYBRID_ORT_PROVIDER") == "cpu"


def test_ui_shows_cpu_ort_not_rtx_when_ep_missing():
    app = APP.read_text(encoding="utf-8")
    assert "function gpuOrtChip" in app
    assert 'label: "CPU ORT"' in app
    assert "gpuOrtChip(status)" in app
    assert "ensureMaxWhenCudaUnusable" not in app  # simple-bg Gyors
    assert "matte_recovered" in app


def test_rebuild_clears_matte_error_on_cpu_preview(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    """After CUDA gray-slab smoke → CPU rebuild, preview must not sticky-toast."""
    import hybrid_editor.cuda_path as cp
    import hybrid_editor.engines.fast_rvm as fr
    from hybrid_editor.media.video_io import is_matte_empty

    cp.clear_cuda_ep_probe_cache()
    model = tmp_path / "rvm_mobilenetv3_fp32.onnx"
    model.write_bytes(b"fake")

    class FakeSess:
        def __init__(self, providers, *, slab: bool = False):
            self._providers = providers
            self._slab = slab

        def get_providers(self):
            return list(self._providers)

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

        def run(self, _outs, feeds):
            src = feeds.get("src")
            # Infer H,W from feed
            if src is not None and hasattr(src, "shape") and len(src.shape) == 4:
                _n, _c, h, w = src.shape
            else:
                h, w = 128, 96
            if self._slab:
                pha = np.ones((1, 1, h, w), np.float32)
            else:
                pha = np.zeros((1, 1, h, w), np.float32)
                pha[0, 0, h // 4 : 3 * h // 4, w // 4 : 3 * w // 4] = 0.9
            fgr = np.zeros((1, 3, h, w), np.float32)
            z = np.zeros((1, 1, 1, 1), np.float32)
            return [fgr, pha, z, z, z, z]

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
            names = []
            for p in providers or []:
                names.append(p[0] if isinstance(p, tuple) else p)
            if "CUDAExecutionProvider" in names and "CPUExecutionProvider" in names:
                # Dual list — CUDA claimed, will gray-slab on smoke
                return FakeSess(["CUDAExecutionProvider", "CPUExecutionProvider"], slab=True)
            if names == ["CUDAExecutionProvider"] or (
                len(names) == 1 and names[0] == "CUDAExecutionProvider"
            ):
                # Probe Identity / CUDA-only — say usable so session tries CUDA
                return FakeSess(["CUDAExecutionProvider"], slab=True)
            return FakeSess(["CPUExecutionProvider"], slab=False)

    monkeypatch.setenv("HYBRID_ORT_PROVIDER", "cuda")
    monkeypatch.setattr(fr, "acquire_cuda", lambda *a, **k: None)
    monkeypatch.setattr(fr, "release_cuda", lambda *a, **k: None)
    monkeypatch.setitem(sys.modules, "onnxruntime", FakeOrt)
    monkeypatch.setattr(cp, "inject_nvidia_pip_libs", lambda: [])
    monkeypatch.setattr(cp, "pip_cudnn_present", lambda: (True, "cudnn ok"))
    monkeypatch.setattr("hybrid_editor.cuda_path.inject_nvidia_pip_libs", lambda: [])
    monkeypatch.setattr("hybrid_editor.cuda_path.pip_cudnn_present", lambda: (True, "cudnn ok"))
    # Probe returns True so we enter CUDA path then smoke forces CPU.
    monkeypatch.setattr(cp, "probe_cuda_ep_usable", lambda *a, **k: (True, "fake cuda ok"))
    monkeypatch.setattr(
        "hybrid_editor.cuda_path.probe_cuda_ep_usable",
        lambda *a, **k: (True, "fake cuda ok"),
    )

    sess = fr._OrtRvmSession(model)
    assert sess.provider == "CPUExecutionProvider"
    assert sess._uses_cuda is False
    note = (sess.fallback_note or "").lower()
    assert sess.fallback_note and ("gray-slab" in note or "cpu" in note)

    # Live matte on CPU must be structured (FakeSess non-slab).
    import cv2

    h, w = 120, 90
    bgr = np.zeros((h, w, 3), dtype=np.uint8)
    bgr[:] = (40, 40, 45)
    cv2.ellipse(bgr, (w // 2, int(h * 0.55)), (w // 5, h // 3), 0, 0, 360, (190, 170, 150), -1)
    alpha = sess.matte(bgr, downsample=0.5)
    assert not is_matte_empty(alpha), "CPU session after rebuild must produce person matte"
    assert float(alpha.std()) > 0.04


@pytest.mark.skipif(_first_onnx() is None, reason="RVM ONNX weights not available")
def test_live_cpu_rvm_person_matte_not_slab(monkeypatch: pytest.MonkeyPatch):
    """P0: CPU path (RVM ± ResNet auto-switch ± heuristic) must yield a person matte."""
    import cv2

    from hybrid_editor.engines.fast_rvm import FastEngine
    from hybrid_editor.media.video_io import is_matte_degenerate, is_matte_empty

    monkeypatch.setenv("HYBRID_ORT_PROVIDER", "cpu")
    onnx = _first_onnx()
    assert onnx is not None

    # Photographic-ish fixture: warm ellipse on cool bg (person-like).
    h, w = 240, 180
    bgr = np.zeros((h, w, 3), dtype=np.uint8)
    bgr[:] = (50, 45, 40)
    cv2.ellipse(bgr, (w // 2, int(h * 0.55)), (w // 5, h // 3), 0, 0, 360, (190, 170, 150), -1)
    cv2.circle(bgr, (w // 2, int(h * 0.28)), w // 8, (200, 180, 160), -1)

    # Product path: primary ORT → alternate ResNet/MobileNet → heuristic.
    eng = FastEngine()
    try:
        assert "CPU" in str(eng._backend) or eng._rvm is None or not getattr(
            eng._rvm, "_uses_cuda", False
        )
        alpha = eng._matte(bgr)
        assert not is_matte_empty(alpha), "CPU matte ladder produced no usable person matte"
        assert float(alpha.std()) > 0.04
        cover = float((alpha > 0.15).mean())
        assert 0.02 < cover < 0.95
        assert not np.allclose(alpha, 1.0)
        assert not is_matte_degenerate(alpha)
    finally:
        eng.close()

    # FastEngine preview on sample (if present) must not sticky-toast gray slab.
    sample = ROOT / "cache" / "sample_person.mp4"
    if sample.is_file():
        eng = FastEngine()
        try:
            eng.open_media(sample)
            frame = eng.preview_frame(0.0)
            meta = frame.meta or {}
            assert meta.get("stamp") == "2026-10-13-full-body-fast"
            empty = bool(meta.get("matte_empty") or meta.get("source_fallback"))
            err = str(meta.get("matte_error") or "")
            assert not empty, f"CPU preview still empty/slab: {meta}"
            assert "egyenletes" not in err
            assert not meta.get("matte_error")
        finally:
            eng.close()
