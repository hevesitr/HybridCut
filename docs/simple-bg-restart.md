# HybridCut restart — simple-bg3 (`2026-10-12-simple-bg3`)

Feature stamp: **`2026-10-12-simple-bg3`**.

Includes prior: simple-bg2 · simple-bg · run-ps1 · rvm-back · matte-cpu2 · cpu-matte · cuda-ps1 · cuda-restore · cuda-ep · seed-crash · rvm-matte · matte-visible · person-restore · auto-person · look-peak.

## Why you still saw AI SÁV / + V1 / + B-roll on simple-bg2

| Symptom | Cause |
|---------|--------|
| Badge `simple-bg2` but timeline shows **AI SÁV** or **+ V1 klip / + B-roll** | Backend SYNC updated, but **stale hashed JS** from look-peak / run-ps1 still served (`index-BGJ2h0CY.js` etc.). `install_to_videoeditor.ps1` used robocopy `/E` **without** purging `frontend/dist` |
| „Hibás maszk (egyenletes szürke lap) — CPU ORT / Max mód” | CPU MobileNet empty/slab on real 1080p close-up; no auto ResNet twin; close-up high-cover falsely treated like all-ones; sticky toast |
| Many `/api/preview` 200, still no silhouette | Preview returned `matte_empty` + egyenletes error — UI toast path |

## What simple-bg3 does

| Area | Behaviour |
|------|-----------|
| **One timeline** | Single **V1** only. Dist must contain **zero** `AI sáv` / `AI SÁV` / `+ V1 klip` / `+ B-roll` / `tl-polish-btn` |
| **Install purge** | `install_to_videoeditor.ps1` **deletes** destination `frontend/dist` before copy, then **refuses** install if banned strings remain |
| **CPU person matte** | MobileNet empty/slab → **auto ResNet fp32** (local `models/`) → close-up-aware heuristic. High-cover face/hair no longer false-slab |
| **Max Előnézet** | Polish cannot leave gray-slab; sticky toast clears when matte OK. Auto preview on Megnyitás |
| **Focus** | Háttéreltávolítás: Megnyitás → Előnézet Cutout → Export `*_full_nobg.mov` |

## Sync + run (Windows) — one-shot

```powershell
# Stop old server (port 3847), pull GitHub tip, install, verify
Get-NetTCPConnection -LocalPort 3847 -ErrorAction SilentlyContinue |
  ForEach-Object { Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue }
cd $env:USERPROFILE\Documents\HybridCut
git fetch origin
git checkout main
git pull origin main
Get-Content .\SYNC_VERSION.txt   # MUST be: 2026-10-12-simple-bg3
.\install_to_videoeditor.ps1
cd $env:USERPROFILE\Documents\Videoeditor
Get-Content .\hybrid_cut\SYNC_VERSION.txt   # MUST be: 2026-10-12-simple-bg3
# Optional ResNet (sharper Max on CPU close-ups):
#   .\hybrid_cut\scripts\download_rvm.ps1 rvm_resnet50_fp32.onnx
#   copy into Documents\Videoeditor\models\ as well if CapCut tree holds weights
.\hybrid_cut\run_hybrid.ps1
# Browser: http://127.0.0.1:3847 — hard refresh Ctrl+F5
# Confirm dist asset name changed (not index-BGJ2h0CY.js / not index-fyrBYl2A.js)
```

## UI — Róbert checklist (HU)

1. **SYNC** = `2026-10-12-simple-bg3`.
2. **Idővonal** — csak **V1** (nincs AI SÁV, nincs + V1 / + B-roll).
3. **Megnyitás** — egy videó; auto Előnézet Cutout.
4. **Maszk / Cutout** — személy sziluett (close-up OK), nem szürke lap.
5. **Export** → `C:\bgcut\*_full_nobg.mov`.

## Smoke

```powershell
cd hybrid_cut
$env:PYTHONPATH="$PWD\backend"
$env:HYBRID_ORT_PROVIDER="cpu"
python -m pytest backend/tests/test_simple_bg3.py backend/tests/test_simple_bg.py backend/tests/test_ai_tracks.py backend/tests/test_cpu_matte.py backend/tests/test_matte_visible.py -q
```

## Dist

New hashed `frontend/dist/assets/index-*.js` / `index-*.css` after build. Hard-refresh **Ctrl+F5**. Grep dist for `AI SÁV` / `+ B-roll` must be **zero**.
