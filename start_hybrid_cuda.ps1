# start_hybrid_cuda.ps1 - HybridCut CUDA prep + launch (ASCII-only)
# Default: do NOT call CapCut remount_ort_gpu.ps1 (its pip upgrade can hit Windows
# OSError access violation). Inject nvidia cudnn/cublas PATH from hybrid + parent
# site-packages, then launch run_hybrid.ps1 without blocking on remount.
#
# Opt-in CapCut remount (path-only / skip pip upgrade):
#   $env:HYBRID_CALL_REMOUNT = "1"
# Legacy: -SkipRemount is default behavior (kept for callers).
#
# Usage (from hybrid_cut or Documents\Videoeditor):
#   .\start_hybrid_cuda.ps1
#   .\start_hybrid_cuda.ps1 -ReuseParentVenv
#   .\start_hybrid_cuda.ps1 -InstallOnly
#   $env:HYBRID_CALL_REMOUNT = "1"; .\start_hybrid_cuda.ps1

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
Write-Host "Stamp: 2026-10-11-timeline-bg (no remount pip upgrade by default)"

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
if ($venvPy) {
    Write-Host ("Python: " + $venvPy)
} else {
    Write-Host "WARN: no .venv python yet - run_hybrid.ps1 will create hybrid .venv."
}

$siteHybrid = Join-Path $Root ".venv\Lib\site-packages"
$parentSite = Join-Path $parentRoot ".venv\Lib\site-packages"
$docsVeSite = Join-Path $docsVe ".venv\Lib\site-packages"

# PATH-only remount: prepend pip nvidia cudnn/cublas bins (no pip upgrade).
function Add-NvidiaPipBinsToPath {
    param([string[]]$SiteRoots)
    $added = 0
    foreach ($site in $SiteRoots) {
        if (-not $site -or -not (Test-Path -LiteralPath $site)) { continue }
        $nv = Join-Path $site "nvidia"
        if (-not (Test-Path -LiteralPath $nv)) { continue }
        Get-ChildItem -LiteralPath $nv -Directory -ErrorAction SilentlyContinue | ForEach-Object {
            foreach ($sub in @("bin", "lib")) {
                $d = Join-Path $_.FullName $sub
                if (Test-Path -LiteralPath $d) {
                    $env:PATH = $d + [IO.Path]::PathSeparator + $env:PATH
                    Write-Host ("PATH += " + $d)
                    $added++
                }
            }
        }
        $dlls = Get-ChildItem -LiteralPath $nv -Filter "cudnn64_*.dll" -Recurse -ErrorAction SilentlyContinue
        foreach ($dll in $dlls) {
            $env:PATH = $dll.DirectoryName + [IO.Path]::PathSeparator + $env:PATH
            Write-Host ("cudnn DLL: " + $dll.FullName)
            $added++
        }
    }
    return $added
}

function Invoke-PathOnlyRemount {
    param(
        [string]$ParentRoot,
        [string[]]$SiteRoots
    )
    Write-Host "Path-only remount (skip pip upgrade) ..."
    $n = Add-NvidiaPipBinsToPath -SiteRoots $SiteRoots
    if ($n -le 0) {
        Write-Host "WARN: no nvidia cudnn bins under hybrid/parent site-packages yet."
        Write-Host "  run_hybrid.ps1 may auto-install nvidia-cudnn-cu12 (no pip upgrade)."
        Write-Host "  Workaround B: `$env:HYBRID_REUSE_PARENT_VENV='1'; .\run_hybrid.ps1"
    } else {
        Write-Host ("PATH inject done (" + $n + " entries).")
    }
    if (-not $env:VIDEOEDITOR_ORT_PROVIDER) {
        $env:VIDEOEDITOR_ORT_PROVIDER = "cuda"
    }
    Write-Host "VIDEOEDITOR_ORT_PROVIDER=cuda (path-only; no CapCut pip remount)"
}

# 1) Default: path-only. Never block on CapCut remount pip upgrade.
#    Opt-in CapCut remount only when HYBRID_CALL_REMOUNT=1; still skip pip upgrade
#    (path-only local remount, or CapCut remount -PathOnly / -SkipPipUpgrade if present).
$callRemount = ($env:HYBRID_CALL_REMOUNT -eq "1") -and (-not $SkipRemount)
$remount = Join-Path $parentRoot "remount_ort_gpu.ps1"

if ($callRemount) {
    Write-Host "HYBRID_CALL_REMOUNT=1 - safe remount (skip pip upgrade) ..."
    $usedCapCutSafe = $false
    if (Test-Path -LiteralPath $remount) {
        # Prefer CapCut remount path-only switches when available (ASCII param names).
        $remountText = Get-Content -LiteralPath $remount -Raw -ErrorAction SilentlyContinue
        if ($remountText -match "PathOnly|SkipPipUpgrade") {
            Write-Host ("Calling CapCut remount with skip-pip: " + $remount)
            $prevEap = $ErrorActionPreference
            $ErrorActionPreference = "Continue"
            try {
                if ($remountText -match "PathOnly") {
                    & $remount -PathOnly
                } else {
                    & $remount -SkipPipUpgrade
                }
                if ($LASTEXITCODE -eq 0) { $usedCapCutSafe = $true }
                else {
                    Write-Host ("WARN: CapCut remount exit=" + $LASTEXITCODE + " - continuing with path-only.")
                }
            } catch {
                Write-Host ("WARN: CapCut remount failed - continuing with path-only. " + $_.Exception.Message)
            } finally {
                $ErrorActionPreference = $prevEap
            }
        } else {
            Write-Host "CapCut remount_ort_gpu.ps1 has no PathOnly/SkipPipUpgrade - skip calling it (avoids pip AV)."
        }
    } else {
        Write-Host ("No remount_ort_gpu.ps1 at " + $remount)
    }
    if (-not $usedCapCutSafe) {
        Invoke-PathOnlyRemount -ParentRoot $parentRoot -SiteRoots @($siteHybrid, $parentSite, $docsVeSite)
    } else {
        # Still ensure hybrid+parent bins are on PATH for this process.
        [void](Add-NvidiaPipBinsToPath -SiteRoots @($siteHybrid, $parentSite, $docsVeSite))
    }
} else {
    Write-Host "Skip CapCut remount (default). Set HYBRID_CALL_REMOUNT=1 for opt-in path-only remount."
    if ($SkipRemount) { Write-Host "SkipRemount=1 (legacy; already default)" }
    Invoke-PathOnlyRemount -ParentRoot $parentRoot -SiteRoots @($siteHybrid, $parentSite, $docsVeSite)
}

# 2) Soft presence check only - do NOT pip upgrade / force-reinstall here.
#    run_hybrid.ps1 installs deps without upgrading pip.
if ($venvPy) {
    $ortOk = & $venvPy -c "import importlib.util; print('1' if importlib.util.find_spec('onnxruntime') else '0')" 2>$null
    if ($ortOk -ne "1") {
        Write-Host "NOTE: onnxruntime missing in active venv - run_hybrid.ps1 will install requirements."
    }
    $hasDll = $false
    foreach ($site in @($siteHybrid, $parentSite, $docsVeSite)) {
        if (-not (Test-Path -LiteralPath $site)) { continue }
        $hit = Get-ChildItem -LiteralPath $site -Filter "cudnn64_*.dll" -Recurse -ErrorAction SilentlyContinue | Select-Object -First 1
        if ($hit) { $hasDll = $true; break }
    }
    if ($hasDll) {
        Write-Host "cuDNN DLL present under hybrid/parent site-packages"
    } else {
        Write-Host "WARN: cudnn64_*.dll not found yet - run_hybrid.ps1 may auto-install nvidia-cudnn-cu12."
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
    Write-Host "InstallOnly: PATH inject done (no remount pip). Run .\run_hybrid.ps1 next."
    exit 0
}

# 4) Launch without waiting on CapCut remount
$launcher = Join-Path $Root "run_hybrid.ps1"
if (-not (Test-Path -LiteralPath $launcher)) {
    $launcher = Join-Path $parentRoot "run_hybrid.ps1"
}
if (-not (Test-Path -LiteralPath $launcher)) {
    Write-Host "ERROR: run_hybrid.ps1 not found"
    exit 1
}
Write-Host ("Launching (no remount pip): " + $launcher)
& $launcher
