import { useEffect, useEffectEvent, useRef, useState, useTransition } from "react";
import { ModeSwitcher } from "./components/ModeSwitcher";
import { SeedPaint } from "./components/SeedPaint";
import { TimelineTrack } from "./components/TimelineTrack";
import { api, type AssistStatus, type EditorStatus, type PreviewResult } from "./lib/api";

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
    return {
      key: "person",
      label: label || (active ? "MatAnyone2 aktív" : "MatAnyone2 nincs — RVM ember-maszk"),
      on: true,
      warn: !active,
      title: active
        ? "MatAnyone2 helyi súlyokkal fut."
        : "Nincs MatAnyone2 súly — Max mód RVM minőségi pipeline-nal ad ember-maszkot.",
    };
  }
  return {
    key: "person",
    label: label || "Gyors RVM ember-maszk",
    on: true,
    warn: false,
    title: "Gyors mód: automatikus RVM ember-maszk (kézi maszk nem kötelező).",
  };
}

function intelFromPreview(preview: PreviewResult | null, status: EditorStatus | null) {
  const meta = preview?.meta ?? {};
  const lanes = meta.proxy_lanes as { stats?: { hot_hits?: number; warm_hits?: number } } | undefined;
  const hot = lanes?.stats?.hot_hits ?? 0;
  const overlays = (meta.overlay_layers as unknown[] | undefined)?.length ?? 0;
  const audio = !!status?.last_bake?.bake_range?.audio || !!status?.intelligence?.export_audio;
  const q = status?.bake_queue_len ?? 0;
  return [
    {
      key: "mode",
      label: status?.mode === "max" ? "Max minőség" : "Gyors mód",
      on: true,
      warn: status?.mode === "max",
      title:
        status?.mode === "max"
          ? "Max: auto RVM ember-maszk + opcionális kézi finomítás / minőségi export."
          : "Gyors: élő előnézet scrub közben (auto RVM).",
    },
    rvmChip(status),
    personMatteChip(status, preview),
    {
      key: "mask",
      label: meta.mask_store ? "MaszkTár talált" : "MaszkTár",
      on: !!meta.mask_store,
      title: "Előre számolt maszkok tárolója — gyorsítja a scrubot.",
    },
    {
      key: "prefetch",
      label: `Előtöltés ×${meta.prefetch_ahead ?? 8}`,
      on: true,
      title: "Következő képkockák előre betöltése sima scrubhoz.",
    },
    {
      key: "proxy",
      label: hot > 0 ? `Proxy HOT ${hot}` : "Proxy sávok",
      on: hot > 0,
      title: "Kis felbontású gyorsítótár az élő előnézethez.",
    },
    {
      key: "seed",
      label: status?.seed_mask || meta.user_seed ? "Kézi finomítás ✓" : "Kézi finomítás",
      on: !!status?.seed_mask || !!meta.user_seed,
      warn: false,
      title: "Opcionális kézi maszk — csak finomítás; az ember-maszk automatikus.",
    },
    {
      key: "broll",
      label: overlays > 0 ? `B-roll ×${overlays}` : status?.intelligence?.broll_track ? "B-roll" : "V1",
      on: overlays > 0 || !!status?.intelligence?.broll_track,
      title: "Második videosáv (B-roll) állapota.",
    },
    {
      key: "audio",
      label: audio ? "Hang AAC" : "Hang",
      on: audio,
      title: "Export hangcsatorna (AAC) állapota.",
    },
    {
      key: "queue",
      label: q > 0 ? `Export sor ${q}` : "Export sor",
      on: q > 0 || !!status?.bake_running,
      title: "Várakozó vagy futó export (bake) feladatok.",
    },
    {
      key: "analyse",
      label:
        (status?.analyse_masks ?? 0) > 0
          ? `Elemzés ${status?.analyse_masks}`
          : status?.analyse_running
            ? "Elemzés…"
            : "Elemzés",
      on: (status?.analyse_masks ?? 0) > 0 || !!status?.analyse_running,
      title: "Ritka maszk-elemzés a timeline mentén.",
    },
  ];
}

function smartStatusLine(
  status: EditorStatus | null,
  note: string,
  busy: boolean,
  error: string | null,
  matteEmpty: boolean,
): string {
  if (error) return error;
  if (status?.bake_running) return status.bake_status || "Export fut…";
  if (status?.analyse_running) return status.analyse_status || "Elemzés fut…";
  if (busy) return "Dolgozom…";
  if (matteEmpty) return "Nincs ember-maszk — futtasd az Előnézetet";
  const person =
    status?.person_matte_label_hu ||
    status?.person_matte?.person_matte_label_hu ||
    "";
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
  const [showSeed, setShowSeed] = useState(false);
  const [seedPng, setSeedPng] = useState<string | null>(null);
  /** Alapnézet: teljes forrás RGB — Előnézet után Cutout, ha van ember-maszk. */
  const [viewMode, setViewMode] = useState<ViewMode>("source");
  const [wipe, setWipe] = useState(100);
  const [dragOver, setDragOver] = useState(false);
  const [assist, setAssist] = useState<AssistStatus | null>(null);
  const [toast, setToast] = useState<string | null>(null);
  const [pending, startTransition] = useTransition();
  const fileRef = useRef<HTMLInputElement>(null);
  const appendRef = useRef<HTMLInputElement>(null);
  const brollRef = useRef<HTMLInputElement>(null);
  const scrubTimer = useRef<number | null>(null);
  const toastTimer = useRef<number | null>(null);

  const showToast = (msg: string) => {
    setToast(msg);
    if (toastTimer.current) window.clearTimeout(toastTimer.current);
    toastTimer.current = window.setTimeout(() => setToast(null), 4200);
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
    const onDragOver = (e: DragEvent) => {
      if (!e.dataTransfer?.types?.includes("Files")) return;
      e.preventDefault();
      setDragOver(true);
    };
    const onDragLeave = (e: DragEvent) => {
      if (e.relatedTarget == null) setDragOver(false);
    };
    const onDrop = (e: DragEvent) => {
      e.preventDefault();
      setDragOver(false);
      const file = e.dataTransfer?.files?.[0];
      if (file && file.type.startsWith("video/")) {
        const append = !!(status?.timeline?.clips?.length);
        void onUpload(file, append, false);
      }
    };
    window.addEventListener("dragover", onDragOver);
    window.addEventListener("dragleave", onDragLeave);
    window.addEventListener("drop", onDrop);
    return () => {
      window.removeEventListener("dragover", onDragOver);
      window.removeEventListener("dragleave", onDragLeave);
      window.removeEventListener("drop", onDrop);
    };
  }, [status?.timeline?.clips?.length]);

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
      if (p.bake_status) setNote(p.bake_status);
      if (!p.bake_running && p.last_bake?.ok) {
        const st = await refresh();
        setNote(p.last_bake.message || "Export kész · hang a preview.mp4-ben");
        if (st.media) await runPreview(tSec, st, p.last_bake.message);
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
      const storeHit = frame.meta?.mask_store ? " · MaszkTár" : "";
      const seedHit = frame.meta?.user_seed ? " · kézi finomítás ✓" : "";
      const emptyHit = empty ? " · Nincs ember-maszk" : "";
      const personHit = personLabel ? ` · ${personLabel}` : "";
      const failHit = frame.meta?.source_fallback ? " · RVM soft-fail" : "";
      const ov = (frame.meta?.overlay_layers as unknown[] | undefined)?.length ?? 0;
      const ovHit = ov ? ` · B-roll ×${ov}` : "";
      const lanes = frame.meta?.proxy_lanes as { stats?: { hot_hits?: number } } | undefined;
      const laneHit = lanes?.stats?.hot_hits ? ` · HOT ${lanes.stats.hot_hits}` : "";
      setNote(
        noteOverride ??
          `${frame.engine} · ${frame.backend}${personHit}${storeHit}${seedHit}${emptyHit}${failHit}${ovHit}${laneHit} · t=${frame.t_sec.toFixed(2)}s`,
      );
      // Explicit Előnézet / upload: jump to Cutout when matte ready (scrub stays put).
      if (opts?.preferCutout) {
        if (!empty) {
          setViewMode("cutout");
          showToast(personLabel || "Ember-maszk kész — Cutout nézet");
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
      api
        .setMode(mode)
        .then(async (st) => {
          setStatus(st);
          setNote(
            mode === "gyors"
              ? "Gyors mód: auto RVM ember-maszk · élő scrub"
              : "Max: auto RVM ember-maszk (MatAnyone2 opcionális) · kézi csak finomítás",
          );
          if (mode === "max") {
            // Seed panel available but not required — auto person first.
            await refreshSeed();
          }
          if (st.media) await runPreview(tSec, st, undefined, { preferCutout: true });
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
      const res = await api.bake(48, true, true, `bake-${Date.now().toString(36)}`);
      setStatus(res.status);
      setNote(
        res.queued
          ? res.message || "Export sorba téve"
          : res.message || "Export fut… (hang AAC)",
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
      const res = await api.openOutputFolder(status?.last_bake?.out_dir ?? undefined);
      setNote(
        res.opened
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
  const mode = status?.mode ?? "gyors";
  const bakePct = Math.round((status?.bake_progress ?? 0) * 100);
  const analysePct = Math.round((status?.analyse_progress ?? 0) * 100);
  const plan = status?.frame_plan;
  const clips = status?.timeline?.clips ?? [];
  const selected = status?.timeline?.selected_clip_id ?? null;
  const locked = busy || !!status?.bake_running || !!status?.analyse_running;
  const hasMedia = !!status?.media || clips.length > 0;
  const chips = intelFromPreview(preview, status);
  const matteEmpty = Boolean(preview?.meta?.matte_empty || preview?.meta?.source_fallback);
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
    viewMode === "mask" && !matteEmpty ? "image/png" : "image/jpeg";
  const beforeSrc = matteEmpty ? sourceSrc : preview?.alpha_png_b64;
  const beforeMime = matteEmpty ? "image/jpeg" : "image/png";
  const afterSrc = matteEmpty ? sourceSrc : preview?.jpeg_b64;
  const statusText = smartStatusLine(status, note, busy, error, matteEmpty);

  const rvm = rvmChip(status);
  const rvmDetail = status?.rvm;

  const viewButtons: { id: ViewMode; label: string; title: string }[] = [
    { id: "source", label: "Forrás", title: "Eredeti videókép — teljes RGB, sakktábla nélkül." },
    { id: "mask", label: "Maszk", title: "Alpha / matte nézet — hol vág a háttéreltávolítás." },
    { id: "cutout", label: "Cutout", title: "Kivágott alany sakktábla felett (ha van maszk)." },
    {
      id: "compare",
      label: "Összehasonlítás",
      title: "Csúsztatható összehasonlítás: maszk ↔ cutout (alapból teljesen Utána).",
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
            <p className="hero-tag">Helyi cutout szerkesztő — tölts be videót, nézd meg, exportálj.</p>
            <p className="hero-sub">
              1) Videó betöltése · 2) Előnézet · 3) Exportálás — RTX 3060 · csak helyi / ingyenes.
            </p>
            <div className="hero-cta">
              <button
                type="button"
                className="btn primary"
                disabled={locked}
                onClick={onSample}
                title="Beépített minta videó betöltése a kipróbáláshoz."
              >
                Minta videó
              </button>
              <button
                type="button"
                className="btn accent"
                disabled={locked}
                onClick={() => fileRef.current?.click()}
                title="Videófájl megnyitása a gépről."
              >
                Videó betöltése
              </button>
            </div>
            <ModeSwitcher mode={mode} disabled={locked || pending} onChange={onMode} />
            <div className="hero-chips" aria-label="Futás állapot">
              <span
                className={`intel-chip ${rvm.on ? "on" : ""} ${rvm.warn ? "warn" : ""}`}
                title={rvm.title}
              >
                {rvm.label}
              </span>
              <span
                className={`intel-chip ${rvmDetail?.onnx_found ? "on" : ""}`}
                title="RVM ONNX modell elérhetősége."
              >
                {rvmDetail?.onnx_found
                  ? `ONNX ${rvmDetail.onnx_name || "✓"}`
                  : "ONNX hiányzik"}
              </span>
              <span
                className={`intel-chip ${rvmDetail?.ort_available ? "on" : ""}`}
                title="ONNX Runtime telepítve van-e."
              >
                {rvmDetail?.ort_available ? "ORT ✓" : "ORT —"}
              </span>
              <span
                className={`intel-chip ${assist?.ok ? "on" : ""}`}
                title="Helyi Ollama asszisztens (llama3)."
              >
                {assist?.ok ? "Ollama ✓" : "Ollama —"}
              </span>
            </div>
            <p className="hero-hint">
              {rvmDetail?.onnx_found
                ? `RVM: ${rvmDetail.source === "parent_videoeditor" ? "szülő Videoeditor models" : rvmDetail.source || "felismerve"}`
                : "Ha a CapCut Videoeditor models\\ mappában van rvm_*.onnx, a Gyors motor automatikusan felismeri."}
              {" · "}Húzd ide a videófájlt, vagy kattints a gombra.
            </p>
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
      {dragOver ? (
        <div className="drop-overlay">
          <strong>Ejtés: klip a timeline-ra</strong>
        </div>
      ) : null}

      <header className="topbar">
        <div className="brand">
          <div className="brand-mark">HybridCut</div>
          <div className="brand-sub">Videoeditor · Róbert Hevesi-Tóth</div>
        </div>
        <div className="sync">
          <div>{status?.sync_version ?? "…"}</div>
          <div>RTX 3060 · helyi / ingyenes</div>
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
        {assist ? (
          <span
            className={`intel-chip ${assist.ok ? "on" : ""}`}
            title={assist.message || "Helyi Ollama asszisztens állapota."}
          >
            {assist.ok ? "Ollama ✓" : "Ollama —"}
          </span>
        ) : null}
      </div>

      <main className="workspace">
        <aside className="rail">
          <div className="rail-block">
            <h2>Matting motor</h2>
            <p className="lead">
              <strong>Gyors</strong> = auto RVM · <strong>Max</strong> = RVM minőség (+ opcionális MatAnyone2)
            </p>
            <ModeSwitcher mode={mode} disabled={locked || pending} onChange={onMode} />
            <div className="actions">
              <button
                type="button"
                className="btn primary"
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
                onClick={() => fileRef.current?.click()}
                title="Videó betöltése a gépről (új projekt)."
              >
                Megnyitás
              </button>
              <button
                type="button"
                className="btn"
                disabled={locked}
                onClick={() => appendRef.current?.click()}
                title="További klip hozzáadása az V1 sávhoz."
              >
                + V1 klip
              </button>
              <button
                type="button"
                className="btn accent"
                disabled={locked}
                onClick={() => brollRef.current?.click()}
                title="B-roll videó hozzáadása a V2 sávhoz."
              >
                + B-roll
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
              <button
                type="button"
                className="btn"
                disabled={locked || !status?.media}
                onClick={() => void runPreview(tSec, undefined, undefined, { preferCutout: true })}
                title="Auto ember-maszk futtatása (RVM) — Cutout nézetre vált, ha kész."
              >
                Előnézet
              </button>
              <button
                type="button"
                className="btn"
                disabled={locked || !status?.media}
                onClick={onAnalyse}
                title="Ritka maszk-elemzés a timeline mentén (előtöltéshez)."
              >
                Elemzés
              </button>
              <button
                type="button"
                className={`btn ${mode === "max" ? "accent" : "primary"}`}
                disabled={(!status?.media && !clips.length) || !!status?.analyse_running}
                onClick={onBake}
                title="Exportálás hanggal — ha fut egy export, a következő a sorba kerül."
              >
                {status?.bake_running ? "Export sorba +" : "Exportálás hanggal"}
              </button>
              <button
                type="button"
                className="btn"
                disabled={!status?.last_bake?.ok && !status?.last_bake?.out_dir}
                onClick={() => void onOpenOutput()}
                title="Utolsó export kimeneti mappájának megnyitása."
              >
                Kimenet mappa
              </button>
            </div>
            <p className="action-help">1) Videó betöltése 2) Előnézet 3) Exportálás</p>
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
            <h3>Idővonal</h3>
            <div className="actions tight">
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
                Vágás alkalmaz
              </button>
            </div>
          </div>

          {(status?.analyse_running || (status?.analyse_progress ?? 0) > 0) && (
            <div className="bake-progress">
              <div className="bake-bar">
                <div className="bake-fill" style={{ width: `${analysePct}%` }} />
              </div>
              <div className="bake-label">
                Elemzés {analysePct}% · {status?.analyse_status || "…"} · maszkok{" "}
                {status?.analyse_masks ?? 0}
              </div>
            </div>
          )}

          {(status?.bake_running || (status?.bake_progress ?? 0) > 0) && (
            <div className="bake-progress">
              <div className="bake-bar">
                <div className="bake-fill" style={{ width: `${bakePct}%` }} />
              </div>
              <div className="bake-label">
                Export {bakePct}% · {status?.bake_status || "…"}
              </div>
            </div>
          )}

          {status?.last_bake?.preview_mp4 || status?.last_bake?.ok ? (
            <div className="export-actions">
              <a
                className="preview-link"
                href="/api/bake/preview.mp4"
                target="_blank"
                rel="noreferrer"
                title="Exportált előnézet MP4 megnyitása."
              >
                HybridCut_preview.mp4
                {status?.last_bake?.bake_range?.audio ? " · hanggal (AAC)" : ""}
              </a>
              <button
                type="button"
                className="btn"
                onClick={() => void onOpenOutput()}
                title="Kimeneti mappa megnyitása az Explorerben."
              >
                Megnyitás Explorerben
              </button>
            </div>
          ) : null}
          {(status?.bake_queue_len ?? 0) > 0 ? (
            <div className="bake-label">Export sor: {status?.bake_queue_len} várakozik</div>
          ) : null}

          <div className="meta">
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
                Assist: <code>{assist.ok ? "llama3 @ 11434" : assist.message}</code>
              </div>
            ) : null}
          </div>
          <div className="license">{status?.license_note}</div>
        </aside>

        <section className="stage">
          <div className="stage-head">
            <div>
              <h2>Előnézet</h2>
              <p className="lead">
                Forrás betöltéskor · Előnézet után Cutout, ha van ember-maszk
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
                    if (v.id === "compare") setWipe(100);
                  }}
                >
                  {v.label}
                </button>
              ))}
            </div>
          </div>

          {viewMode === "compare" ? (
            <div className="wipe-controls">
              <button
                type="button"
                className="btn"
                onClick={() => setWipe(0)}
                title="Csak a maszk / Előtte oldal."
              >
                Előtte
              </button>
              <button
                type="button"
                className="btn"
                onClick={() => setWipe(50)}
                title="Fele-fele összehasonlítás."
              >
                50%
              </button>
              <button
                type="button"
                className="btn"
                onClick={() => setWipe(100)}
                title="Csak a cutout / forrás (Utána) oldal."
              >
                Utána
              </button>
              <input
                className="wipe-slider"
                type="range"
                min={0}
                max={100}
                value={wipe}
                onChange={(e) => setWipe(Number(e.target.value))}
                aria-label="Összehasonlítás csúszka"
                title="Húzd: balra maszk, jobbra cutout/forrás."
              />
            </div>
          ) : null}

          <div className={`preview-stage ${viewMode === "source" || matteEmpty ? "source-solid" : "checker-subtle"}`}>
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
                      onClick={() => void runPreview(tSec, undefined, undefined, { preferCutout: true })}
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
                    <div className="wipe-labels">
                      <span>{matteEmpty ? "Előtte (nincs maszk)" : "Előtte (maszk)"}</span>
                      <span>{matteEmpty ? "Utána (forrás)" : "Utána (cutout)"}</span>
                    </div>
                    <div className="wipe-stage checker-subtle">
                      <img
                        src={`data:${beforeMime};base64,${beforeSrc}`}
                        alt={matteEmpty ? "Forrás — nincs maszk" : "Alpha maszk"}
                        className="wipe-base"
                      />
                      <img
                        src={`data:image/jpeg;base64,${afterSrc}`}
                        alt={matteEmpty ? "Forrás képkocka" : "Cutout"}
                        className="wipe-fg"
                        style={{ clipPath: `inset(0 ${100 - wipe}% 0 0)` }}
                      />
                      <div className="wipe-divider" style={{ left: `${wipe}%` }} />
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
                {seedPng && mode === "max" && viewMode !== "mask" ? (
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
                <p>Előtöltés + MaszkTár adja az élő érzést. A kézi maszk scrub után is megmarad.</p>
              </div>
            )}
          </div>

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
              className={`btn ${showSeed ? "accent" : ""}`}
              disabled={!preview}
              title="Opcionális kézi finomítás — az ember-maszk automatikus (nem kötelező)."
              onClick={() => {
                setShowSeed((v) => {
                  const next = !v;
                  if (next) void refreshSeed();
                  return next;
                });
              }}
            >
              {showSeed ? "Kézi finomítás elrejtése" : "Kézi finomítás (opcionális)"}
            </button>
          </div>

          {showSeed && (
            <SeedPaint
              imageJpegB64={preview?.source_jpeg_b64 || preview?.jpeg_b64 || null}
              initialMaskPngB64={seedPng}
              width={preview?.width ?? 480}
              height={preview?.height ?? 360}
              disabled={locked || !preview}
              onCommit={async (png) => {
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
              }}
              onClear={async () => {
                try {
                  const st = await api.clearSeed();
                  setStatus(st);
                  setSeedPng(null);
                  setNote("Kézi finomítás törölve — auto RVM marad");
                  await runPreview(tSec, st, undefined, { preferCutout: true });
                } catch (e) {
                  setError(e instanceof Error ? e.message : String(e));
                }
              }}
            />
          )}
        </section>
      </main>
    </div>
  );
}
