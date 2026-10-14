"""restore-rvm-fast — CPU Gyors bake uses MobileNet@~640, soft alpha, honest ETA."""

from __future__ import annotations

import sys
from pathlib import Path

import cv2
import numpy as np
import pytest

BACKEND = Path(__file__).resolve().parents[1]
ROOT = BACKEND.parent
sys.path.insert(0, str(BACKEND))

STAMP = "2026-10-14-restore-rvm-fast"


def test_stamp_and_ascii_paste():
    assert (ROOT / "SYNC_VERSION.txt").read_text(encoding="utf-8").strip() == STAMP
    assert (ROOT / "backend/hybrid_editor/FEATURE_RESTORE_RVM_FAST.txt").read_text(
        encoding="utf-8"
    ).strip() == STAMP
    for name in (
        "PASTE_RESTORE_RVM_FAST_GITHUB.ps1",
        "PASTE_RESTORE_RVM_FAST_INSTALL.ps1",
    ):
        p = ROOT / name
        assert p.is_file()
        raw = p.read_bytes()
        assert all(b < 128 for b in raw), name
        text = p.read_text(encoding="utf-8")
        assert STAMP in text
        assert "cursor/restore-rvm-fast-b680" in text


def test_gyors_bake_proxy_flag(monkeypatch: pytest.MonkeyPatch):
    from hybrid_editor.engines.fast_rvm import FastEngine

    monkeypatch.setenv("HYBRID_ORT_PROVIDER", "cpu")
    eng = FastEngine(prefer_quality=False)
    eng._rvm = None  # noqa: SLF001
    ok, long = eng._gyors_bake_proxy()
    assert ok is True
    assert 480 <= long <= 720
    assert long == 640

    monkeypatch.setenv("HYBRID_GYORS_BAKE_LONG", "480")
    ok, long = eng._gyors_bake_proxy()
    assert ok and long == 480

    monkeypatch.setenv("HYBRID_GYORS_BAKE_FULLRES", "1")
    ok, long = eng._gyors_bake_proxy()
    assert ok is False


def test_eta_cpu_gyors_honest_not_8min():
    from hybrid_editor.eta import estimate_bake_sec

    # 10s @ 24fps 1080p — old full-res CPU ~8 min; proxy path ETA ~1 min class
    cpu = estimate_bake_sec(10.0, 24.0, 1920, 1080, "gyors", cpu_ort=True)
    cuda = estimate_bake_sec(10.0, 24.0, 1920, 1080, "gyors", cpu_ort=False)
    assert cuda < 30
    assert 30 <= cpu <= 120  # honest ~45–90s band (not 16s lie, not 480s)
    assert cpu < 480  # must not model the old 8 min path as expected


def test_bake_downscales_and_skips_mask_store(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setenv("HYBRID_ORT_PROVIDER", "cpu")
    monkeypatch.setenv("HYBRID_GYORS_BAKE_LONG", "480")
    from hybrid_editor.engines.fast_rvm import FastEngine

    h, w = 720, 1280
    bgr = np.full((h, w, 3), (40, 50, 70), np.uint8)
    cv2.ellipse(bgr, (w // 2, h // 2), (120, 220), 0, 0, 360, (90, 120, 180), -1)
    vid = tmp_path / "clip.mp4"
    vw = cv2.VideoWriter(str(vid), cv2.VideoWriter_fourcc(*"mp4v"), 12, (w, h))
    for _ in range(3):
        vw.write(bgr)
    vw.release()

    soft = np.zeros((270, 480), np.float32)  # will be resized to bgr_m shape
    # Engine will downscale to long=480 → ~270x480 for 16:9-ish; return matching soft.

    seen: dict[str, object] = {"shapes": [], "mask_put": 0}

    class FakeRvm:
        provider = "CPUExecutionProvider"
        _uses_cuda = False
        model_path = Path("rvm_mobilenetv3_fp32.onnx")
        fallback_note = None
        last_fgr_bgr = None

        def reset(self) -> None:
            return None

        def close(self) -> None:
            return None

        def matte(self, frame, downsample=0.25, prefer_native=False):
            seen["shapes"].append(frame.shape[:2])
            a = np.zeros(frame.shape[:2], np.float32)
            fh, fw = frame.shape[:2]
            cv2.ellipse(a, (fw // 2, fh // 2), (fw // 5, fh // 3), 0, 0, 360, 0.45, -1)
            return a

    eng = FastEngine(prefer_quality=False)
    eng._rvm = FakeRvm()  # noqa: SLF001
    eng._backend = "ort-rvm:CPUExecutionProvider"
    eng.open_media(vid)

    class CountingStore:
        def put(self, *a, **k):
            seen["mask_put"] = int(seen["mask_put"]) + 1

        def put_async(self, *a, **k):
            seen["mask_put"] = int(seen["mask_put"]) + 1

        def get_alpha(self, *a, **k):
            return None

        def purge(self):
            return None

        def clear_memory(self):
            return None

    eng._mask_store = CountingStore()  # noqa: SLF001
    out = tmp_path / "bake"
    out.mkdir()
    # Avoid ffmpeg ProRes failure blocking assertion — monkeypatch finalize lightly.
    monkeypatch.setattr(
        "hybrid_editor.engines.fast_rvm.finalize_bgcut_exports",
        lambda **kw: (str(out / "x_full_nobg.mov"), None),
    )
    monkeypatch.setattr(
        "hybrid_editor.engines.fast_rvm.write_preview_mp4",
        lambda *a, **k: str(out / "preview.mp4"),
    )
    monkeypatch.setattr(
        "hybrid_editor.engines.fast_rvm.media_has_audio",
        lambda *a, **k: False,
    )

    result = eng.bake(out, max_frames=3, in_sec=0.0, out_sec=1.0)
    assert result.ok
    assert result.bake_range.get("cpu_gyors_fast") is True
    assert result.bake_range.get("gyors_bake_long") == 480
    assert result.bake_range.get("soft_alpha") is True
    assert result.bake_range.get("mask_store_bake") is False
    assert seen["mask_put"] == 0
    # Long side of inferred frames must be <= 480
    for sh in seen["shapes"]:
        assert max(sh) <= 480
    assert "CPU Gyors@480" in (result.message or "")


def test_source_mentions_gyors_bake_fast():
    fr = (ROOT / "backend/hybrid_editor/engines/fast_rvm.py").read_text(encoding="utf-8")
    assert "_gyors_bake_proxy" in fr
    assert "HYBRID_GYORS_BAKE_LONG" in fr
    assert "CPU Gyors bake fast-path" in fr
    eta = (ROOT / "frontend/src/lib/eta.ts").read_text(encoding="utf-8")
    assert "CPU_GYORS_SPF_MULT" in eta
