# HybridCut restore-rvm-fast2 one-shot (Windows)
# Prefer Agent Store copy. Fallback: git pull feature branch.
# Max CPU: MobileNet~640 light (soft alpha). Honest ETA. ASCII-only.

$ErrorActionPreference = "Stop"
$TipStamp = "2026-10-14-restore-rvm-fast2"
$Branch = "cursor/restore-rvm-fast2-b680"
$StoreId = "bc-41930eab-1501-4c19-acf3-0c9d63afbf4d"

Write-Host "=== HybridCut restore-rvm-fast2 install ==="

Get-NetTCPConnection -LocalPort 3847 -ErrorAction SilentlyContinue |
  ForEach-Object {
    try { Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue } catch {}
  }
Get-Process -Name python,uvicorn -ErrorAction SilentlyContinue |
  Where-Object { $_.Path -match "hybrid_cut|HybridCut|Videoeditor" } |
  ForEach-Object { try { Stop-Process -Id $_.Id -Force -ErrorAction SilentlyContinue } catch {} }

function Test-HybridSrc([string]$Path) {
  if (-not $Path -or -not (Test-Path -LiteralPath $Path)) { return $false }
  return (Test-Path -LiteralPath (Join-Path $Path "backend\requirements.txt")) -and
         (Test-Path -LiteralPath (Join-Path $Path "frontend\dist\index.html")) -and
         (Test-Path -LiteralPath (Join-Path $Path "install_to_videoeditor.ps1"))
}

function Get-Stamp([string]$Root) {
  $f = Join-Path $Root "SYNC_VERSION.txt"
  if (-not (Test-Path -LiteralPath $f)) { return "" }
  return (Get-Content -LiteralPath $f -Raw).Trim()
}

$candidates = @(
  (Join-Path $env:LOCALAPPDATA "Cursor\AgentStores\cursor_agent_stores\$StoreId\files\docs\hybrid-editor"),
  (Join-Path $env:USERPROFILE "Documents\HybridCut")
)

$src = $null
foreach ($c in $candidates) {
  if (Test-HybridSrc $c) {
    $st = Get-Stamp $c
    Write-Host ("CANDIDATE: " + $c + " stamp=" + $st)
    if ($st -eq $TipStamp) { $src = $c; break }
  }
}

if (-not $src) {
  Write-Host "Tip stamp not in Agent Store - pulling GitHub feature branch ..."
  $repo = Join-Path $env:USERPROFILE "Documents\HybridCut"
  if (-not (Test-Path -LiteralPath (Join-Path $repo ".git"))) {
    New-Item -ItemType Directory -Force -Path (Split-Path -Parent $repo) | Out-Null
    git clone https://github.com/hevesitr/HybridCut.git $repo
  }
  Set-Location -LiteralPath $repo
  git fetch origin
  git checkout $Branch
  if ($LASTEXITCODE -ne 0) {
    git checkout -B $Branch "origin/$Branch"
  }
  git pull origin $Branch
  $src = $repo
}

$stamp = Get-Stamp $src
Write-Host ("SRC: " + $src)
Write-Host ("SRC SYNC_VERSION: " + $stamp)
if ($stamp -ne $TipStamp) {
  Write-Error ("Expected " + $TipStamp + ", got: " + $stamp)
}

& (Join-Path $src "install_to_videoeditor.ps1")
$ve = Join-Path $env:USERPROFILE "Documents\Videoeditor\hybrid_cut"
Write-Host ("INSTALLED: " + (Get-Content -LiteralPath (Join-Path $ve "SYNC_VERSION.txt") -Raw).Trim())
Write-Host "Open http://127.0.0.1:3847 then Ctrl+F5"
Write-Host "Expect: SYNC 2026-10-14-restore-rvm-fast2 - Max CPU light~640 - ETA ~2 perc/10s"
Write-Host "Tune long: `$env:HYBRID_CPU_MAX_LONG='720'"
Write-Host "Old heavy polish: `$env:HYBRID_CPU_MAX_HEAVY_POLISH='1'"
Set-Location -LiteralPath $ve
if (Test-Path -LiteralPath ".\start_hybrid_cuda.ps1") { .\start_hybrid_cuda.ps1 } else { .\run_hybrid.ps1 }
