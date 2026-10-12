# HybridCut restart — cuda-restore (`2026-10-11-cuda-restore`)

Feature stamp: **`2026-10-11-cuda-restore`**.


> **Tip is now [`rvm-back-restart.md`](rvm-back-restart.md) (`2026-10-11-rvm-back`)** — CPU-first launch; CUDA only after hard probe; soft person alpha accepted; clear sticky toast.

Includes prior: cuda-ep · seed-crash · rvm-matte · matte-visible · person-restore · auto-person · look-peak · ai-tracks · person-fix2 · nobg-layer.

## Morning → bad (honest timeline)

| When | What happened |
|------|----------------|
| **Morning** | Person cutout worked on RTX 3060 with **`onnxruntime-gpu==1.30.0`** and a real CUDA EP matte. |
| **Wand / paint / sticky seed** | Wand-era MaskStore scraps + seed UI debt made cutout look broken (face scraps, sticky seed). Later stamps removed wand/paint UI and fixed `setShowLargeSeed` crash. |
| **Gray-slab detection** | **matte-visible / rvm-matte**: uniform gray Maszk correctly refused (`Hibás maszk`). Root cause was often broken CUDA path / fp16 / MemcpyTransformer — not “missing toast”. |
| **cuda-ep stamp** | ORT log: `No registered plugin EP device found for 'CUDAExecutionProvider'`. Listed CUDA ≠ registered plugin. Stamp forced **CPU ORT** before gray-slab RVM. Docs said `pip install onnxruntime-gpu` **unpinned**. |
| **After reinstall** | Pip pulled **1.31.0**. Plugin EP still missing → probe/CPU path; morning-like CUDA gone. |
| **Wrong path tip** | From inside `Documents\Videoeditor\hybrid_cut`, `.\hybrid_cut\start_hybrid_cuda.ps1` → path not found. Correct: `.\start_hybrid_cuda.ps1`. |
| **Probe SyntaxError** | `start_hybrid_cuda.ps1` passed multiline Python via `python -c` → PowerShell quoting → `File "<string>", line 2` SyntaxError. Fixed: **`scripts\probe_cuda_ep.py`**. |

## What this stamp restores

| Path | Behaviour |
|------|-----------|
| **ORT pin** | Prefer **`onnxruntime-gpu==1.30.0`** (`backend/requirements-gpu.txt`). Auto-install/reinstall when missing or ≠ 1.30.0. |
| **Probe file** | `scripts/probe_cuda_ep.py` + `scripts/ort_version.py` — no `python -c` multiline. Prints `OK=1` / `OK=0`, `RESULT=OK` / `RESULT=FAIL`. |
| **start_hybrid_cuda.ps1** | Clear cwd tip; PATH/cuDNN inject; pin; probe; **RESULT: OK** keeps CUDA, **RESULT: FAIL** → `HYBRID_ORT_PROVIDER=cpu`. |
| **CPU fallback** | Still forced if plugin EP missing after pin — real person matte on CPU (slower); keeps **fp32** ResNet/MobileNet + CUDA→CPU slab recovery from rvm-matte. |
| **MemcpyTransformer** | If CUDA EP is half-broken, ORT may log MemcpyTransformer then emit gray pha — probe FAIL avoids that path. |
| **UI** | Chip **RVM CUDA** only when EP registered; else **CPU ORT** + install hint with `==1.30.0`. |

## Correct PowerShell (cwd)

**From CapCut root (`Documents\Videoeditor`):**

```powershell
cd $env:USERPROFILE\Documents\Videoeditor
.\hybrid_cut\start_hybrid_cuda.ps1
# or: .\run_hybrid.ps1
```

**From inside hybrid_cut:**

```powershell
cd $env:USERPROFILE\Documents\Videoeditor\hybrid_cut
.\start_hybrid_cuda.ps1
# NOT: .\hybrid_cut\start_hybrid_cuda.ps1   ← path not found
```

Expect console:

```
=== CUDA EP PROBE ===
ORT_VERSION=1.30.0
PIN=1.30.0
PIN_OK=1
LISTED=1
OK=1
RESULT=OK
RESULT: OK — CUDA EP registered (morning-like path)
```

If `OK=0` / `RESULT: FAIL` → CPU ORT (still usable cutout).

## pip — morning CUDA pin

```powershell
cd $env:USERPROFILE\Documents\Videoeditor\hybrid_cut
.\.venv\Scripts\Activate.ps1
pip uninstall onnxruntime onnxruntime-gpu -y
pip install -r backend\requirements-gpu.txt --trusted-host pypi.org --trusted-host files.pythonhosted.org --no-cache-dir
# = onnxruntime-gpu==1.30.0 + nvidia-cudnn-cu12 …
.\start_hybrid_cuda.ps1
```

Do **not** leave 1.31.x if plugin EP is missing.

## Agent Store sync (no GitHub / no PAT)

```powershell
& "$env:LOCALAPPDATA\Cursor\AgentStores\cursor_agent_stores\bc-41930eab-1501-4c19-acf3-0c9d63afbf4d\files\docs\capcut-features\sync_hybrid.ps1"
cd $env:USERPROFILE\Documents\Videoeditor
Get-Content .\hybrid_cut\SYNC_VERSION.txt   # expect: 2026-10-11-cuda-restore
.\hybrid_cut\start_hybrid_cuda.ps1
# http://127.0.0.1:3847 — Ctrl+F5
```

## Pull + start (GitHub)

```powershell
cd $env:USERPROFILE\Documents\HybridCut
git pull
Get-Content .\SYNC_VERSION.txt   # 2026-10-11-cuda-restore
.\install_to_videoeditor.ps1
cd $env:USERPROFILE\Documents\Videoeditor
$env:HYBRID_RVM_ONNX = "$PWD\models\rvm_resnet50_fp32.onnx"
.\hybrid_cut\start_hybrid_cuda.ps1
```

## UI — Róbert checklist (HU)

1. Sync chip: **`2026-10-11-cuda-restore`**.
2. Probe **RESULT: OK** → chip **RVM CUDA**; person silhouette (not gray slab).
3. Probe **FAIL** → chip **CPU ORT**; still real person matte (slower).
4. Toast „Hibás maszk…” only if matte truly degenerate.
5. Hard-refresh **Ctrl+F5** after sync.

## Smoke

```powershell
cd hybrid_cut
$env:PYTHONPATH="$PWD\backend"
python scripts\probe_cuda_ep.py
python -m pytest backend/tests/test_cuda_ep.py backend/tests/test_cuda_path.py backend/tests/test_rvm_matte.py -q
```

## Dist

`frontend/dist`: `index-D7Y29Lxp.js` / `index-CzWQ2bcp.css`
