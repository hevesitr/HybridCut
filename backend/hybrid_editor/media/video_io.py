"""Lightweight video probe / frame read / preview encode."""

from __future__ import annotations

import base64
from pathlib import Path
from typing import Optional

import cv2
import numpy as np

from hybrid_editor.engines.base import MediaInfo

# CapCut / Photoshop-like dark-theme transparency checker (never dominate the image).
CHECKER_TILE_PX = 10
CHECKER_DARK = 0x2A  # #2a2a2a
CHECKER_LIGHT = 0x35  # #353535
EMPTY_ALPHA_MAX = 0.02


def probe_video(path: Path) -> MediaInfo:
    path = Path(path)
    if not path.is_file():
        raise FileNotFoundError(f"Video not found: {path}")
    cap = cv2.VideoCapture(str(path))
    if not cap.isOpened():
        raise RuntimeError(f"Cannot open video: {path}")
    try:
        width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH) or 0)
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT) or 0)
        fps = float(cap.get(cv2.CAP_PROP_FPS) or 0.0) or 25.0
        frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
        duration = frame_count / fps if fps > 0 and frame_count > 0 else 0.0
        if width <= 0 or height <= 0:
            ok, frame = cap.read()
            if not ok or frame is None:
                raise RuntimeError(f"Empty video: {path}")
            height, width = frame.shape[:2]
        return MediaInfo(
            path=str(path.resolve()),
            width=width,
            height=height,
            fps=fps,
            frame_count=max(0, frame_count),
            duration_sec=float(duration),
        )
    finally:
        cap.release()


def read_frame_at(path: Path, t_sec: float) -> tuple[np.ndarray, float]:
    path = Path(path)
    cap = cv2.VideoCapture(str(path))
    if not cap.isOpened():
        raise RuntimeError(f"Cannot open video: {path}")
    try:
        fps = float(cap.get(cv2.CAP_PROP_FPS) or 0.0) or 25.0
        frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
        max_t = max(0.0, (frame_count - 1) / fps) if frame_count > 0 else max(0.0, t_sec)
        t = float(np.clip(t_sec, 0.0, max_t))
        cap.set(cv2.CAP_PROP_POS_MSEC, t * 1000.0)
        ok, frame = cap.read()
        if not ok or frame is None:
            cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
            ok, frame = cap.read()
        if not ok or frame is None:
            raise RuntimeError(f"Failed to read frame at t={t:.3f}s from {path}")
        return frame, t
    finally:
        cap.release()


def read_frame_index(path: Path, frame_idx: int) -> Optional[np.ndarray]:
    path = Path(path)
    cap = cv2.VideoCapture(str(path))
    if not cap.isOpened():
        return None
    try:
        cap.set(cv2.CAP_PROP_POS_FRAMES, max(0, int(frame_idx)))
        ok, frame = cap.read()
        if not ok or frame is None:
            return None
        return frame
    finally:
        cap.release()


def downscale_long_side(bgr: np.ndarray, max_long: int = 720) -> np.ndarray:
    h, w = bgr.shape[:2]
    long = max(h, w)
    if long <= max_long:
        return bgr
    scale = max_long / float(long)
    return cv2.resize(bgr, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_AREA)


def normalize_alpha(alpha: np.ndarray) -> np.ndarray:
    """Return float32 HxW alpha in [0, 1]."""
    a = np.asarray(alpha)
    if a.ndim == 3:
        a = a[..., 0]
    a = a.astype(np.float32)
    if a.size and float(a.max()) > 1.5:
        a = a / 255.0
    return np.clip(a, 0.0, 1.0)


def make_checkerboard(
    h: int,
    w: int,
    *,
    tile: int = CHECKER_TILE_PX,
    dark: int = CHECKER_DARK,
    light: int = CHECKER_LIGHT,
) -> np.ndarray:
    """Subtle dark-theme checkerboard (BGR uint8)."""
    tile = max(4, int(tile))
    yy, xx = np.mgrid[0:h, 0:w]
    checker = (((xx // tile) + (yy // tile)) % 2).astype(np.uint8)
    plane = np.where(checker == 1, light, dark).astype(np.uint8)
    return np.stack([plane, plane, plane], axis=-1)


def composite_cutout_over_checker(
    bgr: np.ndarray,
    alpha: np.ndarray,
    *,
    tile: int = CHECKER_TILE_PX,
    dark: int = CHECKER_DARK,
    light: int = CHECKER_LIGHT,
) -> np.ndarray:
    """Subject RGB × alpha over subtle checker. Empty alpha → dimmed video, never pure black."""
    h, w = bgr.shape[:2]
    a = normalize_alpha(alpha)
    if a.shape[:2] != (h, w):
        a = cv2.resize(a, (w, h), interpolation=cv2.INTER_LINEAR)
    bg = make_checkerboard(h, w, tile=tile, dark=dark, light=light)
    a3 = a[..., None]
    if float(a.max()) < EMPTY_ALPHA_MAX:
        # Clear empty-matte state: video stays readable, checker hints transparency.
        dim = (bgr.astype(np.float32) * 0.42).astype(np.uint8)
        return (dim.astype(np.float32) * 0.72 + bg.astype(np.float32) * 0.28).astype(np.uint8)
    return (bgr.astype(np.float32) * a3 + bg.astype(np.float32) * (1.0 - a3)).astype(np.uint8)


def visualize_alpha_matte(
    bgr: np.ndarray,
    alpha: np.ndarray,
    *,
    tile: int = CHECKER_TILE_PX,
    dark: int = CHECKER_DARK,
    light: int = CHECKER_LIGHT,
) -> np.ndarray:
    """Soft alpha / matte view over subtle checker — structure, not harsh noise."""
    h, w = bgr.shape[:2]
    a = normalize_alpha(alpha)
    if a.shape[:2] != (h, w):
        a = cv2.resize(a, (w, h), interpolation=cv2.INTER_LINEAR)
    bg = make_checkerboard(h, w, tile=tile, dark=dark, light=light)
    a3 = a[..., None]
    if float(a.max()) < EMPTY_ALPHA_MAX:
        gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
        soft = cv2.cvtColor((gray.astype(np.float32) * 0.35).astype(np.uint8), cv2.COLOR_GRAY2BGR)
        return (soft.astype(np.float32) * 0.65 + bg.astype(np.float32) * 0.35).astype(np.uint8)
    # Soft grayscale matte (light subject) over checker + faint source structure in mid-alpha.
    gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY).astype(np.float32)
    matte = (a * 210.0 + (1.0 - a) * (gray * 0.25)).astype(np.uint8)
    matte3 = cv2.cvtColor(matte, cv2.COLOR_GRAY2BGR)
    return (matte3.astype(np.float32) * a3 + bg.astype(np.float32) * (1.0 - a3)).astype(np.uint8)


def encode_preview_pair(
    bgr: np.ndarray, alpha: np.ndarray, *, max_side: int = 960
) -> tuple[str, str, int, int, str]:
    """Return (jpeg_cutout_b64, alpha_vis_png_b64, w, h, source_jpeg_b64).

    - jpeg: subject RGB × alpha over subtle checker (never solid black void)
    - alpha png: soft matte visualization over subtle checker
    - source jpeg: original video frame for seed / paint underlay
    """
    h, w = bgr.shape[:2]
    if max(h, w) > max_side:
        scale = max_side / float(max(h, w))
        bgr = cv2.resize(bgr, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_AREA)
        alpha = cv2.resize(
            np.asarray(alpha),
            (int(w * scale), int(h * scale)),
            interpolation=cv2.INTER_LINEAR,
        )
        h, w = bgr.shape[:2]

    cutout = composite_cutout_over_checker(bgr, alpha)
    alpha_vis = visualize_alpha_matte(bgr, alpha)

    ok_j, buf_j = cv2.imencode(".jpg", cutout, [int(cv2.IMWRITE_JPEG_QUALITY), 88])
    if not ok_j:
        raise RuntimeError("JPEG encode failed")
    ok_p, buf_p = cv2.imencode(".png", alpha_vis)
    if not ok_p:
        raise RuntimeError("PNG encode failed")
    ok_s, buf_s = cv2.imencode(".jpg", bgr, [int(cv2.IMWRITE_JPEG_QUALITY), 88])
    if not ok_s:
        raise RuntimeError("Source JPEG encode failed")
    return (
        base64.b64encode(buf_j.tobytes()).decode("ascii"),
        base64.b64encode(buf_p.tobytes()).decode("ascii"),
        w,
        h,
        base64.b64encode(buf_s.tobytes()).decode("ascii"),
    )
