"""Opt-in matte/export diagnostics — reversible helpers."""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))


def test_maszk_gyenge_gate_mirrors_frontend():
    from hybrid_editor.diag_matte import would_trigger_maszk_gyenge

    assert would_trigger_maszk_gyenge(
        "egyenletes/teljes-keret maszk (hibás RVM vagy 0–255 clip) — cover=0.99"
    )
    assert would_trigger_maszk_gyenge("bad 0-255 clip")
    assert not would_trigger_maszk_gyenge("gyenge/üres maszk — max=0.05")
    assert not would_trigger_maszk_gyenge(None)


def test_log_and_timer_off_by_default(monkeypatch, caplog):
    monkeypatch.delenv("HYBRID_DIAG_MATTE", raising=False)
    monkeypatch.delenv("HYBRID_DIAG_EXPORT_TIMING", raising=False)
    from hybrid_editor.diag_matte import ExportStageTimer, log_matte_trigger

    log_matte_trigger(
        where="test",
        t_sec=0.0,
        matte_error="egyenletes slab",
        matte_empty=True,
        recovered=False,
        alpha=np.ones((8, 8), np.float32),
    )
    t = ExportStageTimer("test")
    t.mark("a")
    assert t.finish() == {}


def test_log_fires_when_enabled(monkeypatch, caplog):
    import logging

    monkeypatch.setenv("HYBRID_DIAG_MATTE", "1")
    from hybrid_editor import diag_matte as dm

    with caplog.at_level(logging.WARNING, logger="hybrid_editor.diag_matte"):
        dm.log_matte_trigger(
            where="unit",
            t_sec=1.25,
            matte_error="egyenletes/teljes-keret maszk — cover=1.00",
            matte_empty=True,
            recovered=False,
            alpha=np.ones((16, 16), np.float32),
        )
    assert any("DIAG_MATTE_WEAK" in r.message for r in caplog.records)
