# Install HybridCut from this Git clone into CapCut Videoeditor folder.
# Copies tree -> %USERPROFILE%\Documents\Videoeditor\hybrid_cut
# Writes root launcher -> %USERPROFILE%\Documents\Videoeditor\run_hybrid.ps1
# ASCII-only. Safe from any cwd (including System32).

$ErrorActionPreference = "Stop"

$scriptDir = if ($PSScriptRoot) { $PSScriptRoot } else { Split-Path -Parent $MyInvocation.MyCommand.Path }
$src = $scriptDir
$videoeditor = Join-Path $env:USERPROFILE "Documents\Videoeditor"
$dst = Join-Path $videoeditor "hybrid_cut"
$rootLauncher = Join-Path $videoeditor "run_hybrid.ps1"

function Test-HybridSrc([string]$Path) {
    if (-not $Path -or -not (Test-Path -LiteralPath $Path)) { return $false }
    return (Test-Path -LiteralPath (Join-Path $Path "backend\requirements.txt"))
}

if (-not (Test-HybridSrc $src)) {
    Write-Host ""
    Write-Host "HIBA: Ez a script a HybridCut klon gyokerbol kell fusson (backend\requirements.txt hianyzik)."
    Write-Host "ERROR: Run this script from the HybridCut clone root (missing backend\requirements.txt)."
    Write-Host ("Script dir: " + $scriptDir)
    exit 1
}

$distIndex = Join-Path $src "frontend\dist\index.html"
if (-not (Test-Path -LiteralPath $distIndex)) {
    Write-Host "HIBA: Hianyzik frontend\dist\index.html — a GitHub csomagnak tartalmaznia kell a beepitett UI-t."
    Write-Host "ERROR: Missing frontend\dist\index.html — GitHub package should include the built UI."
    exit 1
}

New-Item -ItemType Directory -Force -Path $videoeditor | Out-Null
New-Item -ItemType Directory -Force -Path $dst | Out-Null

Write-Host ("SRC: " + $src)
Write-Host ("DST: " + $dst)

$excludeDirs = @("__pycache__", ".venv", "venv", "node_modules", ".git", "bake", ".pytest_cache")
$robolog = Join-Path $env:TEMP ("hybrid-install-" + [guid]::NewGuid().ToString("N") + ".log")
$xdArgs = @()
foreach ($d in $excludeDirs) { $xdArgs += "/XD"; $xdArgs += $d }

$rcArgs = @($src, $dst, "/E", "/R:1", "/W:1", "/NFL", "/NDL", "/NJH", "/NP", "/XF", "*.pyc", "*.onnx", "*.pth", "*.pt") + $xdArgs + @("/LOG:" + $robolog)
& robocopy @rcArgs | Out-Null
$rc = $LASTEXITCODE
if ($rc -ge 8) {
    Write-Host ("robocopy log: " + $robolog)
    Write-Error ("robocopy failed with exit code " + $rc)
}
Remove-Item -LiteralPath $robolog -Force -ErrorAction SilentlyContinue

# Ensure sample media if present in clone
$sampleSrc = Join-Path $src "cache\sample_person.mp4"
$sampleDstDir = Join-Path $dst "cache"
$sampleDst = Join-Path $sampleDstDir "sample_person.mp4"
if (Test-Path -LiteralPath $sampleSrc) {
    New-Item -ItemType Directory -Force -Path $sampleDstDir | Out-Null
    Copy-Item -LiteralPath $sampleSrc -Destination $sampleDst -Force
}

$need = @(
    (Join-Path $dst "backend\requirements.txt"),
    (Join-Path $dst "backend\hybrid_editor\main.py"),
    (Join-Path $dst "frontend\dist\index.html"),
    (Join-Path $dst "SYNC_VERSION.txt"),
    (Join-Path $dst "run_hybrid.ps1"),
    (Join-Path $dst "README.md")
)
$missing = @()
foreach ($p in $need) {
    if (-not (Test-Path -LiteralPath $p)) { $missing += $p }
}
if ($missing.Count -gt 0) {
    Write-Host "Hianyzo fajlok / Missing files:"
    foreach ($m in $missing) { Write-Host ("  " + $m) }
    Write-Error "Install incomplete - missing files listed above."
}

$verDst = Join-Path $dst "SYNC_VERSION.txt"
$stamp = (Get-Content -LiteralPath $verDst -Raw).Trim()
Copy-Item -LiteralPath $verDst -Destination (Join-Path $dst "SYNC_VERSION") -Force

# Root CapCut-folder launcher (same script; resolves nested hybrid_cut)
$runSrc = Join-Path $dst "run_hybrid.ps1"
Copy-Item -LiteralPath $runSrc -Destination $rootLauncher -Force

Write-Host ""
Write-Host ("INSTALL OK -> " + $dst)
Write-Host ("ROOT LAUNCHER: " + $rootLauncher)
Write-Host ("SYNC_VERSION: " + $stamp)
Write-Host ""
Write-Host "Kovetkezo / Next:"
Write-Host '  cd $env:USERPROFILE\Documents\Videoeditor'
Write-Host "  Get-Content .\hybrid_cut\SYNC_VERSION.txt"
Write-Host "  .\run_hybrid.ps1"
Write-Host "Open: http://127.0.0.1:3847"
Write-Host ""
Write-Host "Megjegyzes: CapCut gyoker = Documents\Videoeditor ; HybridCut = ...\hybrid_cut"
Write-Host "NOTE: CapCut root = Documents\Videoeditor ; HybridCut = ...\hybrid_cut"
