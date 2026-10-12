"""simple-bg5 — CPU Max bake uses MobileNet@~720 so ETA ~43s is real."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parents[1]
ROOT = BACKEND.parent
sys.path.insert(0, str(BACKEND))

STAMP = "2026-10-12-simple-bg5"


def test_stamp_simple_bg5():
    assert (ROOT / "SYNC_VERSION.txt").read_text(encoding="utf-8").strip() == STAMP


def test_cpu_max_fast_flag(monkeypatch: pytest.MonkeyPatch):
    from hybrid_editor.engines.max_quality import MaxQualityEngine

    monkeypatch.setenv("HYBRID_ORT_PROVIDER", "cpu")
    eng = MaxQualityEngine()
    eng._fast._rvm = None  # noqa: SLF001
    assert eng._on_cpu_ort()
    assert eng._cpu_max_fast_enabled()
    monkeypatch.setenv("HYBRID_CPU_MAX_FULLRES", "1")
    assert not eng._cpu_max_fast_enabled()


def test_eta_cpu_max_near_cuda_not_15min():
    from hybrid_editor.eta import estimate_bake_sec

    # 10s @ 24fps 1080p — CUDA Max ~43s; CPU Max fast-path ~1.15x (not ~15 min)
    cuda = estimate_bake_sec(10.0, 24.0, 1920, 1080, "max", cpu_ort=False)
    cpu = estimate_bake_sec(10.0, 24.0, 1920, 1080, "max", cpu_ort=True)
    assert 35 <= cuda <= 55
    assert cpu < 90
    assert cpu / cuda < 1.4
    # Old broken expectation: full-res CPU ~15 min
    assert cpu < 600


def test_source_mentions_cpu_max_fast():
    mq = (ROOT / "backend/hybrid_editor/engines/max_quality.py").read_text(encoding="utf-8")
    assert "_cpu_max_fast_enabled" in mq
    assert "HYBRID_CPU_MAX_LONG" in mq
    assert "CPU Max bake fast-path" in mq
    eta = (ROOT / "frontend/src/lib/eta.ts").read_text(encoding="utf-8")
    assert "cpuOrt" in eta
