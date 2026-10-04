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
    is_matte_empty,
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


def test_empty_alpha_shows_source_rgb_not_checker():
    """Empty matte must show source video — never pure / dominant checkerboard."""
    bgr = np.zeros((48, 64, 3), np.uint8)
    # Distinct RGB so checker gray cannot masquerade as the frame.
    bgr[:, :] = (30, 200, 90)
    cv2.rectangle(bgr, (10, 8), (50, 40), (20, 40, 220), -1)
    alpha = np.zeros((48, 64), np.float32)
    assert is_matte_empty(alpha)

    out = composite_cutout_over_checker(bgr, alpha)
    # Full source RGB (Utána / default): mean close to source, not checker ~0x2a–0x35.
    assert float(out.mean()) > 80
    # Center keeps the red-ish subject channel dominant (B≈220).
    assert int(out[24, 30, 2]) > 180
    # Must not collapse to checker-only grays.
    uniq = {int(v) for v in np.unique(out)}
    assert not uniq.issubset({CHECKER_DARK, CHECKER_LIGHT})

    # Correlation with source: empty cutout ≈ source × 1
    err = float(np.mean(np.abs(out.astype(np.float32) - bgr.astype(np.float32))))
    assert err < 2.0


def test_near_empty_speck_still_shows_source():
    """Tiny alpha noise / speck must not hide the video under checker."""
    bgr = np.full((40, 40, 3), (50, 160, 100), np.uint8)
    alpha = np.zeros((40, 40), np.float32)
    alpha[0, 0] = 0.4  # single pixel — useless coverage
    assert is_matte_empty(alpha)
    out = composite_cutout_over_checker(bgr, alpha)
    assert float(out.mean()) > 80
    assert abs(float(out[20, 20, 1]) - 160) < 3


def test_feet_only_weak_matte_shows_source():
    """Small lower-frame scrap (≈ feet) must not leave a mostly-checker preview."""
    bgr = np.full((80, 120, 3), (40, 150, 90), np.uint8)
    cv2.rectangle(bgr, (30, 10), (90, 70), (30, 50, 210), -1)
    alpha = np.zeros((80, 120), np.float32)
    # ~2.5% coverage in the bottom — typical weak/partial matte.
    alpha[72:80, 40:80] = 0.7
    assert float((alpha > 0.15).mean()) < 0.04
    assert is_matte_empty(alpha)
    out = composite_cutout_over_checker(bgr, alpha)
    err = float(np.mean(np.abs(out.astype(np.float32) - bgr.astype(np.float32))))
    assert err < 4.0
    assert float(out.mean()) > 70


def test_empty_alpha_vis_shows_source_with_nincs_maszk():
    bgr = np.full((64, 96, 3), (40, 90, 180), np.uint8)
    alpha = np.zeros((64, 96), np.float32)
    vis = visualize_alpha_matte(bgr, alpha)
    assert vis.shape == (64, 96, 3)
    # Source remains visible (not checker-only).
    assert float(vis.mean()) > 50
    uniq = {int(v) for v in np.unique(vis)}
    assert not uniq.issubset({CHECKER_DARK, CHECKER_LIGHT})


def test_alpha_vis_shows_structure_over_checker():
    bgr = np.zeros((48, 48, 3), np.uint8)
    bgr[10:38, 10:38] = (30, 60, 200)
    alpha = np.zeros((48, 48), np.float32)
    cv2.circle(alpha, (24, 24), 14, 1.0, -1)
    assert not is_matte_empty(alpha)
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
    jpg, png, w, h, src, empty = encode_preview_pair(bgr, alpha, max_side=120)
    assert w > 0 and h > 0
    assert jpg and png and src
    assert empty is False
    cut = cv2.imdecode(np.frombuffer(base64.b64decode(jpg), np.uint8), cv2.IMREAD_COLOR)
    src_img = cv2.imdecode(np.frombuffer(base64.b64decode(src), np.uint8), cv2.IMREAD_COLOR)
    alpha_vis = cv2.imdecode(np.frombuffer(base64.b64decode(png), np.uint8), cv2.IMREAD_COLOR)
    assert cut is not None and src_img is not None and alpha_vis is not None
    # Source keeps full-frame RGB (no checker crush on opaque green field).
    assert float(src_img.mean()) > 30
    assert normalize_alpha(alpha).max() > 0.5


def test_encode_empty_alpha_flags_and_keeps_source():
    bgr = np.zeros((50, 70, 3), np.uint8)
    bgr[:] = (25, 170, 80)
    alpha = np.zeros((50, 70), np.float32)
    jpg, png, w, h, src, empty = encode_preview_pair(bgr, alpha, max_side=100)
    assert empty is True
    cut = cv2.imdecode(np.frombuffer(base64.b64decode(jpg), np.uint8), cv2.IMREAD_COLOR)
    src_img = cv2.imdecode(np.frombuffer(base64.b64decode(src), np.uint8), cv2.IMREAD_COLOR)
    assert cut is not None and src_img is not None
    # Cutout ≈ source when matte empty (source × 1).
    assert float(np.mean(np.abs(cut.astype(np.float32) - src_img.astype(np.float32)))) < 8.0
    assert float(cut.mean()) > 70
