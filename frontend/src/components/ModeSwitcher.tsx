type Props = {
  mode: "gyors" | "max";
  disabled?: boolean;
  onChange: (mode: "gyors" | "max") => void;
  /** Live ETA labels (Hungarian), e.g. „Kb. 12 mp”. */
  etaGyors?: string;
  etaMax?: string;
  /** Honest path for Max ETA: CUDA EP vs CPU ORT fast-path. */
  pathLabel?: "CUDA" | "CPU";
};

export function ModeSwitcher({
  mode,
  disabled,
  onChange,
  etaGyors,
  etaMax,
  pathLabel,
}: Props) {
  const gEta = etaGyors && etaGyors !== "Kb. —" ? etaGyors : "Kb. —";
  const mEta = etaMax && etaMax !== "Kb. —" ? etaMax : "Kb. —";
  const path = pathLabel === "CUDA" ? "CUDA" : pathLabel === "CPU" ? "CPU" : "";
  const maxSpan =
    path === "CPU" ? "éles · CPU~640" : path === "CUDA" ? "éles · CUDA" : "éles export · apex";
  const gyorsSpan =
    path === "CPU" ? "scrub · CPU~640" : path === "CUDA" ? "scrub · CUDA" : "élő scrub · lágyabb";
  const maxTitle =
    path === "CPU"
      ? `Max — CPU ORT light bake (MobileNet~640). ETA: ${mEta}`
      : path === "CUDA"
        ? `Max — CUDA EP teljes ResNet/APEX. ETA: ${mEta}`
        : `Max háttéreltávolítás — éles export. Becsült idő: ${mEta}`;
  const gyorsTitle =
    path === "CPU"
      ? `Gyors — CPU ORT bake (MobileNet~640, soft alpha). ETA: ${gEta}`
      : path === "CUDA"
        ? `Gyors — CUDA EP MobileNet scrub/bake. ETA: ${gEta}`
        : `Gyors háttéreltávolítás — élő scrub, lágyabb szélek. Becsült idő: ${gEta}`;
  return (
    <div
      className="mode-switch"
      data-mode={mode}
      data-path={path || undefined}
      role="radiogroup"
      aria-label="Háttéreltávolítás mód"
    >
      <button
        type="button"
        className={`mode-btn gyors ${mode === "gyors" ? "active" : ""}`}
        role="radio"
        aria-checked={mode === "gyors"}
        disabled={disabled}
        title={gyorsTitle}
        onClick={() => {
          if (mode !== "gyors") onChange("gyors");
        }}
      >
        <strong>Gyors</strong>
        <span>{gyorsSpan}</span>
        <em className="mode-eta" aria-label={`Gyors ETA ${gEta}`}>
          {gEta}
        </em>
      </button>
      <button
        type="button"
        className={`mode-btn max ${mode === "max" ? "active" : ""}`}
        role="radio"
        aria-checked={mode === "max"}
        disabled={disabled}
        title={maxTitle}
        onClick={() => {
          // Re-clicking active Max used to clear preview (setPreview null) and stall CPU re-polish.
          if (mode !== "max") onChange("max");
        }}
      >
        <strong>Max</strong>
        <span>{maxSpan}</span>
        <em className="mode-eta" aria-label={`Max ETA ${mEta}${path ? ` ${path}` : ""}`}>
          {mEta}
          {path ? ` · ${path}` : ""}
        </em>
      </button>
    </div>
  );
}
