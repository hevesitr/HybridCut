# HybridCut restart — layout-fix (`2026-10-10-layout-fix`)

Feature stamp: **`2026-10-10-layout-fix`**.

Includes prior: `2026-10-10-start-fix` · `2026-10-10-eta-ui` · `2026-10-10-apex` · peak · continue · ui-nobg.

## After pull / sync

```powershell
cd $env:USERPROFILE\Documents\HybridCut
git pull
Get-Content .\SYNC_VERSION.txt   # 2026-10-10-layout-fix
.\install_to_videoeditor.ps1
cd $env:USERPROFILE\Documents\Videoeditor
$env:HYBRID_RVM_ONNX = "$PWD\models\rvm_resnet50_fp32.onnx"
.\hybrid_cut\start_hybrid_cuda.ps1
# http://127.0.0.1:3847
# Compact topbar · preview fills height · Be/Ki ETA · no empty top void
```

Agent Store (no GitHub):

```powershell
& "$env:LOCALAPPDATA\Cursor\AgentStores\cursor_agent_stores\bc-41930eab-1501-4c19-acf3-0c9d63afbf4d\files\docs\capcut-features\sync_hybrid.ps1"
cd $env:USERPROFILE\Documents\Videoeditor
Get-Content .\hybrid_cut\SYNC_VERSION.txt   # expect: 2026-10-10-layout-fix
.\run_hybrid.ps1
```

## What changed (layout-fix)

| Area | Behavior |
|------|----------|
| Void fix | `.app` is topbar + workspace only; intel chips in topbar (no `1fr` strip) |
| Layout | Slim rail 280–320px · preview dominant · timeline dock 120–160px |
| Topbar | HybridCut brand + RTX 3060 chip (+ compact status chips) |
| ETA | Labels Be/Ki range; shows full-clip ETA when range is partial; multi-hour Max warn |
| Start | start-fix retained — no CapCut remount pip upgrade by default |
| Quality | Apex cutout/export unchanged |
