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
# Empty / useless matte: max alpha below this OR almost no opaque coverage.
EMPTY_ALPHA_MAX = 0.05
EMPTY_ALPHA_COVER = 0.002  # fraction of pixels with a > 0.15
# When matte is empty, keep source nearly full brightness (optional slight dim).
EMPTY_SOURCE_DIM = 0.92


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


def is_matte_empty(alpha: np.ndarray) -> bool:
    """True when alpha is missing, all-transparent, or has no useful coverage yet."""
    if alpha is None:
        return True
    a = normalize_alpha(alpha)
    if a.size == 0:
        return True
    if float(a.max()) < EMPTY_ALPHA_MAX:
        return True
    # Tiny speck / noise must not hide the source under checker.
    if float((a > 0.15).mean()) < EMPTY_ALPHA_COVER:
        return True
    return False


def source_visible_bgr(bgr: np.ndarray, *, dim: float = EMPTY_SOURCE_DIM) -> np.ndarray:
    """Source RGB kept readable (optional slight dim) — never replaced by checker."""
    d = float(np.clip(dim, 0.5, 1.0))
    if d >= 0.999:
        return bgr.copy()
    return (bgr.astype(np.float32) * d).astype(np.uint8)


def annotate_nincs_maszk(bgr: np.ndarray) -> np.ndarray:
    """Burn a small 'nincs maszk' label onto a source frame (Előtte / empty matte)."""
    out = bgr.copy()
    h, w = out.shape[:2]
    label = "nincs maszk"
    font = cv2.FONT_HERSHEY_SIMPLEX
    scale = max(0.45, min(w, h) / 640.0)
    thickness = max(1, int(round(scale * 1.6)))
    (tw, th), baseline = cv2.getTextSize(label, font, scale, thickness)
    pad = max(4, int(6 * scale))
    x1, y1 = pad, pad
    x2, y2 = x1 + tw + pad * 2, y1 + th + baseline + pad * 2
    overlay = out.copy()
    cv2.rectangle(overlay, (x1, y1), (x2, y2), (20, 20, 20), -1)
    out = cv2.addWeighted(overlay, 0.55, out, 0.45, 0)
    cv2.putText(
        out,
        label,
        (x1 + pad, y1 + th + pad),
        font,
        scale,
        (220, 220, 220),
        thickness,
        cv2.LINE_AA,
    )
    return out


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
    """Subject RGB × alpha over subtle checker.

    Empty / useless matte → full source RGB (optional slight dim). Never pure checkerboard.
    After a real matte: checker only in truly transparent regions.
    """
    h, w = bgr.shape[:2]
    a = normalize_alpha(alpha)
    if a.shape[:2] != (h, w):
        a = cv2.resize(a, (w, h), interpolation=cv2.INTER_LINEAR)
    if is_matte_empty(a):
        # Utána / default cutout with no matte yet: show the video (source × ~1).
        return source_visible_bgr(bgr, dim=1.0)
    bg = make_checkerboard(h, w, tile=tile, dark=dark, light=light)
    a3 = a[..., None]
    return (bgr.astype(np.float32) * a3 + bg.astype(np.float32) * (1.0 - a3)).astype(np.uint8)


def visualize_alpha_matte(
    bgr: np.ndarray,
    alpha: np.ndarray,
    *,
    tile: int = CHECKER_TILE_PX,
    dark: int = CHECKER_DARK,
    light: int = CHECKER_LIGHT,
) -> np.ndarray:
    """Soft alpha / matte view. Empty matte → source + 'nincs maszk' (not pure checker)."""
    h, w = bgr.shape[:2]
    a = normalize_alpha(alpha)
    if a.shape[:2] != (h, w):
        a = cv2.resize(a, (w, h), interpolation=cv2.INTER_LINEAR)
    if is_matte_empty(a):
        # Előtte with no matte: keep source visible + clear empty-matte cue.
        return annotate_nincs_maszk(source_visible_bgr(bgr, dim=EMPTY_SOURCE_DIM))
    bg = make_checkerboard(h, w, tile=tile, dark=dark, light=light)
    a3 = a[..., None]
    # Soft grayscale matte (light subject) over checker + faint source structure in mid-alpha.
    gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY).astype(np.float32)
    matte = (a * 210.0 + (1.0 - a) * (gray * 0.25)).astype(np.uint8)
    matte3 = cv2.cvtColor(matte, cv2.COLOR_GRAY2BGR)
    return (matte3.astype(np.float32) * a3 + bg.astype(np.float32) * (1.0 - a3)).astype(np.uint8)


def encode_preview_pair(
    bgr: np.ndarray, alpha: np.ndarray, *, max_side: int = 960
) -> tuple[str, str, int, int, str, bool]:
    """Return (jpeg_cutout_b64, alpha_vis_png_b64, w, h, source_jpeg_b64, matte_empty).

    - jpeg: subject RGB × alpha over subtle checker; empty matte → full source RGB
    - alpha png: soft matte vis; empty → source + 'nincs maszk'
    - source jpeg: original video frame for seed / paint underlay
    - matte_empty: True when no useful alpha yet
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

    empty = is_matte_empty(alpha)
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
        empty,
    )


def encode_source_only_preview(
    bgr: np.ndarray, *, max_side: int = 960, note: str = "source-fallback"
) -> tuple[str, str, int, int, str, bool]:
    """Soft-fail preview: always show source RGB (empty matte semantics)."""
    h, w = bgr.shape[:2]
    if max(h, w) > max_side:
        scale = max_side / float(max(h, w))
        bgr = cv2.resize(bgr, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_AREA)
        h, w = bgr.shape[:2]
    alpha = np.zeros((h, w), dtype=np.float32)
    jpg, png, ow, oh, src, empty = encode_preview_pair(bgr, alpha, max_side=max_side)
    _ = note  # callers put note in PreviewFrame.meta
    return jpg, png, ow, oh, src, empty
