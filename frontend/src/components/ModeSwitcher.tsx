type Props = {
  mode: "gyors" | "max";
  disabled?: boolean;
  onChange: (mode: "gyors" | "max") => void;
};

export function ModeSwitcher({ mode, disabled, onChange }: Props) {
  return (
    <div className="mode-switch" role="radiogroup" aria-label="Matting mód">
      <button
        type="button"
        className={`mode-btn gyors ${mode === "gyors" ? "active" : ""}`}
        role="radio"
        aria-checked={mode === "gyors"}
        disabled={disabled}
        onClick={() => onChange("gyors")}
      >
        <strong>Gyors</strong>
        <span>Élő scrub · MaskStore · proxy HOT</span>
        <em>ORT RVM — előnézet FPS</em>
      </button>
      <button
        type="button"
        className={`mode-btn max ${mode === "max" ? "active" : ""}`}
        role="radio"
        aria-checked={mode === "max"}
        disabled={disabled}
        onClick={() => onChange("max")}
      >
        <strong>Max</strong>
        <span>Seed paint · quality bake</span>
        <em>Pipeline / MatAnyone2 — export</em>
      </button>
    </div>
  );
}
