# PASTE THIS ENTIRE BLOCK into PowerShell NOW (ASCII-only hotfix).
# Overwrites Documents\Videoeditor\hybrid_cut\run_hybrid.ps1 then launches HybridCut on :3847.
# Phase 5: skip pip upgrade; trusted-host; parent RVM ONNX; parent .venv reuse.

$ErrorActionPreference = "Stop"
$Root = Join-Path $env:USERPROFILE "Documents\Videoeditor\hybrid_cut"
if (-not (Test-Path -LiteralPath (Join-Path $Root "backend\requirements.txt"))) {
    Write-Host "HIBA: Nincs hybrid_cut a Documents\Videoeditor alatt."
    Write-Host "ERROR: Missing Documents\Videoeditor\hybrid_cut (run sync first)."
    exit 1
}

$srcLauncher = Join-Path $env:LOCALAPPDATA "Cursor\AgentStores\cursor_agent_stores\bc-41930eab-1501-4c19-acf3-0c9d63afbf4d\files\docs\hybrid-editor\run_hybrid.ps1"
$dstLauncher = Join-Path $Root "run_hybrid.ps1"
if (Test-Path -LiteralPath $srcLauncher) {
    Copy-Item -LiteralPath $srcLauncher -Destination $dstLauncher -Force
    Write-Host ("Updated launcher from Agent Store: " + $dstLauncher)
} else {
    Write-Host "WARN: Agent Store run_hybrid.ps1 not found - launching existing nested launcher."
}

$ver = Join-Path $Root "SYNC_VERSION.txt"
if (Test-Path -LiteralPath $ver) {
    Write-Host ("SYNC_VERSION: " + ((Get-Content -LiteralPath $ver -Raw).Trim()))
}

Write-Host "Starting..."
Write-Host "Manual alternative:"
Write-Host '  cd $env:USERPROFILE\Documents\Videoeditor\hybrid_cut'
Write-Host '  $env:PYTHONPATH="$PWD\backend"'
Write-Host '  & .\.venv\Scripts\python.exe -m hybrid_editor.main'
& $dstLauncher
