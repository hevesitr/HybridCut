# HybridCut restart — matte-visible (`2026-10-11-matte-visible`)

Feature stamp: **`2026-10-11-matte-visible`**.

Includes prior: person-restore · auto-person · look-peak · ai-tracks · person-fix2 · nobg-layer.

## What the screenshots proved (honest cause)

| View | What Róbert saw | Cause |
|------|-----------------|-------|
| **Maszk** | Solid light-gray rectangle on checkerboard (no person silhouette) | Alpha was a **near-uniform full-frame / all-ones slab**. `visualize_alpha_matte` paints `a≈1` as ~210 gray over the whole frame → flat gray “person”. |
| **Cutout** | Full source with background (two women); BG not punched | Same all-ones alpha → `subject × 1 + checker × 0` = opaque full frame. UI still showed **Cutout ✓** because empty-matte checks only caught *tiny* masks, not *full-frame* ones. |
| **Gyors chip** | Header still said **Gyors** after Megnyitás | **Max-on-open** from `person-restore` was not on the running tree (Agent Store tip had the fix; GitHub/`Videoeditor` sync often still on older `auto-person`), **or** mode was switched back to Gyors. Gyors + poisoned/degenerate cache made the slab look “ready”. |

Root mechanisms that produce the slab:

1. **ORT pha in 0–255-ish floats** clipped with `np.clip(..., 0, 1)` without `/255` → almost everything becomes `1.0`.
2. **Wrong ORT output tensor** selected as pha (flat map).
3. **Degenerate MaskStore PNG** (all-white / flat) treated as a valid hit → skip fresh RVM.
4. **Silent success**: no toast when matte is useless-but-non-empty.

This is **not** “RVM deleted” and **not** only the older face-scrap empty-matte bug — the UI lied with Cutout ✓ while showing a gray slab.

## What we fixed

| Path | Behaviour |
|------|-----------|
| `is_matte_degenerate` / `is_matte_empty` | Full-frame uniform / all-ones mattes count as **failure** |
| RVM `matte()` | Prefer named `pha`; **`normalize_alpha`** (scale 0–255 before clip) |
| Fast / Max preview | Reject slab → heuristic retry → else `matte_error` + `source_fallback` (no Cutout ✓) |
| MaskStore | Refuse to persist degenerate slabs |
| Maszk encode | Degenerate → source + `hibas maszk` label (never solid gray rectangle) |
| UI | Toast + status line on matte failure (including egyenletes szürke lap) |
| Megnyitás | Still elevates **Max + Éles** (person-restore) |

## Pull + start (GitHub)

```powershell
cd $env:USERPROFILE\Documents\HybridCut
git pull
Get-Content .\SYNC_VERSION.txt   # 2026-10-11-matte-visible
.\install_to_videoeditor.ps1
cd $env:USERPROFILE\Documents\Videoeditor
$env:HYBRID_RVM_ONNX = "$PWD\models\rvm_resnet50_fp32.onnx"
.\hybrid_cut\start_hybrid_cuda.ps1
# http://127.0.0.1:3847 — hard-refresh (Ctrl+F5)
```

## Agent Store sync (no GitHub / no PAT)

```powershell
& "$env:LOCALAPPDATA\Cursor\AgentStores\cursor_agent_stores\bc-41930eab-1501-4c19-acf3-0c9d63afbf4d\files\docs\capcut-features\sync_hybrid.ps1"
cd $env:USERPROFILE\Documents\Videoeditor
Get-Content .\hybrid_cut\SYNC_VERSION.txt   # expect: 2026-10-11-matte-visible
.\run_hybrid.ps1
```

Hard-refresh **Ctrl+F5**.

## Kept from person-restore

- No **Varázsceruza** / Ecset / Radír / Lasszó
- **Delete** / Backspace clip delete
- MaskStore purge on Megnyitás

## UI — Róbert checklist (HU)

1. **Megnyitás** — videó → **Max** (ne Gyors) + teljes ember maszk.
2. **Maszk** — személy sziluett sakktáblán, **nem** egyszínű szürke téglalap. Ha hiba: toast „Hibás maszk…”, nem Cutout ✓.
3. **Cutout** — háttér átlátszó (sakktábla), nem a nyers két-nő forrás.
4. Ha RVM/ONNX/CUDA elhasal → **látható toast**, nem csendes szürke lap.

## Smoke

```powershell
cd hybrid_cut
$env:PYTHONPATH="$PWD\backend"
python -m pytest backend/tests/test_matte_visible.py backend/tests/test_person_restore.py backend/tests/test_preview_composite.py -q
```
