# HybridCut one-click launcher (API + built UI on port 3847)
# ASCII-only. Resolves root via Documents sync target or this script's folder.
# Safe from ANY cwd — never assumes System32 or a prior cd.

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
    Write-Host "FIGYELEM: A jelenlegi konyvtar System32 — a script atlep ide: $Root"
    Write-Host "WARN: Current directory is System32 — switching to: $Root"
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
        -Hu ("Hianyzik a backend: " + $mainPy + " — futtasd ujra a sync.ps1-et.") `
        -En ("Backend missing: " + $mainPy + " — re-run sync.ps1.")
    exit 1
}

$stamp = "unknown"
if (Test-Path -LiteralPath $verFile) {
    $stamp = (Get-Content -LiteralPath $verFile -Raw).Trim()
}

Write-Host ("ROOT: " + $Root)
Write-Host ("SYNC_VERSION: " + $stamp)
Write-Host "UI+API: http://127.0.0.1:3847"

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

if (-not (Test-Path -LiteralPath $venvPy)) {
    Write-Host "Creating venv (.venv)..."
    $ok = Invoke-PyLauncher -PyArgs @("-m", "venv", $venvDir)
    if (-not $ok -or -not (Test-Path -LiteralPath $venvPy)) {
        Write-HybridError `
            -Hu "A venv letrehozasa sikertelen." `
            -En "Failed to create .venv."
        exit 1
    }
}

if (Test-Path -LiteralPath $activate) {
    . $activate
}

Write-Host "pip install -r backend\requirements.txt ..."
& $venvPy -m pip install --upgrade pip
if ($LASTEXITCODE -ne 0) {
    Write-HybridError `
        -Hu "pip upgrade sikertelen." `
        -En "pip upgrade failed."
    exit 1
}
& $venvPy -m pip install -r $req
if ($LASTEXITCODE -ne 0) {
    Write-HybridError `
        -Hu "A fuggosegek telepitese sikertelen (backend\requirements.txt)." `
        -En "Dependency install failed (backend\requirements.txt)."
    exit 1
}

# --- Frontend dist (production serve via FastAPI) ---
if (-not (Test-Path -LiteralPath $distIndex)) {
    Write-Host "frontend\dist hianyzik — npm build kiserlet..."
    Write-Host "frontend\dist missing — attempting npm build..."
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
Write-Host "Browser: http://127.0.0.1:3847"
Write-Host "Stop: Ctrl+C"
Write-Host ""

& $venvPy -m hybrid_editor.main
