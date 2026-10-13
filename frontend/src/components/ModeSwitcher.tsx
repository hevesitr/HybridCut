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
    path === "CPU" ? "éles · CPU~720" : path === "CUDA" ? "éles · CUDA" : "éles export · apex";
  const maxTitle =
    path === "CPU"
      ? `Max — CPU ORT gyors bake (MobileNet~720). ETA: ${mEta}`
      : path === "CUDA"
        ? `Max — CUDA EP teljes ResNet/APEX. ETA: ${mEta}`
        : `Max háttéreltávolítás — éles export. Becsült idő: ${mEta}`;
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
        title={`Gyors háttéreltávolítás — élő scrub, lágyabb szélek. Becsült idő: ${gEta}`}
        onClick={() => onChange("gyors")}
      >
        <strong>Gyors</strong>
        <span>élő scrub · lágyabb</span>
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
        onClick={() => onChange("max")}
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
