# HybridCut restart - simple-bg5 (`2026-10-12-simple-bg5`)

Feature stamp: **`2026-10-12-simple-bg5`**.

**Hattereltavolitas** focus: Megnyitas -> Elonezet Cutout -> Export. **One timeline** - single **V1** only (no **AI sav** / + V1 / + B-roll).

## Why Max said 43s but took ~15 min on simple-bg4

ETA was CUDA-calibrated. Badge **CPU ORT** ran full-res ResNet Max (~3-4 s/frame).

## What simple-bg5 does

| Area | Behaviour |
|------|-----------|
| **CPU Max bake** | MobileNet @ ~720 long-side (not full-res ResNet) so wall-clock ~CUDA ETA (~43s / 10s@24fps) |
| **ETA** | CPU-aware; Max stays near 43s when CPU ORT (fast-path) |
| **CUDA** | Still preferred when `start_hybrid_cuda.ps1` hard-probe OK - then full-res ResNet Max |
| **Opt-out** | `$env:HYBRID_CPU_MAX_FULLRES="1"` for slow full-res on CPU |
| **Matte** | simple-bg4 ladder kept (ResNet / chroma / Gyors->Max auto-retry) |

## Sync + run (Windows)

```powershell
cd $env:USERPROFILE\Documents\HybridCut
git pull origin main
Get-Content .\SYNC_VERSION.txt   # MUST: 2026-10-12-simple-bg5
.\PASTE_SIMPLE_BG5_INSTALL.ps1
# http://127.0.0.1:3847 - Ctrl+F5 - Max Export should finish near chip ETA
```
