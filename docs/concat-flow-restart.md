# HybridCut restart — concat-flow (`2026-10-11-concat-flow`)

Feature stamp: **`2026-10-11-concat-flow`**.

GitHub `main`: `7d1d9fc` · compare https://github.com/hevesitr/HybridCut/compare/97a606b...7d1d9fc

Includes prior: `2026-10-10-look2` · look · layout-fix · start-fix · eta-ui · apex · peak · continue · ui-nobg.

## Pull + start (GitHub)

```powershell
cd $env:USERPROFILE\Documents\HybridCut
git pull
Get-Content .\SYNC_VERSION.txt   # 2026-10-11-concat-flow
.\install_to_videoeditor.ps1
cd $env:USERPROFILE\Documents\Videoeditor
$env:HYBRID_RVM_ONNX = "$PWD\models\rvm_resnet50_fp32.onnx"
.\hybrid_cut\start_hybrid_cuda.ps1
# http://127.0.0.1:3847 — hard-refresh (Ctrl+F5)
# Új projekt · + V1 klip · Forrás/Cutout fills preview stage
```

## Agent Store sync (no GitHub)

```powershell
& "$env:LOCALAPPDATA\Cursor\AgentStores\cursor_agent_stores\bc-41930eab-1501-4c19-acf3-0c9d63afbf4d\files\docs\capcut-features\sync_hybrid.ps1"
cd $env:USERPROFILE\Documents\Videoeditor
Get-Content .\hybrid_cut\SYNC_VERSION.txt   # expect: 2026-10-11-concat-flow
.\run_hybrid.ps1
```

## concat-flow notes

- **Új projekt** (topbar) clears session → full-bleed empty drop; confirm if dirty
- **+ V1 klip** / drop with media open → `append=true` sequential V1; **+ B-roll** → V2
- Preview CSS: single modes fill stage (`object-fit: contain`); wipe only splits
- look2 lime `#b8f000` / orange `#ff7a1a` + Syne/Figtree retained
