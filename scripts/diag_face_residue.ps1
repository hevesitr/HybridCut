# HybridCut face-front / under-chin BG residue diagnostic (Windows / RTX local).
# ASCII-only. Does NOT tweak crush/threshold/erosion. Does NOT claim "javitva".
# Cloud Agent cannot run this on your RTX 3060 — you must execute locally.
#
# Prerequisite stamp: 2026-10-14-fix-shadow-fringe-fast2
#
# One-liner:
#   cd $env:USERPROFILE\Documents\Videoeditor\hybrid_cut
#   .\scripts\diag_face_residue.ps1 -Media "D:\path\to\clip.mp4" -T 1.0

param(
  [Parameter(Mandatory = $true)][string]$Media,
  [double]$T = 0.0,
  [int]$Frame = -1,
  [string]$InstallRoot = "",
  [string]$RoiFace = "",
  [string]$RoiChin = "",
  [string]$Mode = "gyors",
  [switch]$NoOfficialCompare,
  [switch]$NoPurge
)

$ErrorActionPreference = "Stop"
$TipStamp = "2026-10-14-fix-shadow-fringe-fast2"

function Resolve-HybridRoot([string]$Hint) {
  if ($Hint -and (Test-Path -LiteralPath (Join-Path $Hint "backend\hybrid_editor"))) {
    return (Resolve-Path -LiteralPath $Hint).Path
  }
  $scriptDir = $PSScriptRoot
  $up = Split-Path -Parent $scriptDir
  if (Test-Path -LiteralPath (Join-Path $up "backend\hybrid_editor")) {
    return $up
  }
  foreach ($c in @(
      (Join-Path $env:USERPROFILE "Documents\Videoeditor\hybrid_cut"),
      (Join-Path $env:USERPROFILE "Documents\HybridCut"),
      (Join-Path $env:USERPROFILE "Documents\videoeditor\hybrid_cut")
    )) {
    if (Test-Path -LiteralPath (Join-Path $c "backend\hybrid_editor")) { return $c }
  }
  throw "HybridCut/hybrid_cut root not found. Pass -InstallRoot."
}

$Root = Resolve-HybridRoot $InstallRoot
Write-Host "=== HybridCut diag_face_residue ==="
Write-Host ("InstallRoot=" + $Root)

$stampFile = Join-Path $Root "SYNC_VERSION.txt"
$stamp = ""
if (Test-Path -LiteralPath $stampFile) {
  $stamp = (Get-Content -LiteralPath $stampFile -Raw).Trim()
}
Write-Host ("SYNC_VERSION=" + $stamp)
if ($stamp -ne $TipStamp) {
  Write-Host ("WARNING: expected stamp " + $TipStamp + " before diagnosing fringe-fix failure.") -ForegroundColor Yellow
}

$pyCandidates = @(
  (Join-Path $Root ".venv\Scripts\python.exe"),
  (Join-Path (Split-Path -Parent $Root) ".venv\Scripts\python.exe"),
  (Join-Path $env:USERPROFILE "Documents\Videoeditor\.venv\Scripts\python.exe")
)
$Python = $null
foreach ($p in $pyCandidates) {
  if (Test-Path -LiteralPath $p) { $Python = $p; break }
}
if (-not $Python) {
  $cmd = Get-Command python -ErrorAction SilentlyContinue | Select-Object -First 1
  if ($cmd) { $Python = $cmd.Source }
}
if (-not $Python) { throw "python.exe not found" }
Write-Host ("python=" + $Python)

$env:PYTHONPATH = (Join-Path $Root "backend")
$cli = Join-Path $Root "scripts\diag_face_residue_cli.py"
if (-not (Test-Path -LiteralPath $cli)) {
  throw ("Missing " + $cli)
}

$argList = @($cli, "--media", $Media, "--install-root", $Root, "--mode", $Mode)
if ($Frame -ge 0) { $argList += @("--frame", "$Frame") }
else { $argList += @("--t", "$T") }
if ($RoiFace) { $argList += @("--roi-face", $RoiFace) }
if ($RoiChin) { $argList += @("--roi-chin", $RoiChin) }
if ($NoOfficialCompare) { $argList += "--no-official-compare" }
if ($NoPurge) { $argList += "--no-purge" }

Write-Host "NOTE: Cloud Agent did NOT run on your RTX 3060."
Write-Host ("Running: " + $Python + " " + ($argList -join " "))
& $Python @argList
if ($LASTEXITCODE -ne 0) {
  Write-Host ("diag_face_residue FAILED exit=" + $LASTEXITCODE) -ForegroundColor Red
  exit $LASTEXITCODE
}
Write-Host "OK — see cache\diag_face_residue\<timestamp>\report.json + PNGs"
Write-Host "Docs: docs\DIAG_FACE_RESIDUE.md"
