# HybridCut simple-bg3 one-shot (Windows)
# Stop old server → pull GitHub → install → verify SYNC + dist asset → run
# ASCII-safe. Paste into PowerShell.

$ErrorActionPreference = "Stop"

Write-Host "=== HybridCut simple-bg3 install ==="

# 1) Stop anything on 3847
Get-NetTCPConnection -LocalPort 3847 -ErrorAction SilentlyContinue |
  ForEach-Object {
    try { Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue } catch {}
  }
Get-Process -Name python,uvicorn -ErrorAction SilentlyContinue |
  Where-Object { $_.Path -match "hybrid_cut|HybridCut|Videoeditor" } |
  ForEach-Object { try { Stop-Process -Id $_.Id -Force -ErrorAction SilentlyContinue } catch {} }

# 2) Pull tip from GitHub (source of truth)
$repo = Join-Path $env:USERPROFILE "Documents\HybridCut"
if (-not (Test-Path -LiteralPath (Join-Path $repo ".git"))) {
  Write-Host "Clone missing — cloning hevesitr/HybridCut ..."
  New-Item -ItemType Directory -Force -Path (Split-Path -Parent $repo) | Out-Null
  git clone https://github.com/hevesitr/HybridCut.git $repo
}
Set-Location -LiteralPath $repo
git fetch origin
git checkout main
git pull origin main

$stamp = (Get-Content -LiteralPath .\SYNC_VERSION.txt -Raw).Trim()
Write-Host ("REPO SYNC_VERSION: " + $stamp)
if ($stamp -ne "2026-10-12-simple-bg3") {
  Write-Error ("Expected 2026-10-12-simple-bg3, got: " + $stamp + " — push may still be pending; wait for GitHub tip or ask agent for PAT push.")
}

# 3) Install into Documents\Videoeditor\hybrid_cut (purges stale dist)
.\install_to_videoeditor.ps1

$ve = Join-Path $env:USERPROFILE "Documents\Videoeditor\hybrid_cut"
$veStamp = (Get-Content -LiteralPath (Join-Path $ve "SYNC_VERSION.txt") -Raw).Trim()
Write-Host ("INSTALLED SYNC_VERSION: " + $veStamp)
if ($veStamp -ne "2026-10-12-simple-bg3") {
  Write-Error ("Install stamp mismatch: " + $veStamp)
}

# 4) Verify dist asset name (must NOT be old look-peak / bg2 hashes)
$assets = Get-ChildItem -LiteralPath (Join-Path $ve "frontend\dist\assets") -Filter "index-*.js"
$js = $assets | Select-Object -First 1
if (-not $js) { Write-Error "No frontend dist JS" }
Write-Host ("DIST JS: " + $js.Name)
$banned = @("index-BGJ2h0CY.js", "index-fyrBYl2A.js", "index-DY2_6z5E.js")
if ($banned -contains $js.Name) {
  Write-Error ("Stale dist still present: " + $js.Name + " — purge failed; delete frontend\dist and re-run install.")
}
$sample = Get-Content -LiteralPath $js.FullName -Raw
if ($sample -match "AI sáv|AI SÁV|\+ V1 klip|\+ B-roll|tl-polish-btn") {
  Write-Error ("Dist still contains multi-track chrome: " + $js.Name)
}

# 5) Optional ResNet fp32 (better Max close-up on CPU)
$modelsVe = Join-Path $env:USERPROFILE "Documents\Videoeditor\models"
$resnet = Join-Path $modelsVe "rvm_resnet50_fp32.onnx"
if (-not (Test-Path -LiteralPath $resnet)) {
  Write-Host "TIP: for Max close-up quality on CPU, download ResNet:"
  Write-Host '  cd $env:USERPROFILE\Documents\HybridCut'
  Write-Host "  .\scripts\download_rvm.ps1 rvm_resnet50_fp32.onnx"
  Write-Host ("  Copy models\rvm_resnet50_fp32.onnx -> " + $modelsVe)
}

# 6) Run
Set-Location -LiteralPath $ve
$env:HYBRID_ORT_PROVIDER = "cpu"
Write-Host "Starting run_hybrid.ps1 ..."
Write-Host "Open http://127.0.0.1:3847 then Ctrl+F5 (hard refresh browser cache)"
Write-Host "Expect: SYNC 2026-10-12-simple-bg3 · only V1 · Cutout person silhouette"
.\run_hybrid.ps1
