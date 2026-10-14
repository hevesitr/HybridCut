# HybridCut simple-bg3 one-shot (Windows)
# Prefer Agent Store copy (no PAT). Fallback: git pull GitHub tip.
# Copies -> Documents\Videoeditor\hybrid_cut, purges stale dist, verifies SYNC + UI.
# ASCII-safe. Paste into PowerShell.

$ErrorActionPreference = "Stop"
$TipStamp = "2026-10-14-restore-rvm-fast2"
$StoreId = "bc-41930eab-1501-4c19-acf3-0c9d63afbf4d"

Write-Host "=== HybridCut simple-bg3 install ==="

# 1) Stop anything on 3847
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

# 2) Resolve source: Agent Store first (no PAT), else Documents\HybridCut git pull
$candidates = @(
  (Join-Path $env:LOCALAPPDATA "Cursor\AgentStores\cursor_agent_stores\$StoreId\files\docs\hybrid-editor"),
  (Join-Path $env:LOCALAPPDATA "Cursor\AgentStores\cursor_agent_stores\$StoreId\files\docs\capcut-features\hybrid_cut"),
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
  Write-Host "Tip stamp not in Agent Store - pulling GitHub hevesitr/HybridCut ..."
  $repo = Join-Path $env:USERPROFILE "Documents\HybridCut"
  if (-not (Test-Path -LiteralPath (Join-Path $repo ".git"))) {
    New-Item -ItemType Directory -Force -Path (Split-Path -Parent $repo) | Out-Null
    git clone https://github.com/hevesitr/HybridCut.git $repo
  }
  Set-Location -LiteralPath $repo
  git fetch origin
  git checkout main
  git pull origin main
  $src = $repo
}

$stamp = Get-Stamp $src
Write-Host ("SRC: " + $src)
Write-Host ("SRC SYNC_VERSION: " + $stamp)
if ($stamp -ne $TipStamp) {
  Write-Error ("Expected " + $TipStamp + ", got: " + $stamp)
}

# 3) Install into Documents\Videoeditor\hybrid_cut (purges stale dist)
Set-Location -LiteralPath $src
& .\install_to_videoeditor.ps1

$ve = Join-Path $env:USERPROFILE "Documents\Videoeditor\hybrid_cut"
$veStamp = Get-Stamp $ve
Write-Host ("INSTALLED SYNC_VERSION: " + $veStamp)
if ($veStamp -ne $TipStamp) {
  Write-Error ("Install stamp mismatch: " + $veStamp)
}

# 4) Verify dist (must NOT be old look-peak / bg2 hashes; no AI SAV chrome)
$assets = Get-ChildItem -LiteralPath (Join-Path $ve "frontend\dist\assets") -Filter "index-*.js"
$js = $assets | Select-Object -First 1
if (-not $js) { Write-Error "No frontend dist JS" }
Write-Host ("DIST JS: " + $js.Name)
$banned = @("index-BGJ2h0CY.js", "index-fyrBYl2A.js", "index-DY2_6z5E.js")
if ($banned -contains $js.Name) {
  Write-Error ("Stale dist still present: " + $js.Name + " - purge failed; delete frontend\dist and re-run.")
}
$sample = Get-Content -LiteralPath $js.FullName -Raw
if ($sample -match "AI s-v|AI S-V|\+ V1 klip|\+ B-roll|tl-polish-btn") {
  Write-Error ("Dist still contains multi-track chrome: " + $js.Name)
}
Write-Host "VERIFY OK: SYNC + dist have no AI SAV / +V1 / +B-roll"

# 5) Optional ResNet tip
$modelsVe = Join-Path $env:USERPROFILE "Documents\Videoeditor\models"
$resnet = Join-Path $modelsVe "rvm_resnet50_fp32.onnx"
if (-not (Test-Path -LiteralPath $resnet)) {
  Write-Host "TIP: for Max close-up quality on CPU, download ResNet into Documents\Videoeditor\models\"
  Write-Host "  rvm_resnet50_fp32.onnx (via scripts\download_rvm.ps1 in the HybridCut clone)"
}

# 6) Run
Set-Location -LiteralPath $ve
$env:HYBRID_ORT_PROVIDER = "cpu"
Write-Host "Starting run_hybrid.ps1 ..."
Write-Host "Open http://127.0.0.1:3847 then Ctrl+F5"
Write-Host "Expect: SYNC 2026-10-14-restore-rvm-fast2 - only V1 - Cutout person silhouette"
.\run_hybrid.ps1
