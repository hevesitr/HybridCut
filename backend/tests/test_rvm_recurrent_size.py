"""RVM recurrent state must reset when inference spatial size changes.

Regression: Expand_134 cannot broadcast LeftShape {1,128,26,45} vs RightShape
{1,128,51,90} when Max preview/full-res path feeds stale r1..r4 into a larger run.
"""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

import numpy as np

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

from hybrid_editor.engines.fast_rvm import (  # noqa: E402
    _OrtRvmSession,
    resolve_rvm_input_dtype,
)


def _fake_inputs(dtype_name: str = "tensor(float)"):
    return [
        SimpleNamespace(name="src", type=dtype_name, shape=[1, 3, "h", "w"]),
        SimpleNamespace(name="r1i", type=dtype_name, shape=[1, 1, 1, 1]),
        SimpleNamespace(name="r2i", type=dtype_name, shape=[1, 1, 1, 1]),
        SimpleNamespace(name="r3i", type=dtype_name, shape=[1, 1, 1, 1]),
        SimpleNamespace(name="r4i", type=dtype_name, shape=[1, 1, 1, 1]),
        SimpleNamespace(name="downsample_ratio", type="tensor(float)", shape=[1]),
    ]


def _make_session(run_fn) -> _OrtRvmSession:
    class _Sess:
        def get_inputs(self):
            return _fake_inputs()

        def get_providers(self):
            return ["CPUExecutionProvider"]

        def run(self, _outs, feeds):
            return run_fn(feeds)

    obj = object.__new__(_OrtRvmSession)
    obj.session = _Sess()
    obj.provider = "CPUExecutionProvider"
    obj._uses_cuda = False
    obj._r1 = obj._r2 = obj._r3 = obj._r4 = None
    obj._rec_key = None
    obj.model_path = Path("rvm_mobilenetv3_fp32.onnx")
    obj.input_dtype = resolve_rvm_input_dtype(obj.session, obj.model_path)
    obj.fallback_note = None
    return obj


def _pha_outs(h: int, w: int, *, rec_hw: tuple[int, int] | None = None):
    """fgr, pha, r1..r4 — recurrent spatial dims track last successful grid."""
    rh, rw = rec_hw if rec_hw is not None else (max(1, h // 4), max(1, w // 4))
    dtype = np.float32
    fgr = np.zeros((1, 3, h, w), dtype=dtype)
    pha = np.ones((1, 1, h, w), dtype=dtype) * 0.55
    r = np.ones((1, 16, rh, rw), dtype=dtype) * 0.1
    return [fgr, pha, r, r.copy(), r.copy(), r.copy()]


def test_sequential_different_sizes_resets_and_succeeds():
    """Two different (H,W) runs in a row must not crash; second run ok after reset."""
    calls: list[dict] = []

    def run_fn(feeds):
        src = feeds["src"]
        _n, _c, sh, sw = src.shape
        r1 = feeds["r1i"]
        calls.append({"hw": (sh, sw), "r1_hw": tuple(r1.shape[-2:]), "r1_zero": float(np.abs(r1).max()) < 1e-8})
        # If non-zero recurrent spatial != expected grid for this src → Expand-like fail.
        if r1.size > 1 and float(np.abs(r1).max()) > 0 and r1.shape[-2:] != (max(1, sh // 4), max(1, sw // 4)):
            raise RuntimeError(
                f"Expand_134: left operand cannot broadcast on dim 3 "
                f"LeftShape: {{{','.join(str(x) for x in r1.shape)}}}, "
                f"RightShape: {{1,128,{max(1, sh // 4)},{max(1, sw // 4)}}}"
            )
        return _pha_outs(sh, sw)

    sess = _make_session(run_fn)
    small = np.zeros((104, 180, 3), dtype=np.uint8)
    large = np.zeros((208, 360, 3), dtype=np.uint8)

    a1 = sess.matte(small, downsample=0.25)
    assert a1.shape == (104, 180)
    assert sess._rec_key == (104, 180, 0.25)
    assert sess._r1 is not None

    a2 = sess.matte(large, downsample=0.25)
    assert a2.shape == (208, 360)
    assert sess._rec_key == (208, 360, 0.25)
    # Second call must have zeroed recurrent before run (proactive size reset).
    assert len(calls) == 2
    assert calls[0]["r1_zero"] is True
    assert calls[1]["r1_zero"] is True
    assert calls[1]["hw"] == (208, 360)


def test_expand_retry_once_when_stale_recurrent_forced():
    """If size guard is bypassed, Expand must reset + retry once successfully."""
    runs = {"n": 0}

    def run_fn(feeds):
        runs["n"] += 1
        src = feeds["src"]
        _n, _c, sh, sw = src.shape
        r1 = feeds["r1i"]
        # First attempt with stale non-zero wrong-size rec → Expand; zeros → ok.
        if float(np.abs(r1).max()) > 0 and r1.shape[-2:] != (max(1, sh // 4), max(1, sw // 4)):
            raise RuntimeError(
                "Expand_134: left operand cannot broadcast on dim 3 "
                "LeftShape: {1,128,26,45}, RightShape: {1,128,51,90}"
            )
        return _pha_outs(sh, sw)

    sess = _make_session(run_fn)
    # Seed stale recurrent as if prior frame was ~26x45 features.
    sess._r1 = np.ones((1, 16, 26, 45), dtype=np.float32)
    sess._r2 = np.ones((1, 16, 26, 45), dtype=np.float32)
    sess._r3 = np.ones((1, 16, 26, 45), dtype=np.float32)
    sess._r4 = np.ones((1, 16, 26, 45), dtype=np.float32)
    # Same rec_key as "current" so proactive reset is skipped (simulates missed guard).
    sess._rec_key = (208, 360, 0.25)

    alpha = sess.matte(np.zeros((208, 360, 3), dtype=np.uint8), downsample=0.25)
    assert alpha.shape == (208, 360)
    assert runs["n"] == 2  # fail once + retry
    assert sess._r1 is not None
    assert sess._r1.shape[-2:] == (52, 90)  # 208/4 x 360/4


def test_is_expand_broadcast_error_detection():
    assert _OrtRvmSession._is_expand_broadcast_error(
        RuntimeError("Expand_134: left operand cannot broadcast on dim 3")
    )
    assert _OrtRvmSession._is_expand_broadcast_error(
        RuntimeError("Cannot broadcast LeftShape vs RightShape")
    )
    assert not _OrtRvmSession._is_expand_broadcast_error(RuntimeError("CUDA OOM"))


def test_downsample_change_resets_recurrent():
    calls: list[bool] = []

    def run_fn(feeds):
        r1 = feeds["r1i"]
        calls.append(float(np.abs(r1).max()) < 1e-8)
        src = feeds["src"]
        return _pha_outs(src.shape[2], src.shape[3])

    sess = _make_session(run_fn)
    frame = np.zeros((120, 160, 3), dtype=np.uint8)
    sess.matte(frame, downsample=0.25)
    # Leave non-zero state, then change ratio only.
    assert sess._r1 is not None
    sess.matte(frame, downsample=0.5)
    assert len(calls) == 2
    assert calls[0] is True
    assert calls[1] is True  # reset because ds changed
    assert sess._rec_key == (120, 160, 0.5)
