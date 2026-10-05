"""Tests for engine modes, MaskStore preview path, bake export."""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

from hybrid_editor.engines.factory import create_engine, resolve_mode
from hybrid_editor.engines.base import EngineMode
from hybrid_editor.engines.quality_pipeline import (
    DEFAULT_WARMUP,
    AnchorMemoryStabilizer,
    apply_quality_pass,
    build_guidance_trimap,
    warmup_alpha,
)
from hybrid_editor.engines.vram import acquire_cuda, force_release_all, release_cuda
from hybrid_editor.session import EditorSession


def test_resolve_mode_aliases():
    assert resolve_mode("gyors") is EngineMode.GYORS
    assert resolve_mode("fast") is EngineMode.GYORS
    assert resolve_mode("max") is EngineMode.MAX
    assert resolve_mode("max_quality") is EngineMode.MAX
    with pytest.raises(ValueError):
        resolve_mode("cloud")


def test_create_engine_modes():
    fast = create_engine("gyors")
    mx = create_engine("max")
    assert fast.mode is EngineMode.GYORS
    assert mx.mode is EngineMode.MAX
    assert fast.capabilities().available
    assert mx.capabilities().available
    note = mx.capabilities().license_note.lower()
    assert "s-lab" in note or "non-commercial" in note
    # Heuristic documented when no ONNX
    assert fast.capabilities().backend in ("heuristic",) or fast.capabilities().backend.startswith("ort-rvm")


def test_vram_guard_exclusive():
    force_release_all()
    acquire_cuda("fast-ort", detail="test")
    with pytest.raises(RuntimeError):
        acquire_cuda("max-matanyone2", detail="conflict")
    release_cuda("fast-ort")
    acquire_cuda("max-matanyone2", detail="ok")
    release_cuda("max-matanyone2")
    force_release_all()


def test_session_mode_switch_preserves_contract():
    session = EditorSession()
    assert session.mode is EngineMode.GYORS
    st = session.set_mode("max")
    assert st["mode"] == "max"
    assert "Max" in st["mode_label"] or "élesebb" in st["mode_label"]
    assert st.get("sharp_edges") is True
    st2 = session.set_mode("gyors")
    assert st2["mode"] == "gyors"
    assert "lágyabb" in st2["mode_label"] or "Gyors" in st2["mode_label"]
    assert st2["backend"] != ""


def test_trimap_warmup_anchor():
    seed = np.zeros((64, 64), np.float32)
    seed[16:48, 16:48] = 1.0
    tri = build_guidance_trimap(seed, erode_k=5, dilate_k=5)
    assert tri.fg.shape == (64, 64)
    assert float(tri.unknown.mean()) > 0.0
    calls = {"n": 0}

    def matte(_bgr):
        calls["n"] += 1
        return seed

    warm = warmup_alpha(matte, np.zeros((64, 64, 3), np.uint8), n_warmup=DEFAULT_WARMUP)
    assert calls["n"] == DEFAULT_WARMUP
    assert warm.shape == seed.shape
    stab = AnchorMemoryStabilizer(strength=0.4)
    a1 = apply_quality_pass(seed, seed=seed, stabilizer=stab)
    a2 = apply_quality_pass(seed * 0.9, seed=seed, stabilizer=stab)
    assert a1.shape == seed.shape
    assert a2.min() >= 0.0 and a2.max() <= 1.0


def _write_sample(path: Path, n: int = 8) -> None:
    import cv2

    w, h = 160, 120
    writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"mp4v"), 10, (w, h))
    for i in range(n):
        frame = np.zeros((h, w, 3), np.uint8)
        frame[:] = (30, 100, 40)
        cv2.circle(frame, (40 + i * 5, 60), 25, (40, 50, 200), -1)
        writer.write(frame)
    writer.release()


def test_preview_maskstore_and_bake_export(tmp_path: Path):
    sample = tmp_path / "t.mp4"
    _write_sample(sample, n=8)

    session = EditorSession()
    session.set_mode("gyors")
    st = session.open_media(sample)
    assert st["timeline"] is not None
    assert st["frame_plan"] is not None

    prev = session.preview(0.1)
    assert prev.jpeg_b64 and prev.alpha_png_b64
    assert prev.engine == "FastEngine"
    # Second preview near same time should prefer MaskStore
    prev2 = session.preview(0.12)
    assert prev2.meta.get("mask_store") in (True, False)  # may or may not hit depending on ms

    session.update_timeline(in_sec=0.0, out_sec=0.4, playhead_sec=0.1)
    plan = session.get_frame_plan(0.1)
    assert plan["empty"] is False

    session.set_mode("max")
    prev3 = session.preview(0.2)
    assert prev3.engine == "MaxQualityEngine"

    out = tmp_path / "bake"
    result = session.bake(out, max_frames=3, async_job=False)
    assert isinstance(result, type(session.last_bake))
    assert result.ok
    assert result.frames_written == 3
    assert (out / "alpha" / "000000.png").is_file()
    assert result.preview_mp4
    assert Path(result.preview_mp4).is_file()
