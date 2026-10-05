"""UI contracts for nobg result card + stamp ``2026-10-05-ui-nobg``."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
APP = ROOT / "frontend" / "src" / "App.tsx"
CSS = ROOT / "frontend" / "src" / "styles" / "app.css"
SYNC = ROOT / "SYNC_VERSION.txt"
README = ROOT / "README.md"


def test_sync_stamp_ui_nobg():
    assert SYNC.read_text(encoding="utf-8").strip() == "2026-10-05-ui-nobg"


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
    # Dense intel strip trimmed — no always-on Prefetch / Proxy / Hang chips
    assert 'label: `Előtöltés' not in text
    assert 'label: hot > 0 ? `Proxy HOT' not in text


def test_css_result_and_checker_motion():
    css = CSS.read_text(encoding="utf-8")
    assert ".export-result" in css
    assert ".nobg-player" in css
    assert "@keyframes result-in" in css
    assert "@keyframes bake-shimmer" in css
    assert ".meta-fold" in css
    assert "--checker-a: #1a2420" in css


def test_readme_mentions_ui_nobg():
    readme = README.read_text(encoding="utf-8")
    assert "2026-10-05-ui-nobg" in readme
