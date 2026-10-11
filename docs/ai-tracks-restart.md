# HybridCut restart — ai-tracks (`2026-10-11-ai-tracks`)

Feature stamp: **`2026-10-11-ai-tracks`**.

Includes prior: `2026-10-11-look-peak` (UI) · `2026-10-11-person-fix2` (full-person matte) · person-auto · paint-face · nobg-layer · timeline-bg.

## What this adds

| Path | Behaviour |
|------|-----------|
| **AI sáv** | Timeline V2 lane labeled **AI sáv** — drag a clip under another (V1 ↔ AI sáv) |
| **Polírozás** | On stack/drop onto AI sáv → auto **Polírozás** (existing Max + Éles szélek / RVM+APEX) |
| **Status** | „Polírozás…”, „Polírozás kész”, clip badge / **P** button for re-run |
| **Hand drag** | Multi-track composition unchanged — V1 under AI sáv as before |
| **Teljes ember** | Default full-person cutout (person-fix2): all people + body parts, sharp 4K long-side; **Polírozás** never inherits face-only; **Varázsceruza** session-only |

## Pull + start (GitHub)

```powershell
cd $env:USERPROFILE\Documents\HybridCut
git pull
Get-Content .\SYNC_VERSION.txt   # 2026-10-11-ai-tracks
.\install_to_videoeditor.ps1
cd $env:USERPROFILE\Documents\Videoeditor
$env:HYBRID_RVM_ONNX = "$PWD\models\rvm_resnet50_fp32.onnx"
.\hybrid_cut\start_hybrid_cuda.ps1
# http://127.0.0.1:3847 — hard-refresh (Ctrl+F5)
# Húzz egy klipet a V1 alá → AI sáv → Polírozás auto
```

## Agent Store sync (no GitHub)

```powershell
& "$env:LOCALAPPDATA\Cursor\AgentStores\cursor_agent_stores\bc-41930eab-1501-4c19-acf3-0c9d63afbf4d\files\docs\capcut-features\sync_hybrid.ps1"
cd $env:USERPROFILE\Documents\Videoeditor
Get-Content .\hybrid_cut\SYNC_VERSION.txt   # expect: 2026-10-11-ai-tracks
.\run_hybrid.ps1
```

## UI — egymás alá + AI polírozás (HU)

1. **Megnyitás** — első videó a **V1** sávon.
2. **Második klip** — húzd **egymás alá** az AI sávra (vagy → B-roll / AI sáv).
3. Auto indul a **Polírozás** (ember-kivágás / él) — státusz: „Polírozás…”.
4. Kész után Cutout előnézet; Export ugyanúgy `*_full_nobg`.
5. Újra: klipen **P** gomb = Polírozás.
6. **Teljes ember** továbbra is az alap; **Varázsceruza** opcionális arc (session). Prior incomplete person-auto sticky-seed fix superseded by person-fix2.

## Smoke

```powershell
cd hybrid_cut
$env:PYTHONPATH="$PWD\backend"
python -m pytest backend/tests/test_ai_tracks.py backend/tests/test_timeline_bg.py backend/tests/test_person_fix2.py backend/tests/test_person_auto.py -q
```
