# HybridCut restart — clip-delete (`2026-10-11-clip-delete`)

Feature stamp: **`2026-10-11-clip-delete`**.

Scope: restore visible concat/apex clip tools — delete / duplicate / cut / reorder / track move.

```powershell
cd $env:USERPROFILE\Documents\HybridCut
git pull
Get-Content .\SYNC_VERSION.txt   # 2026-10-11-clip-delete
.\install_to_videoeditor.ps1

cd $env:USERPROFILE\Documents\Videoeditor
Get-Content .\hybrid_cut\SYNC_VERSION.txt   # expect: 2026-10-11-clip-delete
$env:HYBRID_RVM_ONNX = "$PWD\models\rvm_resnet50_fp32.onnx"
.\hybrid_cut\start_hybrid_cuda.ps1
# http://127.0.0.1:3847 — Ctrl+F5
# Klip lista → Töröl · or Duplikál/Töröl next to Be/Ki · Delete key
```

Agent Store (no GitHub):

```powershell
& "$env:LOCALAPPDATA\Cursor\AgentStores\cursor_agent_stores\bc-41930eab-1501-4c19-acf3-0c9d63afbf4d\files\docs\capcut-features\sync_hybrid.ps1"
cd $env:USERPROFILE\Documents\Videoeditor
Get-Content .\hybrid_cut\SYNC_VERSION.txt   # 2026-10-11-clip-delete
.\run_hybrid.ps1
```

## clip-delete notes

- **Töröl** on every Klip lista row (disabled only for the last V1)
- Toolbar under Be/Ki: Duplikál · Töröl · Vágás · ← → · → B-roll · → V1
- **Delete / Backspace** removes the selected clip (ignored while typing in inputs)
- Last V1 cannot be removed (HU error: „Az utolsó V1 klip nem törölhető”)
