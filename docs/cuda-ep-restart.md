# HybridCut restart — cuda-ep (`2026-10-11-cuda-ep`) — historical

Feature stamp (historical): **`2026-10-11-cuda-ep`**.

**Tip is now [`cuda-restore-restart.md`](cuda-restore-restart.md) (`2026-10-11-cuda-restore`)** — pin `onnxruntime-gpu==1.30.0` + file-based probe (no `python -c` SyntaxError).

Includes prior: seed-crash · rvm-matte · matte-visible · person-restore · auto-person · look-peak · ai-tracks · person-fix2 · nobg-layer.

## Why CUDA EP was missing (this log)

```
[W:onnxruntime:Default, onnxruntime_pybind_state.cc:855 ...]
No registered plugin EP device found for 'CUDAExecutionProvider' with device_id=0
```

| Factor | What it means |
|--------|----------------|
| **ORT plugin EP (ort-cuda)** | Newer `onnxruntime-gpu` loads CUDA as a **plugin**. `get_available_providers()` can still *list* `CUDAExecutionProvider` while the plugin device is **not registered**. |
| **Wrong / mixed wheel** | CPU `onnxruntime` + leftover GPU bits, or mismatched CUDA/cuDNN DLLs → plugin never registers. |
| **PATH / cudnn64_9.dll** | Pip `nvidia-cudnn-cu12` not on PATH / `os.add_dll_directory` → LoadLibrary fails; EP stays unusable. |
| **Gray-slab toast** | UI correctly refused Cutout ✓ (`Hibás maszk (egyenletes szürke lap)`). Broken CUDA path still ran RVM and emitted a uniform pha. |

This stamp treats **listed ≠ registered**. If the plugin EP is missing, HybridCut uses **CPU ORT** *before* any RVM inference that would produce a gray slab.

## What we fixed

| Path | Behaviour |
|------|-----------|
| `probe_cuda_ep_usable` | Tiny Identity session + stderr/log catch for „No registered plugin EP…”. Cached per process. |
| `_OrtRvmSession` | If CUDA plugin not registered → **CPUExecutionProvider** immediately; sets `HYBRID_ORT_PROVIDER=cpu`; HU `fallback_note`. |
| Max / Gyors | Still prefer **fp32 ResNet** (Max) / MobileNet (Gyors); CPU path produces a real person matte. |
| UI chip | **CPU ORT** (warn) when plugin missing — never **RVM CUDA** / RTX claim. Status line shows install hint (HU). |
| `start_hybrid_cuda.ps1` | After PATH inject, probes providers + plugin; if fail → `HYBRID_ORT_PROVIDER=cpu` + Windows fix lines. |

Detection toast from matte-visible stays if *everything* fails. Prefer cutout **working on CPU now**; CUDA is acceleration when the EP is real.

## Pull + start (GitHub)

```powershell
cd $env:USERPROFILE\Documents\HybridCut
git pull
Get-Content .\SYNC_VERSION.txt   # 2026-10-11-cuda-ep
.\install_to_videoeditor.ps1
cd $env:USERPROFILE\Documents\Videoeditor
$env:HYBRID_RVM_ONNX = "$PWD\models\rvm_resnet50_fp32.onnx"
.\hybrid_cut\start_hybrid_cuda.ps1
# http://127.0.0.1:3847 — hard-refresh (Ctrl+F5)
# Expect chip: CPU ORT  (or RVM CUDA only if probe prints OK=1)
```

## Agent Store sync (no GitHub / no PAT)

```powershell
& "$env:LOCALAPPDATA\Cursor\AgentStores\cursor_agent_stores\bc-41930eab-1501-4c19-acf3-0c9d63afbf4d\files\docs\capcut-features\sync_hybrid.ps1"
cd $env:USERPROFILE\Documents\Videoeditor
Get-Content .\hybrid_cut\SYNC_VERSION.txt   # expect: 2026-10-11-cuda-ep
.\run_hybrid.ps1
```

Hard-refresh **Ctrl+F5**.

## Windows — make CUDA EP real (optional acceleration)

```powershell
cd $env:USERPROFILE\Documents\Videoeditor\hybrid_cut
.\.venv\Scripts\Activate.ps1
pip uninstall onnxruntime onnxruntime-gpu -y
pip install onnxruntime-gpu
pip install nvidia-cudnn-cu12
# PATH + add_dll_directory for cudnn64_9.dll:
.\start_hybrid_cuda.ps1
# or parent CapCut:
#   cd ..; .\remount_ort_gpu.ps1 -PathOnly
```

Verify:

```powershell
$env:PYTHONPATH="$PWD\backend"
python -c "from hybrid_editor.cuda_path import inject_nvidia_pip_libs, probe_cuda_ep_usable; inject_nvidia_pip_libs(); import onnxruntime as o; print(o.get_available_providers()); print(probe_cuda_ep_usable(o, use_cache=False))"
```

Expect: `OK` / `CUDA EP OK` and providers include `CUDAExecutionProvider`. Matching CUDA toolkit + cuDNN for the ORT build matters (RTX 3060 / cu12).

## UI — Róbert checklist (HU)

1. Chip: **CPU ORT** if log had plugin-EP warning — **not** RVM CUDA.
2. **Megnyitás** → Max + Éles → **Előnézet** — személy sziluett (**nem** egyszínű szürke lap).
3. Toast „Hibás maszk…” **nem** jelenik meg, ha CPU RVM jó maszkot ad.
4. Status hint mentions onnxruntime-gpu / cudnn / `start_hybrid_cuda.ps1` when CUDA missing.
5. `SYNC_VERSION` chip: **`2026-10-11-cuda-ep`**.

## Smoke

```powershell
cd hybrid_cut
$env:PYTHONPATH="$PWD\backend"
$env:HYBRID_RVM_ONNX = "$env:USERPROFILE\Documents\Videoeditor\models\rvm_resnet50_fp32.onnx"
python -m pytest backend/tests/test_cuda_ep.py backend/tests/test_rvm_matte.py backend/tests/test_cuda_path.py -q
```

## Dist

`frontend/dist`: `index-2KycPbok.js` / `index-C4rutvUi.css`
