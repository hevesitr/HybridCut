# HybridCut simple-bg6 one-shot (Windows)
# Prefer Agent Store copy (no PAT). Fallback: git pull GitHub tip.
# Copies -> Documents\Videoeditor\hybrid_cut, purges stale dist, downloads ResNet if missing.
# ASCII-only (no em-dash / accented chars) so Windows PowerShell parsers do not break.

$ErrorActionPreference = "Stop"
$TipStamp = "2026-10-13-preview-fast"
$StoreId = "bc-41930eab-1501-4c19-acf3-0c9d63afbf4d"

Write-Host "=== HybridCut simple-bg6 install ==="

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

# Ensure ResNet fp32 for Max / close-up CPU recovery
$modelsHybrid = Join-Path $src "models"
New-Item -ItemType Directory -Force -Path $modelsHybrid | Out-Null
$resnet = Join-Path $modelsHybrid "rvm_resnet50_fp32.onnx"
if (-not (Test-Path -LiteralPath $resnet)) {
  Write-Host "Downloading rvm_resnet50_fp32.onnx (PeterL1n RVM) ..."
  $dl = Join-Path $src "scripts\download_rvm.ps1"
  if (Test-Path -LiteralPath $dl) {
    & $dl rvm_resnet50_fp32.onnx
  } else {
    $url = "https://github.com/PeterL1n/RobustVideoMatting/releases/download/v1.0.0/rvm_resnet50_fp32.onnx"
    Invoke-WebRequest -Uri $url -OutFile $resnet
  }
}
$modelsVe = Join-Path $env:USERPROFILE "Documents\Videoeditor\models"
New-Item -ItemType Directory -Force -Path $modelsVe | Out-Null
if (Test-Path -LiteralPath $resnet) {
  Copy-Item -LiteralPath $resnet -Destination (Join-Path $modelsVe "rvm_resnet50_fp32.onnx") -Force
  Write-Host ("ResNet OK: " + (Join-Path $modelsVe "rvm_resnet50_fp32.onnx"))
}

Set-Location -LiteralPath $src
& .\install_to_videoeditor.ps1

$ve = Join-Path $env:USERPROFILE "Documents\Videoeditor\hybrid_cut"
$veStamp = Get-Stamp $ve
Write-Host ("INSTALLED SYNC_VERSION: " + $veStamp)
if ($veStamp -ne $TipStamp) {
  Write-Error ("Install stamp mismatch: " + $veStamp)
}

$assets = Get-ChildItem -LiteralPath (Join-Path $ve "frontend\dist\assets") -Filter "index-*.js"
$js = $assets | Select-Object -First 1
if (-not $js) { Write-Error "No frontend dist JS" }
Write-Host ("DIST JS: " + $js.Name)
$banned = @("index-BGJ2h0CY.js", "index-fyrBYl2A.js", "index-DY2_6z5E.js", "index-DakKRMds.js", "index-7OPITa-N.js", "index-3rVnbc6C.js")
if ($banned -contains $js.Name) {
  Write-Error ("Stale dist still present: " + $js.Name + " - purge failed; delete frontend\dist and re-run.")
}
$sample = Get-Content -LiteralPath $js.FullName -Raw
# ASCII-safe banned chrome check (accented AI sav variants matched loosely)
if ($sample -match "AI [Ss].[Vv]|\+ V1 klip|\+ B-roll|tl-polish-btn") {
  Write-Error ("Dist still contains multi-track chrome: " + $js.Name)
}
Write-Host "VERIFY OK: SYNC + dist have no AI SAV / +V1 / +B-roll"

Set-Location -LiteralPath $ve
$env:HYBRID_ORT_PROVIDER = "cpu"
Write-Host "Starting run_hybrid.ps1 ..."
Write-Host "Open http://127.0.0.1:3847 then Ctrl+F5"
Write-Host "Expect: SYNC 2026-10-13-preview-fast - only V1 - Cutout person silhouette"
Write-Host "Gyors stays when you click it. Auto Max only once per open. Less export shadow on CPU."
.\run_hybrid.ps1
