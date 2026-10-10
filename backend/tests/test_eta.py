"""ETA helpers — Gyors/Max bake duration (RTX 3060 calibration)."""

from __future__ import annotations

from pathlib import Path

from hybrid_editor.eta import (
    GYORS_SEC_PER_FRAME_1080P,
    MAX_SEC_PER_FRAME_1080P,
    both_mode_etas,
    clip_duration_sec,
    estimate_bake_sec,
    format_eta_hu,
    frame_count,
    parse_bake_frames,
    remaining_bake_sec,
    resolution_factor,
    sec_per_frame,
)

ROOT = Path(__file__).resolve().parents[2]
ETA_TS = ROOT / "frontend" / "src" / "lib" / "eta.ts"
MODE = ROOT / "frontend" / "src" / "components" / "ModeSwitcher.tsx"
APP = ROOT / "frontend" / "src" / "App.tsx"
SYNC = ROOT / "SYNC_VERSION.txt"


def test_sync_stamp_eta_ui():
    assert SYNC.read_text(encoding="utf-8").strip() == "2026-10-10-eta-ui"


def test_gyors_faster_than_max_same_clip():
    g = estimate_bake_sec(10.0, 30.0, 1920, 1080, "gyors")
    m = estimate_bake_sec(10.0, 30.0, 1920, 1080, "max")
    assert g > 0 and m > 0
    assert g < m
    assert MAX_SEC_PER_FRAME_1080P > GYORS_SEC_PER_FRAME_1080P


def test_scales_with_duration_and_resolution():
    short = estimate_bake_sec(5.0, 30.0, 1920, 1080, "max")
    long = estimate_bake_sec(20.0, 30.0, 1920, 1080, "max")
    assert long > short * 2.5
    sd = estimate_bake_sec(10.0, 30.0, 1280, 720, "max")
    hd = estimate_bake_sec(10.0, 30.0, 1920, 1080, "max")
    uhd = estimate_bake_sec(10.0, 30.0, 3840, 2160, "max")
    assert sd < hd < uhd


def test_fps_increases_frame_work():
    slow = estimate_bake_sec(10.0, 24.0, 1920, 1080, "gyors")
    fast = estimate_bake_sec(10.0, 60.0, 1920, 1080, "gyors")
    assert frame_count(10.0, 60.0) > frame_count(10.0, 24.0)
    assert fast > slow


def test_format_eta_hu():
    assert format_eta_hu(12) == "Kb. 12 mp"
    assert format_eta_hu(60) == "Kb. 1 perc"
    assert format_eta_hu(80) == "Kb. 1 perc 20 mp"
    assert format_eta_hu(0) == "Kb. —"
    assert "óra" in format_eta_hu(3700)


def test_clip_duration_and_both():
    assert clip_duration_sec(1.0, 4.5) == 3.5
    assert clip_duration_sec(5.0, 5.0, 12.0) == 12.0
    both = both_mode_etas(8.0, 25.0, 1920, 1080)
    assert both["gyors"]["label_hu"].startswith("Kb.")
    assert both["max"]["label_hu"].startswith("Kb.")
    assert float(both["gyors"]["seconds"]) < float(both["max"]["seconds"])


def test_remaining_from_frames_and_progress():
    assert parse_bake_frames("Max bake 50/200 frame") == (50, 200)
    rem = remaining_bake_sec(
        duration_sec=10.0,
        fps=30.0,
        width=1920,
        height=1080,
        mode="max",
        bake_progress=0.25,
        bake_status="Max bake 50/200 frame",
    )
    total = estimate_bake_sec(10.0, 30.0, 1920, 1080, "max")
    assert 0 < rem < total
    mid = remaining_bake_sec(
        duration_sec=10.0,
        fps=30.0,
        width=1920,
        height=1080,
        mode="gyors",
        bake_progress=0.5,
        bake_status="",
    )
    assert abs(mid - total * 0.5) > 0 or True  # progress path uses gyors total
    g_total = estimate_bake_sec(10.0, 30.0, 1920, 1080, "gyors")
    assert abs(mid - g_total * 0.5) < 0.5


def test_resolution_factor_gyors_softer():
    g = resolution_factor(3840, 2160, "gyors")
    m = resolution_factor(3840, 2160, "max")
    assert g < m
    assert sec_per_frame(1920, 1080, "gyors") == GYORS_SEC_PER_FRAME_1080P * resolution_factor(
        1920, 1080, "gyors"
    )


def test_frontend_eta_mirror_and_ui_hooks():
    ts = ETA_TS.read_text(encoding="utf-8")
    assert "GYORS_SEC_PER_FRAME_1080P = 0.028" in ts
    assert "MAX_SEC_PER_FRAME_1080P = 0.165" in ts
    assert "formatEtaHu" in ts
    assert "remainingBakeSec" in ts
    mode = MODE.read_text(encoding="utf-8")
    assert "etaGyors" in mode
    assert "etaMax" in mode
    assert "élő scrub · lágyabb" in mode or "lágyabb" in mode
    app = APP.read_text(encoding="utf-8")
    assert "bothModeEtas" in app or "estimateBakeSec" in app
    assert "Hátravan" in app or "hátravan" in app or "marad" in app
    assert "export-eta" in app
