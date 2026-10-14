"""UI contracts for nobg result card + stamp ``2026-10-11-ai-tracks``."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
APP = ROOT / "frontend" / "src" / "App.tsx"
CSS = ROOT / "frontend" / "src" / "styles" / "app.css"
SYNC = ROOT / "SYNC_VERSION.txt"
README = ROOT / "README.md"
HTML = ROOT / "frontend" / "index.html"


def test_sync_stamp_concat_flow():
    assert SYNC.read_text(encoding="utf-8").strip() == "2026-10-14-restore-rvm-fast"


def test_app_result_card_and_explorer():
    text = APP.read_text(encoding="utf-8")
    assert "export-result" in text
    assert "Átlátszó nobg kész" in text
    assert "Megnyitás Explorerben" in text
    assert "nobg-player" in text
    assert "/api/bake/preview.mp4" in text
    assert "bakePreviewKey" in text
    # Progress only while running — flip to result card when done
    assert "{status?.bake_running ? (" in text or "status?.bake_running ?" in text
    assert "bake_running || (status?.bake_progress" not in text
    assert "{!status?.bake_running && status?.last_bake ? (" in text
    # Mux failure surfaces error, not silent alpha folder success
    assert "Export sikertelen" in text
    assert "FFMPEG_PATH" in text
    # Dense intel strip trimmed — no always-on Prefetch / Proxy / Hang / Ollama chips
    assert 'label: `Előtöltés' not in text
    assert 'label: hot > 0 ? `Proxy HOT' not in text
    assert "Ollama ✓" not in text  # Ollama folded into Részletek, not chip strip
    # Compact chip labels + apex Max copy
    assert 'label: status?.mode === "max" ? "Max" : "Gyors"' in text
    assert "APEX polish" in text or "apex polish" in text
    # CapCut-simple one-click flow (peak-ui copy)
    assert "Megnyitás → Cutout → Export" in text or "Megnyitás → Előnézet Cutout → Export" in text
    assert "flow-steps" in text
    assert "flow-num" in text
    assert "1 · Megnyitás" in text
    assert "2 · Előnézet" in text or "2 · Előnézet Cutout" in text
    assert "3 · Exportálás" in text
    # ETA on Gyors/Max mode cards + slim Be/Ki strip (no duplicate eta-pair cards in rail)
    assert "export-eta" in text
    assert "eta-pair" not in text  # decluttered — ETA lives on ModeSwitcher
    assert "Hátravan" in text
    assert "bothModeEtas" in text
    assert "Be/Ki" in text
    assert "eta-long-warn" in text
    assert "timeline-dock" in text
    assert "gpu-chip" in text
    assert "preview-ready" in text
    # Full-bleed empty shell (no skinny centered marketing column)
    assert "app empty" in text
    assert "concat-home" in text
    assert "empty-cta-row" in text
    assert "empty-workspace" in text
    assert "empty-drop" in text
    assert "hero-inner" not in text
    # Tech chips folded under Részletek (RVM not in intel strip)
    assert "intelFromPreview" in text
    assert "rvmChip(status)" not in text.split("function intelFromPreview")[1].split("function smartStatusLine")[0]


def test_css_result_and_checker_motion():
    css = CSS.read_text(encoding="utf-8")
    assert ".export-result" in css
    assert ".nobg-player" in css
    assert "@keyframes result-in" in css
    assert "@keyframes bake-shimmer" in css
    assert "@keyframes mode-pick" in css
    assert "@keyframes preview-load" in css
    assert ".meta-fold" in css
    assert "--checker-a: #1a2420" in css
    assert ".flow-steps" in css
    assert "@keyframes cta-glow" in css
    assert "--accent: #ff7a1a" in css
    assert "--accent-2: #c8f000" in css or "--accent-2: #b8f000" in css
    assert "Sora" in css
    assert "DM Sans" in css
    assert ".eta-pair" in css  # retained (hidden) for contract / reuse
    assert ".export-eta" in css
    assert ".mode-eta" in css
    assert "peak-ui" in css
    # layout-fix retained: no 1fr intel void; preview fills; timeline dock
    assert "intel-strip" in css
    assert "timeline-dock" in css
    assert "gpu-chip" in css
    assert "THREE children" in css or "intel-strip" in css
    assert "grid-template-rows: auto 1fr" in css
    assert "height: 100vh" in css
    assert "minmax(250px, 280px)" in css or "250px" in css
    # look2: full-bleed empty — no min(720px) marketing column
    assert ".empty-cta-row" in css
    assert ".empty-workspace" in css
    assert ".empty-drop" in css
    assert "min(720px" not in css
    assert (
        "person-restore" in css
        or "auto-person" in css
        or "person-fix2" in css
        or "look-peak" in css
        or "ai-tracks" in css
        or "peak-ui" in css
        or "peak-cutout" in css
    )
    assert "@keyframes playhead-glow" in css
    assert "@keyframes stage-focus" in css
    assert "--ink-tl" in css
    # Concat-flow: Forrás/Cutout/Maszk fill stage (not tiny intrinsic proxy)
    assert "place-items: stretch" in css
    assert ".clip-add-row" in css


def test_fonts_loaded():
    html = HTML.read_text(encoding="utf-8")
    assert "Sora" in html
    assert "DM+Sans" in html or "DM Sans" in html


def test_readme_mentions_concat_flow_stamp():
    readme = README.read_text(encoding="utf-8")
    assert "2026-10-11-cuda-restore" in readme or "2026-10-11-paint-face" in readme
    assert "2026-10-11-concat-look" in readme  # prior retained
    assert "2026-10-10-look2" in readme  # prior retained in history
    assert "2026-10-10-layout-fix" in readme
