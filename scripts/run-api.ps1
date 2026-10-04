$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $Root
$env:PYTHONPATH = Join-Path $Root "backend"
$env:HYBRID_HOST = "127.0.0.1"
$env:HYBRID_PORT = "3847"
Write-Host "HybridCut API  http://127.0.0.1:3847"
Write-Host "SYNC" (Get-Content (Join-Path $Root "SYNC_VERSION.txt") -Raw).Trim()
python -m hybrid_editor.main
