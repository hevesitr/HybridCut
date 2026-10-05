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
from hybrid_editor.engines.videoeditor_polish import BEST_SPEC, polish_videoeditor
from hybrid_editor.engines.vram import acquire_cuda, force_release_all, release_cuda
from hybrid_editor.export.composer import (
    AudioSegment,
    media_has_audio,
    try_prores_alpha,
    write_preview_mp4,
)
from hybrid_editor.media.video_io import (
    downscale_long_side,
    encode_preview_pair,
    encode_source_only_preview,
    is_matte_empty,
    read_frame_at,
)

logger = logging.getLogger(__name__)


class MaxQualityEngine(MattingEngine):
    mode = EngineMode.MAX

    def __init__(self) -> None:
        # Prefer ResNet50 when present — MobileNet is Gyors/scrub only.
        self._fast = FastEngine(prefer_quality=True)
        self._adapter = MatAnyone2Adapter()
        self._status = probe_matanyone2()
        self._media: Optional[MediaInfo] = None
        self._stabilizer = AnchorMemoryStabilizer(strength=0.4, jump_threshold=0.18)
        self._seed: Optional[np.ndarray] = None
        self._user_seed: Optional[np.ndarray] = None  # painted / lasso first-frame mask
        # Default on: CapCut-like sharp bake / preview (toggle via session).
        self.sharp_edges: bool = True
        if self._adapter.available:
            self._backend = "matanyone2-adapter"
        else:
            # Always RVM (or heuristic) quality pipeline when MatAnyone2 weights missing.
            self._backend = f"quality-pipeline+{self._fast.capabilities().backend}"
        self._status_note = self.person_matte_label()

    def set_sharp_edges(self, enabled: bool) -> None:
        self.sharp_edges = bool(enabled)

    def person_matte_label(self) -> str:
        """Clear HU status: MatAnyone2 active vs RVM person-matte fallback."""
        if self._adapter.available:
            return "MatAnyone2 aktív"
        return "MatAnyone2 nincs — RVM ember-maszk"

    def person_matte_info(self) -> dict:
        active = bool(self._adapter.available)
        return {
            "matanyone2_active": active,
            "matanyone2_available": active,
            "matanyone2_reason": self._status.reason,
            "person_matte_backend": "matanyone2" if active else "rvm-quality-pipeline",
            "person_matte_label_hu": self.person_matte_label(),
            "auto_person_matte": True,
            "manual_seed_refinement_only": True,
        }

    def set_user_seed(self, alpha: Optional[np.ndarray]) -> None:
        """Optional paint/lasso refinement — never required for auto person matte."""
        if alpha is None:
            self._user_seed = None
            return
        a = np.asarray(alpha, dtype=np.float32)
        if a.ndim == 3:
            a = a[..., 0]
        a = np.clip(a, 0.0, 1.0)
        # Near-empty paint must not arm a "seed present" path that BG-clamps the frame.
        if float(a.max()) < 0.05 or float((a > 0.15).mean()) < 0.002:
            self._user_seed = None
            return
        self._user_seed = a

    def clear_user_seed(self) -> None:
        self._user_seed = None

    @property
    def user_seed(self) -> Optional[np.ndarray]:
        return self._user_seed

    def capabilities(self) -> EngineCapabilities:
        info = self.person_matte_info()
        if self._adapter.available:
            detail = (
                f"{info['person_matte_label_hu']}. "
                "Local adapter (user weights). "
                "VRAM guard unloads Fast ORT CUDA before bake on 8GB."
            )
            vram = 5.5
            weights = self._status.weights_path
        else:
            fast_caps = self._fast.capabilities()
            weights_name = Path(fast_caps.weights_path).name if fast_caps.weights_path else "heuristic"
            sharp = "éles szélek ON" if self.sharp_edges else "lágyabb szélek"
            detail = (
                f"{info['person_matte_label_hu']}. "
                f"Quality pipeline on {fast_caps.backend} ({weights_name}, {sharp}) "
                f"(warmup×{DEFAULT_WARMUP}/trimap/anchor/mem_every). "
                f"MatAnyone2: {self._status.reason}"
            )
            vram = 3.5
            weights = self._status.weights_path or fast_caps.weights_path
        self._status_note = info["person_matte_label_hu"]
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
        """Always run Fast RVM / heuristic — never leave an empty matte for missing MatAnyone2."""
        from hybrid_editor.engines.fast_rvm import heuristic_person_alpha

        try:
            a = self._fast._matte(bgr)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Max base matte failed — heuristic: %s", exc)
            a = heuristic_person_alpha(bgr)
        if is_matte_empty(a):
            # Belt-and-suspenders: FastEngine._matte already retries, but keep Max safe
            # if a stub/backbone returns zeros without going through that path.
            a = heuristic_person_alpha(bgr)
        return a

    def _ensure_nonempty_alpha(self, bgr: np.ndarray, alpha: Optional[np.ndarray]) -> np.ndarray:
        """Last-resort person alpha so Max Előnézet never ships an empty mask."""
        from hybrid_editor.engines.fast_rvm import heuristic_person_alpha

        if alpha is not None and not is_matte_empty(alpha):
            return alpha
        try:
            a = self._base_alpha(bgr)
            if not is_matte_empty(a):
                return a
        except Exception:  # noqa: BLE001
            pass
        return heuristic_person_alpha(bgr)

    def _seed_for(self, bgr: np.ndarray, auto: np.ndarray) -> np.ndarray:
        """Guidance seed for quality trimap.

        Manual lasso/paint is **refinement only**: union with auto RVM alpha.
        Replacing auto with a tiny yellow blob used to BG-clamp the whole frame
        via fuse_alpha_trimap (person recognition looked broken).
        """
        auto_a = np.clip(np.asarray(auto, dtype=np.float32), 0.0, 1.0)
        if self._user_seed is None:
            return auto_a
        h, w = bgr.shape[:2]
        seed = self._user_seed
        if seed.shape[:2] != (h, w):
            seed = cv2.resize(seed, (w, h), interpolation=cv2.INTER_LINEAR)
        seed = np.clip(seed.astype(np.float32), 0.0, 1.0)
        if float(seed.max()) < 0.05:
            return auto_a
        return np.maximum(auto_a, seed)

    def _polish(self, bgr: np.ndarray, *, warmup: bool = False) -> np.ndarray:
        if warmup:
            a = warmup_alpha(self._base_alpha, bgr, n_warmup=DEFAULT_WARMUP)
        else:
            a = self._base_alpha(bgr)
        if self._seed is None:
            self._seed = self._seed_for(bgr, a.copy())
        # Soft-boost painted FG on the live alpha too (same union rule).
        if self._user_seed is not None:
            a = self._seed_for(bgr, a)
        # Éles szélek (default): CapCut Videoeditor polish — NO wide trimap fuse
        # (trimap erode/dilate was the thick halo / hair-hole source on the right side).
        if self.sharp_edges:
            polished = polish_videoeditor(a, bgr, spec=BEST_SPEC, seed=self._seed)
            return self._stabilizer.update(polished)
        return apply_quality_pass(
            a,
            seed=self._seed,
            stabilizer=self._stabilizer,
            sharp_edges=False,
            frame_bgr=bgr,
        )

    def preview_frame(self, t_sec: float) -> PreviewFrame:
        if self._media is None:
            raise RuntimeError("No media open")
        # Preview: quality polish; MaskStore/prefetch live inside Fast backbone
        self._fast.reset()
        # Keep Fast backend string fresh (CUDA→CPU fallback may update it).
        if not self._adapter.available:
            self._backend = f"quality-pipeline+{self._fast.capabilities().backend}"
        frame = self._fast.preview_frame(t_sec)
        # Re-polish with Videoeditor path at near-source resolution (match left-side quality).
        bgr, t = read_frame_at(Path(self._media.path), t_sec)
        # Sharp: keep up to 1440 long-side for Cutout preview (full bake stays native).
        preview_long = int(os.environ.get("HYBRID_MAX_PREVIEW_LONG", "1440") or "1440")
        if not self.sharp_edges:
            preview_long = 720
        bgr = downscale_long_side(bgr, preview_long)
        self._stabilizer.reset()
        self._seed = None
        matte_error = None
        recovered = False
        try:
            alpha = self._polish(bgr, warmup=True)
            # Polish / empty RVM must never leave Max without a person mask.
            if is_matte_empty(alpha):
                alpha = self._ensure_nonempty_alpha(bgr, alpha)
                recovered = not is_matte_empty(alpha)
            jpg, png, w, h, src, empty = encode_preview_pair(
                bgr, alpha, max_side=preview_long, sharp_cutout=self.sharp_edges
            )
        except Exception as exc:  # noqa: BLE001
            matte_error = str(exc)[:240]
            try:
                alpha = self._ensure_nonempty_alpha(bgr, None)
                recovered = not is_matte_empty(alpha)
                jpg, png, w, h, src, empty = encode_preview_pair(
                    bgr, alpha, max_side=preview_long, sharp_cutout=self.sharp_edges
                )
            except Exception as exc2:  # noqa: BLE001
                matte_error = f"{matte_error}; recover: {str(exc2)[:120]}"
                alpha = None
                jpg, png, w, h, src, empty = encode_source_only_preview(bgr, max_side=preview_long)
                empty = True
        if alpha is not None and (empty or is_matte_empty(alpha)):
            # Final hard retry before admitting empty to the UI.
            alpha = self._ensure_nonempty_alpha(bgr, alpha)
            if not is_matte_empty(alpha):
                jpg, png, w, h, src, empty = encode_preview_pair(
                    bgr, alpha, max_side=preview_long, sharp_cutout=self.sharp_edges
                )
                recovered = True
            else:
                empty = True
        info = self.person_matte_info()
        weights = self._fast.capabilities().weights_path
        # Status: clear empty vs live RVM person-matte label.
        label_hu = info["person_matte_label_hu"]
        if empty:
            label_hu = "Nincs ember-maszk"
        meta = {
            "mode": self.mode.value,
            "matanyone2": self._adapter.available,
            "matanyone2_active": info["matanyone2_active"],
            "matanyone2_reason": self._status.reason,
            "person_matte_label_hu": label_hu,
            "person_matte_backend": info["person_matte_backend"],
            "auto_person_matte": True,
            "warmup": DEFAULT_WARMUP,
            "user_seed": self._user_seed is not None,
            "manual_seed_refinement_only": True,
            "fast_meta": frame.meta,
            "matte_empty": empty,
            "matte_recovered": recovered,
            "sharp_edges": self.sharp_edges,
            "cutout_format": "png" if self.sharp_edges else "jpeg",
            "polish": "videoeditor" if self.sharp_edges else "trimap-soft",
            "rvm_weights": Path(weights).name if weights else None,
            "preview_long_side": preview_long,
        }
        if matte_error and empty:
            meta["matte_error"] = matte_error
            meta["source_fallback"] = True
        elif matte_error and not empty:
            meta["matte_error_recovered"] = matte_error
        return PreviewFrame(
            t_sec=t,
            width=w,
            height=h,
            jpeg_b64=jpg,
            alpha_png_b64=png,
            engine="MaxQualityEngine",
            backend=self._backend,
            meta=meta,
            source_jpeg_b64=src,
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
                # Full source resolution polish/bake (no proxy downsample before matte).
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
                # preview.mp4 may use a display proxy; ProRes / sharp export keeps full-res BGRA.
                preview_long = 1080 if self.sharp_edges else 720
                proxy = downscale_long_side(bgr, preview_long)
                a_p = cv2.resize(alpha, (proxy.shape[1], proxy.shape[0]), interpolation=cv2.INTER_LINEAR)
                frames_bgr.append(proxy)
                frames_alpha.append(a_p)
                if self.sharp_edges:
                    bgra = cv2.cvtColor(bgr, cv2.COLOR_BGR2BGRA)
                    bgra[:, :, 3] = a8
                else:
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
        sharp_note = " · éles szélek" if self.sharp_edges else ""
        weights = self._fast.capabilities().weights_path
        w_note = f" · {Path(weights).name}" if weights else ""
        return BakeResult(
            ok=written > 0,
            out_dir=str(out_dir.resolve()),
            frames_written=written,
            engine="MaxQualityEngine",
            backend=self._backend,
            message=(
                f"Quality pipeline wrote {written} frames + preview{audio_note}"
                f"{sharp_note}{w_note} (full-res alpha · {self._backend})"
            ),
            alpha_preview=str(alpha_dir / "000000.png") if written else None,
            preview_mp4=preview_mp4,
            prores_mov=prores,
            bake_range={
                "in_sec": start_t,
                "out_sec": end_t,
                "audio": audio_ok,
                "sharp_edges": self.sharp_edges,
                "full_res_alpha": True,
            },
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
            aa = np.clip(a.astype(np.float32), 0.0, 1.0)
            if aa.shape[:2] != frames_bgr[i].shape[:2]:
                aa = cv2.resize(aa, (frames_bgr[i].shape[1], frames_bgr[i].shape[0]), interpolation=cv2.INTER_LINEAR)
            # Same CapCut polish as quality-pipeline Max — kill halo / fill hair holes.
            if self.sharp_edges:
                aa = polish_videoeditor(aa, frames_bgr[i], spec=BEST_SPEC)
            a8 = (np.clip(aa, 0, 1) * 255).astype(np.uint8)
            cv2.imwrite(str(alpha_dir / f"{i:06d}.png"), a8)
            a = aa  # for proxy resize below
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
        self._fast = FastEngine(prefer_quality=True)
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
