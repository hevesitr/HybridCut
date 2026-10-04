# PASTE THIS into PowerShell NOW (ASCII-only).
# Creates Documents\Videoeditor\run_hybrid.ps1 wrapper without reinstall.
# Requires hybrid_cut already present (SYNC_VERSION ok).

$ErrorActionPreference = "Stop"
$ve = Join-Path $env:USERPROFILE "Documents\Videoeditor"
$nested = Join-Path $ve "hybrid_cut\run_hybrid.ps1"
$root = Join-Path $ve "run_hybrid.ps1"
if (-not (Test-Path -LiteralPath $nested)) {
    Write-Host "HIBA: Hianyzik hybrid_cut\run_hybrid.ps1 - eloszor telepitsd/synceld a HybridCutot."
    Write-Host "ERROR: Missing hybrid_cut\run_hybrid.ps1 - install/sync HybridCut first."
    exit 1
}
New-Item -ItemType Directory -Force -Path $ve | Out-Null
$wrap = @'
# HybridCut root launcher (Documents\Videoeditor) - thin wrapper
$ErrorActionPreference = "Stop"
$here = if ($PSScriptRoot) { $PSScriptRoot } else { Split-Path -Parent $MyInvocation.MyCommand.Path }
$nested = Join-Path $here "hybrid_cut\run_hybrid.ps1"
if (-not (Test-Path -LiteralPath $nested)) {
    $nested = Join-Path $env:USERPROFILE "Documents\Videoeditor\hybrid_cut\run_hybrid.ps1"
}
if (-not (Test-Path -LiteralPath $nested)) {
    Write-Host "HIBA: Hianyzik hybrid_cut\run_hybrid.ps1"
    Write-Host "ERROR: Missing hybrid_cut\run_hybrid.ps1"
    exit 1
}
& $nested @args
exit $LASTEXITCODE
'@
Set-Content -LiteralPath $root -Value $wrap -Encoding ascii
Write-Host ("OK wrote: " + $root)
Write-Host "Next: cd `$env:USERPROFILE\Documents\Videoeditor; .\run_hybrid.ps1"
Write-Host "Open: http://127.0.0.1:3847"
