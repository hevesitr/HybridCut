# start_hybrid_cuda.ps1 - HybridCut CUDA prep + launch (ASCII-only)
# Includes: rvm-back - cuda-restore - simple-bg7 CUDA stick
# Stamp: 2026-10-13-full-body-fast (CUDA probe sticks; single V1 BG remove)
# Default: do NOT call CapCut remount_ort_gpu.ps1 (its pip upgrade can hit Windows
# OSError access violation). Inject nvidia cudnn/cublas PATH from hybrid + parent
# site-packages, pin onnxruntime-gpu==1.30.0 (morning-working), probe plugin EP,
# then launch run_hybrid.ps1 without blocking on remount.
#
# Opt-in CapCut remount (path-only / skip pip upgrade):
#   $env:HYBRID_CALL_REMOUNT = "1"
# Legacy: -SkipRemount is default behavior (kept for callers).
#
# CORRECT cwd (pick ONE):
#   From Documents\Videoeditor:
#     .\hybrid_cut\start_hybrid_cuda.ps1
#   From Documents\Videoeditor\hybrid_cut:
#     .\start_hybrid_cuda.ps1
#   WRONG (path not found when already inside hybrid_cut):
#     .\hybrid_cut\start_hybrid_cuda.ps1
#
# Other:
#   .\start_hybrid_cuda.ps1 -ReuseParentVenv
#   .\start_hybrid_cuda.ps1 -InstallOnly
#   $env:HYBRID_CALL_REMOUNT = "1"; .\start_hybrid_cuda.ps1

param(
    [switch]$ReuseParentVenv,
    [switch]$SkipRemount,
    [switch]$InstallOnly,
    [switch]$SkipOrtPin
)

$ErrorActionPreference = "Stop"

$scriptDir = if ($PSScriptRoot) { $PSScriptRoot } else { Split-Path -Parent $MyInvocation.MyCommand.Path }
$nestedUnderCapCut = Join-Path $env:USERPROFILE "Documents\Videoeditor\hybrid_cut"
$docsVe = Join-Path $env:USERPROFILE "Documents\Videoeditor"
$OrtGpuPin = if ($env:HYBRID_ORT_GPU_PIN) { $env:HYBRID_ORT_GPU_PIN.Trim() } else { "1.30.0" }

$Root = $null
foreach ($cand in @($scriptDir, $nestedUnderCapCut)) {
    if (Test-Path -LiteralPath (Join-Path $cand "backend\requirements.txt")) {
        $Root = $cand
        break
    }
}
if (-not $Root) {
    Write-Host 'ERROR: HybridCut tree not found (backend\requirements.txt).'
    Write-Host "  From Videoeditor:  .\hybrid_cut\start_hybrid_cuda.ps1"
    Write-Host "  From hybrid_cut:   .\start_hybrid_cuda.ps1"
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
Write-Host ("Stamp: 2026-10-13-full-body-fast - pin onnxruntime-gpu==" + $OrtGpuPin + "; CUDA only after hard probe OK; persist cache\ort_provider.txt; ASCII PS1")
Write-Host "CWD tip: inside hybrid_cut use .\start_hybrid_cuda.ps1  |  from Videoeditor use .\hybrid_cut\start_hybrid_cuda.ps1"

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
    Write-Host 'HYBRID_REUSE_PARENT_VENV=1 (prefer parent CapCut .venv)'
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
    Write-Host 'Path-only remount (skip pip upgrade) ...'
    $n = Add-NvidiaPipBinsToPath -SiteRoots $SiteRoots
    if ($n -le 0) {
        Write-Host "WARN: no nvidia cudnn bins under hybrid/parent site-packages yet."
        Write-Host '  run_hybrid.ps1 may auto-install nvidia-cudnn-cu12 (no pip upgrade).'
        Write-Host "  Workaround B: `$env:HYBRID_REUSE_PARENT_VENV='1'; .\run_hybrid.ps1"
    } else {
        Write-Host ("PATH inject done (" + $n + " entries).")
    }
    if (-not $env:VIDEOEDITOR_ORT_PROVIDER) {
        $env:VIDEOEDITOR_ORT_PROVIDER = "cuda"
    }
    Write-Host 'VIDEOEDITOR_ORT_PROVIDER=cuda (path-only; no CapCut pip remount)'
}

function Get-OrtVersion {
    param(
        [string]$PythonExe,
        [string]$HybridRoot
    )
    if (-not $PythonExe) { return "" }
    $verScript = Join-Path $HybridRoot "scripts\ort_version.py"
    if (-not (Test-Path -LiteralPath $verScript)) {
        Write-Host ("WARN: missing " + $verScript)
        return ""
    }
    $prevEap = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    try {
        $raw = & $PythonExe $verScript 2>$null
    } finally {
        $ErrorActionPreference = $prevEap
    }
    if ($null -eq $raw) { return "" }
    return ([string]$raw).Trim()
}

function Test-OrtPresent {
    param(
        [string]$PythonExe,
        [string]$HybridRoot
    )
    if (-not $PythonExe) { return "0" }
    $presentScript = Join-Path $HybridRoot "scripts\ort_present.py"
    if (-not (Test-Path -LiteralPath $presentScript)) {
        Write-Host ("WARN: missing " + $presentScript)
        return "0"
    }
    $prevEap = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    try {
        $raw = & $PythonExe $presentScript 2>$null
    } finally {
        $ErrorActionPreference = $prevEap
    }
    if ($null -eq $raw) { return "0" }
    $s = ([string]$raw).Trim()
    if ($s -eq "1") { return "1" }
    return "0"
}

function Install-OrtGpuPin {
    param(
        [string]$PythonExe,
        [string]$Pin,
        [string]$ReqGpu
    )
    Write-Host ("Installing onnxruntime-gpu==" + $Pin + " (morning pin) ...")
    $pipTrusted = @("--trusted-host", "pypi.org", "--trusted-host", "files.pythonhosted.org", "--no-cache-dir")
    & $PythonExe -m pip uninstall onnxruntime onnxruntime-gpu -y 2>$null | Out-Null
    if ($ReqGpu -and (Test-Path -LiteralPath $ReqGpu)) {
        & $PythonExe -m pip install -r $ReqGpu @pipTrusted
    } else {
        & $PythonExe -m pip install ("onnxruntime-gpu==" + $Pin) "nvidia-cudnn-cu12>=9.0.0" @pipTrusted
    }
    return ($LASTEXITCODE -eq 0)
}

function Invoke-CudaEpProbe {
    param([string]$PythonExe, [string]$HybridRoot)
    # IMPORTANT: run a .py file - never python -c with multiline (PS quoting SyntaxError).
    $probeScript = Join-Path $HybridRoot "scripts\probe_cuda_ep.py"
    if (-not (Test-Path -LiteralPath $probeScript)) {
        return "OK=0`nRESULT=FAIL`nDETAIL=missing scripts/probe_cuda_ep.py`n"
    }
    $env:HYBRID_ROOT = $HybridRoot
    $env:PYTHONPATH = Join-Path $HybridRoot "backend"
    $prevEap = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    try {
        # Merge stderr so ORT plugin warnings do not become PS error records.
        $probeOut = & $PythonExe $probeScript 2>&1 | ForEach-Object {
            if ($_ -is [System.Management.Automation.ErrorRecord]) {
                [string]$_.ToString()
            } else {
                [string]$_
            }
        } | Out-String
    } finally {
        $ErrorActionPreference = $prevEap
    }
    return $probeOut
}

# 1) Default: path-only. Never block on CapCut remount pip upgrade.
$callRemount = ($env:HYBRID_CALL_REMOUNT -eq "1") -and (-not $SkipRemount)
$remount = Join-Path $parentRoot "remount_ort_gpu.ps1"

if ($callRemount) {
    Write-Host 'HYBRID_CALL_REMOUNT=1 - safe remount (skip pip upgrade) ...'
    $usedCapCutSafe = $false
    if (Test-Path -LiteralPath $remount) {
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
            Write-Host 'CapCut remount_ort_gpu.ps1 has no PathOnly/SkipPipUpgrade - skip calling it (avoids pip AV).'
        }
    } else {
        Write-Host ("No remount_ort_gpu.ps1 at " + $remount)
    }
    if (-not $usedCapCutSafe) {
        Invoke-PathOnlyRemount -ParentRoot $parentRoot -SiteRoots @($siteHybrid, $parentSite, $docsVeSite)
    } else {
        [void](Add-NvidiaPipBinsToPath -SiteRoots @($siteHybrid, $parentSite, $docsVeSite))
    }
} else {
    Write-Host 'Skip CapCut remount (default). Set HYBRID_CALL_REMOUNT=1 for opt-in path-only remount.'
    if ($SkipRemount) { Write-Host 'SkipRemount=1 (legacy; already default)' }
    Invoke-PathOnlyRemount -ParentRoot $parentRoot -SiteRoots @($siteHybrid, $parentSite, $docsVeSite)
}

# 2) Soft presence check + pin onnxruntime-gpu==1.30.0 when wrong/missing.
$reqGpu = Join-Path $Root "backend\requirements-gpu.txt"
if ($venvPy) {
    # File helper - never python -c with nested quotes/parens (PS 5.1 quoting).
    $ortOk = Test-OrtPresent -PythonExe $venvPy -HybridRoot $Root
    $ortVer = Get-OrtVersion -PythonExe $venvPy -HybridRoot $Root
    $ortVerLabel = if ($ortVer) { $ortVer } else { 'missing' }
    Write-Host ("ORT version in venv: " + $ortVerLabel)
    $needPin = $false
    if (-not $SkipOrtPin -and $env:HYBRID_SKIP_ORT_PIN -ne "1") {
        if ($ortOk -ne "1") { $needPin = $true }
        elseif ($ortVer -and ($ortVer -ne $OrtGpuPin)) { $needPin = $true }
    }
    if ($needPin) {
        $haveLabel = if ($ortVer) { $ortVer } else { 'none' }
        Write-Host ("ORT pin needed (want onnxruntime-gpu==" + $OrtGpuPin + ", have " + $haveLabel + ")")
        $pinOk = Install-OrtGpuPin -PythonExe $venvPy -Pin $OrtGpuPin -ReqGpu $reqGpu
        if ($pinOk) {
            Write-Host ("ORT pin install OK: onnxruntime-gpu==" + $OrtGpuPin)
            [void](Add-NvidiaPipBinsToPath -SiteRoots @($siteHybrid, $parentSite, $docsVeSite))
        } else {
            Write-Host 'WARN: ORT pin install failed - probe may FAIL; CPU fallback still available.'
        }
    } elseif ($ortOk -ne "1") {
        Write-Host 'NOTE: onnxruntime missing - run_hybrid.ps1 / requirements-gpu.txt will install.'
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

# 3b) CPU-first: never open Elonezet on broken CUDA Conv Fallback.
# Optional CUDA only after hard probe OK (plugin EP registered + no gray-slab).
if (-not $env:HYBRID_ORT_PROVIDER) {
    $env:HYBRID_ORT_PROVIDER = "cpu"
}
if (-not $env:VIDEOEDITOR_ORT_PROVIDER) {
    $env:VIDEOEDITOR_ORT_PROVIDER = "cpu"
}
Write-Host ('HYBRID_ORT_PROVIDER default: ' + $env:HYBRID_ORT_PROVIDER + ' (CPU-first; CUDA only after hard probe)')

# Probe when user asked for CUDA, or when unset was just defaulted to cpu and we
# may upgrade - always probe so a healthy morning stack can opt into CUDA.
$wantProbe = $true
if ($env:HYBRID_SKIP_CUDA_PROBE -eq "1") { $wantProbe = $false }
if ($venvPy -and $wantProbe) {
    Write-Host ""
    Write-Host "=== CUDA EP PROBE ==="
    $probeOut = Invoke-CudaEpProbe -PythonExe $venvPy -HybridRoot $Root
    Write-Host $probeOut.Trim()

    # If probe FAIL and version still wrong / plugin missing, one more pin+retry.
    if (($probeOut -notmatch "OK=1") -and (-not $SkipOrtPin) -and ($env:HYBRID_SKIP_ORT_PIN -ne "1")) {
        $verLine = ($probeOut -split "`n" | Where-Object { $_ -match "^ORT_VERSION=" } | Select-Object -First 1)
        $curVer = if ($verLine) { ($verLine -replace "^ORT_VERSION=", "").Trim() } else { "" }
        if ($curVer -ne $OrtGpuPin) {
            $verLabel = if ($curVer) { $curVer } else { 'none' }
            Write-Host ('PROBE FAIL + wrong ORT (' + $verLabel + ') - reinstall pin ' + $OrtGpuPin)
            if (Install-OrtGpuPin -PythonExe $venvPy -Pin $OrtGpuPin -ReqGpu $reqGpu) {
                [void](Add-NvidiaPipBinsToPath -SiteRoots @($siteHybrid, $parentSite, $docsVeSite))
                Write-Host '=== CUDA EP PROBE (retry after pin) ==='
                $probeOut = Invoke-CudaEpProbe -PythonExe $venvPy -HybridRoot $Root
                Write-Host $probeOut.Trim()
            }
        }
    }

    # Hard FAIL if plugin EP warning appears OR gray-slab smoke - even when OK=1
    # was printed from a soft/listed-only heuristic (native C++ warn bypassed tee).
    $pluginWarn = ($probeOut -match "No registered plugin EP")
    $slabFail = ($probeOut -match "gray-slab|gray slab|MemcpyTransformer")
    $okLine = ($probeOut -match "(?m)^OK=1\b") -or ($probeOut -match "OK=1")
    $probeHardOk = $okLine -and (-not $pluginWarn) -and (-not $slabFail) -and ($probeOut -match "RESULT[=:]OK|RESULT: OK")

    $cacheDir = Join-Path $Root "cache"
    New-Item -ItemType Directory -Force -Path $cacheDir | Out-Null
    $providerFile = Join-Path $cacheDir "ort_provider.txt"

    if ($probeHardOk) {
        Write-Host 'RESULT: OK - CUDA EP registered (morning-like path) - upgrading from CPU default'
        Write-Host "=== CUDA EP PROBE END ==="
        Write-Host "HYBRID_ORT_PROVIDER=cuda"
        $env:HYBRID_ORT_PROVIDER = "cuda"
        $env:VIDEOEDITOR_ORT_PROVIDER = "cuda"
        Set-Content -LiteralPath $providerFile -Value "cuda" -Encoding Ascii
        Write-Host ("Persisted: " + $providerFile + " = cuda")
    } else {
        if ($pluginWarn) {
            Write-Host 'RESULT: FAIL - plugin EP warning in probe output (ignore false OK=1)'
        } elseif ($slabFail) {
            Write-Host 'RESULT: FAIL - CUDA smoke gray-slab / MemcpyTransformer'
        } else {
            Write-Host 'RESULT: FAIL - CUDA EP plugin not registered'
        }
        Write-Host "=== CUDA EP PROBE END ==="
        Write-Host 'KEEP: HYBRID_ORT_PROVIDER=cpu (CPU-first; real person matte; no Conv Fallback)'
        Write-Host '  Optional morning CUDA fix (Windows):'
        Write-Host "    cd `$env:USERPROFILE\Documents\Videoeditor\hybrid_cut"
        Write-Host "    .\.venv\Scripts\Activate.ps1"
        Write-Host "    pip uninstall onnxruntime onnxruntime-gpu -y"
        Write-Host ("    pip install onnxruntime-gpu==" + $OrtGpuPin + " nvidia-cudnn-cu12")
        Write-Host "    .\start_hybrid_cuda.ps1"
        Write-Host '  Expect probe RESULT: OK before CUDA is used'
        $env:HYBRID_ORT_PROVIDER = "cpu"
        $env:VIDEOEDITOR_ORT_PROVIDER = "cpu"
        Set-Content -LiteralPath $providerFile -Value "cpu" -Encoding Ascii
        Write-Host ("Persisted: " + $providerFile + " = cpu")
    }
    Write-Host ""
}

if ($InstallOnly) {
    Write-Host "InstallOnly: PATH inject + ORT pin + CUDA EP probe done. Run .\run_hybrid.ps1 next."
    Write-Host ("HYBRID_ORT_PROVIDER=" + $env:HYBRID_ORT_PROVIDER)
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
