# HybridCut restart — apex (`2026-10-10-apex`)

Feature stamp: **`2026-10-10-apex`**.

Includes prior: `2026-10-10-peak` · `2026-10-10-continue` · `2026-10-05-ui-nobg` · paint-fix · bgcut-mov · rvm-state · hybrid-polish · max-accuracy.

## After pull / sync

```powershell
cd $env:USERPROFILE\Documents\HybridCut
git pull
Get-Content .\SYNC_VERSION.txt   # 2026-10-10-apex
.\install_to_videoeditor.ps1
cd $env:USERPROFILE\Documents\Videoeditor
$env:HYBRID_RVM_ONNX = "$PWD\models\rvm_resnet50_fp32.onnx"
.\hybrid_cut\start_hybrid_cuda.ps1
# http://127.0.0.1:3847
# Megnyitás → auto Cutout → Exportálás → C:\bgcut\*_full_nobg.mov + _preview.mp4
```

Agent Store (no GitHub):

```powershell
& "$env:LOCALAPPDATA\Cursor\AgentStores\cursor_agent_stores\bc-41930eab-1501-4c19-acf3-0c9d63afbf4d\files\docs\capcut-features\sync_hybrid.ps1"
cd $env:USERPROFILE\Documents\Videoeditor
Get-Content .\hybrid_cut\SYNC_VERSION.txt   # expect: 2026-10-10-apex
.\run_hybrid.ps1
```

## What changed (apex vs peak)

| Area | Behavior |
|------|----------|
| Cutout | `APEX_SPEC` Max default: hair strand recover, micro rim despill, stronger hair/spill/fringe/sharpen |
| Multi-person | Keep all person-sized instances (≥20% of largest) — unchanged |
| Speed | Gyors proxy scrub; Max full-res + streamed BGRA bake (3060 RAM) |
| Export | Always `_full_nobg.mov` + checker `_preview.mp4`; progress `N/M frame` accurate |
| UI | CapCut-clean: HybridCut hero · fewer chips · Részletek for tech · flow Megnyitás→Cutout→Export · lime/orange · Sora/Manrope |
