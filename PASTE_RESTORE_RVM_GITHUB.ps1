# HybridCut restore-rvm - GitHub-only install (no Agent Store).
# ASCII-only. Paste into Windows PowerShell.
# Mirrors OSS RVM/rembg: soft pha preview, no crush wipe.

$ErrorActionPreference = "Stop"
$TipStamp = "2026-10-14-restore-rvm-fast"
$RepoUrl = "https://github.com/hevesitr/HybridCut.git"
$Repo = Join-Path $env:USERPROFILE "Documents\HybridCut"

Write-Host "=== HybridCut restore-rvm (GitHub pull) ==="

Get-NetTCPConnection -LocalPort 3847 -ErrorAction SilentlyContinue |
  ForEach-Object {
    try { Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue } catch {}
  }

New-Item -ItemType Directory -Force -Path (Split-Path -Parent $Repo) | Out-Null
if (-not (Test-Path -LiteralPath (Join-Path $Repo ".git"))) {
  git clone $RepoUrl $Repo
}
Set-Location -LiteralPath $Repo
git fetch origin
git checkout cursor/restore-rvm-fast-b680
if ($LASTEXITCODE -ne 0) {
  git checkout -B cursor/restore-rvm-fast-b680 origin/cursor/restore-rvm-fast-b680
}
git pull origin cursor/restore-rvm-fast-b680

$stamp = ""
$sf = Join-Path $Repo "SYNC_VERSION.txt"
if (Test-Path -LiteralPath $sf) { $stamp = (Get-Content -LiteralPath $sf -Raw).Trim() }
Write-Host ("SRC SYNC_VERSION: " + $stamp)
if ($stamp -ne $TipStamp) {
  Write-Host ("WARN: expected " + $TipStamp + " - continuing with pulled tip")
}

& .\install_to_videoeditor.ps1
$ve = Join-Path $env:USERPROFILE "Documents\Videoeditor\hybrid_cut"
Write-Host ("INSTALLED: " + (Get-Content -LiteralPath (Join-Path $ve "SYNC_VERSION.txt") -Raw).Trim())
Write-Host "Open http://127.0.0.1:3847 then Ctrl+F5"
Write-Host "Expect: Gyors Elonezet shows soft RVM person cutout (OSS path); no gray-slab"
Set-Location -LiteralPath $ve
if (Test-Path -LiteralPath ".\start_hybrid_cuda.ps1") { .\start_hybrid_cuda.ps1 } else { .\run_hybrid.ps1 }
