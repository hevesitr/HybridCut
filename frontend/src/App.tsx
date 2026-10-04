import { useEffect, useEffectEvent, useRef, useState, useTransition } from "react";
import { ModeSwitcher } from "./components/ModeSwitcher";
import { SeedPaint } from "./components/SeedPaint";
import { TimelineTrack } from "./components/TimelineTrack";
import { api, type AssistStatus, type EditorStatus, type PreviewResult } from "./lib/api";

function rvmChip(status: EditorStatus | null) {
  const rvm = status?.rvm;
  const backend = (status?.backend || rvm?.engine_backend || "").toLowerCase();
  const ortCuda = !!rvm?.cuda_ep;
  const liveCuda = backend.includes("cuda");
  const onnx = !!rvm?.onnx_found || backend.startsWith("ort-rvm");
  if (liveCuda || (ortCuda && onnx)) {
    return { key: "rvm", label: onnx ? "RVM CUDA" : "CUDA EP", on: true, warn: false };
  }
  if (onnx && rvm?.ort_available) {
    return { key: "rvm", label: "RVM CPU", on: true, warn: true };
  }
  if (onnx) {
    return { key: "rvm", label: "RVM (no ORT)", on: false, warn: true };
  }
  return { key: "rvm", label: "RVM —", on: false, warn: false };
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
      label: status?.mode === "max" ? "Max bake" : "Gyors scrub",
      on: true,
      warn: status?.mode === "max",
    },
    rvmChip(status),
    { key: "mask", label: meta.mask_store ? "MaskStore hit" : "MaskStore", on: !!meta.mask_store },
    { key: "prefetch", label: `Prefetch ×${meta.prefetch_ahead ?? 8}`, on: true },
    { key: "proxy", label: hot > 0 ? `Proxy HOT ${hot}` : "Proxy lanes", on: hot > 0 },
    {
      key: "seed",
      label: status?.seed_mask || meta.user_seed ? "Seed ✓" : "Seed",
      on: !!status?.seed_mask || !!meta.user_seed,
      warn: !!status?.seed_mask,
    },
    {
      key: "broll",
      label: overlays > 0 ? `B-roll ×${overlays}` : status?.intelligence?.broll_track ? "B-roll" : "V1",
      on: overlays > 0 || !!status?.intelligence?.broll_track,
    },
    { key: "audio", label: audio ? "Audio AAC" : "Audio", on: audio },
    {
      key: "queue",
      label: q > 0 ? `Bake sor ${q}` : "Bake sor",
      on: q > 0 || !!status?.bake_running,
    },
    {
      key: "analyse",
      label:
        (status?.analyse_masks ?? 0) > 0
          ? `Analyse ${status?.analyse_masks}`
          : status?.analyse_running
            ? "Analyse…"
            : "Analyse",
      on: (status?.analyse_masks ?? 0) > 0 || !!status?.analyse_running,
    },
  ];
}

function smartStatusLine(
  status: EditorStatus | null,
  note: string,
  busy: boolean,
  error: string | null,
): string {
  if (error) return error;
  if (status?.bake_running) return status.bake_status || "Bake fut…";
  if (status?.analyse_running) return status.analyse_status || "Analyse fut…";
  if (busy) return "Dolgozom…";
  const fallback = status?.rvm?.cuda_fallback || status?.detail || "";
  if (fallback && /CUDA|cuDNN|cudnn/i.test(fallback)) {
    return fallback.length > 220 ? `${fallback.slice(0, 220)}…` : fallback;
  }
  if (status?.rvm?.cudnn_ok === false && status.rvm.cudnn_detail) {
    return status.rvm.cudnn_detail;
  }
  const mode = status?.mode === "max" ? "Max" : "Gyors";
  const seed = status?.seed_mask ? " · seed ✓" : "";
  const clips = status?.timeline?.clips?.length ?? 0;
  const broll = status?.timeline?.clips?.filter((c) => (c.track ?? 0) >= 1).length ?? 0;
  const tl = clips ? ` · ${clips} klip${broll ? ` (${broll} B-roll)` : ""}` : "";
  const base = note || `${mode}${seed}${tl}`;
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
  const [wipe, setWipe] = useState(100);
  const [showWipe, setShowWipe] = useState(false);
  const [dragOver, setDragOver] = useState(false);
  const [assist, setAssist] = useState<AssistStatus | null>(null);
  const [pending, startTransition] = useTransition();
  const fileRef = useRef<HTMLInputElement>(null);
  const appendRef = useRef<HTMLInputElement>(null);
  const brollRef = useRef<HTMLInputElement>(null);
  const scrubTimer = useRef<number | null>(null);

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
    refresh().catch((e: Error) => setError(e.message));
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
        setNote(p.last_bake.message || "Bake kész · audio a preview.mp4-ben");
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
  ) => {
    const cur = st ?? status;
    if (!cur?.media && !cur?.timeline?.clips?.length) return;
    setBusy(true);
    setError(null);
    try {
      await api.setTimeline({ playhead_sec: t });
      const frame = await api.preview(t);
      setPreview(frame);
      const storeHit = frame.meta?.mask_store ? " · MaskStore" : "";
      const seedHit = frame.meta?.user_seed ? " · seed ✓" : "";
      const ov = (frame.meta?.overlay_layers as unknown[] | undefined)?.length ?? 0;
      const ovHit = ov ? ` · B-roll ×${ov}` : "";
      const lanes = frame.meta?.proxy_lanes as { stats?: { hot_hits?: number } } | undefined;
      const laneHit = lanes?.stats?.hot_hits ? ` · HOT ${lanes.stats.hot_hits}` : "";
      setNote(
        noteOverride ??
          `${frame.engine} · ${frame.backend}${storeHit}${seedHit}${ovHit}${laneHit} · t=${frame.t_sec.toFixed(2)}s`,
      );
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
              ? "Gyors: élő scrub · MaskStore · proxy HOT"
              : "Max: seed paint + quality bake (export)",
          );
          if (mode === "max") {
            setShowSeed(true);
            await refreshSeed();
          }
          if (st.media) await runPreview(tSec, st);
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
      syncTrimFromStatus(st);
      await refreshSeed();
      await runPreview(0, st);
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
      if (!append && !asBroll) setTSec(0);
      syncTrimFromStatus(st);
      await runPreview(append || asBroll ? (st.timeline?.playhead_sec ?? 0) : 0, st);
      setNote(
        asBroll
          ? "B-roll a V2 sávon"
          : append
            ? "Klip hozzáadva (V1)"
            : "Videó megnyitva",
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
      setNote(`Trim: ${inSec.toFixed(2)}s → ${outSec.toFixed(2)}s`);
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
      setNote(`Timeline: ${action}`);
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
      setNote(res.status.analyse_status || "Sparse analyse fut…");
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
          ? res.message || "Bake sorba téve"
          : res.message || "Bake fut… (audio AAC mux)",
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
  const statusText = smartStatusLine(status, note, busy, error);

  const rvm = rvmChip(status);
  const rvmDetail = status?.rvm;

  if (!hasMedia) {
    return (
      <div className="app empty">
        {dragOver ? (
          <div className="drop-overlay">
            <strong>Ejtés: videó megnyitása</strong>
          </div>
        ) : null}
        <section className="hero">
          <div className="hero-inner">
            <div className="brand-mark">HybridCut</div>
            <p className="hero-tag">Helyi cutout szerkesztő — nyiss videót, scrubolj, bake-elj.</p>
            <p className="hero-sub">
              1) Videó vagy minta · 2) Gyors élő scrub · 3) Max seed + Bake + hang · RTX 3060 ·
              Ollama-only.
            </p>
            <div className="hero-cta">
              <button type="button" className="btn primary" disabled={locked} onClick={onSample}>
                Minta videó
              </button>
              <button
                type="button"
                className="btn accent"
                disabled={locked}
                onClick={() => fileRef.current?.click()}
              >
                Videó megnyitása
              </button>
            </div>
            <ModeSwitcher mode={mode} disabled={locked || pending} onChange={onMode} />
            <div className="hero-chips" aria-label="Runtime status">
              <span className={`intel-chip ${rvm.on ? "on" : ""} ${rvm.warn ? "warn" : ""}`}>
                {rvm.label}
              </span>
              <span className={`intel-chip ${rvmDetail?.onnx_found ? "on" : ""}`}>
                {rvmDetail?.onnx_found
                  ? `ONNX ${rvmDetail.onnx_name || "✓"}`
                  : "ONNX hiányzik"}
              </span>
              <span className={`intel-chip ${rvmDetail?.ort_available ? "on" : ""}`}>
                {rvmDetail?.ort_available ? "ORT ✓" : "ORT —"}
              </span>
              <span className={`intel-chip ${assist?.ok ? "on" : ""}`}>
                {assist?.ok ? "Ollama ✓" : "Ollama —"}
              </span>
            </div>
            <p className="hero-hint">
              {rvmDetail?.onnx_found
                ? `RVM: ${rvmDetail.source === "parent_videoeditor" ? "parent Videoeditor models" : rvmDetail.source || "discovered"}`
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

      <div className="intel-strip" aria-label="Intelligence status">
        {chips.map((c) => (
          <span
            key={c.key}
            className={`intel-chip ${c.on ? "on" : ""} ${c.warn ? "warn" : ""}`}
          >
            {c.label}
          </span>
        ))}
        {assist ? (
          <span className={`intel-chip ${assist.ok ? "on" : ""}`} title={assist.message}>
            {assist.ok ? "Ollama ✓" : "Ollama —"}
          </span>
        ) : null}
      </div>

      <main className="workspace">
        <aside className="rail">
          <div className="rail-block">
            <h2>Matting motor</h2>
            <p className="lead">
              <strong>Gyors</strong> = scrub · <strong>Max</strong> = seed + export bake
            </p>
            <ModeSwitcher mode={mode} disabled={locked || pending} onChange={onMode} />
            <div className="actions">
              <button type="button" className="btn primary" disabled={locked} onClick={onSample}>
                Minta
              </button>
              <button
                type="button"
                className="btn"
                disabled={locked}
                onClick={() => fileRef.current?.click()}
              >
                Megnyitás
              </button>
              <button
                type="button"
                className="btn"
                disabled={locked}
                onClick={() => appendRef.current?.click()}
              >
                + V1 klip
              </button>
              <button
                type="button"
                className="btn accent"
                disabled={locked}
                onClick={() => brollRef.current?.click()}
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
                onClick={() => runPreview(tSec)}
              >
                Előnézet
              </button>
              <button
                type="button"
                className="btn"
                disabled={locked || !status?.media}
                onClick={onAnalyse}
              >
                Analyse
              </button>
              <button
                type="button"
                className={`btn ${mode === "max" ? "accent" : "primary"}`}
                disabled={(!status?.media && !clips.length) || (!!status?.analyse_running)}
                onClick={onBake}
                title="Ha bake fut, a következő a sorba kerül"
              >
                {status?.bake_running ? "Bake sorba +" : "Bake + hang"}
              </button>
              <button
                type="button"
                className="btn"
                disabled={!status?.last_bake?.ok && !status?.last_bake?.out_dir}
                onClick={() => void onOpenOutput()}
              >
                Kimenet mappa
              </button>
            </div>
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
            <h3>Timeline</h3>
            <div className="actions tight">
              <button
                type="button"
                className="btn"
                disabled={locked || !clips.length}
                onClick={() => runAction("duplicate")}
              >
                Duplikál
              </button>
              <button
                type="button"
                className="btn"
                disabled={locked || clips.length < 2}
                onClick={() => runAction("remove")}
              >
                Töröl
              </button>
              <button
                type="button"
                className="btn"
                disabled={locked || !clips.length}
                onClick={() => runAction("cut", { t_sec: tSec })}
              >
                Vágás
              </button>
              <button
                type="button"
                className="btn"
                disabled={locked || !selected}
                onClick={() => runAction("move", { clip_id: selected ?? undefined, direction: -1 })}
              >
                ←
              </button>
              <button
                type="button"
                className="btn"
                disabled={locked || !selected}
                onClick={() => runAction("move", { clip_id: selected ?? undefined, direction: 1 })}
              >
                →
              </button>
              <button
                type="button"
                className="btn accent"
                disabled={locked || !selected}
                onClick={() => runAction("to_broll", { clip_id: selected ?? undefined })}
                title="Kijelölt klip → V2 B-roll"
              >
                → B-roll
              </button>
              <button
                type="button"
                className="btn"
                disabled={locked || !selected}
                onClick={() => runAction("to_v1", { clip_id: selected ?? undefined })}
              >
                → V1
              </button>
            </div>
            <div className="trim-row">
              <label>
                In
                <input
                  type="number"
                  min={0}
                  step={0.05}
                  value={inSec}
                  disabled={!clips.length || locked}
                  onChange={(e) => setInSec(Number(e.target.value))}
                />
              </label>
              <label>
                Out
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
              >
                Trim
              </button>
            </div>
          </div>

          {(status?.analyse_running || (status?.analyse_progress ?? 0) > 0) && (
            <div className="bake-progress">
              <div className="bake-bar">
                <div className="bake-fill" style={{ width: `${analysePct}%` }} />
              </div>
              <div className="bake-label">
                Analyse {analysePct}% · {status?.analyse_status || "…"} · masks{" "}
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
                {bakePct}% · {status?.bake_status || "…"}
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
              >
                HybridCut_preview.mp4
                {status?.last_bake?.bake_range?.audio ? " · hanggal (AAC)" : ""}
              </a>
              <button type="button" className="btn" onClick={() => void onOpenOutput()}>
                Megnyitás Explorerben
              </button>
            </div>
          ) : null}
          {(status?.bake_queue_len ?? 0) > 0 ? (
            <div className="bake-label">Bake sor: {status?.bake_queue_len} várakozik</div>
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
                FramePlan:{" "}
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
              <p className="lead">V1/V2 timeline · MaskStore · wipe · Max seed (perzisztens)</p>
            </div>
            <div className="preview-tools">
              <button
                type="button"
                className={`btn ${showWipe ? "primary" : ""}`}
                disabled={!preview}
                onClick={() => setShowWipe((v) => !v)}
              >
                Előtte / Utána
              </button>
              {showWipe ? (
                <div className="wipe-controls">
                  <button type="button" className="btn" onClick={() => setWipe(0)} title="Csak alpha">
                    Előtte
                  </button>
                  <button type="button" className="btn" onClick={() => setWipe(50)}>
                    50%
                  </button>
                  <button
                    type="button"
                    className="btn"
                    onClick={() => setWipe(100)}
                    title="Csak cutout"
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
                    aria-label="Wipe összehasonlítás"
                  />
                </div>
              ) : null}
            </div>
          </div>

          <div className="preview-stage">
            {preview ? (
              <div className="wipe-wrap">
                {showWipe && preview.alpha_png_b64 ? (
                  <div className="wipe-compare">
                    <div className="wipe-labels">
                      <span>Előtte (alpha)</span>
                      <span>Utána (cutout)</span>
                    </div>
                    <div className="wipe-stage">
                      <img
                        src={`data:image/png;base64,${preview.alpha_png_b64}`}
                        alt="Alpha"
                        className="wipe-base"
                      />
                      <img
                        src={`data:image/jpeg;base64,${preview.jpeg_b64}`}
                        alt="Cutout"
                        className="wipe-fg"
                        style={{ clipPath: `inset(0 ${100 - wipe}% 0 0)` }}
                      />
                      <div className="wipe-divider" style={{ left: `${wipe}%` }} />
                    </div>
                  </div>
                ) : (
                  <img src={`data:image/jpeg;base64,${preview.jpeg_b64}`} alt="Matting előnézet" />
                )}
                {seedPng && mode === "max" ? (
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
                <h3>Scrub a timeline-on</h3>
                <p>MaskStore + prefetch adja az élő érzést. Seed megmarad scrub közben.</p>
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
              />
              <span>{duration.toFixed(1)}s</span>
            </div>
            <div className={`status-line ${error ? "error" : ""}`}>{statusText}</div>
          </div>

          <div className="seed-toggle">
            <button
              type="button"
              className={`btn ${showSeed || mode === "max" ? "accent" : ""}`}
              disabled={!preview}
              onClick={() => {
                setShowSeed((v) => {
                  const next = !v;
                  if (next) void refreshSeed();
                  return next;
                });
              }}
            >
              {showSeed ? "Seed panel elrejtése" : "Max seed paint"}
            </button>
          </div>

          {showSeed && (
            <SeedPaint
              imageJpegB64={preview?.jpeg_b64 ?? null}
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
                  setNote("Seed mask mentve · túléli a scruböt / újratöltést");
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
                  setNote("Seed törölve");
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
