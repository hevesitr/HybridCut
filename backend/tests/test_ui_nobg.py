"""UI contracts for nobg result card + stamp ``2026-10-10-eta-ui``."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
APP = ROOT / "frontend" / "src" / "App.tsx"
CSS = ROOT / "frontend" / "src" / "styles" / "app.css"
SYNC = ROOT / "SYNC_VERSION.txt"
README = ROOT / "README.md"


def test_sync_stamp_eta_ui():
    assert SYNC.read_text(encoding="utf-8").strip() == "2026-10-10-eta-ui"


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
    # CapCut-simple one-click flow
    assert "Megnyitás → auto Cutout → Exportálás" in text
    assert "flow-steps" in text
    # Upfront Gyors + Max ETA
    assert "export-eta" in text
    assert "eta-pair" in text
    assert "Hátravan" in text
    assert "bothModeEtas" in text
    # Tech chips folded under Részletek (RVM not in intel strip)
    assert "intelFromPreview" in text
    assert "rvmChip(status)" not in text.split("function intelFromPreview")[1].split("function smartStatusLine")[0]


def test_css_result_and_checker_motion():
    css = CSS.read_text(encoding="utf-8")
    assert ".export-result" in css
    assert ".nobg-player" in css
    assert "@keyframes result-in" in css
    assert "@keyframes bake-shimmer" in css
    assert ".meta-fold" in css
    assert "--checker-a: #1a2420" in css
    assert ".flow-steps" in css
    assert "@keyframes cta-glow" in css
    assert "--accent: #ff7a1a" in css
    assert "--accent-2: #b8f000" in css
    assert "Sora" in css
    assert "Manrope" in css
    assert ".eta-pair" in css
    assert ".export-eta" in css
    assert ".mode-eta" in css


def test_readme_mentions_eta_ui_stamp():
    readme = README.read_text(encoding="utf-8")
    assert "2026-10-10-eta-ui" in readme
