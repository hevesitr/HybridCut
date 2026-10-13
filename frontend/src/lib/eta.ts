/** Bake / háttéreltávolítás ETA — RTX 3060-class (mirrors backend hybrid_editor/eta.py). */

export type BakeMode = "gyors" | "max";

/** Calibrated sec/frame @ 1920×1080, CUDA ORT RVM on RTX 3060 8GB-class. */
export const GYORS_SEC_PER_FRAME_1080P = 0.028;
export const MAX_SEC_PER_FRAME_1080P = 0.165;
const REF_PIXELS = 1920 * 1080;
const MUX_FIXED_SEC = 2.8;
const MUX_PER_VIDEO_SEC = 0.035;

const FRAME_RE = /(\d+)\s*\/\s*(\d+)\s*frame/i;

export function clipDurationSec(inSec: number, outSec: number, fallback = 0): number {
  const d = Number(outSec) - Number(inSec);
  if (d > 1e-6) return d;
  return Math.max(0, Number(fallback) || 0);
}

export function frameCount(durationSec: number, fps: number): number {
  const f = fps && fps > 1e-6 ? fps : 25;
  const d = Math.max(0, durationSec);
  return d > 1e-6 ? Math.max(1, Math.round(d * f)) : 0;
}

export function resolutionFactor(width: number, height: number, mode: BakeMode): number {
  // Missing probe → assume 720p (not fake 1080p) so ETA does not overstate work.
  const w = Math.max(1, width || 1280);
  const h = Math.max(1, height || 720);
  const mp = (w * h) / REF_PIXELS;
  if (mode === "gyors") {
    return 0.42 + 0.58 * Math.min(1.4, Math.max(0.35, mp ** 0.62));
  }
  return Math.min(2.4, Math.max(0.5, mp ** 0.88));
}

export function secPerFrame(
  width: number,
  height: number,
  mode: BakeMode,
  opts?: { cpuOrt?: boolean },
): number {
  const base = mode === "gyors" ? GYORS_SEC_PER_FRAME_1080P : MAX_SEC_PER_FRAME_1080P;
  let spf = base * resolutionFactor(width, height, mode);
  // CPU Max uses MobileNet@~720 fast-path (~CUDA wall clock). Gyors on CPU is slower.
  if (opts?.cpuOrt) {
    spf *= mode === "max" ? 1.15 : 2.4;
  }
  return spf;
}

export function estimateBakeSec(
  durationSec: number,
  fps: number,
  width: number,
  height: number,
  mode: BakeMode,
  opts?: { cpuOrt?: boolean },
): number {
  const n = frameCount(durationSec, fps);
  if (n <= 0) return 0;
  const matte = n * secPerFrame(width, height, mode, opts);
  const mux = MUX_FIXED_SEC + MUX_PER_VIDEO_SEC * Math.max(0, durationSec);
  return matte + mux;
}

/** Hungarian: „Kb. 12 mp” / „Kb. 1 perc 20 mp”. */
export function formatEtaHu(seconds: number): string {
  if (!Number.isFinite(seconds) || seconds <= 0) return "Kb. —";
  let s = Math.round(seconds);
  if (s < 1) s = 1;
  if (s < 60) return `Kb. ${s} mp`;
  const mins = Math.floor(s / 60);
  const rem = s % 60;
  if (mins < 60) {
    if (rem === 0) return `Kb. ${mins} perc`;
    return `Kb. ${mins} perc ${rem} mp`;
  }
  const hours = Math.floor(mins / 60);
  const m2 = mins % 60;
  if (m2 === 0 && rem === 0) return `Kb. ${hours} óra`;
  if (rem === 0) return `Kb. ${hours} óra ${m2} perc`;
  return `Kb. ${hours} óra ${m2} perc ${rem} mp`;
}

export function parseBakeFrames(bakeStatus: string): { done: number; total: number } | null {
  if (!bakeStatus) return null;
  const m = FRAME_RE.exec(bakeStatus);
  if (!m) return null;
  const done = Number(m[1]);
  const total = Number(m[2]);
  if (!total || total <= 0) return null;
  return { done: Math.max(0, done), total };
}

export function remainingBakeSec(opts: {
  durationSec: number;
  fps: number;
  width: number;
  height: number;
  mode: BakeMode;
  bakeProgress?: number;
  bakeStatus?: string;
  cpuOrt?: boolean;
  /** Wall-clock seconds since bake start — corrects lying model ETA on slow CPU. */
  elapsedSec?: number;
}): number {
  const cpuOpts = { cpuOrt: !!opts.cpuOrt };
  const total = estimateBakeSec(
    opts.durationSec,
    opts.fps,
    opts.width,
    opts.height,
    opts.mode,
    cpuOpts,
  );
  const parsed = parseBakeFrames(opts.bakeStatus || "");
  if (parsed) {
    const left = Math.max(0, parsed.total - parsed.done);
    let spf = secPerFrame(opts.width, opts.height, opts.mode, cpuOpts);
    const mux = MUX_FIXED_SEC + MUX_PER_VIDEO_SEC * Math.max(0, opts.durationSec);
    if (left <= 0) {
      const prog = Math.max(0, Math.min(1, opts.bakeProgress ?? 0));
      if (prog >= 0.99) return 0;
      return mux * Math.max(0.05, 1 - prog);
    }
    const el = Number(opts.elapsedSec) || 0;
    if (parsed.done >= 8 && el > 1.5) {
      const observed = el / parsed.done;
      spf =
        observed > spf * 1.35
          ? 0.25 * spf + 0.75 * observed
          : 0.65 * spf + 0.35 * observed;
    }
    return left * spf + mux * 0.85;
  }
  const prog = Math.max(0, Math.min(1, opts.bakeProgress ?? 0));
  if (prog <= 0.01) return total;
  if (prog >= 0.99) return 0;
  const el = Number(opts.elapsedSec) || 0;
  if (el > 2 && prog > 0.05) {
    return Math.max(0, (el / prog) * (1 - prog));
  }
  return total * (1 - prog);
}

export function bothModeEtas(
  durationSec: number,
  fps: number,
  width: number,
  height: number,
  opts?: { cpuOrt?: boolean },
): Record<BakeMode, { seconds: number; labelHu: string }> {
  const modes: BakeMode[] = ["gyors", "max"];
  const out = {} as Record<BakeMode, { seconds: number; labelHu: string }>;
  for (const mode of modes) {
    const seconds = estimateBakeSec(durationSec, fps, width, height, mode, opts);
    out[mode] = { seconds, labelHu: formatEtaHu(seconds) };
  }
  return out;
}
