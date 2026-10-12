# HybridCut restart — simple-bg4 (`2026-10-12-simple-bg4`)

Feature stamp: **`2026-10-12-simple-bg4`**.

**Háttéreltávolítás** focus: Megnyitás → Előnézet Cutout → Export. **One timeline** — single **V1** only (no **AI sáv** / + V1 / + B-roll).

Includes prior: simple-bg3 · simple-bg2 · simple-bg · run-ps1 · rvm-back · matte-cpu2 · cpu-matte · cuda-ps1 · cuda-restore · cuda-ep · seed-crash · rvm-matte · matte-visible · person-restore · auto-person · look-peak.

## Why simple-bg3 still left „Hibás maszk (egyenletes szürke lap)”

| Symptom | Cause |
|---------|--------|
| CPU ORT + Gyors, MobileNet, toast gray slab | MobileNet on CPU after CUDA→CPU can emit all-ones / dust speck; ResNet often **not installed**; speck passed structured floors → skipped ResNet/heuristic |
| `/api/preview` 200, overlay „Nincs ember-maszk” | Gray-slab rejection stuck — no solid-BG chroma fallback for classic blue-screen close-ups |
| Slow Előnézet on CPU | CUDA EP missing → CPU ORT (primary). CPU ds ladder tried **native 1.0 first** on every fail (up to 4 ORT passes) even for uniform slabs |

## What simple-bg4 does

| Area | Behaviour |
|------|-----------|
| **Matte ladder** | Primary RVM → **ResNet twin** → **solid-BG chroma** (blue/green screen) → GrabCut heuristic → zeros |
| **Speck gate** | `is_matte_good_enough` — dust that passed structured floors still retries |
| **Uniform slab** | Skip remaining ds retries (same garbage at every ratio) |
| **Gyors→Max** | If Gyors preview still empty/slab → **one-shot auto Max** (ResNet + polish) |
| **CPU speed** | Gyors CPU ladder starts at **0.5** (native last); never upsamples source |
| **UI badge** | True probe `width×height` (no invented 1920×1080) |
| **One timeline** | Single **V1** only (simple-bg3 purge kept) |

## Sync + run (Windows)

```powershell
Get-NetTCPConnection -LocalPort 3847 -ErrorAction SilentlyContinue |
  ForEach-Object { Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue }
cd $env:USERPROFILE\Documents\HybridCut
git fetch origin; git checkout main; git pull origin main
Get-Content .\SYNC_VERSION.txt   # MUST be: 2026-10-12-simple-bg4
# ResNet strongly recommended for Max / close-up CPU:
.\scripts\download_rvm.ps1 rvm_resnet50_fp32.onnx
New-Item -ItemType Directory -Force -Path "$env:USERPROFILE\Documents\Videoeditor\models" | Out-Null
Copy-Item .\models\rvm_resnet50_fp32.onnx "$env:USERPROFILE\Documents\Videoeditor\models\" -Force -ErrorAction SilentlyContinue
.\install_to_videoeditor.ps1
cd $env:USERPROFILE\Documents\Videoeditor
Get-Content .\hybrid_cut\SYNC_VERSION.txt   # MUST be: 2026-10-12-simple-bg4
.\hybrid_cut\run_hybrid.ps1
# Browser: http://127.0.0.1:3847 — Ctrl+F5 — Előnézet Cutout
# Gyors auto-retries Max on failure — you do NOT need to click Max first.
```

## Slowness (user FAQ)

**Primary:** CUDA EP plugin not registered → intentional **CPU ORT** (much slower than RTX CUDA).  
**Not** because HybridCut invents 1080p: probe uses native `width×height`; `downscale_long_side` never upsamples. Gyors proxies at ≤720 long-side; Max preview caps at **min(source, 1440)**.

## Smoke

```powershell
cd hybrid_cut
$env:PYTHONPATH="$PWD\backend"
$env:HYBRID_ORT_PROVIDER="cpu"
python -m pytest backend/tests/test_simple_bg4.py backend/tests/test_simple_bg3.py backend/tests/test_simple_bg.py backend/tests/test_cpu_matte.py -q
```
