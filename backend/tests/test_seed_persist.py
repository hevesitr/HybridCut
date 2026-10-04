"""Phase 4: seed mask disk persist + encode roundtrip."""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

from hybrid_editor.cache.seed_mask import (  # noqa: E402
    decode_alpha_png_b64,
    encode_alpha_png_b64,
    load_seed,
    save_seed,
)


def test_seed_roundtrip_disk(tmp_path: Path):
    alpha = np.zeros((64, 80), np.float32)
    alpha[10:40, 20:50] = 0.85
    path = tmp_path / "seed.png"
    save_seed(path, alpha)
    loaded = load_seed(path)
    assert loaded is not None
    assert loaded.shape == alpha.shape
    assert float(loaded[20, 30]) > 0.7
    assert float(loaded[0, 0]) < 0.05


def test_seed_b64_roundtrip():
    alpha = np.zeros((32, 48), np.float32)
    alpha[5:25, 8:30] = 1.0
    b64 = encode_alpha_png_b64(alpha)
    back = decode_alpha_png_b64(b64)
    assert back.shape == alpha.shape
    assert float(back[10, 12]) > 0.9
