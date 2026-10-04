import type { MouseEvent } from "react";
import type { ClipInfo } from "../lib/api";

type Props = {
  clips: ClipInfo[];
  duration: number;
  playhead: number;
  selectedId: string | null;
  disabled?: boolean;
  onSeek: (t: number) => void;
  onSelect: (clipId: string) => void;
};

const V1_COLORS = ["#3ecf9a", "#2fd4a1", "#6ec6ff", "#5bbf8a"];
const V2_COLORS = ["#d4a24c", "#e0b35a", "#e36b5b", "#c39bdc"];

export function TimelineTrack({
  clips,
  duration,
  playhead,
  selectedId,
  disabled,
  onSeek,
  onSelect,
}: Props) {
  const dur = Math.max(duration, 0.01);
  const v1 = clips.filter((c) => (c.track ?? 0) === 0);
  const v2 = clips.filter((c) => (c.track ?? 0) >= 1);

  const onTrackClick = (e: MouseEvent<HTMLDivElement>) => {
    if (disabled) return;
    const rect = e.currentTarget.getBoundingClientRect();
    const x = Math.min(Math.max(0, e.clientX - rect.left), rect.width);
    onSeek((x / rect.width) * dur);
  };

  const renderLane = (
    laneClips: ClipInfo[],
    label: string,
    colors: string[],
    laneClass: string,
  ) => (
    <div className={`tl-lane ${laneClass}`}>
      <div className="tl-lane-label">{label}</div>
      <div
        className={`tl-track ${disabled ? "disabled" : ""}`}
        onClick={onTrackClick}
        role="slider"
        aria-valuemin={0}
        aria-valuemax={dur}
        aria-valuenow={playhead}
        tabIndex={0}
      >
        {laneClips.map((c, i) => {
          const start = c.timeline_start_sec;
          const end = c.timeline_end_sec ?? start + (c.out_sec - c.in_sec);
          const left = (start / dur) * 100;
          const width = (Math.max(0.05, end - start) / dur) * 100;
          const selected = c.clip_id === selectedId;
          return (
            <button
              key={c.clip_id}
              type="button"
              className={`tl-clip ${selected ? "selected" : ""}`}
              style={{
                left: `${left}%`,
                width: `${width}%`,
                background: `linear-gradient(135deg, ${colors[i % colors.length]}55, ${colors[i % colors.length]}22)`,
                borderColor: colors[i % colors.length],
              }}
              disabled={disabled}
              onClick={(ev) => {
                ev.stopPropagation();
                onSelect(c.clip_id);
                onSeek(start + 0.01);
              }}
              title={`${c.display_label || c.clip_id} · ${c.track_label || label} · ${start.toFixed(2)}–${end.toFixed(2)}s`}
            >
              <span>{c.display_label || c.clip_id}</span>
            </button>
          );
        })}
        <div className="tl-playhead" style={{ left: `${(playhead / dur) * 100}%` }} />
      </div>
    </div>
  );

  return (
    <div className="tl-shell">
      <div className="tl-ruler">
        <span>0s</span>
        <span>{(dur / 2).toFixed(1)}s</span>
        <span>{dur.toFixed(1)}s</span>
      </div>
      {renderLane(v1, "V1", V1_COLORS, "v1")}
      {renderLane(v2, "V2 B-roll", V2_COLORS, "v2")}
    </div>
  );
}
