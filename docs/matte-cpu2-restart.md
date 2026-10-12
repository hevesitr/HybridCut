> **Tip is now [`rvm-back-restart.md`](rvm-back-restart.md) (`2026-10-11-rvm-back`).**

# HybridCut restart — matte-cpu2 (`2026-10-11-matte-cpu2`)

Feature stamp: **`2026-10-11-matte-cpu2`** (superseded).

Includes prior: cpu-matte · cuda-ps1 · cuda-restore · cuda-ep · seed-crash · rvm-matte · matte-visible · person-restore · auto-person · look-peak.

## Why toast still appeared after CUDA→CPU (cpu-matte)

| Symptom | Cause |
|---------|--------|
| Probe `OK=1` / `RESULT: OK` **and** log `No registered plugin EP device found…` | ORT C++ writes the plugin warning to the **OS stderr FD**, bypassing Python `sys.stderr` tee → probe soft-missed the warning |
| Server `CUDA→CPU: CUDA smoke matte was gray-slab` then still toast | Probe had already set `HYBRID_ORT_PROVIDER=cuda`; half-broken CUDA ran first; after rebuild, Gyors MaskStore / sticky `matte_error` / UI toast could keep „Hibás maszk (egyenletes szürke lap)” even when CPU/heuristic later succeeded |
| `OP Conv(...) running in Fallback mode` | Listed CUDA + missing plugin → Conv Fallback storm before CPU-only session |

## What this stamp does

| Path | Behaviour |
|------|-----------|
| **Native stderr capture** | Probe catcher `dup2`s OS stderr — plugin EP warning ⇒ **OK=0** (never OK=1 from LISTED-only) |
| **RVM smoke in probe** | When RVM ONNX present: CUDA-only synthetic person; gray-slab / plugin warn ⇒ FAIL |
| **start_hybrid_cuda.ps1** | Hard FAIL if probe output contains plugin warning or gray-slab — even if a false `OK=1` line slipped through → **`HYBRID_ORT_PROVIDER=cpu`** before server start (skip broken CUDA entirely) |
| **CUDA→CPU rebuild** | Purge MaskStore (`_masks_stale`); verify CPU smoke; clear `matte_error` when preview non-empty; CPU ds ladder 0.5–1.0 |
| **UI toast** | Successful preview clears sticky gray-slab toast; `matte_recovered` skips re-toast |
| **Badge** | **CPU ORT** when EP not registered — Maszk = person silhouette (not gray lap) |

## Sync + run (Windows)

```powershell
& "$env:LOCALAPPDATA\Cursor\AgentStores\cursor_agent_stores\bc-41930eab-1501-4c19-acf3-0c9d63afbf4d\files\docs\capcut-features\sync_hybrid.ps1"
cd $env:USERPROFILE\Documents\Videoeditor
Get-Content .\hybrid_cut\SYNC_VERSION.txt   # expect: 2026-10-11-matte-cpu2
.\hybrid_cut\start_hybrid_cuda.ps1
# http://127.0.0.1:3847 — Ctrl+F5
```

Expect console when plugin missing:

```
=== CUDA EP PROBE ===
OK=0
RESULT: FAIL
RESULT: FAIL - plugin EP warning in probe output (ignore false OK=1)
WARN: forcing HYBRID_ORT_PROVIDER=cpu (skip broken CUDA; real person matte on CPU)
```

UI: topbar **CPU ORT**. Maszk = person silhouette. No sticky gray-slab toast after CPU path succeeds.

## Smoke

```powershell
cd hybrid_cut
$env:PYTHONPATH="$PWD\backend"
$env:HYBRID_ORT_PROVIDER="cpu"
python -m pytest backend/tests/test_cpu_matte.py backend/tests/test_cuda_ep.py -q
```

## Dist

`frontend/dist`: `index-C5VDrUYU.js` / `index-Bv2GNnfq.css`. Hard-refresh **Ctrl+F5**.
