# HybridCut one-click launcher (API + built UI on port 3847)
# ASCII-only. Resolves root via Documents sync target or this script's folder.
# Safe from ANY cwd - never assumes System32 or a prior cd.
# Phase 5: skip pip upgrade; trusted-host; parent Videoeditor .venv reuse;
# auto HYBRID_RVM_ONNX from parent Documents\Videoeditor\models when present.

$ErrorActionPreference = "Stop"

function Write-HybridError {
    param([string]$Hu, [string]$En)
    Write-Host ""
    Write-Host ("HIBA: " + $Hu)
    Write-Host ("ERROR: " + $En)
    Write-Host ""
}

$scriptDir = if ($PSScriptRoot) { $PSScriptRoot } else { Split-Path -Parent $MyInvocation.MyCommand.Path }
$nestedUnderCapCut = Join-Path $env:USERPROFILE "Documents\Videoeditor\hybrid_cut"
$legacySibling = Join-Path $env:USERPROFILE "Documents\Videoeditor-hybrid"

$Root = $null
foreach ($cand in @($scriptDir, $nestedUnderCapCut, $legacySibling)) {
    if (Test-Path -LiteralPath (Join-Path $cand "backend\requirements.txt")) {
        $Root = $cand
        break
    }
}

if (-not $Root) {
    Write-HybridError `
        -Hu "Nem talalom a HybridCut fat (backend\requirements.txt). Eloszor: hybrid-editor\sync.ps1 (Agent Store)." `
        -En "HybridCut tree not found. Run docs/hybrid-editor/sync.ps1 from the Agent Store first."
    Write-Host "Pelda / Example (any directory):"
    Write-Host '  & "$env:LOCALAPPDATA\Cursor\AgentStores\cursor_agent_stores\bc-41930eab-1501-4c19-acf3-0c9d63afbf4d\files\docs\hybrid-editor\sync.ps1"'
    Write-Host '  cd $env:USERPROFILE\Documents\Videoeditor\hybrid_cut'
    Write-Host "  .\run_hybrid.ps1"
    exit 1
}

$cwd = (Get-Location).Path
if ($cwd -match '(?i)\\Windows\\System32$') {
    Write-Host "FIGYELEM: A jelenlegi konyvtar System32 - a script atlep ide: $Root"
    Write-Host "WARN: Current directory is System32 - switching to: $Root"
}

Set-Location -LiteralPath $Root

$req = Join-Path $Root "backend\requirements.txt"
$mainPy = Join-Path $Root "backend\hybrid_editor\main.py"
$distIndex = Join-Path $Root "frontend\dist\index.html"
$verFile = Join-Path $Root "SYNC_VERSION.txt"

if (-not (Test-Path -LiteralPath $req)) {
    Write-HybridError `
        -Hu ("Hianyzik: " + $req) `
        -En ("Missing: " + $req)
    exit 1
}
if (-not (Test-Path -LiteralPath $mainPy)) {
    Write-HybridError `
        -Hu ("Hianyzik a backend: " + $mainPy + " - futtasd ujra a sync.ps1-et.") `
        -En ("Backend missing: " + $mainPy + " - re-run sync.ps1.")
    exit 1
}

$stamp = "unknown"
if (Test-Path -LiteralPath $verFile) {
    $stamp = (Get-Content -LiteralPath $verFile -Raw).Trim()
}

Write-Host ("ROOT: " + $Root)
Write-Host ("SYNC_VERSION: " + $stamp)
Write-Host "UI+API: http://127.0.0.1:3847"

# Parent CapCut Videoeditor (Documents\Videoeditor when Root is ...\hybrid_cut)
$parentRoot = Split-Path -Parent $Root
$parentVenvPy = Join-Path $parentRoot ".venv\Scripts\python.exe"
$parentModels = Join-Path $parentRoot "models"
# Also accept Documents\Videoeditor\.venv when script lives one level deeper
$docsVeVenv = Join-Path $env:USERPROFILE "Documents\Videoeditor\.venv\Scripts\python.exe"
$docsVeModels = Join-Path $env:USERPROFILE "Documents\Videoeditor\models"

# --- Auto-wire parent RVM ONNX (no weight redistribution; prefer fp32) ---
if (-not $env:HYBRID_RVM_ONNX) {
    $rvmNames = @(
        "rvm_mobilenetv3_fp32.onnx",
        "rvm_mobilenetv3.onnx",
        "rvm_mobilenetv3_fp16.onnx",
        "rvm_resnet50_fp32.onnx",
        "rvm_resnet50_fp16.onnx"
    )
    $searchDirs = @(
        (Join-Path $Root "models"),
        $parentModels,
        $docsVeModels
    )
    foreach ($dir in $searchDirs) {
        if (-not (Test-Path -LiteralPath $dir)) { continue }
        foreach ($name in $rvmNames) {
            $cand = Join-Path $dir $name
            if (Test-Path -LiteralPath $cand) {
                $env:HYBRID_RVM_ONNX = $cand
                Write-Host ("HYBRID_RVM_ONNX <= " + $cand)
                break
            }
        }
        if ($env:HYBRID_RVM_ONNX) { break }
        $any = Get-ChildItem -LiteralPath $dir -Filter "rvm_*.onnx" -ErrorAction SilentlyContinue | Select-Object -First 1
        if ($any) {
            $env:HYBRID_RVM_ONNX = $any.FullName
            Write-Host ("HYBRID_RVM_ONNX <= " + $any.FullName)
            break
        }
    }
    if (-not $env:HYBRID_RVM_ONNX) {
        Write-Host "RVM ONNX: not found yet (heuristic fallback). Parent models/ or scripts\download_rvm.ps1."
    }
}

# Prefer CUDA like CapCut Videoeditor; override: $env:HYBRID_ORT_PROVIDER = "cpu"
if (-not $env:HYBRID_ORT_PROVIDER) {
    $env:HYBRID_ORT_PROVIDER = "cuda"
}

# Prepend pip nvidia cudnn/cublas bins to PATH (hybrid + parent CapCut venv).
# Same idea as CapCut run_gpu.ps1 / remount_ort_gpu.ps1 — needed before ORT CUDA EP.
function Add-NvidiaPipBinsToPath {
    param([string[]]$SiteRoots)
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
                }
            }
        }
        $dlls = Get-ChildItem -LiteralPath $nv -Filter "cudnn64_*.dll" -Recurse -ErrorAction SilentlyContinue
        foreach ($dll in $dlls) {
            $env:PATH = $dll.DirectoryName + [IO.Path]::PathSeparator + $env:PATH
            Write-Host ("cudnn DLL: " + $dll.FullName)
        }
    }
}

# --- Python / venv ---
function Invoke-PyLauncher {
    param([string[]]$PyArgs)
    $prevEap = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    try {
        if (Get-Command py -ErrorAction SilentlyContinue) {
            & py -3.12 @PyArgs
            if ($LASTEXITCODE -eq 0) { return $true }
            & py -3 @PyArgs
            if ($LASTEXITCODE -eq 0) { return $true }
        }
        if (Get-Command python -ErrorAction SilentlyContinue) {
            & python @PyArgs
            if ($LASTEXITCODE -eq 0) { return $true }
        }
    } finally {
        $ErrorActionPreference = $prevEap
    }
    return $false
}

$hasPy = $false
if (Get-Command py -ErrorAction SilentlyContinue) { $hasPy = $true }
elseif (Get-Command python -ErrorAction SilentlyContinue) { $hasPy = $true }
if (-not $hasPy) {
    Write-HybridError `
        -Hu "Python nem talalhato. Telepits Python 3.12-t (python.org), majd inditsd ujra a PowerShell-t." `
        -En "Python not found. Install Python 3.12 from python.org, then reopen PowerShell."
    exit 1
}

$venvDir = Join-Path $Root ".venv"
$venvPy = Join-Path $venvDir "Scripts\python.exe"
$activate = Join-Path $venvDir "Scripts\Activate.ps1"
$usingParentVenv = $false

# Optional force: $env:HYBRID_REUSE_PARENT_VENV = "1"
if ($env:HYBRID_REUSE_PARENT_VENV -eq "1") {
    foreach ($candPy in @($parentVenvPy, $docsVeVenv)) {
        if (Test-Path -LiteralPath $candPy) {
            $venvPy = $candPy
            $usingParentVenv = $true
            Write-Host ("HYBRID_REUSE_PARENT_VENV=1 -> " + $venvPy)
            break
        }
    }
}

if (-not $usingParentVenv -and -not (Test-Path -LiteralPath $venvPy)) {
    Write-Host "Creating venv (.venv)..."
    $ok = Invoke-PyLauncher -PyArgs @("-m", "venv", $venvDir)
    if (-not $ok -or -not (Test-Path -LiteralPath $venvPy)) {
        # Fall back to parent Videoeditor .venv if hybrid venv create fails
        foreach ($candPy in @($parentVenvPy, $docsVeVenv)) {
            if (Test-Path -LiteralPath $candPy) {
                $venvPy = $candPy
                $usingParentVenv = $true
                Write-Host ("Hybrid venv create failed - reusing parent: " + $venvPy)
                break
            }
        }
    }
}

if (-not (Test-Path -LiteralPath $venvPy)) {
    Write-HybridError `
        -Hu "Nincs python a hybrid .venv-ben, es a parent Videoeditor\.venv sem talalhato." `
        -En "No hybrid .venv python and parent Videoeditor\.venv missing."
    exit 1
}

if (-not $usingParentVenv -and (Test-Path -LiteralPath $activate)) {
    . $activate
}

# pip: do NOT upgrade pip by default (Windows PyPI can hit
# ProtocolError / OSError access violation on pip install --upgrade pip).
# Opt-in: $env:HYBRID_UPGRADE_PIP = "1"
# Install uses --trusted-host. Opt-out cache skip: $env:HYBRID_PIP_USE_CACHE = "1"

$pipTrusted = @("--trusted-host", "pypi.org", "--trusted-host", "files.pythonhosted.org")
$pipNoCache = @()
if ($env:HYBRID_PIP_USE_CACHE -ne "1") {
    $pipNoCache = @("--no-cache-dir")
}

if ($env:HYBRID_UPGRADE_PIP -eq "1") {
    Write-Host "pip upgrade (HYBRID_UPGRADE_PIP=1) ..."
    & $venvPy -m pip install --upgrade pip @pipTrusted @pipNoCache
    if ($LASTEXITCODE -ne 0) {
        Write-HybridError `
            -Hu "pip upgrade sikertelen (HYBRID_UPGRADE_PIP=1). Probalj HYBRID_UPGRADE_PIP nelkul." `
            -En "pip upgrade failed (HYBRID_UPGRADE_PIP=1). Retry without HYBRID_UPGRADE_PIP."
        exit 1
    }
} else {
    Write-Host "Skipping pip upgrade (set HYBRID_UPGRADE_PIP=1 to force)."
}

Write-Host "pip install -r backend\requirements.txt ..."
& $venvPy -m pip install -r $req @pipTrusted @pipNoCache
if ($LASTEXITCODE -ne 0) {
    $fallbackPy = $null
    foreach ($candPy in @($parentVenvPy, $docsVeVenv)) {
        if ((Test-Path -LiteralPath $candPy) -and ($candPy -ne $venvPy)) {
            $fallbackPy = $candPy
            break
        }
    }
    if ($fallbackPy) {
        Write-Host ("Hybrid pip failed - installing deps with parent venv: " + $fallbackPy)
        & $fallbackPy -m pip install -r $req @pipTrusted @pipNoCache
        if ($LASTEXITCODE -eq 0) {
            $venvPy = $fallbackPy
            $usingParentVenv = $true
            Write-Host ("Runtime python switched to parent: " + $venvPy)
        } else {
            Write-HybridError `
                -Hu "A fuggosegek telepitese sikertelen (hybrid es parent venv)." `
                -En "Dependency install failed (hybrid and parent venv)."
            exit 1
        }
    } else {
        Write-HybridError `
            -Hu "A fuggosegek telepitese sikertelen (backend\requirements.txt)." `
            -En "Dependency install failed (backend\requirements.txt)."
        exit 1
    }
}

# Optional GPU ORT note (do not force-uninstall; CapCut parent may already have onnxruntime-gpu)
$ortProbe = & $venvPy -c "import importlib.util; print('1' if importlib.util.find_spec('onnxruntime') else '0')" 2>$null
if ($ortProbe -ne "1") {
    Write-Host "NOTE: onnxruntime not installed. For CUDA RVM on RTX 3060:"
    Write-Host ("  & '" + $venvPy + "' -m pip install onnxruntime-gpu --trusted-host pypi.org --trusted-host files.pythonhosted.org --no-cache-dir")
    Write-Host "  (or reuse parent Videoeditor\.venv after .\setup_gpu.ps1 / .\remount_ort_gpu.ps1)"
    Write-Host "  Or: .\start_hybrid_cuda.ps1"
}

# Auto-install nvidia-cudnn-cu12 into active venv when cudnn64_*.dll is missing.
# Hybrid .venv often has onnxruntime-gpu but CapCut's remount put cuDNN only in parent.
$siteHybrid = Join-Path $Root ".venv\Lib\site-packages"
$parentSite = Join-Path $parentRoot ".venv\Lib\site-packages"
$docsVeSite = Join-Path $env:USERPROFILE "Documents\Videoeditor\.venv\Lib\site-packages"

function Test-CudnnDllPresent {
    param([string[]]$SiteRoots)
    foreach ($site in $SiteRoots) {
        if (-not $site -or -not (Test-Path -LiteralPath $site)) { continue }
        $hit = Get-ChildItem -LiteralPath $site -Filter "cudnn64_*.dll" -Recurse -ErrorAction SilentlyContinue | Select-Object -First 1
        if ($hit) { return $true }
    }
    return $false
}

$hasCudnnDll = Test-CudnnDllPresent -SiteRoots @($siteHybrid, $parentSite, $docsVeSite)
if (-not $hasCudnnDll) {
    Write-Host "cudnn64_*.dll missing - auto-installing nvidia-cudnn-cu12 (+ cublas/cudart) into active venv..."
    & $venvPy -m pip install `
        "nvidia-cudnn-cu12>=9.0.0" `
        "nvidia-cublas-cu12>=12.0.0" `
        "nvidia-cuda-runtime-cu12>=12.0.0" `
        "nvidia-cuda-nvrtc-cu12>=12.0.0" `
        @pipTrusted @pipNoCache
    if ($LASTEXITCODE -ne 0) {
        Write-Host "WARN: nvidia-cudnn-cu12 auto-install failed."
        Write-Host "  Workaround B: `$env:HYBRID_REUSE_PARENT_VENV='1'; then .\run_hybrid.ps1"
        Write-Host "  Or CapCut: cd parent Videoeditor; .\remount_ort_gpu.ps1"
        Write-Host "  Or: .\start_hybrid_cuda.ps1"
    } else {
        Write-Host "nvidia-cudnn-cu12 installed OK."
    }
    $hasCudnnDll = Test-CudnnDllPresent -SiteRoots @($siteHybrid, $parentSite, $docsVeSite)
}

# PATH inject AFTER possible install so new bins are visible to ORT CUDA EP.
Add-NvidiaPipBinsToPath -SiteRoots @($siteHybrid, $parentSite, $docsVeSite)
if ($hasCudnnDll) {
    Write-Host "cuDNN DLL available; PATH prepended for ORT CUDA EP (Python also uses os.add_dll_directory)."
} else {
    Write-Host "WARN: cuDNN still missing after install attempt - HybridCut will soft-fallback to CPU if CUDA EP fails."
}

# --- Frontend dist (production serve via FastAPI) ---
if (-not (Test-Path -LiteralPath $distIndex)) {
    Write-Host "frontend\dist hianyzik - npm build kiserlet..."
    Write-Host "frontend\dist missing - attempting npm build..."
    $fe = Join-Path $Root "frontend"
    if (-not (Test-Path -LiteralPath (Join-Path $fe "package.json"))) {
        Write-HybridError `
            -Hu "Nincs frontend (package.json / dist). Futtasd ujra a sync.ps1-et." `
            -En "Frontend missing (package.json / dist). Re-run sync.ps1."
        exit 1
    }
    if (-not (Get-Command npm -ErrorAction SilentlyContinue)) {
        Write-HybridError `
            -Hu "Nincs frontend/dist es nincs npm. Telepits Node.js-t, VAGY synceld ujra a fat (a dist benne van)." `
            -En "No frontend/dist and no npm. Install Node.js, OR re-run sync.ps1 (dist is included)."
        exit 1
    }
    Push-Location $fe
    try {
        if (-not (Test-Path -LiteralPath (Join-Path $fe "node_modules"))) {
            npm install
            if ($LASTEXITCODE -ne 0) { throw "npm install failed" }
        }
        npm run build
        if ($LASTEXITCODE -ne 0) { throw "npm run build failed" }
    } catch {
        Pop-Location
        Write-HybridError `
            -Hu ("Frontend build hiba: " + $_) `
            -En ("Frontend build error: " + $_)
        exit 1
    }
    Pop-Location
}

if (-not (Test-Path -LiteralPath $distIndex)) {
    Write-HybridError `
        -Hu "frontend\dist\index.html meg mindig hianyzik." `
        -En "frontend\dist\index.html still missing."
    exit 1
}

$env:PYTHONPATH = Join-Path $Root "backend"
$env:HYBRID_HOST = "127.0.0.1"
$env:HYBRID_PORT = "3847"

Write-Host ""
Write-Host "Starting HybridCut..."
Write-Host ("Python: " + $venvPy + $(if ($usingParentVenv) { " (parent venv)" } else { "" }))
if ($env:HYBRID_RVM_ONNX) { Write-Host ("RVM: " + $env:HYBRID_RVM_ONNX) }
Write-Host "Browser: http://127.0.0.1:3847"
Write-Host "Manual start (user-confirmed working):"
Write-Host '  cd hybrid_cut'
Write-Host '  $env:PYTHONPATH="$PWD\backend"'
Write-Host '  & .\.venv\Scripts\python.exe -m hybrid_editor.main'
Write-Host "Stop: Ctrl+C"
Write-Host ""

& $venvPy -m hybrid_editor.main
