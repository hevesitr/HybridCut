# HybridCut dev: API :3847 + Vite :3848
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $Root

$env:PYTHONPATH = Join-Path $Root "backend"
$env:HYBRID_HOST = "127.0.0.1"
$env:HYBRID_PORT = "3847"

Write-Host "SYNC:" (Get-Content (Join-Path $Root "SYNC_VERSION.txt") -Raw).Trim()
Write-Host "Starting API on http://127.0.0.1:3847 ..."

Start-Process -FilePath "python" -ArgumentList "-m","hybrid_editor.main" -WorkingDirectory $Root -NoNewWindow

Set-Location (Join-Path $Root "frontend")
if (-not (Test-Path "node_modules")) { npm install }
npm run dev
