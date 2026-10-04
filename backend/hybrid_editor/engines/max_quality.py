"""MaxQualityEngine — MatAnyone2 adapter when available, else hardened quality pipeline."""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Optional

import cv2
import numpy as np

from hybrid_editor.engines.base import (
    BakeResult,
    EngineCapabilities,
    EngineMode,
    MattingEngine,
    MediaInfo,
    PreviewFrame,
    ProgressCb,
)
from hybrid_editor.engines.fast_rvm import FastEngine
from hybrid_editor.engines.matanyone2_adapter import LICENSE_NOTE, MatAnyone2Adapter, probe_matanyone2
from hybrid_editor.engines.quality_pipeline import (
    DEFAULT_WARMUP,
    AnchorMemoryStabilizer,
    apply_quality_pass,
    warmup_alpha,
)
from hybrid_editor.engines.vram import acquire_cuda, force_release_all, release_cuda
from hybrid_editor.export.composer import (
    AudioSegment,
    media_has_audio,
    try_prores_alpha,
    write_preview_mp4,
)
from hybrid_editor.media.video_io import downscale_long_side, encode_preview_pair, read_frame_at

logger = logging.getLogger(__name__)


class MaxQualityEngine(MattingEngine):
    mode = EngineMode.MAX

    def __init__(self) -> None:
        self._fast = FastEngine()
        self._adapter = MatAnyone2Adapter()
        self._status = probe_matanyone2()
        self._media: Optional[MediaInfo] = None
        self._stabilizer = AnchorMemoryStabilizer(strength=0.4, jump_threshold=0.18)
        self._seed: Optional[np.ndarray] = None
        self._user_seed: Optional[np.ndarray] = None  # painted / lasso first-frame mask
        if self._adapter.available:
            self._backend = "matanyone2-adapter"
        else:
            self._backend = f"quality-pipeline+{self._fast.capabilities().backend}"

    def set_user_seed(self, alpha: Optional[np.ndarray]) -> None:
        """MatAnyone2-style first-frame seed mask from UI paint/lasso."""
        if alpha is None:
            self._user_seed = None
            return
        a = np.asarray(alpha, dtype=np.float32)
        if a.ndim == 3:
            a = a[..., 0]
        self._user_seed = np.clip(a, 0.0, 1.0)

    def clear_user_seed(self) -> None:
        self._user_seed = None

    @property
    def user_seed(self) -> Optional[np.ndarray]:
        return self._user_seed

    def capabilities(self) -> EngineCapabilities:
        if self._adapter.available:
            detail = (
                "MatAnyone2 local adapter (user weights). "
                "VRAM guard unloads Fast ORT CUDA before bake on 8GB."
            )
            vram = 5.5
            weights = self._status.weights_path
        else:
            detail = (
                f"Quality pipeline (warmup×{DEFAULT_WARMUP}/trimap/anchor/mem_every). "
                f"MatAnyone2: {self._status.reason}"
            )
            vram = 3.5
            weights = self._status.weights_path
        return EngineCapabilities(
            mode=self.mode,
            name="Max minőségű háttéreltávolítás",
            backend=self._backend,
            available=True,
            license_note=LICENSE_NOTE,
            vram_hint_gb=vram,
            detail=detail,
            weights_path=weights,
        )

    def reset(self) -> None:
        self._fast.reset()
        self._adapter.reset()
        self._stabilizer.reset()
        self._seed = None
        # Keep painted user seed across reset (tied to media, cleared on open/clear)

    def close(self) -> None:
        self._adapter.unload()
        release_cuda("max-matanyone2")
        self._fast.close()

    def open_media(self, path: Path) -> MediaInfo:
        self.reset()
        self._user_seed = None
        self._media = self._fast.open_media(path)
        return self._media

    def _base_alpha(self, bgr: np.ndarray) -> np.ndarray:
        return self._fast._matte(bgr)

    def _seed_for(self, bgr: np.ndarray, auto: np.ndarray) -> np.ndarray:
        if self._user_seed is None:
            return auto
        h, w = bgr.shape[:2]
        seed = self._user_seed
        if seed.shape[:2] != (h, w):
            seed = cv2.resize(seed, (w, h), interpolation=cv2.INTER_LINEAR)
        return np.clip(seed.astype(np.float32), 0.0, 1.0)

    def _polish(self, bgr: np.ndarray, *, warmup: bool = False) -> np.ndarray:
        if warmup:
            a = warmup_alpha(self._base_alpha, bgr, n_warmup=DEFAULT_WARMUP)
        else:
            a = self._base_alpha(bgr)
        if self._seed is None:
            self._seed = self._seed_for(bgr, a.copy())
        return apply_quality_pass(a, seed=self._seed, stabilizer=self._stabilizer)

    def preview_frame(self, t_sec: float) -> PreviewFrame:
        if self._media is None:
            raise RuntimeError("No media open")
        # Preview: quality polish; MaskStore/prefetch live inside Fast backbone
        self._fast.reset()
        frame = self._fast.preview_frame(t_sec)
        # Re-polish with quality path (re-decode for polish fidelity)
        bgr, t = read_frame_at(Path(self._media.path), t_sec)
        bgr = downscale_long_side(bgr, 720)
        self._stabilizer.reset()
        self._seed = None
        alpha = self._polish(bgr, warmup=True)
        jpg, png, w, h = encode_preview_pair(bgr, alpha)
        return PreviewFrame(
            t_sec=t,
            width=w,
            height=h,
            jpeg_b64=jpg,
            alpha_png_b64=png,
            engine="MaxQualityEngine",
            backend=self._backend,
            meta={
                "mode": self.mode.value,
                "matanyone2": self._adapter.available,
                "matanyone2_reason": self._status.reason,
                "warmup": DEFAULT_WARMUP,
                "user_seed": self._user_seed is not None,
                "fast_meta": frame.meta,
            },
        )

    def bake(
        self,
        out_dir: Path,
        *,
        max_frames: Optional[int] = None,
        progress: Optional[ProgressCb] = None,
        in_sec: float = 0.0,
        out_sec: Optional[float] = None,
    ) -> BakeResult:
        if self._media is None:
            raise RuntimeError("No media open")
        out_dir = Path(out_dir)
        alpha_dir = out_dir / "alpha"
        alpha_dir.mkdir(parents=True, exist_ok=True)

        if self._adapter.available:
            try:
                return self._bake_matanyone2(
                    out_dir, alpha_dir, max_frames=max_frames, progress=progress,
                    in_sec=in_sec, out_sec=out_sec,
                )
            except Exception as exc:  # noqa: BLE001
                logger.warning("MatAnyone2 bake failed (%s) — falling back to quality pipeline", exc)
                self._adapter.unload()
                release_cuda("max-matanyone2")

        return self._bake_quality_pipeline(
            out_dir, alpha_dir, max_frames=max_frames, progress=progress,
            in_sec=in_sec, out_sec=out_sec,
        )

    def _bake_quality_pipeline(
        self,
        out_dir: Path,
        alpha_dir: Path,
        *,
        max_frames: Optional[int],
        progress: Optional[ProgressCb],
        in_sec: float,
        out_sec: Optional[float],
    ) -> BakeResult:
        assert self._media is not None
        self.reset()
        path = Path(self._media.path)
        fps = self._media.fps or 25.0
        start_t = max(0.0, float(in_sec))
        end_t = float(out_sec) if out_sec is not None and out_sec > 0 else self._media.duration_sec
        end_t = max(start_t, end_t)
        cap = cv2.VideoCapture(str(path))
        if not cap.isOpened():
            raise RuntimeError(f"Cannot open {path}")
        cap.set(cv2.CAP_PROP_POS_MSEC, start_t * 1000.0)
        written = 0
        limit = max_frames if max_frames is not None else 10**9
        if limit <= 0:
            limit = 10**9
        total_est = int(max(1, round((end_t - start_t) * fps)))
        if max_frames is not None:
            total_est = min(total_est, max_frames)
        frames_bgr: list[np.ndarray] = []
        frames_alpha: list[np.ndarray] = []
        frames_bgra: list[np.ndarray] = []
        try:
            idx = 0
            while written < limit:
                ok, bgr = cap.read()
                if not ok or bgr is None:
                    break
                cur_t = start_t + (idx / fps)
                if cur_t > end_t + 1e-6:
                    break
                alpha = self._polish(bgr, warmup=(idx == 0))
                # Mid-clip re-warmup on strong drift vs seed
                if idx > 0 and idx % 48 == 0 and self._seed is not None:
                    drift = float(np.mean(np.abs(alpha - self._seed)))
                    if drift > 0.28:
                        if progress:
                            progress(written / max(total_est, 1), "Max re-warmup…")
                        self._fast.reset()
                        alpha = self._polish(bgr, warmup=True)
                a8 = (np.clip(alpha, 0, 1) * 255).astype(np.uint8)
                cv2.imwrite(str(alpha_dir / f"{idx:06d}.png"), a8)
                proxy = downscale_long_side(bgr, 720)
                a_p = cv2.resize(alpha, (proxy.shape[1], proxy.shape[0]), interpolation=cv2.INTER_LINEAR)
                frames_bgr.append(proxy)
                frames_alpha.append(a_p)
                bgra = cv2.cvtColor(proxy, cv2.COLOR_BGR2BGRA)
                bgra[:, :, 3] = (a_p * 255).astype(np.uint8)
                frames_bgra.append(bgra)
                written += 1
                idx += 1
                if progress:
                    progress(min(0.85, written / max(total_est, 1)), f"Max bake {written}/{total_est}")
        finally:
            cap.release()

        preview_mp4 = None
        prores = None
        audio_ok = False
        if written:
            if progress:
                progress(0.9, "Export preview.mp4 + audio…")
            audio_segs = [
                AudioSegment(
                    path=str(path),
                    in_sec=start_t,
                    out_sec=end_t,
                    timeline_start_sec=0.0,
                )
            ]
            preview_mp4 = write_preview_mp4(
                frames_bgr,
                frames_alpha,
                out_dir / "preview.mp4",
                fps=fps,
                audio_segments=audio_segs,
                audio_duration_sec=end_t - start_t,
            )
            audio_ok = bool(preview_mp4) and media_has_audio(preview_mp4)
            if os.environ.get("HYBRID_EXPORT_PRORES", "").strip() in {"1", "true", "yes"}:
                prores = try_prores_alpha(frames_bgra, out_dir / "master_alpha.mov", fps=fps)
            if progress:
                progress(1.0, "Bake kész")

        audio_note = " · audio AAC" if audio_ok else ""
        return BakeResult(
            ok=written > 0,
            out_dir=str(out_dir.resolve()),
            frames_written=written,
            engine="MaxQualityEngine",
            backend=self._backend,
            message=f"Quality pipeline wrote {written} frames + preview{audio_note} ({self._backend})",
            alpha_preview=str(alpha_dir / "000000.png") if written else None,
            preview_mp4=preview_mp4,
            prores_mov=prores,
            bake_range={"in_sec": start_t, "out_sec": end_t, "audio": audio_ok},
        )

    def _bake_matanyone2(
        self,
        out_dir: Path,
        alpha_dir: Path,
        *,
        max_frames: Optional[int],
        progress: Optional[ProgressCb],
        in_sec: float,
        out_sec: Optional[float],
    ) -> BakeResult:
        """VRAM-safe: unload Fast ORT CUDA, claim Max slot, run adapter."""
        assert self._media is not None
        # Free ORT CUDA before PyTorch MatAnyone2 on 8GB
        self._fast.close()
        force_release_all()
        acquire_cuda("max-matanyone2", detail="matanyone2 bake")

        path = Path(self._media.path)
        fps = self._media.fps or 25.0
        start_t = max(0.0, float(in_sec))
        end_t = float(out_sec) if out_sec is not None and out_sec > 0 else self._media.duration_sec
        end_t = max(start_t, end_t)
        cap = cv2.VideoCapture(str(path))
        frames_rgb: list[np.ndarray] = []
        frames_bgr: list[np.ndarray] = []
        limit = max_frames if max_frames is not None else 10**9
        if limit <= 0:
            limit = 10**9
        try:
            cap.set(cv2.CAP_PROP_POS_MSEC, start_t * 1000.0)
            idx = 0
            while len(frames_rgb) < limit:
                ok, bgr = cap.read()
                if not ok or bgr is None:
                    break
                cur_t = start_t + (idx / fps)
                if cur_t > end_t + 1e-6:
                    break
                frames_bgr.append(bgr)
                frames_rgb.append(cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB))
                idx += 1
        finally:
            cap.release()
        if not frames_rgb:
            release_cuda("max-matanyone2")
            return BakeResult(
                ok=False,
                out_dir=str(out_dir.resolve()),
                frames_written=0,
                engine="MaxQualityEngine",
                backend="matanyone2-adapter",
                message="No frames to bake",
            )
        if progress:
            progress(0.05, "MatAnyone2 warmup…")
        # Prefer painted seed; else CPU heuristic (no Fast CUDA reload on 8GB)
        from hybrid_editor.engines.fast_rvm import heuristic_person_alpha

        if self._user_seed is not None:
            h0, w0 = frames_bgr[0].shape[:2]
            seed = self._user_seed
            if seed.shape[:2] != (h0, w0):
                seed = cv2.resize(seed, (w0, h0), interpolation=cv2.INTER_LINEAR)
        else:
            seed = heuristic_person_alpha(frames_bgr[0])
        seed_bin = (seed > 0.5).astype(np.float32)
        try:
            alphas = self._adapter.matte_sequence(frames_rgb, seed_bin, n_warmup=DEFAULT_WARMUP)
        finally:
            self._adapter.unload()
            release_cuda("max-matanyone2")

        frames_alpha: list[np.ndarray] = []
        frames_proxy: list[np.ndarray] = []
        frames_bgra: list[np.ndarray] = []
        for i, a in enumerate(alphas):
            a8 = (np.clip(a, 0, 1) * 255).astype(np.uint8)
            if a8.shape[:2] != frames_bgr[i].shape[:2]:
                a8 = cv2.resize(a8, (frames_bgr[i].shape[1], frames_bgr[i].shape[0]))
            cv2.imwrite(str(alpha_dir / f"{i:06d}.png"), a8)
            proxy = downscale_long_side(frames_bgr[i], 720)
            a_p = cv2.resize(a8.astype(np.float32) / 255.0, (proxy.shape[1], proxy.shape[0]))
            frames_proxy.append(proxy)
            frames_alpha.append(a_p)
            bgra = cv2.cvtColor(proxy, cv2.COLOR_BGR2BGRA)
            bgra[:, :, 3] = (a_p * 255).astype(np.uint8)
            frames_bgra.append(bgra)
            if progress:
                progress(0.05 + 0.8 * (i + 1) / max(len(alphas), 1), f"MatAnyone2 {i + 1}")

        audio_segs = [
            AudioSegment(
                path=str(path),
                in_sec=start_t,
                out_sec=end_t,
                timeline_start_sec=0.0,
            )
        ]
        preview_mp4 = write_preview_mp4(
            frames_proxy,
            frames_alpha,
            out_dir / "preview.mp4",
            fps=fps,
            audio_segments=audio_segs,
            audio_duration_sec=end_t - start_t,
        )
        prores = None
        if os.environ.get("HYBRID_EXPORT_PRORES", "").strip() in {"1", "true", "yes"}:
            prores = try_prores_alpha(frames_bgra, out_dir / "master_alpha.mov", fps=fps)

        # Restore Fast backbone for further preview (CPU/heuristic or ORT as available)
        self._fast = FastEngine()
        if self._media:
            self._fast.open_media(Path(self._media.path))

        audio_ok = bool(preview_mp4) and media_has_audio(preview_mp4)
        audio_note = " · audio AAC" if audio_ok else ""
        return BakeResult(
            ok=True,
            out_dir=str(out_dir.resolve()),
            frames_written=len(alphas),
            engine="MaxQualityEngine",
            backend="matanyone2-adapter",
            message=(
                f"MatAnyone2 adapter wrote {len(alphas)} frames + preview{audio_note} "
                "(S-Lab NC, local)"
            ),
            alpha_preview=str(alpha_dir / "000000.png"),
            preview_mp4=preview_mp4,
            prores_mov=prores,
            bake_range={"in_sec": start_t, "out_sec": end_t, "audio": audio_ok},
        )
