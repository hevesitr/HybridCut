import {
  useRef,
  useState,
  type MouseEvent as ReactMouseEvent,
  type PointerEvent as ReactPointerEvent,
  type RefObject,
} from "react";
import type { ClipInfo } from "../lib/api";

type Props = {
  clips: ClipInfo[];
  duration: number;
  playhead: number;
  selectedId: string | null;
  disabled?: boolean;
  onSeek: (t: number) => void;
  onSelect: (clipId: string) => void;
  /** Drag trim handle → Be/Ki via timeline time. */
  onTrimEdge?: (clipId: string, edge: "in" | "out", timelineT: number) => void;
  /** Horizontal place / reorder. */
  onPlace?: (clipId: string, timelineStartSec: number) => void;
  /** Vertical stack: drop onto V1 (0) or V2 (1). */
  onSetTrack?: (clipId: string, track: number, timelineStartSec?: number) => void;
};

const V1_COLORS = ["#3ecf9a", "#2fd4a1", "#6ec6ff", "#5bbf8a"];
const V2_COLORS = ["#ff7a1a", "#e0b35a", "#e36b5b", "#c39bdc"];

type DragKind = "move" | "in" | "out";

type DragState = {
  kind: DragKind;
  clipId: string;
  track: number;
  startClientX: number;
  startClientY: number;
  originStart: number;
  originEnd: number;
  laneTop: number;
  laneBottom: number;
  moved: boolean;
};

export function TimelineTrack({
  clips,
  duration,
  playhead,
  selectedId,
  disabled,
  onSeek,
  onSelect,
  onTrimEdge,
  onPlace,
  onSetTrack,
}: Props) {
  const dur = Math.max(duration, 0.01);
  const shellRef = useRef<HTMLDivElement>(null);
  const v1TrackRef = useRef<HTMLDivElement>(null);
  const v2TrackRef = useRef<HTMLDivElement>(null);
  const [drag, setDrag] = useState<DragState | null>(null);
  const [ghost, setGhost] = useState<{
    leftPct: number;
    widthPct: number;
    track: number;
    label: string;
  } | null>(null);

  const v1 = clips.filter((c) => (c.track ?? 0) === 0);
  const v2 = clips.filter((c) => (c.track ?? 0) >= 1);

  const trackWidth = () => {
    const el = v1TrackRef.current || v2TrackRef.current;
    return el?.getBoundingClientRect().width || 1;
  };

  const xToTime = (clientX: number, trackEl: HTMLDivElement | null) => {
    const el = trackEl || v1TrackRef.current;
    if (!el) return 0;
    const rect = el.getBoundingClientRect();
    const x = Math.min(Math.max(0, clientX - rect.left), rect.width);
    return (x / Math.max(1, rect.width)) * dur;
  };

  const onTrackClick = (e: ReactMouseEvent<HTMLDivElement>) => {
    if (disabled || drag?.moved) return;
    const rect = e.currentTarget.getBoundingClientRect();
    const x = Math.min(Math.max(0, e.clientX - rect.left), rect.width);
    onSeek((x / rect.width) * dur);
  };

  const beginDrag = (
    e: ReactPointerEvent<HTMLElement>,
    clip: ClipInfo,
    kind: DragKind,
  ) => {
    if (disabled) return;
    e.preventDefault();
    e.stopPropagation();
    onSelect(clip.clip_id);
    const start = clip.timeline_start_sec;
    const end = clip.timeline_end_sec ?? start + (clip.out_sec - clip.in_sec);
    const v1r = v1TrackRef.current?.getBoundingClientRect();
    const v2r = v2TrackRef.current?.getBoundingClientRect();
    try {
      e.currentTarget.setPointerCapture(e.pointerId);
    } catch {
      /* ignore */
    }
    setDrag({
      kind,
      clipId: clip.clip_id,
      track: clip.track ?? 0,
      startClientX: e.clientX,
      startClientY: e.clientY,
      originStart: start,
      originEnd: end,
      laneTop: v1r?.top ?? 0,
      laneBottom: v2r?.bottom ?? (v1r?.bottom ?? 0),
      moved: false,
    });
    setGhost({
      leftPct: (start / dur) * 100,
      widthPct: (Math.max(0.05, end - start) / dur) * 100,
      track: clip.track ?? 0,
      label: clip.display_label || clip.clip_id,
    });
  };

  const onPointerMove = (e: ReactPointerEvent<HTMLDivElement>) => {
    if (!drag) return;
    const dx = e.clientX - drag.startClientX;
    const dy = e.clientY - drag.startClientY;
    if (!drag.moved && Math.abs(dx) + Math.abs(dy) > 3) {
      setDrag({ ...drag, moved: true });
    }
    const tw = trackWidth();
    const dt = (dx / tw) * dur;
    let left = drag.originStart;
    let width = drag.originEnd - drag.originStart;
    if (drag.kind === "in") {
      const newStart = Math.min(drag.originEnd - 0.05, Math.max(0, drag.originStart + dt));
      width = drag.originEnd - newStart;
      left = newStart;
    } else if (drag.kind === "out") {
      width = Math.max(0.05, drag.originEnd + dt - drag.originStart);
      left = drag.originStart;
    } else {
      left = Math.max(0, drag.originStart + dt);
    }
    // Vertical track target while dragging body
    let track = drag.track;
    if (drag.kind === "move") {
      const midY = (drag.laneTop + drag.laneBottom) / 2;
      const v2Top = v2TrackRef.current?.getBoundingClientRect().top ?? midY;
      track = e.clientY >= v2Top - 4 ? 1 : 0;
    }
    setGhost({
      leftPct: (left / dur) * 100,
      widthPct: (width / dur) * 100,
      track,
      label: ghost?.label || "",
    });
  };

  const endDrag = (e: ReactPointerEvent<HTMLDivElement>) => {
    if (!drag) return;
    const dx = e.clientX - drag.startClientX;
    const dy = e.clientY - drag.startClientY;
    const tw = trackWidth();
    const dt = (dx / tw) * dur;
    const moved = drag.moved || Math.abs(dx) + Math.abs(dy) > 3;

    if (moved) {
      if (drag.kind === "in" && onTrimEdge) {
        onTrimEdge(drag.clipId, "in", drag.originStart + dt);
      } else if (drag.kind === "out" && onTrimEdge) {
        onTrimEdge(drag.clipId, "out", drag.originEnd + dt);
      } else if (drag.kind === "move") {
        const v2Top = v2TrackRef.current?.getBoundingClientRect().top ?? 0;
        const targetTrack = e.clientY >= v2Top - 4 ? 1 : 0;
        const newStart = Math.max(0, drag.originStart + dt);
        if (targetTrack !== drag.track && onSetTrack) {
          onSetTrack(drag.clipId, targetTrack, newStart);
        } else if (onPlace) {
          onPlace(drag.clipId, newStart);
        }
      }
    } else {
      onSelect(drag.clipId);
      onSeek(drag.originStart + 0.01);
    }
    setDrag(null);
    setGhost(null);
  };

  const renderLane = (
    laneClips: ClipInfo[],
    label: string,
    colors: string[],
    laneClass: string,
    trackRef: RefObject<HTMLDivElement | null>,
    trackIndex: number,
  ) => (
    <div className={`tl-lane ${laneClass}`}>
      <div className="tl-lane-label">{label}</div>
      <div
        ref={trackRef}
        className={`tl-track ${disabled ? "disabled" : ""}`}
        onClick={onTrackClick}
        role="slider"
        aria-valuemin={0}
        aria-valuemax={dur}
        aria-valuenow={playhead}
        tabIndex={0}
        data-track={trackIndex}
      >
        {laneClips.map((c, i) => {
          const start = c.timeline_start_sec;
          const end = c.timeline_end_sec ?? start + (c.out_sec - c.in_sec);
          const left = (start / dur) * 100;
          const width = (Math.max(0.05, end - start) / dur) * 100;
          const selected = c.clip_id === selectedId;
          const dragging = drag?.clipId === c.clip_id;
          return (
            <div
              key={c.clip_id}
              className={`tl-clip ${selected ? "selected" : ""} ${dragging ? "dragging" : ""}`}
              style={{
                left: `${left}%`,
                width: `${width}%`,
                background: `linear-gradient(135deg, ${colors[i % colors.length]}55, ${colors[i % colors.length]}22)`,
                borderColor: colors[i % colors.length],
              }}
              title={`${c.display_label || c.clip_id} · ${c.track_label || label} · húzd a sávok között · szélek = Be/Ki`}
              onPointerDown={(ev) => beginDrag(ev, c, "move")}
            >
              <button
                type="button"
                className="tl-handle tl-handle-in"
                aria-label="Be pont (trim)"
                title="Be — húzd a kezdőpontot"
                disabled={disabled}
                onPointerDown={(ev) => beginDrag(ev, c, "in")}
              />
              <span className="tl-clip-label">{c.display_label || c.clip_id}</span>
              <button
                type="button"
                className="tl-handle tl-handle-out"
                aria-label="Ki pont (trim)"
                title="Ki — húzd a végpontot"
                disabled={disabled}
                onPointerDown={(ev) => beginDrag(ev, c, "out")}
              />
            </div>
          );
        })}
        {ghost && ghost.track === trackIndex ? (
          <div
            className="tl-clip tl-ghost"
            style={{
              left: `${ghost.leftPct}%`,
              width: `${ghost.widthPct}%`,
            }}
          >
            <span className="tl-clip-label">{ghost.label}</span>
          </div>
        ) : null}
        <div className="tl-playhead" style={{ left: `${(playhead / dur) * 100}%` }} />
      </div>
    </div>
  );

  return (
    <div
      className={`tl-shell ${drag ? "tl-dragging" : ""}`}
      ref={shellRef}
      onPointerMove={onPointerMove}
      onPointerUp={endDrag}
      onPointerCancel={endDrag}
    >
      <div className="tl-ruler">
        <span>0s</span>
        <span>{(dur / 2).toFixed(1)}s</span>
        <span>{dur.toFixed(1)}s</span>
      </div>
      {renderLane(v1, "V1", V1_COLORS, "v1", v1TrackRef, 0)}
      {renderLane(v2, "V2", V2_COLORS, "v2", v2TrackRef, 1)}
      <p className="tl-hint">
        Kattints a klipre · húzd V1↔V2 közé · szélek = Be/Ki trim
      </p>
    </div>
  );
}
