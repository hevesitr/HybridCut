"""User-painted seed mask for MaxQuality / MatAnyone2 first-frame guidance."""

from __future__ import annotations

import base64
from pathlib import Path
from typing import Optional

import cv2
import numpy as np


def decode_alpha_png_b64(data: str) -> np.ndarray:
    raw = data.split(",", 1)[-1] if "," in data else data
    buf = base64.b64decode(raw)
    arr = np.frombuffer(buf, dtype=np.uint8)
    img = cv2.imdecode(arr, cv2.IMREAD_UNCHANGED)
    if img is None:
        raise ValueError("Invalid PNG seed mask")
    if img.ndim == 2:
        a = img.astype(np.float32) / 255.0
    elif img.shape[2] == 4:
        a = img[:, :, 3].astype(np.float32) / 255.0
    else:
        a = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY).astype(np.float32) / 255.0
    return np.clip(a, 0.0, 1.0)


def encode_alpha_png_b64(alpha: np.ndarray) -> str:
    a8 = np.clip(np.asarray(alpha, dtype=np.float32) * 255.0, 0, 255).astype(np.uint8)
    ok, buf = cv2.imencode(".png", a8)
    if not ok:
        raise RuntimeError("Failed to encode seed mask PNG")
    return base64.b64encode(buf.tobytes()).decode("ascii")


def resize_alpha(alpha: np.ndarray, shape: tuple[int, int]) -> np.ndarray:
    h, w = shape
    if alpha.shape[:2] == (h, w):
        return np.asarray(alpha, dtype=np.float32)
    return cv2.resize(
        np.asarray(alpha, dtype=np.float32),
        (w, h),
        interpolation=cv2.INTER_LINEAR,
    )


def save_seed(path: Path, alpha: np.ndarray) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    a8 = np.clip(np.asarray(alpha, dtype=np.float32) * 255.0, 0, 255).astype(np.uint8)
    cv2.imwrite(str(path), a8)


def load_seed(path: Path) -> Optional[np.ndarray]:
    if not path.is_file():
        return None
    gray = cv2.imread(str(path), cv2.IMREAD_GRAYSCALE)
    if gray is None:
        return None
    return (gray.astype(np.float32) / 255.0).clip(0.0, 1.0)
