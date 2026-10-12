# HybridCut restart — seed-crash (`2026-10-11-seed-crash`)

Feature stamp: **`2026-10-11-seed-crash`** (tip now **`2026-10-11-cuda-restore`** — ORT 1.30.0 pin + file probe).

Includes prior: rvm-matte · matte-visible · person-restore · auto-person · look-peak · ai-tracks · person-fix2 · nobg-layer.

## Why Assist showed `setShowLargeSeed is not defined`

After **auto-person** removed SeedPaint / large-seed modal, `onNewProject` still called **`setShowLargeSeed(false)`** with no `useState`. The `try/catch` turned that into the status-line error next to **Assist / Ollama**.

That mid-flow throw also aborted the rest of „Új projekt” UI reset — preview/toast could stay inconsistent while the backend project was already cleared.

## What we fixed

| Path | Behaviour |
|------|-----------|
| Frontend | Removed dead `setShowLargeSeed` / large-seed UI refs. Grep-clean in `frontend/src`. |
| Új projekt | Completes reset (view/source, wipe, toast, error clear) without throwing. |
| Max polish | If APEX/quality polish turns a good RVM matte into a **degenerate gray slab**, keep base RVM/heuristic alpha. |
| RVM (kept from rvm-matte) | fp32-first · CapCut cold recurrent · refuse tiny→full pha · **CUDA→CPU** when CUDA pha is a slab. |

Detection toast from matte-visible stays when inference still fails after all recovery.

## Pull + start (GitHub)

```powershell
cd $env:USERPROFILE\Documents\HybridCut
git pull
Get-Content .\SYNC_VERSION.txt   # 2026-10-11-seed-crash
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
Get-Content .\hybrid_cut\SYNC_VERSION.txt   # expect: 2026-10-11-seed-crash
.\run_hybrid.ps1
```

Hard-refresh **Ctrl+F5**.

## Kept from person-restore / auto-person / rvm-matte

- No **Varázsceruza** / Ecset / Radír / Lasszó / SeedPaint
- **Delete** / Backspace clip delete
- MaskStore purge on Megnyitás
- Max + Éles on open
- fp32-first RVM + CUDA→CPU slab recovery
- Degenerate gray-slab toast (honest failure, not Cutout ✓)

## UI — Róbert checklist (HU)

1. **Új** / Assist sáv — **nincs** `setShowLargeSeed is not defined`.
2. **Megnyitás** — videó → **Max** (vagy **Gyors**) + **Éles**.
3. **Előnézet futtatása** — személy sziluett sakktáblán (**nem** egyszínű szürke / all-ones téglalap).
4. **Cutout** — háttér átlátszó; toast „Hibás maszk…” **nem** jelenik meg, ha a matte jó.
5. `SYNC_VERSION` chip: **`2026-10-11-seed-crash`**.

## Smoke

```powershell
cd hybrid_cut
$env:PYTHONPATH="$PWD\backend"
$env:HYBRID_RVM_ONNX = "$env:USERPROFILE\Documents\Videoeditor\models\rvm_resnet50_fp32.onnx"
python -m pytest backend/tests/test_auto_person.py backend/tests/test_rvm_matte.py backend/tests/test_matte_visible.py -q
```

## Dist

`frontend/dist`: `index-CeO067mX.js` / `index-CpRi5XjA.css`

## Gray matte note

If after this stamp + Ctrl+F5 + fp32 ONNX the toast still fires, check status for **CUDA→CPU** / ORT Memcpy logs — that is remaining RVM/ORT box work, not the seed-UI crash.
