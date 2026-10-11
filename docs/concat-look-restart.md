# HybridCut restart — concat-look (`2026-10-11-concat-look`)

Feature stamp: **`2026-10-11-concat-look`**.

Includes prior: `2026-10-11-clip-delete` · `2026-10-11-timeline-bg` · `2026-10-11-concat-flow` · look2.

## Pull + start (GitHub)

```powershell
cd $env:USERPROFILE\Documents\HybridCut
git pull
Get-Content .\SYNC_VERSION.txt   # 2026-10-11-concat-look
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
Get-Content .\hybrid_cut\SYNC_VERSION.txt   # expect: 2026-10-11-concat-look
.\run_hybrid.ps1
```

## Look notes

- Charcoal dark (`#121212`) + lime `#b8f000` primary; orange reserved for Max
- Projects home: sidebar Megnyitás / Minta / Beállítások · **+ Új projekt**
- Editor: big preview · timeline tools + HH:MM:SS:FF · L/V/M track chrome · right PROJECT / TIMELINE / CONTENTS
- Green **Export** top-right · empty preview „Nincs tartalom a lejátszási fej alatt”
- BG-remove unchanged: Gyors/Max · paint · bake → `C:\bgcut\*_full_nobg.mov`
