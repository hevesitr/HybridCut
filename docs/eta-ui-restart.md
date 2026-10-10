# HybridCut restart — eta-ui (`2026-10-10-eta-ui`)

Feature stamp: **`2026-10-10-eta-ui`**.

Includes prior: `2026-10-10-apex` · `2026-10-10-peak` · `2026-10-10-continue` · `2026-10-05-ui-nobg`.

## After pull / sync

```powershell
cd $env:USERPROFILE\Documents\HybridCut
git pull
Get-Content .\SYNC_VERSION.txt   # 2026-10-10-eta-ui
.\install_to_videoeditor.ps1
cd $env:USERPROFILE\Documents\Videoeditor
$env:HYBRID_RVM_ONNX = "$PWD\models\rvm_resnet50_fp32.onnx"
.\hybrid_cut\start_hybrid_cuda.ps1
# http://127.0.0.1:3847
# Mode cards show Gyors + Max ETA · Export gombon is · bake közben „Hátravan …”
```

Agent Store (no GitHub):

```powershell
& "$env:LOCALAPPDATA\Cursor\AgentStores\cursor_agent_stores\bc-41930eab-1501-4c19-acf3-0c9d63afbf4d\files\docs\capcut-features\sync_hybrid.ps1"
cd $env:USERPROFILE\Documents\Videoeditor
Get-Content .\hybrid_cut\SYNC_VERSION.txt   # expect: 2026-10-10-eta-ui
.\run_hybrid.ps1
```

## What changed (eta-ui vs apex)

| Area | Behavior |
|------|----------|
| ETA upfront | Gyors + Max háttéreltávolítás estimates on mode cards + export strip |
| Live | Updates when Be/Ki, clip, fps, resolution change |
| Bake | Remaining ETA from `N/M frame` (else progress %) |
| UX | CapCut-clean 1-2-3 flow; timeline/tech under Részletek |
| Quality | Apex APEX_SPEC / export path unchanged |
