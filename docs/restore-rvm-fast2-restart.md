# HybridCut restart — restore-rvm-fast2 (`2026-10-14-restore-rvm-fast2`)

Branch: `cursor/restore-rvm-fast2-b680` (from `cursor/restore-rvm-fast-b680`).

## Problem

Max export on CPU ORT: chip said **~49s**, wall **~4 perc** (31/240 · Hátravan ~3:42).
Root: aspirational `CPU_MAX_SPF_MULT=1.15` assumed MobileNet@720 ≈ CUDA Max, but
`polish_videoeditor` + `_crush_soft_shadow_alpha` + color polish ≈ **~1 s/frame**.

Gyors soft recognition stays intact (fast2 does not touch Gyors bake path).

## Fixes

| Change | Effect |
|--------|--------|
| Honest Max CPU ETA | `CPU_MAX_SPF_MULT=3.5` → chip ~**2 perc** for 10s@24; remaining trusts observed from frame 3 |
| Light Max CPU bake (default) | Soft RVM + hole-fill + stabilizer; **skip** heavy polish / crush / color polish |
| Default long-side **640** | Was 720; env `HYBRID_CPU_MAX_LONG=720` for sharper |
| Opt-in heavy | `HYBRID_CPU_MAX_HEAVY_POLISH=1` restores old polish path (~4 min) |

## Expected wall (10s @ 24 / 240 frames, CPU ORT)

| Path | Wall-clock |
|------|------------|
| Before (polish@720) | ~**4 perc** (~1 s/frame); chip lied ~49s |
| After light@640 | ~**1.5–2.5 perc** target; chip ~**2 perc** |
| Heavy polish opt-in | ~4 perc (honest remaining after a few frames) |
| CUDA EP OK | Faster — only if probe OK=1 |

## PowerShell

```powershell
cd $env:USERPROFILE\Documents\HybridCut
git fetch origin
git checkout cursor/restore-rvm-fast2-b680
git pull origin cursor/restore-rvm-fast2-b680
Get-Content .\SYNC_VERSION.txt   # 2026-10-14-restore-rvm-fast2
.\install_to_videoeditor.ps1
cd $env:USERPROFILE\Documents\Videoeditor
.\hybrid_cut\start_hybrid_cuda.ps1
# http://127.0.0.1:3847 — Ctrl+F5
# Max Export: CPU Max~640 … frame; ETA ~2 perc; soft person kept
```

Or paste `PASTE_RESTORE_RVM_FAST2_GITHUB.ps1` / `PASTE_RESTORE_RVM_FAST2_INSTALL.ps1`.

```powershell
$env:HYBRID_CPU_MAX_LONG = "720"           # sharper Max CPU
$env:HYBRID_CPU_MAX_HEAVY_POLISH = "1"     # old polish (slower)
```

Push ≠ GPU proof. Shadow-fringe work is a separate branch/worker.
