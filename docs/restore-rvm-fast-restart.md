# HybridCut restart — restore-rvm-fast (`2026-10-14-restore-rvm-fast`)

Branch: `cursor/restore-rvm-fast-b680` (from `cursor/restore-rvm-diag-20261014`).
Keeps soft person alpha (OSS / restore-rvm). Speeds **Gyors bake on CPU ORT**.

## Root cause (~8 min for 10s 1080p24 / 240 frames)

| Factor | Detail |
|--------|--------|
| Full-res `src` every frame | `FastEngine.bake()` fed native 1080p BGR into CPU MobileNet. `downsample_ratio` alone still ships a huge float tensor → ~**2 s/frame** (~8 min). |
| No bake proxy | Scrub preview already used ~480 long; **bake did not**. Max CPU already had MobileNet@~720. |
| MaskStore PNG thrash | Every bake frame called `mask_store.put` → disk PNG write (scrub cache, useless for export). |
| Soft alpha OK | Person cutout / checkerboard worked; speed was the only regression. |
| CUDA EP | Probe still FAIL (plugin EP / MemcpyTransformer gray smoke) → badge **CPU ORT** is correct. Push ≠ GPU proof. |

## What changed

| Change | Effect |
|--------|--------|
| CPU Gyors bake long-side **640** (env `HYBRID_GYORS_BAKE_LONG`, clamp 480–720) | Downscale **before** ORT; soft pha unchanged (no crush). |
| Skip MaskStore writes during bake | No per-frame PNG thrash. |
| Honest ETA | CPU Gyors multiplier **6×** CUDA base → ~**1 perc** for 10s@24 (not optimistic 16s, not silent 8 min). |
| Progress tag | `Gyors~640 N/M frame` so UI matches the path. |
| Opt-out | `HYBRID_GYORS_BAKE_FULLRES=1` restores old slow full-res bake. |

**Expected wall-clock (CPU ORT, RTX 3060 host, 10s@24 / 240 frames):** ~**45–90 s** (was ~8 min). CUDA EP OK would be faster still — only claim GPU when probe prints `OK=1`.

## CUDA EP (Windows ORT 1.30) — do not invent GPU

Reliable remount path (already in tree):

```powershell
cd $env:USERPROFILE\Documents\Videoeditor\hybrid_cut
.\start_hybrid_cuda.ps1
# Look for: === CUDA EP PROBE ===  RESULT: OK / FAIL
# OK=1 → chip RVM CUDA, HYBRID_ORT_PROVIDER=cuda
# FAIL → CPU ORT (correct). Gray-slab CUDA is worse than slow CPU.
```

Pin: `onnxruntime-gpu==1.30.0` + `nvidia-cudnn-cu12`, PATH inject, hard probe via `scripts/probe_cuda_ep.py`.
Listed CUDA ≠ registered plugin EP. Never claim GPU without probe OK.

## PowerShell (user)

```powershell
# Option A - GitHub feature branch
irm is not used; paste PASTE_RESTORE_RVM_FAST_GITHUB.ps1 from repo tip, or:

cd $env:USERPROFILE\Documents\HybridCut
git fetch origin
git checkout cursor/restore-rvm-fast-b680
git pull origin cursor/restore-rvm-fast-b680
Get-Content .\SYNC_VERSION.txt   # 2026-10-14-restore-rvm-fast
.\install_to_videoeditor.ps1
cd $env:USERPROFILE\Documents\Videoeditor
.\hybrid_cut\start_hybrid_cuda.ps1
# http://127.0.0.1:3847 — Ctrl+F5
# Gyors Export: expect Gyors~640 progress; soft cutout; ~1 min for 10s clip on CPU
```

```powershell
# Option B - one-shot install script (Agent Store or GitHub fallback)
# Run PASTE_RESTORE_RVM_FAST_INSTALL.ps1 from the repo / Agent Store copy
```

Tune:

```powershell
$env:HYBRID_GYORS_BAKE_LONG = "480"   # faster scrub bake
$env:HYBRID_GYORS_BAKE_LONG = "720"   # sharper (still << full 1080p CPU)
# $env:HYBRID_GYORS_BAKE_FULLRES = "1"  # old ~8 min path — debug only
```

## Verify

1. Chip: **CPU ORT** (or **RVM CUDA** only if probe OK).
2. Gyors Előnézet: soft person / checkerboard (unchanged).
3. Gyors Export 10s: progress `Gyors~640 … frame`, wall clock **under ~2 perc** (target ~1 perc).
4. Soft alpha: no aggressive crush / gray-slab toast on happy path.
