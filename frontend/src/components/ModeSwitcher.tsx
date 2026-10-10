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
        title="Gyors = élő scrub, gyors előnézet."
        onClick={() => onChange("gyors")}
      >
        <strong>Gyors</strong>
        <span>élő scrub</span>
      </button>
      <button
        type="button"
        className={`mode-btn max ${mode === "max" ? "active" : ""}`}
        role="radio"
        aria-checked={mode === "max"}
        disabled={disabled}
        title="Max = apex export (ResNet50 ha van, APEX polish, teljes felbontású bake)."
        onClick={() => onChange("max")}
      >
        <strong>Max</strong>
        <span>apex export</span>
      </button>
    </div>
  );
}
