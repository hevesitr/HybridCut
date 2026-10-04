# HybridCut restart — cuDNN + alpha preview (Windows)

Stamp: **`2026-10-04-person-matte`**

Includes:

1. cuDNN / CUDA PATH soft-fallback (`2026-10-04-hybrid-cudnn-path`)
2. **Transparency UX** — subtle checker when a real matte exists
3. **Empty / weak matte → source visible** — upload/scrub shows source RGB (not pure checker)
4. **Hungarian UX** — Forrás | Maszk | Cutout | Összehasonlítás; minden gomb HU + tooltip; alapnézet = Forrás
5. **Person matte** — Max without MatAnyone2 → RVM ember-maszk; Előnézet → Cutout; kézi csak finomítás

---

## Pull + verify transparency (recommended)

### Already cloned `Documents\HybridCut`

```powershell
cd $env:USERPROFILE\Documents\HybridCut
git pull
Get-Content .\SYNC_VERSION.txt
# expect: 2026-10-04-person-matte

.\install_to_videoeditor.ps1

cd $env:USERPROFILE\Documents\Videoeditor
Get-Content .\hybrid_cut\SYNC_VERSION.txt
# expect: 2026-10-04-person-matte

$env:HYBRID_RVM_ONNX = "$PWD\models\rvm_mobilenetv3_fp32.onnx"
.\hybrid_cut\start_hybrid_cuda.ps1
# open http://127.0.0.1:3847
```

### CapCut tree only (`Videoeditor\hybrid_cut`)

If you sync Agent Store / copy tree instead of GitHub:

```powershell
cd $env:USERPROFILE\Documents\Videoeditor\hybrid_cut
Get-Content .\SYNC_VERSION.txt
# expect: 2026-10-04-person-matte
$env:HYBRID_RVM_ONNX = "$env:USERPROFILE\Documents\Videoeditor\models\rvm_mobilenetv3_fp32.onnx"
.\start_hybrid_cuda.ps1
```

### UI checks after open

1. Chip: **RVM CUDA** (not CUDA→CPU)
2. After upload (no bake yet) → **video frame visible** immediately (badge „nincs maszk” OK) — never full-stage checker only
3. With a real matte → cutout shows **subject over soft dark checker** (#2a2a2a / #353535)
4. **Előtte / Utána** empty → source / source; with matte → alpha / cutout
5. **Max seed paint** → **video frame under** amber mask

---

## A — CUDA launcher (fp32 + auto PATH/cuDNN)

```powershell
cd $env:USERPROFILE\Documents\Videoeditor
$env:HYBRID_RVM_ONNX = "$PWD\models\rvm_mobilenetv3_fp32.onnx"
.\hybrid_cut\start_hybrid_cuda.ps1
# open http://127.0.0.1:3847
```

---

## B — Workaround: CapCut parent venv

```powershell
cd $env:USERPROFILE\Documents\Videoeditor
$env:HYBRID_REUSE_PARENT_VENV = "1"
$env:HYBRID_RVM_ONNX = "$PWD\models\rvm_mobilenetv3_fp32.onnx"
$env:HYBRID_ORT_PROVIDER = "cuda"
.\run_hybrid.ps1
```

---

## Soft CPU fallback

If CUDA EP fails, HybridCut retries CPU and shows `CUDA→CPU: …` in status (UI stays up).

```powershell
$env:HYBRID_ORT_PROVIDER = "cpu"
.\run_hybrid.ps1
```

---

## GPU verify (RTX 3060 — local only)

```powershell
cd $env:USERPROFILE\Documents\Videoeditor\hybrid_cut
$env:PYTHONPATH = "$PWD\backend"
& .\.venv\Scripts\python.exe -c @"
from hybrid_editor.cuda_path import inject_nvidia_pip_libs, pip_cudnn_present
inject_nvidia_pip_libs()
print(pip_cudnn_present())
import onnxruntime as ort
print(ort.get_available_providers())
"@
```

Expect providers include `CUDAExecutionProvider`.
