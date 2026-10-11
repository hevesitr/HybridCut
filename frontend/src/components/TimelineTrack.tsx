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
  fps?: number;
  disabled?: boolean;
  onSeek: (t: number) => void;
  onSelect: (clipId: string) => void;
  /** Drag trim handle → Be/Ki via timeline time. */
  onTrimEdge?: (clipId: string, edge: "in" | "out", timelineT: number) => void;
  /** Horizontal place / reorder. */
  onPlace?: (clipId: string, timelineStartSec: number) => void;
  /** Vertical stack: drop onto V1 (0) or AI sáv / V2 (1). */
  onSetTrack?: (clipId: string, track: number, timelineStartSec?: number) => void;
  /** Manual AI polírozás on AI-sáv clip. */
  onPolish?: (clipId: string) => void;
  onAddClip?: () => void;
  onDelete?: () => void;
  onCut?: () => void;
  canDelete?: boolean;
};

const V1_COLORS = ["#8fd14f", "#6ecf7a", "#5bbf8a", "#3ecf9a"];
const AI_COLORS = ["#c8e86a", "#a8d44a", "#9ad000", "#7ab800"];

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

/** Concat-style timecode HH:MM:SS:FF */
export function formatTimecode(sec: number, fps = 24): string {
  const f = Math.max(1, Math.round(fps));
  const totalFrames = Math.max(0, Math.round(sec * f));
  const frames = totalFrames % f;
  const totalSec = Math.floor(totalFrames / f);
  const s = totalSec % 60;
  const m = Math.floor(totalSec / 60) % 60;
  const h = Math.floor(totalSec / 3600);
  const pad = (n: number, w = 2) => String(n).padStart(w, "0");
  return `${pad(h)}:${pad(m)}:${pad(s)}:${pad(frames)}`;
}

export function TimelineTrack({
  clips,
  duration,
  playhead,
  selectedId,
  fps = 24,
  disabled,
  onSeek,
  onSelect,
  onTrimEdge,
  onPlace,
  onSetTrack,
  onPolish,
  onAddClip,
  onDelete,
  onCut,
  canDelete,
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
  const [snapOn, setSnapOn] = useState(true);
  const [trackState, setTrackState] = useState({
    0: { lock: false, hide: false, mute: false },
    1: { lock: false, hide: false, mute: false },
  });

  const v1 = clips.filter((c) => (c.track ?? 0) === 0);
  const v2 = clips.filter((c) => (c.track ?? 0) >= 1);

  const trackWidth = () => {
    const el = v1TrackRef.current || v2TrackRef.current;
    return el?.getBoundingClientRect().width || 1;
  };

  const onTrackClick = (e: ReactMouseEvent<HTMLDivElement>, trackIndex: number) => {
    if (disabled || drag?.moved) return;
    if (trackState[trackIndex as 0 | 1]?.lock) return;
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
    const t = (clip.track ?? 0) >= 1 ? 1 : 0;
    if (trackState[t as 0 | 1]?.lock) return;
    e.preventDefault();
    e.stopPropagation();
    onSelect(clip.clip_id);
    // Keep keyboard focus on the timeline so Delete/Backspace removes the clip
    // (range scrub / number inputs must not swallow keys after click-select).
    try {
      shellRef.current?.focus({ preventScroll: true });
    } catch {
      shellRef.current?.focus();
    }
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
    let track = drag.track;
    if (drag.kind === "move") {
      const v2Top = v2TrackRef.current?.getBoundingClientRect().top ?? 0;
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
        let newStart = Math.max(0, drag.originStart + dt);
        if (snapOn) {
          newStart = Math.round(newStart * fps) / fps;
        }
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

  const toggleTrack = (track: 0 | 1, key: "lock" | "hide" | "mute") => {
    setTrackState((prev) => ({
      ...prev,
      [track]: { ...prev[track], [key]: !prev[track][key] },
    }));
  };

  const rulerMarks = [0, 0.25, 0.5, 0.75, 1].map((p) => ({
    pct: p * 100,
    label: formatTimecode(dur * p, fps),
  }));

  const renderLane = (
    laneClips: ClipInfo[],
    label: string,
    colors: string[],
    laneClass: string,
    trackRef: RefObject<HTMLDivElement | null>,
    trackIndex: 0 | 1,
  ) => {
    const st = trackState[trackIndex];
    return (
      <div
        className={`tl-lane ${laneClass}${st.hide ? " hidden" : ""}${st.mute ? " muted" : ""}${st.lock ? " locked" : ""}`}
      >
        <div className="tl-lane-chrome">
          <div className="tl-lane-label">{label}</div>
          <div className="tl-lane-toggles" role="group" aria-label={`${label} sáv`}>
            <button
              type="button"
              className={`tl-tog ${st.lock ? "on" : ""}`}
              title={st.lock ? "Feloldás" : "Zárolás"}
              aria-label={st.lock ? "Feloldás" : "Zárolás"}
              aria-pressed={st.lock}
              onClick={() => toggleTrack(trackIndex, "lock")}
            >
              L
            </button>
            <button
              type="button"
              className={`tl-tog ${st.hide ? "on" : ""}`}
              title={st.hide ? "Mutatás" : "Elrejtés"}
              aria-label={st.hide ? "Mutatás" : "Elrejtés"}
              aria-pressed={st.hide}
              onClick={() => toggleTrack(trackIndex, "hide")}
            >
              V
            </button>
            <button
              type="button"
              className={`tl-tog ${st.mute ? "on" : ""}`}
              title={st.mute ? "Hang be" : "Némítás"}
              aria-label={st.mute ? "Hang be" : "Némítás"}
              aria-pressed={st.mute}
              onClick={() => toggleTrack(trackIndex, "mute")}
            >
              M
            </button>
          </div>
        </div>
        <div
          ref={trackRef}
          className={`tl-track ${disabled || st.lock ? "disabled" : ""}`}
          onClick={(e) => onTrackClick(e, trackIndex)}
          role="slider"
          aria-valuemin={0}
          aria-valuemax={dur}
          aria-valuenow={playhead}
          tabIndex={0}
          data-track={trackIndex}
        >
          {st.hide
            ? null
            : laneClips.map((c, i) => {
                const start = c.timeline_start_sec;
                const end = c.timeline_end_sec ?? start + (c.out_sec - c.in_sec);
                const left = (start / dur) * 100;
                const width = (Math.max(0.05, end - start) / dur) * 100;
                const selected = c.clip_id === selectedId;
                const dragging = drag?.clipId === c.clip_id;
                const polish = (c.ai_polish || "idle").toLowerCase();
                const polishRunning = polish === "running" || polish === "pending";
                return (
                  <div
                    key={c.clip_id}
                    className={`tl-clip ${selected ? "selected" : ""} ${dragging ? "dragging" : ""}${
                      trackIndex === 1 ? " tl-clip-ai" : ""
                    }${polishRunning ? " tl-clip-polish" : ""}${polish === "done" ? " tl-clip-polish-done" : ""}`}
                    style={{
                      left: `${left}%`,
                      width: `${width}%`,
                      background: `linear-gradient(135deg, ${colors[i % colors.length]}66, ${colors[i % colors.length]}28)`,
                      borderColor: colors[i % colors.length],
                      opacity: st.mute ? 0.45 : 1,
                    }}
                    title={`${c.display_label || c.clip_id} · ${c.track_label || label} · húzd a sávok között · szélek = Be/Ki${
                      c.ai_polish_label_hu ? ` · ${c.ai_polish_label_hu}` : ""
                    }`}
                    onPointerDown={(ev) => beginDrag(ev, c, "move")}
                  >
                    <button
                      type="button"
                      className="tl-handle tl-handle-in"
                      aria-label="Be pont (trim)"
                      title="Be — húzd a kezdőpontot"
                      disabled={disabled || st.lock}
                      onPointerDown={(ev) => beginDrag(ev, c, "in")}
                    />
                    <span className="tl-clip-label">{c.display_label || c.clip_id}</span>
                    {trackIndex === 1 && onPolish ? (
                      <button
                        type="button"
                        className={`tl-polish-btn${polishRunning ? " running" : ""}`}
                        title={
                          polishRunning
                            ? "Polírozás folyamatban…"
                            : "Polírozás — ember-kivágás / él (RVM/APEX)"
                        }
                        aria-label="Polírozás"
                        disabled={disabled || st.lock || polishRunning}
                        onPointerDown={(ev) => {
                          ev.preventDefault();
                          ev.stopPropagation();
                        }}
                        onClick={(ev) => {
                          ev.preventDefault();
                          ev.stopPropagation();
                          onPolish(c.clip_id);
                        }}
                      >
                        {polishRunning ? "…" : "P"}
                      </button>
                    ) : null}
                    <button
                      type="button"
                      className="tl-handle tl-handle-out"
                      aria-label="Ki pont (trim)"
                      title="Ki — húzd a végpontot"
                      disabled={disabled || st.lock}
                      onPointerDown={(ev) => beginDrag(ev, c, "out")}
                    />
                  </div>
                );
              })}
          {ghost && ghost.track === trackIndex && !st.hide ? (
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
  };

  return (
    <div
      className={`tl-shell ${drag ? "tl-dragging" : ""}`}
      ref={shellRef}
      tabIndex={0}
      role="application"
      aria-label="Idővonal — kijelölt klip: Delete vagy Backspace töröl"
      onPointerMove={onPointerMove}
      onPointerUp={endDrag}
      onPointerCancel={endDrag}
      onKeyDown={(e) => {
        if (e.key !== "Delete" && e.key !== "Backspace") return;
        if (disabled || !canDelete || !onDelete) return;
        e.preventDefault();
        e.stopPropagation();
        onDelete();
      }}
    >
      <div className="tl-chrome-bar">
        <div className="tl-tabs" role="tablist" aria-label="Idővonal">
          <button type="button" className="tl-tab active" role="tab" aria-selected>
            Timeline 1
          </button>
        </div>
        <div className="tl-tools" role="toolbar" aria-label="Idővonal eszközök">
          <button
            type="button"
            className="tl-tool"
            title="Klip hozzáadása"
            disabled={disabled || !onAddClip}
            onClick={() => onAddClip?.()}
          >
            +
          </button>
          <button type="button" className="tl-tool" title="Visszavonás (helyi)" disabled>
            Undo
          </button>
          <button
            type="button"
            className="tl-tool"
            title="Vágás a lejátszási fejnél"
            disabled={disabled || !onCut}
            onClick={() => onCut?.()}
          >
            Cut
          </button>
          <button type="button" className="tl-tool on" title="Kijelölés" disabled={disabled}>
            Sel
          </button>
          <button
            type="button"
            className="tl-tool danger"
            title="Kijelölt klip törlése"
            disabled={disabled || !canDelete || !onDelete}
            onClick={() => onDelete?.()}
          >
            Del
          </button>
          <button
            type="button"
            className={`tl-tool snap ${snapOn ? "on" : ""}`}
            title={snapOn ? "Snap be" : "Snap ki"}
            aria-pressed={snapOn}
            onClick={() => setSnapOn((v) => !v)}
          >
            Snap
          </button>
          <span className="tl-playhead-tc" title="Lejátszási fej">
            {formatTimecode(playhead, fps)}
          </span>
        </div>
      </div>
      <div className="tl-ruler" aria-hidden>
        {rulerMarks.map((m) => (
          <span key={m.pct} style={{ left: `${m.pct}%` }} className="tl-ruler-mark">
            {m.label}
          </span>
        ))}
      </div>
      {renderLane(v1, "V1", V1_COLORS, "v1", v1TrackRef, 0)}
      {renderLane(v2, "AI sáv", AI_COLORS, "v2 ai", v2TrackRef, 1)}
      <p className="tl-hint">
        Kattints · húzd egymás alá → AI sáv · Polírozás auto · szélek = Be/Ki · L/V/M
      </p>
    </div>
  );
}
