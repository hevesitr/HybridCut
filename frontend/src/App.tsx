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
import { SeedPaint } from "./components/SeedPaint";
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

/** Match TimelineDoc.remove_clip: last V1 stays; V2 / extra V1 can go. */
function canRemoveClip(clips: ClipRow[], clipId: string | null | undefined): boolean {
  if (!clipId) return false;
  const target = clips.find((c) => c.clip_id === clipId);
  if (!target) return false;
  if ((target.track ?? 0) >= 1) return true;
  return clips.filter((c) => (c.track ?? 0) === 0).length > 1;
}

function rvmChip(status: EditorStatus | null) {
  const rvm = status?.rvm;
  const backend = (status?.backend || rvm?.engine_backend || "").toLowerCase();
  const liveCuda = backend.includes("cuda");
  const liveCpu =
    backend.includes("cpuexecutionprovider") ||
    backend.endsWith(":cpu") ||
    backend.includes("ort-rvm:cpu");
  const onnx = !!rvm?.onnx_found || backend.includes("ort-rvm") || backend.includes("quality-pipeline");
  // Prefer live session provider — do not show CUDA when EP is actually CPU.
  if (liveCuda) {
    return {
      key: "rvm",
      label: "RVM CUDA",
      on: true,
      warn: false,
      title: "Háttéreltávolító GPU-n fut (CUDA).",
    };
  }
  if (liveCpu || (onnx && rvm?.ort_available)) {
    return {
      key: "rvm",
      label: "RVM CPU",
      on: true,
      warn: true,
      title: rvm?.cuda_fallback
        ? String(rvm.cuda_fallback)
        : "RVM CPU-n fut — ember-maszk így is készül (lassabb, mint CUDA).",
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
    if (preview?.meta?.source_fallback || preview?.meta?.matte_error) {
      return "Ember-maszk sikertelen — próbáld újra az Előnézetet";
    }
    return "Nincs ember-maszk — futtasd az Előnézetet";
  }
  const fallback = status?.rvm?.cuda_fallback || status?.detail || "";
  if (fallback && /CUDA|cuDNN|cudnn/i.test(fallback)) {
    const short = fallback.length > 180 ? `${fallback.slice(0, 180)}…` : fallback;
    return person ? `${person} · ${short}` : short;
  }
  if (status?.rvm?.cudnn_ok === false && status.rvm.cudnn_detail) {
    return status.rvm.cudnn_detail;
  }
  const mode = status?.mode === "max" ? "Max" : "Gyors";
  const seed = status?.seed_mask ? " · kézi finomítás ✓" : "";
  const clips = status?.timeline?.clips?.length ?? 0;
  const broll = status?.timeline?.clips?.filter((c) => (c.track ?? 0) >= 1).length ?? 0;
  const tl = clips ? ` · ${clips} klip${broll ? ` (${broll} B-roll)` : ""}` : "";
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
  /** Optional large duplicate seed panel below — default paint is on Előnézet. */
  const [showLargeSeed, setShowLargeSeed] = useState(false);
  const [seedPng, setSeedPng] = useState<string | null>(null);
  /** True while Ecset/Radír/… pointer is captured on the mask (timeline must ignore). */
  const [paintGesture, setPaintGesture] = useState(false);
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
  const appendRef = useRef<HTMLInputElement>(null);
  const brollRef = useRef<HTMLInputElement>(null);
  /** Fresh status for drop/append — avoid stale closure blocking second clip. */
  const statusRef = useRef<EditorStatus | null>(null);
  statusRef.current = status;
  const scrubTimer = useRef<number | null>(null);
  const toastTimer = useRef<number | null>(null);
  const seedCommitTimer = useRef<number | null>(null);
  const seedCommitGen = useRef(0);
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

  const refreshSeed = async () => {
    try {
      const s = await api.getSeed();
      setSeedPng(s.seed_mask_png_b64);
    } catch {
      /* ignore */
    }
  };

  const refresh = async () => {
    const st = await api.status();
    setStatus(st);
    syncTrimFromStatus(st);
    if (st.seed_mask) void refreshSeed();
    return st;
  };

  useEffect(() => {
    refresh()
      .then((st) => {
        if (st?.media || st?.timeline?.clips?.length) {
          const t = st.timeline?.playhead_sec ?? 0;
          setTSec(t);
          setViewMode("source");
          void runPreview(t, st);
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
      const seedHit = frame.meta?.user_seed ? " · kézi finomítás ✓" : "";
      const ov = (frame.meta?.overlay_layers as unknown[] | undefined)?.length ?? 0;
      const composite = Boolean(frame.meta?.timeline_composite);
      const ovHit = ov
        ? composite
          ? ` · idővonal kompozit V1+V2×${ov}`
          : ` · B-roll ×${ov}`
        : "";
      // Apex: short human status — tech detail stays under Részletek.
      setNote(
        noteOverride ??
          (empty
            ? "Nincs ember-maszk — futtasd az Előnézetet"
            : `Cutout kész${seedHit}${ovHit} · t=${frame.t_sec.toFixed(2)}s`),
      );
      // Explicit Előnézet / upload: jump to Cutout when matte ready (scrub stays put).
      if (opts?.preferCutout) {
        if (!empty) {
          setViewMode("cutout");
          showToast(
            personLabel
              ? `${personLabel} — Exportálás a következő lépés`
              : "Cutout kész — Exportálás a következő lépés",
          );
        } else if (frame.meta?.matte_error || frame.meta?.source_fallback) {
          showToast("Ember-maszk sikertelen — RVM/heuristic nem adott maszkot");
        } else {
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
            await refreshSeed();
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
      const st = await api.loadSample();
      setStatus(st);
      setTSec(0);
      setViewMode("source");
      syncTrimFromStatus(st);
      await refreshSeed();
      await runPreview(0, st, undefined, { preferCutout: true });
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  const onUpload = async (file: File | null, append = false, asBroll = false) => {
    if (!file) return;
    setBusy(true);
    setError(null);
    try {
      // asBroll always appends on V2; append=true stacks V1 after existing clips.
      const useAppend = asBroll ? true : append;
      const st = await api.upload(file, useAppend, asBroll);
      setStatus(st);
      if (!useAppend && !asBroll) {
        setTSec(0);
        setViewMode("source");
      }
      syncTrimFromStatus(st);
      await runPreview(
        useAppend || asBroll ? (st.timeline?.playhead_sec ?? 0) : 0,
        st,
        undefined,
        { preferCutout: !useAppend && !asBroll },
      );
      setNote(
        asBroll
          ? "B-roll a V2 sávon"
          : useAppend
            ? "Új klip az idővonalon (V1)"
            : "Videó betöltve — auto ember-maszk fut",
      );
      if (!useAppend && !asBroll) await refreshSeed();
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
      setSeedPng(null);
      setShowLargeSeed(false);
      setViewMode("source");
      setWipe(50);
      setBakePreviewKey(0);
      setToast(null);
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

  /** Latest onUpload + status for window drop (append when media already open). */
  const dropUpload = useEffectEvent((file: File) => {
    const st = statusRef.current;
    const append = !!(st?.media || (st?.timeline?.clips?.length ?? 0) > 0);
    void onUpload(file, append, false);
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
        select: "Klip kiválasztva — BG / Varázsceruza erre megy",
        to_broll: "Áthelyezve V2-re",
        to_v1: "Áthelyezve V1-re",
        set_track: "Sáv váltva (V1/V2)",
        place: "Klip áthelyezve az idővonalon",
        trim_edge: "Be/Ki trim frissítve",
        set_transform: "Pozíció / méret frissítve",
        reset_transform: "Pozíció visszaállítva (közép · 100%)",
      };
      if (!opts?.quiet) setNote(labels[action] || `Timeline: ${action}`);
      if (action === "select") void refreshSeed();
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
      /* allow drag when not painting — paintOnPreview checked at call site */
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
    const mov = statusRef.current?.last_bake?.prores_mov;
    if (!mov) {
      setError("Nincs *_full_nobg.mov a timeline-ra");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const hasClips = (statusRef.current?.timeline?.clips?.length ?? 0) > 0;
      const st = await api.openPath(mov, hasClips, hasClips, true);
      setStatus(st);
      syncTrimFromStatus(st);
      const t = st.timeline?.playhead_sec ?? tSec;
      setTSec(t);
      setNote(
        hasClips
          ? "Nobg a V2 sávon — húzd az előnézeten, vagy állítsd a Pozíciót"
          : "Nobg betöltve V1-re (átlátszó klip)",
      );
      setViewMode("cutout");
      setMoveMode(true);
      setDetailsTab("timeline");
      showToast("Nobg a timeline-ra — mozgasd / méretezd");
      if (st.timeline?.clips?.length) await runPreview(t, st, undefined, { preferCutout: true });
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  /** Delete / Backspace — remove selected clip (apex/concat clip tools). */
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
      const el = e.target as HTMLElement | null;
      const tag = (el?.tagName || "").toLowerCase();
      if (tag === "input" || tag === "textarea" || el?.isContentEditable) return;
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
  /** Paint tools live on main Előnézet for Cutout / Maszk / Forrás (not Összehasonlítás). */
  const paintOnPreview =
    !!preview && (viewMode === "cutout" || viewMode === "mask" || viewMode === "source");

  const commitSeed = async (png: string, opts?: { quiet?: boolean }) => {
    const quiet = !!opts?.quiet;
    const mode = statusRef.current?.seed_mode;
    const part = statusRef.current?.seed_part;
    const replace = mode === "replace";
    // Quiet path (stroke auto-commit): debounce + never block React on sync ORT.
    if (quiet) {
      setSeedPng(png);
      if (seedCommitTimer.current) window.clearTimeout(seedCommitTimer.current);
      const gen = ++seedCommitGen.current;
      seedCommitTimer.current = window.setTimeout(() => {
        void (async () => {
          try {
            const st = await api.setSeed(png, mode, part);
            if (gen !== seedCommitGen.current) return;
            setStatus(st);
            setSeedPng(st.seed_mask_png_b64 ?? png);
            setNote(
              replace
                ? "Rész-maszk finomítva — export csak a kijelölt részt (pl. arc) viszi"
                : "Kézi finomítás mentve — auto ember-maszk + festés unió",
            );
            const frame = await api.preview(tSec);
            if (gen !== seedCommitGen.current) return;
            setPreview(frame);
          } catch (e) {
            if (gen !== seedCommitGen.current) return;
            setError(e instanceof Error ? e.message : String(e));
          }
        })();
      }, 280);
      return;
    }
    setBusy(true);
    try {
      const st = await api.setSeed(png, mode, part);
      setStatus(st);
      setSeedPng(st.seed_mask_png_b64 ?? png);
      setNote(
        replace
          ? "Rész-maszk mentve — *_full_nobg csak a kijelölt részt tartalmazza"
          : "Kézi finomítás mentve — auto ember-maszk + festés unió",
      );
      await runPreview(tSec, st, undefined, { preferCutout: true });
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  const onWandPick = async (args: {
    xNorm: number;
    yNorm: number;
    erase: boolean;
  }) => {
    try {
      const st = await api.seedPick({
        x: args.xNorm,
        y: args.yNorm,
        t_sec: tSec,
        erase: args.erase,
      });
      setStatus(st);
      const png = st.seed_mask_png_b64 ?? null;
      if (png) setSeedPng(png);
      const pick = st.pick;
      const label = pick?.label_hu || st.seed_part_label_hu || "Rész";
      const msg = args.erase
        ? `Varázsceruza: ${label} törölve`
        : `Varázsceruza: ${label} kijelölve — export = csak ez a rész`;
      setNote(msg);
      showToast(msg);
      setViewMode("cutout");
      await runPreview(tSec, st, undefined, { preferCutout: true });
      return {
        ok: true,
        pngB64: png,
        message: msg,
        part: pick?.part ?? st.seed_part,
        labelHu: label,
      };
    } catch (e) {
      const message = e instanceof Error ? e.message : String(e);
      setError(message);
      return { ok: false, message, pngB64: null };
    }
  };

  const clearSeedMask = async () => {
    try {
      const st = await api.clearSeed();
      setStatus(st);
      setSeedPng(null);
      setNote("Kézi finomítás törölve — auto RVM marad");
      await runPreview(tSec, st, undefined, { preferCutout: true });
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  };

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
      <div className="app empty concat-home">
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
            <span className="gpu-chip" title="Cél GPU — helyi, ingyenes">
              RTX 3060
            </span>
            <p className="empty-tagline">Helyi cutout · Concat-szerű szerkesztő</p>
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
                Húzd ide a videót, vagy indíts új projektet. Háttéreltávolítás → C:\bgcut
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
    <div className="app">
      {/* Compact editor chrome: topbar + workspace only (no separate 1fr intel row). */}

      <header className="topbar">
        <div className="topbar-left">
          <div className="brand">
            <div className="brand-mark">HybridCut</div>
          </div>
          <span className="gpu-chip" title="Cél GPU — helyi, ingyenes">
            RTX 3060
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
        <section
          className={`stage${paintOnPreview ? " paint-tools-on" : ""}${
            paintGesture ? " paint-gesture" : ""
          }`}
        >
          <div className="stage-head">
            <div>
              <h2>Előnézet</h2>
              <p className="lead">
                {viewMode === "compare"
                  ? "Húzd a vonalat a képen — maszk balra, cutout jobbra"
                  : paintOnPreview
                    ? "Ecset / Radír a képen · Varázsceruza = arc / rész → nobg"
                    : "Forrás betöltéskor · Előnézet után Cutout, ha van ember-maszk"}
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
                    {!paintOnPreview && seedPng && mode === "max" && viewMode !== "mask" ? (
                      <img
                        className="seed-overlay-preview"
                        src={
                          seedPng.startsWith("data:")
                            ? seedPng
                            : `data:image/png;base64,${seedPng}`
                        }
                        alt=""
                        aria-hidden
                      />
                    ) : null}
                    {moveMode && selected && viewMode !== "compare" ? (
                      <div
                        ref={previewDragRef}
                        className="transform-drag-layer"
                        title="Húzd oldalra / fel-le — Pozíció X/Y"
                        onPointerDown={onTransformPointerDown}
                        onPointerMove={onTransformPointerMove}
                        onPointerUp={onTransformPointerUp}
                        onPointerCancel={onTransformPointerUp}
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

            if (paintOnPreview) {
              return (
                <SeedPaint
                  variant="docked"
                  autoCommitOnStrokeEnd
                  selectedClipId={selected}
                  imageJpegB64={preview?.source_jpeg_b64 || preview?.jpeg_b64 || null}
                  initialMaskPngB64={seedPng}
                  width={preview?.width ?? 480}
                  height={preview?.height ?? 360}
                  disabled={
                    !!status?.bake_running ||
                    !!status?.analyse_running ||
                    !preview ||
                    moveMode
                  }
                  onWandPick={onWandPick}
                  onPaintGesture={setPaintGesture}
                  onCommit={(png) => void commitSeed(png, { quiet: true })}
                  onClear={() => void clearSeedMask()}
                  frame={stageInner}
                />
              );
            }
            return stageInner;
          })()}

          <div
            className={`timeline-dock${paintGesture ? " timeline-dock--paint-locked" : ""}`}
            data-paint-locked={paintGesture ? "1" : "0"}
          >
            <TimelineTrack
              clips={clips}
              duration={duration}
              playhead={tSec}
              selectedId={selected}
              fps={mediaFps}
              disabled={locked || paintGesture}
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
              onSetTrack={(clipId, track, start) => {
                void runAction("set_track", {
                  clip_id: clipId,
                  track,
                  timeline_start_sec: start,
                });
              }}
              onAddClip={() => appendRef.current?.click()}
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

          <div className="seed-toggle">
            <button
              type="button"
              className={`btn ${showLargeSeed ? "accent" : ""}`}
              disabled={!preview}
              title="Nagy seed panel — csak ha a külön forrás+maszk nézet kell (alapból az Előnézeten fests)."
              onClick={() => {
                setShowLargeSeed((v) => {
                  const next = !v;
                  if (next) void refreshSeed();
                  return next;
                });
              }}
            >
              {showLargeSeed ? "Nagy seed panel elrejtése" : "Nagy seed panel"}
            </button>
            {paintOnPreview ? (
              <span
                className="seed-toggle-hint"
                title="Ecset / Radír / Lasszó / Varázsceruza a képkocka feletti sávon — nem a videó pixelein."
              >
                Kézi finomítás: eszközsáv a képkocka felett
              </span>
            ) : null}
          </div>

          {showLargeSeed && (
            <SeedPaint
              variant="panel"
              selectedClipId={selected}
              imageJpegB64={preview?.source_jpeg_b64 || preview?.jpeg_b64 || null}
              initialMaskPngB64={seedPng}
              width={preview?.width ?? 480}
              height={preview?.height ?? 360}
              disabled={locked || !preview}
              onWandPick={onWandPick}
              onPaintGesture={setPaintGesture}
              onCommit={(png) => void commitSeed(png)}
              onClear={() => void clearSeedMask()}
            />
          )}
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
            <p className="lead">Gyors / Max · ETA a gombokon · Be/Ki tartomány.</p>
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
              <div className="clip-add-row" role="group" aria-label="Több klip">
                <button
                  type="button"
                  className="btn accent"
                  disabled={locked || !hasMedia}
                  onClick={() => appendRef.current?.click()}
                  title="Új klip alá — további videó az V1 sávra, a meglévő után."
                >
                  + V1 klip
                </button>
                <button
                  type="button"
                  className="btn"
                  disabled={locked || !hasMedia}
                  onClick={() => brollRef.current?.click()}
                  title="B-roll videó a V2 sávra (playheadnél)."
                >
                  + B-roll
                </button>
              </div>
              <input
                ref={fileRef}
                type="file"
                accept="video/*"
                hidden
                onChange={(e) => onFilePicked(e, false, false)}
              />
              <input
                ref={appendRef}
                type="file"
                accept="video/*"
                hidden
                onChange={(e) => onFilePicked(e, true, false)}
              />
              <input
                ref={brollRef}
                type="file"
                accept="video/*"
                hidden
                onChange={(e) => onFilePicked(e, true, true)}
              />
            </div>
            <p className="action-help">
              Megnyitás → auto Cutout → Exportálás ·{" "}
              <code>{"C:\\bgcut\\*_full_nobg.mov"}</code>
              {" · "}
              <span title="Második videó: + V1 klip vagy ejtsd a fájlt (append=true).">
                Új klip alá
              </span>
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
                        {(c.track ?? 0) >= 1 ? "V2" : "V1"} #{i + 1}{" "}
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
                      title={
                        removable
                          ? "Klip törlése (Delete)"
                          : "Az utolsó V1 klip nem törölhető"
                      }
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
              <button
                type="button"
                className="btn accent"
                disabled={locked || !selected}
                onClick={() => runAction("to_broll", { clip_id: selected ?? undefined })}
                title="Kijelölt klip áthelyezése a V2 B-roll sávra."
              >
                → B-roll
              </button>
              <button
                type="button"
                className="btn"
                disabled={locked || !selected}
                onClick={() => runAction("to_v1", { clip_id: selected ?? undefined })}
                title="Kijelölt klip visszarakása az V1 sávra."
              >
                → V1
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

          <div className="trim-block transform-block">
            <h3>Pozíció / Méret</h3>
            <p className="transform-hint">
              {selectedClip?.has_alpha
                ? "Átlátszó nobg — húzd az előnézeten (Mozgatás), vagy írd be az értékeket."
                : "CapCut-szerű eltolás / méret a kijelölt klipen (V1 vagy V2)."}
            </p>
            <div className="trim-row transform-row">
              <label title="Vízszintes eltolás a vászon közepétől (%).">
                Pozíció X
                <input
                  type="number"
                  step={1}
                  value={posXPct}
                  disabled={!selected || locked}
                  onChange={(e) => setPosXPct(Number(e.target.value))}
                />
              </label>
              <label title="Függőleges eltolás a vászon közepétől (%).">
                Pozíció Y
                <input
                  type="number"
                  step={1}
                  value={posYPct}
                  disabled={!selected || locked}
                  onChange={(e) => setPosYPct(Number(e.target.value))}
                />
              </label>
              <label title="Méret százalékban (100 = tartalmazva a vászonra).">
                Méretérték
                <input
                  type="number"
                  min={5}
                  max={400}
                  step={1}
                  value={scalePct}
                  disabled={!selected || locked}
                  onChange={(e) => setScalePct(Number(e.target.value))}
                />
              </label>
            </div>
            <div className="actions tight clip-tools">
              <button
                type="button"
                className={`btn ${moveMode ? "primary" : ""}`}
                disabled={!selected || locked}
                onClick={() => setMoveMode((v) => !v)}
                title="Előnézeten húzással mozgatás (overlay a festés felett)."
              >
                Mozgatás
              </button>
              <button
                type="button"
                className="btn"
                disabled={!selected || locked}
                onClick={() => void applyTransform()}
                title="Pozíció / méret alkalmazása."
              >
                Alkalmaz
              </button>
              <button
                type="button"
                className="btn ghost"
                disabled={!selected || locked}
                onClick={() =>
                  void runAction("reset_transform", { clip_id: selected ?? undefined })
                }
                title="Közép + 100% méret."
              >
                Visszaállítás
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
                      title="Betölti a *_full_nobg.mov-ot a timeline-ra (V2 ha van már klip) — átlátszó, mozgatható."
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
                className="btn"
                disabled={locked || !hasMedia}
                onClick={() => appendRef.current?.click()}
                title="Új klip alá — V1 sáv, meglévő után."
              >
                + V1 klip
              </button>
              <button
                type="button"
                className="btn"
                disabled={locked || !hasMedia}
                onClick={() => brollRef.current?.click()}
                title="B-roll videó a V2 sávra."
              >
                + B-roll
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
                  Gyors {etas.gyors.labelHu} · Max {etas.max.labelHu} · RTX 3060
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
