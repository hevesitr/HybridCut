# HybridCut restart — look2 (`2026-10-10-look2`)

Feature stamp: **`2026-10-10-look2`**.

Includes prior: `2026-10-10-look` · `2026-10-10-layout-fix` · `2026-10-10-start-fix` · `2026-10-10-eta-ui` · apex · peak · continue · ui-nobg.

## Pull + start (GitHub)

```powershell
cd $env:USERPROFILE\Documents\HybridCut
git pull
Get-Content .\SYNC_VERSION.txt   # 2026-10-10-look2
.\install_to_videoeditor.ps1
cd $env:USERPROFILE\Documents\Videoeditor
$env:HYBRID_RVM_ONNX = "$PWD\models\rvm_resnet50_fp32.onnx"
.\hybrid_cut\start_hybrid_cuda.ps1
# http://127.0.0.1:3847 — hard-refresh (Ctrl+F5)
# Full-bleed empty: topbar + CTA row + rail chips + drop stage (no skinny column)
```

## Agent Store sync (no GitHub)

```powershell
& "$env:LOCALAPPDATA\Cursor\AgentStores\cursor_agent_stores\bc-41930eab-1501-4c19-acf3-0c9d63afbf4d\files\docs\capcut-features\sync_hybrid.ps1"
cd $env:USERPROFILE\Documents\Videoeditor
Get-Content .\hybrid_cut\SYNC_VERSION.txt   # expect: 2026-10-10-look2
.\run_hybrid.ps1
```

## look2 notes

- Empty state = same full-bleed shell as editor (100vw topbar + workspace)
- Full-width open CTA row (Megnyitás / Minta)
- Gyors/Max as slim horizontal chips in left rail — not a 400px column in void
- Syne / Figtree · lime `#b8f000` · orange `#ff7a1a` retained
- Removed `min(720px)` centered marketing column
