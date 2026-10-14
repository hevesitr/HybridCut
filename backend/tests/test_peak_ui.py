"""peak-ui — chrome stamp + Gyors preview matte boost."""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

BACKEND = Path(__file__).resolve().parents[1]
ROOT = BACKEND.parent
sys.path.insert(0, str(BACKEND))

STAMP = "2026-10-14-restore-rvm-fast"
SYNC = ROOT / "SYNC_VERSION.txt"
FEATURE = ROOT / "backend" / "hybrid_editor" / "FEATURE_PEAK_UI.txt"
PASTE = ROOT / "PASTE_PEAK_UI_INSTALL.ps1"
CSS = ROOT / "frontend" / "src" / "styles" / "app.css"
APP = ROOT / "frontend" / "src" / "App.tsx"
HTML = ROOT / "frontend" / "index.html"


def test_stamp_and_ui_chrome():
    assert SYNC.read_text(encoding="utf-8").strip() == STAMP
    assert FEATURE.read_text(encoding="utf-8").strip() == STAMP
    assert PASTE.is_file()
    paste = PASTE.read_text(encoding="utf-8")
    assert STAMP in paste
    assert "start_hybrid_cuda.ps1" in paste
    css = CSS.read_text(encoding="utf-8")
    assert STAMP in css
    assert "Sora" in css or "DM Sans" in css
    assert "peak-ui" in css
    html = HTML.read_text(encoding="utf-8")
    assert "Sora" in html and "DM+Sans" in html
    app = APP.read_text(encoding="utf-8")
    assert "peak-ui" in app
    assert "brand-sub" in app
    assert "AI sáv" not in app
    assert "+ V1 klip" not in app
    assert "+ B-roll" not in app


def test_preview_boost_person_alpha():
    from hybrid_editor.engines.peak_cutout import preview_boost_person_alpha

    a = np.zeros((120, 120), np.float32)
    a[40:90, 40:90] = 0.42  # soft person
    a[2:8, 2:12] = 0.18  # far corner fog
    out = preview_boost_person_alpha(a)
    assert float(out[60, 60]) > float(a[60, 60])
    assert float(out[4, 5]) < float(a[4, 5]) * 0.6
