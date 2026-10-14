"""restore-rvm-fast2 — honest Max CPU ETA + light bake (no heavy polish default)."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parents[1]
ROOT = BACKEND.parent
sys.path.insert(0, str(BACKEND))

STAMP = "2026-10-14-restore-rvm-fast2"


def test_stamp_fast2():
    assert (ROOT / "SYNC_VERSION.txt").read_text(encoding="utf-8").strip() == STAMP
    assert (ROOT / "backend/hybrid_editor/FEATURE_RESTORE_RVM_FAST2.txt").read_text(
        encoding="utf-8"
    ).strip() == STAMP


def test_cpu_max_bake_long_default_640(monkeypatch: pytest.MonkeyPatch):
    from hybrid_editor.engines.max_quality import MaxQualityEngine

    monkeypatch.delenv("HYBRID_CPU_MAX_LONG", raising=False)
    assert MaxQualityEngine._cpu_max_bake_long() == 640
    monkeypatch.setenv("HYBRID_CPU_MAX_LONG", "720")
    assert MaxQualityEngine._cpu_max_bake_long() == 720
    monkeypatch.setenv("HYBRID_CPU_MAX_LONG", "480")
    assert MaxQualityEngine._cpu_max_bake_long() == 480


def test_cpu_max_heavy_polish_default_off(monkeypatch: pytest.MonkeyPatch):
    from hybrid_editor.engines.max_quality import MaxQualityEngine

    monkeypatch.delenv("HYBRID_CPU_MAX_HEAVY_POLISH", raising=False)
    assert MaxQualityEngine._cpu_max_heavy_polish() is False
    monkeypatch.setenv("HYBRID_CPU_MAX_HEAVY_POLISH", "1")
    assert MaxQualityEngine._cpu_max_heavy_polish() is True


def test_eta_cpu_max_honest_not_49s():
    from hybrid_editor.eta import estimate_bake_sec

    # 10s @ 24fps 1080p — old chip ~49s lied vs ~4 min wall (polish@720).
    # Light path ETA should land ~2–3 perc class (not 49s, not 15 min).
    cuda = estimate_bake_sec(10.0, 24.0, 1920, 1080, "max", cpu_ort=False)
    cpu = estimate_bake_sec(10.0, 24.0, 1920, 1080, "max", cpu_ort=True)
    assert 35 <= cuda <= 55
    assert cpu >= 90  # must not claim ~49s again
    assert cpu <= 240  # light path model ~2–3.5 perc (not old 4+ min heavy)
    # Measured heavy was ~240s; model must not pretend near-CUDA.
    assert cpu / cuda >= 2.0


def test_remaining_trusts_observed_early():
    from hybrid_editor.eta import remaining_bake_sec

    # 31/240 at ~1s/frame observed — remaining must be ~3+ perc, not model lie.
    rem = remaining_bake_sec(
        duration_sec=10.0,
        fps=24.0,
        width=1920,
        height=1080,
        mode="max",
        bake_progress=0.13,
        bake_status="CPU Max~640 31/240 frame",
        cpu_ort=True,
        elapsed_sec=31.0,  # ~1s/frame observed
    )
    assert rem >= 150  # ~209 frames left * ~1s
    assert rem <= 280


def test_source_mentions_light_path():
    mq = (ROOT / "backend/hybrid_editor/engines/max_quality.py").read_text(encoding="utf-8")
    assert "_cpu_max_heavy_polish" in mq
    assert "HYBRID_CPU_MAX_HEAVY_POLISH" in mq
    assert "light_cpu" in mq
    eta = (ROOT / "frontend/src/lib/eta.ts").read_text(encoding="utf-8")
    assert "CPU_MAX_SPF_MULT = 3.5" in eta


def test_ascii_paste_fast2():
    for name in (
        "PASTE_RESTORE_RVM_FAST2_GITHUB.ps1",
        "PASTE_RESTORE_RVM_FAST2_INSTALL.ps1",
    ):
        p = ROOT / name
        assert p.is_file(), name
        raw = p.read_bytes()
        assert all(b < 128 for b in raw), name
        text = p.read_text(encoding="utf-8")
        assert STAMP in text
        assert "cursor/restore-rvm-fast2-b680" in text
