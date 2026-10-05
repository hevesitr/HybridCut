"""Sharp person edges — tighter trimap, ResNet prefer, PNG cutout, full-res bake."""

from __future__ import annotations

import base64
import sys
from pathlib import Path

import cv2
import numpy as np
import pytest

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

from hybrid_editor.engines.fast_rvm import resolve_rvm_onnx
from hybrid_editor.engines.max_quality import MaxQualityEngine
from hybrid_editor.engines.quality_pipeline import (
    DEFAULT_DILATE_K,
    DEFAULT_ERODE_K,
    SHARP_DILATE_K,
    SHARP_ERODE_K,
    apply_quality_pass,
    build_guidance_trimap,
)
from hybrid_editor.media.video_io import encode_preview_pair
from hybrid_editor.session import EditorSession


def _soft_seed(h: int = 96, w: int = 96) -> tuple[np.ndarray, np.ndarray]:
    bgr = np.zeros((h, w, 3), np.uint8)
    bgr[:] = (40, 90, 40)
    cv2.ellipse(bgr, (w // 2, h // 2), (28, 40), 0, 0, 360, (90, 120, 200), -1)
    alpha = np.zeros((h, w), np.float32)
    cv2.ellipse(alpha, (w // 2, h // 2), (28, 40), 0, 0, 360, 1.0, -1)
    alpha = cv2.GaussianBlur(alpha, (0, 0), sigmaX=3.5)  # foggy halo like the screenshot
    return bgr, alpha


def test_harden_foggy_halo_shrinks_midband():
    from hybrid_editor.engines.videoeditor_polish import harden_foggy_halo

    h, w = 96, 96
    a = np.zeros((h, w), np.float32)
    cv2.ellipse(a, (w // 2, h // 2), (28, 40), 0, 0, 360, 1.0, -1)
    foggy = cv2.GaussianBlur(a, (0, 0), sigmaX=4.0)
    hard = harden_foggy_halo(foggy)
    mid_in = float(((foggy > 0.05) & (foggy < 0.95)).mean())
    mid_out = float(((hard > 0.05) & (hard < 0.95)).mean())
    assert mid_out < mid_in
    assert float(hard[48, 48]) > 0.7
    assert float(hard[2, 2]) < 0.08


def test_sharp_trimap_tighter_than_legacy():
    assert SHARP_ERODE_K < DEFAULT_ERODE_K
    assert SHARP_DILATE_K < DEFAULT_DILATE_K
    seed = np.zeros((80, 80), np.float32)
    seed[20:60, 20:60] = 1.0
    soft = build_guidance_trimap(seed, erode_k=DEFAULT_ERODE_K, dilate_k=DEFAULT_DILATE_K, sharp_edges=False)
    sharp = build_guidance_trimap(seed, erode_k=SHARP_ERODE_K, dilate_k=SHARP_DILATE_K, sharp_edges=True)
    # Soft path spreads a wider unknown/halo band.
    assert float(soft.unknown.mean()) > float(sharp.unknown.mean())


def test_sharp_quality_pass_hardens_foggy_halo():
    bgr, soft = _soft_seed()
    out = apply_quality_pass(soft, seed=soft, sharp_edges=True, frame_bgr=bgr)
    # Mid-band fraction should shrink vs heavily feathered input (less fog).
    soft_mid = float(((soft > 0.05) & (soft < 0.95)).mean())
    out_mid = float(((out > 0.05) & (out < 0.95)).mean())
    assert out_mid < soft_mid * 0.95
    # Core stays opaque; far BG stays near zero.
    assert float(out[48, 48]) > 0.85
    assert float(out[2, 2]) < 0.08


def test_videoeditor_polish_beats_trimap_on_halo_and_holes():
    """Priority: eliminate thick smudge + hair holes (right-side HybridCut failure)."""
    from hybrid_editor.engines.videoeditor_polish import polish_videoeditor

    bgr, soft = _soft_seed(128, 128)
    # Punch hair holes in mid-alpha
    soft[40:55, 55:70] = 0.15
    soft[50:58, 48:62] = 0.08
    # Wide foggy halo
    soft = cv2.GaussianBlur(soft, (0, 0), sigmaX=4.0)

    ve = polish_videoeditor(soft, bgr)
    tri = apply_quality_pass(soft, seed=soft, sharp_edges=False, frame_bgr=bgr)

    # Far BG: Videoeditor polish must kill bleed better than soft trimap
    assert float(ve[3, 3]) <= float(tri[3, 3]) + 0.02
    assert float(ve[3, 3]) < 0.05

    # Hair-hole region should be lifted (not stay near-zero speck)
    hole = float(ve[48:56, 56:68].mean())
    assert hole > 0.25, f"expected hair hole fill, got mean={hole:.3f}"

    # Soft mid-band (halo fog) should shrink
    soft_mid = float(((soft > 0.05) & (soft < 0.95)).mean())
    ve_mid = float(((ve > 0.05) & (ve < 0.95)).mean())
    assert ve_mid < soft_mid * 0.9


def test_max_polish_uses_videoeditor_when_sharp():
    eng = MaxQualityEngine()
    assert eng.sharp_edges is True
    bgr, soft = _soft_seed(96, 96)
    # Inject via stubbing base alpha
    eng._base_alpha = lambda _b: soft  # type: ignore[method-assign]
    eng._seed = None
    out = eng._polish(bgr, warmup=False)
    assert float(out[2, 2]) < 0.08
    assert float(out[48, 48]) > 0.7


def test_sharp_cutout_encodes_png_not_jpeg():
    bgr, alpha = _soft_seed(64, 64)
    alpha = (alpha > 0.5).astype(np.float32)
    jpg_field, _, _, _, _, empty = encode_preview_pair(bgr, alpha, sharp_cutout=True)
    assert empty is False
    raw = base64.b64decode(jpg_field)
    # PNG magic
    assert raw[:8] == b"\x89PNG\r\n\x1a\n"
    soft_jpg, _, _, _, _, _ = encode_preview_pair(bgr, alpha, sharp_cutout=False)
    raw_j = base64.b64decode(soft_jpg)
    assert raw_j[:2] == b"\xff\xd8"  # JPEG SOI


def test_resolve_rvm_prefers_resnet_for_quality(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("HYBRID_RVM_ONNX", raising=False)
    monkeypatch.delenv("VIDEOEDITOR_RVM_ONNX", raising=False)
    monkeypatch.delenv("HYBRID_MODELS_DIR", raising=False)
    monkeypatch.delenv("VIDEOEDITOR_MODELS", raising=False)
    monkeypatch.delenv("VIDEOEDITOR_MODELS_DIR", raising=False)

    import hybrid_editor.engines.fast_rvm as fr

    models = tmp_path / "models"
    models.mkdir()
    mob = models / "rvm_mobilenetv3_fp32.onnx"
    res = models / "rvm_resnet50_fp16.onnx"
    mob.write_bytes(b"m")
    res.write_bytes(b"r")
    monkeypatch.setattr(fr, "ROOT", tmp_path)
    monkeypatch.setattr(fr, "parent_videoeditor_roots", lambda: [])

    assert resolve_rvm_onnx(prefer="fast") == mob
    assert resolve_rvm_onnx(prefer="quality") == res


def test_max_engine_defaults_sharp_and_quality_backbone():
    eng = MaxQualityEngine()
    assert eng.sharp_edges is True
    assert eng._fast._prefer_quality is True
    eng.set_sharp_edges(False)
    assert eng.sharp_edges is False


def test_session_sharp_edges_api():
    session = EditorSession()
    assert session.sharp_edges is True
    st = session.status()
    assert st["sharp_edges"] is True
    st2 = session.set_sharp_edges(False)
    assert st2["sharp_edges"] is False
    session.set_mode("max")
    assert isinstance(session.engine, MaxQualityEngine)
    assert session.engine.sharp_edges is False
    session.set_sharp_edges(True)
    assert session.engine.sharp_edges is True


def test_max_bake_writes_full_res_alpha(tmp_path: Path):
    eng = MaxQualityEngine()
    path = tmp_path / "clip.mp4"
    w, h = 320, 240
    writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"mp4v"), 10, (w, h))
    for i in range(4):
        frame = np.zeros((h, w, 3), np.uint8)
        frame[:] = (50, 80, 40)
        cv2.ellipse(frame, (w // 2 + i, h // 2), (60, 90), 0, 0, 360, (80, 110, 200), -1)
        writer.write(frame)
    writer.release()
    eng.open_media(path)
    out = tmp_path / "bake"
    res = eng.bake(out, max_frames=3)
    assert res.ok
    assert res.prores_mov and Path(res.prores_mov).is_file()
    assert Path(res.prores_mov).name.endswith("_full_nobg.mov")
    # Optional debug dumps stay off — full-res alpha lives in the MOV
    assert not (out / "alpha").exists() or not any((out / "alpha").glob("*.png"))
    assert res.bake_range and res.bake_range.get("full_res_alpha") is True


def test_sharp_edges_tighter_midband_than_soft_max_polish():
    """Max sharp (Videoeditor) mid-band must be tighter than soft trimap baseline."""
    from hybrid_editor.engines.videoeditor_polish import polish_videoeditor

    bgr, soft = _soft_seed(160, 160)
    soft = cv2.GaussianBlur(soft, (0, 0), sigmaX=5.0)
    sharp_eng = MaxQualityEngine()
    sharp_eng.set_sharp_edges(True)
    sharp_eng._base_alpha = lambda _b: soft.copy()  # type: ignore[method-assign]
    sharp_eng._seed = None
    sharp_out = sharp_eng._polish(bgr, warmup=False)

    soft_eng = MaxQualityEngine()
    soft_eng.set_sharp_edges(False)
    soft_eng._base_alpha = lambda _b: soft.copy()  # type: ignore[method-assign]
    soft_eng._seed = None
    soft_out = soft_eng._polish(bgr, warmup=False)

    sharp_mid = float(((sharp_out > 0.05) & (sharp_out < 0.95)).mean())
    soft_mid = float(((soft_out > 0.05) & (soft_out < 0.95)).mean())
    assert sharp_mid <= soft_mid * 0.98 + 0.01
    # Far corner BG cleaner on sharp path
    assert float(sharp_out[2, 2]) <= float(soft_out[2, 2]) + 0.03
    # Direct polish helper agrees with engine sharp path
    ve = polish_videoeditor(soft, bgr)
    assert float(ve[2, 2]) < 0.08
