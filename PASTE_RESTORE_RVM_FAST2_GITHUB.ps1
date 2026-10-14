# HybridCut restore-rvm-fast2 - GitHub pull (honest Max CPU ETA + light bake).
# ASCII-only. Paste into Windows PowerShell.
# Soft Gyors alpha kept. CUDA only if probe OK (push != GPU proof).

$ErrorActionPreference = "Stop"
$TipStamp = "2026-10-14-restore-rvm-fast2"
$Branch = "cursor/restore-rvm-fast2-b680"
$RepoUrl = "https://github.com/hevesitr/HybridCut.git"
$Repo = Join-Path $env:USERPROFILE "Documents\HybridCut"

Write-Host "=== HybridCut restore-rvm-fast2 (GitHub) ==="
Write-Host ("Branch: " + $Branch + " stamp=" + $TipStamp)

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
git checkout $Branch
if ($LASTEXITCODE -ne 0) {
  Write-Host "Branch missing locally - trying origin tip..."
  git checkout -B $Branch "origin/$Branch"
}
git pull origin $Branch

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
Write-Host "Expect: Max CPU light~640; ETA ~2 perc for 10s@24 (not fake 49s); soft Gyors OK"
Write-Host "Heavy polish (old ~4 min): `$env:HYBRID_CPU_MAX_HEAVY_POLISH='1'"
Write-Host "Sharper Max long: `$env:HYBRID_CPU_MAX_LONG='720'"
Set-Location -LiteralPath $ve
if (Test-Path -LiteralPath ".\start_hybrid_cuda.ps1") { .\start_hybrid_cuda.ps1 } else { .\run_hybrid.ps1 }
