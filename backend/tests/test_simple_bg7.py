"""simple-bg7 — CUDA stick + honest ETA path + CPU_MAX polish."""

from __future__ import annotations

import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
ROOT = BACKEND.parent
sys.path.insert(0, str(BACKEND))

STAMP = "2026-10-13-simple-bg7"
SYNC = ROOT / "SYNC_VERSION.txt"
START = ROOT / "start_hybrid_cuda.ps1"
RUN = ROOT / "run_hybrid.ps1"
PASTE = ROOT / "PASTE_SIMPLE_BG7_INSTALL.ps1"
APP = ROOT / "frontend" / "src" / "App.tsx"
MODE = ROOT / "frontend" / "src" / "components" / "ModeSwitcher.tsx"
CUDA = ROOT / "backend" / "hybrid_editor" / "cuda_path.py"


def test_stamp_and_cuda_stick_scripts():
    assert SYNC.read_text(encoding="utf-8").strip() == STAMP
    start = START.read_text(encoding="utf-8")
    assert "ort_provider.txt" in start
    assert "probe_cuda_ep.py" in start
    run = RUN.read_text(encoding="utf-8")
    assert "ort_provider.txt" in run
    assert "re-probing CUDA EP" in run or "re-probe" in run.lower()
    paste = PASTE.read_text(encoding="utf-8")
    assert STAMP in paste
    assert "start_hybrid_cuda.ps1" in paste
    assert 'HYBRID_ORT_PROVIDER = "cpu"' not in paste


def test_ort_provider_inject_and_cpu_max_spec():
    from hybrid_editor.cuda_path import inject_ort_provider_dirs, inject_nvidia_pip_libs
    from hybrid_editor.engines.videoeditor_polish import CPU_MAX_SPEC, APEX_SPEC

    assert callable(inject_ort_provider_dirs)
    assert "inject_ort_provider_dirs" in CUDA.read_text(encoding="utf-8")
    assert CPU_MAX_SPEC.residual_halo_px < APEX_SPEC.residual_halo_px
    # Smoke: never raises
    inject_nvidia_pip_libs()


def test_ui_path_label():
    app = APP.read_text(encoding="utf-8")
    assert "pathLabel" in app
    assert "liveCudaEp" in app
    mode = MODE.read_text(encoding="utf-8")
    assert "pathLabel" in mode
    assert "CUDA" in mode and "CPU" in mode
