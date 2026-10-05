# HybridCut restart — UI polish + visible nobg

Feature stamp: **`2026-10-05-ui-nobg`**.

Includes prior: `2026-10-05-paint-fix` · `2026-10-05-bgcut-mov` · `2026-10-05-rvm-state`.

## After pull / sync

```powershell
cd $env:USERPROFILE\Documents\HybridCut
git pull
Get-Content .\SYNC_VERSION.txt   # 2026-10-05-ui-nobg
.\install_to_videoeditor.ps1
cd $env:USERPROFILE\Documents\Videoeditor
$env:HYBRID_RVM_ONNX = "$PWD\models\rvm_resnet50_fp32.onnx"
.\hybrid_cut\start_hybrid_cuda.ps1
# http://127.0.0.1:3847
```

Agent Store (no GitHub):

```powershell
& "$env:LOCALAPPDATA\Cursor\AgentStores\cursor_agent_stores\bc-41930eab-1501-4c19-acf3-0c9d63afbf4d\files\docs\capcut-features\sync_hybrid.ps1"
cd $env:USERPROFILE\Documents\Videoeditor
Get-Content .\hybrid_cut\SYNC_VERSION.txt   # expect: 2026-10-05-ui-nobg
.\run_hybrid.ps1
```

## How you see transparent nobg

1. Load clip → **Előnézet** → **Exportálás hanggal** (full In/Out).
2. Progress bar only while baking. At 100% it **flips** to the green result card:
   - Eyebrow: **Átlátszó nobg kész**
   - Full path: `C:\bgcut\{stem}_full_nobg.mov`
   - In-app video on **checker** = `_preview.mp4` (H.264 checker composite — Chrome can play this)
   - **Megnyitás Explorerben** selects the `.mov` (NLE master; ProRes/qtrle may not play in Chrome)
3. If mux failed: red **Export sikertelen** — set `$env:FFMPEG_PATH = "C:\ffmpeg\bin\ffmpeg.exe"` and re-export. Do **not** use `C:\bgcut\alpha\` (off by default).

## Files on disk

| File | Role |
|------|------|
| `C:\bgcut\{stem}_full_nobg.mov` | Master alpha for Premiere / Resolve |
| `C:\bgcut\{stem}_full_nobg_preview.mp4` | Checker + optional AAC — UI preview |

## Note on multi-person BG leftovers

If a second subject still shows a solid dark plate in the live Cutout view, that is matte coverage (run **Max** + **Éles szélek**, or paint with Ecset/Varázsceruza). The export result card still shows the baked alpha MOV / checker preview once bake finishes.
