# Sync HybridCut (docs/hybrid-editor) from Cursor Agent Store into
# Documents\Videoeditor\hybrid_cut  (nested under CapCut delivery — no root clash).
# ASCII-only. Safe to invoke via full path from ANY directory (including System32).
# Does NOT require Set-Location beforehand.
#
# CapCut root sync.ps1 owns Documents\Videoeditor — HybridCut lands in hybrid_cut/.

$ErrorActionPreference = "Stop"

$dst = Join-Path $env:USERPROFILE "Documents\Videoeditor\hybrid_cut"
$storeId = "bc-41930eab-1501-4c19-acf3-0c9d63afbf4d"
$scriptDir = if ($PSScriptRoot) { $PSScriptRoot } else { Split-Path -Parent $MyInvocation.MyCommand.Path }
$baseStores = Join-Path $env:LOCALAPPDATA "Cursor\AgentStores"

function Test-HybridSrc {
    param([string]$Path)
    if (-not $Path) { return $false }
    if (-not (Test-Path -LiteralPath $Path)) { return $false }
    return (Test-Path -LiteralPath (Join-Path $Path "backend\requirements.txt"))
}

function Add-Candidate {
    param(
        [System.Collections.Generic.List[string]]$List,
        [string]$Path
    )
    if ($Path -and -not $List.Contains($Path)) { $List.Add($Path) }
}

$candidates = New-Object System.Collections.Generic.List[string]
# Classic store id path
Add-Candidate $candidates (Join-Path $baseStores ("cursor_agent_stores\" + $storeId + "\files\docs\hybrid-editor"))
Add-Candidate $candidates (Join-Path $baseStores ($storeId + "\files\docs\hybrid-editor"))
# Wildcard store roots (layout variants)
Add-Candidate $candidates (Join-Path $baseStores "cursor_agent_stores\*\files\docs\hybrid-editor")
Add-Candidate $candidates (Join-Path $baseStores "*\files\docs\hybrid-editor")
# Sibling of capcut-features (same docs/ folder)
Add-Candidate $candidates (Join-Path (Split-Path -Parent $scriptDir) "hybrid-editor")
$parentName = Split-Path -Leaf (Split-Path -Parent $scriptDir)
if ($parentName -eq "capcut-features") {
    Add-Candidate $candidates (Join-Path (Split-Path -Parent (Split-Path -Parent $scriptDir)) "hybrid-editor")
}
# This script's own directory (when already inside hybrid-editor)
Add-Candidate $candidates $scriptDir

$src = $null
$tried = New-Object System.Collections.Generic.List[string]
foreach ($pattern in $candidates) {
    $tried.Add($pattern)
    $resolved = @()
    try {
        $resolved = @(Resolve-Path -Path $pattern -ErrorAction SilentlyContinue | ForEach-Object { $_.Path })
    } catch {
        $resolved = @()
    }
    foreach ($cPath in $resolved) {
        if (-not (Test-HybridSrc $cPath)) { continue }
        $uiMarker = Join-Path $cPath "frontend\dist\index.html"
        if (Test-Path -LiteralPath $uiMarker) {
            $src = $cPath
            break
        }
        if (-not $src) { $src = $cPath }
    }
    if ($src -and (Test-Path -LiteralPath (Join-Path $src "frontend\dist\index.html"))) { break }
}

# Crawl AgentStores for hybrid-editor if still missing
if (-not $src -and (Test-Path -LiteralPath $baseStores)) {
    $tried.Add((Join-Path $baseStores "**\hybrid-editor (crawl)"))
    $hits = Get-ChildItem -Path $baseStores -Directory -Filter "hybrid-editor" -Recurse -ErrorAction SilentlyContinue |
        Where-Object { Test-HybridSrc $_.FullName } |
        Select-Object -First 8
    foreach ($h in $hits) {
        $uiMarker = Join-Path $h.FullName "frontend\dist\index.html"
        if (Test-Path -LiteralPath $uiMarker) {
            $src = $h.FullName
            break
        }
        if (-not $src) { $src = $h.FullName }
    }
}

if (-not $src) {
    $capcutHybrid = Join-Path $baseStores ("cursor_agent_stores\" + $storeId + "\files\docs\capcut-features\sync_hybrid.ps1")
    $zipDocs = Join-Path $baseStores ("cursor_agent_stores\" + $storeId + "\files\docs\hybrid-editor-portable.zip")
    $zipCapcut = Join-Path $baseStores ("cursor_agent_stores\" + $storeId + "\files\docs\capcut-features\hybrid-editor-portable.zip")
    Write-Host ""
    Write-Host "HIBA / ERROR: HybridCut forras nem talalhato az Agent Store tukorben."
    Write-Host "Source tree not found. Tried:"
    foreach ($c in $tried) { Write-Host ("  " + $c) }
    Write-Host ""
    Write-Host "KOVETKEZO LEPESEK / EXACT NEXT STEPS (order A-D):"
    Write-Host "  A) CapCut-path hybrid helper (prefer):"
    Write-Host ('     & "' + $capcutHybrid + '"')
    Write-Host "  B) CapCut sync.ps1 (also copies HybridCut when sibling/zip available):"
    Write-Host ('     & "' + (Join-Path $baseStores ("cursor_agent_stores\" + $storeId + "\files\docs\capcut-features\sync.ps1")) + '"')
    Write-Host "  C) Manual zip extract to Documents\Videoeditor\hybrid_cut:"
    Write-Host ('     Expand-Archive -Path "' + $zipCapcut + '" -DestinationPath "' + $dst + '" -Force')
    Write-Host ('     # alt: "' + $zipDocs + '"')
    Write-Host "  D) Diagnostic:"
    Write-Host '     Get-ChildItem "$env:LOCALAPPDATA\Cursor\AgentStores" -Recurse -Filter hybrid-editor -Directory -ErrorAction SilentlyContinue'
    Write-Host '     Get-ChildItem "$env:LOCALAPPDATA\Cursor\AgentStores" -Recurse -Filter hybrid-editor-portable.zip -ErrorAction SilentlyContinue'
    Write-Error "HybridCut sync source missing."
}

New-Item -ItemType Directory -Force -Path $dst | Out-Null

Write-Host ("SRC: " + $src)
Write-Host ("DST: " + $dst)

# Mirror tree; skip heavy / local junk (venv, node_modules, pycache, bake outputs)
$excludeDirs = @("__pycache__", ".venv", "venv", "node_modules", ".git", "bake", ".pytest_cache")
$robolog = Join-Path $env:TEMP ("hybrid-sync-" + [guid]::NewGuid().ToString("N") + ".log")
$xdArgs = @()
foreach ($d in $excludeDirs) { $xdArgs += "/XD"; $xdArgs += $d }

# /E copy subdirs incl empty; /NFL /NDL quieter; /R:1 /W:1 quick retry
$rcArgs = @($src, $dst, "/E", "/R:1", "/W:1", "/NFL", "/NDL", "/NJH", "/NP", "/XF", "*.pyc") + $xdArgs + @("/LOG:" + $robolog)
& robocopy @rcArgs | Out-Null
$rc = $LASTEXITCODE
# robocopy: 0-7 = success-ish; >=8 = failure
if ($rc -ge 8) {
    Write-Host ("robocopy log: " + $robolog)
    Write-Error ("robocopy failed with exit code " + $rc)
}
Remove-Item -LiteralPath $robolog -Force -ErrorAction SilentlyContinue

# Ensure sample media exists even if cache/ was partially skipped
$sampleSrc = Join-Path $src "cache\sample_person.mp4"
$sampleDstDir = Join-Path $dst "cache"
$sampleDst = Join-Path $sampleDstDir "sample_person.mp4"
if (Test-Path -LiteralPath $sampleSrc) {
    New-Item -ItemType Directory -Force -Path $sampleDstDir | Out-Null
    Copy-Item -LiteralPath $sampleSrc -Destination $sampleDst -Force
}

$need = @(
    (Join-Path $dst "backend\requirements.txt"),
    (Join-Path $dst "backend\hybrid_editor\main.py"),
    (Join-Path $dst "frontend\dist\index.html"),
    (Join-Path $dst "SYNC_VERSION.txt"),
    (Join-Path $dst "sync.ps1"),
    (Join-Path $dst "run_hybrid.ps1"),
    (Join-Path $dst "README.md")
)
$missing = @()
foreach ($p in $need) {
    if (-not (Test-Path -LiteralPath $p)) { $missing += $p }
}
if ($missing.Count -gt 0) {
    Write-Host "Hianyzo fajlok / Missing files:"
    foreach ($m in $missing) { Write-Host ("  " + $m) }
    Write-Error "Sync incomplete - missing files listed above."
}

$verSrc = Join-Path $src "SYNC_VERSION.txt"
$verDst = Join-Path $dst "SYNC_VERSION.txt"
if (Test-Path -LiteralPath $verSrc) {
    Copy-Item -LiteralPath $verSrc -Destination $verDst -Force
}
$stamp = (Get-Content -LiteralPath $verDst -Raw).Trim()
Copy-Item -LiteralPath $verDst -Destination (Join-Path $dst "SYNC_VERSION") -Force

Write-Host ""
Write-Host ("SYNC OK -> " + $dst)
Write-Host ("SYNC_VERSION: " + $stamp)
Write-Host ""
Write-Host "Kovetkezo / Next (any directory):"
Write-Host '  cd $env:USERPROFILE\Documents\Videoeditor\hybrid_cut'
Write-Host "  .\run_hybrid.ps1"
Write-Host "Open: http://127.0.0.1:3847"
Write-Host ""
Write-Host "Megjegyzes: CapCut gyoker = Documents\Videoeditor ; HybridCut = ...\hybrid_cut"
Write-Host "NOTE: CapCut root = Documents\Videoeditor ; HybridCut = ...\hybrid_cut"
Write-Host "FIGYELEM: NE futtasd a pip/python parancsokat System32-bol."
Write-Host "WARN: Do NOT run pip/python from C:\WINDOWS\System32."
