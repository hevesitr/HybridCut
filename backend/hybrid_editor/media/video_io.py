"""Lightweight video probe / frame read / preview encode."""

from __future__ import annotations

import base64
from pathlib import Path
from typing import Optional

import cv2
import numpy as np

from hybrid_editor.engines.base import MediaInfo


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


def encode_preview_pair(bgr: np.ndarray, alpha: np.ndarray, *, max_side: int = 960) -> tuple[str, str, int, int]:
    """Return (jpeg_b64 composite checker, alpha_png_b64, w, h)."""
    h, w = bgr.shape[:2]
    if max(h, w) > max_side:
        scale = max_side / float(max(h, w))
        bgr = cv2.resize(bgr, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_AREA)
        alpha = cv2.resize(alpha, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_LINEAR)
        h, w = bgr.shape[:2]
    a = alpha.astype(np.float32)
    if a.max() > 1.5:
        a = a / 255.0
    a = np.clip(a, 0.0, 1.0)
    tile = 16
    yy, xx = np.mgrid[0:h, 0:w]
    checker = (((xx // tile) + (yy // tile)) % 2).astype(np.float32)
    bg = (checker * 220 + (1.0 - checker) * 40).astype(np.uint8)
    bg = np.stack([bg, bg, bg], axis=-1)
    a3 = a[..., None]
    comp = (bgr.astype(np.float32) * a3 + bg.astype(np.float32) * (1.0 - a3)).astype(np.uint8)
    ok_j, buf_j = cv2.imencode(".jpg", comp, [int(cv2.IMWRITE_JPEG_QUALITY), 85])
    if not ok_j:
        raise RuntimeError("JPEG encode failed")
    a8 = (a * 255.0).astype(np.uint8)
    ok_p, buf_p = cv2.imencode(".png", a8)
    if not ok_p:
        raise RuntimeError("PNG encode failed")
    return (
        base64.b64encode(buf_j.tobytes()).decode("ascii"),
        base64.b64encode(buf_p.tobytes()).decode("ascii"),
        w,
        h,
    )
