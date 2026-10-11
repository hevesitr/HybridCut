"""Pure FramePlan at time t — shared by monitor preview and bake/export.

Concat idea: plan_frame is pure (no I/O). Phase 2: multi-clip track —
add/remove/reorder, cut at playhead, per-clip trim.
Phase 4: V1 main + V2 overlay/B-roll stub (track index).
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Optional
from uuid import uuid4


def _clip_id() -> str:
    return f"clip-{uuid4().hex[:8]}"


@dataclass
class ClipRange:
    """One media clip on a timeline track (0=V1 main, 1=AI sáv / V2 overlay)."""

    media_path: str
    clip_id: str = field(default_factory=_clip_id)
    # Source trim (seconds in media)
    in_sec: float = 0.0
    out_sec: float = 0.0  # 0 = media end
    # Timeline placement
    timeline_start_sec: float = 0.0
    opacity: float = 1.0
    fps: float = 25.0
    width: int = 0
    height: int = 0
    media_duration_sec: float = 0.0
    label: str = ""
    # 0 = V1 main (sequential pack), 1 = AI sáv (V2 overlay / polish lane)
    track: int = 0
    # CapCut-like transform — center offset as fraction of canvas (−1…1), scale 1=100%
    pos_x: float = 0.0
    pos_y: float = 0.0
    scale: float = 1.0
    # True for *_full_nobg.mov / alpha WebM — decode+composite preserve alpha (no re-matte)
    has_alpha: bool = False
    # AI sáv: clip stacked for person cutout / edge polish orchestration
    ai_lane: bool = False
    # idle | pending | running | done | error
    ai_polish: str = "idle"

    def effective_out(self) -> float:
        end = self.out_sec if self.out_sec > 0 else self.media_duration_sec
        if end <= 0:
            end = max(self.in_sec, 0.0) + 1.0
        return max(float(end), float(self.in_sec))

    def source_duration(self) -> float:
        return max(0.0, self.effective_out() - float(self.in_sec))

    def timeline_end(self) -> float:
        return float(self.timeline_start_sec) + self.source_duration()

    def display_label(self) -> str:
        if self.label:
            return self.label
        name = self.media_path.replace("\\", "/").split("/")[-1]
        return name or self.clip_id

    def track_label(self) -> str:
        if int(self.track) >= 1:
            if self.has_alpha:
                return "AI sáv · nobg"
            status = (self.ai_polish or "idle").strip().lower()
            if status == "running":
                return "AI sáv · Polírozás…"
            if status == "done":
                return "AI sáv · kész"
            if status == "pending":
                return "AI sáv · vár"
            if status == "error":
                return "AI sáv · hiba"
            return "AI sáv"
        if self.has_alpha:
            return "V1 nobg"
        return "V1"


@dataclass(frozen=True)
class PlannedLayer:
    clip_id: str
    media_path: str
    source_t_sec: float
    opacity: float
    width: int
    height: int
    track: int = 0
    pos_x: float = 0.0
    pos_y: float = 0.0
    scale: float = 1.0
    has_alpha: bool = False


@dataclass(frozen=True)
class FramePlan:
    """Pure plan at timeline time t — no pixels, no I/O."""

    t_sec: float
    frame_index: int
    fps: float
    layers: tuple[PlannedLayer, ...]
    empty: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "t_sec": self.t_sec,
            "frame_index": self.frame_index,
            "fps": self.fps,
            "empty": self.empty,
            "layers": [asdict(layer) for layer in self.layers],
        }


@dataclass
class TimelineDoc:
    """Editable multi-clip / multi-track timeline document for the UI."""

    clips: list[ClipRange] = field(default_factory=list)
    playhead_sec: float = 0.0
    fps: float = 25.0
    selected_clip_id: Optional[str] = None

    @classmethod
    def from_media(
        cls,
        *,
        path: str,
        duration_sec: float,
        fps: float,
        width: int,
        height: int,
        in_sec: float = 0.0,
        out_sec: float = 0.0,
        label: str = "",
        track: int = 0,
        has_alpha: bool = False,
        pos_x: float = 0.0,
        pos_y: float = 0.0,
        scale: float = 1.0,
        opacity: float = 1.0,
    ) -> "TimelineDoc":
        clip = ClipRange(
            media_path=path,
            in_sec=max(0.0, float(in_sec)),
            out_sec=float(out_sec) if out_sec > 0 else float(duration_sec),
            timeline_start_sec=0.0,
            fps=float(fps) or 25.0,
            width=int(width),
            height=int(height),
            media_duration_sec=float(duration_sec),
            label=label,
            track=int(track),
            has_alpha=bool(has_alpha),
            pos_x=float(pos_x),
            pos_y=float(pos_y),
            scale=max(0.05, float(scale)),
            opacity=np_clip(opacity, 0.0, 1.0),
        )
        return cls(
            clips=[clip],
            playhead_sec=0.0,
            fps=float(fps) or 25.0,
            selected_clip_id=clip.clip_id,
        )

    def duration_sec(self) -> float:
        if not self.clips:
            return 0.0
        return max(c.timeline_end() for c in self.clips)

    def _find(self, clip_id: Optional[str] = None) -> Optional[ClipRange]:
        cid = clip_id or self.selected_clip_id
        if cid:
            for c in self.clips:
                if c.clip_id == cid:
                    return c
        return self.clips[0] if self.clips else None

    def clips_on(self, track: int) -> list[ClipRange]:
        return [c for c in self.clips if int(c.track) == int(track)]

    def select_clip(self, clip_id: str) -> None:
        if any(c.clip_id == clip_id for c in self.clips):
            self.selected_clip_id = clip_id

    def relayout_sequential(self) -> None:
        """Pack V1 (track 0) end-to-end; leave V2 overlay starts alone."""
        t = 0.0
        for c in self.clips:
            if int(c.track) != 0:
                continue
            c.timeline_start_sec = t
            t = c.timeline_end()
        self.playhead_sec = min(max(0.0, self.playhead_sec), self.duration_sec())

    def set_trim(
        self,
        *,
        in_sec: Optional[float] = None,
        out_sec: Optional[float] = None,
        clip_id: Optional[str] = None,
    ) -> None:
        clip = self._find(clip_id)
        if clip is None:
            return
        if in_sec is not None:
            clip.in_sec = max(0.0, min(float(in_sec), clip.media_duration_sec or float(in_sec)))
        if out_sec is not None:
            hi = clip.media_duration_sec if clip.media_duration_sec > 0 else float(out_sec)
            clip.out_sec = max(clip.in_sec, min(float(out_sec), hi if hi > 0 else float(out_sec)))
        if int(clip.track) == 0:
            self.relayout_sequential()

    def set_playhead(self, t_sec: float) -> None:
        """Scrub playhead only — do not steal clip selection (Concat-like)."""
        dur = self.duration_sec()
        self.playhead_sec = min(max(0.0, float(t_sec)), dur if dur > 0 else max(0.0, float(t_sec)))

    def set_track(
        self,
        clip_id: str,
        track: int,
        *,
        timeline_start_sec: Optional[float] = None,
    ) -> bool:
        """Move clip to V1 (0) or AI sáv / V2 (1); optional free start on AI lane."""
        clip = self._find(clip_id)
        if clip is None:
            return False
        new_track = 0 if int(track) <= 0 else 1
        old_track = int(clip.track)
        if new_track == 0 and old_track >= 1:
            # Demoting last? always ok. Promoting away last V1 blocked elsewhere.
            pass
        if new_track >= 1 and old_track == 0 and len(self.clips_on(0)) <= 1:
            return False
        clip.track = new_track
        if new_track >= 1:
            start = (
                float(timeline_start_sec)
                if timeline_start_sec is not None
                else float(self.playhead_sec)
            )
            clip.timeline_start_sec = max(0.0, start)
            # Alpha nobg overlays stay fully opaque; plain B-roll softens slightly
            if clip.opacity >= 0.999 and not clip.has_alpha:
                clip.opacity = 0.85
            clip.ai_lane = True
            # Stack onto AI sáv → queue person/edge polish (orchestration, not new model)
            if not clip.has_alpha and (clip.ai_polish or "idle") in {"idle", "error"}:
                clip.ai_polish = "pending"
        else:
            clip.ai_lane = False
            if (clip.ai_polish or "") == "pending":
                clip.ai_polish = "idle"
            if not clip.has_alpha:
                clip.opacity = 1.0
            self.relayout_sequential()
        self.selected_clip_id = clip_id
        return True

    def set_transform(
        self,
        clip_id: Optional[str] = None,
        *,
        pos_x: Optional[float] = None,
        pos_y: Optional[float] = None,
        scale: Optional[float] = None,
        opacity: Optional[float] = None,
    ) -> bool:
        """CapCut-like position / scale on the selected (or given) clip."""
        clip = self._find(clip_id)
        if clip is None:
            return False
        if pos_x is not None:
            clip.pos_x = float(np_clip(pos_x, -2.0, 2.0))
        if pos_y is not None:
            clip.pos_y = float(np_clip(pos_y, -2.0, 2.0))
        if scale is not None:
            clip.scale = float(np_clip(scale, 0.05, 4.0))
        if opacity is not None:
            clip.opacity = float(np_clip(opacity, 0.0, 1.0))
        self.selected_clip_id = clip.clip_id
        return True

    def reset_transform(self, clip_id: Optional[str] = None) -> bool:
        """Reset position/scale to centered 100% (CapCut Reset)."""
        clip = self._find(clip_id)
        if clip is None:
            return False
        clip.pos_x = 0.0
        clip.pos_y = 0.0
        clip.scale = 1.0
        if clip.has_alpha or int(clip.track) == 0:
            clip.opacity = 1.0
        self.selected_clip_id = clip.clip_id
        return True

    def set_timeline_start(self, clip_id: str, timeline_start_sec: float) -> bool:
        """Place V2 overlay in time; for V1, reorder by nearest sequential slot."""
        clip = self._find(clip_id)
        if clip is None:
            return False
        t = max(0.0, float(timeline_start_sec))
        if int(clip.track) >= 1:
            clip.timeline_start_sec = t
            self.selected_clip_id = clip_id
            return True
        # V1: find insert index by target start among other V1 clips
        others = [c for c in self.clips_on(0) if c.clip_id != clip_id]
        others_sorted = sorted(others, key=lambda c: float(c.timeline_start_sec))
        insert_at = 0
        for i, o in enumerate(others_sorted):
            mid = float(o.timeline_start_sec) + 0.5 * o.source_duration()
            if t >= mid:
                insert_at = i + 1
        # Rebuild V1 order in self.clips
        v2 = [c for c in self.clips if int(c.track) >= 1]
        new_v1 = others_sorted[:insert_at] + [clip] + others_sorted[insert_at:]
        self.clips = new_v1 + v2
        self.selected_clip_id = clip_id
        self.relayout_sequential()
        return True

    def trim_edge(
        self,
        clip_id: str,
        *,
        edge: str,
        timeline_t: float,
    ) -> bool:
        """Drag trim handle: edge in|out at absolute timeline time → source in/out."""
        clip = self._find(clip_id)
        if clip is None:
            return False
        t = float(timeline_t)
        local = t - float(clip.timeline_start_sec)
        if edge in {"in", "left", "be"}:
            # New in: keep out fixed in source; shift timeline start for overlays
            new_in = float(clip.in_sec) + local
            new_in = max(0.0, min(new_in, clip.effective_out() - 0.05))
            delta = new_in - float(clip.in_sec)
            clip.in_sec = new_in
            if int(clip.track) >= 1:
                clip.timeline_start_sec = float(clip.timeline_start_sec) + delta
            elif int(clip.track) == 0:
                self.relayout_sequential()
        elif edge in {"out", "right", "ki"}:
            new_out = float(clip.in_sec) + local
            hi = clip.media_duration_sec if clip.media_duration_sec > 0 else new_out
            new_out = max(float(clip.in_sec) + 0.05, min(new_out, hi if hi > 0 else new_out))
            clip.out_sec = new_out
            if int(clip.track) == 0:
                self.relayout_sequential()
        else:
            return False
        self.selected_clip_id = clip_id
        return True

    def add_clip(
        self,
        *,
        media_path: str,
        duration_sec: float,
        fps: float,
        width: int,
        height: int,
        in_sec: float = 0.0,
        out_sec: float = 0.0,
        label: str = "",
        after_clip_id: Optional[str] = None,
        track: int = 0,
        timeline_start_sec: Optional[float] = None,
        opacity: float = 1.0,
        has_alpha: bool = False,
        pos_x: float = 0.0,
        pos_y: float = 0.0,
        scale: float = 1.0,
    ) -> ClipRange:
        clip = ClipRange(
            media_path=media_path,
            in_sec=max(0.0, float(in_sec)),
            out_sec=float(out_sec) if out_sec > 0 else float(duration_sec),
            fps=float(fps) or float(self.fps) or 25.0,
            width=int(width),
            height=int(height),
            media_duration_sec=float(duration_sec),
            label=label,
            track=max(0, int(track)),
            opacity=np_clip(opacity, 0.0, 1.0),
            has_alpha=bool(has_alpha),
            pos_x=float(pos_x),
            pos_y=float(pos_y),
            scale=max(0.05, float(scale)),
        )
        if int(clip.track) >= 1:
            # AI sáv / overlay: place at playhead (or explicit start); do not pack into V1
            start = (
                float(timeline_start_sec)
                if timeline_start_sec is not None
                else float(self.playhead_sec)
            )
            clip.timeline_start_sec = max(0.0, start)
            clip.ai_lane = True
            if not clip.has_alpha and (clip.ai_polish or "idle") == "idle":
                clip.ai_polish = "pending"
            self.clips.append(clip)
        elif after_clip_id:
            idx = next((i for i, c in enumerate(self.clips) if c.clip_id == after_clip_id), -1)
            if idx >= 0:
                self.clips.insert(idx + 1, clip)
            else:
                self.clips.append(clip)
        else:
            self.clips.append(clip)
        self.selected_clip_id = clip.clip_id
        if not self.fps:
            self.fps = clip.fps
        if int(clip.track) == 0:
            self.relayout_sequential()
        return clip

    def add_broll(
        self,
        *,
        media_path: str,
        duration_sec: float,
        fps: float,
        width: int,
        height: int,
        in_sec: float = 0.0,
        out_sec: float = 0.0,
        label: str = "",
        timeline_start_sec: Optional[float] = None,
        opacity: float = 0.85,
        has_alpha: bool = False,
        pos_x: float = 0.0,
        pos_y: float = 0.0,
        scale: float = 1.0,
    ) -> ClipRange:
        """Convenience: place media on AI sáv (V2) at playhead."""
        return self.add_clip(
            media_path=media_path,
            duration_sec=duration_sec,
            fps=fps,
            width=width,
            height=height,
            in_sec=in_sec,
            out_sec=out_sec,
            label=label or ("nobg" if has_alpha else "AI"),
            track=1,
            timeline_start_sec=timeline_start_sec,
            opacity=1.0 if has_alpha else opacity,
            has_alpha=has_alpha,
            pos_x=pos_x,
            pos_y=pos_y,
            scale=scale,
        )

    def duplicate_selected(self) -> Optional[ClipRange]:
        src = self._find()
        if src is None:
            return None
        return self.add_clip(
            media_path=src.media_path,
            duration_sec=src.media_duration_sec,
            fps=src.fps,
            width=src.width,
            height=src.height,
            in_sec=src.in_sec,
            out_sec=src.effective_out(),
            label=src.label,
            after_clip_id=src.clip_id if int(src.track) == 0 else None,
            track=int(src.track),
            timeline_start_sec=(
                None if int(src.track) == 0 else float(src.timeline_end())
            ),
            opacity=src.opacity,
            has_alpha=src.has_alpha,
            pos_x=src.pos_x,
            pos_y=src.pos_y,
            scale=src.scale,
        )

    def remove_clip(self, clip_id: Optional[str] = None) -> bool:
        cid = clip_id or self.selected_clip_id
        if not cid:
            return False
        # Keep at least one V1 clip if any exist; allow removing last overlay
        target = next((c for c in self.clips if c.clip_id == cid), None)
        if target is None:
            return False
        v1 = self.clips_on(0)
        if int(target.track) == 0 and len(v1) <= 1:
            return False
        self.clips = [c for c in self.clips if c.clip_id != cid]
        if self.selected_clip_id == cid:
            self.selected_clip_id = self.clips[0].clip_id if self.clips else None
        self.relayout_sequential()
        return True

    def move_clip(self, clip_id: str, *, direction: int) -> bool:
        """direction: -1 left, +1 right — reorder within same track then pack V1."""
        idx = next((i for i, c in enumerate(self.clips) if c.clip_id == clip_id), -1)
        if idx < 0:
            return False
        track = int(self.clips[idx].track)
        same = [(i, c) for i, c in enumerate(self.clips) if int(c.track) == track]
        pos = next((k for k, (i, _) in enumerate(same) if i == idx), -1)
        if pos < 0:
            return False
        jpos = pos + (1 if direction > 0 else -1)
        if jpos < 0 or jpos >= len(same):
            return False
        i_a = same[pos][0]
        i_b = same[jpos][0]
        self.clips[i_a], self.clips[i_b] = self.clips[i_b], self.clips[i_a]
        self.selected_clip_id = clip_id
        if track == 0:
            self.relayout_sequential()
        else:
            # Swap timeline starts for overlays
            a, b = self.clips[i_a], self.clips[i_b]
            a.timeline_start_sec, b.timeline_start_sec = b.timeline_start_sec, a.timeline_start_sec
        return True

    def cut_at_playhead(self, t_sec: Optional[float] = None) -> bool:
        """Split the V1 (or selected) clip under t into two (simple razor cut)."""
        t = self.playhead_sec if t_sec is None else float(t_sec)
        clip = None
        idx = -1
        # Prefer selected if under playhead; else V1 under playhead
        sel = self._find()
        candidates = []
        if sel is not None:
            candidates.append(sel)
        candidates.extend(c for c in self.clips_on(0) if c not in candidates)
        candidates.extend(c for c in self.clips if c not in candidates)
        for c in candidates:
            if c.timeline_start_sec < t < c.timeline_end() - 1e-6:
                clip = c
                idx = self.clips.index(c)
                break
        if clip is None:
            return False
        local = t - float(clip.timeline_start_sec)
        if local <= 1e-3 or local >= clip.source_duration() - 1e-3:
            return False
        cut_source = float(clip.in_sec) + local
        right = ClipRange(
            media_path=clip.media_path,
            in_sec=cut_source,
            out_sec=clip.effective_out(),
            fps=clip.fps,
            width=clip.width,
            height=clip.height,
            media_duration_sec=clip.media_duration_sec,
            label=clip.label,
            track=int(clip.track),
            opacity=clip.opacity,
            timeline_start_sec=t if int(clip.track) >= 1 else 0.0,
            has_alpha=bool(clip.has_alpha),
            pos_x=float(clip.pos_x),
            pos_y=float(clip.pos_y),
            scale=float(clip.scale),
        )
        clip.out_sec = cut_source
        self.clips.insert(idx + 1, right)
        self.selected_clip_id = right.clip_id
        if int(clip.track) == 0:
            self.relayout_sequential()
        self.set_playhead(t)
        return True

    def to_dict(self) -> dict[str, Any]:
        return {
            "playhead_sec": self.playhead_sec,
            "fps": self.fps,
            "duration_sec": self.duration_sec(),
            "selected_clip_id": self.selected_clip_id,
            "tracks": [
                {"id": 0, "label": "V1"},
                {"id": 1, "label": "AI sáv"},
            ],
            "clips": [
                {
                    **asdict(c),
                    "timeline_end_sec": c.timeline_end(),
                    "source_duration_sec": c.source_duration(),
                    "display_label": c.display_label(),
                    "track_label": c.track_label(),
                    "ai_lane": bool(c.ai_lane or int(c.track) >= 1),
                    "ai_polish": (c.ai_polish or "idle"),
                    "ai_polish_label_hu": {
                        "pending": "Polírozás vár",
                        "running": "Polírozás…",
                        "done": "Polírozás kész",
                        "error": "Polírozás hiba",
                    }.get((c.ai_polish or "idle").lower(), ""),
                }
                for c in self.clips
            ],
        }


def plan_frame(doc: TimelineDoc, t_sec: float) -> FramePlan:
    """Pure FramePlan at timeline time t (visible layers bottom→top by track)."""
    fps = float(doc.fps) or 25.0
    t = max(0.0, float(t_sec))
    frame_index = int(round(t * fps))
    layers: list[PlannedLayer] = []
    # Stable order: V1 then V2 (bottom to top)
    ordered = sorted(doc.clips, key=lambda c: (int(c.track), float(c.timeline_start_sec)))
    for clip in ordered:
        start = float(clip.timeline_start_sec)
        end = clip.timeline_end()
        if t < start or t >= end - 1e-9:
            continue
        local = t - start
        source_t = float(clip.in_sec) + local
        source_t = min(source_t, clip.effective_out())
        layers.append(
            PlannedLayer(
                clip_id=clip.clip_id,
                media_path=clip.media_path,
                source_t_sec=source_t,
                opacity=np_clip(clip.opacity, 0.0, 1.0),
                width=int(clip.width),
                height=int(clip.height),
                track=int(clip.track),
                pos_x=float(clip.pos_x),
                pos_y=float(clip.pos_y),
                scale=max(0.05, float(clip.scale)),
                has_alpha=bool(clip.has_alpha),
            )
        )
    return FramePlan(
        t_sec=t,
        frame_index=frame_index,
        fps=fps,
        layers=tuple(layers),
        empty=len(layers) == 0,
    )


def np_clip(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, float(v)))
