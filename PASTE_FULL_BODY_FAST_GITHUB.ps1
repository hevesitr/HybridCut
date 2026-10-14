# HybridCut full-body-fast - GitHub-only install (no Agent Store / Context sync).
# ASCII-only. Paste into Windows PowerShell.
# Requires: git + network to https://github.com/hevesitr/HybridCut

$ErrorActionPreference = "Stop"
$TipStamp = "2026-10-14-restore-rvm-fast2"
$RepoUrl = "https://github.com/hevesitr/HybridCut.git"
$Repo = Join-Path $env:USERPROFILE "Documents\HybridCut"

Write-Host "=== HybridCut full-body-fast (GitHub pull) ==="

Get-NetTCPConnection -LocalPort 3847 -ErrorAction SilentlyContinue |
  ForEach-Object {
    try { Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue } catch {}
  }

New-Item -ItemType Directory -Force -Path (Split-Path -Parent $Repo) | Out-Null
if (-not (Test-Path -LiteralPath (Join-Path $Repo ".git"))) {
  if (Test-Path -LiteralPath $Repo) {
    Write-Host ("Existing folder without .git - cloning into " + $Repo + "_tip")
    $Repo = Join-Path $env:USERPROFILE "Documents\HybridCut_tip"
  }
  git clone $RepoUrl $Repo
}
Set-Location -LiteralPath $Repo
git fetch origin
git checkout main
git pull origin main

$stampFile = Join-Path $Repo "SYNC_VERSION.txt"
$stamp = if (Test-Path -LiteralPath $stampFile) { (Get-Content -LiteralPath $stampFile -Raw).Trim() } else { "" }
Write-Host ("SRC: " + $Repo)
Write-Host ("SYNC_VERSION: " + $stamp)
if ($stamp -ne $TipStamp) {
  Write-Host ("WARN: expected " + $TipStamp + " - tip may not be pushed yet. Continuing with pulled tip.")
}

& .\install_to_videoeditor.ps1

$ve = Join-Path $env:USERPROFILE "Documents\Videoeditor\hybrid_cut"
$veStamp = if (Test-Path -LiteralPath (Join-Path $ve "SYNC_VERSION.txt")) {
  (Get-Content -LiteralPath (Join-Path $ve "SYNC_VERSION.txt") -Raw).Trim()
} else { "" }
Write-Host ("INSTALLED: " + $veStamp)
Write-Host "Open http://127.0.0.1:3847 then Ctrl+F5"
Set-Location -LiteralPath $ve
if (Test-Path -LiteralPath ".\start_hybrid_cuda.ps1") {
  .\start_hybrid_cuda.ps1
} else {
  .\run_hybrid.ps1
}
