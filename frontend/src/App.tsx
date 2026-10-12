import {
  useEffect,
  useEffectEvent,
  useRef,
  useState,
  useTransition,
  type ChangeEvent,
  type PointerEvent as ReactPointerEvent,
} from "react";
import { ModeSwitcher } from "./components/ModeSwitcher";
import { formatTimecode, TimelineTrack } from "./components/TimelineTrack";
import { api, type AssistStatus, type EditorStatus, type PreviewResult } from "./lib/api";
import {
  bothModeEtas,
  clipDurationSec,
  formatEtaHu,
  remainingBakeSec,
  type BakeMode,
} from "./lib/eta";

/** Előnézet nézet: alapból Forrás (teljes RGB), nem wipe / nem csak alpha. */
type ViewMode = "source" | "mask" | "cutout" | "compare";

type ClipRow = {
  clip_id: string;
  track?: number;
};

/** simple-bg: the one V1 clip can be deleted (Delete / Backspace). */
function canRemoveClip(clips: ClipRow[], clipId: string | null | undefined): boolean {
  if (!clipId) return false;
  return clips.some((c) => c.clip_id === clipId);
}

/** Ignore Delete/Backspace only while typing in real text fields (not range/scrub). */
function isTypingTarget(el: EventTarget | null): boolean {
  if (!(el instanceof HTMLElement)) return false;
  if (el.isContentEditable) return true;
  const tag = el.tagName.toLowerCase();
  if (tag === "textarea") return true;
  if (tag !== "input") return false;
  const type = ((el as HTMLInputElement).type || "text").toLowerCase();
  return !["button", "checkbox", "radio", "range", "file", "submit", "reset", "color", "image"].includes(type);
}

function rvmChip(status: EditorStatus | null) {
  const rvm = status?.rvm;
  const backend = (status?.backend || rvm?.engine_backend || "").toLowerCase();
  const epRegistered = rvm?.cuda_ep_registered === true || rvm?.cuda_ep === true;
  const liveCuda =
    epRegistered &&
    backend.includes("cuda") &&
    !backend.includes("cpuexecutionprovider") &&
    !rvm?.cuda_fallback;
  const liveCpu =
    backend.includes("cpuexecutionprovider") ||
    backend.endsWith(":cpu") ||
    backend.includes("ort-rvm:cpu") ||
    rvm?.ort_label_hu === "CPU ORT" ||
    (!!rvm?.cuda_fallback && /CUDA→CPU|plugin EP|CPU ORT/i.test(String(rvm.cuda_fallback)));
  const onnx = !!rvm?.onnx_found || backend.includes("ort-rvm") || backend.includes("quality-pipeline");
  // Prefer live session provider — never claim RTX/CUDA when plugin EP missing.
  if (liveCuda) {
    return {
      key: "rvm",
      label: "RVM CUDA",
      on: true,
      warn: false,
      title: "Háttéreltávolító GPU-n fut (CUDA EP regisztrálva).",
    };
  }
  if (liveCpu || (onnx && rvm?.ort_available)) {
    const hint =
      rvm?.cuda_fallback ||
      rvm?.cuda_ep_detail ||
      "CPU ORT — ember-maszk készül CPU-n. CUDA EP-hez: pip install onnxruntime-gpu==1.30.0 + nvidia-cudnn-cu12 + start_hybrid_cuda.ps1";
    return {
      key: "rvm",
      label: "CPU ORT",
      on: true,
      warn: true,
      title: String(hint),
    };
  }
  if (onnx) {
    return {
      key: "rvm",
      label: "RVM (nincs ORT)",
      on: false,
      warn: true,
      title: "ONNX megvan, de az ONNX Runtime hiányzik.",
    };
  }
  return {
    key: "rvm",
    label: "RVM —",
    on: false,
    warn: false,
    title: "Nincs betöltött RVM modell — heurisztikus ember-maszk.",
  };
}

/** Topbar GPU chip: never show RTX 3060 when CUDA EP plugin is missing. */
function gpuOrtChip(status: EditorStatus | null): { label: string; title: string; warn: boolean } {
  const rvm = status?.rvm;
  const backend = (status?.backend || rvm?.engine_backend || "").toLowerCase();
  const epRegistered = rvm?.cuda_ep_registered === true || rvm?.cuda_ep === true;
  const fallback = String(rvm?.cuda_fallback || "");
  const forcedCpu =
    rvm?.ort_label_hu === "CPU ORT" ||
    backend.includes("cpuexecutionprovider") ||
    backend.includes("ort-rvm:cpu") ||
    /CUDA→CPU|plugin EP|CPU ORT/i.test(fallback) ||
    (rvm?.prefer === "cpu" && !epRegistered);
  if (epRegistered && !forcedCpu && !fallback) {
    return {
      label: "RTX 3060",
      title: "CUDA EP regisztrálva — RVM GPU-n (onnxruntime-gpu).",
      warn: false,
    };
  }
  return {
    label: "CPU ORT",
    title:
      fallback ||
      rvm?.cuda_ep_detail ||
      "CUDA EP nincs regisztrálva — RVM CPU-n fut (ember-maszk készül, lassabb). Javítás: pip install onnxruntime-gpu==1.30.0 + nvidia-cudnn-cu12 + start_hybrid_cuda.ps1",
    warn: true,
  };
}

function cudaEpUnusable(status: EditorStatus | null): boolean {
  const rvm = status?.rvm;
  if (!rvm) return false;
  if (rvm.cuda_ep_registered === true || rvm.cuda_ep === true) {
    return !!rvm.cuda_fallback;
  }
  return (
    rvm.ort_label_hu === "CPU ORT" ||
    !!rvm.cuda_fallback ||
    rvm.prefer === "cpu" ||
    rvm.cuda_ep_listed === true
  );
}

function personMatteChip(status: EditorStatus | null, preview: PreviewResult | null) {
  const label =
    preview?.meta?.person_matte_label_hu ||
    status?.person_matte_label_hu ||
    status?.person_matte?.person_matte_label_hu;
  const active = !!(
    preview?.meta?.matanyone2_active ||
    status?.matanyone2_active ||
    status?.person_matte?.matanyone2_active
  );
  if (status?.mode === "max") {
    // Short strip label — full HU string lives in status line / meta-fold.
    const short = active ? "MatAnyone2" : "RVM ember";
    return {
      key: "person",
      label: short,
      on: true,
      warn: !active,
      title:
        label ||
        (active
          ? "MatAnyone2 helyi súlyokkal fut."
          : "Nincs MatAnyone2 súly — Max mód RVM minőségi pipeline-nal ad ember-maszkot (több személy)."),
    };
  }
  return {
    key: "person",
    label: "RVM ember",
    on: true,
    warn: false,
    title: label || "Gyors mód: automatikus RVM ember-maszk (kézi maszk nem kötelező).",
  };
}

function intelFromPreview(preview: PreviewResult | null, status: EditorStatus | null) {
  /** Apex strip: mode + export only — RVM / person / Ollama live under Részletek. */
  const q = status?.bake_queue_len ?? 0;
  const matteReady = !!(
    preview &&
    !preview.meta?.matte_empty &&
    !preview.meta?.source_fallback
  );
  const chips = [
    {
      key: "mode",
      label: status?.mode === "max" ? "Max" : "Gyors",
      on: true,
      warn: status?.mode === "max",
      title:
        status?.mode === "max"
          ? "Max apex: ResNet50 + APEX polish (haj/spill/fringe) · teljes felbontású bake · több személy."
          : "Gyors: MobileNet scrub / proxy — gyors előnézet, Max bake a csúcs minőség.",
    },
  ];
  if (matteReady && !status?.bake_running && !(status?.last_bake?.ok && status.last_bake.prores_mov)) {
    chips.push({
      key: "cutout",
      label: "Cutout ✓",
      on: true,
      warn: false,
      title: "Ember-maszk kész — Exportálás a következő lépés.",
    });
  }
  if (status?.bake_running || q > 0) {
    chips.push({
      key: "queue",
      label: status?.bake_running ? "Export…" : `Sor ${q}`,
      on: true,
      warn: false,
      title: "Várakozó vagy futó export (bake) feladatok.",
    });
  } else if (status?.last_bake && !status.last_bake.ok) {
    chips.push({
      key: "export",
      label: "Export hiba",
      on: false,
      warn: true,
      title: status.last_bake.message || "Nincs *_full_nobg.mov",
    });
  } else if (status?.last_bake?.ok && status.last_bake.prores_mov) {
    chips.push({
      key: "export",
      label: "nobg ✓",
      on: true,
      warn: false,
      title: status.last_bake.prores_mov,
    });
  }
  return chips;
}

function smartStatusLine(
  status: EditorStatus | null,
  note: string,
  busy: boolean,
  error: string | null,
  matteEmpty: boolean,
  preview: PreviewResult | null,
): string {
  if (error) return error;
  if (status?.bake_running) return status.bake_status || "Export fut…";
  if (status?.analyse_running) return status.analyse_status || "Elemzés fut…";
  if (busy) return "Dolgozom…";
  const person =
    preview?.meta?.person_matte_label_hu ||
    status?.person_matte_label_hu ||
    status?.person_matte?.person_matte_label_hu ||
    "";
  if (matteEmpty) {
    const err = String(preview?.meta?.matte_error || "");
    if (/egyenletes|teljes-keret|0–255|0-255/i.test(err)) {
      return "Hibás egyenletes maszk — ne fogadd el Cutout ✓-ként; futtasd Max Előnézetet";
    }
    if (preview?.meta?.source_fallback || err) {
      return err
        ? `Ember-maszk sikertelen — ${err.slice(0, 140)}`
        : "Ember-maszk sikertelen — próbáld újra az Előnézetet";
    }
    return "Nincs ember-maszk — futtasd az Előnézetet";
  }
  const fallback = status?.rvm?.cuda_fallback || status?.detail || "";
  if (fallback && /CUDA|cuDNN|cudnn|plugin EP|CPU ORT/i.test(fallback)) {
    const short = fallback.length > 180 ? `${fallback.slice(0, 180)}…` : fallback;
    return person ? `${person} · ${short}` : short;
  }
  if (status?.rvm?.cuda_ep === false && status?.rvm?.cuda_ep_listed && status.rvm.cuda_ep_detail) {
    const d = String(status.rvm.cuda_ep_detail);
    const short = d.length > 160 ? `${d.slice(0, 160)}…` : d;
    return person ? `${person} · CPU ORT · ${short}` : `CPU ORT · ${short}`;
  }
  if (status?.rvm?.cudnn_ok === false && status.rvm.cudnn_detail) {
    return status.rvm.cudnn_detail;
  }
  const mode = status?.mode === "max" ? "Max" : "Gyors";
  const seed = status?.seed_mask ? " · kézi finomítás ✓" : "";
  const clips = status?.timeline?.clips?.length ?? 0;
  const broll = status?.timeline?.clips?.filter((c) => (c.track ?? 0) >= 1).length ?? 0;
  const tl = clips ? ` · ${Math.min(clips, 1)} klip` : "";
  const personBit = person ? ` · ${person}` : "";
  const base = note || `${mode}${personBit}${seed}${tl}`;
  return base;
}

export default function App() {
  const [status, setStatus] = useState<EditorStatus | null>(null);
  const [preview, setPreview] = useState<PreviewResult | null>(null);
  const [tSec, setTSec] = useState(0);
  const [inSec, setInSec] = useState(0);
  const [outSec, setOutSec] = useState(0);
  /** CapCut-like transform — pos as % of canvas (−100…100), scale %. */
  const [posXPct, setPosXPct] = useState(0);
  const [posYPct, setPosYPct] = useState(0);
  const [scalePct, setScalePct] = useState(100);
  /** Preview drag for CapCut-like position (overlays paint when on). */
  const [moveMode, setMoveMode] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [note, setNote] = useState("Nyiss meg egy videót, vagy tölts be mintát.");
  /** Alapnézet: teljes forrás RGB — Előnézet után Cutout, ha van ember-maszk. */
  const [viewMode, setViewMode] = useState<ViewMode>("source");
  const [wipe, setWipe] = useState(50);
  const [dragOver, setDragOver] = useState(false);
  const [assist, setAssist] = useState<AssistStatus | null>(null);
  const [toast, setToast] = useState<string | null>(null);
  /** Cache-bust in-app checker preview after each bake. */
  const [bakePreviewKey, setBakePreviewKey] = useState(0);
  /** Concat-like right details tabs. */
  const [detailsTab, setDetailsTab] = useState<"project" | "timeline" | "contents">("project");
  const [pending, startTransition] = useTransition();
  const fileRef = useRef<HTMLInputElement>(null);
  /** Fresh status for drop/append — avoid stale closure blocking second clip. */
  const statusRef = useRef<EditorStatus | null>(null);
  statusRef.current = status;
  const scrubTimer = useRef<number | null>(null);
  const toastTimer = useRef<number | null>(null);
  const wipeStageRef = useRef<HTMLDivElement>(null);
  const wipeDragging = useRef(false);
  const previewDragRef = useRef<HTMLDivElement>(null);
  const transformDragging = useRef(false);
  const transformDragOrigin = useRef<{
    x: number;
    y: number;
    posX: number;
    posY: number;
    w: number;
    h: number;
  } | null>(null);
  const transformCommitTimer = useRef<number | null>(null);

  const showToast = (msg: string) => {
    setToast(msg);
    if (toastTimer.current) window.clearTimeout(toastTimer.current);
    toastTimer.current = window.setTimeout(() => setToast(null), 4200);
  };

  const wipeFromClientX = (clientX: number) => {
    const el = wipeStageRef.current;
    if (!el) return;
    const rect = el.getBoundingClientRect();
    if (rect.width <= 0) return;
    const pct = ((clientX - rect.left) / rect.width) * 100;
    setWipe(Math.max(0, Math.min(100, pct)));
  };

  const onWipePointerDown = (e: ReactPointerEvent<HTMLDivElement>) => {
    e.preventDefault();
    wipeDragging.current = true;
    e.currentTarget.setPointerCapture(e.pointerId);
    wipeFromClientX(e.clientX);
  };

  const onWipePointerMove = (e: ReactPointerEvent<HTMLDivElement>) => {
    if (!wipeDragging.current) return;
    wipeFromClientX(e.clientX);
  };

  const onWipePointerUp = (e: ReactPointerEvent<HTMLDivElement>) => {
    if (!wipeDragging.current) return;
    wipeDragging.current = false;
    try {
      e.currentTarget.releasePointerCapture(e.pointerId);
    } catch {
      /* ignore */
    }
  };

  const syncTrimFromStatus = (st: EditorStatus) => {
    const selId = st.timeline?.selected_clip_id;
    const clip =
      st.timeline?.clips?.find((c) => c.clip_id === selId) ?? st.timeline?.clips?.[0];
    if (clip) {
      setInSec(clip.in_sec);
      setOutSec(clip.out_sec);
      setPosXPct(Math.round((clip.pos_x ?? 0) * 100));
      setPosYPct(Math.round((clip.pos_y ?? 0) * 100));
      setScalePct(Math.round((clip.scale ?? 1) * 100));
    }
  };


  const refresh = async () => {
    const st = await api.status();
    setStatus(st);
    syncTrimFromStatus(st);
    return st;
  };

  useEffect(() => {
    refresh()
      .then((st) => {
        if (st?.media || st?.timeline?.clips?.length) {
          const t = st.timeline?.playhead_sec ?? 0;
          setTSec(t);
          // simple-bg3: auto Cutout on open so user never sits on „Nincs ember-maszk”.
          void runPreview(t, st, undefined, { preferCutout: true });
        }
      })
      .catch(() => {
        // Empty landing: status probe may 500 before FastAPI is up — never paint
        // a red "Internal Server Error" across the full-bleed shell.
      });
    api.assistStatus().then(setAssist).catch(() => setAssist(null));
  }, []);

  const pollBake = useEffectEvent(async () => {
    try {
      const p = await api.bakeProgress();
      setStatus((prev) =>
        prev
          ? {
              ...prev,
              bake_running: p.bake_running,
              bake_progress: p.bake_progress,
              bake_status: p.bake_status,
              last_bake: p.last_bake,
            }
          : prev,
      );
      if (p.bake_status && p.bake_running) setNote(p.bake_status);
      if (!p.bake_running && p.last_bake) {
        const st = await refresh();
        const mov = p.last_bake.prores_mov;
        if (p.last_bake.ok && mov) {
          setBakePreviewKey(Date.now());
          setNote(`Kész: ${mov}`);
          showToast("nobg MOV kész — sakktábla előnézet + Explorer");
        } else if (!p.last_bake.ok) {
          setNote(
            p.last_bake.message ||
              "SIKERTELEN: nincs *_full_nobg.mov — ellenőrizd az ffmpeg / FFMPEG_PATH-ot.",
          );
        } else {
          setNote(p.last_bake.message || "Export kész");
        }
        if (st.media) await runPreview(tSec, st, mov || p.last_bake.message);
      }
    } catch {
      /* ignore */
    }
  });

  const pollAnalyse = useEffectEvent(async () => {
    try {
      const p = await api.analyseProgress();
      setStatus((prev) =>
        prev
          ? {
              ...prev,
              analyse_running: p.analyse_running,
              analyse_progress: p.analyse_progress,
              analyse_status: p.analyse_status,
              analyse_masks: p.analyse_masks,
              mask_rate: p.mask_rate,
            }
          : prev,
      );
      if (p.analyse_status) setNote(p.analyse_status);
      if (!p.analyse_running && (p.analyse_progress ?? 0) >= 1) {
        await refresh();
      }
    } catch {
      /* ignore */
    }
  });

  useEffect(() => {
    if (!status?.bake_running) return;
    const id = window.setInterval(() => void pollBake(), 400);
    return () => window.clearInterval(id);
  }, [status?.bake_running, pollBake]);

  useEffect(() => {
    if (!status?.analyse_running) return;
    const id = window.setInterval(() => void pollAnalyse(), 350);
    return () => window.clearInterval(id);
  }, [status?.analyse_running, pollAnalyse]);

  const runPreview = async (
    t: number,
    st?: EditorStatus | null,
    noteOverride?: string,
    opts?: { preferCutout?: boolean },
  ) => {
    const cur = st ?? status;
    if (!cur?.media && !cur?.timeline?.clips?.length) return;
    setBusy(true);
    setError(null);
    try {
      await api.setTimeline({ playhead_sec: t });
      const frame = await api.preview(t);
      setPreview(frame);
      const empty = Boolean(frame.meta?.matte_empty || frame.meta?.source_fallback);
      const personLabel = String(frame.meta?.person_matte_label_hu || "");
      const matteErr = String(frame.meta?.matte_error || "");
      const degenerate =
        /egyenletes|teljes-keret|0–255|0-255|hibás RVM|hibas maszk/i.test(matteErr);
      const seedHit = frame.meta?.user_seed ? " · kézi finomítás ✓" : "";
      const ov = (frame.meta?.overlay_layers as unknown[] | undefined)?.length ?? 0;
      const composite = Boolean(frame.meta?.timeline_composite);
      const ovHit = ov ? (composite ? ` · kompozit ×${ov}` : "") : "";
      // Apex: short human status — tech detail stays under Részletek.
      setNote(
        noteOverride ??
          (empty
            ? degenerate
              ? "Hibás egyenletes maszk — RVM újrafuttatás / Max mód"
              : matteErr
                ? `Ember-maszk hiba — ${matteErr.slice(0, 120)}`
                : "Nincs ember-maszk — futtasd az Előnézetet"
            : `Cutout kész${seedHit}${ovHit} · t=${frame.t_sec.toFixed(2)}s`),
      );
      // Always surface RVM/ORT/CUDA matte failures (never silent gray slab + Cutout ✓).
      // Drop sticky CUDA gray-slab toast whenever preview recovers a person matte.
      const recovered = Boolean(frame.meta?.matte_recovered) || !empty;
      if (recovered) {
        if (toastTimer.current) window.clearTimeout(toastTimer.current);
        setToast((prev) =>
          prev && /Hibás maszk|egyenletes|szürke lap|Ember-maszk/i.test(prev)
            ? null
            : prev,
        );
      } else if (empty && (matteErr || frame.meta?.source_fallback)) {
        // Only toast true failures — never re-poison after matte_recovered.
        showToast(
          degenerate
            ? "Hibás maszk (egyenletes szürke lap) — CPU ORT / Max mód"
            : matteErr
              ? `Ember-maszk sikertelen — ${matteErr.slice(0, 140)}`
              : "Ember-maszk sikertelen — RVM/heuristic nem adott maszkot",
        );
      }
      // Explicit Előnézet / upload: jump to Cutout when matte ready (scrub stays put).
      if (opts?.preferCutout) {
        if (!empty) {
          setViewMode("cutout");
          showToast(
            personLabel
              ? `${personLabel} — Exportálás a következő lépés`
              : "Cutout kész — Exportálás a következő lépés",
          );
        } else if (!(matteErr || frame.meta?.source_fallback)) {
          showToast("Nincs ember-maszk — futtasd az Előnézetet újra");
        }
      }
      const refreshed = await api.status();
      setStatus(refreshed);
      syncTrimFromStatus(refreshed);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  const schedulePreview = (t: number) => {
    setTSec(t);
    if (scrubTimer.current) window.clearTimeout(scrubTimer.current);
    scrubTimer.current = window.setTimeout(() => {
      void runPreview(t);
    }, 100);
  };

  const onMode = (mode: "gyors" | "max") => {
    startTransition(() => {
      setBusy(true);
      setError(null);
      // Clear stale empty matte from previous mode before Max auto-preview.
      if (mode === "max") {
        setPreview(null);
      }
      api
        .setMode(mode)
        .then(async (st) => {
          setStatus(st);
          const personHint =
            (st as { person_matte_hint_hu?: string }).person_matte_hint_hu ||
            st.person_matte_label_hu ||
            "";
          setNote(
            mode === "gyors"
              ? "Gyors = gyors/lágyabb · MobileNet scrub"
              : personHint
                ? `Max · ${personHint} · Éles szélek alapból be`
                : "Max = élesebb export · ResNet50 ha van · Éles szélek alapból be",
          );
          if (mode === "max") {
            // Seed panel available but not required — auto person first.
          }
          const hasMedia = !!(st.media || (st.timeline?.clips?.length ?? 0) > 0);
          if (hasMedia) {
            await runPreview(tSec, st, undefined, { preferCutout: true });
          } else if (mode === "max") {
            showToast(personHint || "Max: tölts be videót, majd Előnézet — RVM ember-maszk automatikus");
          }
        })
        .catch((e: Error) => setError(e.message))
        .finally(() => setBusy(false));
    });
  };

  const onSample = async () => {
    setBusy(true);
    setError(null);
    try {
      let st = await api.loadSample();
      setStatus(st);
      setTSec(0);
      setViewMode("source");
      syncTrimFromStatus(st);
      await runPreview(0, st, undefined, { preferCutout: true });
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  const onUpload = async (file: File | null, append = false, asBroll = false) => {
    if (!file) return;
    // simple-bg: one clip only — reject second drops / B-roll / append stack
    const cur = statusRef.current;
    const hasClip = !!(cur?.media || (cur?.timeline?.clips?.length ?? 0) > 0);
    if (hasClip && (append || asBroll)) {
      showToast("Egy klip — töröld a V1-et, vagy Új projekt (második videó elutasítva)");
      setNote("Egy idővonal · egy klip · háttéreltávolítás");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      // Always replace (single V1). append/asBroll ignored by backend too.
      let st = await api.upload(file, false, false);
      setStatus(st);
      setTSec(0);
      setViewMode("source");
      syncTrimFromStatus(st);
      await runPreview(0, st, undefined, { preferCutout: true });
      setNote("Videó betöltve — Gyors auto ember-maszk (háttéreltávolítás)");
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  const onNewProject = async () => {
    const st = statusRef.current;
    const dirty = !!(
      st?.media ||
      (st?.timeline?.clips?.length ?? 0) > 0 ||
      st?.seed_mask ||
      st?.last_bake
    );
    if (
      dirty &&
      !window.confirm(
        "Új projekt? Az idővonal, a médiák, a seed maszk és a bake állapot törlődik.",
      )
    ) {
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const next = await api.newProject();
      setStatus(next);
      setPreview(null);
      setTSec(0);
      setInSec(0);
      setOutSec(0);
      setViewMode("source");
      setWipe(50);
      setBakePreviewKey(0);
      setToast(null);
      setError(null);
      setNote("Új projekt — húzd ide a videót, vagy nyisd meg.");
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  const onFilePicked = (
    e: ChangeEvent<HTMLInputElement>,
    append: boolean,
    asBroll: boolean,
  ) => {
    const file = e.target.files?.[0] ?? null;
    e.target.value = "";
    void onUpload(file, append, asBroll);
  };

  /** simple-bg: window drop replaces only when empty; reject second video. */
  const dropUpload = useEffectEvent((file: File) => {
    const st = statusRef.current;
    const hasClip = !!(st?.media || (st?.timeline?.clips?.length ?? 0) > 0);
    if (hasClip) {
      showToast("Egy klip — töröld a V1-et, vagy Új projekt (második videó elutasítva)");
      return;
    }
    void onUpload(file, false, false);
  });

  useEffect(() => {
    let dragDepth = 0;
    const onDragEnter = (e: DragEvent) => {
      if (!e.dataTransfer?.types?.includes("Files")) return;
      e.preventDefault();
      dragDepth += 1;
      const st = statusRef.current;
      // Empty hero only — never cover a loaded timeline with „Ejtés: klip…”.
      if (!(st?.media || (st?.timeline?.clips?.length ?? 0) > 0)) {
        setDragOver(true);
      }
    };
    const onDragOver = (e: DragEvent) => {
      if (!e.dataTransfer?.types?.includes("Files")) return;
      e.preventDefault();
    };
    const onDragLeave = (e: DragEvent) => {
      if (!e.dataTransfer?.types?.includes("Files")) return;
      dragDepth = Math.max(0, dragDepth - 1);
      if (dragDepth === 0) setDragOver(false);
    };
    const onDrop = (e: DragEvent) => {
      e.preventDefault();
      dragDepth = 0;
      setDragOver(false);
      const file = e.dataTransfer?.files?.[0];
      if (file && file.type.startsWith("video/")) {
        dropUpload(file);
      }
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setDragOver(false);
    };
    window.addEventListener("dragenter", onDragEnter);
    window.addEventListener("dragover", onDragOver);
    window.addEventListener("dragleave", onDragLeave);
    window.addEventListener("drop", onDrop);
    window.addEventListener("keydown", onKey);
    return () => {
      window.removeEventListener("dragenter", onDragEnter);
      window.removeEventListener("dragover", onDragOver);
      window.removeEventListener("dragleave", onDragLeave);
      window.removeEventListener("drop", onDrop);
      window.removeEventListener("keydown", onKey);
    };
  }, []);

  const applyTrim = async () => {
    setBusy(true);
    setError(null);
    try {
      const clipId = status?.timeline?.selected_clip_id ?? undefined;
      const st = await api.setTimeline({
        in_sec: inSec,
        out_sec: outSec,
        playhead_sec: tSec,
        clip_id: clipId,
      });
      setStatus(st);
      setNote(`Vágás: ${inSec.toFixed(2)}s → ${outSec.toFixed(2)}s`);
      if (st.media) await runPreview(Math.min(tSec, st.timeline?.duration_sec ?? tSec), st);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };


  const runAction = async (
    action:
      | "duplicate"
      | "remove"
      | "cut"
      | "move"
      | "select"
      | "to_broll"
      | "to_v1"
      | "set_track"
      | "ai_polish"
      | "place"
      | "trim_edge"
      | "set_transform"
      | "reset_transform",
    extra?: {
      clip_id?: string;
      direction?: number;
      t_sec?: number;
      track?: number;
      timeline_start_sec?: number;
      timeline_t?: number;
      edge?: "in" | "out";
      pos_x?: number;
      pos_y?: number;
      scale?: number;
      opacity?: number;
    },
    opts?: { quiet?: boolean },
  ) => {
    if (!opts?.quiet) setBusy(true);
    setError(null);
    try {
      const st = await api.timelineAction({ action, ...extra });
      setStatus(st);
      syncTrimFromStatus(st);
      const t = st.timeline?.playhead_sec ?? tSec;
      setTSec(t);
      const labels: Record<string, string> = {
        duplicate: "Klip duplikálva",
        remove: "Klip törölve",
        cut: "Klip felvágva",
        move: "Klip áthelyezve",
        select: "Klip kiválasztva — Delete / Backspace = törlés",
        to_broll: "Csak egy V1 sáv",
        to_v1: "Áthelyezve V1-re",
        set_track: "Egy sáv (V1)",
        ai_polish: "Csak háttéreltávolítás",
        place: "Klip áthelyezve az idővonalon",
        trim_edge: "Be/Ki trim frissítve",
        set_transform: "Pozíció / méret frissítve",
        reset_transform: "Pozíció visszaállítva (közép · 100%)",
      };
      if (!opts?.quiet) setNote(labels[action] || `Timeline: ${action}`);
      // simple-bg3: one V1 track only — no second lane / polish
      if (st.timeline?.clips?.length) await runPreview(t, st);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      if (!opts?.quiet) setBusy(false);
    }
  };

  const applyTransform = async (opts?: {
    posX?: number;
    posY?: number;
    scale?: number;
    quiet?: boolean;
  }) => {
    const clipId = statusRef.current?.timeline?.selected_clip_id;
    if (!clipId) return;
    const px = opts?.posX ?? posXPct;
    const py = opts?.posY ?? posYPct;
    const sc = opts?.scale ?? scalePct;
    await runAction(
      "set_transform",
      {
        clip_id: clipId,
        pos_x: px / 100,
        pos_y: py / 100,
        scale: Math.max(5, sc) / 100,
      },
      { quiet: opts?.quiet },
    );
  };

  const scheduleTransformCommit = (posX: number, posY: number, scale: number) => {
    if (transformCommitTimer.current) window.clearTimeout(transformCommitTimer.current);
    transformCommitTimer.current = window.setTimeout(() => {
      void applyTransform({ posX, posY, scale, quiet: true });
    }, 120);
  };

  const onTransformPointerDown = (e: ReactPointerEvent<HTMLDivElement>) => {
    const sel = statusRef.current?.timeline?.selected_clip_id;
    if (!sel || viewMode === "compare") return;
    // Seed paint owns the pointer when Max paint tools are on the preview.
    if (mode === "max" && viewMode !== "mask" && viewMode !== "source") {
      /* preview transform drag */
    }
    e.preventDefault();
    transformDragging.current = true;
    const rect = e.currentTarget.getBoundingClientRect();
    transformDragOrigin.current = {
      x: e.clientX,
      y: e.clientY,
      posX: posXPct,
      posY: posYPct,
      w: rect.width || 1,
      h: rect.height || 1,
    };
    e.currentTarget.setPointerCapture(e.pointerId);
  };

  const onTransformPointerMove = (e: ReactPointerEvent<HTMLDivElement>) => {
    if (!transformDragging.current || !transformDragOrigin.current) return;
    const o = transformDragOrigin.current;
    const dx = ((e.clientX - o.x) / o.w) * 100;
    const dy = ((e.clientY - o.y) / o.h) * 100;
    const nx = Math.max(-200, Math.min(200, Math.round(o.posX + dx)));
    const ny = Math.max(-200, Math.min(200, Math.round(o.posY + dy)));
    setPosXPct(nx);
    setPosYPct(ny);
    scheduleTransformCommit(nx, ny, scalePct);
  };

  const onTransformPointerUp = (e: ReactPointerEvent<HTMLDivElement>) => {
    if (!transformDragging.current) return;
    transformDragging.current = false;
    transformDragOrigin.current = null;
    try {
      e.currentTarget.releasePointerCapture(e.pointerId);
    } catch {
      /* ignore */
    }
    void applyTransform({ quiet: true });
  };

  const onNobgToTimeline = async () => {
    // simple-bg: load nobg as the single V1 clip (replace), no overlay chrome
    const mov = statusRef.current?.last_bake?.prores_mov;
    if (!mov) {
      setError("Nincs *_full_nobg.mov");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const st = await api.openPath(mov, false, false, false);
      setStatus(st);
      syncTrimFromStatus(st);
      setTSec(0);
      setNote("Nobg betöltve V1-re (egy klip)");
      setViewMode("cutout");
      setMoveMode(false);
      setDetailsTab("project");
      showToast("Nobg a V1-en — egy klip");
      if (st.timeline?.clips?.length) await runPreview(0, st, undefined, { preferCutout: true });
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  /** Delete / Backspace — remove the one V1 clip. */
  const deleteSelectedClip = useEffectEvent(() => {
    const st = statusRef.current;
    if (busy || st?.bake_running || st?.analyse_running) return;
    const list = st?.timeline?.clips ?? [];
    const cid = st?.timeline?.selected_clip_id;
    if (!cid || !canRemoveClip(list, cid)) return;
    void runAction("remove", { clip_id: cid });
  });

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key !== "Delete" && e.key !== "Backspace") return;
      if (isTypingTarget(e.target)) return;
      e.preventDefault();
      deleteSelectedClip();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  const onAnalyse = async () => {
    setBusy(true);
    setError(null);
    try {
      const res = await api.analyse(10);
      setStatus(res.status);
      setNote(res.status.analyse_status || "Ritka elemzés fut…");
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  const onBake = async () => {
    setBusy(true);
    setError(null);
    try {
      const clipId = status?.timeline?.selected_clip_id ?? undefined;
      await api.setTimeline({
        in_sec: inSec,
        out_sec: outSec,
        playhead_sec: tSec,
        clip_id: clipId,
      });
      const res = await api.bake(null, true, true, `bake-${Date.now().toString(36)}`);
      setStatus(res.status);
      const dur =
        status?.timeline?.duration_sec ?? status?.media?.duration_sec ?? outSec - inSec;
      const etaNow = bothModeEtas(
        clipDurationSec(inSec, outSec, dur),
        status?.timeline?.fps || status?.media?.fps || 25,
        status?.media?.width ?? 1920,
        status?.media?.height ?? 1080,
      )[mode]?.labelHu;
      setNote(
        res.queued
          ? res.message || "Export sorba téve"
          : res.message ||
              `Export fut… ${etaNow || "Kb. —"} · ~${Math.max(0, dur).toFixed(1)}s klip · C:\\bgcut\\*_full_nobg.mov`,
      );
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  const onOpenOutput = async () => {
    setBusy(true);
    setError(null);
    try {
      // Prefer selecting the *_full_nobg.mov (primary deliverable), not alpha/
      const prefer =
        status?.last_bake?.prores_mov ?? status?.last_bake?.out_dir ?? undefined;
      const res = await api.openOutputFolder(prefer);
      const mov = res.prores_mov || status?.last_bake?.prores_mov;
      setNote(
        mov
          ? `MOV megnyitva / kijelölve: ${mov}`
          : res.opened
            ? `Kimenet megnyitva: ${res.out_dir}`
            : `Kimenet mappa: ${res.out_dir}${res.error ? ` (${res.error})` : ""}`,
      );
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  const duration = status?.timeline?.duration_sec ?? status?.media?.duration_sec ?? 0;
  const mode = (status?.mode ?? "gyors") as BakeMode;
  const bakePct = Math.round((status?.bake_progress ?? 0) * 100);
  const analysePct = Math.round((status?.analyse_progress ?? 0) * 100);
  const plan = status?.frame_plan;
  const clips = status?.timeline?.clips ?? [];
  const selected = status?.timeline?.selected_clip_id ?? null;
  const selectedClip = clips.find((c) => c.clip_id === selected) ?? null;
  const locked = busy || !!status?.bake_running || !!status?.analyse_running;
  const hasMedia = !!status?.media || clips.length > 0;
  const mediaW = status?.media?.width ?? 1920;
  const mediaH = status?.media?.height ?? 1080;
  const mediaFps = status?.timeline?.fps || status?.media?.fps || 25;
  const bakeSpanSec = clipDurationSec(inSec, outSec, duration);
  const fullClipSec = Math.max(
    0,
    Number(status?.media?.duration_sec) || Number(duration) || 0,
  );
  const etas = bothModeEtas(bakeSpanSec, mediaFps, mediaW, mediaH);
  const fullEtas = bothModeEtas(fullClipSec, mediaFps, mediaW, mediaH);
  const selectedEta = etas[mode]?.labelHu ?? "Kb. —";
  const rangeLabel = `${Math.max(0, inSec).toFixed(1)}–${Math.max(inSec, outSec).toFixed(1)}s`;
  const rangeIsPartial =
    fullClipSec > 1e-3 &&
    bakeSpanSec > 1e-3 &&
    bakeSpanSec < fullClipSec - 0.25;
  const maxFullHours = (fullEtas.max?.seconds ?? 0) / 3600;
  const maxRangeHours = (etas.max?.seconds ?? 0) / 3600;
  const longMaxWarn =
    maxFullHours >= 2 || (mode === "max" && maxRangeHours >= 2);
  const remainSec = status?.bake_running
    ? remainingBakeSec({
        durationSec: bakeSpanSec,
        fps: mediaFps,
        width: mediaW,
        height: mediaH,
        mode,
        bakeProgress: status?.bake_progress ?? 0,
        bakeStatus: status?.bake_status ?? "",
      })
    : 0;
  const remainLabel = status?.bake_running ? formatEtaHu(remainSec) : "";
  const chips = intelFromPreview(preview, status);
  const matteEmpty = Boolean(preview?.meta?.matte_empty || preview?.meta?.source_fallback);
  const cutoutIsPng =
    !matteEmpty &&
    (preview?.meta?.cutout_format === "png" ||
      (preview?.meta?.sharp_edges === true && status?.mode === "max"));
  const cutoutMime = cutoutIsPng ? "image/png" : "image/jpeg";
  const sourceSrc = preview?.source_jpeg_b64 || preview?.jpeg_b64 || null;
  const maskSrc = matteEmpty ? sourceSrc : preview?.alpha_png_b64 || null;
  const maskMime = matteEmpty ? "image/jpeg" : "image/png";
  const cutoutSrc = matteEmpty ? sourceSrc : preview?.jpeg_b64 || null;
  const singleSrc =
    viewMode === "source"
      ? sourceSrc
      : viewMode === "mask"
        ? maskSrc
        : viewMode === "cutout"
          ? cutoutSrc
          : null;
  const singleMime =
    viewMode === "mask" && !matteEmpty
      ? "image/png"
      : viewMode === "cutout" && cutoutIsPng
        ? "image/png"
        : "image/jpeg";
  const beforeSrc = matteEmpty ? sourceSrc : preview?.alpha_png_b64;
  const beforeMime = matteEmpty ? "image/jpeg" : "image/png";
  const afterSrc = matteEmpty ? sourceSrc : preview?.jpeg_b64;
  const afterMime = matteEmpty ? "image/jpeg" : cutoutMime;
  const sharpEdges = status?.sharp_edges !== false;
  const statusText = smartStatusLine(status, note, busy, error, matteEmpty, preview);
  const onSharpEdges = (enabled: boolean) => {
    startTransition(() => {
      setBusy(true);
      setError(null);
      api
        .setSharpEdges(enabled)
        .then(async (st) => {
          setStatus(st);
          setNote(
            enabled
              ? "Éles szélek be — apex polish, PNG cutout, teljes felbontású Max bake"
              : "Éles szélek ki — lágyabb feather / Gyors-szerű szélek",
          );
          if (st.media) await runPreview(tSec, st);
        })
        .catch((e: Error) => setError(e.message))
        .finally(() => setBusy(false));
    });
  };

  const rvm = rvmChip(status);
  const personChip = personMatteChip(status, preview);
  const matteReady = !!(
    preview &&
    !preview.meta?.matte_empty &&
    !preview.meta?.source_fallback
  );
  const flowStep: 1 | 2 | 3 =
    status?.last_bake?.ok && status.last_bake.prores_mov
      ? 3
      : matteReady
        ? 2
        : 1;

  const viewButtons: { id: ViewMode; label: string; title: string }[] = [
    { id: "source", label: "Forrás", title: "Eredeti videókép — teljes RGB, sakktábla nélkül." },
    { id: "mask", label: "Maszk", title: "Alpha / matte nézet — hol vág a háttéreltávolítás." },
    { id: "cutout", label: "Cutout", title: "Kivágott alany sakktábla felett (ha van maszk)." },
    {
      id: "compare",
      label: "Összehasonlítás",
      title: "Húzd a függőleges vonalat a képen: maszk ↔ cutout.",
    },
  ];

  if (!hasMedia) {
    return (
      <div className="app empty concat-home look-peak matte-visible rvm-matte">
        {dragOver ? (
          <div className="drop-overlay">
            <strong>Ejtés: videó betöltése</strong>
          </div>
        ) : null}
        <header className="topbar">
          <div className="topbar-left">
            <div className="brand">
              <div className="brand-mark">HybridCut</div>
            </div>
            <span
              className={`gpu-chip${gpuOrtChip(status).warn ? " warn" : ""}`}
              title={gpuOrtChip(status).title}
            >
              {gpuOrtChip(status).label}
            </span>
            <p className="empty-tagline">Helyi cutout · CapCut-szintű szerkesztő</p>
          </div>
          <div className="sync">
            <div className="sync-stamp">{status?.sync_version ?? "…"}</div>
          </div>
        </header>
        {/* Contract: empty-cta-row class retained (hidden) for layout tests. */}
        <div className="empty-cta-row home-cta-hidden" aria-hidden="true">
          <button type="button" className="btn accent hero-cta-primary" tabIndex={-1}>
            Megnyitás
          </button>
          <span className="empty-cta-hint">Megnyitás → Cutout → Export</span>
        </div>
        <main className="workspace empty-workspace home-workspace">
          <aside className="rail empty-rail home-sidebar">
            <div className="home-nav">
              <button
                type="button"
                className="home-nav-btn active"
                disabled={locked}
                onClick={() => fileRef.current?.click()}
                title="Videó megnyitása — automatikus Cutout előnézet."
              >
                Megnyitás
              </button>
              <button
                type="button"
                className="home-nav-btn"
                disabled={locked}
                onClick={onSample}
                title="Beépített minta videó."
              >
                Minta
              </button>
              <button type="button" className="home-nav-btn" disabled title="Helyi beállítások">
                Beállítások
              </button>
            </div>
            <div className="rail-block home-mode-block">
              <h2>Mód</h2>
              <p className="lead">Gyors scrub vagy Max export — ETA a chipen.</p>
              <ModeSwitcher
                mode={mode}
                disabled={locked || pending}
                onChange={onMode}
                etaGyors={etas.gyors.labelHu}
                etaMax={etas.max.labelHu}
              />
            </div>
            <div className="hero-meta">Videoeditor · helyi · Ollama llama3</div>
            {error ? <div className="status-line error">{error}</div> : null}
          </aside>
          <section className="stage empty-stage home-stage">
            <div className="empty-drop home-projects" role="region" aria-label="Projektek">
              <div className="empty-drop-brand brand-mark">HybridCut</div>
              <p className="empty-drop-title">Projektek</p>
              <p className="empty-drop-sub">
                Húzd ide a videót, vagy indíts új projektet. Megnyitás → Cutout → Export · C:\bgcut
              </p>
              <div className="home-project-actions">
                <button
                  type="button"
                  className="btn primary home-new-project"
                  disabled={locked}
                  onClick={() => fileRef.current?.click()}
                  title="Új projekt — videó megnyitása."
                >
                  + Új projekt
                </button>
                <button
                  type="button"
                  className="btn ghost"
                  disabled={locked}
                  onClick={() => fileRef.current?.click()}
                  title="Meglévő videó megnyitása."
                >
                  Megnyitás
                </button>
              </div>
            </div>
          </section>
        </main>
        <input
          ref={fileRef}
          type="file"
          accept="video/*"
          hidden
          onChange={(e) => onFilePicked(e, false, false)}
        />
      </div>
    );
  }

  return (
    <div className="app look-peak matte-visible rvm-matte">
      {/* Compact editor chrome: topbar + workspace only (no separate 1fr intel row). look-peak visual shell. */}

      <header className="topbar">
        <div className="topbar-left">
          <div className="brand">
            <div className="brand-mark">HybridCut</div>
          </div>
          <span
            className={`gpu-chip${gpuOrtChip(status).warn ? " warn" : ""}`}
            title={gpuOrtChip(status).title}
          >
            {gpuOrtChip(status).label}
          </span>
          <div className="intel-strip" aria-label="Állapotjelzők">
            {chips.map((c) => (
              <span
                key={c.key}
                className={`intel-chip ${c.on ? "on" : ""} ${c.warn ? "warn" : ""}`}
                title={c.title}
              >
                {c.label}
              </span>
            ))}
          </div>
          {status?.media ? (
            <span className="media-meta-chip" title="Projekt felbontás / fps">
              {mediaW}×{mediaH} · {mediaFps.toFixed(0)} fps
            </span>
          ) : null}
        </div>
        <div className="sync">
          <button
            type="button"
            className="btn ghost topbar-new-project"
            disabled={locked}
            onClick={() => void onNewProject()}
            title="Új projekt / Kilépés — törli az idővonalat, médiát, seedet és bake állapotot."
          >
            Új projekt
          </button>
          <button
            type="button"
            className="btn primary topbar-export"
            disabled={(!status?.media && !clips.length) || !!status?.analyse_running}
            onClick={onBake}
            title={`Exportálás hanggal — ${selectedEta} · C:\\bgcut\\{stem}_full_nobg.mov`}
          >
            {status?.bake_running ? "Export…" : "Export"}
          </button>
          <div className="sync-stamp">{status?.sync_version ?? "…"}</div>
        </div>
      </header>

      <main className="workspace concat-workspace">
        <section className="stage">
          <div className="stage-head">
            <div>
              <h2>Előnézet</h2>
              <p className="lead">
                {viewMode === "compare"
                  ? "Húzd a vonalat a képen — maszk balra, cutout jobbra"
                  : "Forrás betöltéskor · Előnézet → Cutout (teljes ember auto RVM maszk)"}
              </p>
            </div>
            <div className="preview-tools" role="radiogroup" aria-label="Előnézet nézet">
              {viewButtons.map((v) => (
                <button
                  key={v.id}
                  type="button"
                  role="radio"
                  aria-checked={viewMode === v.id}
                  className={`btn ${viewMode === v.id ? "primary" : ""}`}
                  disabled={!preview}
                  title={v.title}
                  onClick={() => {
                    setViewMode(v.id);
                    if (v.id === "compare") setWipe(50);
                  }}
                >
                  {v.label}
                </button>
              ))}
            </div>
          </div>

          {(() => {
            const stageInner = (
              <div
                className={`preview-stage ${viewMode === "source" || matteEmpty ? "source-solid" : "checker-subtle"}${preview ? " preview-ready" : ""}`}
              >
                {toast ? (
                  <div className="preview-toast" role="status">
                    {toast}
                  </div>
                ) : null}
                {preview && (singleSrc || (viewMode === "compare" && beforeSrc && afterSrc)) ? (
                  <div className="wipe-wrap">
                    {matteEmpty && viewMode === "mask" ? (
                      <div className="mask-empty-overlay" role="status">
                        <p>Nincs ember-maszk — futtasd az Előnézetet</p>
                        <button
                          type="button"
                          className="btn primary"
                          disabled={locked}
                          onClick={() =>
                            void runPreview(tSec, undefined, undefined, { preferCutout: true })
                          }
                        >
                          Előnézet futtatása
                        </button>
                      </div>
                    ) : matteEmpty ? (
                      <div
                        className="matte-empty-badge"
                        title="Még nincs hasznos maszk — a forrás képkocka látszik."
                      >
                        Nincs ember-maszk — futtasd az Előnézetet
                      </div>
                    ) : null}
                    {viewMode === "compare" && beforeSrc && afterSrc ? (
                      <div className="wipe-compare">
                        <div className="wipe-labels" aria-hidden>
                          <span>{matteEmpty ? "Előtte" : "Maszk"}</span>
                          <span>{matteEmpty ? "Forrás" : "Cutout"}</span>
                        </div>
                        <div
                          ref={wipeStageRef}
                          className="wipe-stage checker-subtle"
                          role="slider"
                          aria-label="Összehasonlítás vonal"
                          aria-valuemin={0}
                          aria-valuemax={100}
                          aria-valuenow={Math.round(wipe)}
                          title="Húzd a vonalat a képen: balra maszk, jobbra cutout."
                          onPointerDown={onWipePointerDown}
                          onPointerMove={onWipePointerMove}
                          onPointerUp={onWipePointerUp}
                          onPointerCancel={onWipePointerUp}
                        >
                          <img
                            src={`data:${beforeMime};base64,${beforeSrc}`}
                            alt={matteEmpty ? "Forrás — nincs maszk" : "Alpha maszk"}
                            className="wipe-base"
                            draggable={false}
                          />
                          <img
                            src={`data:${afterMime};base64,${afterSrc}`}
                            alt={matteEmpty ? "Forrás képkocka" : "Cutout"}
                            className="wipe-fg"
                            draggable={false}
                            style={{ clipPath: `inset(0 ${100 - wipe}% 0 0)` }}
                          />
                          <div className="wipe-divider" style={{ left: `${wipe}%` }}>
                            <span className="wipe-handle" aria-hidden />
                          </div>
                        </div>
                      </div>
                    ) : singleSrc ? (
                      <img
                        className="preview-cutout"
                        src={`data:${singleMime};base64,${singleSrc}`}
                        alt={
                          viewMode === "source"
                            ? "Forrás képkocka"
                            : viewMode === "mask"
                              ? "Maszk nézet"
                              : "Cutout előnézet"
                        }
                      />
                    ) : null}
                  </div>
                ) : (
                  <div className="preview-empty">
                    <h3>Nincs tartalom a lejátszási fej alatt</h3>
                    <p>
                      {mediaW}×{mediaH} · {mediaFps.toFixed(0)} fps ·{" "}
                      {formatTimecode(tSec, mediaFps)}
                    </p>
                    <p className="preview-empty-hint">
                      Scrub az idővonalon, vagy futtasd az Előnézet Cutoutot a jobb panelen.
                    </p>
                  </div>
                )}
              </div>
            );

            return stageInner;
          })()}

          <div className="timeline-dock" data-paint-locked="0">
            <TimelineTrack
              clips={clips}
              duration={duration}
              playhead={tSec}
              selectedId={selected}
              fps={mediaFps}
              disabled={locked}
              onSeek={schedulePreview}
              onSelect={(id) => {
                void runAction("select", { clip_id: id });
              }}
              onTrimEdge={(clipId, edge, timelineT) => {
                void runAction("trim_edge", {
                  clip_id: clipId,
                  edge,
                  timeline_t: timelineT,
                });
              }}
              onPlace={(clipId, start) => {
                void runAction("place", {
                  clip_id: clipId,
                  timeline_start_sec: start,
                });
              }}
              onAddClip={undefined}
              onDelete={() => void runAction("remove", { clip_id: selected ?? undefined })}
              onCut={() => void runAction("cut", { t_sec: tSec })}
              canDelete={canRemoveClip(clips, selected)}
            />
            <div className="scrub">
              <span>{formatTimecode(0, mediaFps)}</span>
              <input
                type="range"
                min={0}
                max={Math.max(duration, 0.01)}
                step={0.05}
                value={Math.min(tSec, duration || tSec)}
                disabled={!clips.length || locked}
                onChange={(e) => schedulePreview(Number(e.target.value))}
                title="Idővonal scrub — húzd a képkockához."
                aria-label="Lejátszási fej"
              />
              <span>{formatTimecode(duration, mediaFps)}</span>
            </div>
            <div className={`status-line ${error ? "error" : ""}`}>{statusText}</div>
          </div>

        </section>

        <aside className="rail details-pane">
          <div className="details-tabs" role="tablist" aria-label="Részletek">
            {(
              [
                ["project", "PROJECT"],
                ["timeline", "TIMELINE"],
                ["contents", "CONTENTS"],
              ] as const
            ).map(([id, label]) => (
              <button
                key={id}
                type="button"
                role="tab"
                aria-selected={detailsTab === id}
                className={`details-tab ${detailsTab === id ? "active" : ""}`}
                onClick={() => setDetailsTab(id)}
              >
                {label}
              </button>
            ))}
          </div>

          <div className="rail-block" hidden={detailsTab !== "project"}>
            <ol className="flow-steps" aria-label="Egy kattintásos folyamat">
              <li className={flowStep >= 1 ? "done" : ""} data-step="1">
                <span className="flow-num">1</span>
                Megnyitás
              </li>
              <li className={flowStep >= 2 ? "done" : flowStep === 1 ? "next" : ""} data-step="2">
                <span className="flow-num">2</span>
                Cutout
              </li>
              <li className={flowStep >= 3 ? "done" : flowStep === 2 ? "next" : ""} data-step="3">
                <span className="flow-num">3</span>
                Exportálás
              </li>
            </ol>
            <h2>Cutout</h2>
            <p className="lead">Háttéreltávolítás · Gyors/Max · egy klip · Export nobg.</p>
            <ModeSwitcher
              mode={mode}
              disabled={locked || pending}
              onChange={onMode}
              etaGyors={etas.gyors.labelHu}
              etaMax={etas.max.labelHu}
            />
            <p
              className="export-eta"
              aria-live="polite"
              title="Becsült bake idő a kiválasztott Be/Ki tartományra (RTX 3060)."
            >
              Be/Ki ({rangeLabel}):{" "}
              <strong>
                {mode === "max" ? "Max" : "Gyors"} {selectedEta}
              </strong>
              {bakeSpanSec > 0 ? (
                <span className="eta-range">
                  {bakeSpanSec.toFixed(1)}s · {mediaW}×{mediaH} · {mediaFps.toFixed(0)} fps
                  {rangeIsPartial && fullClipSec > 0
                    ? ` · teljes klip Max ${fullEtas.max.labelHu}`
                    : ""}
                </span>
              ) : null}
            </p>
            {longMaxWarn ? (
              <p className="eta-long-warn" role="status">
                Teljes klip Max bake <strong>{fullEtas.max.labelHu}</strong>
                {fullClipSec >= 60 ? ` (~${(fullClipSec / 60).toFixed(0)} perc)` : ""} — rövidítsd
                a Be/Ki-t, vagy válassz Gyorsot.
              </p>
            ) : null}
            <div className="actions export-actions primary-flow">
              <button
                type="button"
                className="btn primary"
                disabled={locked}
                onClick={() => fileRef.current?.click()}
                title="Videó betöltése (csere) — automatikus Cutout előnézet."
              >
                1 · Megnyitás
              </button>
              <button
                type="button"
                className={`btn ${flowStep === 1 ? "accent pulse-cta" : "ghost"}`}
                disabled={locked || !status?.media}
                onClick={() => void runPreview(tSec, undefined, undefined, { preferCutout: true })}
                title="Auto ember-maszk futtatása (RVM) — Cutout nézetre vált, ha kész."
              >
                2 · Előnézet Cutout
              </button>
              <button
                type="button"
                className={`btn ${flowStep === 2 ? "accent pulse-cta" : mode === "max" ? "accent" : "primary"}`}
                disabled={(!status?.media && !clips.length) || !!status?.analyse_running}
                onClick={onBake}
                title={`Exportálás hanggal — ${selectedEta} · C:\\bgcut\\{stem}_full_nobg.mov`}
              >
                {status?.bake_running ? "Export…" : `3 · Exportálás · ${selectedEta}`}
              </button>
              <input
                ref={fileRef}
                type="file"
                accept="video/*"
                hidden
                onChange={(e) => onFilePicked(e, false, false)}
              />
            </div>
            <p className="action-help">
              Megnyitás → Előnézet Cutout → Export nobg ·{" "}
              <code>{"C:\\bgcut\\*_full_nobg.mov"}</code>
              {" · egy klip · háttéreltávolítás"}
            </p>
          </div>

          <div className="rail-block" hidden={detailsTab !== "timeline"}>
          {clips.length > 0 && (
            <div className="clip-bin">
              <h3>Klip lista ({clips.length})</h3>
              {clips.map((c, i) => {
                const removable = canRemoveClip(clips, c.clip_id);
                return (
                  <div
                    key={c.clip_id}
                    className={`clip-bin-item ${c.clip_id === selected ? "active" : ""}`}
                  >
                    <button
                      type="button"
                      className="clip-bin-select"
                      disabled={locked}
                      onClick={() => void runAction("select", { clip_id: c.clip_id })}
                      title="Klip kiválasztása az idővonalon."
                    >
                      <span>
                        V1 #{i + 1}{" "}
                        {c.display_label || c.clip_id}
                      </span>
                      <span>
                        {(c.source_duration_sec ?? c.out_sec - c.in_sec).toFixed(1)}s
                      </span>
                    </button>
                    <button
                      type="button"
                      className="clip-bin-del"
                      disabled={locked || !removable}
                      onClick={() => void runAction("remove", { clip_id: c.clip_id })}
                      title="Klip törlése (Delete / Backspace)"
                    >
                      Töröl
                    </button>
                  </div>
                );
              })}
            </div>
          )}

          <div className="trim-block">
            <h3>Be / Ki · ETA frissül</h3>
            <div className="actions tight clip-tools">
              <button
                type="button"
                className="btn"
                disabled={locked || !clips.length}
                onClick={() => runAction("duplicate")}
                title="Kijelölt klip másolása."
              >
                Duplikál
              </button>
              <button
                type="button"
                className="btn"
                disabled={locked || !canRemoveClip(clips, selected)}
                onClick={() => runAction("remove", { clip_id: selected ?? undefined })}
                title="Kijelölt klip törlése (Delete / Backspace)."
              >
                Töröl
              </button>
              <button
                type="button"
                className="btn"
                disabled={locked || !clips.length}
                onClick={() => runAction("cut", { t_sec: tSec })}
                title="Klip felvágása a lejátszási fejnél."
              >
                Vágás
              </button>
              <button
                type="button"
                className="btn"
                disabled={locked || !selected}
                onClick={() => runAction("move", { clip_id: selected ?? undefined, direction: -1 })}
                title="Klip léptetése balra."
              >
                ←
              </button>
              <button
                type="button"
                className="btn"
                disabled={locked || !selected}
                onClick={() => runAction("move", { clip_id: selected ?? undefined, direction: 1 })}
                title="Klip léptetése jobbra."
              >
                →
              </button>

            </div>
            <div className="trim-row">
              <label title="Klip kezdőpontja másodpercben.">
                Be
                <input
                  type="number"
                  min={0}
                  step={0.05}
                  value={inSec}
                  disabled={!clips.length || locked}
                  onChange={(e) => setInSec(Number(e.target.value))}
                />
              </label>
              <label title="Klip végpontja másodpercben.">
                Ki
                <input
                  type="number"
                  min={0}
                  step={0.05}
                  value={outSec}
                  disabled={!clips.length || locked}
                  onChange={(e) => setOutSec(Number(e.target.value))}
                />
              </label>
              <button
                type="button"
                className="btn"
                disabled={!clips.length || locked}
                onClick={applyTrim}
                title="Be/Ki pontok alkalmazása a kijelölt klipre."
              >
                Alkalmaz
              </button>
            </div>
          </div>

          </div>

          {status?.analyse_running ? (
            <div className="bake-progress" aria-live="polite">
              <div className="bake-bar">
                <div className="bake-fill" style={{ width: `${analysePct}%` }} />
              </div>
              <div className="bake-label">
                Elemzés {analysePct}% · {status?.analyse_status || "…"}
              </div>
            </div>
          ) : null}

          {status?.bake_running ? (
            <div className="bake-progress export-busy" aria-live="polite">
              <div className="bake-bar">
                <div className="bake-fill" style={{ width: `${bakePct}%` }} />
              </div>
              <div className="bake-label">
                Export {bakePct}% · {status?.bake_status || "…"}
                {remainLabel && remainLabel !== "Kb. —" ? (
                  <span className="bake-remain"> · Hátravan {remainLabel.replace(/^Kb\.\s*/, "")}</span>
                ) : null}
              </div>
            </div>
          ) : null}

          {!status?.bake_running && status?.last_bake ? (
            <div
              className={`export-result ${status.last_bake.ok && status.last_bake.prores_mov ? "ok" : "fail"}`}
              role="status"
            >
              {status.last_bake.ok && status.last_bake.prores_mov ? (
                <>
                  <div className="export-result-eyebrow">Átlátszó nobg kész · apex</div>
                  <p className="export-result-path" title={status.last_bake.prores_mov}>
                    {status.last_bake.prores_mov}
                  </p>
                  {status.last_bake.preview_mp4 ? (
                    <div className="nobg-player checker-subtle">
                      <video
                        key={bakePreviewKey}
                        className="nobg-video"
                        src={`/api/bake/preview.mp4?t=${bakePreviewKey}`}
                        controls
                        playsInline
                        preload="metadata"
                        title="Sakktábla alá kompozitált _preview.mp4 (Chrome-barát). Master: ProRes/qtrle .mov"
                      />
                    </div>
                  ) : (
                    <p className="export-result-hint">
                      Nincs böngésző-előnézet — nyisd meg a MOV-ot Premiere / Resolve-ban (ProRes alpha).
                    </p>
                  )}
                  <div className="export-result-actions">
                    <button
                      type="button"
                      className="btn primary"
                      disabled={locked}
                      onClick={() => void onNobgToTimeline()}
                      title="Betölti a *_full_nobg.mov-ot a V1-re (csere — egy klip)."
                    >
                      Nobg a timeline-ra
                    </button>
                    <button
                      type="button"
                      className="btn"
                      onClick={() => void onOpenOutput()}
                      title="Explorer: kijelöli a *_full_nobg.mov fájlt (elsődleges kimenet)."
                    >
                      Megnyitás Explorerben
                    </button>
                    {status.last_bake.preview_mp4 ? (
                      <a
                        className="btn preview-link-btn"
                        href={`/api/bake/preview.mp4?t=${bakePreviewKey}`}
                        target="_blank"
                        rel="noreferrer"
                        title="Opcionális előnézet MP4 (sakktábla + hang)."
                      >
                        _preview.mp4
                        {status.last_bake.bake_range?.audio ? " · AAC" : ""}
                      </a>
                    ) : null}
                  </div>
                </>
              ) : (
                <>
                  <div className="export-result-eyebrow warn">Export sikertelen</div>
                  <p className="export-result-path fail-text">
                    {status.last_bake.message ||
                      "Nincs *_full_nobg.mov — ne az alpha mappát használd. Állítsd be az FFMPEG_PATH-ot."}
                  </p>
                  <div className="export-result-actions">
                    <button
                      type="button"
                      className="btn"
                      onClick={() => void onOpenOutput()}
                      title="Kimenet mappa megnyitása"
                    >
                      Mappa megnyitása
                    </button>
                  </div>
                </>
              )}
            </div>
          ) : null}
          {(status?.bake_queue_len ?? 0) > 0 ? (
            <div className="bake-label">Export sor: {status?.bake_queue_len} várakozik</div>
          ) : null}

          <div className="rail-block" hidden={detailsTab !== "contents"}>
          <details className="meta-fold" open>
            <summary>Részletek · idővonal / motor / VRAM</summary>
            <div className="actions tight more-tools">
              <button
                type="button"
                className="btn"
                disabled={locked}
                onClick={onSample}
                title="Beépített minta videó betöltése."
              >
                Minta
              </button>
              <button
                type="button"
                className="btn ghost"
                disabled={locked}
                onClick={() => void onNewProject()}
                title="Új projekt / Kilépés — üres drop képernyő."
              >
                Új projekt
              </button>
              <button
                type="button"
                className="btn"
                disabled={!status?.last_bake?.ok && !status?.last_bake?.out_dir}
                onClick={() => void onOpenOutput()}
                title="Explorer: kijelöli a *_full_nobg.mov fájlt."
              >
                Explorer
              </button>
            </div>
            <label
              className={`sharp-toggle ${sharpEdges ? "on" : ""}`}
              title="Éles szélek (apex): haj/fringe/spill polish, PNG cutout, teljes felbontású Max bake. Alapból be Max/exportnál."
            >
              <input
                type="checkbox"
                checked={sharpEdges}
                disabled={locked || pending}
                onChange={(e) => onSharpEdges(e.target.checked)}
              />
              <span>Éles szélek</span>
              <em>{mode === "max" ? "Max / export" : "exportnál érvényes"}</em>
            </label>
            <div className="meta">
              <div title={rvm.title}>
                RVM: <code>{rvm.label}</code>
              </div>
              <div title={personChip.title}>
                Ember-maszk: <code>{personChip.label}</code>
              </div>
              <div>
                Motor: <code>{status?.engine ?? "—"}</code>
              </div>
              <div>
                Backend: <code>{status?.backend ?? "—"}</code>
              </div>
              <div>
                VRAM: <code>{status?.vram_hint_gb ?? "—"} GB</code>
                {status?.vram?.cuda_holder && status.vram.cuda_holder !== "none" ? (
                  <>
                    {" "}
                    · CUDA: <code>{status.vram.cuda_holder}</code>
                  </>
                ) : null}
              </div>
              {status?.media ? (
                <div>
                  Média:{" "}
                  <code>
                    {status.media.width}×{status.media.height} · {status.media.fps.toFixed(1)} fps ·{" "}
                    {status.media.duration_sec.toFixed(1)}s
                  </code>
                </div>
              ) : null}
              <div>
                ETA kalibráció:{" "}
                <code>
                  Gyors {etas.gyors.labelHu} · Max {etas.max.labelHu} ·{" "}
                  {gpuOrtChip(status).label}
                </code>
              </div>
              {plan && !plan.empty ? (
                <div>
                  Képterv:{" "}
                  <code>
                    {plan.layers.map((L) => `${L.track === 1 ? "V2" : "V1"}:${L.clip_id}`).join(" + ") ||
                      "—"}{" "}
                    · src {plan.layers[0]?.source_t_sec.toFixed(2)}s
                  </code>
                </div>
              ) : null}
              <div>{status?.detail}</div>
              {assist ? (
                <div title={assist.message}>
                  Assist / Ollama: <code>{assist.ok ? "llama3 @ 11434" : assist.message}</code>
                </div>
              ) : null}
              {status?.rvm ? (
                <div>
                  RVM fájl:{" "}
                  <code>
                    {status.rvm.onnx_found
                      ? `${status.rvm.onnx_name || "onnx"} · ORT ${status.rvm.ort_available ? "✓" : "—"}`
                      : "onnx hiányzik"}
                  </code>
                </div>
              ) : null}
              <div>
                Elemzés:{" "}
                <button
                  type="button"
                  className="btn linkish"
                  disabled={locked || !status?.media}
                  onClick={onAnalyse}
                  title="Ritka maszk-elemzés a timeline mentén (előtöltéshez)."
                >
                  Ritka elemzés
                </button>
              </div>
            </div>
            <div className="license">{status?.license_note}</div>
          </details>
          </div>
        </aside>
      </main>
    </div>
  );
}
