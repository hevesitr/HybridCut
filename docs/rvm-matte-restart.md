# HybridCut restart — rvm-matte (`2026-10-11-rvm-matte`)

Feature stamp: **`2026-10-11-rvm-matte`**.

Includes prior: matte-visible · person-restore · auto-person · look-peak · ai-tracks · person-fix2 · nobg-layer.

## Why the toast appeared (honest)

After **matte-visible**, the UI correctly refused Cutout ✓ when alpha was a **near-uniform / all-ones slab** (Maszk = solid light-gray rectangle). Toast:

> Hibás maszk (egyenletes szürke lap) — RVM/ONNX újra, vagy Max mód

That stamp **detected** failure. It did **not** fix RVM inference on RTX 3060 + CUDA ORT.

### Root cause of the uniform matte

| Factor | What went wrong |
|--------|-----------------|
| **CUDA EP + `torch-jit-export`** | ORT logs `MemcpyTransformer` — parts of the RVM graph copy CPU↔GPU. On 3060 this often yields a **flat / all-ones `pha`** (silent wrong output, not a hard error). |
| **fp16 preferred for Max** | `_RVM_NAMES_QUALITY` listed `rvm_resnet50_fp16.onnx` **before** fp32. fp16 + CUDA Memcpy is the flaky path. |
| **Tiny / dust `pha` upscaled** | A 1×1 (or tiny) pha of ~1.0 bilinear-resized to full frame → perfect gray slab. |
| **Recurrent cold-start** | Meta-derived zeros could disagree with CapCut’s always-`1×1×1×1` cold `r1i..r4i`. |
| **No CUDA→CPU recovery** | Session stayed on CUDA after useless pha; heuristic sometimes also looked “full frame” on busy skin BGs. |

Detection from matte-visible (degenerate checks + toast) stays. This stamp **makes RVM emit a real person matte again**.

## What we fixed

| Path | Behaviour |
|------|-----------|
| Model resolve | **fp32 before fp16** (Gyors + Max). Auto-pick fp32 sibling when env points at `*fp16*` (override: `HYBRID_RVM_ALLOW_FP16=1`). |
| CUDA session | Provider options: `do_copy_in_default_stream`, cudnn algo `DEFAULT`, soft VRAM cap (~3.5GB). |
| Recurrent | CapCut-safe **`1×1×1×1` cold** feeds; refuse non-finite / bad-rank state. |
| `pha` extract | Prefer CapCut `fgr,pha,r1o..`; **refuse tiny→full resize**; NaN scrub. |
| Bad CUDA pha | Cold retry → **CPU EP session** (same ONNX) → promote primary to CPU if CPU matte is good. |
| Degenerate guard | Still rejects slabs; MaskStore still refuses flat PNGs; toast still fires if everything fails. |

## Pull + start (GitHub)

```powershell
cd $env:USERPROFILE\Documents\HybridCut
git pull
Get-Content .\SYNC_VERSION.txt   # 2026-10-11-rvm-matte
.\install_to_videoeditor.ps1
cd $env:USERPROFILE\Documents\Videoeditor
# Prefer fp32 ResNet for Max quality on 3060
$env:HYBRID_RVM_ONNX = "$PWD\models\rvm_resnet50_fp32.onnx"
.\hybrid_cut\start_hybrid_cuda.ps1
# http://127.0.0.1:3847 — hard-refresh (Ctrl+F5)
```

If CUDA pha still slabs once, status/detail may show **CUDA→CPU** — mattes stay correct on CPU until you remount ORT GPU / switch to fp32.

## Agent Store sync (no GitHub / no PAT)

```powershell
& "$env:LOCALAPPDATA\Cursor\AgentStores\cursor_agent_stores\bc-41930eab-1501-4c19-acf3-0c9d63afbf4d\files\docs\capcut-features\sync_hybrid.ps1"
cd $env:USERPROFILE\Documents\Videoeditor
Get-Content .\hybrid_cut\SYNC_VERSION.txt   # expect: 2026-10-11-rvm-matte
.\run_hybrid.ps1
```

Hard-refresh **Ctrl+F5**.

## Kept from person-restore / auto-person

- No **Varázsceruza** / Ecset / Radír / Lasszó
- **Delete** / Backspace clip delete
- MaskStore purge on Megnyitás
- Max + Éles on open

## UI — Róbert checklist (HU)

1. **Megnyitás** — videó → **Max** + **Éles**.
2. **Maszk** — személy sziluett sakktáblán (**nem** egyszínű szürke téglalap).
3. **Cutout** — háttér átlátszó (sakktábla), nem a nyers teljes kép.
4. Toast „Hibás maszk…” **nem** jelenik meg, ha az RVM/CPU path jó maszkot ad.
5. `SYNC_VERSION` chip: **`2026-10-11-rvm-matte`**.

## Smoke

```powershell
cd hybrid_cut
$env:PYTHONPATH="$PWD\backend"
$env:HYBRID_RVM_ONNX = "$env:USERPROFILE\Documents\Videoeditor\models\rvm_resnet50_fp32.onnx"
python -m pytest backend/tests/test_rvm_matte.py backend/tests/test_matte_visible.py backend/tests/test_rvm_input_dtype.py -q
```

## Dist

`frontend/dist`: `index-DLrm3ph7.js` / `index-B7IYoAdx.css`
