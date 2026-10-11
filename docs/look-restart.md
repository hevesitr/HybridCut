# HybridCut restart — look (`2026-10-10-look`)

Feature stamp: **`2026-10-10-look`**.

Includes prior: `2026-10-10-layout-fix` · `2026-10-10-start-fix` · `2026-10-10-eta-ui` · apex · peak · continue · ui-nobg.

## Pull + start (GitHub)

```powershell
cd $env:USERPROFILE\Documents\HybridCut
git pull
Get-Content .\SYNC_VERSION.txt   # 2026-10-10-look
.\install_to_videoeditor.ps1
cd $env:USERPROFILE\Documents\Videoeditor
$env:HYBRID_RVM_ONNX = "$PWD\models\rvm_resnet50_fp32.onnx"
.\hybrid_cut\start_hybrid_cuda.ps1
# http://127.0.0.1:3847 — hard-refresh (Ctrl+F5)
```

## Agent Store sync (no GitHub)

```powershell
& "$env:LOCALAPPDATA\Cursor\AgentStores\cursor_agent_stores\bc-41930eab-1501-4c19-acf3-0c9d63afbf4d\files\docs\capcut-features\sync_hybrid.ps1"
cd $env:USERPROFILE\Documents\Videoeditor
Get-Content .\hybrid_cut\SYNC_VERSION.txt   # expect: 2026-10-10-look
.\run_hybrid.ps1
```

## Look notes

- Syne (display) + Figtree (body); lime `#b8f000` / orange `#ff7a1a` on deep olive ink
- Atmospheric layered gradients + diagonal hatch — not flat void
- Compact topbar: hero-weight HybridCut + RTX 3060 + slim chips
- Slim rail ~250–280px; preview fills; timeline secondary
- ETA on Gyors/Max cards; duplicate eta-pair cards removed
- Motions: `mode-pick`, `preview-load`, `result-in`
