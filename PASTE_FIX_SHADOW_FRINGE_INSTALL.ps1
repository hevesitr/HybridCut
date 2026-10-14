# HybridCut fix-shadow-fringe-fast2 one-shot (Windows)
# Stamp: 2026-10-14-fix-shadow-fringe-fast2
# Branch: cursor/fix-shadow-fringe-fast2-2eca
# Max ETA honesty (fast2) + BG residue strip fix. Soft hair; both people. ASCII-only.

$ErrorActionPreference = "Stop"
$TipStamp = "2026-10-14-fix-shadow-fringe-fast2"
$Branch = "cursor/fix-shadow-fringe-fast2-2eca"
$StoreId = "bc-41930eab-1501-4c19-acf3-0c9d63afbf4d"

Write-Host "=== HybridCut fix-shadow-fringe-fast2 install ==="

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
Write-Host "Expect: soft cutout without BG residue strips; honest Max ETA (fast2); both people kept"
Write-Host "Diag: `$env:HYBRID_DIAG_SHADOW='1'; `$env:HYBRID_DIAG_DIR=`"$env:USERPROFILE\Documents\HybridCut_diag`""
Write-Host "See docs\fix-shadow-fringe.md"
Set-Location -LiteralPath $ve
