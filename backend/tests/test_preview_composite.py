"""Unit tests for subtle checker / cutout / alpha preview compositing."""

from __future__ import annotations

import base64

import cv2
import numpy as np

from hybrid_editor.media.video_io import (
    CHECKER_DARK,
    CHECKER_LIGHT,
    CHECKER_TILE_PX,
    composite_cutout_over_checker,
    encode_preview_pair,
    make_checkerboard,
    normalize_alpha,
    visualize_alpha_matte,
)


def test_checkerboard_subtle_dark_theme():
    bg = make_checkerboard(64, 64, tile=CHECKER_TILE_PX)
    assert bg.shape == (64, 64, 3)
    uniq = {int(v) for v in np.unique(bg)}
    assert uniq <= {CHECKER_DARK, CHECKER_LIGHT}
    # Low contrast: channel delta well below old harsh 220/40 pair.
    assert abs(CHECKER_LIGHT - CHECKER_DARK) <= 20
    assert CHECKER_TILE_PX <= 12


def test_cutout_composites_subject_rgb_not_black():
    bgr = np.zeros((40, 40, 3), np.uint8)
    bgr[:, :] = (40, 180, 90)  # green-ish subject
    alpha = np.zeros((40, 40), np.float32)
    alpha[8:32, 8:32] = 1.0
    out = composite_cutout_over_checker(bgr, alpha)
    # Opaque subject region keeps source RGB (not crushed to black).
    center = out[20, 20]
    assert int(center[1]) > 140
    # Transparent corner is subtle checker gray, not near-white/near-black harsh tiles.
    corner = out[2, 2]
    assert CHECKER_DARK - 2 <= int(corner[0]) <= CHECKER_LIGHT + 2


def test_empty_alpha_shows_dimmed_video_not_void():
    bgr = np.full((32, 32, 3), 180, np.uint8)
    alpha = np.zeros((32, 32), np.float32)
    out = composite_cutout_over_checker(bgr, alpha)
    mean = float(out.mean())
    assert mean > 40  # not pure black void
    assert mean < 160  # dimmed / blended, not full bright frame


def test_alpha_vis_shows_structure_over_checker():
    bgr = np.zeros((48, 48, 3), np.uint8)
    bgr[10:38, 10:38] = (30, 60, 200)
    alpha = np.zeros((48, 48), np.float32)
    cv2.circle(alpha, (24, 24), 14, 1.0, -1)
    vis = visualize_alpha_matte(bgr, alpha)
    assert vis.shape == (48, 48, 3)
    # Center (opaque) brighter than far corner (checker).
    assert float(vis[24, 24].mean()) > float(vis[2, 2].mean()) + 40


def test_encode_preview_pair_returns_source_and_decodable():
    bgr = np.zeros((60, 80, 3), np.uint8)
    bgr[:] = (20, 90, 40)
    cv2.rectangle(bgr, (20, 10), (60, 50), (50, 40, 220), -1)
    alpha = np.zeros((60, 80), np.float32)
    alpha[10:50, 20:60] = 0.85
    jpg, png, w, h, src = encode_preview_pair(bgr, alpha, max_side=120)
    assert w > 0 and h > 0
    assert jpg and png and src
    cut = cv2.imdecode(np.frombuffer(base64.b64decode(jpg), np.uint8), cv2.IMREAD_COLOR)
    src_img = cv2.imdecode(np.frombuffer(base64.b64decode(src), np.uint8), cv2.IMREAD_COLOR)
    alpha_vis = cv2.imdecode(np.frombuffer(base64.b64decode(png), np.uint8), cv2.IMREAD_COLOR)
    assert cut is not None and src_img is not None and alpha_vis is not None
    # Source keeps full-frame RGB (no checker crush on opaque green field).
    assert float(src_img.mean()) > 30
    assert normalize_alpha(alpha).max() > 0.5
