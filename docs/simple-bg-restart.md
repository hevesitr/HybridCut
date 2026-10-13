# HybridCut restart - peak-cutout (`2026-10-13-peak-cutout`)

Feature stamp: **`2026-10-13-peak-cutout`** (includes simple-bg7 CUDA stick).

**Háttéreltávolítás** focus: Megnyitás → Előnézet Cutout → Export. **One timeline** — single **V1** only (no **AI sáv** / + V1 / + B-roll).

## What peak-cutout adds

| Upgrade | Source idea | Behaviour |
|---------|-------------|-----------|
| Guided alpha upsample | RVM DGF / guided-filter (MIT family) | Edge-aware 720→native (less soft halo) |
| Flow temporal smooth | Alpha-Flow / TemporalConsistency (reimpl) | Farneback warp + EMA flicker kill |
| RVM downsample | PeterL1n official table | Full-body bias, stage-1 in 256–512 |
| RVM fgr composite | PeterL1n fgr output | Cleaner edge RGB before despill |
| Peak edge crisp | Classical unsharp mid-band | Needle silhouette |
| CUDA stick (bg7) | onnxruntime plugin EP probe | Persist + re-probe; no forced CPU install |

## Sync + run (Windows)

```powershell
cd $env:USERPROFILE\Documents\HybridCut
git pull origin main
Get-Content .\SYNC_VERSION.txt   # MUST: 2026-10-13-peak-cutout
.\PASTE_PEAK_CUTOUT_INSTALL.ps1
# http://127.0.0.1:3847 - Ctrl+F5
```
