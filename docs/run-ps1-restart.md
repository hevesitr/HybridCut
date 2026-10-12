> **Tip is now [`simple-bg-restart.md`](simple-bg-restart.md) (`2026-10-12-simple-bg2`).**

# HybridCut restart - run-ps1 (`2026-10-11-run-ps1`)

Feature stamp: **`2026-10-11-run-ps1`**.

Includes prior: rvm-back · matte-cpu2 · cpu-matte · cuda-ps1 · cuda-restore · cuda-ep · seed-crash · rvm-matte · matte-visible · person-restore · auto-person · look-peak.

## What broke (user paste after rvm-back sync)

```
At ...\run_hybrid.ps1:124 char:36
if (-not $env:HYBRID_ORT_PROVIDER) {
Missing closing '}' ...
+ ... HYBRID_ORT_PROVIDER=cpu (default â€” skip broken CUDA Conv Fallback)"
Unexpected token ')' ...
```

**Cause:** UTF-8 em-dash `U+2014` (`—`) in a double-quoted `Write-Host` string on the CPU-default line. Windows PowerShell 5.1 often reads `.ps1` as system ANSI (Windows-1252). Bytes `E2 80 94` become mojibake `â€"` — and byte `0x94` is a **literal `"`**, which closes the string early. Parser then sees bare `)` / broken `if` block.

Same class of bug as **cuda-ps1** (`start_hybrid_cuda.ps1`). Probe FAIL → KEEP cpu logic was correct; the launcher never started because parse failed first.

Also hardened: nested `()` / `print('1' if ...)` inside `"..."` for `python -c` (moved to `scripts/ort_present.py`).

## What this stamp fixes

| Item | Change |
|------|--------|
| `run_hybrid.ps1` | Pure ASCII; em-dash → `-`; single-quoted paren messages; no `$(if ...)` inside concat |
| `start_hybrid_cuda.ps1` | Remaining em-dashes / HU accents in comments cleaned; RESULT OK line ASCII |
| ORT presence | `scripts/ort_present.py` (both launchers; no `python -c`) |
| SYNC | `2026-10-11-run-ps1` |
| Dist | unchanged (`index-BGJ2h0CY.js` / `index-Bv2GNnfq.css`) - launcher-only |

Behaviour of rvm-back kept: CPU-first default; CUDA only after hard probe OK; FAIL → KEEP cpu.

## Correct PowerShell (cwd = hybrid_cut)

**From CapCut root (`Documents\Videoeditor`):**

```powershell
cd $env:USERPROFILE\Documents\Videoeditor
.\hybrid_cut\start_hybrid_cuda.ps1
# or, after probe already decided cpu:
.\hybrid_cut\run_hybrid.ps1
```

**From inside hybrid_cut:**

```powershell
cd $env:USERPROFILE\Documents\Videoeditor\hybrid_cut
.\run_hybrid.ps1
# NOT: .\hybrid_cut\run_hybrid.ps1
```

Expect console (no parse error; plugin missing):

```
SYNC_VERSION: 2026-10-11-run-ps1
HYBRID_ORT_PROVIDER=cpu (default - skip broken CUDA Conv Fallback)
...
Starting HybridCut...
```

With `start_hybrid_cuda.ps1` when probe fails:

```
=== CUDA EP PROBE ===
OK=0
RESULT: FAIL
KEEP: HYBRID_ORT_PROVIDER=cpu (CPU-first; real person matte; no Conv Fallback)
```

Then `run_hybrid.ps1` starts the server on http://127.0.0.1:3847.

## Agent Store sync (no GitHub / no PAT)

```powershell
& "$env:LOCALAPPDATA\Cursor\AgentStores\cursor_agent_stores\bc-41930eab-1501-4c19-acf3-0c9d63afbf4d\files\docs\capcut-features\sync_hybrid.ps1"
cd $env:USERPROFILE\Documents\Videoeditor
Get-Content .\hybrid_cut\SYNC_VERSION.txt   # expect: 2026-10-11-run-ps1
cd hybrid_cut
.\run_hybrid.ps1
# http://127.0.0.1:3847 - Ctrl+F5
```

Or CUDA path (probe FAIL still starts via KEEP cpu → run_hybrid):

```powershell
cd $env:USERPROFILE\Documents\Videoeditor\hybrid_cut
.\start_hybrid_cuda.ps1
```

## Pull + start (GitHub)

```powershell
cd $env:USERPROFILE\Documents\HybridCut
git pull
Get-Content .\SYNC_VERSION.txt   # 2026-10-11-run-ps1
.\install_to_videoeditor.ps1
cd $env:USERPROFILE\Documents\Videoeditor\hybrid_cut
.\run_hybrid.ps1
```

## UI checklist (HU)

1. Sync chip: **`2026-10-11-run-ps1`**.
2. `run_hybrid.ps1` / `start_hybrid_cuda.ps1` parse under Windows PowerShell 5.1 (no Unexpected token / Missing `}`).
3. Probe **FAIL** → KEEP cpu → server starts; chip **CPU ORT**; person silhouette.
4. Hard-refresh **Ctrl+F5** after sync.

## Dist

`frontend/dist`: `index-BGJ2h0CY.js` / `index-Bv2GNnfq.css` (unchanged)
