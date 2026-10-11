# HybridCut restart — person-auto (`2026-10-11-person-auto`) — incomplete

> **Tip stamp moved:** use **`2026-10-11-person-fix2`** — full-person auto matte + multi-person/4K harden. See [`person-fix2-restart.md`](person-fix2-restart.md).

Feature stamp (historical): **`2026-10-11-person-auto`**.

Includes prior: `2026-10-11-paint-face` (Radír isolation + Varázsceruza face pick) · nobg-layer · concat-look · timeline-bg.

## What broke (paint-face)

`2026-10-11-paint-face` made **Varázsceruza** set `seed_mode=replace` (face-only alpha). That mode was **persisted to disk** and **reloaded on every Megnyitás**, so preview/export stayed face-gated even when you only wanted the old **teljes ember** auto RVM matte. One wand click (or a leftover seed) looked like “automatic person detect / select / cutout is gone.”

## What this restores

| Path | Behaviour |
|------|-----------|
| **Alap (teljes ember)** | Videó → Max/Gyors → **Előnézet** → auto RVM ember-maszk → Cutout → Export `*_full_nobg` = **teljes átlátszó személy** (nincs Varázsceruza) |
| **Opcionális arc** | **Varázsceruza** → kattints az arcra → `replace` → export csak az arc |
| **Kilépés arc módból** | **Teljes ember** / „Vissza: teljes ember” / Maszk törlés — union + auto RVM |
| **Újranyitás** | Disk `replace` seed **nem** töltődik vissza — mindig teljes ember default |

## Pull + start (GitHub)

```powershell
cd $env:USERPROFILE\Documents\HybridCut
git pull
Get-Content .\SYNC_VERSION.txt   # 2026-10-11-person-auto
.\install_to_videoeditor.ps1
cd $env:USERPROFILE\Documents\Videoeditor
$env:HYBRID_RVM_ONNX = "$PWD\models\rvm_resnet50_fp32.onnx"
.\hybrid_cut\start_hybrid_cuda.ps1
# http://127.0.0.1:3847 — hard-refresh (Ctrl+F5)
```

## Agent Store sync (no GitHub)

```powershell
& "$env:LOCALAPPDATA\Cursor\AgentStores\cursor_agent_stores\bc-41930eab-1501-4c19-acf3-0c9d63afbf4d\files\docs\capcut-features\sync_hybrid.ps1"
cd $env:USERPROFILE\Documents\Videoeditor
Get-Content .\hybrid_cut\SYNC_VERSION.txt   # expect: 2026-10-11-person-auto
.\run_hybrid.ps1
```

## UI — teljes ember vs arc (HU)

1. **Teljes ember (alap):** Max vagy Gyors → Megnyitás → **Előnézet** → Cutout → **Export**. Nem kell Varázsceruza.
2. **Csak arc:** Varázsceruza → kattints az **arcra** → toast „export = csak ez a rész”.
3. **Vissza teljes emberhez:** gomb **Teljes ember** / „Vissza: teljes ember” a narancs sávon — vagy újra Megnyitás (arc seed nem ragad).

## Smoke

```powershell
cd hybrid_cut
$env:PYTHONPATH="$PWD\backend"
python -m pytest backend/tests/test_person_auto.py backend/tests/test_paint_face.py backend/tests/test_nobg_layer.py -q
```
