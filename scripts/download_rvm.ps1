# Opt-in RVM ONNX download (PeterL1n RobustVideoMatting v1.0.0 release).
# Does NOT run automatically. User must invoke. Check upstream license before commercial use.

$ErrorActionPreference = "Stop"
$scriptDir = if ($PSScriptRoot) { $PSScriptRoot } else { Split-Path -Parent $MyInvocation.MyCommand.Path }
$Root = Split-Path -Parent $scriptDir
$models = Join-Path $Root "models"
New-Item -ItemType Directory -Force -Path $models | Out-Null

$name = if ($args.Count -gt 0) { $args[0] } else { "rvm_mobilenetv3_fp16.onnx" }
$url = "https://github.com/PeterL1n/RobustVideoMatting/releases/download/v1.0.0/$name"
$dest = Join-Path $models $name

Write-Host "Download: $url"
Write-Host "Dest:     $dest"
Write-Host "License:  follow upstream RVM / release terms (not redistributed by HybridCut by default)."

if (Test-Path -LiteralPath $dest) {
    Write-Host "Already exists — skip."
    Write-Host ("Set: `$env:HYBRID_RVM_ONNX = '" + $dest + "'")
    exit 0
}

Invoke-WebRequest -Uri $url -OutFile $dest
Write-Host "OK."
Write-Host ("Set before run_hybrid.ps1:")
Write-Host ("  `$env:HYBRID_RVM_ONNX = '" + $dest + "'")
Write-Host "  pip install onnxruntime-gpu   # Windows CUDA"
