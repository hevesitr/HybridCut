"""Varázsceruza part-pick — face-only (or compact region) matte from a click.

Local/CPU only (OpenCV Haar + skin gate). Intersects with person silhouette so
exported ``*_full_nobg`` alpha carries just the picked part — not the whole body.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any, Optional

import cv2
import numpy as np

PART_FACE = "face"
PART_REGION = "region"

PART_LABELS_HU: dict[str, str] = {
    PART_FACE: "Arc",
    PART_REGION: "Rész",
}


@lru_cache(maxsize=1)
def _cascades() -> list[cv2.CascadeClassifier]:
    out: list[cv2.CascadeClassifier] = []
    paths: list[Path] = []
    try:
        data = getattr(cv2, "data", None)
        if data is not None:
            root = Path(data.haarcascades)
            paths.append(root / "haarcascade_frontalface_default.xml")
            paths.append(root / "haarcascade_profileface.xml")
    except Exception:
        pass
    # Optional vendored copy next to hybrid models/
    here = Path(__file__).resolve().parents[3] / "models"
    paths.append(here / "haarcascade_frontalface_default.xml")
    for p in paths:
        if not p.is_file():
            continue
        try:
            c = cv2.CascadeClassifier(str(p))
            if not c.empty():
                out.append(c)
        except Exception:
            continue
    return out


def _detect_faces(gray: np.ndarray) -> list[tuple[int, int, int, int]]:
    h, w = gray.shape[:2]
    min_side = max(24, int(min(h, w) * 0.06))
    faces: list[tuple[int, int, int, int]] = []
    for cas in _cascades():
        try:
            found = cas.detectMultiScale(
                gray,
                scaleFactor=1.08,
                minNeighbors=4,
                minSize=(min_side, min_side),
                flags=cv2.CASCADE_SCALE_IMAGE,
            )
        except Exception:
            continue
        for x, y, fw, fh in found:
            faces.append((int(x), int(y), int(fw), int(fh)))
    return _nms_faces(faces)


def _nms_faces(
    faces: list[tuple[int, int, int, int]], iou_thresh: float = 0.35
) -> list[tuple[int, int, int, int]]:
    if not faces:
        return []
    boxes = sorted(faces, key=lambda b: b[2] * b[3], reverse=True)
    kept: list[tuple[int, int, int, int]] = []

    def iou(a: tuple[int, int, int, int], b: tuple[int, int, int, int]) -> float:
        ax, ay, aw, ah = a
        bx, by, bw, bh = b
        x0, y0 = max(ax, bx), max(ay, by)
        x1, y1 = min(ax + aw, bx + bw), min(ay + ah, by + bh)
        inter = max(0, x1 - x0) * max(0, y1 - y0)
        if inter <= 0:
            return 0.0
        union = aw * ah + bw * bh - inter
        return inter / max(union, 1)

    for b in boxes:
        if all(iou(b, k) < iou_thresh for k in kept):
            kept.append(b)
    return kept


def _skin_mask(bgr: np.ndarray) -> np.ndarray:
    hsv = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)
    ycrcb = cv2.cvtColor(bgr, cv2.COLOR_BGR2YCrCb)
    skin = cv2.inRange(hsv, (0, 25, 40), (25, 180, 255))
    skin2 = cv2.inRange(hsv, (160, 25, 40), (180, 180, 255))
    skin = cv2.bitwise_or(skin, skin2)
    y = cv2.inRange(ycrcb, (0, 135, 85), (255, 180, 135))
    skin = cv2.bitwise_or(skin, y)
    k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
    skin = cv2.morphologyEx(skin, cv2.MORPH_CLOSE, k, iterations=2)
    skin = cv2.morphologyEx(skin, cv2.MORPH_OPEN, k, iterations=1)
    return skin


def _ellipse_mask(h: int, w: int, box: tuple[int, int, int, int], pad: float = 0.18) -> np.ndarray:
    x, y, fw, fh = box
    cx = x + fw * 0.5
    cy = y + fh * 0.48
    ax = max(4.0, fw * (0.5 + pad))
    ay = max(4.0, fh * (0.55 + pad))
    hard = np.zeros((h, w), dtype=np.uint8)
    cv2.ellipse(
        hard,
        (int(round(cx)), int(round(cy))),
        (int(round(ax)), int(round(ay))),
        0,
        0,
        360,
        255,
        -1,
    )
    sigma = max(1.5, min(ax, ay) * 0.08)
    soft = cv2.GaussianBlur(hard.astype(np.float32) / 255.0, (0, 0), sigmaX=sigma)
    m = float(soft.max()) if soft.size else 1.0
    if m > 1e-6:
        soft = soft / m
    return np.clip(soft, 0.0, 1.0).astype(np.float32)


def _person_gate(bgr: np.ndarray) -> np.ndarray:
    """Soft person silhouette — heuristic only (no ORT) for pick-time gate."""
    from hybrid_editor.engines.fast_rvm import heuristic_person_alpha

    try:
        a = heuristic_person_alpha(bgr)
        return np.clip(np.asarray(a, dtype=np.float32), 0.0, 1.0)
    except Exception:
        h, w = bgr.shape[:2]
        return np.ones((h, w), dtype=np.float32)


def _pick_face_box(
    faces: list[tuple[int, int, int, int]],
    x: int,
    y: int,
    frame_h: int,
    frame_w: int,
) -> Optional[tuple[int, int, int, int]]:
    if not faces:
        return None
    # Prefer face that contains the click (with margin)
    for fx, fy, fw, fh in faces:
        m = int(max(fw, fh) * 0.22)
        if fx - m <= x <= fx + fw + m and fy - m <= y <= fy + fh + m:
            return (fx, fy, fw, fh)
    # Nearest face center in upper 70% of frame
    best = None
    best_d = 1e18
    for fx, fy, fw, fh in faces:
        cx, cy = fx + fw * 0.5, fy + fh * 0.5
        if cy > frame_h * 0.78:
            continue
        d = (cx - x) ** 2 + (cy - y) ** 2
        # Allow pick when click is within ~1.4× face diagonal
        diag = (fw**2 + fh**2) ** 0.5
        if d < best_d and d <= (diag * 1.4) ** 2:
            best_d = d
            best = (fx, fy, fw, fh)
    return best


def _flood_region(
    bgr: np.ndarray,
    x: int,
    y: int,
    *,
    tol: int = 28,
) -> np.ndarray:
    """Compact flood around click — last-resort part when Haar misses."""
    h, w = bgr.shape[:2]
    seed = np.zeros((h + 2, w + 2), dtype=np.uint8)
    flood = bgr.copy()
    mask = np.zeros((h, w), dtype=np.uint8)
    flags = 4 | (255 << 8) | cv2.FLOODFILL_MASK_ONLY
    try:
        cv2.floodFill(
            flood,
            seed,
            (int(x), int(y)),
            (255, 255, 255),
            loDiff=(tol, tol, tol),
            upDiff=(tol, tol, tol),
            flags=flags,
        )
        mask = seed[1:-1, 1:-1]
    except Exception:
        mask[:] = 0
    # Cap runaway floods (whole torso/BG)
    max_px = int(h * w * 0.12)
    if int(mask.sum()) // 255 > max_px:
        # Keep only a disk around the click
        disk = np.zeros((h, w), dtype=np.uint8)
        r = int(min(h, w) * 0.12)
        cv2.circle(disk, (x, y), max(8, r), 255, -1)
        mask = cv2.bitwise_and(mask, disk)
    soft = cv2.GaussianBlur(mask.astype(np.float32) / 255.0, (0, 0), sigmaX=2.0)
    return np.clip(soft, 0.0, 1.0).astype(np.float32)


def pick_part_matte(
    bgr: np.ndarray,
    x_norm: float,
    y_norm: float,
    *,
    erase: bool = False,
    existing: Optional[np.ndarray] = None,
) -> dict[str, Any]:
    """Pick face/region at normalized click → float alpha HxW.

    Returns dict with alpha, part, label_hu, pixels, method.
    """
    if bgr is None or bgr.size == 0:
        raise ValueError("Üres képkocka a Varázsceruza pickhez")
    h, w = bgr.shape[:2]
    x = int(np.clip(round(float(x_norm) * (w - 1)), 0, w - 1))
    y = int(np.clip(round(float(y_norm) * (h - 1)), 0, h - 1))

    gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
    gray = cv2.equalizeHist(gray)
    faces = _detect_faces(gray)
    box = _pick_face_box(faces, x, y, h, w)

    person = _person_gate(bgr)
    skin = _skin_mask(bgr).astype(np.float32) / 255.0

    if box is not None:
        part = PART_FACE
        method = "haar-face"
        alpha = _ellipse_mask(h, w, box, pad=0.2)
        # Soft skin preference inside ellipse; keep some non-skin (hair/glasses)
        alpha = alpha * np.clip(0.35 + 0.65 * skin, 0.0, 1.0)
        alpha = alpha * np.clip(np.maximum(person, 0.25), 0.0, 1.0)
        # Slight vertical taper below chin already handled by ellipse cy
    else:
        part = PART_REGION
        method = "flood-region"
        alpha = _flood_region(bgr, x, y)
        alpha = alpha * np.clip(np.maximum(person, 0.2), 0.0, 1.0)
        # If flood landed on skin in upper frame, treat as face-ish
        ys, xs = np.where(alpha > 0.35)
        if ys.size > 40:
            cy = float(ys.mean()) / max(h, 1)
            skin_frac = float((skin[alpha > 0.35] > 0.4).mean()) if ys.size else 0.0
            if cy < 0.55 and skin_frac > 0.35:
                part = PART_FACE
                method = "flood-face"

    alpha = np.clip(alpha.astype(np.float32), 0.0, 1.0)
    # Tiny cleanup
    a8 = (alpha * 255).astype(np.uint8)
    k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
    a8 = cv2.morphologyEx(a8, cv2.MORPH_OPEN, k, iterations=1)
    alpha = a8.astype(np.float32) / 255.0

    if erase:
        if existing is None:
            out = np.zeros((h, w), dtype=np.float32)
        else:
            ex = np.asarray(existing, dtype=np.float32)
            if ex.shape[:2] != (h, w):
                ex = cv2.resize(ex, (w, h), interpolation=cv2.INTER_LINEAR)
            out = np.clip(ex - alpha, 0.0, 1.0)
    else:
        # Replace with part matte (face-only); do not union with prior full-body seed
        out = alpha

    pixels = int((out > 0.15).sum())
    return {
        "alpha": out,
        "part": part,
        "label_hu": PART_LABELS_HU.get(part, part),
        "pixels": pixels,
        "method": method,
        "erase": bool(erase),
        "faces_found": len(faces),
    }
