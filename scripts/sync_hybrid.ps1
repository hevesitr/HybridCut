# Sync HybridCut into Documents\Videoeditor\hybrid_cut (+ root run_hybrid.ps1).
# ASCII-only. Safe from ANY cwd (including System32).
# Prefer nested capcut-features\hybrid_cut (stale-mirror friendly).
# CapCut sync.ps1 may also deliver this tree - this script is a standalone fallback.
#
# PASTE NOW:
#   & "$env:LOCALAPPDATA\Cursor\AgentStores\cursor_agent_stores\bc-41930eab-1501-4c19-acf3-0c9d63afbf4d\files\docs\capcut-features\sync_hybrid.ps1"
#   cd $env:USERPROFILE\Documents\Videoeditor
#   Get-Content .\hybrid_cut\SYNC_VERSION.txt
#   # expect tip stamp: 2026-10-13-simple-bg7
#   .\run_hybrid.ps1

$ErrorActionPreference = "Stop"

# Tip this script MUST install. Stale AgentStores (run-ps1 / rvm-back) are rejected.
$TipStamp = "2026-10-13-simple-bg7"
$StaleStamps = @(
    "2026-10-11-run-ps1",
    "2026-10-11-rvm-back",
    "2026-10-11-matte-cpu2",
    "2026-10-11-cpu-matte",
    "2026-10-12-simple-bg"
)

$storeId = "bc-41930eab-1501-4c19-acf3-0c9d63afbf4d"
$videoeditor = Join-Path $env:USERPROFILE "Documents\Videoeditor"
$dst = Join-Path $videoeditor "hybrid_cut"
$scriptDir = if ($PSScriptRoot) { $PSScriptRoot } else { Split-Path -Parent $MyInvocation.MyCommand.Path }
$baseStores = Join-Path $env:LOCALAPPDATA "Cursor\AgentStores"

function New-AsciiTempPath {
    param([string]$Suffix = ".log")
    $leaf = [guid]::NewGuid().ToString("N") + $Suffix
    return [System.IO.Path]::Combine([System.IO.Path]::GetTempPath(), $leaf)
}

function Remove-TempQuiet {
    param([string]$Path)
    if (-not $Path) { return }
    try {
        if (Test-Path -LiteralPath $Path) {
            Remove-Item -LiteralPath $Path -Force -ErrorAction Stop
        }
    } catch {
        # Never fail sync on temp log cleanup (8.3 / accented profile paths).
    }
}

function Test-HybridSrc {
    param([string]$Path)
    if (-not $Path) { return $false }
    if (-not (Test-Path -LiteralPath $Path)) { return $false }
    return (Test-Path -LiteralPath (Join-Path $Path "backend\requirements.txt"))
}

function Get-SrcStamp {
    param([string]$Path)
    if (-not $Path) { return $null }
    $p = Join-Path $Path "SYNC_VERSION.txt"
    if (-not (Test-Path -LiteralPath $p)) {
        $p = Join-Path $Path "SYNC_VERSION"
    }
    if (-not (Test-Path -LiteralPath $p)) { return $null }
    try {
        return (Get-Content -LiteralPath $p -Raw).Trim()
    } catch {
        return $null
    }
}

function Test-TipStamp {
    param([string]$Stamp)
    if (-not $Stamp) { return $false }
    return ($Stamp -eq $TipStamp)
}

function Find-ZipCandidates {
    $zips = New-Object System.Collections.Generic.List[string]
    foreach ($z in @(
        (Join-Path $scriptDir "hybrid-editor-portable.zip"),
        (Join-Path (Split-Path -Parent $scriptDir) "hybrid-editor-portable.zip"),
        (Join-Path $baseStores ("cursor_agent_stores\" + $storeId + "\files\docs\capcut-features\hybrid-editor-portable.zip")),
        (Join-Path $baseStores ("cursor_agent_stores\" + $storeId + "\files\docs\hybrid-editor-portable.zip"))
    )) {
        if ($z -and (Test-Path -LiteralPath $z)) { $zips.Add($z) }
    }
    if (Test-Path -LiteralPath $baseStores) {
        Get-ChildItem -Path $baseStores -Filter "hybrid-editor-portable.zip" -Recurse -ErrorAction SilentlyContinue |
            Select-Object -First 5 |
            ForEach-Object { if (-not $zips.Contains($_.FullName)) { $zips.Add($_.FullName) } }
    }
    return $zips
}

function Expand-HybridZip {
    param([string]$ZipPath, [string]$Dest)
    Write-Host ("Extracting portable zip: " + $ZipPath)
    $tmp = New-AsciiTempPath -Suffix ""
    New-Item -ItemType Directory -Force -Path $tmp | Out-Null
    Expand-Archive -LiteralPath $ZipPath -DestinationPath $tmp -Force

    $copyFrom = $null
    foreach ($innerName in @("hybrid_cut", "hybrid-editor")) {
        $inner = Join-Path $tmp $innerName
        if (Test-HybridSrc $inner) { $copyFrom = $inner; break }
    }
    if (-not $copyFrom) {
        if (Test-HybridSrc $tmp) {
            $copyFrom = $tmp
        } else {
            $hit = Get-ChildItem -Path $tmp -Directory -Recurse -ErrorAction SilentlyContinue |
                Where-Object { Test-HybridSrc $_.FullName } |
                Select-Object -First 1
            if ($hit) { $copyFrom = $hit.FullName }
        }
    }
    if (-not $copyFrom) {
        Remove-TempQuiet -Path $tmp
        try { if (Test-Path -LiteralPath $tmp) { Remove-Item -LiteralPath $tmp -Recurse -Force -ErrorAction Stop } } catch { }
        Write-Error ("Zip did not contain hybrid_cut/hybrid-editor tree: " + $ZipPath)
    }

    New-Item -ItemType Directory -Force -Path $Dest | Out-Null
    $excludeDirs = @("__pycache__", ".venv", "venv", "node_modules", ".git", "bake", ".pytest_cache")
    $robolog = New-AsciiTempPath -Suffix ".log"
    $xdArgs = @()
    foreach ($d in $excludeDirs) { $xdArgs += "/XD"; $xdArgs += $d }
    $rcArgs = @($copyFrom, $Dest, "/E", "/R:1", "/W:1", "/NFL", "/NDL", "/NJH", "/NP", "/XF", "*.pyc") + $xdArgs + @("/LOG:" + $robolog)
    & robocopy @rcArgs | Out-Null
    $rc = $LASTEXITCODE
    Remove-TempQuiet -Path $robolog
    try { if (Test-Path -LiteralPath $tmp) { Remove-Item -LiteralPath $tmp -Recurse -Force -ErrorAction Stop } } catch { }
    if ($rc -ge 8) {
        Write-Error ("robocopy from zip failed with exit code " + $rc)
    }
}

function Find-HybridSrc {
    $tried = New-Object System.Collections.Generic.List[string]
    $candidates = New-Object System.Collections.Generic.List[string]
    $patterns = @(
        (Join-Path $scriptDir "hybrid_cut"),
        (Join-Path (Split-Path -Parent $scriptDir) "hybrid-editor"),
        (Join-Path $baseStores ("cursor_agent_stores\" + $storeId + "\files\docs\capcut-features\hybrid_cut")),
        (Join-Path $baseStores ("cursor_agent_stores\" + $storeId + "\files\docs\hybrid-editor")),
        (Join-Path $baseStores ($storeId + "\files\docs\capcut-features\hybrid_cut")),
        (Join-Path $baseStores ($storeId + "\files\docs\hybrid-editor")),
        (Join-Path $baseStores "cursor_agent_stores\*\files\docs\capcut-features\hybrid_cut"),
        (Join-Path $baseStores "cursor_agent_stores\*\files\docs\hybrid-editor"),
        (Join-Path $scriptDir "hybrid-editor")
    )

    foreach ($pattern in $patterns) {
        $tried.Add($pattern)
        $resolved = @()
        try {
            $resolved = @(Resolve-Path -Path $pattern -ErrorAction SilentlyContinue | ForEach-Object { $_.Path })
        } catch {
            $resolved = @()
        }
        foreach ($c in $resolved) {
            if (-not (Test-HybridSrc $c)) { continue }
            if (-not $candidates.Contains($c)) { $candidates.Add($c) }
        }
    }

    if (Test-Path -LiteralPath $baseStores) {
        $tried.Add((Join-Path $baseStores "**\hybrid_cut|hybrid-editor (crawl)"))
        $hits = @()
        $hits += Get-ChildItem -Path $baseStores -Directory -Filter "hybrid_cut" -Recurse -ErrorAction SilentlyContinue |
            Where-Object { Test-HybridSrc $_.FullName } |
            Select-Object -First 8
        $hits += Get-ChildItem -Path $baseStores -Directory -Filter "hybrid-editor" -Recurse -ErrorAction SilentlyContinue |
            Where-Object { Test-HybridSrc $_.FullName } |
            Select-Object -First 8
        foreach ($h in $hits) {
            if (-not $candidates.Contains($h.FullName)) { $candidates.Add($h.FullName) }
        }
    }

    # Prefer tip stamp + UI dist. Never pick stale run-ps1 / rvm-back when tip exists.
    $tipHits = New-Object System.Collections.Generic.List[string]
    $otherHits = New-Object System.Collections.Generic.List[string]
    foreach ($c in $candidates) {
        $stamp = Get-SrcStamp $c
        $uiMarker = Join-Path $c "frontend\dist\index.html"
        $hasUi = Test-Path -LiteralPath $uiMarker
        if (Test-TipStamp $stamp) {
            if ($hasUi) { $tipHits.Insert(0, $c) } else { $tipHits.Add($c) }
        } elseif ($stamp -and ($StaleStamps -contains $stamp)) {
            Write-Host ("SKIP stale SRC (" + $stamp + "): " + $c)
        } else {
            if ($hasUi) { $otherHits.Insert(0, $c) } else { $otherHits.Add($c) }
        }
    }

    if ($tipHits.Count -gt 0) {
        return @{ Src = $tipHits[0]; Tried = $tried; Stamp = (Get-SrcStamp $tipHits[0]) }
    }

    # No tip tree — report stale finds so user refreshes Agent Store.
    if ($otherHits.Count -gt 0) {
        $st = Get-SrcStamp $otherHits[0]
        Write-Host ""
        Write-Host ("HIBA: tip " + $TipStamp + " nincs a helyi Agent Store-ban.")
        Write-Host ("Talalt regi forras: " + $otherHits[0] + " (SYNC=" + $st + ")")
        Write-Host "Nyisd ujra a Cursor-t / varj amig a Cloud Agent Store frissul, majd futtasd ujra."
        Write-Error ("Tip stamp missing locally — refuse to install stale " + $st)
    }

    return @{ Src = $null; Tried = $tried; Stamp = $null }
}

function Assert-HybridDst {
    param([string]$Dest, [string]$ExpectedStamp)
    $need = @(
        (Join-Path $Dest "backend\requirements.txt"),
        (Join-Path $Dest "backend\hybrid_editor\main.py"),
        (Join-Path $Dest "frontend\dist\index.html"),
        (Join-Path $Dest "SYNC_VERSION.txt"),
        (Join-Path $Dest "run_hybrid.ps1"),
        (Join-Path $Dest "README.md")
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
    $verDst = Join-Path $Dest "SYNC_VERSION.txt"
    # Force tip stamp onto DST — never leave an older SYNC from a partial robocopy.
    Set-Content -LiteralPath $verDst -Value ($ExpectedStamp + "`n") -Encoding ascii -NoNewline
    Copy-Item -LiteralPath $verDst -Destination (Join-Path $Dest "SYNC_VERSION") -Force
    $stamp = (Get-Content -LiteralPath $verDst -Raw).Trim()
    if ($stamp -ne $ExpectedStamp) {
        Write-Error ("SYNC_VERSION mismatch after sync: got '" + $stamp + "' expected '" + $ExpectedStamp + "'")
    }
    # Refuse obvious stale UI markers (AI SÁV lane in built JS of old tips).
    $distJs = Get-ChildItem -Path (Join-Path $Dest "frontend\dist\assets") -Filter "index-*.js" -ErrorAction SilentlyContinue |
        Select-Object -First 1
    if ($distJs) {
        $sample = Get-Content -LiteralPath $distJs.FullName -Raw -ErrorAction SilentlyContinue
        if ($sample -and ($sample -match "tl-polish-btn" -or $sample -match "renderLane\(v2")) {
            Write-Error ("DST dist still looks like AI-sav tip (" + $distJs.Name + ") — Agent Store stale; re-open Cursor.")
        }
        Write-Host ("DIST: " + $distJs.Name)
    }
    return $stamp
}

function Install-RootLauncher {
    param([string]$HybridRoot)
    New-Item -ItemType Directory -Force -Path $videoeditor | Out-Null
    $inner = Join-Path $HybridRoot "run_hybrid.ps1"
    $rootLauncher = Join-Path $scriptDir "run_hybrid.ps1"
    $dstLauncher = Join-Path $videoeditor "run_hybrid.ps1"
    if (Test-Path -LiteralPath $rootLauncher) {
        Copy-Item -LiteralPath $rootLauncher -Destination $dstLauncher -Force
    } elseif (Test-Path -LiteralPath $inner) {
        # Minimal wrapper if CapCut root launcher missing from store
        $wrap = @"
# Auto-generated HybridCut root launcher
`$ErrorActionPreference = "Stop"
`$Root = Join-Path `$env:USERPROFILE "Documents\Videoeditor\hybrid_cut"
& (Join-Path `$Root "run_hybrid.ps1")
exit `$LASTEXITCODE
"@
        Set-Content -LiteralPath $dstLauncher -Value $wrap -Encoding ascii
    }
    Write-Host ("Root launcher: " + $dstLauncher)
}

Write-Host "HybridCut sync_hybrid.ps1 -> Documents\Videoeditor\hybrid_cut"
Write-Host ("TIP: " + $TipStamp)
Write-Host ("DST: " + $dst)

$found = Find-HybridSrc
$src = $found.Src

if ($src) {
    $srcStamp = Get-SrcStamp $src
    Write-Host ("SRC: " + $src)
    Write-Host ("SRC SYNC: " + $srcStamp)
    if (-not (Test-TipStamp $srcStamp)) {
        Write-Error ("Refuse stale SRC SYNC='" + $srcStamp + "' — need " + $TipStamp)
    }

    New-Item -ItemType Directory -Force -Path $dst | Out-Null
    # Wipe stale dist assets so old index-BGJ2h0CY.js cannot linger next to new tip.
    $dstDist = Join-Path $dst "frontend\dist"
    if (Test-Path -LiteralPath $dstDist) {
        Write-Host "Purging old frontend/dist before copy (avoid stale JS hash)."
        Remove-Item -LiteralPath $dstDist -Recurse -Force -ErrorAction SilentlyContinue
    }
    $excludeDirs = @("__pycache__", ".venv", "venv", "node_modules", ".git", "bake", ".pytest_cache")
    $robolog = New-AsciiTempPath -Suffix ".log"
    $xdArgs = @()
    foreach ($d in $excludeDirs) { $xdArgs += "/XD"; $xdArgs += $d }
    $rcArgs = @($src, $dst, "/E", "/R:1", "/W:1", "/NFL", "/NDL", "/NJH", "/NP", "/XF", "*.pyc") + $xdArgs + @("/LOG:" + $robolog)
    & robocopy @rcArgs | Out-Null
    $rc = $LASTEXITCODE
    if ($rc -ge 8) {
        Write-Host ("robocopy log: " + $robolog)
        Remove-TempQuiet -Path $robolog
        Write-Error ("robocopy failed with exit code " + $rc)
    }
    $sampleSrc = Join-Path $src "cache\sample_person.mp4"
    $sampleDstDir = Join-Path $dst "cache"
    if (Test-Path -LiteralPath $sampleSrc) {
        New-Item -ItemType Directory -Force -Path $sampleDstDir | Out-Null
        Copy-Item -LiteralPath $sampleSrc -Destination (Join-Path $sampleDstDir "sample_person.mp4") -Force
    }

    # Always re-stamp DST from tip — never leave run-ps1 SYNC if SRC was correct.
    $srcVer = Join-Path $src "SYNC_VERSION.txt"
    if (Test-Path -LiteralPath $srcVer) {
        Copy-Item -LiteralPath $srcVer -Destination (Join-Path $dst "SYNC_VERSION.txt") -Force
    }
    Set-Content -LiteralPath (Join-Path $dst "SYNC_VERSION.txt") -Value ($TipStamp + "`n") -Encoding ascii -NoNewline

    Install-RootLauncher $dst
    Remove-TempQuiet -Path $robolog
    $stamp = Assert-HybridDst -Dest $dst -ExpectedStamp $TipStamp
    Write-Host ""
    Write-Host ("SYNC_HYBRID OK -> " + $dst)
    Write-Host ("SYNC_VERSION: " + $stamp)
    Write-Host ""
    Write-Host "Kovetkezo / Next:"
    Write-Host '  cd $env:USERPROFILE\Documents\Videoeditor'
    Write-Host "  Get-Content .\hybrid_cut\SYNC_VERSION.txt   # must be $TipStamp"
    Write-Host "  .\run_hybrid.ps1"
    Write-Host "Open: http://127.0.0.1:3847  (Ctrl+F5)"
    exit 0
}

# Fallback: portable zip
$zips = @(Find-ZipCandidates)
if ($zips.Count -gt 0) {
    Write-Host "hybrid_cut/hybrid-editor folder missing locally; using portable zip fallback..."
    Expand-HybridZip -ZipPath $zips[0] -Dest $dst
    Set-Content -LiteralPath (Join-Path $dst "SYNC_VERSION.txt") -Value ($TipStamp + "`n") -Encoding ascii -NoNewline
    Install-RootLauncher $dst
    $stamp = Assert-HybridDst -Dest $dst -ExpectedStamp $TipStamp
    Write-Host ""
    Write-Host ("SYNC_HYBRID OK (zip) -> " + $dst)
    Write-Host ("SYNC_VERSION: " + $stamp)
    Write-Host ("ZIP: " + $zips[0])
    Write-Host ""
    Write-Host "Kovetkezo / Next:"
    Write-Host '  cd $env:USERPROFILE\Documents\Videoeditor'
    Write-Host "  .\run_hybrid.ps1"
    Write-Host "Open: http://127.0.0.1:3847"
    exit 0
}

Write-Host ""
Write-Host "HIBA / ERROR: HybridCut forras es portable zip sem talalhato."
Write-Host "Source tree and portable zip not found. Tried tree paths:"
foreach ($c in $found.Tried) { Write-Host ("  " + $c) }
Write-Host "Also looked for hybrid-editor-portable.zip next to this script and under AgentStores."
Write-Host ""
Write-Host "KOVETKEZO LEPESEK / NEXT STEPS:"
Write-Host "  1) Re-open Cursor so Agent Store refreshes capcut-features (includes hybrid_cut + sync_hybrid.ps1)."
Write-Host "  2) Or run CapCut sync.ps1 after the other agent embeds hybrid_cut delivery."
Write-Host '  3) Diagnostic:'
Write-Host '     Test-Path "$env:LOCALAPPDATA\Cursor\AgentStores\cursor_agent_stores\bc-41930eab-1501-4c19-acf3-0c9d63afbf4d\files\docs\capcut-features\hybrid_cut\run_hybrid.ps1"'
Write-Host ("  4) Expect SYNC_VERSION.txt = " + $TipStamp)
Write-Error "HybridCut sync_hybrid source missing."
