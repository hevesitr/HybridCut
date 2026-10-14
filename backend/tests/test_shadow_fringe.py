"""BG residue strips/blotches on soft cutout — protocol + minimal fix.

User visual (not mere dark-premult guess):
- light greenish-grey BG strip on hair edge
- irregular light BG blotch on face side
- checkerboard elsewhere (not total α failure)
- BOTH people must remain
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import cv2
import numpy as np
import pytest

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

STAMP = "2026-10-14-fix-shadow-fringe-fast2"


def _two_people_with_bg_residue(
    h: int = 160, w: int = 240
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Light greenish-grey plate + two people + soft mid-α BG strip/blotch."""
    bg = (168, 175, 162)  # BGR light greenish-grey
    bgr = np.full((h, w, 3), bg, np.uint8)
    fgr = np.full((h, w, 3), bg, np.uint8)
    a = np.zeros((h, w), np.float32)

    # Person L (blonde-ish) + Person R (brunette-ish)
    people = [
        ((int(w * 0.32), int(h * 0.52)), (28, 48), (210, 190, 160), (70, 90, 140)),
        ((int(w * 0.68), int(h * 0.55)), (30, 50), (90, 70, 50), (40, 50, 80)),
    ]
    for (cx, cy), (rx, ry), skin, hair in people:
        cv2.ellipse(bgr, (cx, cy), (rx, ry), 0, 0, 360, skin, -1)
        cv2.ellipse(bgr, (cx, cy - ry // 2), (rx - 4, ry // 3), 0, 0, 360, hair, -1)
        cv2.ellipse(fgr, (cx, cy), (rx + 2, ry + 2), 0, 0, 360, skin, -1)
        cv2.ellipse(fgr, (cx, cy - ry // 2), (rx - 2, ry // 3 + 2), 0, 0, 360, hair, -1)
        cv2.ellipse(a, (cx, cy), (rx, ry), 0, 0, 360, 1.0, -1)
        cv2.ellipse(a, (cx, cy - ry // 2), (rx - 4, ry // 3), 0, 0, 360, 1.0, -1)

    # Soft person α (preserves hair band) then paint BG-colored mid-α leftovers
    a = cv2.GaussianBlur(a, (0, 0), sigmaX=2.2)

    # Blonde RIGHT hair edge: light BG strip (mid α, BG RGB)
    x0, x1 = int(w * 0.40), int(w * 0.48)
    y0, y1 = int(h * 0.28), int(h * 0.48)
    a[y0:y1, x0:x1] = np.maximum(a[y0:y1, x0:x1], 0.42)
    bgr[y0:y1, x0:x1] = bg
    # FGR decontaminated — person hair color, not plate
    fgr[y0:y1, x0:x1] = (70, 90, 140)

    # Brunette face side: larger irregular blotch
    blotch = np.zeros((h, w), np.uint8)
    cv2.ellipse(blotch, (int(w * 0.55), int(h * 0.50)), (22, 18), 25, 0, 360, 255, -1)
    # Only keep blotch outside solid brunette core
    a[blotch > 0] = np.maximum(a[blotch > 0], 0.38)
    bgr[blotch > 0] = bg
    fgr[blotch > 0] = (90, 70, 50)

    return bgr, a, fgr


def test_protocol_raw_alpha_too_high_in_bg_rois():
    """Step 2: residue ROIs have elevated raw α (not a pure premul story)."""
    from hybrid_editor.diag_shadow_fringe import bg_residue_mask

    bgr, a, _fgr = _two_people_with_bg_residue()
    mask, stats = bg_residue_mask(bgr, a)
    assert stats["residue_cover"] >= 0.004
    assert stats["residue_mean_alpha"] >= 0.28
    assert stats["raw_alpha_too_high_in_bg"] is True
    assert mask.any()


def test_suppress_bg_residue_keeps_two_people():
    from hybrid_editor.engines.videoeditor_polish import suppress_bg_color_residue

    bgr, a, _fgr = _two_people_with_bg_residue()
    out = suppress_bg_color_residue(a, bgr, strength=0.85)
    # Two solid cores survive
    hard = (out >= 0.55).astype(np.uint8) * 255
    n, _labels, stats, _ = cv2.connectedComponentsWithStats(hard, connectivity=8)
    areas = sorted(
        [int(stats[i, cv2.CC_STAT_AREA]) for i in range(1, n)], reverse=True
    )
    assert len(areas) >= 2
    assert areas[1] >= max(40, int(areas[0] * 0.10))
    # Residue cover drops
    from hybrid_editor.diag_shadow_fringe import bg_residue_mask

    _m0, s0 = bg_residue_mask(bgr, a)
    _m1, s1 = bg_residue_mask(bgr, out)
    assert s1["residue_cover"] < s0["residue_cover"] * 0.65


def test_fgr_plus_residue_cleaner_than_source_on_magenta():
    """Acceptance proxy: used FG on magenta shows less BG plate than source×α."""
    from hybrid_editor.diag_shadow_fringe import (
        bg_residue_mask,
        composite_over_solid,
    )
    from hybrid_editor.engines.peak_cutout import cutout_rgb_for_alpha
    from hybrid_editor.engines.videoeditor_polish import suppress_bg_color_residue

    bgr, a, fgr = _two_people_with_bg_residue()
    a2 = suppress_bg_color_residue(a, bgr)
    used = cutout_rgb_for_alpha(bgr, a2, fgr, mix=0.9, decontaminate=0.55)
    mag = (255, 0, 255)
    before = composite_over_solid(bgr, a, mag).astype(np.float32)
    after = composite_over_solid(used, a2, mag).astype(np.float32)
    # Residue ROI: before should be closer to plate grey; after closer to magenta or person
    mask, _ = bg_residue_mask(bgr, a)
    assert mask.any()
    bg = np.array([168, 175, 162], np.float32)
    dist_before = np.sqrt(((before[mask] - bg) ** 2).sum(axis=1)).mean()
    dist_after = np.sqrt(((after[mask] - bg) ** 2).sum(axis=1)).mean()
    assert dist_after > dist_before + 8.0


def test_diag_dump_magenta_and_hint(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("HYBRID_DIAG_SHADOW", "1")
    monkeypatch.setenv("HYBRID_DIAG_DIR", str(tmp_path))
    from hybrid_editor.diag_shadow_fringe import dump_shadow_fringe_frame

    bgr, a, fgr = _two_people_with_bg_residue()
    out = dump_shadow_fringe_frame(
        tag="unit_two",
        t_sec=0.5,
        src_bgr=bgr,
        raw_alpha=a,
        post_alpha=None,
        fgr_bgr=fgr,
        fg_used_bgr=fgr,
    )
    assert out is not None
    metrics = json.loads((out / "metrics.json").read_text(encoding="utf-8"))
    assert metrics["birth_site_hint"] == "raw_alpha_bg_residue"
    assert (out / "07_comp_src_on_magenta.png").is_file()
    assert (out / "14_bg_residue_mask.png").is_file()


def test_fast_engine_pipeline_reduces_residue(monkeypatch: pytest.MonkeyPatch):
    from hybrid_editor.diag_shadow_fringe import bg_residue_mask
    from hybrid_editor.engines.fast_rvm import FastEngine

    bgr, a, fgr = _two_people_with_bg_residue(120, 180)
    eng = FastEngine(prefer_quality=False)
    eng._rvm = type(
        "R",
        (),
        {
            "last_fgr_bgr": fgr,
            "provider": "CPUExecutionProvider",
            "_uses_cuda": False,
            "matte": lambda *a, **k: a,  # unused
        },
    )()
    cleaned = eng._soft_bg_residue(bgr, a)  # noqa: SLF001
    cut = eng._cutout_bgr(bgr, cleaned)  # noqa: SLF001
    _m0, s0 = bg_residue_mask(bgr, a)
    _m1, s1 = bg_residue_mask(bgr, cleaned)
    assert s1["residue_cover"] < s0["residue_cover"]
    soft = (cleaned > 0.12) & (cleaned < 0.88)
    assert float(cut[soft][:, 2].mean()) != float(bgr[soft][:, 2].mean()) or soft.sum() == 0


def test_no_keep_largest_only():
    """Two similar-sized cores both survive color residue pass."""
    from hybrid_editor.engines.videoeditor_polish import suppress_bg_color_residue

    bgr, a, _ = _two_people_with_bg_residue()
    out = suppress_bg_color_residue(a, bgr)
    hard = (out >= 0.55).astype(np.uint8)
    n, _, stats, _ = cv2.connectedComponentsWithStats(hard, connectivity=8)
    big = sorted(int(stats[i, cv2.CC_STAT_AREA]) for i in range(1, n))
    assert len(big) >= 2


def test_stamp_file():
    root = BACKEND.parent
    assert (root / "SYNC_VERSION.txt").read_text(encoding="utf-8").strip() == STAMP
    feat = root / "backend/hybrid_editor/FEATURE_FIX_SHADOW_FRINGE.txt"
    assert feat.is_file()
    assert feat.read_text(encoding="utf-8").strip() == STAMP
