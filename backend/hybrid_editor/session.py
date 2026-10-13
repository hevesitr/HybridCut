"""In-memory editor session — single V1 clip + BG remove (simple-bg)."""

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
from hybrid_editor.cache.seed_mask import encode_alpha_png_b64
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
        self._seed_mode: str = "union"  # auto-person only (paint/wand removed)
        self._seed_part: Optional[str] = None
        self._open_path: Optional[str] = None
        # Default ON for Max/export — CapCut-like needle-sharp person edges.
        self.sharp_edges: bool = True
        # simple-bg6: auto Max on empty Gyors runs at most once per open.
        # Explicit Gyors click sets _suppress_auto_max so UI mode sticks.
        self._auto_max_done: bool = False
        self._suppress_auto_max: bool = False
        self._sync_sharp_to_engine()

    def _sync_sharp_to_engine(self) -> None:
        if isinstance(self.engine, MaxQualityEngine) and hasattr(self.engine, "set_sharp_edges"):
            self.engine.set_sharp_edges(self.sharp_edges)

    def _seed_media_path(self) -> Optional[str]:
        """Seed is per selected clip media (falls back to open media)."""
        if self.timeline is not None:
            sel = self.timeline._find()
            if sel is not None and sel.media_path:
                return sel.media_path
        if self.media is not None:
            return self.media.path
        return None

    def _seed_path(self) -> Optional[Path]:
        media_path = self._seed_media_path()
        if not media_path:
            return None
        return ROOT / "cache" / "seeds" / f"{Path(media_path).stem}_seed.png"

    def _purge_seed_disk(self, sp: Optional[Path] = None) -> None:
        """Delete seed PNG + meta (used for face-only / sticky replace cleanup)."""
        from hybrid_editor.cache.seed_mask import seed_meta_path

        path = sp if sp is not None else self._seed_path()
        if path is None:
            return
        if path.is_file():
            try:
                path.unlink()
            except OSError:
                pass
        mp = seed_meta_path(path)
        if mp.is_file():
            try:
                mp.unlink()
            except OSError:
                pass

    def _purge_mask_store(self, media_path: Optional[str] = None) -> None:
        """Purge MaskStore memory + disk (wand face scraps must not shadow RVM)."""
        import shutil

        from hybrid_editor.cache.mask_store import mask_dir

        fast = getattr(self.engine, "_fast", None) or self.engine
        store = getattr(fast, "_mask_store", None)
        if store is not None and hasattr(store, "purge"):
            store.purge()
        elif store is not None and hasattr(store, "clear_memory"):
            store.clear_memory()
        path = media_path or self._seed_media_path()
        if not path and self.media is not None:
            path = self.media.path
        if path:
            d = mask_dir(ROOT, path, subject="person")
            if d.is_dir():
                shutil.rmtree(d, ignore_errors=True)

    def _ensure_full_person_gyors(self, media_path: Optional[str] = None) -> None:
        """Megnyitás auto-person: stay Gyors (MobileNet scrub) + purge seeds.

        simple-bg: Max only on explicit user choice / export bake — not on open.
        """
        path = media_path or (self.media.path if self.media else None)
        if self.mode is not EngineMode.GYORS:
            old = self.engine
            try:
                old.close()
            except Exception:  # noqa: BLE001
                pass
            self.mode = EngineMode.GYORS
            self.engine = create_engine(EngineMode.GYORS)
            self.sharp_edges = False
            self._sync_sharp_to_engine()
            if path:
                self.media = self.engine.open_media(Path(path))
                self._open_path = path
        else:
            self.sharp_edges = False
            self._sync_sharp_to_engine()
            if path and self._open_path != path:
                self.media = self.engine.open_media(Path(path))
                self._open_path = path
        self._apply_seed_to_engine(None)

    # Compat alias — older tests / callers
    def _ensure_full_person_max(self, media_path: Optional[str] = None) -> None:
        self._ensure_full_person_gyors(media_path)

    def _load_seed_for_selection(self) -> None:
        """Auto-person only: purge any leftover seed PNG and never re-arm paint/wand.

        Pre-wand / apex default — full RVM person matte with no sticky seed gate.
        """
        sp = self._seed_path()
        if sp is not None and sp.is_file():
            self._purge_seed_disk(sp)
        self._purge_mask_store()
        self._apply_seed_to_engine(None)
        if isinstance(self.engine, MaxQualityEngine):
            # Keep auto guidance seed; only drop sticky user/paint state.
            self.engine.set_user_seed(None)

    def _preview_matte_long(self) -> int:
        """Long-side for timeline composite matte decode — Max keeps near-4K detail."""
        if self.mode is EngineMode.MAX and self.sharp_edges:
            try:
                return max(960, int(os.environ.get("HYBRID_MAX_PREVIEW_LONG", "1440") or "1440"))
            except ValueError:
                return 1440
        return 960

    def _bake_matte_long(self) -> int:
        """Long-side for multiclip bake decode — Max prefers native/4K-friendly."""
        if self.mode is EngineMode.MAX:
            try:
                return max(1080, int(os.environ.get("HYBRID_MAX_BAKE_LONG", "2160") or "2160"))
            except ValueError:
                return 2160
        return 720

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
                "sharp_edges": self.sharp_edges,
                "timeline_multiclip": False,
                "broll_track": False,
                "simple_bg": True,
                "export_audio": True,
                "open_output_folder": True,
                "bake_queue": True,
            }
            rvm = probe_ort_runtime()
            # Prefer live engine backend when Fast/Max already loaded ORT
            rvm["engine_backend"] = caps.backend
            rvm["engine_weights"] = caps.weights_path
            live_note = getattr(self.engine, "_status_note", None)
            if live_note is None and hasattr(self.engine, "_fast"):
                # MaxQualityEngine wraps FastEngine — surface CUDA→CPU note from backbone
                fast = getattr(self.engine, "_fast", None)
                live_note = getattr(fast, "_status_note", None) if fast else None
            if live_note is None and hasattr(self.engine, "_rvm"):
                rvm_sess = getattr(self.engine, "_rvm", None)
                live_note = getattr(rvm_sess, "fallback_note", None) if rvm_sess else None
            if live_note:
                rvm["cuda_fallback"] = live_note
            # Honest UI: live CPU session must not keep RVM CUDA / RTX badges.
            live_backend = str(caps.backend or "").lower()
            live_note_s = str(live_note or "")
            if "cpuexecutionprovider" in live_backend or live_backend.endswith(":cpu"):
                rvm["cuda_ep"] = False
                rvm["cuda_ep_registered"] = False
                rvm["ort_label_hu"] = "CPU ORT"
                rvm["prefer"] = "cpu"
            elif live_note_s and (
                "CUDA→CPU" in live_note_s
                or "plugin EP" in live_note_s
                or "CPU ORT" in live_note_s
            ):
                rvm["cuda_ep"] = False
                rvm["cuda_ep_registered"] = False
                rvm["ort_label_hu"] = "CPU ORT"
                rvm["prefer"] = "cpu"
            person_info: dict[str, Any] = {}
            if isinstance(self.engine, MaxQualityEngine) and hasattr(self.engine, "person_matte_info"):
                person_info = self.engine.person_matte_info()
            elif self.mode is EngineMode.GYORS:
                person_info = {
                    "matanyone2_active": False,
                    "person_matte_backend": "rvm-gyors",
                    "person_matte_label_hu": "Gyors RVM ember-maszk",
                    "auto_person_matte": True,
                    "manual_seed_refinement_only": True,
                }
            mode_label = (
                "Gyors — gyors/lágyabb scrub"
                if self.mode is EngineMode.GYORS
                else "Max — élesebb export"
            )
            return {
                "sync_version": SYNC_VERSION,
                "mode": self.mode.value,
                "mode_label": mode_label,
                "engine": caps.name,
                "backend": caps.backend,
                "available": caps.available,
                "license_note": caps.license_note,
                "vram_hint_gb": caps.vram_hint_gb,
                "detail": caps.detail,
                "weights_path": caps.weights_path,
                "sharp_edges": self.sharp_edges,
                "matanyone2_active": bool(person_info.get("matanyone2_active")),
                "person_matte_label_hu": person_info.get("person_matte_label_hu"),
                "person_matte_backend": person_info.get("person_matte_backend"),
                "person_matte": person_info or None,
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
                "seed_mode": self._seed_mode if self._seed_alpha is not None else "union",
                "seed_part": self._seed_part if self._seed_alpha is not None else None,
                "seed_part_label_hu": (
                    {"face": "Arc", "region": "Rész"}.get(self._seed_part or "", None)
                    if self._seed_alpha is not None and self._seed_part
                    else None
                ),
                # True unless Varázsceruza face/part replace is active this session.
                "full_person_matte": not (
                    self._seed_alpha is not None and self._seed_mode == "replace"
                ),
                "mask_rate": MASK_RATE,
                "intelligence": intel,
                **self.analyser.status(),
            }

    def set_mode(self, mode: str) -> dict[str, Any]:
        with self._lock:
            if self.bake_running:
                raise RuntimeError("Bake fut — várj, vagy ne válts módot közben")
            new_mode = resolve_mode(mode)

            def _drop_near_empty_seed(seed: Optional[np.ndarray]) -> Optional[np.ndarray]:
                if seed is None:
                    return None
                s = np.asarray(seed, dtype=np.float32)
                if s.ndim == 3:
                    s = s[..., 0]
                if float(s.max()) < 0.05 or float((s > 0.15).mean()) < 0.002:
                    self._seed_alpha = None
                    return None
                return seed

            if new_mode is self.mode and self.engine.mode is new_mode:
                # Already on target mode (Megnyitás stays Gyors) — still sanitize
                # near-empty paint leftovers and recommend Előnézet.
                # User re-clicked Gyors: keep mode locked (no preview auto-Max).
                if new_mode is EngineMode.GYORS:
                    self._suppress_auto_max = True
                seed = _drop_near_empty_seed(self._seed_alpha)
                if seed is None:
                    self._apply_seed_to_engine(None)
                st = self.status()
                if new_mode is EngineMode.MAX:
                    st = {
                        **st,
                        "auto_preview_recommended": True,
                        "person_matte_hint_hu": (
                            st.get("person_matte_label_hu")
                            or "MatAnyone2 nincs — RVM ember-maszk"
                        ),
                    }
                return st
            media_path = self.media.path if self.media else None
            # Near-empty kézi seed must not travel into Max (old wipe path / stale UI).
            seed = _drop_near_empty_seed(self._seed_alpha)
            # Explicit mode click: Gyors must stick; Max allows future auto once reset.
            if new_mode is EngineMode.GYORS:
                self._suppress_auto_max = True
                self.sharp_edges = False  # scrub soft
            else:
                self._suppress_auto_max = False
                self.sharp_edges = True  # Max export: apex / CPU_MAX sharp
            old = self.engine
            old.close()
            self.mode = new_mode
            self.engine = create_engine(new_mode)
            self._sync_sharp_to_engine()
            if media_path:
                self.media = self.engine.open_media(Path(media_path))
                self._open_path = media_path
                self._ensure_timeline(reset=False)
                # Drop in-memory MaskStore after mode switch so empty Gyors caches
                # cannot shadow a fresh Max RVM / ResNet matte on the same path.
                fast = getattr(self.engine, "_fast", None) or self.engine
                store = getattr(fast, "_mask_store", None)
                if store is not None and hasattr(store, "clear_memory"):
                    store.clear_memory()
            self._apply_seed_to_engine(seed)
            st = self.status()
            if new_mode is EngineMode.MAX:
                st = {
                    **st,
                    "auto_preview_recommended": True,
                    "person_matte_hint_hu": (
                        st.get("person_matte_label_hu")
                        or "MatAnyone2 nincs — RVM ember-maszk"
                    ),
                }
            return st

    def set_sharp_edges(self, enabled: bool) -> dict[str, Any]:
        """Toggle CapCut-like sharp person edges (default on for Max/export)."""
        with self._lock:
            self.sharp_edges = bool(enabled)
            self._sync_sharp_to_engine()
            return self.status()

    def new_project(self) -> dict[str, Any]:
        """Új projekt / Kilépés — clear timeline, media, seeds, bake; empty drop again."""
        from hybrid_editor.cache.analyse import AnalyseStatus

        with self._lock:
            if self.bake_running:
                raise RuntimeError("Bake fut — várj, mielőtt új projektet nyitsz")
            self.analyser.cancel()
            self.analyser.state = AnalyseStatus()
            self._bake_queue.clear()
            self.last_bake = None
            self.bake_progress = 0.0
            self.bake_status = ""
            self._seed_alpha = None
            self.media = None
            self.timeline = None
            self._open_path = None
            self._auto_max_done = False
            self._suppress_auto_max = False
            try:
                self.engine.reset()
            except Exception:  # noqa: BLE001
                pass
            fast = getattr(self.engine, "_fast", None) or self.engine
            store = getattr(fast, "_mask_store", None)
            if store is not None and hasattr(store, "clear_memory"):
                store.clear_memory()
            prefetch = getattr(fast, "_prefetch", None)
            if prefetch is not None and hasattr(prefetch, "reset"):
                prefetch.reset()
            if isinstance(self.engine, MaxQualityEngine):
                self.engine.clear_user_seed()
            return self.status()

    def _apply_seed_to_engine(
        self,
        seed: Optional[np.ndarray],
        *,
        mode: Optional[str] = None,
        part: Optional[str] = None,
    ) -> None:
        if mode is not None:
            m = str(mode).strip().lower()
            self._seed_mode = "replace" if m == "replace" else "union"
        if part is not None:
            self._seed_part = str(part).strip() or None
        if seed is None:
            self._seed_alpha = None
            self._seed_mode = "union"
            self._seed_part = None
        else:
            self._seed_alpha = seed
        if isinstance(self.engine, MaxQualityEngine):
            if seed is not None:
                self.engine.set_user_seed(
                    seed, mode=self._seed_mode, part=self._seed_part
                )
            else:
                self.engine.clear_user_seed()
            # Drop live quality-seed cache so next preview/bake re-reads mode.
            self.engine._seed = None  # noqa: SLF001

    def _ensure_timeline(self, *, reset: bool = False, has_alpha: bool = False) -> None:
        from hybrid_editor.media.video_io import looks_like_alpha_media

        if self.media is None:
            self.timeline = None
            return
        alpha_flag = bool(has_alpha) or looks_like_alpha_media(self.media.path)
        if reset or self.timeline is None or not self.timeline.clips:
            self.timeline = TimelineDoc.from_media(
                path=self.media.path,
                duration_sec=self.media.duration_sec,
                fps=self.media.fps,
                width=self.media.width,
                height=self.media.height,
                has_alpha=alpha_flag,
                label="nobg" if alpha_flag else "",
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
                has_alpha=alpha_flag,
                label="nobg" if alpha_flag else "",
            )

    def open_media(
        self,
        path: str | Path,
        *,
        append: bool = False,
        track: int = 0,
        as_broll: bool = False,
        as_nobg: bool = False,
    ) -> dict[str, Any]:
        """simple-bg: one V1 clip only. Ignore append / B-roll / nobg stack flags."""
        from hybrid_editor.media.video_io import looks_like_alpha_media

        with self._lock:
            if self.bake_running:
                raise RuntimeError("Bake fut — előbb várj")
            path = Path(path)
            info = probe_video(path)
            is_nobg = bool(as_nobg) or looks_like_alpha_media(path)
            # Reject multi-clip / multi-track stacking — always replace single V1.
            _ = (append, track, as_broll)  # ignored (compat API)
            self.last_bake = None
            self.bake_progress = 0.0
            self.bake_status = ""
            self._seed_alpha = None
            self._seed_mode = "union"
            self._seed_part = None
            # Gyors-first auto person: MobileNet scrub + MaskStore purge (no Max-on-open).
            self._purge_seed_disk()
            self._purge_mask_store(info.path)
            self._auto_max_done = False
            self._suppress_auto_max = False
            if self.mode is not EngineMode.GYORS:
                try:
                    self.engine.close()
                except Exception:  # noqa: BLE001
                    pass
                self.mode = EngineMode.GYORS
                self.engine = create_engine(EngineMode.GYORS)
            self.sharp_edges = False
            self._sync_sharp_to_engine()
            self.media = self.engine.open_media(path)
            self._open_path = info.path
            self._ensure_timeline(reset=True, has_alpha=is_nobg)
            if isinstance(self.engine, MaxQualityEngine):
                self.engine.set_user_seed(None)
            self._apply_seed_to_engine(None)
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
                    raise RuntimeError("Nincs törölhető klip")
                if not self.timeline.clips:
                    # Empty timeline after last clip delete — clear engine media.
                    self.media = None
                    self._open_path = None
                    self._seed_alpha = None
                    self._seed_mode = "union"
                    self._seed_part = None
                    if isinstance(self.engine, MaxQualityEngine):
                        self.engine.clear_user_seed()
                        self.engine._seed = None  # noqa: SLF001
                    self.last_bake = None
                else:
                    sel = self.timeline._find(self.timeline.selected_clip_id)
                    if sel is not None:
                        self._ensure_engine_media(sel.media_path)
                    self._load_seed_for_selection()
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
                sel = self.timeline._find(cid)
                if sel is not None:
                    self._ensure_engine_media(sel.media_path)
                self._load_seed_for_selection()
            elif act == "add_sample_dup":
                self.timeline.duplicate_selected()
            elif act in {"promote_broll", "to_broll", "set_track"}:
                cid = kwargs.get("clip_id") or self.timeline.selected_clip_id
                if act == "set_track":
                    track = int(kwargs.get("track", 1))
                    start = kwargs.get("timeline_start_sec")
                    if not cid or not self.timeline.set_track(
                        cid,
                        track,
                        timeline_start_sec=None if start is None else float(start),
                    ):
                        raise RuntimeError("Cannot move clip to that track")
                else:
                    clip = self.timeline._find(cid)
                    if clip is None:
                        raise RuntimeError("No clip to move to AI sáv")
                    if int(clip.track) >= 1:
                        return self._status_with_ai_polish(clip.clip_id)
                    if not self.timeline.set_track(
                        cid, 1, timeline_start_sec=float(self.timeline.playhead_sec)
                    ):
                        raise RuntimeError("Need another V1 clip before promoting to AI sáv")
                moved = self.timeline._find(cid)
                if moved is not None and int(moved.track) >= 1 and not moved.has_alpha:
                    return self._status_with_ai_polish(moved.clip_id, recommend=True)
            elif act in {"to_v1", "demote_broll"}:
                cid = kwargs.get("clip_id") or self.timeline.selected_clip_id
                if not cid or not self.timeline.set_track(cid, 0):
                    raise RuntimeError("No clip")
            elif act in {"ai_polish", "polish", "polirozas"}:
                return self.polish_ai_clip(kwargs.get("clip_id"))
            elif act in {"place", "set_start"}:
                cid = kwargs.get("clip_id") or self.timeline.selected_clip_id
                start = kwargs.get("timeline_start_sec")
                if cid is None or start is None:
                    raise RuntimeError("clip_id and timeline_start_sec required")
                if not self.timeline.set_timeline_start(cid, float(start)):
                    raise RuntimeError("Cannot place clip")
            elif act in {"trim_edge", "trim"}:
                cid = kwargs.get("clip_id") or self.timeline.selected_clip_id
                edge = str(kwargs.get("edge") or "out")
                t = kwargs.get("timeline_t")
                if cid is None or t is None:
                    raise RuntimeError("clip_id and timeline_t required")
                if not self.timeline.trim_edge(cid, edge=edge, timeline_t=float(t)):
                    raise RuntimeError("Trim failed")
            elif act in {"set_transform", "transform"}:
                cid = kwargs.get("clip_id") or self.timeline.selected_clip_id
                if not self.timeline.set_transform(
                    cid,
                    pos_x=kwargs.get("pos_x"),
                    pos_y=kwargs.get("pos_y"),
                    scale=kwargs.get("scale"),
                    opacity=kwargs.get("opacity"),
                ):
                    raise RuntimeError("Nincs klip a pozícióhoz / mérethez")
            elif act in {"reset_transform", "reset_pos"}:
                cid = kwargs.get("clip_id") or self.timeline.selected_clip_id
                if not self.timeline.reset_transform(cid):
                    raise RuntimeError("Nincs klip a visszaállításhoz")
            else:
                raise ValueError(f"Unknown timeline action: {action}")
            return self.status()

    def _status_with_ai_polish(
        self,
        clip_id: Optional[str],
        *,
        recommend: bool = False,
    ) -> dict[str, Any]:
        st = self.status()
        clip = None
        if self.timeline is not None and clip_id:
            clip = self.timeline._find(clip_id)
        status = (clip.ai_polish if clip is not None else "idle") or "idle"
        # simple-bg3: polish lane removed — never advertise AI sáv in status payload.
        label_map = {
            "pending": "",
            "running": "",
            "done": "",
            "error": "",
            "idle": "",
        }
        st["ai_polish"] = {
            "clip_id": clip_id,
            "status": "idle",
            "label_hu": "",
            "lane_label_hu": "",
        }
        if recommend and clip_id and status in {"pending", "idle", "error"}:
            st["ai_polish_recommended"] = clip_id
        return st

    def polish_ai_clip(self, clip_id: Optional[str] = None) -> dict[str, Any]:
        """Run existing RVM/APEX polish on an AI-sáv (stacked) clip — no new model.

        Keeps full-person default (does not set seed_mode=replace / face-only).
        """
        with self._lock:
            if self.timeline is None:
                raise RuntimeError("Open a video first")
            clip = self.timeline._find(clip_id)
            if clip is None:
                raise RuntimeError("Nincs klip a polírozáshoz")
            # Stack onto AI sáv when another V1 remains (hand-drag multi-track)
            if int(clip.track) == 0 and len(self.timeline.clips_on(0)) > 1:
                if not self.timeline.set_track(
                    clip.clip_id, 1, timeline_start_sec=float(clip.timeline_start_sec)
                ):
                    raise RuntimeError("Nem lehet AI sávra tenni")
                clip = self.timeline._find(clip.clip_id)
            if clip is None:
                raise RuntimeError("Nincs klip a polírozáshoz")
            clip.ai_lane = True
            clip.ai_polish = "running"
            self.timeline.selected_clip_id = clip.clip_id
            mid_tl = float(clip.timeline_start_sec) + 0.5 * clip.source_duration()
            self.timeline.set_playhead(mid_tl)

            # Ensure Max + Éles szélek — auto full-person RVM only (no paint/wand seed).
            self._apply_seed_to_engine(None)
            self._purge_seed_disk()
            self._purge_mask_store(clip.media_path)
            if self.mode is not EngineMode.MAX:
                media_path = clip.media_path
                old = self.engine
                old.close()
                self.mode = EngineMode.MAX
                self.engine = create_engine(EngineMode.MAX)
                self.sharp_edges = True
                self._sync_sharp_to_engine()
                self.media = self.engine.open_media(Path(media_path))
                self._open_path = media_path
                self._apply_seed_to_engine(None)
            else:
                self.sharp_edges = True
                self._sync_sharp_to_engine()
                self._ensure_engine_media(clip.media_path)
                self._load_seed_for_selection()

            try:
                from hybrid_editor.media.video_io import downscale_long_side, is_matte_empty, read_frame_at

                src_t = float(clip.in_sec) + 0.5 * clip.source_duration()
                bgr, _t = read_frame_at(Path(clip.media_path), src_t)
                # Sharp 4K-friendly long-side (person-fix2 Max preview)
                bgr = downscale_long_side(bgr, self._preview_matte_long())
                alpha = self._matte_bgr(bgr, warmup=True)
                ok = alpha is not None and not is_matte_empty(alpha)
                clip.ai_polish = "done" if ok else "error"
            except Exception as exc:  # noqa: BLE001
                clip.ai_polish = "error"
                st = self._status_with_ai_polish(clip.clip_id)
                st["detail"] = f"Polírozás hiba: {exc}"[:240]
                return st
            return self._status_with_ai_polish(clip.clip_id)

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
        # Auto-person only — never re-arm paint/wand seed when switching media.
        # open_media already purged MaskStore disk for this path.
        if isinstance(self.engine, MaxQualityEngine):
            self.engine.clear_user_seed()
        self._seed_alpha = None
        self._seed_mode = "union"
        self._seed_part = None

    def _matte_bgr(self, bgr: "np.ndarray", *, warmup: bool = False) -> "np.ndarray":
        """Alpha for one BGR frame — selected-clip seed applies when engine has it."""
        if self.mode is EngineMode.MAX and isinstance(self.engine, MaxQualityEngine):
            return self.engine._polish(bgr, warmup=warmup).astype(np.float32)
        return np.asarray(self.engine._matte(bgr), dtype=np.float32)  # type: ignore[attr-defined]

    def _decode_layer_pixels(
        self,
        layer: Any,
        source_t: float,
        *,
        max_long: int = 960,
        warmup: bool = False,
    ) -> tuple[Any, Any, float]:
        """Decode BGR + alpha for one PlannedLayer (embedded alpha for nobg, else matte)."""
        from hybrid_editor.media.video_io import (
            downscale_long_side,
            normalize_alpha,
            read_frame_at,
            read_frame_bgra,
        )

        path = Path(layer.media_path)
        has_alpha = bool(getattr(layer, "has_alpha", False))
        if has_alpha:
            bgra, t, useful = read_frame_bgra(path, float(source_t))
            bgr = bgra[:, :, :3]
            alpha = normalize_alpha(bgra[:, :, 3])
            bgr = downscale_long_side(bgr, max_long)
            if alpha.shape[:2] != bgr.shape[:2]:
                import cv2

                alpha = cv2.resize(
                    alpha, (bgr.shape[1], bgr.shape[0]), interpolation=cv2.INTER_LINEAR
                )
            if not useful:
                # Fallback: still try engine matte on RGB if alpha decode failed
                self._ensure_engine_media(layer.media_path)
                alpha = self._matte_bgr(bgr, warmup=warmup)
            return bgr, alpha.astype(np.float32), float(t)
        self._ensure_engine_media(layer.media_path)
        bgr, t = read_frame_at(path, float(source_t))
        bgr = downscale_long_side(bgr, max_long)
        alpha = self._matte_bgr(bgr, warmup=warmup)
        return bgr, alpha.astype(np.float32), float(t)

    def preview(self, t_sec: float = 0.0) -> PreviewFrame:
        """Timeline composition at playhead: V1 cutout + V2 overlays (Concat plan→compose)."""
        with self._lock:
            if self.media is None and (self.timeline is None or not self.timeline.clips):
                raise RuntimeError("Open a video first")
            source_t = float(t_sec)
            overlay_meta: dict[str, Any] = {}
            matte_layer = None
            overlays: list = []
            if self.timeline is not None:
                self.timeline.set_playhead(t_sec)
                plan = plan_frame(self.timeline, self.timeline.playhead_sec)
                if plan.layers:
                    v1_layers = [L for L in plan.layers if int(L.track) == 0]
                    overlays = [L for L in plan.layers if int(L.track) >= 1]
                    # BG remove: selected V1 under playhead, else any V1, else bottom layer
                    sel_id = self.timeline.selected_clip_id
                    matte_layer = next(
                        (L for L in v1_layers if L.clip_id == sel_id),
                        v1_layers[0] if v1_layers else plan.layers[0],
                    )
                    source_t = matte_layer.source_t_sec
                    self._ensure_engine_media(matte_layer.media_path)
                    # Auto-person only — drop paint/wand user seed; keep auto `_seed`.
                    if isinstance(self.engine, MaxQualityEngine):
                        self.engine.set_user_seed(None)
                    if overlays or getattr(matte_layer, "has_alpha", False):
                        overlay_meta = {
                            "overlay_layers": [
                                {
                                    "clip_id": L.clip_id,
                                    "media_path": L.media_path,
                                    "source_t_sec": L.source_t_sec,
                                    "opacity": L.opacity,
                                    "track": L.track,
                                    "pos_x": getattr(L, "pos_x", 0.0),
                                    "pos_y": getattr(L, "pos_y", 0.0),
                                    "scale": getattr(L, "scale", 1.0),
                                    "has_alpha": getattr(L, "has_alpha", False),
                                }
                                for L in overlays
                            ],
                            "timeline_composite": True,
                            "matte_clip_id": matte_layer.clip_id,
                            "matte_has_alpha": bool(getattr(matte_layer, "has_alpha", False)),
                            "matte_pos_x": float(getattr(matte_layer, "pos_x", 0.0)),
                            "matte_pos_y": float(getattr(matte_layer, "pos_y", 0.0)),
                            "matte_scale": float(getattr(matte_layer, "scale", 1.0)),
                        }

            # Multi-layer OR alpha V1 nobg: decode + composite (same math as bake)
            need_custom = matte_layer is not None and (
                bool(overlays) or bool(getattr(matte_layer, "has_alpha", False))
                or abs(float(getattr(matte_layer, "pos_x", 0.0))) > 1e-6
                or abs(float(getattr(matte_layer, "pos_y", 0.0))) > 1e-6
                or abs(float(getattr(matte_layer, "scale", 1.0)) - 1.0) > 1e-6
            )
            if need_custom:
                from hybrid_editor.media.video_io import (
                    OverlayFrame,
                    composite_overlay_layers,
                    encode_preview_pair,
                    encode_source_only_preview,
                    place_layer_on_canvas,
                    read_frame_at,
                )

                try:
                    matte_long = self._preview_matte_long()
                    bgr, alpha, t = self._decode_layer_pixels(
                        matte_layer, source_t, max_long=matte_long, warmup=True
                    )
                    # Apply V1 transform when user repositioned the base cutout
                    if (
                        abs(float(matte_layer.pos_x)) > 1e-6
                        or abs(float(matte_layer.pos_y)) > 1e-6
                        or abs(float(matte_layer.scale) - 1.0) > 1e-6
                    ):
                        canvas_h, canvas_w = bgr.shape[:2]
                        placed_bgr, placed_a = place_layer_on_canvas(
                            canvas_h,
                            canvas_w,
                            bgr,
                            alpha,
                            pos_x=float(matte_layer.pos_x),
                            pos_y=float(matte_layer.pos_y),
                            scale=float(matte_layer.scale),
                        )
                        # Keep canvas size; transparent elsewhere → checker in encode
                        bgr, alpha = placed_bgr, placed_a
                    ov_frames: list[OverlayFrame] = []
                    for ov in overlays:
                        try:
                            obgr, oalpha, _ = self._decode_layer_pixels(
                                ov, ov.source_t_sec, max_long=matte_long
                            )
                            ov_frames.append(
                                OverlayFrame(
                                    bgr=obgr,
                                    opacity=float(ov.opacity),
                                    alpha=oalpha if getattr(ov, "has_alpha", False) else None,
                                    pos_x=float(getattr(ov, "pos_x", 0.0)),
                                    pos_y=float(getattr(ov, "pos_y", 0.0)),
                                    scale=float(getattr(ov, "scale", 1.0)),
                                )
                            )
                        except Exception:  # noqa: BLE001
                            continue
                    if ov_frames:
                        bgr, alpha = composite_overlay_layers(bgr, alpha, ov_frames)
                    sharp = bool(getattr(self, "sharp_edges", True))
                    jpg, png, w, h, src, empty = encode_preview_pair(
                        bgr, alpha, sharp_cutout=sharp and self.mode is EngineMode.MAX
                    )
                    meta_extra: dict[str, Any] = {
                        "matte_empty": empty,
                        "has_alpha_clip": bool(getattr(matte_layer, "has_alpha", False)),
                        "stamp": "2026-10-13-peak-ui",
                        **overlay_meta,
                    }
                    if empty:
                        from hybrid_editor.media.video_io import matte_failure_reason

                        why = matte_failure_reason(alpha)
                        if why:
                            meta_extra["matte_error"] = why
                            meta_extra["source_fallback"] = True
                    else:
                        meta_extra.pop("matte_error", None)
                        meta_extra.pop("source_fallback", None)
                        meta_extra["matte_recovered"] = True
                    frame = PreviewFrame(
                        t_sec=t,
                        width=w,
                        height=h,
                        jpeg_b64=jpg,
                        alpha_png_b64=png,
                        engine=self.engine.capabilities().name,
                        backend=self.engine.capabilities().backend,
                        meta=meta_extra,
                        source_jpeg_b64=src,
                    )
                except Exception as exc:  # noqa: BLE001
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
                            **overlay_meta,
                        },
                        source_jpeg_b64=src,
                    )
            else:
                try:
                    frame = self.engine.preview_frame(source_t)
                except Exception as exc:  # noqa: BLE001
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
            # simple-bg6: Gyors empty/slab → auto Max at most once per open.
            # Never fight an explicit Gyors click (_suppress_auto_max).
            meta0 = frame.meta or {}
            gyros_empty = bool(meta0.get("matte_empty") or meta0.get("source_fallback"))
            if (
                gyros_empty
                and self.mode is EngineMode.GYORS
                and not getattr(self, "_suppress_auto_max", False)
                and not getattr(self, "_auto_max_done", False)
                and not getattr(self, "_preview_auto_max_guard", False)
            ):
                self._preview_auto_max_guard = True
                self._auto_max_done = True
                try:
                    logger = __import__("logging").getLogger(__name__)
                    logger.warning(
                        "Gyors matte empty/slab — auto-switching to Max once "
                        "(re-click Gyors to stay on Gyors)"
                    )
                    self.set_mode("max")
                    frame = self.engine.preview_frame(source_t)
                    frame.meta = {
                        **(frame.meta or {}),
                        "auto_max_retry": True,
                        "auto_max_from": "gyors",
                    }
                    if overlay_meta:
                        frame.meta = {**(frame.meta or {}), **overlay_meta}
                except Exception as auto_exc:  # noqa: BLE001
                    frame.meta = {
                        **(frame.meta or {}),
                        "auto_max_retry": False,
                        "auto_max_error": str(auto_exc)[:160],
                    }
                finally:
                    self._preview_auto_max_guard = False
            elif (
                gyros_empty
                and self.mode is EngineMode.GYORS
                and getattr(self, "_suppress_auto_max", False)
            ):
                frame.meta = {
                    **(frame.meta or {}),
                    "auto_max_skipped": True,
                    "auto_max_skip_reason": "user_locked_gyors",
                }
            if self._seed_alpha is not None:
                frame.meta = {
                    **(frame.meta or {}),
                    "user_seed": True,
                    "seed_bound": True,
                    "seed_clip_id": self.timeline.selected_clip_id if self.timeline else None,
                }
            # Surface true source resolution (never invent 1920×1080).
            if self.media is not None:
                frame.meta = {
                    **(frame.meta or {}),
                    "source_width": int(self.media.width),
                    "source_height": int(self.media.height),
                    "source_fps": float(self.media.fps),
                }
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

    def set_seed_mask(
        self,
        png_b64: str,
        *,
        mode: Optional[str] = None,
        part: Optional[str] = None,
    ) -> dict[str, Any]:
        """Removed: paint/wand seeds no longer apply. Clears any leftover mask."""
        del png_b64, mode, part
        return self.clear_seed_mask()

    def pick_seed_part(
        self,
        *,
        x: float,
        y: float,
        t_sec: Optional[float] = None,
        erase: bool = False,
    ) -> dict[str, Any]:
        """Removed: Varázsceruza / face_pick — auto full-person RVM only."""
        del x, y, t_sec, erase
        raise RuntimeError(
            "Varázsceruza eltávolítva — auto teljes ember (RVM). Használd az Előnézet / Polírozás útvonalat."
        )

    def get_seed_mask(self) -> dict[str, Any]:
        with self._lock:
            if self._seed_alpha is None:
                return {"seed_mask": False, "seed_mask_png_b64": None}
            return {
                "seed_mask": True,
                "seed_mask_png_b64": encode_alpha_png_b64(self._seed_alpha),
                "width": int(self._seed_alpha.shape[1]),
                "height": int(self._seed_alpha.shape[0]),
                "seed_mode": self._seed_mode,
                "seed_part": self._seed_part,
            }

    def clear_seed_mask(self) -> dict[str, Any]:
        with self._lock:
            self._apply_seed_to_engine(None)
            if isinstance(self.engine, MaxQualityEngine):
                self.engine._seed = None  # noqa: SLF001
                if hasattr(self.engine, "_stabilizer"):
                    try:
                        self.engine._stabilizer.reset()
                    except Exception:
                        pass
            self._purge_seed_disk()
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
            finalize_bgcut_exports,
            media_has_audio,
            write_preview_mp4,
        )
        from hybrid_editor.media.video_io import downscale_long_side, read_frame_at
        from hybrid_editor.timeline import plan_frame as _plan

        assert self.timeline is not None
        out_dir = Path(out_dir)
        from hybrid_editor.export.bgcut import alpha_dump_dir, dump_alpha_frames_enabled

        dump_alpha = dump_alpha_frames_enabled()
        alpha_dir = alpha_dump_dir(out_dir) if dump_alpha else None
        if alpha_dir is not None:
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
            bake_long = self._bake_matte_long()
            bgr, alpha, _ = self._decode_layer_pixels(
                v1, v1.source_t_sec, max_long=bake_long, warmup=(written == 0)
            )
            from hybrid_editor.media.video_io import (
                OverlayFrame,
                composite_overlay_layers,
                place_layer_on_canvas,
            )

            if (
                abs(float(getattr(v1, "pos_x", 0.0))) > 1e-6
                or abs(float(getattr(v1, "pos_y", 0.0))) > 1e-6
                or abs(float(getattr(v1, "scale", 1.0)) - 1.0) > 1e-6
            ):
                ch, cw = bgr.shape[:2]
                bgr, alpha = place_layer_on_canvas(
                    ch,
                    cw,
                    bgr,
                    alpha,
                    pos_x=float(v1.pos_x),
                    pos_y=float(v1.pos_y),
                    scale=float(v1.scale),
                )
            # Composite V2 B-roll / nobg over cutout (same helper as monitor preview)
            ov_frames = []
            for ov in overlays:
                try:
                    obgr, oalpha, _ = self._decode_layer_pixels(
                        ov, ov.source_t_sec, max_long=bake_long
                    )
                    ov_frames.append(
                        OverlayFrame(
                            bgr=obgr,
                            opacity=float(ov.opacity),
                            alpha=oalpha if getattr(ov, "has_alpha", False) else None,
                            pos_x=float(getattr(ov, "pos_x", 0.0)),
                            pos_y=float(getattr(ov, "pos_y", 0.0)),
                            scale=float(getattr(ov, "scale", 1.0)),
                        )
                    )
                except Exception:  # noqa: BLE001
                    continue
            if ov_frames:
                bgr, alpha = composite_overlay_layers(bgr, alpha, ov_frames)
            a8 = (np.clip(alpha, 0, 1) * 255).astype(np.uint8)
            if alpha_dir is not None:
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
            # Build BGRA for alpha MOV (same proxy size as preview)
            frames_bgra = []
            for bgr, a in zip(frames_bgr, frames_alpha):
                bgra = cv2.cvtColor(bgr, cv2.COLOR_BGR2BGRA)
                a8 = (np.clip(a, 0, 1) * 255).astype(np.uint8)
                bgra[:, :, 3] = a8
                frames_bgra.append(bgra)
            stem = Path(self.timeline.clips_on(0)[0].media_path).stem if self.timeline.clips_on(0) else "timeline"
            if progress:
                progress(0.95, "Export C:\\bgcut *_full_nobg.mov…")
            prores, companion = finalize_bgcut_exports(
                media_stem=stem,
                out_dir=out_dir,
                preview_mp4=preview_mp4,
                frames_bgra=frames_bgra,
                fps=fps,
            )
            if progress:
                progress(1.0, "Bake kész")
        else:
            prores = None

        n_broll = len(self.timeline.clips_on(1))
        audio_note = " · audio AAC" if audio_ok else ""
        broll_note = f" · {n_broll} B-roll" if n_broll else ""
        mov_note = f" · {prores}" if prores else " · HIÁNYZIK: *_full_nobg.mov"
        msg_core = (
            f"Kész: {Path(prores).name}" if prores else "SIKERTELEN: nincs *_full_nobg.mov (ffmpeg?)"
        )
        return BakeResult(
            ok=written > 0 and bool(prores),
            out_dir=str(out_dir.resolve()),
            frames_written=written,
            engine=self.engine.capabilities().name,
            backend=self.engine.capabilities().backend,
            message=(
                f"{msg_core} · multi-clip {written} frame · "
                f"{len(self.timeline.clips)} clips{broll_note}{audio_note}{mov_note}"
            ),
            alpha_preview=(
                str(alpha_dir / "000000.png") if alpha_dir is not None and written else None
            ),
            preview_mp4=companion or preview_mp4,
            prores_mov=prores,
            bake_range={
                "in_sec": 0.0,
                "out_sec": dur,
                "duration_sec": dur,
                "clips": len(self.timeline.clips),
                "broll": n_broll,
                "audio": audio_ok,
                "max_frames_cap": max_frames,
                "mov_path": prores,
            },
        )

    def open_output_folder(self, out_dir: Optional[str] = None) -> dict[str, Any]:
        """Reveal last bake ``*_full_nobg.mov`` (prefer file select) or output folder."""
        with self._lock:
            folder: Optional[Path] = None
            reveal: Optional[Path] = None
            if out_dir:
                cand = Path(out_dir).expanduser()
                if cand.is_file():
                    reveal = cand
                    folder = cand.parent
                else:
                    folder = cand
            elif self.last_bake:
                if self.last_bake.prores_mov:
                    reveal = Path(self.last_bake.prores_mov)
                    folder = reveal.parent
                elif self.last_bake.preview_mp4:
                    reveal = Path(self.last_bake.preview_mp4)
                    folder = reveal.parent
                elif self.last_bake.out_dir:
                    folder = Path(self.last_bake.out_dir)
            if folder is None:
                from hybrid_editor.export.bgcut import default_bgcut_dir

                folder = default_bgcut_dir()
            folder = folder.resolve()
            if not folder.exists():
                folder.mkdir(parents=True, exist_ok=True)
            if reveal is not None:
                reveal = reveal.resolve()
            opened = False
            error: Optional[str] = None
            try:
                if sys.platform.startswith("win"):
                    if reveal is not None and reveal.is_file():
                        # Select the .mov in Explorer — primary deliverable
                        subprocess.run(
                            ["explorer", f"/select,{reveal}"],
                            check=False,
                            timeout=15,
                        )
                        opened = True
                    else:
                        os.startfile(str(folder))  # type: ignore[attr-defined]
                        opened = True
                elif sys.platform == "darwin":
                    if reveal is not None and reveal.is_file():
                        subprocess.run(["open", "-R", str(reveal)], check=False, timeout=15)
                    else:
                        subprocess.run(["open", str(folder)], check=False, timeout=15)
                    opened = True
                else:
                    opener = "xdg-open"
                    target = str(reveal if reveal is not None and reveal.is_file() else folder)
                    if os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY"):
                        subprocess.run([opener, target], check=False, timeout=15)
                        opened = True
                    else:
                        error = "No display — path returned only"
            except Exception as exc:  # noqa: BLE001
                error = str(exc)
            return {
                "ok": True,
                "opened": opened,
                "out_dir": str(folder),
                "prores_mov": str(reveal) if reveal is not None else None,
                "error": error,
            }

    def bake(
        self,
        out_dir: str | Path,
        *,
        max_frames: Optional[int] = None,
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
            # Engines already write {stem}_full_nobg.mov + companion preview into out_dir.
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
