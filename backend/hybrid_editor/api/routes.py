"""REST routes wiring UI → MattingEngine + multi-clip timeline + analyse + seed."""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from hybrid_editor import ROOT, SYNC_VERSION
from hybrid_editor.cache import MASK_RATE
from hybrid_editor.session import SESSION

router = APIRouter()


class ModeBody(BaseModel):
    mode: str = Field(..., description="gyors | max")


class SharpEdgesBody(BaseModel):
    enabled: bool = Field(True, description="Éles szélek — default on for Max/export")


class OpenBody(BaseModel):
    path: str
    append: bool = False
    track: int = 0
    as_broll: bool = False


class PreviewBody(BaseModel):
    t_sec: float = 0.0


class BakeBody(BaseModel):
    # None = full In/Out (or full media). Never default to a preview sample (was 48 ≈ 1–2s).
    max_frames: Optional[int] = None
    out_dir: Optional[str] = None
    async_job: bool = True
    queue_if_busy: bool = True
    label: str = ""


class OpenFolderBody(BaseModel):
    out_dir: Optional[str] = None


class TimelineBody(BaseModel):
    playhead_sec: Optional[float] = None
    in_sec: Optional[float] = None
    out_sec: Optional[float] = None
    clip_id: Optional[str] = None
    selected_clip_id: Optional[str] = None


class TimelineActionBody(BaseModel):
    action: str = Field(
        ...,
        description="duplicate|remove|cut|move|select|to_broll|to_v1",
    )
    clip_id: Optional[str] = None
    direction: Optional[int] = None
    t_sec: Optional[float] = None


class PlanBody(BaseModel):
    t_sec: Optional[float] = None


class AnalyseBody(BaseModel):
    mask_rate: float = MASK_RATE
    max_span_sec: Optional[float] = None


class SeedBody(BaseModel):
    png_b64: str = Field(..., description="PNG alpha (or RGBA) as base64 / data-URL")


class AssistChatBody(BaseModel):
    prompt: str = Field(..., min_length=1)
    system: Optional[str] = None


@router.get("/health")
def health() -> dict:
    return {"ok": True, "sync_version": SYNC_VERSION, "brand": "HybridCut"}


@router.get("/status")
def status() -> dict:
    return SESSION.status()


@router.post("/mode")
def set_mode(body: ModeBody) -> dict:
    try:
        return SESSION.set_mode(body.mode)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/sharp-edges")
def set_sharp_edges(body: SharpEdgesBody) -> dict:
    """Éles szélek toggle — tighter trimap / PNG cutout / full-res Max bake."""
    return SESSION.set_sharp_edges(body.enabled)


@router.post("/open")
def open_path(body: OpenBody) -> dict:
    path = Path(body.path).expanduser()
    if not path.is_file():
        raise HTTPException(status_code=404, detail=f"File not found: {path}")
    try:
        return SESSION.open_media(
            path,
            append=body.append,
            track=body.track,
            as_broll=body.as_broll,
        )
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/upload")
async def upload_video(
    file: UploadFile = File(...),
    append: bool = False,
    as_broll: bool = False,
    track: int = 0,
) -> dict:
    suffix = Path(file.filename or "clip.mp4").suffix or ".mp4"
    dest_dir = ROOT / "cache" / "uploads"
    dest_dir.mkdir(parents=True, exist_ok=True)
    # Unique name when appending so multi-clip keeps distinct files
    stem = "upload"
    if append or as_broll:
        from uuid import uuid4

        stem = f"upload-{uuid4().hex[:8]}"
    dest = dest_dir / f"{stem}{suffix}"
    with dest.open("wb") as f:
        shutil.copyfileobj(file.file, f)
    try:
        return SESSION.open_media(
            dest,
            append=append or as_broll,
            track=track,
            as_broll=as_broll,
        )
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/preview")
def preview(body: PreviewBody) -> dict:
    try:
        frame = SESSION.preview(body.t_sec)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {
        "t_sec": frame.t_sec,
        "width": frame.width,
        "height": frame.height,
        "jpeg_b64": frame.jpeg_b64,
        "alpha_png_b64": frame.alpha_png_b64,
        "source_jpeg_b64": frame.source_jpeg_b64 or "",
        "engine": frame.engine,
        "backend": frame.backend,
        "meta": frame.meta,
        "mode": SESSION.mode.value,
        "frame_plan": SESSION.status().get("frame_plan"),
    }


@router.post("/timeline")
def update_timeline(body: TimelineBody) -> dict:
    try:
        return SESSION.update_timeline(
            playhead_sec=body.playhead_sec,
            in_sec=body.in_sec,
            out_sec=body.out_sec,
            clip_id=body.clip_id,
            selected_clip_id=body.selected_clip_id,
        )
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/timeline/action")
def timeline_action(body: TimelineActionBody) -> dict:
    try:
        return SESSION.timeline_action(
            body.action,
            clip_id=body.clip_id,
            direction=body.direction,
            t_sec=body.t_sec,
        )
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/plan")
def frame_plan(body: PlanBody) -> dict:
    try:
        return SESSION.get_frame_plan(body.t_sec)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/analyse")
def start_analyse(body: AnalyseBody) -> dict:
    try:
        job = SESSION.start_analyse(mask_rate=body.mask_rate, max_span_sec=body.max_span_sec)
        return {"ok": True, **job, "status": SESSION.status()}
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/analyse/progress")
def analyse_progress() -> dict:
    st = SESSION.status()
    return {
        "analyse_running": st.get("analyse_running", False),
        "analyse_progress": st.get("analyse_progress", 0.0),
        "analyse_status": st.get("analyse_status", ""),
        "analyse_masks": st.get("analyse_masks", 0),
        "mask_rate": st.get("mask_rate", MASK_RATE),
    }


@router.post("/seed")
def set_seed(body: SeedBody) -> dict:
    try:
        return SESSION.set_seed_mask(body.png_b64)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/seed")
def get_seed() -> dict:
    return SESSION.get_seed_mask()


@router.delete("/seed")
def clear_seed() -> dict:
    return SESSION.clear_seed_mask()


@router.post("/bake")
def bake(body: BakeBody) -> dict:
    from hybrid_editor.export.bgcut import default_bgcut_dir, ensure_bgcut_dir

    # Default: Videoeditor-style C:\bgcut\ (create if missing). Override via out_dir / HYBRID_BGCUT_DIR.
    out = Path(body.out_dir) if body.out_dir else default_bgcut_dir()
    ensure_bgcut_dir(out)
    try:
        result = SESSION.bake(
            out,
            max_frames=body.max_frames,
            async_job=body.async_job,
            queue_if_busy=body.queue_if_busy,
            label=body.label,
        )
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if isinstance(result, dict):
        queued = bool(result.get("queued"))
        return {
            "ok": True,
            "async": True,
            "queued": queued,
            "out_dir": str(out.resolve()),
            "message": result.get("bake_status", "Bake started"),
            "status": result,
            "mode": SESSION.mode.value,
        }

    return {
        "ok": result.ok,
        "async": False,
        "queued": False,
        "out_dir": result.out_dir,
        "frames_written": result.frames_written,
        "engine": result.engine,
        "backend": result.backend,
        "message": result.message,
        "alpha_preview": result.alpha_preview,
        "preview_mp4": result.preview_mp4,
        "prores_mov": result.prores_mov,
        "bake_range": result.bake_range,
        "mode": SESSION.mode.value,
        "status": SESSION.status(),
    }


@router.post("/export/open-folder")
def open_export_folder(body: OpenFolderBody | None = None) -> dict:
    """Open last bake output folder (Windows Explorer / OS file manager)."""
    try:
        return SESSION.open_output_folder(None if body is None else body.out_dir)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/bake/progress")
def bake_progress() -> dict:
    st = SESSION.status()
    return {
        "bake_running": st["bake_running"],
        "bake_progress": st["bake_progress"],
        "bake_status": st["bake_status"],
        "last_bake": st["last_bake"],
        "mode": st["mode"],
    }


@router.get("/bake/preview.mp4")
def bake_preview_file() -> FileResponse:
    st = SESSION.status()
    last = st.get("last_bake") or {}
    path = last.get("preview_mp4")
    if not path or not Path(path).is_file():
        cand = ROOT / "cache" / "bake" / SESSION.mode.value / "preview.mp4"
        if cand.is_file():
            path = str(cand)
        else:
            raise HTTPException(status_code=404, detail="Nincs preview.mp4 — futtass bake-et")
    return FileResponse(path, media_type="video/mp4", filename="hybridcut_preview.mp4")


@router.get("/assist/status")
def assist_status() -> dict:
    """Local Ollama probe — llama3 @ localhost:11434 (no paid APIs)."""
    from hybrid_editor.assist import status as ollama_status

    return ollama_status().to_dict()


@router.post("/assist/chat")
def assist_chat(body: AssistChatBody) -> dict:
    from hybrid_editor.assist import chat as ollama_chat

    system = body.system or (
        "You are HybridCut local assist for a Windows video cutout editor. "
        "Be brief. Suggest Gyors vs Max, seed paint, analyse, bake, B-roll. "
        "Never recommend paid cloud APIs."
    )
    return ollama_chat(body.prompt, system=system)


@router.api_route("/demo/sample", methods=["GET", "POST"])
def ensure_sample() -> dict:
    """Create a tiny synthetic MP4 if none uploaded — keeps first-run UX alive."""
    sample = ROOT / "cache" / "sample_person.mp4"
    sample.parent.mkdir(parents=True, exist_ok=True)
    if not sample.is_file():
        import cv2
        import numpy as np

        w, h, n, fps = 480, 360, 36, 12
        fourcc = cv2.VideoWriter_fourcc(*"mp4v")
        writer = cv2.VideoWriter(str(sample), fourcc, fps, (w, h))
        for i in range(n):
            frame = np.zeros((h, w, 3), np.uint8)
            frame[:] = (40, 90, 50)
            cx = int(w * 0.35 + (i / n) * w * 0.3)
            cy = int(h * 0.55)
            cv2.ellipse(frame, (cx, cy), (55, 110), 0, 0, 360, (40, 55, 190), -1)
            cv2.circle(frame, (cx, cy - 90), 38, (50, 70, 200), -1)
            writer.write(frame)
        writer.release()
    return SESSION.open_media(sample)
