"""Lightweight video probe / frame read / preview encode."""

from __future__ import annotations

import base64
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Sequence, Union

import cv2
import numpy as np

from hybrid_editor.engines.base import MediaInfo

# CapCut / Photoshop-like dark-theme transparency checker (never dominate the image).
CHECKER_TILE_PX = 10
CHECKER_DARK = 0x2A  # #2a2a2a
CHECKER_LIGHT = 0x35  # #353535
# Empty / useless matte: max alpha below this OR almost no opaque coverage.
EMPTY_ALPHA_MAX = 0.05
# Soft RVM person in a wide shot often lands cover≈0.03–0.08 / mean≈0.015–0.05.
# Floors must not reject those (cpu-matte/matte-cpu2 false-empty → toast / heuristic).
EMPTY_ALPHA_COVER = 0.012  # fraction of pixels with a > 0.15 (was 0.04 — too strict)
EMPTY_ALPHA_MEAN = 0.008  # mean alpha below this ⇒ treat as empty / weak (was 0.03)
# Structured soft person: peak + std can accept below cover/mean floors.
STRUCTURED_ALPHA_MAX = 0.35
STRUCTURED_ALPHA_STD = 0.035
STRUCTURED_ALPHA_COVER = 0.008
# Degenerate full-frame slab: near-uniform high alpha → Maszk = solid gray, Cutout = opaque source.
# (RVM 0–255 clip bug, wrong ORT tensor, or poisoned all-ones MaskStore.)
DEGENERATE_COVER = 0.90  # fraction a > 0.15
DEGENERATE_STD = 0.05  # spatial std below this + high cover ⇒ flat slab
DEGENERATE_MEAN = 0.85  # mean alpha with low std also useless
DEGENERATE_OPAQUE = 0.90  # fraction a >= 0.99
# Dust / tiny speck can pass structured floors — still retry ResNet / chroma / heuristic.
GOOD_ENOUGH_COVER = 0.025
GOOD_ENOUGH_BLOB_FRAC = 0.015
# Weak-but-not-empty: still prefer source underlay over checker domination.
WEAK_ALPHA_COVER = 0.08
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


def looks_like_alpha_media(path: Path | str) -> bool:
    """Heuristic: HybridCut *_full_nobg.mov / alpha WebM / explicit alpha stems."""
    p = Path(path)
    stem = p.stem.lower()
    suf = p.suffix.lower()
    if "nobg" in stem or "_alpha" in stem or stem.endswith("-alpha"):
        return True
    if suf == ".webm":
        return True
    return False


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


def _ffmpeg_read_bgra(path: Path, t_sec: float, width: int, height: int) -> Optional[np.ndarray]:
    """Decode one BGRA frame via ffmpeg (ProRes/qtrle/VP9 alpha). None on failure."""
    try:
        from hybrid_editor.export.ffmpeg_bin import resolve_ffmpeg
    except Exception:  # noqa: BLE001
        return None
    ff = resolve_ffmpeg("ffmpeg")
    if not ff or width <= 0 or height <= 0:
        return None
    t = max(0.0, float(t_sec))
    cmd = [
        ff,
        "-hide_banner",
        "-loglevel",
        "error",
        "-ss",
        f"{t:.4f}",
        "-i",
        str(path),
        "-frames:v",
        "1",
        "-f",
        "rawvideo",
        "-pix_fmt",
        "bgra",
        "-",
    ]
    try:
        proc = subprocess.run(cmd, capture_output=True, check=False, timeout=30)
    except (OSError, subprocess.TimeoutExpired):
        return None
    need = int(width) * int(height) * 4
    if proc.returncode != 0 or len(proc.stdout) < need:
        return None
    return np.frombuffer(proc.stdout[:need], dtype=np.uint8).reshape((height, width, 4)).copy()


def read_frame_bgra(path: Path, t_sec: float) -> tuple[np.ndarray, float, bool]:
    """Read BGRA (alpha preserved when possible). Returns (bgra, t, has_useful_alpha)."""
    path = Path(path)
    info = probe_video(path)
    t = float(np.clip(t_sec, 0.0, max(0.0, info.duration_sec)))
    bgra = _ffmpeg_read_bgra(path, t, info.width, info.height)
    if bgra is not None:
        a = bgra[:, :, 3].astype(np.float32) / 255.0
        useful = float(a.max()) > 0.05 and float((a > 0.15).mean()) > 0.01
        # Some opaque MOVs decode as full alpha — still valid
        if useful or looks_like_alpha_media(path):
            if not useful:
                # Opaque plate: treat as full coverage so layer still draws
                bgra = bgra.copy()
                bgra[:, :, 3] = 255
            return bgra, t, True
    # OpenCV fallback (usually drops alpha)
    bgr, t2 = read_frame_at(path, t)
    out = cv2.cvtColor(bgr, cv2.COLOR_BGR2BGRA)
    if looks_like_alpha_media(path):
        # Without real alpha, keep RGB and full A — caller may still transform as overlay
        out[:, :, 3] = 255
        return out, t2, False
    out[:, :, 3] = 255
    return out, t2, False


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
    """Return float32 HxW alpha in [0, 1].

    Some ORT RVM exports emit 0–255-ish floats; clipping those without scaling
    produces an all-ones slab (solid gray Maszk + opaque Cutout).
    """
    a = np.asarray(alpha)
    if a.ndim == 3:
        a = a[..., 0]
    a = a.astype(np.float32)
    if a.size and float(a.max()) > 1.5:
        a = a / 255.0
    return np.clip(a, 0.0, 1.0)


def _matte_border_mean(a: np.ndarray) -> float:
    h, w = a.shape[:2]
    if h < 8 or w < 8:
        return float(a.mean())
    b = max(2, min(h, w) // 40)
    border = np.concatenate(
        [
            a[:b, :].ravel(),
            a[-b:, :].ravel(),
            a[:, :b].ravel(),
            a[:, -b:].ravel(),
        ]
    )
    return float(border.mean())


def _matte_center_mean(a: np.ndarray) -> float:
    h, w = a.shape[:2]
    return float(a[h // 4 : 3 * h // 4, w // 4 : 3 * w // 4].mean())


def is_closeup_person_matte(alpha: np.ndarray) -> bool:
    """True for a high-cover silhouette with transparent-ish border (face/hair fill).

    Close-up 1920×1080 talking-head clips often have cover 0.7–0.95 — that must NOT
    be treated as an all-ones gray slab.

    matte-hard: reject near-uniform soft plates that only punch a thin rim
    (std low + cover ~1.0) — those look like the gray Maszk toast users report.
    """
    if alpha is None:
        return False
    a = normalize_alpha(alpha)
    if a.size == 0 or a.shape[0] < 8 or a.shape[1] < 8:
        return False
    std = float(a.std())
    if std < 0.08:
        return False
    cover = float((a > 0.15).mean())
    if cover < 0.35:
        return False
    # Soft full-frame plate with hairline rim ≠ close-up person.
    if cover >= 0.92 and std < 0.14:
        return False
    center = _matte_center_mean(a)
    border = _matte_border_mean(a)
    # Person fills frame: interior opaque, rim softer / punched.
    return center >= 0.55 and (center - border) >= 0.12 and border <= 0.75


def is_matte_degenerate(alpha: np.ndarray) -> bool:
    """True when alpha is a near-uniform full-frame slab (no person silhouette).

    Matches user Maszk screenshot: solid light-gray rectangle on checkerboard —
    ``visualize_alpha_matte`` with a≈1 everywhere paints ~210 gray over the frame.
    Cutout then stays fully opaque (BG never punched).

    Close-up face/hair silhouettes (high cover, structured rim) are NOT degenerate.
    """
    if alpha is None:
        return False
    a = normalize_alpha(alpha)
    if a.size == 0:
        return False
    # Structured close-up person — accept before slab heuristics.
    if is_closeup_person_matte(a):
        return False
    cover = float((a > 0.15).mean())
    std = float(a.std())
    mean = float(a.mean())
    opaque = float((a >= 0.99).mean())
    if opaque >= DEGENERATE_OPAQUE and std < 0.08:
        return True
    if cover >= DEGENERATE_COVER and std < DEGENERATE_STD:
        return True
    if mean >= DEGENERATE_MEAN and std < DEGENERATE_STD * 1.6:
        return True
    # matte-hard: soft full-frame plate (thin rim only) ≡ gray Maszk slab.
    if cover >= 0.92 and std < 0.10:
        return True
    # Opaque border + near-full cover ⇒ full-frame fill, not a person cutout.
    h, w = a.shape[:2]
    if h >= 8 and w >= 8:
        border_m = _matte_border_mean(a)
        if cover >= 0.85 and border_m >= 0.85 and std < 0.12:
            return True
    return False


def is_matte_structured(alpha: np.ndarray) -> bool:
    """True when alpha looks like a soft person silhouette (not dust, not slab)."""
    if alpha is None:
        return False
    a = normalize_alpha(alpha)
    if a.size == 0 or is_matte_degenerate(a):
        return False
    mx = float(a.max())
    std = float(a.std())
    cover = float((a > 0.15).mean())
    return (
        mx >= STRUCTURED_ALPHA_MAX
        and std >= STRUCTURED_ALPHA_STD
        and cover >= STRUCTURED_ALPHA_COVER
    )


def matte_failure_reason(alpha: np.ndarray) -> Optional[str]:
    """Short HU/tech reason when matte is useless for Cutout, else None."""
    if alpha is None:
        return "nincs alpha"
    a = normalize_alpha(alpha)
    if a.size == 0:
        return "üres alpha"
    if is_matte_degenerate(a):
        return (
            "egyenletes/teljes-keret maszk (hibás RVM vagy 0–255 clip) — "
            f"cover={float((a > 0.15).mean()):.2f} std={float(a.std()):.3f}"
        )
    if is_matte_structured(a):
        return None
    if float(a.max()) < EMPTY_ALPHA_MAX:
        return f"gyenge/üres maszk — max={float(a.max()):.3f}"
    cover = float((a > 0.15).mean())
    if cover < EMPTY_ALPHA_COVER or float(a.mean()) < EMPTY_ALPHA_MEAN:
        return (
            "gyenge/üres maszk — "
            f"max={float(a.max()):.3f} cover={cover:.3f}"
        )
    return None


def is_matte_empty(alpha: np.ndarray) -> bool:
    """True when alpha is missing, weak, or a degenerate full-frame slab.

    Degenerate all-ones / flat-gray mattes must NOT count as success — they
    previously showed Cutout ✓ while Maszk was a solid gray rectangle and
    Cutout kept the full background.

    Soft CPU RVM person mattes (wide shot, low mean/cover but clear peak+std)
    must count as success — matte-cpu2 false-empty rejected those and left
    Előnézet on heuristic / sticky gray toast after broken CUDA.
    """
    if alpha is None:
        return True
    a = normalize_alpha(alpha)
    if a.size == 0:
        return True
    if is_matte_degenerate(a):
        return True
    # Real soft person silhouette — accept before cover/mean floors.
    if is_matte_structured(a):
        return False
    if float(a.max()) < EMPTY_ALPHA_MAX:
        return True
    # Tiny speck / noise / feet-only scraps must not hide the source under checker.
    if float((a > 0.15).mean()) < EMPTY_ALPHA_COVER:
        return True
    if float(a.mean()) < EMPTY_ALPHA_MEAN:
        return True
    return False


def is_matte_sliver(alpha: np.ndarray, *, min_width_frac: float = 0.14) -> bool:
    """True when FG is a thin vertical/horizontal strip — catastrophic over-erase.

    matte-safe: crush that keeps only a bright MobileNet ridge produces a jagged
    vertical sliver on checkerboard (TELE HIBÁVAL). Reject and fall back.
    """
    if alpha is None:
        return False
    a = normalize_alpha(alpha)
    if a.size == 0:
        return False
    h, w = a.shape[:2]
    mask = a > 0.15
    if not np.any(mask):
        return False
    cover = float(mask.mean())
    ys, xs = np.where(mask)
    bw = int(xs.max() - xs.min()) + 1
    bh = int(ys.max() - ys.min()) + 1
    width_frac = bw / float(max(1, w))
    height_frac = bh / float(max(1, h))
    aspect = bh / float(max(1, bw))
    # Thin vertical strip: tall, narrow, low cover.
    if width_frac < float(min_width_frac) and aspect >= 2.2 and cover < 0.22:
        return True
    # Thin horizontal strip (rare).
    if height_frac < float(min_width_frac) and (bw / float(max(1, bh))) >= 2.2 and cover < 0.22:
        return True
    # Absolute tiny bbox area vs frame.
    if (bw * bh) < int(h * w * 0.04) and cover < 0.08:
        return True
    return False


def is_matte_good_enough(alpha: np.ndarray) -> bool:
    """True when alpha is usable for Cutout — not empty, not slab, not dust speck.

    simple-bg4: MobileNet on CPU can emit a tiny structured speck that passed
    ``is_matte_empty`` / structured floors; that skipped ResNet + chroma and left
    the user with a useless (or later gray-slab) preview. Specks must retry.

    matte-hard: near-full cover with weak spatial structure is NOT good enough —
    it reads as the gray Maszk slab and must continue the recovery ladder.
    """
    if alpha is None or is_matte_empty(alpha) or is_matte_degenerate(alpha):
        return False
    a = normalize_alpha(alpha)
    cover = float((a > 0.15).mean())
    std = float(a.std())
    if cover >= 0.90 and std < 0.12 and not is_closeup_person_matte(a):
        return False
    if cover >= GOOD_ENOUGH_COVER:
        return True
    # Low cover: require a real connected person blob (not ORT dust).
    mask = (a > 0.35).astype(np.uint8)
    if int(mask.max()) < 1:
        return False
    n, _labels, stats, _ = cv2.connectedComponentsWithStats(mask, connectivity=8)
    if n <= 1:
        return False
    largest = int(stats[1:, cv2.CC_STAT_AREA].max())
    return largest >= int(a.size * GOOD_ENOUGH_BLOB_FRAC)


def is_uniform_slab(alpha: np.ndarray) -> bool:
    """True for near-constant pha (all-ones / flat) — skip ds ladder retries."""
    if alpha is None:
        return False
    a = normalize_alpha(alpha)
    if a.size == 0:
        return False
    return float(a.std()) < 0.012 and float(a.mean()) >= 0.85


def source_visible_bgr(bgr: np.ndarray, *, dim: float = EMPTY_SOURCE_DIM) -> np.ndarray:
    """Source RGB kept readable (optional slight dim) — never replaced by checker."""
    d = float(np.clip(dim, 0.5, 1.0))
    if d >= 0.999:
        return bgr.copy()
    return (bgr.astype(np.float32) * d).astype(np.uint8)


def annotate_nincs_maszk(bgr: np.ndarray, label: str = "nincs maszk") -> np.ndarray:
    """Burn a small empty/broken-matte label onto a source frame (Előtte / empty matte)."""
    out = bgr.copy()
    h, w = out.shape[:2]
    text = str(label or "nincs maszk")[:48]
    font = cv2.FONT_HERSHEY_SIMPLEX
    scale = max(0.45, min(w, h) / 640.0)
    thickness = max(1, int(round(scale * 1.6)))
    (tw, th), baseline = cv2.getTextSize(text, font, scale, thickness)
    pad = max(4, int(6 * scale))
    x1, y1 = pad, pad
    x2, y2 = x1 + tw + pad * 2, y1 + th + baseline + pad * 2
    overlay = out.copy()
    cv2.rectangle(overlay, (x1, y1), (x2, y2), (20, 20, 20), -1)
    out = cv2.addWeighted(overlay, 0.55, out, 0.45, 0)
    cv2.putText(
        out,
        text,
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


@dataclass
class OverlayFrame:
    """One overlay layer for monitor + bake (CapCut PiP / nobg cutout)."""

    bgr: np.ndarray
    opacity: float = 1.0
    alpha: Optional[np.ndarray] = None
    pos_x: float = 0.0
    pos_y: float = 0.0
    scale: float = 1.0


OverlayInput = Union[OverlayFrame, tuple]


def _as_overlay(item: OverlayInput) -> OverlayFrame:
    if isinstance(item, OverlayFrame):
        return item
    if not isinstance(item, tuple) or len(item) < 2:
        raise TypeError("overlay must be OverlayFrame or (bgr, opacity[, ...])")
    bgr = item[0]
    opacity = float(item[1])
    alpha = item[2] if len(item) >= 3 else None
    pos_x = float(item[3]) if len(item) >= 4 else 0.0
    pos_y = float(item[4]) if len(item) >= 5 else 0.0
    scale = float(item[5]) if len(item) >= 6 else 1.0
    return OverlayFrame(
        bgr=bgr, opacity=opacity, alpha=alpha, pos_x=pos_x, pos_y=pos_y, scale=scale
    )


def place_layer_on_canvas(
    canvas_h: int,
    canvas_w: int,
    layer_bgr: np.ndarray,
    layer_alpha: np.ndarray,
    *,
    pos_x: float = 0.0,
    pos_y: float = 0.0,
    scale: float = 1.0,
) -> tuple[np.ndarray, np.ndarray]:
    """Contain-fit layer onto canvas with CapCut-like center offset + scale.

    pos_x/pos_y are fractions of canvas size (0,0 = centered). scale 1 = 100%.
    Returns full-canvas BGR + alpha float32 (zeros outside the placed rect).
    """
    lh, lw = layer_bgr.shape[:2]
    if lh <= 0 or lw <= 0 or canvas_h <= 0 or canvas_w <= 0:
        z_bgr = np.zeros((canvas_h, canvas_w, 3), np.uint8)
        z_a = np.zeros((canvas_h, canvas_w), np.float32)
        return z_bgr, z_a
    a = normalize_alpha(layer_alpha)
    if a.shape[:2] != (lh, lw):
        a = cv2.resize(a, (lw, lh), interpolation=cv2.INTER_LINEAR)
    fit = min(canvas_w / float(lw), canvas_h / float(lh))
    sc = max(0.05, float(scale)) * fit
    out_w = max(1, int(round(lw * sc)))
    out_h = max(1, int(round(lh * sc)))
    resized = cv2.resize(layer_bgr, (out_w, out_h), interpolation=cv2.INTER_AREA)
    a_r = cv2.resize(a, (out_w, out_h), interpolation=cv2.INTER_LINEAR)
    cx = canvas_w * 0.5 + float(pos_x) * canvas_w
    cy = canvas_h * 0.5 + float(pos_y) * canvas_h
    x0 = int(round(cx - out_w * 0.5))
    y0 = int(round(cy - out_h * 0.5))
    x1, y1 = x0 + out_w, y0 + out_h
    # Clip to canvas
    src_x0 = max(0, -x0)
    src_y0 = max(0, -y0)
    dst_x0 = max(0, x0)
    dst_y0 = max(0, y0)
    dst_x1 = min(canvas_w, x1)
    dst_y1 = min(canvas_h, y1)
    placed_bgr = np.zeros((canvas_h, canvas_w, 3), np.uint8)
    placed_a = np.zeros((canvas_h, canvas_w), np.float32)
    if dst_x1 <= dst_x0 or dst_y1 <= dst_y0:
        return placed_bgr, placed_a
    src_x1 = src_x0 + (dst_x1 - dst_x0)
    src_y1 = src_y0 + (dst_y1 - dst_y0)
    placed_bgr[dst_y0:dst_y1, dst_x0:dst_x1] = resized[src_y0:src_y1, src_x0:src_x1]
    placed_a[dst_y0:dst_y1, dst_x0:dst_x1] = a_r[src_y0:src_y1, src_x0:src_x1]
    return placed_bgr, placed_a


def composite_overlay_layers(
    bgr: np.ndarray,
    alpha: np.ndarray,
    overlays: Sequence[OverlayInput],
) -> tuple[np.ndarray, np.ndarray]:
    """Porter-Duff over: stack V2 overlays (nobg alpha / B-roll) on V1 cutout.

    Concat idea: one compositor path for monitor + export — same blend math as bake.
    Each overlay is OverlayFrame or legacy (bgr_uint8, opacity 0..1).
    Optional alpha + pos_x/pos_y/scale enable CapCut-like movable cutouts.
    """
    out = bgr.astype(np.float32)
    a = normalize_alpha(alpha).astype(np.float32)
    h, w = out.shape[:2]
    for raw in overlays:
        ov = _as_overlay(raw)
        op = float(np.clip(ov.opacity, 0.0, 1.0))
        if op <= 1e-6:
            continue
        layer = ov.bgr
        if ov.alpha is not None:
            la = normalize_alpha(ov.alpha)
        else:
            la = np.ones(layer.shape[:2], np.float32)
        # Identity transform + matching size → fast path (legacy B-roll)
        identity = (
            abs(float(ov.pos_x)) < 1e-6
            and abs(float(ov.pos_y)) < 1e-6
            and abs(float(ov.scale) - 1.0) < 1e-6
            and ov.alpha is None
        )
        if identity:
            if layer.shape[:2] != (h, w):
                layer = cv2.resize(layer, (w, h), interpolation=cv2.INTER_AREA)
            mask = op
            out = out * (1.0 - mask) + layer.astype(np.float32) * mask
            a = np.maximum(a, mask)
            continue
        placed_bgr, placed_a = place_layer_on_canvas(
            h,
            w,
            layer,
            la,
            pos_x=float(ov.pos_x),
            pos_y=float(ov.pos_y),
            scale=float(ov.scale),
        )
        mask = np.clip(placed_a * op, 0.0, 1.0)[..., None]
        out = out * (1.0 - mask) + placed_bgr.astype(np.float32) * mask
        a = np.maximum(a, mask[..., 0])
    return out.astype(np.uint8), a.astype(np.float32)


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
    cover = float((a > 0.15).mean())
    if cover < WEAK_ALPHA_COVER:
        # Weak matte: keep source visible as underlay (never mostly-checker).
        bg = source_visible_bgr(bgr, dim=0.94)
    else:
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
    """Soft alpha / matte view. Empty/degenerate → source + label (never solid gray slab)."""
    h, w = bgr.shape[:2]
    a = normalize_alpha(alpha)
    if a.shape[:2] != (h, w):
        a = cv2.resize(a, (w, h), interpolation=cv2.INTER_LINEAR)
    if is_matte_degenerate(a):
        # Never paint the flat ~210 gray rectangle users reported as Maszk.
        return annotate_nincs_maszk(
            source_visible_bgr(bgr, dim=EMPTY_SOURCE_DIM),
            label="hibas maszk",
        )
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
    bgr: np.ndarray,
    alpha: np.ndarray,
    *,
    max_side: int = 960,
    sharp_cutout: bool = False,
) -> tuple[str, str, int, int, str, bool]:
    """Return (cutout_b64, alpha_vis_png_b64, w, h, source_jpeg_b64, matte_empty).

    - cutout: subject RGB × alpha over subtle checker; empty matte → full source RGB
      sharp_cutout=True → PNG (no JPEG halo soft); else high-quality JPEG
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

    if sharp_cutout:
        # Lossless cutout composite — avoids JPEG ringing on hair / shoulder edges.
        ok_j, buf_j = cv2.imencode(".png", cutout)
        if not ok_j:
            raise RuntimeError("PNG cutout encode failed")
    else:
        ok_j, buf_j = cv2.imencode(".jpg", cutout, [int(cv2.IMWRITE_JPEG_QUALITY), 92])
        if not ok_j:
            raise RuntimeError("JPEG encode failed")
    ok_p, buf_p = cv2.imencode(".png", alpha_vis)
    if not ok_p:
        raise RuntimeError("PNG encode failed")
    ok_s, buf_s = cv2.imencode(".jpg", bgr, [int(cv2.IMWRITE_JPEG_QUALITY), 90])
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
