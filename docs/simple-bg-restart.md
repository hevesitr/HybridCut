# HybridCut restart - simple-bg7 (`2026-10-13-simple-bg7`)

Feature stamp: **`2026-10-13-simple-bg7`**.

**Háttéreltávolítás** focus: Megnyitás → Előnézet Cutout → Export. **One timeline** — single **V1** only (no **AI sáv** / + V1 / + B-roll).

## What simple-bg7 does

| Area | Behaviour |
|------|-----------|
| **CUDA stick** | `start_hybrid_cuda.ps1` hard-probes EP; persists `cache/ort_provider.txt`. `run_hybrid.ps1` re-probes when cache=cuda (no fake CUDA). |
| **Install** | `PASTE_SIMPLE_BG7_INSTALL.ps1` launches CUDA starter (does **not** force CPU). |
| **ORT pin** | `onnxruntime-gpu==1.30.0` + cuDNN PATH + provider DLL dirs. |
| **Cutout** | Max enables sharp edges; CPU Max uses `CPU_MAX_SPEC` + soft-alpha crush. |
| **Gyors** | Mode sticks (no Max flip-loop); auto Max once per open. |
| **ETA** | Max chip shows `· CUDA` or `· CPU` matching live path. |

## Sync + run (Windows)

```powershell
cd $env:USERPROFILE\Documents\HybridCut
git pull origin main
Get-Content .\SYNC_VERSION.txt   # MUST: 2026-10-13-simple-bg7
.\PASTE_SIMPLE_BG7_INSTALL.ps1
# http://127.0.0.1:3847 - Ctrl+F5
# Expect badge RVM CUDA when probe OK, else honest CPU ORT
```
