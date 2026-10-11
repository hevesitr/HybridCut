# HybridCut restart — person-fix2 (`2026-10-11-person-fix2`)

Feature stamp: **`2026-10-11-person-fix2`** (matte).

**Rebased under tip `2026-10-11-ai-tracks`** (AI sáv + Polírozás). Tip SYNC should read **`2026-10-11-ai-tracks`**; confirm matte with `FEATURE_PERSON_FIX2.txt`.

Treats **`2026-10-11-person-auto` as incomplete**. Includes prior: paint-face (Radír + optional Varázsceruza) · nobg-layer · concat-look · timeline-bg · apex polish.

## Honest root cause (what person-auto still missed)

| Hole | Effect |
|------|--------|
| **Clip select reloaded `replace`** | `_load_seed_for_selection` re-armed face-only from disk even after Megnyitás purged it |
| **Wand still wrote `replace` to disk** | One Varázsceruza click (or leftover PNG) sticky-gated preview/export again |
| **Seed re-apply dropped mode** | `_ensure_engine_media` / preview called `set_user_seed(alpha)` without mode |
| **Quality floor** | Timeline composite/bake long-side too low for sharp 4K; multi-person / limb reconnect too strict |

GitHub tip may still be paint-face `8231c3c` if PAT push never landed — use **Context sync** below.

## What this restores + raises

| Path | Behaviour |
|------|-----------|
| **Alap (teljes ember)** | Videó → Max/Gyors → **Előnézet** → auto RVM **all people** + body parts → Cutout → Export `*_full_nobg` — **no wand** |
| **Multi-person** | Keep every person-sized instance; reconnect hands/feet/hair gaps |
| **4K / sharp** | Max preview ~1440 long-side; bake up to 2160; APEX polish default |
| **Opcionális arc** | **Varázsceruza** → face-only for **this session only** (never disk) |
| **Kilépés arc módból** | **Teljes ember** / clear / reopen → full-person auto again |

## Pull + start (GitHub — when tip includes ai-tracks + person-fix2)

```powershell
cd $env:USERPROFILE\Documents\HybridCut
git pull
Get-Content .\SYNC_VERSION.txt   # 2026-10-11-ai-tracks
Get-Content .\backend\hybrid_editor\FEATURE_PERSON_FIX2.txt   # 2026-10-11-person-fix2
.\install_to_videoeditor.ps1
cd $env:USERPROFILE\Documents\Videoeditor
$env:HYBRID_RVM_ONNX = "$PWD\models\rvm_resnet50_fp32.onnx"
.\hybrid_cut\start_hybrid_cuda.ps1
# http://127.0.0.1:3847 — hard-refresh (Ctrl+F5)
```

## Agent Store sync (recommended while PAT missing)

```powershell
& "$env:LOCALAPPDATA\Cursor\AgentStores\cursor_agent_stores\bc-41930eab-1501-4c19-acf3-0c9d63afbf4d\files\docs\capcut-features\sync_hybrid.ps1"
cd $env:USERPROFILE\Documents\Videoeditor
Get-Content .\hybrid_cut\SYNC_VERSION.txt   # expect: 2026-10-11-ai-tracks
Get-Content .\hybrid_cut\backend\hybrid_editor\FEATURE_PERSON_FIX2.txt   # 2026-10-11-person-fix2
.\run_hybrid.ps1
```

## UI — teljes ember vs arc (HU)

1. **Teljes ember (alap):** Max vagy Gyors → Megnyitás → **Előnézet** → Cutout → **Export**. Nem kell Varázsceruza.
2. **Csak arc:** Varázsceruza → kattints az **arcra** → toast „export = csak ez a rész”.
3. **Vissza:** **Teljes ember** / „Vissza: teljes ember” — vagy újra Megnyitás (arc seed nem ragad diskre).

## Smoke

```powershell
cd hybrid_cut
$env:PYTHONPATH="$PWD\backend"
python -m pytest backend/tests/test_person_fix2.py backend/tests/test_ai_tracks.py backend/tests/test_multi_person.py -q
```
