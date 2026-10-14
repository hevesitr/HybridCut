# HybridCut full-body-fast - local path finder (Agent Store lag / no Context).
# ASCII-only. Tries several known local mirrors, then falls back to GitHub.
# Paste into Windows PowerShell.

$ErrorActionPreference = "Stop"
$TipStamp = "2026-10-14-restore-rvm-fast2"
$StoreId = "bc-41930eab-1501-4c19-acf3-0c9d63afbf4d"

Write-Host "=== HybridCut full-body-fast (local finder) ==="

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

$base = Join-Path $env:LOCALAPPDATA "Cursor\AgentStores\cursor_agent_stores\$StoreId"
$candidates = @(
  (Join-Path $base "files\docs\hybrid-editor"),
  (Join-Path $base "files\docs\capcut-features\hybrid_cut"),
  (Join-Path $base "docs\hybrid-editor"),
  (Join-Path $base "docs\capcut-features\hybrid_cut"),
  (Join-Path $env:USERPROFILE "Documents\HybridCut"),
  (Join-Path $env:USERPROFILE "Documents\HybridCut_tip"),
  (Join-Path $env:USERPROFILE "Documents\Videoeditor\hybrid_cut")
)

$src = $null
foreach ($c in $candidates) {
  if (Test-HybridSrc $c) {
    $st = Get-Stamp $c
    Write-Host ("CANDIDATE: " + $c + " stamp=" + $st)
    if ($st -eq $TipStamp) { $src = $c; break }
    if (-not $src) { $src = $c }
  }
}

if (-not $src -or (Get-Stamp $src) -ne $TipStamp) {
  Write-Host "Tip not in Agent Store / local mirrors - switching to GitHub pull ..."
  $gh = Join-Path $env:USERPROFILE "Documents\HybridCut"
  if (-not (Test-Path -LiteralPath (Join-Path $gh ".git"))) {
    New-Item -ItemType Directory -Force -Path (Split-Path -Parent $gh) | Out-Null
    git clone https://github.com/hevesitr/HybridCut.git $gh
  }
  Set-Location -LiteralPath $gh
  git fetch origin
  git checkout main
  git pull origin main
  $src = $gh
}

Write-Host ("SRC: " + $src + " stamp=" + (Get-Stamp $src))
Set-Location -LiteralPath $src
& .\install_to_videoeditor.ps1
$ve = Join-Path $env:USERPROFILE "Documents\Videoeditor\hybrid_cut"
Write-Host ("INSTALLED SYNC: " + (Get-Stamp $ve))
Write-Host "Open http://127.0.0.1:3847 then Ctrl+F5"
Set-Location -LiteralPath $ve
if (Test-Path -LiteralPath ".\start_hybrid_cuda.ps1") { .\start_hybrid_cuda.ps1 } else { .\run_hybrid.ps1 }
