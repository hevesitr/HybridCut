# HybridCut restart — nobg-layer (`2026-10-11-nobg-layer`)

Feature stamp: **`2026-10-11-nobg-layer`** (included in tip **`2026-10-11-paint-face`**).

Includes prior: `2026-10-11-concat-look` · `2026-10-11-clip-delete` · `2026-10-11-timeline-bg`.

Latest tip restart: [`paint-face-restart.md`](paint-face-restart.md).

## Pull + start (GitHub)

```powershell
cd $env:USERPROFILE\Documents\HybridCut
git pull
Get-Content .\SYNC_VERSION.txt   # 2026-10-11-nobg-layer
.\install_to_videoeditor.ps1
cd $env:USERPROFILE\Documents\Videoeditor
$env:HYBRID_RVM_ONNX = "$PWD\models\rvm_resnet50_fp32.onnx"
.\hybrid_cut\start_hybrid_cuda.ps1
# http://127.0.0.1:3847 — hard-refresh (Ctrl+F5)
# Export → Nobg a timeline-ra → Mozgatás / Pozíció X·Y / Méretérték
```

## Agent Store sync (no GitHub)

```powershell
& "$env:LOCALAPPDATA\Cursor\AgentStores\cursor_agent_stores\bc-41930eab-1501-4c19-acf3-0c9d63afbf4d\files\docs\capcut-features\sync_hybrid.ps1"
cd $env:USERPROFILE\Documents\Videoeditor
Get-Content .\hybrid_cut\SYNC_VERSION.txt   # expect: 2026-10-11-nobg-layer
.\run_hybrid.ps1
```

## Research (CapCut / Concat patterns) vs shipped MVP

| Pattern (editors) | Shipped in HybridCut |
|-------------------|----------------------|
| Import ProRes/qtrle/WebM alpha as overlay | Yes — `*_full_nobg.mov` / `nobg` stem / `.webm` → `has_alpha` |
| Place cutout on upper track (V2) | Yes — „Nobg a timeline-ra” appends V2 when clips exist |
| Drag position in preview | Yes — **Mozgatás** overlay + Pozíció X/Y % |
| Scale % (PiP) | Yes — **Méretérték** (contain-fit × scale) |
| Reset transform | Yes — **Visszaállítás** (center · 100%) |
| Preview + bake same composite | Yes — `OverlayFrame` + `place_layer_on_canvas` |
| Layer order V1 under V2 | Yes — existing FramePlan track order |
| Fit / fill modes | MVP: contain only |
| Rotation / keyframes / blend modes | **Not shipped** (out of BG-remove scope) |
| Opacity blend for plain B-roll | Kept (0.85 default); nobg stays opacity 1 |

## How to use

1. Bake cutout → green card shows `C:\bgcut\*_full_nobg.mov`.
2. Click **Nobg a timeline-ra** (V2 if timeline already has clips).
3. Select the nobg clip → **Pozíció / Méret** · enable **Mozgatás** and drag, or type X/Y/% · **Alkalmaz** / **Visszaállítás**.
4. Or open any `*_full_nobg.mov` / alpha WebM via Megnyitás / + B-roll (auto `has_alpha`).
5. Előnézet + Export bake both respect transform + embedded alpha over lower track / checker.
