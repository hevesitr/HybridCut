# HybridCut restart — continue (`2026-10-10-continue`)

Feature stamp: **`2026-10-10-continue`**.

Includes prior: `2026-10-05-ui-nobg` · paint-fix · bgcut-mov · rvm-state · hybrid-polish.

## After pull / sync

```powershell
cd $env:USERPROFILE\Documents\HybridCut
git pull
Get-Content .\SYNC_VERSION.txt   # 2026-10-10-continue
.\install_to_videoeditor.ps1
cd $env:USERPROFILE\Documents\Videoeditor
$env:HYBRID_RVM_ONNX = "$PWD\models\rvm_resnet50_fp32.onnx"
.\hybrid_cut\start_hybrid_cuda.ps1
# http://127.0.0.1:3847
# Max + Éles szélek — 2+ people should all cut out; Export → C:\bgcut\*_full_nobg.mov + _preview.mp4
```

Agent Store (no GitHub):

```powershell
& "$env:LOCALAPPDATA\Cursor\AgentStores\cursor_agent_stores\bc-41930eab-1501-4c19-acf3-0c9d63afbf4d\files\docs\capcut-features\sync_hybrid.ps1"
cd $env:USERPROFILE\Documents\Videoeditor
Get-Content .\hybrid_cut\SYNC_VERSION.txt   # expect: 2026-10-10-continue
.\run_hybrid.ps1
```

## What changed

| Area | Behavior |
|------|----------|
| Multi-person Max | Keep all person-sized instances (≥20% of largest CC) — secondary subjects not left as solid BG |
| Export | Always `_full_nobg.mov` + checker `_preview.mp4`; mux fail = red card / clear log |
| UI | Leaner chips; paint stays in chrome; lime/orange brand |
| Unchanged | RVM recurrent size reset · full-duration bake · `C:\bgcut` naming |
