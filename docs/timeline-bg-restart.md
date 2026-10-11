# HybridCut restart — timeline-bg (`2026-10-11-timeline-bg`)

Feature stamp: **`2026-10-11-timeline-bg`**.

Scope: multi-track timeline + background removal only (no effects/filters/text/audio mixer port).

```powershell
cd $env:USERPROFILE\Documents\HybridCut
git pull
Get-Content .\SYNC_VERSION.txt   # 2026-10-11-timeline-bg
.\install_to_videoeditor.ps1

cd $env:USERPROFILE\Documents\Videoeditor
Get-Content .\hybrid_cut\SYNC_VERSION.txt   # expect: 2026-10-11-timeline-bg
$env:HYBRID_RVM_ONNX = "$PWD\models\rvm_resnet50_fp32.onnx"
.\hybrid_cut\start_hybrid_cuda.ps1
# http://127.0.0.1:3847 — Ctrl+F5
# V1/V2 drag · Be/Ki handles · select clip · Varázsceruza · dual-track cutout preview
```

Agent Store (no GitHub):

```powershell
& "$env:LOCALAPPDATA\Cursor\AgentStores\cursor_agent_stores\bc-41930eab-1501-4c19-acf3-0c9d63afbf4d\files\docs\capcut-features\sync_hybrid.ps1"
cd $env:USERPROFILE\Documents\Videoeditor
Get-Content .\hybrid_cut\SYNC_VERSION.txt   # expect: 2026-10-11-timeline-bg
.\run_hybrid.ps1
```

## timeline-bg notes

- **V1 / V2** lanes: click clip to select (BG + seed + Varázsceruza target that clip)
- **Drag** clip body horizontally to reorder (V1) / place (V2); vertically to stack onto the other track
- **Trim handles** on clip edges = Be / Ki (also numeric Be/Ki in the rail)
- **Preview** at playhead composites V1 cutout + V2 overlays (same blend as bake)
- **Varázsceruza**: scanline flood-fill, tűrés slider, Alt+click erase; seed stored per selected clip media
