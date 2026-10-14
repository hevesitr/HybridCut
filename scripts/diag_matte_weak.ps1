# HybridCut diagnostic helper — "Maszk gyenge" / empty preview / slow export.
# ASCII-only. Opt-in env flags; off by default. Does not change matte quality path.
# Usage (from HybridCut or Videoeditor\hybrid_cut root):
#   .\scripts\diag_matte_weak.ps1
#   .\run_hybrid.ps1
# Then reproduce: Megnyitas -> Elonezet (Gyors) / Export. Watch API console for:
#   DIAG_MATTE_WEAK ...
#   DIAG_ALPHA_DUMP ...
#   DIAG_EXPORT_TIMING ...
# Disable: close shell or Unset-Item Env:HYBRID_DIAG_*

$ErrorActionPreference = "Stop"

$env:HYBRID_DIAG_MATTE = "1"
$env:HYBRID_DIAG_ALPHA_DUMP = "1"
$env:HYBRID_DIAG_EXPORT_TIMING = "1"
# Also enable existing bake alpha PNG dumps under bgcut/alpha when exporting:
$env:HYBRID_BGCUT_DUMP_ALPHA = "1"

if (-not $env:HYBRID_DIAG_DIR -or -not $env:HYBRID_DIAG_DIR.Trim()) {
  $tmp = if ($env:TEMP) { $env:TEMP } else { $env:TMPDIR }
  if (-not $tmp) { $tmp = Join-Path $env:USERPROFILE "AppData\Local\Temp" }
  $env:HYBRID_DIAG_DIR = Join-Path $tmp "hybridcut_diag"
}
New-Item -ItemType Directory -Force -Path $env:HYBRID_DIAG_DIR | Out-Null
New-Item -ItemType Directory -Force -Path (Join-Path $env:HYBRID_DIAG_DIR "alpha") | Out-Null

Write-Host "=== HybridCut matte/export diagnostics ENABLED ==="
Write-Host ("HYBRID_DIAG_MATTE=" + $env:HYBRID_DIAG_MATTE)
Write-Host ("HYBRID_DIAG_ALPHA_DUMP=" + $env:HYBRID_DIAG_ALPHA_DUMP)
Write-Host ("HYBRID_DIAG_EXPORT_TIMING=" + $env:HYBRID_DIAG_EXPORT_TIMING)
Write-Host ("HYBRID_BGCUT_DUMP_ALPHA=" + $env:HYBRID_BGCUT_DUMP_ALPHA)
Write-Host ("HYBRID_DIAG_DIR=" + $env:HYBRID_DIAG_DIR)
Write-Host ""
Write-Host "Next: start HybridCut in THIS shell (run_hybrid.ps1 / start_hybrid_cuda.ps1)."
Write-Host "Logs: look for DIAG_MATTE_WEAK / DIAG_EXPORT_TIMING in the API console."
Write-Host "PNG dumps: HYBRID_DIAG_DIR\alpha\*_raw.png (preview weak/empty path)."
Write-Host "Docs: docs\RESTORE_RVM_DIAG.md"
Write-Host ""
Write-Host "Reversible: open a new PowerShell without this script to run clean."
