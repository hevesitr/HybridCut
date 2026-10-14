# restore-rvm diagnostics — Maszk gyenge / empty preview / slow export

Minimal, **opt-in**, reversible. Does not change the soft Gyors alpha path
(`2026-10-13-restore-rvm`). Default install (PASTE / `install_to_videoeditor.ps1`)
leaves diagnostics **off**.

## What it covers

| Symptom | What to look for |
|---------|------------------|
| Toast **"Maszk gyenge — automatikus javítás…"** | Frontend keys off `matte_error` matching `egyenletes` / `teljes-keret` / `0-255` (see `App.tsx`). Backend logs the same gate as `maszk_gyenge_toast: true` plus alpha stats. |
| Empty person preview | `matte_empty: true` + `DIAG_MATTE_WEAK` payload (`max` / `cover` / `std`). |
| Slow export | `DIAG_EXPORT_TIMING` stages: `seek_open` → `matte_loop` → `preview_mp4` → `prores_mov` → `done`. |

## Enable (Windows)

From HybridCut or `%USERPROFILE%\Documents\Videoeditor\hybrid_cut`:

```powershell
.\scripts\diag_matte_weak.ps1
.\run_hybrid.ps1
# or: .\start_hybrid_cuda.ps1
```

Env flags set by the script (ASCII names):

| Variable | Effect |
|----------|--------|
| `HYBRID_DIAG_MATTE=1` | Log trigger values when empty / Maszk-gyenge condition fires |
| `HYBRID_DIAG_ALPHA_DUMP=1` | Write `*_raw.png` under `%TEMP%\hybridcut_diag\alpha\` on weak/empty preview |
| `HYBRID_DIAG_EXPORT_TIMING=1` | Log bake stage wall times |
| `HYBRID_BGCUT_DUMP_ALPHA=1` | Existing bake hook: PNG sequence under `bgcut\alpha\` |
| `HYBRID_DIAG_DIR` | Optional override for dump root |

## Disable

Close the shell, or:

```powershell
Remove-Item Env:HYBRID_DIAG_MATTE -ErrorAction SilentlyContinue
Remove-Item Env:HYBRID_DIAG_ALPHA_DUMP -ErrorAction SilentlyContinue
Remove-Item Env:HYBRID_DIAG_EXPORT_TIMING -ErrorAction SilentlyContinue
Remove-Item Env:HYBRID_BGCUT_DUMP_ALPHA -ErrorAction SilentlyContinue
```

No code rollback required — hooks are no-ops when flags are unset.

## Code map

- `backend/hybrid_editor/diag_matte.py` — helpers
- `FastEngine.preview_frame` / `MaxQualityEngine.preview_frame` — weak/empty log + optional dump
- `FastEngine.bake` / `MaxQualityEngine._bake_quality_pipeline` — stage timers
- `scripts/diag_matte_weak.ps1` — one-shot env enable

## Soft Gyors reminder

restore-rvm keeps **real soft alpha** on Gyors (no preview crush / boost / good_enough wipe).
Diagnostics only observe; they do not re-enable aggressive crush.
