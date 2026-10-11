# HybridCut restart — paint-face (`2026-10-11-paint-face`)

> **Tip stamp moved:** use **`2026-10-11-person-fix2`** — full-person auto matte restored; face wand stays optional. See [`person-fix2-restart.md`](person-fix2-restart.md).

Feature stamp (historical): **`2026-10-11-paint-face`**.

Includes prior: `2026-10-11-nobg-layer` (overlay Mozgatás / Pozíció) · concat-look · timeline-bg.

## Pull + start (GitHub)

```powershell
cd $env:USERPROFILE\Documents\HybridCut
git pull
Get-Content .\SYNC_VERSION.txt   # 2026-10-11-paint-face
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
Get-Content .\hybrid_cut\SYNC_VERSION.txt   # expect: 2026-10-11-paint-face
.\run_hybrid.ps1
```

## What fixed (Róbert)

| Issue | Fix |
|-------|-----|
| **Radír** strokes hit the timeline | Mask clipped to preview; pointer `stopPropagation` + release when leaving surface; timeline `z-index: 20` + paint-gesture lock |
| **Varázsceruza** selected whole person | Part-pick (Haar face / compact region) → `seed_mode=replace` → alpha / `*_full_nobg` = **only that face** |
| Overlay transform regress | **Mozgatás** still works — paint mask goes passthrough while Mozgatás is on |

## Face-only UI (HU)

1. Max mód · Előnézet · válaszd a klipet.
2. **Varázsceruza** → kattints az **arcra**.
3. Toast: „Arc kijelölve — export = csak ez a rész”.
4. Ecset / Radír finomít (replace mód megmarad).
5. **Export** → `C:\bgcut\*_full_nobg.mov` átlátszó **csak az arccal**.

Alt+katt a Varázsceruzával: rész törlése a seedből.

## Smoke

```powershell
cd hybrid_cut
$env:PYTHONPATH="$PWD\backend"
python -m pytest backend/tests/test_paint_face.py backend/tests/test_nobg_layer.py -q
```
