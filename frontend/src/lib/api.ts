export type ClipInfo = {
  media_path: string;
  clip_id: string;
  in_sec: number;
  out_sec: number;
  timeline_start_sec: number;
  timeline_end_sec?: number;
  source_duration_sec?: number;
  display_label?: string;
  track_label?: string;
  track?: number;
  opacity: number;
  width?: number;
  height?: number;
  media_duration_sec?: number;
};

export type EditorStatus = {
  sync_version: string;
  mode: "gyors" | "max";
  mode_label: string;
  engine: string;
  backend: string;
  available: boolean;
  license_note: string;
  vram_hint_gb: number;
  detail: string;
  weights_path: string | null;
  media: {
    path: string;
    width: number;
    height: number;
    fps: number;
    frame_count: number;
    duration_sec: number;
  } | null;
  timeline: {
    playhead_sec: number;
    fps: number;
    duration_sec: number;
    selected_clip_id: string | null;
    tracks?: Array<{ id: number; label: string }>;
    clips: ClipInfo[];
  } | null;
  frame_plan: {
    t_sec: number;
    frame_index: number;
    fps: number;
    empty: boolean;
    layers: Array<{
      clip_id: string;
      media_path: string;
      source_t_sec: number;
      opacity: number;
      track?: number;
    }>;
  } | null;
  bake_progress: number;
  bake_status: string;
  bake_running: boolean;
  last_bake: {
    ok: boolean;
    out_dir: string;
    frames_written: number;
    engine: string;
    backend: string;
    message: string;
    preview_mp4?: string | null;
    prores_mov?: string | null;
    bake_range?: { audio?: boolean; broll?: number; clips?: number };
  } | null;
  vram?: {
    cuda_holder: string;
    detail: string;
    vram_budget_gb: number;
  };
  rvm?: {
    onnx_found: boolean;
    onnx_path: string | null;
    onnx_name?: string | null;
    ort_available: boolean;
    cuda_ep: boolean;
    providers: string[];
    prefer?: string;
    source?: string | null;
    engine_backend?: string;
    engine_weights?: string | null;
    ort_error?: string;
    cudnn_ok?: boolean;
    cudnn_detail?: string;
    cuda_fallback?: string | null;
  };
  detail?: string;
  bake_queue_len?: number;
  bake_queue?: Array<{ out_dir: string; max_frames?: number | null; label?: string }>;
  seed_mask?: boolean;
  mask_rate?: number;
  analyse_running?: boolean;
  analyse_progress?: number;
  analyse_status?: string;
  analyse_masks?: number;
  intelligence?: Record<string, unknown>;
};

export type PreviewResult = {
  t_sec: number;
  width: number;
  height: number;
  jpeg_b64: string;
  alpha_png_b64: string;
  engine: string;
  backend: string;
  mode: string;
  meta: Record<string, unknown>;
  frame_plan?: EditorStatus["frame_plan"];
};

export type BakeStart = {
  ok: boolean;
  async: boolean;
  queued?: boolean;
  message: string;
  out_dir?: string;
  frames_written?: number;
  preview_mp4?: string | null;
  status: EditorStatus;
};

export type AssistStatus = {
  ok: boolean;
  message: string;
  host: string;
  chat_model: string;
  embed_model: string;
  models: string[];
  has_llama3: boolean;
  has_nomic: boolean;
};

async function json<T>(url: string, init?: RequestInit): Promise<T> {
  const res = await fetch(url, {
    headers: { "Content-Type": "application/json", ...(init?.headers || {}) },
    ...init,
  });
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      detail = body.detail || JSON.stringify(body);
    } catch {
      /* ignore */
    }
    throw new Error(detail);
  }
  return res.json() as Promise<T>;
}

export const api = {
  status: () => json<EditorStatus>("/api/status"),
  setMode: (mode: "gyors" | "max") =>
    json<EditorStatus>("/api/mode", { method: "POST", body: JSON.stringify({ mode }) }),
  loadSample: () => json<EditorStatus>("/api/demo/sample"),
  openPath: (path: string, append = false, as_broll = false) =>
    json<EditorStatus>("/api/open", {
      method: "POST",
      body: JSON.stringify({ path, append, as_broll }),
    }),
  preview: (t_sec: number) =>
    json<PreviewResult>("/api/preview", {
      method: "POST",
      body: JSON.stringify({ t_sec }),
    }),
  setTimeline: (body: {
    playhead_sec?: number;
    in_sec?: number;
    out_sec?: number;
    clip_id?: string;
    selected_clip_id?: string;
  }) => json<EditorStatus>("/api/timeline", { method: "POST", body: JSON.stringify(body) }),
  timelineAction: (body: {
    action: "duplicate" | "remove" | "cut" | "move" | "select" | "to_broll" | "to_v1";
    clip_id?: string;
    direction?: number;
    t_sec?: number;
  }) =>
    json<EditorStatus>("/api/timeline/action", { method: "POST", body: JSON.stringify(body) }),
  plan: (t_sec?: number) =>
    json<NonNullable<EditorStatus["frame_plan"]>>("/api/plan", {
      method: "POST",
      body: JSON.stringify({ t_sec }),
    }),
  analyse: (mask_rate = 10, max_span_sec?: number) =>
    json<{ ok: boolean; status: EditorStatus } & Record<string, unknown>>("/api/analyse", {
      method: "POST",
      body: JSON.stringify({ mask_rate, max_span_sec }),
    }),
  analyseProgress: () =>
    json<{
      analyse_running: boolean;
      analyse_progress: number;
      analyse_status: string;
      analyse_masks: number;
      mask_rate: number;
    }>("/api/analyse/progress"),
  setSeed: (png_b64: string) =>
    json<EditorStatus & { seed_mask_png_b64?: string }>("/api/seed", {
      method: "POST",
      body: JSON.stringify({ png_b64 }),
    }),
  getSeed: () =>
    json<{ seed_mask: boolean; seed_mask_png_b64: string | null; width?: number; height?: number }>(
      "/api/seed",
    ),
  clearSeed: () => json<EditorStatus>("/api/seed", { method: "DELETE" }),
  bake: (max_frames = 48, async_job = true, queue_if_busy = true, label = "") =>
    json<BakeStart>("/api/bake", {
      method: "POST",
      body: JSON.stringify({ max_frames, async_job, queue_if_busy, label }),
    }),
  bakeProgress: () =>
    json<{
      bake_running: boolean;
      bake_progress: number;
      bake_status: string;
      last_bake: EditorStatus["last_bake"];
      mode: string;
    }>("/api/bake/progress"),
  openOutputFolder: (out_dir?: string) =>
    json<{ ok: boolean; opened: boolean; out_dir: string; error: string | null }>(
      "/api/export/open-folder",
      { method: "POST", body: JSON.stringify({ out_dir: out_dir ?? null }) },
    ),
  assistStatus: () => json<AssistStatus>("/api/assist/status"),
  assistChat: (prompt: string) =>
    json<{ ok: boolean; reply: string | null; error: string | null; status: AssistStatus }>(
      "/api/assist/chat",
      { method: "POST", body: JSON.stringify({ prompt }) },
    ),
  upload: async (file: File, append = false, as_broll = false) => {
    const fd = new FormData();
    fd.append("file", file);
    const qs = new URLSearchParams({
      append: append || as_broll ? "true" : "false",
      as_broll: as_broll ? "true" : "false",
    });
    const res = await fetch(`/api/upload?${qs}`, {
      method: "POST",
      body: fd,
    });
    if (!res.ok) {
      const body = await res.json().catch(() => ({}));
      throw new Error(body.detail || res.statusText);
    }
    return res.json() as Promise<EditorStatus>;
  },
};
