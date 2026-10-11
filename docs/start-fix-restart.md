# HybridCut restart — start-fix (`2026-10-10-start-fix`)

Feature stamp: **`2026-10-10-start-fix`**.

Fixes Windows start hang/crash when CapCut `remount_ort_gpu.ps1` runs `pip install --upgrade pip` (`OSError` access violation).

## Pull + install

```powershell
cd $env:USERPROFILE\Documents\HybridCut
git pull
Get-Content .\SYNC_VERSION.txt   # 2026-10-10-start-fix
.\install_to_videoeditor.ps1
```

## Start (no remount pip)

```powershell
cd $env:USERPROFILE\Documents\Videoeditor
Get-Content .\hybrid_cut\SYNC_VERSION.txt   # expect: 2026-10-10-start-fix
$env:HYBRID_RVM_ONNX = "$PWD\models\rvm_resnet50_fp32.onnx"
.\hybrid_cut\start_hybrid_cuda.ps1
# http://127.0.0.1:3847
```

## Immediate bypass (eta-ui already installed)

Skip CapCut remount entirely — launch HybridCut directly:

```powershell
cd $env:USERPROFILE\Documents\Videoeditor
$env:HYBRID_RVM_ONNX = "$PWD\models\rvm_resnet50_fp32.onnx"
.\run_hybrid.ps1
# or: .\hybrid_cut\run_hybrid.ps1
```

## Opt-in path-only remount

```powershell
$env:HYBRID_CALL_REMOUNT = "1"
.\hybrid_cut\start_hybrid_cuda.ps1
```

Uses path-only cudnn PATH inject (or CapCut `remount_ort_gpu.ps1 -PathOnly` if present). Never blocks on pip upgrade.
