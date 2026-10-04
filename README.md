# HybridCut — greenfield Videoeditor

Modern hybrid cutout editor for **Róbert Hevesi-Tóth**: Concat-inspired host/timeline/prefetch/MaskStore ideas + MatAnyone2-class quality pipeline, without vendoring those codebases.

| | |
|--|--|
| SYNC | `2026-10-04-hybrid-phase5-rvm` (see `SYNC_VERSION.txt`) |
| Sync target | `%USERPROFILE%\Documents\Videoeditor\hybrid_cut` |
| CapCut root | `%USERPROFILE%\Documents\Videoeditor` + root `run_hybrid.ps1` |
| Stack | **Python FastAPI** engines + **Vite/React** UI |
| Modes | **Gyors** (ORT RVM scrub) · **Max** (seed + quality bake / MatAnyone2 adapter) |
| Target | Windows + NVIDIA RTX 3060 8GB · local / free only |
| GitHub | https://github.com/hevesitr/HybridCut |

Architecture plan: [`../hybrid-editor-plan.md`](../hybrid-editor-plan.md)

---

## License blockers (read first)

| Piece | License | Policy |
|-------|---------|--------|
| **MatAnyone2** weights / upstream | **S-Lab 1.0 — non-commercial** | Adapter only. Set `HYBRID_MATANYONE2_WEIGHTS`. **We do not redistribute weights.** |
| **Concat** | AGPL-3.0 | Ideas only — **no Concat source** |
| **RVM ONNX** | Upstream-dependent | Opt-in: parent `Documents\Videoeditor\models\*.onnx`, `scripts/download_rvm.ps1`, or `HYBRID_RVM_ONNX` |
| Our hybrid code | MIT (this tree) | See NOTICE |

Without RVM ONNX, **Gyors** uses a documented OpenCV GrabCut/center **heuristic fallback** (demo/CI — not ML quality).

---

## Confirmed working start (Windows PowerShell)

User-confirmed while UI already served on `:3847`:

```powershell
cd hybrid_cut
$env:PYTHONPATH="$PWD\backend"
& .\.venv\Scripts\python.exe -m hybrid_editor.main
```

From CapCut root after install/sync:

```powershell
cd $env:USERPROFILE\Documents\Videoeditor
Get-Content .\hybrid_cut\SYNC_VERSION.txt
# expect: 2026-10-04-hybrid-phase5-rvm
.\run_hybrid.ps1
# open http://127.0.0.1:3847
```

One-click from Agent Store:

```powershell
& "$env:LOCALAPPDATA\Cursor\AgentStores\cursor_agent_stores\bc-41930eab-1501-4c19-acf3-0c9d63afbf4d\files\docs\capcut-features\sync_hybrid.ps1"
cd $env:USERPROFILE\Documents\Videoeditor
.\run_hybrid.ps1
```

GitHub clone into CapCut folder:

```powershell
cd $env:USERPROFILE\Documents
git clone https://github.com/hevesitr/HybridCut.git
cd HybridCut
.\install_to_videoeditor.ps1
cd $env:USERPROFILE\Documents\Videoeditor
.\run_hybrid.ps1
```

---

## Phase 5 (this stamp)

- **FastEngine** resolves RVM ONNX from `HYBRID_RVM_ONNX` / `VIDEOEDITOR_RVM_ONNX` / hybrid `models/` / **parent** `Documents\Videoeditor\models\*.onnx`
- `run_hybrid.ps1`: skip pip upgrade; trusted-host; auto parent RVM; reuse parent `.venv` when hybrid pip/venv is weak (`Documents\Videoeditor\.venv`)
- `install_to_videoeditor.ps1`: ASCII robolog + root launcher before cleanup (shipped)
- UI: clearer first-run empty state + **RVM/CUDA/ORT** status chips; before/after wipe; bake queue; **open output folder**
- Export: audio AAC mux confirmed; `/api/export/open-folder` + Explorer button

---

## Pip / venv notes (Windows)

- `run_hybrid.ps1` does **not** run `pip install --upgrade pip` by default. Opt-in: `$env:HYBRID_UPGRADE_PIP = "1"`.
- Deps install with `--trusted-host pypi.org --trusted-host files.pythonhosted.org` and `--no-cache-dir`.
- Force parent venv: `$env:HYBRID_REUSE_PARENT_VENV = "1"`.
- GPU ORT (parent CapCut path):

```powershell
cd $env:USERPROFILE\Documents\Videoeditor
.\setup_gpu.ps1
# or .\remount_ort_gpu.ps1
# then HybridCut can reuse ..\Videoeditor\.venv via run_hybrid.ps1 fallback
```

Hotfix paste: `PASTE_FIX_RUN_HYBRID.ps1`.

---

## Tests

```powershell
cd $env:USERPROFILE\Documents\Videoeditor\hybrid_cut
$env:PYTHONPATH = "$PWD\backend"
& .\.venv\Scripts\python.exe -m pytest backend\tests -q
```
