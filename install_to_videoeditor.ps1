# Install HybridCut from this Git clone into CapCut Videoeditor folder.
# Copies tree -> %USERPROFILE%\Documents\Videoeditor\hybrid_cut
# Writes root launcher -> %USERPROFILE%\Documents\Videoeditor\run_hybrid.ps1
# ASCII-only. Safe from any cwd (including System32).
# Robolog uses GetTempPath + ASCII guid only; cleanup never aborts install
# (accented usernames / 8.3 short paths like RBERT~1 can break Remove-Item).

$ErrorActionPreference = "Stop"

$scriptDir = if ($PSScriptRoot) { $PSScriptRoot } else { Split-Path -Parent $MyInvocation.MyCommand.Path }
$src = $scriptDir
$videoeditor = Join-Path $env:USERPROFILE "Documents\Videoeditor"
$dst = Join-Path $videoeditor "hybrid_cut"
$rootLauncher = Join-Path $videoeditor "run_hybrid.ps1"

function New-AsciiTempPath {
    param([string]$Suffix = ".log")
    # Prefer BCL temp path; filename is ASCII guid only (no username in the leaf).
    $leaf = [guid]::NewGuid().ToString("N") + $Suffix
    return [System.IO.Path]::Combine([System.IO.Path]::GetTempPath(), $leaf)
}

function Remove-TempQuiet {
    param([string]$Path)
    if (-not $Path) { return }
    try {
        if (Test-Path -LiteralPath $Path) {
            Remove-Item -LiteralPath $Path -Force -ErrorAction Stop
        }
    } catch {
        # Never fail install/sync on temp log cleanup (8.3 / accented profile paths).
    }
}

function Test-HybridSrc([string]$Path) {
    if (-not $Path -or -not (Test-Path -LiteralPath $Path)) { return $false }
    return (Test-Path -LiteralPath (Join-Path $Path "backend\requirements.txt"))
}

function Write-RootLauncher {
    param([string]$HybridRoot, [string]$LauncherPath)
    New-Item -ItemType Directory -Force -Path (Split-Path -Parent $LauncherPath) | Out-Null
    $wrap = @"
# HybridCut root launcher (Documents\Videoeditor) - thin wrapper
# ASCII-only. Points at nested hybrid_cut\run_hybrid.ps1.
`$ErrorActionPreference = "Stop"
`$here = if (`$PSScriptRoot) { `$PSScriptRoot } else { Split-Path -Parent `$MyInvocation.MyCommand.Path }
`$nested = Join-Path `$here "hybrid_cut\run_hybrid.ps1"
if (-not (Test-Path -LiteralPath `$nested)) {
    `$nested = Join-Path `$env:USERPROFILE "Documents\Videoeditor\hybrid_cut\run_hybrid.ps1"
}
if (-not (Test-Path -LiteralPath `$nested)) {
    Write-Host "HIBA: Hianyzik hybrid_cut\run_hybrid.ps1"
    Write-Host "ERROR: Missing hybrid_cut\run_hybrid.ps1"
    exit 1
}
& `$nested @args
exit `$LASTEXITCODE
"@
    Set-Content -LiteralPath $LauncherPath -Value $wrap -Encoding ascii
    Write-Host ("ROOT LAUNCHER: " + $LauncherPath)
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
    Write-Host "HIBA: Hianyzik frontend\dist\index.html - a GitHub csomagnak tartalmaznia kell a beepitett UI-t."
    Write-Host "ERROR: Missing frontend\dist\index.html - GitHub package should include the built UI."
    exit 1
}

New-Item -ItemType Directory -Force -Path $videoeditor | Out-Null
New-Item -ItemType Directory -Force -Path $dst | Out-Null

Write-Host ("SRC: " + $src)
Write-Host ("DST: " + $dst)

$excludeDirs = @("__pycache__", ".venv", "venv", "node_modules", ".git", "bake", ".pytest_cache")
$robolog = New-AsciiTempPath -Suffix ".log"
$xdArgs = @()
foreach ($d in $excludeDirs) { $xdArgs += "/XD"; $xdArgs += $d }

$rcArgs = @($src, $dst, "/E", "/R:1", "/W:1", "/NFL", "/NDL", "/NJH", "/NP", "/XF", "*.pyc", "*.onnx", "*.pth", "*.pt") + $xdArgs + @("/LOG:" + $robolog)
& robocopy @rcArgs | Out-Null
$rc = $LASTEXITCODE
if ($rc -ge 8) {
    Write-Host ("robocopy log: " + $robolog)
    Remove-TempQuiet -Path $robolog
    Write-Error ("robocopy failed with exit code " + $rc)
}

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
    Remove-TempQuiet -Path $robolog
    Write-Error "Install incomplete - missing files listed above."
}

$verDst = Join-Path $dst "SYNC_VERSION.txt"
$stamp = (Get-Content -LiteralPath $verDst -Raw).Trim()
Copy-Item -LiteralPath $verDst -Destination (Join-Path $dst "SYNC_VERSION") -Force

# Root launcher BEFORE robolog cleanup - must not depend on temp log delete.
Write-RootLauncher -HybridRoot $dst -LauncherPath $rootLauncher

Remove-TempQuiet -Path $robolog

Write-Host ""
Write-Host ("INSTALL OK -> " + $dst)
Write-Host ("ROOT LAUNCHER: " + $rootLauncher)
Write-Host ("SYNC_VERSION: " + $stamp)
Write-Host ""
Write-Host "Kovetkezo / Next:"
Write-Host '  cd $env:USERPROFILE\Documents\Videoeditor'
Write-Host "  Get-Content .\hybrid_cut\SYNC_VERSION.txt"
Write-Host "  # expect: 2026-10-04-hybrid-cudnn-path"
Write-Host '  $env:HYBRID_RVM_ONNX = "$PWD\models\rvm_mobilenetv3_fp32.onnx"'
Write-Host "  .\hybrid_cut\start_hybrid_cuda.ps1"
Write-Host "  # or: .\run_hybrid.ps1"
Write-Host "  # Workaround B: `$env:HYBRID_REUSE_PARENT_VENV='1'; .\run_hybrid.ps1"
Write-Host "Open: http://127.0.0.1:3847"
Write-Host ""
Write-Host "Megjegyzes: CapCut gyoker = Documents\Videoeditor ; HybridCut = ...\hybrid_cut"
Write-Host "NOTE: CapCut root = Documents\Videoeditor ; HybridCut = ...\hybrid_cut"
