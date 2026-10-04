"""In-memory editor session — multi-clip timeline + engines + analyse + seed mask."""

from __future__ import annotations

import os
import subprocess
import sys
import threading
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Optional

import numpy as np

from hybrid_editor import ROOT, SYNC_VERSION
from hybrid_editor.cache import MASK_RATE
from hybrid_editor.cache.analyse import SparseAnalyser
from hybrid_editor.cache.seed_mask import (
    decode_alpha_png_b64,
    encode_alpha_png_b64,
    load_seed,
    save_seed,
)
from hybrid_editor.engines import EngineMode, MattingEngine, create_engine, resolve_mode
from hybrid_editor.engines.base import BakeResult, MediaInfo, PreviewFrame
from hybrid_editor.engines.fast_rvm import probe_ort_runtime
from hybrid_editor.engines.max_quality import MaxQualityEngine
from hybrid_editor.engines.vram import status as vram_status
from hybrid_editor.media.video_io import probe_video
from hybrid_editor.timeline import TimelineDoc, plan_frame


@dataclass
class BakeQueueItem:
    out_dir: str
    max_frames: Optional[int]
    timeline_all: bool
    label: str = ""


class EditorSession:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self.mode: EngineMode = EngineMode.GYORS
        self.engine: MattingEngine = create_engine(self.mode)
        self.media: Optional[MediaInfo] = None
        self.timeline: Optional[TimelineDoc] = None
        self.last_bake: Optional[BakeResult] = None
        self.bake_progress: float = 0.0
        self.bake_status: str = ""
        self.bake_running: bool = False
        self._bake_thread: Optional[threading.Thread] = None
        self._bake_queue: list[BakeQueueItem] = []
        self.analyser = SparseAnalyser()
        self._seed_alpha: Optional[np.ndarray] = None
        self._open_path: Optional[str] = None

    def _seed_path(self) -> Optional[Path]:
        if self.media is None:
            return None
        return ROOT / "cache" / "seeds" / f"{Path(self.media.path).stem}_seed.png"

    def status(self) -> dict[str, Any]:
        with self._lock:
            caps = self.engine.capabilities()
            plan = None
            if self.timeline is not None:
                plan = plan_frame(self.timeline, self.timeline.playhead_sec).to_dict()
            has_broll = bool(
                self.timeline and any(int(c.track) >= 1 for c in self.timeline.clips)
            )
            intel = {
                "mask_store": True,
                "prefetch_ahead": 8,
                "proxy_lanes": True,
                "sparse_analyse": True,
                "seed_paint": self.mode is EngineMode.MAX or self._seed_alpha is not None,
                "quality_pipeline": self.mode is EngineMode.MAX,
                "timeline_multiclip": bool(self.timeline and len(self.timeline.clips) > 1),
                "broll_track": has_broll,
                "export_audio": True,
                "open_output_folder": True,
                "bake_queue": True,
            }
            rvm = probe_ort_runtime()
            # Prefer live engine backend when Fast/Max already loaded ORT
            rvm["engine_backend"] = caps.backend
            rvm["engine_weights"] = caps.weights_path
            live_note = getattr(self.engine, "_status_note", None)
            if live_note is None and hasattr(self.engine, "_rvm"):
                rvm_sess = getattr(self.engine, "_rvm", None)
                live_note = getattr(rvm_sess, "fallback_note", None) if rvm_sess else None
            if live_note:
                rvm["cuda_fallback"] = live_note
            return {
                "sync_version": SYNC_VERSION,
                "mode": self.mode.value,
                "mode_label": "Gyors mód" if self.mode is EngineMode.GYORS else "Max minőségű háttéreltávolítás",
                "engine": caps.name,
                "backend": caps.backend,
                "available": caps.available,
                "license_note": caps.license_note,
                "vram_hint_gb": caps.vram_hint_gb,
                "detail": caps.detail,
                "weights_path": caps.weights_path,
                "media": asdict(self.media) if self.media else None,
                "timeline": self.timeline.to_dict() if self.timeline else None,
                "frame_plan": plan,
                "bake_progress": self.bake_progress,
                "bake_status": self.bake_status,
                "bake_running": self.bake_running,
                "bake_queue_len": len(self._bake_queue),
                "bake_queue": [
                    {"out_dir": q.out_dir, "max_frames": q.max_frames, "label": q.label}
                    for q in self._bake_queue
                ],
                "last_bake": asdict(self.last_bake) if self.last_bake else None,
                "vram": vram_status(),
                "rvm": rvm,
                "seed_mask": self._seed_alpha is not None,
                "mask_rate": MASK_RATE,
                "intelligence": intel,
                **self.analyser.status(),
            }

    def set_mode(self, mode: str) -> dict[str, Any]:
        with self._lock:
            if self.bake_running:
                raise RuntimeError("Bake fut — várj, vagy ne válts módot közben")
            new_mode = resolve_mode(mode)
            if new_mode is self.mode and self.engine.mode is new_mode:
                return self.status()
            media_path = self.media.path if self.media else None
            seed = self._seed_alpha
            old = self.engine
            old.close()
            self.mode = new_mode
            self.engine = create_engine(new_mode)
            if media_path:
                self.media = self.engine.open_media(Path(media_path))
                self._open_path = media_path
                self._ensure_timeline(reset=False)
            self._apply_seed_to_engine(seed)
            return self.status()

    def _apply_seed_to_engine(self, seed: Optional[np.ndarray]) -> None:
        self._seed_alpha = seed
        if isinstance(self.engine, MaxQualityEngine):
            if seed is not None:
                self.engine.set_user_seed(seed)
            else:
                self.engine.clear_user_seed()

    def _ensure_timeline(self, *, reset: bool = False) -> None:
        if self.media is None:
            self.timeline = None
            return
        if reset or self.timeline is None or not self.timeline.clips:
            self.timeline = TimelineDoc.from_media(
                path=self.media.path,
                duration_sec=self.media.duration_sec,
                fps=self.media.fps,
                width=self.media.width,
                height=self.media.height,
            )
            return
        # If primary media path changed and no matching clip, rebuild
        paths = {c.media_path for c in self.timeline.clips}
        if self.media.path not in paths:
            self.timeline = TimelineDoc.from_media(
                path=self.media.path,
                duration_sec=self.media.duration_sec,
                fps=self.media.fps,
                width=self.media.width,
                height=self.media.height,
            )

    def open_media(
        self,
        path: str | Path,
        *,
        append: bool = False,
        track: int = 0,
        as_broll: bool = False,
    ) -> dict[str, Any]:
        with self._lock:
            if self.bake_running:
                raise RuntimeError("Bake fut — előbb várj")
            path = Path(path)
            info = probe_video(path)
            use_track = 1 if as_broll else max(0, int(track))
            if append and self.timeline is not None and self.timeline.clips:
                if use_track >= 1:
                    self.timeline.add_broll(
                        media_path=info.path,
                        duration_sec=info.duration_sec,
                        fps=info.fps,
                        width=info.width,
                        height=info.height,
                        label=Path(info.path).name,
                    )
                else:
                    self.timeline.add_clip(
                        media_path=info.path,
                        duration_sec=info.duration_sec,
                        fps=info.fps,
                        width=info.width,
                        height=info.height,
                    )
                # Keep engine on newly added media for preview convenience
                self.media = self.engine.open_media(path)
                self._open_path = info.path
                # Do not wipe V1 seed when adding B-roll
                if use_track == 0:
                    self._seed_alpha = None
                    if isinstance(self.engine, MaxQualityEngine):
                        self.engine.clear_user_seed()
            else:
                self.media = self.engine.open_media(path)
                self._open_path = info.path
                self.last_bake = None
                self.bake_progress = 0.0
                self.bake_status = ""
                self._seed_alpha = None
                if isinstance(self.engine, MaxQualityEngine):
                    self.engine.clear_user_seed()
                self._ensure_timeline(reset=True)
                # Restore seed from disk if present (survives reload)
                sp = self._seed_path()
                if sp is not None:
                    loaded = load_seed(sp)
                    if loaded is not None:
                        self._apply_seed_to_engine(loaded)
            return self.status()

    def update_timeline(
        self,
        *,
        playhead_sec: Optional[float] = None,
        in_sec: Optional[float] = None,
        out_sec: Optional[float] = None,
        clip_id: Optional[str] = None,
        selected_clip_id: Optional[str] = None,
    ) -> dict[str, Any]:
        with self._lock:
            if self.timeline is None:
                raise RuntimeError("Open a video first")
            if selected_clip_id:
                self.timeline.select_clip(selected_clip_id)
            if in_sec is not None or out_sec is not None:
                self.timeline.set_trim(in_sec=in_sec, out_sec=out_sec, clip_id=clip_id)
            if playhead_sec is not None:
                self.timeline.set_playhead(playhead_sec)
            return self.status()

    def timeline_action(self, action: str, **kwargs: Any) -> dict[str, Any]:
        with self._lock:
            if self.timeline is None:
                raise RuntimeError("Open a video first")
            act = action.strip().lower()
            if act == "duplicate":
                self.timeline.duplicate_selected()
            elif act == "remove":
                if not self.timeline.remove_clip(kwargs.get("clip_id")):
                    raise RuntimeError("Cannot remove last V1 clip")
            elif act == "cut":
                t = kwargs.get("t_sec")
                if not self.timeline.cut_at_playhead(None if t is None else float(t)):
                    raise RuntimeError("Cut failed — move playhead inside a clip")
            elif act == "move":
                cid = kwargs.get("clip_id") or self.timeline.selected_clip_id
                direction = int(kwargs.get("direction", 0))
                if not cid or not self.timeline.move_clip(cid, direction=direction):
                    raise RuntimeError("Cannot move clip")
            elif act == "select":
                cid = kwargs.get("clip_id")
                if not cid:
                    raise RuntimeError("clip_id required")
                self.timeline.select_clip(cid)
            elif act == "add_sample_dup":
                self.timeline.duplicate_selected()
            elif act in {"promote_broll", "to_broll"}:
                cid = kwargs.get("clip_id") or self.timeline.selected_clip_id
                clip = self.timeline._find(cid)
                if clip is None:
                    raise RuntimeError("No clip to move to B-roll")
                if int(clip.track) >= 1:
                    return self.status()
                # Keep at least one V1
                if len(self.timeline.clips_on(0)) <= 1:
                    raise RuntimeError("Need another V1 clip before promoting to B-roll")
                clip.track = 1
                clip.timeline_start_sec = float(self.timeline.playhead_sec)
                clip.opacity = 0.85
                self.timeline.relayout_sequential()
            elif act in {"to_v1", "demote_broll"}:
                cid = kwargs.get("clip_id") or self.timeline.selected_clip_id
                clip = self.timeline._find(cid)
                if clip is None:
                    raise RuntimeError("No clip")
                clip.track = 0
                clip.opacity = 1.0
                self.timeline.relayout_sequential()
            else:
                raise ValueError(f"Unknown timeline action: {action}")
            return self.status()

    def get_frame_plan(self, t_sec: Optional[float] = None) -> dict[str, Any]:
        with self._lock:
            if self.timeline is None:
                raise RuntimeError("Open a video first")
            t = self.timeline.playhead_sec if t_sec is None else float(t_sec)
            return plan_frame(self.timeline, t).to_dict()

    def _ensure_engine_media(self, media_path: str) -> None:
        if self._open_path == media_path and self.media is not None:
            return
        self.media = self.engine.open_media(Path(media_path))
        self._open_path = media_path
        # Re-apply seed for Max when switching media
        if isinstance(self.engine, MaxQualityEngine) and self._seed_alpha is not None:
            self.engine.set_user_seed(self._seed_alpha)

    def preview(self, t_sec: float = 0.0) -> PreviewFrame:
        with self._lock:
            if self.media is None and (self.timeline is None or not self.timeline.clips):
                raise RuntimeError("Open a video first")
            source_t = float(t_sec)
            overlay_meta: dict[str, Any] = {}
            if self.timeline is not None:
                self.timeline.set_playhead(t_sec)
                plan = plan_frame(self.timeline, self.timeline.playhead_sec)
                if plan.layers:
                    # Prefer V1 for matting engine; note overlays for UI
                    v1 = next((L for L in plan.layers if int(L.track) == 0), plan.layers[0])
                    source_t = v1.source_t_sec
                    self._ensure_engine_media(v1.media_path)
                    overlays = [L for L in plan.layers if int(L.track) >= 1]
                    if overlays:
                        overlay_meta = {
                            "overlay_layers": [
                                {
                                    "clip_id": L.clip_id,
                                    "media_path": L.media_path,
                                    "source_t_sec": L.source_t_sec,
                                    "opacity": L.opacity,
                                    "track": L.track,
                                }
                                for L in overlays
                            ]
                        }
            try:
                frame = self.engine.preview_frame(source_t)
            except Exception as exc:  # noqa: BLE001
                # Soft-fail at session boundary: still return source RGB so UI is never blank checker.
                from hybrid_editor.media.video_io import (
                    encode_source_only_preview,
                    read_frame_at,
                )

                if self.media is None:
                    raise
                bgr, t = read_frame_at(Path(self.media.path), source_t)
                jpg, png, w, h, src, _empty = encode_source_only_preview(bgr)
                frame = PreviewFrame(
                    t_sec=t,
                    width=w,
                    height=h,
                    jpeg_b64=jpg,
                    alpha_png_b64=png,
                    engine=getattr(self.engine, "__class__", type(self.engine)).__name__,
                    backend=str(getattr(self.engine, "_backend", "unknown")),
                    meta={
                        "matte_empty": True,
                        "source_fallback": True,
                        "matte_error": str(exc)[:240],
                    },
                    source_jpeg_b64=src,
                )
            if overlay_meta:
                frame.meta = {**(frame.meta or {}), **overlay_meta}
            if self._seed_alpha is not None:
                frame.meta = {**(frame.meta or {}), "user_seed": True, "seed_bound": True}
            return frame

    def start_analyse(
        self,
        *,
        mask_rate: float = MASK_RATE,
        max_span_sec: Optional[float] = None,
    ) -> dict[str, Any]:
        """Sparse MaskStore pre-analyse — background, does not block scrub UI."""
        with self._lock:
            if self.media is None:
                raise RuntimeError("Open a video first")
            if self.bake_running:
                raise RuntimeError("Bake fut — analyse később")
            # Analyse uses Fast backbone matte; Max mode temporarily uses fast._matte
            if self.mode is EngineMode.MAX and isinstance(self.engine, MaxQualityEngine):
                matte_fn = self.engine._fast._matte
                model_id = f"analyse-{self.engine._fast.capabilities().backend}"
            else:
                matte_fn = self.engine._matte  # type: ignore[attr-defined]
                model_id = f"analyse-{self.engine.capabilities().backend}"

            in_sec = 0.0
            out_sec = float(self.media.duration_sec)
            if self.timeline and self.timeline.clips:
                # Cover full timeline media of selected clip (source range)
                sel = self.timeline._find()
                if sel is not None:
                    # Ensure engine on that media
                    self._ensure_engine_media(sel.media_path)
                    in_sec = float(sel.in_sec)
                    out_sec = float(sel.effective_out())
            if max_span_sec is not None and max_span_sec > 0:
                out_sec = min(out_sec, in_sec + float(max_span_sec))

            media_path = Path(self.media.path)
            duration = float(self.media.duration_sec)

            def _prog(p: float, msg: str) -> None:
                # status already updated inside analyser
                pass

            return self.analyser.start(
                root=ROOT,
                media_path=media_path,
                duration_sec=duration,
                matte_fn=matte_fn,
                model_id=model_id,
                mask_rate=mask_rate,
                in_sec=in_sec,
                out_sec=out_sec,
                progress=_prog,
            )

    def set_seed_mask(self, png_b64: str) -> dict[str, Any]:
        with self._lock:
            if self.media is None:
                raise RuntimeError("Open a video first")
            alpha = decode_alpha_png_b64(png_b64)
            # Match preview proxy-ish size is fine; bake resizes
            self._apply_seed_to_engine(alpha)
            sp = self._seed_path()
            if sp is not None:
                save_seed(sp, alpha)
            st = self.status()
            st["seed_mask_png_b64"] = encode_alpha_png_b64(alpha)
            return st

    def get_seed_mask(self) -> dict[str, Any]:
        with self._lock:
            if self._seed_alpha is None:
                return {"seed_mask": False, "seed_mask_png_b64": None}
            return {
                "seed_mask": True,
                "seed_mask_png_b64": encode_alpha_png_b64(self._seed_alpha),
                "width": int(self._seed_alpha.shape[1]),
                "height": int(self._seed_alpha.shape[0]),
            }

    def clear_seed_mask(self) -> dict[str, Any]:
        with self._lock:
            self._apply_seed_to_engine(None)
            sp = self._seed_path()
            if sp is not None and sp.is_file():
                try:
                    sp.unlink()
                except OSError:
                    pass
            return self.status()

    def _bake_timeline_multiclip(
        self,
        out_dir: Path,
        *,
        max_frames: Optional[int],
        progress,
    ) -> BakeResult:
        """Walk FramePlan across all clips — Concat-like shared plan bake + audio."""
        import cv2

        from hybrid_editor.export.composer import (
            AudioSegment,
            media_has_audio,
            write_preview_mp4,
            write_windows_companion,
        )
        from hybrid_editor.media.video_io import downscale_long_side, read_frame_at
        from hybrid_editor.timeline import plan_frame as _plan

        assert self.timeline is not None
        out_dir = Path(out_dir)
        alpha_dir = out_dir / "alpha"
        alpha_dir.mkdir(parents=True, exist_ok=True)
        fps = float(self.timeline.fps) or 25.0
        dur = self.timeline.duration_sec()
        step = 1.0 / fps
        limit = max_frames if max_frames is not None and max_frames > 0 else 10**9
        frames_bgr: list = []
        frames_alpha: list = []
        written = 0
        t = 0.0
        total_est = int(max(1, round(dur * fps)))
        if max_frames is not None:
            total_est = min(total_est, max_frames)

        # Prefer Fast matte for timeline scrub-bake speed; Max polish if mode=max
        while t < dur - 1e-9 and written < limit:
            plan = _plan(self.timeline, t)
            if plan.empty or not plan.layers:
                t += step
                continue
            v1 = next((L for L in plan.layers if int(L.track) == 0), plan.layers[0])
            overlays = [L for L in plan.layers if int(L.track) >= 1]
            self._ensure_engine_media(v1.media_path)
            bgr, _ = read_frame_at(Path(v1.media_path), v1.source_t_sec)
            bgr = downscale_long_side(bgr, 720)
            if self.mode is EngineMode.MAX and isinstance(self.engine, MaxQualityEngine):
                alpha = self.engine._polish(bgr, warmup=(written == 0))
            else:
                alpha = self.engine._matte(bgr)  # type: ignore[attr-defined]
            alpha = alpha.astype(np.float32)
            # Composite V2 B-roll over cutout (opaque overlay at clip opacity)
            for ov in overlays:
                try:
                    obgr, _ = read_frame_at(Path(ov.media_path), ov.source_t_sec)
                    obgr = downscale_long_side(obgr, 720)
                    if obgr.shape[:2] != bgr.shape[:2]:
                        obgr = cv2.resize(obgr, (bgr.shape[1], bgr.shape[0]), interpolation=cv2.INTER_AREA)
                    op = float(ov.opacity)
                    bgr = (
                        bgr.astype(np.float32) * (1.0 - op) + obgr.astype(np.float32) * op
                    ).astype(np.uint8)
                    # Where overlay sits, force alpha full so B-roll shows on checker
                    alpha = np.maximum(alpha, op)
                except Exception:  # noqa: BLE001
                    pass
            a8 = (np.clip(alpha, 0, 1) * 255).astype(np.uint8)
            cv2.imwrite(str(alpha_dir / f"{written:06d}.png"), a8)
            frames_bgr.append(bgr)
            frames_alpha.append(alpha.astype(np.float32))
            written += 1
            if progress:
                progress(min(0.85, written / max(total_est, 1)), f"Timeline bake {written}/{total_est}")
            t += step

        preview_mp4 = None
        companion = None
        audio_ok = False
        if written:
            if progress:
                progress(0.9, "Export preview.mp4 + audio…")
            # Audio from V1 clips in timeline order (source trims)
            audio_segs = [
                AudioSegment(
                    path=c.media_path,
                    in_sec=float(c.in_sec),
                    out_sec=float(c.effective_out()),
                    timeline_start_sec=float(c.timeline_start_sec),
                )
                for c in self.timeline.clips_on(0)
            ]
            preview_mp4 = write_preview_mp4(
                frames_bgr,
                frames_alpha,
                out_dir / "preview.mp4",
                fps=fps,
                audio_segments=audio_segs,
                audio_duration_sec=dur,
            )
            audio_ok = bool(preview_mp4) and media_has_audio(preview_mp4)
            companion = write_windows_companion(preview_mp4, out_dir)
            if progress:
                progress(1.0, "Bake kész")

        n_broll = len(self.timeline.clips_on(1))
        audio_note = " · audio AAC" if audio_ok else ""
        broll_note = f" · {n_broll} B-roll" if n_broll else ""
        return BakeResult(
            ok=written > 0,
            out_dir=str(out_dir.resolve()),
            frames_written=written,
            engine=self.engine.capabilities().name,
            backend=self.engine.capabilities().backend,
            message=(
                f"Multi-clip timeline bake: {written} frames · "
                f"{len(self.timeline.clips)} clips{broll_note}{audio_note}"
            ),
            alpha_preview=str(alpha_dir / "000000.png") if written else None,
            preview_mp4=companion or preview_mp4,
            bake_range={
                "in_sec": 0.0,
                "out_sec": dur,
                "clips": len(self.timeline.clips),
                "broll": n_broll,
                "audio": audio_ok,
            },
        )

    def open_output_folder(self, out_dir: Optional[str] = None) -> dict[str, Any]:
        """Reveal last bake (or given) folder in the OS file manager."""
        with self._lock:
            path: Optional[Path] = None
            if out_dir:
                path = Path(out_dir).expanduser()
            elif self.last_bake and self.last_bake.out_dir:
                path = Path(self.last_bake.out_dir)
            else:
                path = ROOT / "cache" / "bake" / self.mode.value
            path = path.resolve()
            if not path.exists():
                path.mkdir(parents=True, exist_ok=True)
            opened = False
            error: Optional[str] = None
            try:
                if sys.platform.startswith("win"):
                    os.startfile(str(path))  # type: ignore[attr-defined]
                    opened = True
                elif sys.platform == "darwin":
                    subprocess.run(["open", str(path)], check=False, timeout=15)
                    opened = True
                else:
                    opener = "xdg-open"
                    if os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY"):
                        subprocess.run([opener, str(path)], check=False, timeout=15)
                        opened = True
                    else:
                        error = "No display — folder path returned only"
            except Exception as exc:  # noqa: BLE001
                error = str(exc)
            return {
                "ok": True,
                "opened": opened,
                "out_dir": str(path),
                "error": error,
            }

    def bake(
        self,
        out_dir: str | Path,
        *,
        max_frames: Optional[int] = 30,
        async_job: bool = False,
        timeline_all: bool = True,
        queue_if_busy: bool = True,
        label: str = "",
    ) -> BakeResult | dict[str, Any]:
        with self._lock:
            if self.media is None:
                raise RuntimeError("Open a video first")
            if self.analyser.state.running:
                raise RuntimeError("Analyse fut — bake később (VRAM / CPU)")

            out_dir_s = str(Path(out_dir))
            if self.bake_running:
                if not queue_if_busy or not async_job:
                    raise RuntimeError("Bake already running")
                item = BakeQueueItem(
                    out_dir=out_dir_s,
                    max_frames=max_frames,
                    timeline_all=timeline_all,
                    label=label or f"bake-{len(self._bake_queue) + 1}",
                )
                self._bake_queue.append(item)
                self.bake_status = f"Sorba téve ({len(self._bake_queue)} várakozik)"
                return {
                    **self.status(),
                    "queued": True,
                    "bake_status": self.bake_status,
                }

            return self._start_bake(
                out_dir_s,
                max_frames=max_frames,
                async_job=async_job,
                timeline_all=timeline_all,
            )

    def _start_bake(
        self,
        out_dir: str,
        *,
        max_frames: Optional[int],
        async_job: bool,
        timeline_all: bool,
    ) -> BakeResult | dict[str, Any]:
        # Multi-clip bake when >1 clip OR any B-roll overlay present
        multi = bool(
            timeline_all
            and self.timeline
            and (
                len(self.timeline.clips) > 1
                or any(int(c.track) >= 1 for c in self.timeline.clips)
            )
        )

        # Single-clip: bake selected clip source range via engine
        in_sec = 0.0
        out_sec: Optional[float] = None
        if not multi and self.timeline and self.timeline.clips:
            clip = self.timeline._find()
            if clip is not None:
                self._ensure_engine_media(clip.media_path)
                in_sec = float(clip.in_sec)
                out_sec = float(clip.effective_out())

        def _prog(p: float, msg: str) -> None:
            self.bake_progress = float(p)
            self.bake_status = msg

        def _do_bake() -> BakeResult:
            if multi:
                return self._bake_timeline_multiclip(
                    Path(out_dir), max_frames=max_frames, progress=_prog
                )
            result = self.engine.bake(
                Path(out_dir),
                max_frames=max_frames,
                progress=_prog,
                in_sec=in_sec,
                out_sec=out_sec,
            )
            from hybrid_editor.export.composer import write_windows_companion

            companion = write_windows_companion(result.preview_mp4, Path(out_dir))
            if companion:
                result.preview_mp4 = companion
            return result

        if not async_job:
            self.bake_running = True
            try:
                result = _do_bake()
                self.last_bake = result
                self.bake_progress = 1.0 if result.ok else self.bake_progress
                self.bake_status = result.message
                return result
            finally:
                self.bake_running = False
                self._drain_bake_queue()

        self.bake_running = True
        self.bake_progress = 0.0
        self.bake_status = "Bake indul…"

        def _run() -> None:
            try:
                result = _do_bake()
                with self._lock:
                    self.last_bake = result
                    self.bake_progress = 1.0 if result.ok else self.bake_progress
                    self.bake_status = result.message
            except Exception as exc:  # noqa: BLE001
                with self._lock:
                    self.bake_status = f"Bake hiba: {exc}"
            finally:
                with self._lock:
                    self.bake_running = False
                    self._drain_bake_queue()

        self._bake_thread = threading.Thread(target=_run, daemon=True, name="hybrid-bake")
        self._bake_thread.start()
        return self.status()

    def _drain_bake_queue(self) -> None:
        """Start next queued bake if idle (caller holds lock or is finishing)."""
        if self.bake_running or not self._bake_queue:
            return
        if self.media is None:
            self._bake_queue.clear()
            return
        nxt = self._bake_queue.pop(0)
        self.bake_status = f"Sor következő: {nxt.label or nxt.out_dir}"
        # Fire async without re-queueing into itself
        self._start_bake(
            nxt.out_dir,
            max_frames=nxt.max_frames,
            async_job=True,
            timeline_all=nxt.timeline_all,
        )


SESSION = EditorSession()
