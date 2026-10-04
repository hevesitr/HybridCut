# Models (not shipped)

Place user-obtained weights here, or set env paths:

| File / env | Role |
|------------|------|
| `rvm_mobilenetv3_fp16.onnx` or `HYBRID_RVM_ONNX` | FastEngine ORT RVM (opt-in download: `scripts/download_rvm.ps1`) |
| `HYBRID_MATANYONE2_WEIGHTS` | Max MatAnyone2 adapter — **S-Lab NC, not redistributed** |

Without RVM ONNX, FastEngine uses the documented OpenCV heuristic fallback (demo/CI only).
