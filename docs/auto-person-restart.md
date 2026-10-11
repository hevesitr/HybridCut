# HybridCut restart — auto-person (`2026-10-11-auto-person`)

Feature stamp: **`2026-10-11-auto-person`**.

Includes prior: look-peak (UI) · ai-tracks (AI sáv + Polírozás) · person-fix2 matte harden · nobg-layer · concat-look.

## What changed

| Area | Behaviour |
|------|-----------|
| **Delete** | Click a V1 / AI sáv clip → **Delete** or **Backspace** removes it (also Del / Töröl). Works with scrub range focused (not only when typing in text fields). Last V1 may be cleared. |
| **Removed** | **Varázsceruza**, Ecset, Radír, Lasszó UI + `face_pick` / seed paint path — permanently gone |
| **Auto person** | Megnyitás / drop / AI sáv **Polírozás** → full-person RVM for **all people** + body parts (apex polish). No wand. Sticky seed PNGs purged on open/select. |
| **Kept** | Auto RVM cutout · AI Polírozás · nobg layer Mozgatás / Pozíció |

## Pull + start (GitHub)

```powershell
cd $env:USERPROFILE\Documents\HybridCut
git pull
Get-Content .\SYNC_VERSION.txt   # 2026-10-11-auto-person
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
Get-Content .\hybrid_cut\SYNC_VERSION.txt   # expect: 2026-10-11-auto-person
.\run_hybrid.ps1
```

Hard-refresh **Ctrl+F5**.

## UI — Róbert checklist (HU)

1. **Megnyitás** — videó a V1-re; Előnézet → Cutout = teljes ember auto (nincs Varázsceruza).
2. **Klip törlés** — kattints a klipre → **Delete** / **Backspace**, vagy Del / Töröl.
3. **AI sáv** — húzd egymás alá → **Polírozás** auto; **P** újrafuttat.
4. **Export** → `C:\bgcut\*_full_nobg.mov` · Nobg a timeline-ra továbbra is.

## Smoke

```powershell
cd hybrid_cut
$env:PYTHONPATH="$PWD\backend"
python -m pytest backend/tests/test_auto_person.py backend/tests/test_person_fix2.py backend/tests/test_ai_tracks.py backend/tests/test_timeline_bg.py -q
```
