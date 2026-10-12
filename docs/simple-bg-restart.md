# HybridCut restart — simple-bg2 (`2026-10-12-simple-bg2`)

Feature stamp: **`2026-10-12-simple-bg2`**.

Includes prior: simple-bg · run-ps1 · rvm-back · matte-cpu2 · cpu-matte · cuda-ps1 · cuda-restore · cuda-ep · seed-crash · rvm-matte · matte-visible · person-restore · auto-person · look-peak.

## Why you still saw AI SÁV + gray toast

| Symptom | Cause |
|---------|--------|
| AI SÁV lane + Polírozás footer | Local Agent Store / `Documents\Videoeditor\hybrid_cut` still had **`2026-10-11-run-ps1`** (`index-BGJ2h0CY.js`) — synced **before** simple-bg mirror landed |
| `SYNC_VERSION=run-ps1` after sync | `sync_hybrid.ps1` picked the first tree with UI; stale AgentStores copy won |
| „Hibás egyenletes maszk…” toast | Broken CUDA / old tip path; CPU ORT person matte not reached |

## What simple-bg2 does

| Area | Behaviour |
|------|-----------|
| **One timeline** | Single **V1** lane only. API `tracks` = `[V1]`. No AI sáv label anywhere in UI. |
| **Focus** | **Háttéreltávolítás** only: Megnyitás → Előnézet Cutout → Export `*_full_nobg.mov` |
| **Gyors default** | Megnyitás stays **Gyors** (MobileNet). Max only when user picks it / bake. |
| **CPU person matte** | `HYBRID_ORT_PROVIDER=cpu` · MobileNet/ResNet ORT · load smoke + heuristic recovery · no sticky gray-slab toast when matte recovers |
| **Sync harden** | `sync_hybrid.ps1` **refuses** stale stamps (`run-ps1`, `rvm-back`, even `simple-bg`) — installs only **`2026-10-12-simple-bg2`**, purges old `frontend/dist`, rewrites SYNC |
| **Removed** | AI sáv · Polírozás · B-roll · multi-track · nobg Mozgatás · + V1 klip stack · Varázsceruza |

## Sync + run (Windows)

```powershell
& "$env:LOCALAPPDATA\Cursor\AgentStores\cursor_agent_stores\bc-41930eab-1501-4c19-acf3-0c9d63afbf4d\files\docs\capcut-features\sync_hybrid.ps1"
cd $env:USERPROFILE\Documents\Videoeditor
Get-Content .\hybrid_cut\SYNC_VERSION.txt   # MUST be: 2026-10-12-simple-bg2
cd hybrid_cut
.\run_hybrid.ps1
# http://127.0.0.1:3847 — Ctrl+F5
# Dist JS hash must NOT be index-BGJ2h0CY.js
```

If sync errors with „Tip stamp missing” / „Refuse stale SRC”: **re-open Cursor** so Agent Store refreshes, then run sync again. Do **not** keep using Documents\hybrid_cut from run-ps1.

## UI — Róbert checklist (HU)

1. **SYNC** = `2026-10-12-simple-bg2` (not run-ps1 / not simple-bg).
2. **Idővonal** — csak **V1** (nincs üres AI SÁV).
3. **Megnyitás** — egy videó; második ejtés elutasítva.
4. **Előnézet Cutout / Maszk** — személy sziluett, háttér sakktábla (nem szürke lap).
5. **Export** → `C:\bgcut\*_full_nobg.mov`.

## Smoke

```powershell
cd hybrid_cut
$env:PYTHONPATH="$PWD\backend"
$env:HYBRID_ORT_PROVIDER="cpu"
python -m pytest backend/tests/test_simple_bg.py backend/tests/test_ai_tracks.py backend/tests/test_cpu_matte.py backend/tests/test_matte_visible.py -q
```

## Dist

`frontend/dist`: `index-fyrBYl2A.js` / `index-DgGXKx1Y.css` (not `index-BGJ2h0CY.js` / not `index-DY2_6z5E.js`). Hard-refresh **Ctrl+F5**.
