# start_hybrid_cuda.ps1 - HybridCut CUDA prep + launch (ASCII-only)
# Pattern: call CapCut remount_ort_gpu.ps1 if sibling Videoeditor has it;
# auto-install nvidia-cudnn-cu12 into hybrid (or parent) venv; PATH inject;
# prefer parent Videoeditor .venv optionally; then run_hybrid.ps1.
#
# Usage (from hybrid_cut or Documents\Videoeditor):
#   .\start_hybrid_cuda.ps1
#   .\start_hybrid_cuda.ps1 -ReuseParentVenv
#   .\start_hybrid_cuda.ps1 -SkipRemount
#   .\start_hybrid_cuda.ps1 -InstallOnly

param(
    [switch]$ReuseParentVenv,
    [switch]$SkipRemount,
    [switch]$InstallOnly
)

$ErrorActionPreference = "Stop"

$scriptDir = if ($PSScriptRoot) { $PSScriptRoot } else { Split-Path -Parent $MyInvocation.MyCommand.Path }
$nestedUnderCapCut = Join-Path $env:USERPROFILE "Documents\Videoeditor\hybrid_cut"
$docsVe = Join-Path $env:USERPROFILE "Documents\Videoeditor"

$Root = $null
foreach ($cand in @($scriptDir, $nestedUnderCapCut)) {
    if (Test-Path -LiteralPath (Join-Path $cand "backend\requirements.txt")) {
        $Root = $cand
        break
    }
}
if (-not $Root) {
    Write-Host "ERROR: HybridCut tree not found (backend\requirements.txt)."
    exit 1
}

Set-Location -LiteralPath $Root
$parentRoot = Split-Path -Parent $Root
if (-not ($parentRoot -and (Test-Path -LiteralPath (Join-Path $parentRoot "run_gpu.ps1")))) {
    if (Test-Path -LiteralPath $docsVe) { $parentRoot = $docsVe }
}

Write-Host "=== HybridCut CUDA start ==="
Write-Host ("Root: " + $Root)
Write-Host ("Parent: " + $parentRoot)

$pipTrusted = @("--trusted-host", "pypi.org", "--trusted-host", "files.pythonhosted.org")
$pipNoCache = @("--no-cache-dir")

# Resolve python: hybrid .venv or parent CapCut .venv
$hybridPy = Join-Path $Root ".venv\Scripts\python.exe"
$parentPy = Join-Path $parentRoot ".venv\Scripts\python.exe"
$docsPy = Join-Path $docsVe ".venv\Scripts\python.exe"
$venvPy = $null
if ($ReuseParentVenv -or $env:HYBRID_REUSE_PARENT_VENV -eq "1") {
    foreach ($cand in @($parentPy, $docsPy, $hybridPy)) {
        if (Test-Path -LiteralPath $cand) { $venvPy = $cand; break }
    }
    $env:HYBRID_REUSE_PARENT_VENV = "1"
    Write-Host "HYBRID_REUSE_PARENT_VENV=1 (prefer parent CapCut .venv)"
} else {
    foreach ($cand in @($hybridPy, $parentPy, $docsPy)) {
        if (Test-Path -LiteralPath $cand) { $venvPy = $cand; break }
    }
}
if (-not $venvPy) {
    Write-Host "WARN: no .venv python yet - run_hybrid.ps1 will create hybrid .venv."
}

# 1) CapCut remount when available (installs ort-gpu + cudnn into parent .venv)
$remount = Join-Path $parentRoot "remount_ort_gpu.ps1"
if (-not $SkipRemount) {
    if (Test-Path -LiteralPath $remount) {
        Write-Host "Calling sibling CapCut remount_ort_gpu.ps1 ..."
        & $remount
        if ($LASTEXITCODE -ne 0) {
            Write-Host "WARN: remount_ort_gpu.ps1 failed - will try pip into active venv."
        }
    } else {
        Write-Host ("No remount_ort_gpu.ps1 at " + $remount + " - skip remount.")
    }
} else {
    Write-Host "SkipRemount=1"
}

# 2) Ensure cudnn + ort-gpu in active venv when python exists
if ($venvPy) {
    Write-Host ("Python: " + $venvPy)
    $ortOk = & $venvPy -c "import importlib.util; print('1' if importlib.util.find_spec('onnxruntime') else '0')" 2>$null
    if ($ortOk -ne "1") {
        Write-Host "Installing onnxruntime-gpu ..."
        & $venvPy -m pip install "onnxruntime-gpu>=1.16.0,<2" @pipTrusted @pipNoCache
    }
    $site = Join-Path (Split-Path -Parent (Split-Path -Parent $venvPy)) "Lib\site-packages"
    $hasDll = $false
    if (Test-Path -LiteralPath $site) {
        $hit = Get-ChildItem -LiteralPath $site -Filter "cudnn64_*.dll" -Recurse -ErrorAction SilentlyContinue | Select-Object -First 1
        if ($hit) { $hasDll = $true }
    }
    if (-not $hasDll) {
        Write-Host "Installing nvidia-cudnn-cu12 (+ cublas/cudart/nvrtc) ..."
        & $venvPy -m pip install `
            "nvidia-cudnn-cu12>=9.0.0" `
            "nvidia-cublas-cu12>=12.0.0" `
            "nvidia-cuda-runtime-cu12>=12.0.0" `
            "nvidia-cuda-nvrtc-cu12>=12.0.0" `
            @pipTrusted @pipNoCache
        if ($LASTEXITCODE -ne 0) {
            Write-Host "WARN: nvidia pip wheels failed. CapCut remount or Workaround B (parent venv)."
        }
    } else {
        Write-Host ("cuDNN DLL present under " + $site)
    }
}

# 3) Prefer fp32 RVM if present and unset
if (-not $env:HYBRID_RVM_ONNX) {
    foreach ($dir in @(
        (Join-Path $Root "models"),
        (Join-Path $parentRoot "models"),
        (Join-Path $docsVe "models")
    )) {
        if (-not (Test-Path -LiteralPath $dir)) { continue }
        $fp32 = Join-Path $dir "rvm_mobilenetv3_fp32.onnx"
        if (Test-Path -LiteralPath $fp32) {
            $env:HYBRID_RVM_ONNX = $fp32
            Write-Host ("HYBRID_RVM_ONNX <= " + $fp32)
            break
        }
    }
}

if (-not $env:HYBRID_ORT_PROVIDER) {
    $env:HYBRID_ORT_PROVIDER = "cuda"
}

if ($InstallOnly) {
    Write-Host "InstallOnly: CUDA/cuDNN prep done. Run .\run_hybrid.ps1 next."
    exit 0
}

# 4) Launch (run_hybrid.ps1 PATH-injects nvidia bins again + soft CPU fallback in Python)
$launcher = Join-Path $Root "run_hybrid.ps1"
if (-not (Test-Path -LiteralPath $launcher)) {
    $launcher = Join-Path $parentRoot "run_hybrid.ps1"
}
if (-not (Test-Path -LiteralPath $launcher)) {
    Write-Host "ERROR: run_hybrid.ps1 not found"
    exit 1
}
Write-Host ("Launching: " + $launcher)
& $launcher
