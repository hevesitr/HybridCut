# HybridCut — greenfield Videoeditor

Modern hybrid cutout editor for **Róbert Hevesi-Tóth**: Concat-inspired host/timeline/prefetch/MaskStore ideas + MatAnyone2-class quality pipeline, without vendoring those codebases.

| | |
|--|--|
| SYNC | `2026-10-04-hu-ux` (see `SYNC_VERSION.txt`) |
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
# expect: 2026-10-04-hu-ux
.\run_hybrid.ps1
# open http://127.0.0.1:3847
# CUDA+cuDNN: .\hybrid_cut\start_hybrid_cuda.ps1
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

## Hungarian UX + Forrás default (this stamp)

- Preview default: **Forrás** (full source RGB) on load/scrub — not 50% wipe / alpha-only
- View toggle: **Forrás | Maszk | Cutout | Összehasonlítás** (compare wipe starts at Utána=100%)
- Weak/empty matte → source underlay + status „Maszk üres — forrás látszik”
- All control buttons/chips: short Hungarian labels + `title` tooltips
- Help line: `1) Videó betöltése 2) Előnézet 3) Exportálás`

## Phase 5 + cuDNN PATH (this stamp)

- **FastEngine** resolves RVM ONNX from `HYBRID_RVM_ONNX` / parent `models/` (prefers **fp32**)
- `hybrid_editor.cuda_path`: PATH + `os.add_dll_directory` for pip `nvidia-cudnn-cu12` **before** ORT session
- Soft fallback: CUDA/cuDNN `LoadLibrary` failure → **CPU EP** with clear status (no raw ORT crash in UI)
- `run_hybrid.ps1`: auto-install `nvidia-cudnn-cu12` when `cudnn64_*.dll` missing; PATH prepend hybrid+parent
- `start_hybrid_cuda.ps1`: CapCut `remount_ort_gpu.ps1` if sibling; pip cudnn/ort-gpu; then launch
- Workaround B: `$env:HYBRID_REUSE_PARENT_VENV='1'` (CapCut `.venv` that already works)

---

## Pip / venv notes (Windows)

- `run_hybrid.ps1` does **not** run `pip install --upgrade pip` by default. Opt-in: `$env:HYBRID_UPGRADE_PIP = "1"`.
- Deps install with `--trusted-host pypi.org --trusted-host files.pythonhosted.org` and `--no-cache-dir`.
- Force parent venv (Workaround B): `$env:HYBRID_REUSE_PARENT_VENV = "1"`.
- GPU ORT / cuDNN:

```powershell
cd $env:USERPROFILE\Documents\Videoeditor
$env:HYBRID_RVM_ONNX = "$PWD\models\rvm_mobilenetv3_fp32.onnx"
.\hybrid_cut\start_hybrid_cuda.ps1
# auto: remount if sibling + nvidia-cudnn-cu12 + PATH
# or: .\run_hybrid.ps1  (also auto-installs cudnn when DLL missing)
```

Restart cheat-sheet: [`../hybrid-cudnn-restart.md`](../hybrid-cudnn-restart.md). Hotfix paste: `PASTE_FIX_RUN_HYBRID.ps1`.

---

## Tests

```powershell
cd $env:USERPROFILE\Documents\Videoeditor\hybrid_cut
$env:PYTHONPATH = "$PWD\backend"
& .\.venv\Scripts\python.exe -m pytest backend\tests -q
```
