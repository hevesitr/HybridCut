"""HybridCut FastAPI entrypoint."""

from __future__ import annotations

import os
from pathlib import Path

# Prefer CUDA (RTX 3060). Force CPU: $env:HYBRID_ORT_PROVIDER = "cpu"
if "HYBRID_ORT_PROVIDER" not in os.environ:
    os.environ["HYBRID_ORT_PROVIDER"] = "cuda"

# PATH inject before any engine/ORT import (hybrid_editor package also injects).
try:
    from hybrid_editor.cuda_path import inject_nvidia_pip_libs, pip_cudnn_present

    inject_nvidia_pip_libs()
    _ok, _detail = pip_cudnn_present()
    if not _ok:
        print(f"[HybridCut] cuDNN note: {_detail}")
except Exception:
    pass

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from hybrid_editor import SYNC_VERSION
from hybrid_editor.api.routes import router

APP_ROOT = Path(__file__).resolve().parents[2]
FRONTEND_DIST = APP_ROOT / "frontend" / "dist"

app = FastAPI(
    title="HybridCut",
    description="Hybrid Videoeditor — Gyors RVM + Max minőség (MatAnyone2 adapter / quality pipeline)",
    version=SYNC_VERSION,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router, prefix="/api")


@app.get("/api")
def api_root() -> dict:
    return {"brand": "HybridCut", "sync_version": SYNC_VERSION}


if FRONTEND_DIST.is_dir():
    app.mount("/assets", StaticFiles(directory=FRONTEND_DIST / "assets"), name="assets")

    @app.get("/")
    def index() -> FileResponse:
        return FileResponse(FRONTEND_DIST / "index.html")


def run() -> None:
    import uvicorn

    host = os.environ.get("HYBRID_HOST", "127.0.0.1")
    port = int(os.environ.get("HYBRID_PORT", "3847"))
    uvicorn.run("hybrid_editor.main:app", host=host, port=port, reload=False)


if __name__ == "__main__":
    run()
