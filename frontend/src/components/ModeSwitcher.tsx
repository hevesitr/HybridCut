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
        title="Gyors mód: élő előnézet scrub közben, MaszkTár és proxy gyorsítótárral."
        onClick={() => onChange("gyors")}
      >
        <strong>Gyors mód</strong>
        <span>Élő előnézet · MaszkTár · proxy</span>
        <em>ORT RVM — előnézet FPS</em>
      </button>
      <button
        type="button"
        className={`mode-btn max ${mode === "max" ? "active" : ""}`}
        role="radio"
        aria-checked={mode === "max"}
        disabled={disabled}
        title="Max minőség: kézi maszk festés + minőségi export (hanggal)."
        onClick={() => onChange("max")}
      >
        <strong>Max minőség</strong>
        <span>Kézi maszk · minőségi export</span>
        <em>Pipeline / MatAnyone2 — export</em>
      </button>
    </div>
  );
}
