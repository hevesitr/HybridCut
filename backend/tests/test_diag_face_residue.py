"""Face-residue diagnostic helpers — no GPU required."""

from __future__ import annotations

import sys
from pathlib import Path

import cv2
import numpy as np

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))


def _face_fog_frame(h: int = 180, w: int = 260):
    """Two people + high mid-α grey-green fog in front of face (core-eligible)."""
    bg = (168, 175, 162)
    bgr = np.full((h, w, 3), bg, np.uint8)
    a = np.zeros((h, w), np.float32)
    # Two solid people
    for cx, cy, rx, ry, skin in (
        (int(w * 0.32), int(h * 0.55), 28, 50, (210, 190, 160)),
        (int(w * 0.68), int(h * 0.55), 30, 52, (90, 70, 50)),
    ):
        cv2.ellipse(bgr, (cx, cy), (rx, ry), 0, 0, 360, skin, -1)
        cv2.ellipse(a, (cx, cy), (rx, ry), 0, 0, 360, 1.0, -1)
    a = cv2.GaussianBlur(a, (0, 0), sigmaX=1.5)
    # Face-front fog: α=0.65 (above hard_thresh 0.55) + plate color — large blotch
    cv2.ellipse(bgr, (int(w * 0.68), int(h * 0.42)), (18, 14), 0, 0, 360, bg, -1)
    cv2.ellipse(a, (int(w * 0.68), int(h * 0.42)), (18, 14), 0, 0, 360, 0.65, -1)
    # Under-chin softer fog α=0.40
    cv2.ellipse(bgr, (int(w * 0.68), int(h * 0.62)), (20, 10), 0, 0, 360, bg, -1)
    cv2.ellipse(a, (int(w * 0.68), int(h * 0.62)), (20, 10), 0, 0, 360, 0.40, -1)
    return bgr, a


def test_high_alpha_face_fog_blocked_by_core():
    """Document gate: α>=hard_thresh BG fog is classified as core → suppress skips."""
    from hybrid_editor.diag_face_residue import roi_stats
    from hybrid_editor.engines.videoeditor_polish import suppress_bg_color_residue

    bgr, a = _face_fog_frame()
    face = (int(bgr.shape[1] * 0.55), int(bgr.shape[0] * 0.30), int(bgr.shape[1] * 0.85), int(bgr.shape[0] * 0.52))
    before = roi_stats(a, bgr, face)
    out = suppress_bg_color_residue(a, bgr)
    after = roi_stats(out, bgr, face)
    # Fog is in/near hard core — suppress must not wipe person, and face mean α stays high
    assert before["frac_hard_core"] > 0.05 or before["mid_bg_blocked_by_core_frac"] > 0.02
    assert after["mean_alpha"] > 0.20
    # Two people still present
    hard = (out >= 0.55).astype(np.uint8) * 255
    n, _l, st, _ = cv2.connectedComponentsWithStats(hard, connectivity=8)
    areas = sorted([int(st[i, cv2.CC_STAT_AREA]) for i in range(1, n)], reverse=True)
    assert len(areas) >= 2


def test_default_rois_and_stamp_constant():
    from hybrid_editor.diag_face_residue import STAMP_REQUIRED, default_face_rois

    assert STAMP_REQUIRED == "2026-10-14-fix-shadow-fringe-fast2"
    rois = default_face_rois(1080, 1920)
    assert "face_front" in rois and "under_chin" in rois
    x0, y0, x1, y1 = rois["face_front"]
    assert x1 > x0 and y1 > y0


def test_purge_does_not_touch_media(tmp_path: Path):
    from hybrid_editor.diag_face_residue import purge_mask_preview_cache_for_media
    from hybrid_editor.cache.mask_store import mask_dir, media_key

    root = tmp_path / "hybrid"
    media = tmp_path / "clip.mp4"
    media.write_bytes(b"fake")
    md = mask_dir(root, media, subject="person")
    md.mkdir(parents=True)
    (md / "000000000.png").write_bytes(b"x")
    proxy = root / "cache" / "proxy" / media.stem
    proxy.mkdir(parents=True)
    (proxy / "0.jpg").write_bytes(b"y")

    report = purge_mask_preview_cache_for_media(root, media)
    assert media.is_file()
    assert not md.exists()
    assert not proxy.exists()
    assert any("masks" in p.replace("\\", "/") for p in report["purged"])
