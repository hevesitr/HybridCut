import { useEffect, useEffectEvent, useRef, useState, useTransition, type PointerEvent as ReactPointerEvent } from "react";
import { ModeSwitcher } from "./components/ModeSwitcher";
import { SeedPaint } from "./components/SeedPaint";
import { TimelineTrack } from "./components/TimelineTrack";
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
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [note, setNote] = useState("Nyiss meg egy videót, vagy tölts be mintát.");
  /** Optional large duplicate seed panel below — default paint is on Előnézet. */
  const [showLargeSeed, setShowLargeSeed] = useState(false);
  const [seedPng, setSeedPng] = useState<string | null>(null);
  /** Alapnézet: teljes forrás RGB — Előnézet után Cutout, ha van ember-maszk. */
  const [viewMode, setViewMode] = useState<ViewMode>("source");
  const [wipe, setWipe] = useState(50);
  const [dragOver, setDragOver] = useState(false);
  const [assist, setAssist] = useState<AssistStatus | null>(null);
  const [toast, setToast] = useState<string | null>(null);
  /** Cache-bust in-app checker preview after each bake. */
  const [bakePreviewKey, setBakePreviewKey] = useState(0);
  const [pending, startTransition] = useTransition();
  const fileRef = useRef<HTMLInputElement>(null);
  const appendRef = useRef<HTMLInputElement>(null);
  const brollRef = useRef<HTMLInputElement>(null);
  const scrubTimer = useRef<number | null>(null);
  const toastTimer = useRef<number | null>(null);
  const seedCommitTimer = useRef<number | null>(null);
  const seedCommitGen = useRef(0);
  const wipeStageRef = useRef<HTMLDivElement>(null);
  const wipeDragging = useRef(false);

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
      .catch((e: Error) => setError(e.message));
    api.assistStatus().then(setAssist).catch(() => setAssist(null));
  }, []);

  useEffect(() => {
    let dragDepth = 0;
    const onDragEnter = (e: DragEvent) => {
      if (!e.dataTransfer?.types?.includes("Files")) return;
      e.preventDefault();
      dragDepth += 1;
      // Empty hero only — never cover a loaded timeline with „Ejtés: klip…”.
      if (!(status?.media || (status?.timeline?.clips?.length ?? 0) > 0)) {
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
        const append = !!(status?.timeline?.clips?.length);
        void onUpload(file, append, false);
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
  }, [status?.timeline?.clips?.length, status?.media]);

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
      const ovHit = ov ? ` · B-roll ×${ov}` : "";
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
      const st = await api.upload(file, append, asBroll);
      setStatus(st);
      if (!append && !asBroll) {
        setTSec(0);
        setViewMode("source");
      }
      syncTrimFromStatus(st);
      await runPreview(
        append || asBroll ? (st.timeline?.playhead_sec ?? 0) : 0,
        st,
        undefined,
        { preferCutout: !append && !asBroll },
      );
      setNote(
        asBroll
          ? "B-roll a V2 sávon"
          : append
            ? "Klip hozzáadva (V1)"
            : "Videó betöltve — auto ember-maszk fut",
      );
      if (!append && !asBroll) await refreshSeed();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

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
    action: "duplicate" | "remove" | "cut" | "move" | "select" | "to_broll" | "to_v1",
    extra?: { clip_id?: string; direction?: number; t_sec?: number },
  ) => {
    setBusy(true);
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
        select: "Klip kiválasztva",
        to_broll: "Áthelyezve B-rollra",
        to_v1: "Áthelyezve V1-re",
      };
      setNote(labels[action] || `Timeline: ${action}`);
      if (st.timeline?.clips?.length) await runPreview(t, st);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

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
  const locked = busy || !!status?.bake_running || !!status?.analyse_running;
  const hasMedia = !!status?.media || clips.length > 0;
  const mediaW = status?.media?.width ?? 1920;
  const mediaH = status?.media?.height ?? 1080;
  const mediaFps = status?.timeline?.fps || status?.media?.fps || 25;
  const bakeSpanSec = clipDurationSec(inSec, outSec, duration);
  const etas = bothModeEtas(bakeSpanSec, mediaFps, mediaW, mediaH);
  const selectedEta = etas[mode]?.labelHu ?? "Kb. —";
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
    // Quiet path (stroke auto-commit): debounce + never block React on sync ORT.
    if (quiet) {
      setSeedPng(png);
      if (seedCommitTimer.current) window.clearTimeout(seedCommitTimer.current);
      const gen = ++seedCommitGen.current;
      seedCommitTimer.current = window.setTimeout(() => {
        void (async () => {
          try {
            const st = await api.setSeed(png);
            if (gen !== seedCommitGen.current) return;
            setStatus(st);
            setSeedPng(st.seed_mask_png_b64 ?? png);
            setNote("Kézi finomítás mentve — auto ember-maszk + festés unió");
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
      const st = await api.setSeed(png);
      setStatus(st);
      setSeedPng(st.seed_mask_png_b64 ?? png);
      setNote("Kézi finomítás mentve — auto ember-maszk + festés unió");
      await runPreview(tSec, st, undefined, { preferCutout: true });
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
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
      <div className="app empty">
        {dragOver ? (
          <div className="drop-overlay">
            <strong>Ejtés: videó betöltése</strong>
          </div>
        ) : null}
        <section className="hero">
          <div className="hero-inner">
            <div className="brand-mark">HybridCut</div>
            <p className="hero-tag">Egy kattintás a helyi cutoutra.</p>
            <p className="hero-sub">
              Megnyitás → auto Cutout → Exportálás. Lime · orange · RTX 3060 · csak helyi.
            </p>
            <div className="hero-cta">
              <button
                type="button"
                className="btn accent hero-cta-primary"
                disabled={locked}
                onClick={() => fileRef.current?.click()}
                title="Videó megnyitása — automatikus Cutout előnézet."
              >
                Megnyitás
              </button>
              <button
                type="button"
                className="btn primary"
                disabled={locked}
                onClick={onSample}
                title="Beépített minta videó betöltése a kipróbáláshoz."
              >
                Minta
              </button>
            </div>
            <ModeSwitcher
              mode={mode}
              disabled={locked || pending}
              onChange={onMode}
              etaGyors={etas.gyors.labelHu}
              etaMax={etas.max.labelHu}
            />
            <div className="hero-meta">
              {status?.sync_version ?? "…"} · Videoeditor · Róbert Hevesi-Tóth
            </div>
            {error ? <div className="status-line error">{error}</div> : null}
          </div>
        </section>
        <input
          ref={fileRef}
          type="file"
          accept="video/*"
          hidden
          onChange={(e) => onUpload(e.target.files?.[0] ?? null, false, false)}
        />
      </div>
    );
  }

  return (
    <div className="app">
      {/* Drop overlay only on empty hero — never when timeline has media. */}

      <header className="topbar">
        <div className="brand">
          <div className="brand-mark">HybridCut</div>
          <div className="brand-sub">lime · orange · helyi cutout</div>
        </div>
        <div className="sync">
          <div className="sync-stamp">{status?.sync_version ?? "…"}</div>
          <div>RTX 3060 · helyi</div>
        </div>
      </header>

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

      <main className="workspace">
        <aside className="rail">
          <div className="rail-block">
            <ol className="flow-steps" aria-label="Egy kattintásos folyamat">
              <li className={flowStep >= 1 ? "done" : ""} data-step="1">
                Megnyitás
              </li>
              <li className={flowStep >= 2 ? "done" : flowStep === 1 ? "next" : ""} data-step="2">
                Cutout
              </li>
              <li className={flowStep >= 3 ? "done" : flowStep === 2 ? "next" : ""} data-step="3">
                Exportálás
              </li>
            </ol>
            <h2>Cutout</h2>
            <p className="lead">
              1 Megnyitás → 2 Előnézet/Cutout → 3 Export. Válaszd a módot — az ETA élőben frissül.
            </p>
            <ModeSwitcher
              mode={mode}
              disabled={locked || pending}
              onChange={onMode}
              etaGyors={etas.gyors.labelHu}
              etaMax={etas.max.labelHu}
            />
            <div className="eta-pair" aria-live="polite">
              <div className={`eta-card ${mode === "gyors" ? "active" : ""}`}>
                <span className="eta-card-mode">Gyors háttéreltávolítás</span>
                <strong>{etas.gyors.labelHu}</strong>
              </div>
              <div className={`eta-card ${mode === "max" ? "active" : ""}`}>
                <span className="eta-card-mode">Max háttéreltávolítás</span>
                <strong>{etas.max.labelHu}</strong>
              </div>
            </div>
            <p className="export-eta" title="Becsült bake idő a jelenlegi Be/Ki és felbontás alapján (RTX 3060).">
              Export előtt · {mode === "max" ? "Max" : "Gyors"}: <strong>{selectedEta}</strong>
              {bakeSpanSec > 0 ? (
                <span>
                  {" "}
                  · {bakeSpanSec.toFixed(1)}s klip · {mediaW}×{mediaH} · {mediaFps.toFixed(0)} fps
                </span>
              ) : null}
            </p>
            <div className="actions export-actions primary-flow">
              <button
                type="button"
                className="btn accent"
                disabled={locked}
                onClick={() => fileRef.current?.click()}
                title="Videó betöltése — automatikus Cutout előnézet."
              >
                1 · Megnyitás
              </button>
              <button
                type="button"
                className={`btn ${flowStep === 1 ? "accent pulse-cta" : ""}`}
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
                onChange={(e) => onUpload(e.target.files?.[0] ?? null, false, false)}
              />
              <input
                ref={appendRef}
                type="file"
                accept="video/*"
                hidden
                onChange={(e) => onUpload(e.target.files?.[0] ?? null, true, false)}
              />
              <input
                ref={brollRef}
                type="file"
                accept="video/*"
                hidden
                onChange={(e) => onUpload(e.target.files?.[0] ?? null, true, true)}
              />
            </div>
            <p className="action-help">
              Megnyitás → auto Cutout → Exportálás · master:{" "}
              <code>{"C:\\bgcut\\{stem}_full_nobg.mov"}</code>
            </p>
          </div>

          {clips.length > 0 && (
            <div className="clip-bin">
              <h3>Klip lista ({clips.length})</h3>
              {clips.map((c, i) => (
                <button
                  key={c.clip_id}
                  type="button"
                  className={`clip-bin-item ${c.clip_id === selected ? "active" : ""}`}
                  disabled={locked}
                  onClick={() => void runAction("select", { clip_id: c.clip_id })}
                  title="Klip kiválasztása az idővonalon."
                >
                  <span>
                    {(c.track ?? 0) >= 1 ? "V2" : "V1"} #{i + 1} {c.display_label || c.clip_id}
                  </span>
                  <span>{(c.source_duration_sec ?? c.out_sec - c.in_sec).toFixed(1)}s</span>
                </button>
              ))}
            </div>
          )}

          <div className="trim-block">
            <h3>Be / Ki · ETA frissül</h3>
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

          <details className="meta-fold">
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
                disabled={locked}
                onClick={() => appendRef.current?.click()}
                title="További klip hozzáadása az V1 sávhoz."
              >
                + V1
              </button>
              <button
                type="button"
                className="btn"
                disabled={locked}
                onClick={() => brollRef.current?.click()}
                title="B-roll videó hozzáadása a V2 sávhoz."
              >
                + B-roll
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
                disabled={locked || clips.length < 2}
                onClick={() => runAction("remove")}
                title="Kijelölt klip törlése."
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
        </aside>

        <section className="stage">
          <div className="stage-head">
            <div>
              <h2>Előnézet</h2>
              <p className="lead">
                {viewMode === "compare"
                  ? "Húzd a vonalat a képen — maszk balra, cutout jobbra"
                  : paintOnPreview
                    ? "Ecset / Radír / Lasszó / Varázsceruza a képkocka felett · festés a képen"
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
                className={`preview-stage ${viewMode === "source" || matteEmpty ? "source-solid" : "checker-subtle"}`}
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
                  </div>
                ) : (
                  <div className="preview-empty">
                    <h3>Scrub az idővonalon</h3>
                    <p>
                      Előtöltés + MaszkTár adja az élő érzést. A kézi maszk scrub után is megmarad.
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
                  imageJpegB64={preview?.source_jpeg_b64 || preview?.jpeg_b64 || null}
                  initialMaskPngB64={seedPng}
                  width={preview?.width ?? 480}
                  height={preview?.height ?? 360}
                  disabled={!!status?.bake_running || !!status?.analyse_running || !preview}
                  onCommit={(png) => void commitSeed(png, { quiet: true })}
                  onClear={() => void clearSeedMask()}
                  frame={stageInner}
                />
              );
            }
            return stageInner;
          })()}

          {clips.length > 0 && (
            <TimelineTrack
              clips={clips}
              duration={duration}
              playhead={tSec}
              selectedId={selected}
              disabled={locked}
              onSeek={schedulePreview}
              onSelect={(id) => {
                void runAction("select", { clip_id: id });
              }}
            />
          )}

          <div>
            <div className="scrub">
              <span>0s</span>
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
              <span>{duration.toFixed(1)}s</span>
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
              imageJpegB64={preview?.source_jpeg_b64 || preview?.jpeg_b64 || null}
              initialMaskPngB64={seedPng}
              width={preview?.width ?? 480}
              height={preview?.height ?? 360}
              disabled={locked || !preview}
              onCommit={(png) => void commitSeed(png)}
              onClear={() => void clearSeedMask()}
            />
          )}
        </section>
      </main>
    </div>
  );
}
