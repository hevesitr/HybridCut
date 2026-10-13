# HybridCut restart - peak-ui (`2026-10-13-peak-ui`)

Feature stamp: **`2026-10-13-peak-ui`** (includes peak-cutout + simple-bg7).

**Háttéreltávolítás** focus: Megnyitás → Előnézet Cutout → Export. **One timeline** — single **V1** only (no **AI sáv** / + V1 / + B-roll).

## What peak-ui adds

| Area | Behaviour |
|------|-----------|
| **Chrome** | Larger HybridCut brand + `cutout` wordmark; Sora + DM Sans; darker CapCut-class shell |
| **Motion** | Mode pick, preview-ready glow, bake shimmer |
| **Gyors preview** | Display-boost person matte so recognition pops on checker |
| **Prior** | peak-cutout quality + CUDA stick |

## Sync + run (Windows)

```powershell
cd $env:USERPROFILE\Documents\HybridCut
git pull origin main
Get-Content .\SYNC_VERSION.txt   # MUST: 2026-10-13-peak-ui
.\PASTE_PEAK_UI_INSTALL.ps1
# http://127.0.0.1:3847 - Ctrl+F5
```
