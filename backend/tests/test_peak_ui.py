"""peak-ui — chrome stamp + Gyors preview matte boost."""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

BACKEND = Path(__file__).resolve().parents[1]
ROOT = BACKEND.parent
sys.path.insert(0, str(BACKEND))

STAMP = "2026-10-13-peak-ui"
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

    a = np.zeros((80, 80), np.float32)
    a[20:60, 20:60] = 0.42  # soft person
    a[10:14, 10:40] = 0.22  # detached fog
    out = preview_boost_person_alpha(a)
    assert float(out[40, 40]) > float(a[40, 40])
    assert float(out[12, 20]) < float(a[12, 20]) + 0.01
