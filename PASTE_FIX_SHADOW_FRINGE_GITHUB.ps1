# HybridCut fix-shadow-fringe-fast2 — fetch combined feature branch (ASCII-only)
# Stamp: 2026-10-14-fix-shadow-fringe-fast2
# Branch: cursor/fix-shadow-fringe-fast2-2eca
# Includes: restore-rvm-fast2 (Max ETA honesty) + BG residue fringe fix

$ErrorActionPreference = "Stop"
$dest = Join-Path $env:USERPROFILE "Documents\HybridCut"
if (-not (Test-Path $dest)) {
  git clone https://github.com/hevesitr/HybridCut.git $dest
}
Set-Location $dest
git fetch origin
git checkout cursor/fix-shadow-fringe-fast2-2eca
git pull origin cursor/fix-shadow-fringe-fast2-2eca
Get-Content .\SYNC_VERSION.txt
Write-Host "OK — next: PASTE_FIX_SHADOW_FRINGE_INSTALL.ps1"
