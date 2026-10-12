> **Tip is now [`rvm-back-restart.md`](rvm-back-restart.md) (`2026-10-11-rvm-back`).**

# HybridCut restart — cpu-matte (`2026-10-11-matte-cpu2`)

Feature stamp: **`2026-10-11-matte-cpu2`**.

Includes prior: cuda-ps1 · cuda-restore · cuda-ep · seed-crash · rvm-matte · matte-visible · person-restore · auto-person · look-peak.

## What still broke after cuda-ps1 + ORT 1.30.0

| Symptom | Cause |
|---------|--------|
| Toast `Hibás maszk (egyenletes szürke lap)` | RVM `pha` all-ones / near-uniform |
| Overlay `Nincs ember-maszk` | Degenerate alpha refused (correct) but no good matte |
| Log `No registered plugin EP device found for 'CUDAExecutionProvider'` | CUDA **listed** but **plugin EP not registered** |
| Log `MemcpyTransformer` + `CUDAExecutionProvider` | Half-broken CUDA session still ran inference |
| UI badge **RTX 3060** + **Gyors** | Hardware chip hardcoded; EP not registered |

**Root cause:** probe could **soft-OK** when cuDNN DLLs were present even if the CUDA session/plugin failed. ORT then created a `[CUDA, CPU]` session that logged the plugin warning, ran MemcpyTransformer, and emitted a gray-slab `pha`. CPU fallback either never ran first, or arrived too late after a poisoned path.

Also: `onnxruntime-gpu==1.30.0` alone does not register the CUDA plugin if `ort-cuda` / matching CUDA+cuDNN DLLs are not loadable in DLL order on PATH. Morning CUDA needs the full pin + PATH inject from `start_hybrid_cuda.ps1` / `remount_ort_gpu.ps1`.

## What this stamp does (P0 = working person matte)

| Path | Behaviour |
|------|-----------|
| **No soft-OK** | Probe OK only if CUDA-only Identity session **activates** CUDA EP, runs Identity, and emits **no** plugin-EP warning. cuDNN present ≠ CUDA usable. |
| **CPU-only session** | When plugin EP missing / smoke gray-slab → destroy CUDA session; create **`["CPUExecutionProvider"]` only** (never leave CUDA in the provider list). |
| **Load smoke** | If CUDA still claimed, one synthetic person smoke matte; slab → CPU-only immediately. |
| **Előnézet / Max / Gyors** | All share `_OrtRvmSession`; when CUDA unusable they use the CPU path. |
| **UI badge** | **CPU ORT** (warn style) when EP not registered — **not** RTX 3060. **RVM CUDA** / RTX only when EP registered. |
| **Auto Max** | On open/sample, if CUDA EP unusable and mode is still Gyors → force Max + fresh RVM. |

## Sync + run (Windows)

```powershell
& "$env:LOCALAPPDATA\Cursor\AgentStores\cursor_agent_stores\bc-41930eab-1501-4c19-acf3-0c9d63afbf4d\files\docs\capcut-features\sync_hybrid.ps1"
cd $env:USERPROFILE\Documents\Videoeditor
Get-Content .\hybrid_cut\SYNC_VERSION.txt   # expect: 2026-10-11-matte-cpu2
.\hybrid_cut\start_hybrid_cuda.ps1
# http://127.0.0.1:3847 — Ctrl+F5
```

Expect console on plugin FAIL:

```
=== CUDA EP PROBE ===
OK=0
RESULT: FAIL
RESULT: FAIL - CUDA EP plugin not registered
WARN: forcing HYBRID_ORT_PROVIDER=cpu (real person matte on CPU; slower)
```

UI: topbar chip **CPU ORT** (not RTX 3060). Maszk = person silhouette (not gray slab).

## Optional: restore morning CUDA

```powershell
cd $env:USERPROFILE\Documents\Videoeditor\hybrid_cut
.\.venv\Scripts\Activate.ps1
pip uninstall onnxruntime onnxruntime-gpu -y
pip install -r backend\requirements-gpu.txt --trusted-host pypi.org --trusted-host files.pythonhosted.org --no-cache-dir
# = onnxruntime-gpu==1.30.0 + nvidia-cudnn-cu12 …
.\start_hybrid_cuda.ps1
# Expect OK=1 / RESULT: OK and chip RVM CUDA / RTX 3060
```

DLL load order: `start_hybrid_cuda.ps1` prepends `site-packages\nvidia\*\bin` (cudnn, cublas, cuda_runtime) to PATH **before** ORT import. Prefer **`onnxruntime-gpu==1.30.0`** (not 1.31.x). Do not mix CPU `onnxruntime` with GPU wheel in the same venv.

## Why CUDA may still fail with 1.30 + cudnn

1. Plugin EP (`ort-cuda`) not loaded — listed in `get_available_providers()` is not registration.
2. Wrong wheel / mixed `onnxruntime` + `onnxruntime-gpu`.
3. cuDNN DLL on disk but not on PATH before first `import onnxruntime`.
4. Soft-OK (removed this stamp) previously hid (1)–(3).

Until probe `OK=1`, HybridCut must stay on **CPU ORT** for a real person matte.

## Smoke

```powershell
cd hybrid_cut
$env:PYTHONPATH="$PWD\backend"
$env:HYBRID_ORT_PROVIDER="cpu"
python -m pytest backend/tests/test_cpu_matte.py backend/tests/test_cuda_ep.py backend/tests/test_rvm_matte.py -q
```

## Dist

`frontend/dist`: `index-CLu0f9Hu.js` / `index-Bv2GNnfq.css`. Hard-refresh **Ctrl+F5**.
