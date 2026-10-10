type Props = {
  mode: "gyors" | "max";
  disabled?: boolean;
  onChange: (mode: "gyors" | "max") => void;
  /** Live ETA labels (Hungarian), e.g. „Kb. 12 mp”. */
  etaGyors?: string;
  etaMax?: string;
};

export function ModeSwitcher({ mode, disabled, onChange, etaGyors, etaMax }: Props) {
  const gEta = etaGyors && etaGyors !== "Kb. —" ? etaGyors : "Kb. —";
  const mEta = etaMax && etaMax !== "Kb. —" ? etaMax : "Kb. —";
  return (
    <div className="mode-switch" role="radiogroup" aria-label="Háttéreltávolítás mód">
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
        title={`Max háttéreltávolítás — éles export, APEX polish. Becsült idő: ${mEta}`}
        onClick={() => onChange("max")}
      >
        <strong>Max</strong>
        <span>éles export · apex</span>
        <em className="mode-eta" aria-label={`Max ETA ${mEta}`}>
          {mEta}
        </em>
      </button>
    </div>
  );
}
