"""Hybrid Videoeditor — greenfield host + matting engines."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SYNC_VERSION = (ROOT / "SYNC_VERSION.txt").read_text(encoding="utf-8").strip()

__version__ = SYNC_VERSION

# CRITICAL: prepend pip nvidia-cudnn / cublas bins to PATH before ORT loads.
# HybridCut's own .venv often has onnxruntime-gpu but missing cudnn64_9.dll on PATH.
try:
    from hybrid_editor.cuda_path import inject_nvidia_pip_libs

    inject_nvidia_pip_libs()
except Exception:
    pass
