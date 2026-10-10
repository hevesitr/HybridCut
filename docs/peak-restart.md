# HybridCut restart — peak (`2026-10-10-peak`)

Feature stamp: **`2026-10-10-peak`**.

Includes prior: `2026-10-10-continue` · `2026-10-05-ui-nobg` · paint-fix · bgcut-mov · rvm-state · hybrid-polish · max-accuracy.

## After pull / sync

```powershell
cd $env:USERPROFILE\Documents\HybridCut
git pull
Get-Content .\SYNC_VERSION.txt   # 2026-10-10-peak
.\install_to_videoeditor.ps1
cd $env:USERPROFILE\Documents\Videoeditor
$env:HYBRID_RVM_ONNX = "$PWD\models\rvm_resnet50_fp32.onnx"
.\hybrid_cut\start_hybrid_cuda.ps1
# http://127.0.0.1:3847
# Max + Éles szélek → Előnézet Cutout → Export → C:\bgcut\*_full_nobg.mov + _preview.mp4
```

Agent Store (no GitHub):

```powershell
& "$env:LOCALAPPDATA\Cursor\AgentStores\cursor_agent_stores\bc-41930eab-1501-4c19-acf3-0c9d63afbf4d\files\docs\capcut-features\sync_hybrid.ps1"
cd $env:USERPROFILE\Documents\Videoeditor
Get-Content .\hybrid_cut\SYNC_VERSION.txt   # expect: 2026-10-10-peak
.\run_hybrid.ps1
```

## What changed (peak)

| Area | Behavior |
|------|----------|
| Cutout | `PEAK_SPEC`: unknown-band hair, bright-fringe kill, edge sharpen, stronger despill/decontam |
| Multi-person | Keep all person-sized instances (≥20% of largest) — from continue |
| Warmup | MatAnyone2-inspired ×10 on frame 0 / re-warmup on drift |
| Speed | Gyors proxy scrub; Max full-res + streamed BGRA bake (3060 RAM) |
| Export | Always `_full_nobg.mov` + checker `_preview.mp4`; ffmpeg resolve hardened |
| UI | CapCut-simple HU: load → preview cutout → export; result card; paint in chrome |
