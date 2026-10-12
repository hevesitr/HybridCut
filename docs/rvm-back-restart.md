# HybridCut restart — rvm-back (`2026-10-11-rvm-back`)

> **Tip is now [`run-ps1-restart.md`](run-ps1-restart.md) (`2026-10-11-run-ps1`).** ASCII-only `run_hybrid.ps1` / remaining `.ps1` (em-dash parse fix).

Feature stamp: **`2026-10-11-rvm-back`** (superseded tip).

Includes prior: matte-cpu2 · cpu-matte · cuda-ps1 · cuda-restore · cuda-ep · seed-crash · rvm-matte · matte-visible · person-restore · auto-person · look-peak.

## Why still broken after cpu-matte / matte-cpu2

| Symptom | Cause |
|---------|--------|
| Toast `Hibás maszk (egyenletes szürke lap)` after matte-cpu2 | **Launch still defaulted `HYBRID_ORT_PROVIDER=cuda`** (`main.py` / `run_hybrid.ps1` / `start_hybrid_cuda.ps1`). Probe could still leave a half-broken CUDA session first → `No registered plugin EP` + `OP Conv… Fallback` / MemcpyTransformer → all-ones gray `pha` → toast |
| CPU path “OK” in logs but Maszk still wrong / toast sticky | Soft CPU RVM person mattes (wide shot: cover≈0.03–0.08, mean≈0.015) were **false-empty** under `EMPTY_ALPHA_COVER=0.04` / `EMPTY_ALPHA_MEAN=0.03` → rejected real silhouette; Gyors ladder tried 0.25 first; sticky UI toast / MaskStore could keep the gray message even after heuristic |
| GitHub tip stuck at `d348914` rvm-matte | matte-cpu2 never pushed (no PAT) — sync-from-GH alone missed CPU-first + sticky-toast fixes |

Morning look-peak / pre-paint-face worked because Előnézet did not hit the broken CUDA Conv Fallback path as hard, and empty checks did not fold soft RVM into “egyenletes lap”.

## What this stamp does

| Path | Behaviour |
|------|-----------|
| **CPU-first launch** | Default `HYBRID_ORT_PROVIDER=cpu` in `main.py`, `run_hybrid.ps1`, `start_hybrid_cuda.ps1`, `_OrtRvmSession`. Előnézet never opens on broken CUDA first |
| **CUDA only after hard probe** | `start_hybrid_cuda.ps1` upgrades to cuda **only** on probe hard OK (no plugin EP warn, no gray-slab). Fail → keep CPU |
| **Soft person accepted** | `is_matte_structured` + lower cover/mean floors — real CPU RVM silhouette is not false-empty |
| **CPU ds ladder** | Prefer `1.0 → 0.5` before Gyors `0.25`; first run cold |
| **Sticky toast** | UI clears gray-slab / Ember-maszk toast whenever `matte_recovered` or non-empty preview |
| **Keep** | Delete key, no Varázsceruza, AI sáv |

## Sync + run (Windows)

```powershell
& "$env:LOCALAPPDATA\Cursor\AgentStores\cursor_agent_stores\bc-41930eab-1501-4c19-acf3-0c9d63afbf4d\files\docs\capcut-features\sync_hybrid.ps1"
cd $env:USERPROFILE\Documents\Videoeditor
Get-Content .\hybrid_cut\SYNC_VERSION.txt   # expect: 2026-10-11-rvm-back
.\hybrid_cut\start_hybrid_cuda.ps1
# http://127.0.0.1:3847 — Ctrl+F5
```

Expect console (plugin missing):

```
HYBRID_ORT_PROVIDER default: cpu (CPU-first; CUDA only after hard probe)
=== CUDA EP PROBE ===
OK=0
RESULT: FAIL
KEEP: HYBRID_ORT_PROVIDER=cpu (CPU-first; real person matte; no Conv Fallback)
```

UI: topbar **CPU ORT**. Maszk = person silhouette. **No** „Hibás maszk (egyenletes szürke lap)” toast.

## Smoke

```powershell
cd hybrid_cut
$env:PYTHONPATH="$PWD\backend"
$env:HYBRID_ORT_PROVIDER="cpu"
python -m pytest backend/tests/test_cpu_matte.py backend/tests/test_rvm_matte.py backend/tests/test_matte_visible.py -q
```

## Dist

`frontend/dist`: `index-BGJ2h0CY.js` / `index-Bv2GNnfq.css`. Hard-refresh **Ctrl+F5**.
