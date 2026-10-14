"""peak-cutout — guided upsample, flow temporal, RVM ds, fgr composite."""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest

BACKEND = Path(__file__).resolve().parents[1]
ROOT = BACKEND.parent
sys.path.insert(0, str(BACKEND))

STAMP = "2026-10-14-restore-rvm-fast2"
SYNC = ROOT / "SYNC_VERSION.txt"
FEATURE = ROOT / "backend" / "hybrid_editor" / "FEATURE_PEAK_CUTOUT.txt"
PASTE = ROOT / "PASTE_PEAK_CUTOUT_INSTALL.ps1"
MOD = ROOT / "backend" / "hybrid_editor" / "engines" / "peak_cutout.py"


def test_stamp_and_paste():
    assert SYNC.read_text(encoding="utf-8").strip() == STAMP
    assert FEATURE.read_text(encoding="utf-8").strip() == STAMP
    assert PASTE.is_file()
    paste = PASTE.read_text(encoding="utf-8")
    assert STAMP in paste
    assert "start_hybrid_cuda.ps1" in paste
    assert 'HYBRID_ORT_PROVIDER = "cpu"' not in paste
    assert MOD.is_file()


def test_rvm_auto_downsample_full_body():
    from hybrid_editor.engines.peak_cutout import rvm_auto_downsample_ratio

    ds = rvm_auto_downsample_ratio(1080, 1920, full_body=True, target_long=432)
    # Official full-body ~0.4 @1080; our bias near that band.
    assert 0.20 <= ds <= 0.55
    assert rvm_auto_downsample_ratio(480, 480) == 1.0


def test_guided_upsample_and_crisp():
    from hybrid_editor.engines.peak_cutout import guided_upsample_alpha, peak_edge_crisp

    lo = np.zeros((90, 160), np.float32)
    lo[20:70, 40:120] = 0.95
    lo[18:22, 40:120] = 0.35  # soft fringe
    guide = np.zeros((180, 320, 3), np.uint8)
    guide[:] = (40, 40, 40)
    guide[40:140, 80:240] = (160, 140, 120)
    up = guided_upsample_alpha(lo, guide, radius=3)
    assert up.shape == (180, 320)
    assert float(up[90, 160]) > 0.7
    crisp = peak_edge_crisp(up, strength=0.4)
    assert crisp.shape == up.shape
    assert float(crisp.max()) <= 1.0


def test_flow_temporal_smoother():
    from hybrid_editor.engines.peak_cutout import FlowTemporalSmoother

    sm = FlowTemporalSmoother(momentum=0.4)
    a0 = np.zeros((64, 64), np.float32)
    a0[16:48, 16:48] = 1.0
    bgr = np.zeros((64, 64, 3), np.uint8)
    bgr[16:48, 16:48] = 180
    o0 = sm.update(a0, bgr)
    assert float(o0[32, 32]) > 0.9
    a1 = np.roll(a0, shift=2, axis=1)
    bgr1 = np.roll(bgr, shift=2, axis=1)
    o1 = sm.update(a1, bgr1)
    assert o1.shape == a1.shape
    assert 0.0 <= float(o1.mean()) <= 1.0


def test_composite_with_fgr():
    from hybrid_editor.engines.peak_cutout import composite_with_fgr

    bgr = np.full((32, 32, 3), 80, np.uint8)
    fgr = np.full((32, 32, 3), 200, np.uint8)
    a = np.zeros((32, 32), np.float32)
    a[8:24, 8:24] = 0.5
    out = composite_with_fgr(bgr, a, fgr, mix=0.8)
    assert out.shape == bgr.shape
    # Edge band should pull toward fgr (brighter than source 80).
    assert int(out[16, 16].mean()) > 100
