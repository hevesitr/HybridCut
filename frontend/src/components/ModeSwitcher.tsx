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
        title="Gyors = gyors/lágyabb élő előnézet (MobileNet scrub, MaszkTár, proxy)."
        onClick={() => onChange("gyors")}
      >
        <strong>Gyors</strong>
        <span>gyors / lágyabb</span>
        <em>MobileNet · élő scrub</em>
      </button>
      <button
        type="button"
        className={`mode-btn max ${mode === "max" ? "active" : ""}`}
        role="radio"
        aria-checked={mode === "max"}
        disabled={disabled}
        title="Max = élesebb export (ResNet50 ha van, szűk trimap, teljes felbontású bake)."
        onClick={() => onChange("max")}
      >
        <strong>Max</strong>
        <span>élesebb export</span>
        <em>ResNet / pipeline · bake</em>
      </button>
    </div>
  );
}
