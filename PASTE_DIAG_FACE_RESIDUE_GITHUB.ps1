# HybridCut diag-face-auto-roi - GitHub checkout + paste into Videoeditor\hybrid_cut
# Stamp: 2026-10-14-fix-shadow-fringe-fast2 (soft Gyors unchanged)
# Branch: cursor/diag-face-auto-roi-6533
# Feature: person+residue auto ROI (no manual Paint ROI)
# ASCII-only. Does not claim local RTX proof / "javitva".

$ErrorActionPreference = "Stop"
$Branch = "cursor/diag-face-auto-roi-6533"
$TipStamp = "2026-10-14-fix-shadow-fringe-fast2"
$Repo = "https://github.com/hevesitr/HybridCut.git"

Write-Host "=== HybridCut diag-face-auto-roi (GitHub) ==="
Write-Host "Cloud Agent did NOT run on your RTX 3060."

$Hybrid = Join-Path $env:USERPROFILE "Documents\HybridCut"
$Dest = Join-Path $env:USERPROFILE "Documents\Videoeditor\hybrid_cut"

if (-not (Test-Path -LiteralPath $Hybrid)) {
  git clone $Repo $Hybrid
}
Push-Location $Hybrid
try {
  git fetch origin
  git checkout $Branch
  git pull origin $Branch
} finally {
  Pop-Location
}

$stamp = (Get-Content -LiteralPath (Join-Path $Hybrid "SYNC_VERSION.txt") -Raw).Trim()
Write-Host ("SYNC_VERSION=" + $stamp)
if ($stamp -ne $TipStamp) {
  Write-Host ("WARNING: expected stamp " + $TipStamp) -ForegroundColor Yellow
}

if (-not (Test-Path -LiteralPath $Dest)) {
  New-Item -ItemType Directory -Force -Path $Dest | Out-Null
}

$inst = Join-Path $Hybrid "install_to_videoeditor.ps1"
if (Test-Path -LiteralPath $inst) {
  Push-Location $Hybrid
  try { & $inst } finally { Pop-Location }
} else {
  Write-Host "Copy backend/scripts/docs manually - install_to_videoeditor.ps1 missing"
}

Write-Host ""
Write-Host "Run diagnostic (no manual ROI):"
Write-Host ('  cd "' + $Dest + '"')
Write-Host '  .\scripts\diag_face_residue.ps1 -Media "C:\29308762a.webm" -T 1.0'
Write-Host "Docs: docs\DIAG_FACE_RESIDUE.md"
