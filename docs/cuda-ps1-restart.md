# HybridCut restart - cuda-ps1 (`2026-10-11-cuda-ps1`)

Feature stamp: **`2026-10-11-cuda-ps1`**.

Includes prior: cuda-restore · cuda-ep · seed-crash · rvm-matte · matte-visible · person-restore · auto-person · look-peak · ai-tracks · person-fix2 · nobg-layer.

## What broke (user paste after cuda-restore sync)

```
At ...\start_hybrid_cuda.ps1:316 char:107
+ ... (if ($curVer) { $curVer } else { "none" }) + ") â€” reinstall pin " + ...
Unexpected token 'reinstall' ...
Missing closing ')' ...
```

**Cause:** UTF-8 em-dash `U+2014` (`—`) in a double-quoted / concatenated `Write-Host` string. Windows PowerShell 5.1 often reads `.ps1` as system ANSI (Windows-1252). Bytes `E2 80 94` become mojibake `â€"` — and byte `0x94` is a **literal `"`**, which closes the string early. Parser then sees bare `reinstall` → Unexpected token.

Same class of bug as CapCut `run_gpu.ps1` parse fixes. Line 335 paren text was also hardened (single-quoted) though the em-dash was the hard break.

## What this stamp fixes

| Item | Change |
|------|--------|
| `start_hybrid_cuda.ps1` | Pure ASCII strings; em/en dashes → `-` |
| Nested labels | `$verLabel` / `$haveLabel` computed before `Write-Host` (no `$(if ...)` inside concat) |
| Paren messages | Single-quoted `Write-Host '...'` for CPU fallback / RESULT lines |
| SYNC | `2026-10-11-cuda-ps1` |
| Dist | unchanged (`index-D7Y29Lxp.js` / `index-CzWQ2bcp.css`) — launcher-only |

Behaviour of cuda-restore kept: pin `onnxruntime-gpu==1.30.0`, file probe `scripts/probe_cuda_ep.py`, **OK=1** keeps CUDA, FAIL → CPU ORT.

## Correct PowerShell (cwd)

**From CapCut root (`Documents\Videoeditor`):**

```powershell
cd $env:USERPROFILE\Documents\Videoeditor
.\hybrid_cut\start_hybrid_cuda.ps1
```

**From inside hybrid_cut:**

```powershell
cd $env:USERPROFILE\Documents\Videoeditor\hybrid_cut
.\start_hybrid_cuda.ps1
# NOT: .\hybrid_cut\start_hybrid_cuda.ps1
```

Expect console (no parse error):

```
Stamp: 2026-10-11-cuda-ps1 ...
=== CUDA EP PROBE ===
ORT_VERSION=1.30.0
PIN=1.30.0
PIN_OK=1
LISTED=1
OK=1
RESULT=OK
RESULT: OK - CUDA EP registered (morning-like path)
```

If `OK=0` / `RESULT: FAIL` → CPU ORT (still usable cutout).

## Agent Store sync (no GitHub / no PAT)

```powershell
& "$env:LOCALAPPDATA\Cursor\AgentStores\cursor_agent_stores\bc-41930eab-1501-4c19-acf3-0c9d63afbf4d\files\docs\capcut-features\sync_hybrid.ps1"
cd $env:USERPROFILE\Documents\Videoeditor
Get-Content .\hybrid_cut\SYNC_VERSION.txt   # expect: 2026-10-11-cuda-ps1
.\hybrid_cut\start_hybrid_cuda.ps1
# http://127.0.0.1:3847 - Ctrl+F5
```

## Pull + start (GitHub)

```powershell
cd $env:USERPROFILE\Documents\HybridCut
git pull
Get-Content .\SYNC_VERSION.txt   # 2026-10-11-cuda-ps1
.\install_to_videoeditor.ps1
cd $env:USERPROFILE\Documents\Videoeditor
$env:HYBRID_RVM_ONNX = "$PWD\models\rvm_resnet50_fp32.onnx"
.\hybrid_cut\start_hybrid_cuda.ps1
```

## UI checklist (HU)

1. Sync chip: **`2026-10-11-cuda-ps1`**.
2. Script parses under Windows PowerShell 5.1 (no Unexpected token).
3. Probe **OK=1** → chip **RVM CUDA**; person silhouette (not gray slab).
4. Probe **FAIL** → chip **CPU ORT**; still real person matte (slower).
5. Hard-refresh **Ctrl+F5** after sync.

## Smoke

```powershell
cd hybrid_cut
$env:PYTHONPATH="$PWD\backend"
python scripts\probe_cuda_ep.py
# expect OK=1 when ORT 1.30.0 + CUDA EP registered
```

## Dist

`frontend/dist`: `index-D7Y29Lxp.js` / `index-CzWQ2bcp.css` (unchanged)
