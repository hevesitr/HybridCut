## Stamp - restore-rvm (`2026-10-13-restore-rvm`)

Gyors Elonezet mirrors OSS RVM/rembg: MobileNet/ResNet ONNX -> soft pha -> encode. No crush/boost/good_enough ladder that wiped soft mattes into gray-slab/strip. Crush gated to Max bake only. Install: `PASTE_RESTORE_RVM_GITHUB.ps1` (ASCII) or `PASTE_RESTORE_RVM_INSTALL.ps1`. Dist: `index-DP52nBrj.js`.

# HybridCut — greenfield Videoeditor

Modern hybrid cutout editor for **Róbert Hevesi-Tóth**: Concat-inspired host/timeline/prefetch/MaskStore ideas + MatAnyone2-class quality pipeline, without vendoring those codebases.

| | |
|--|--|
| SYNC | `2026-10-13-restore-rvm` (see `SYNC_VERSION.txt`) |
| Sync target | `%USERPROFILE%\Documents\Videoeditor\hybrid_cut` |
| CapCut root | `%USERPROFILE%\Documents\Videoeditor` + root `run_hybrid.ps1` |
| Stack | **Python FastAPI** engines + **Vite/React** UI |
| Modes | **Gyors** = gyors/lágyabb (MobileNet scrub) · **Max** = élesebb export (ResNet50 + Éles szélek) |
| Target | Windows + NVIDIA RTX 3060 8GB · local / free only |
| GitHub | https://github.com/hevesitr/HybridCut |

Architecture plan: [`../hybrid-editor-plan.md`](../hybrid-editor-plan.md)

---

## License blockers (read first)

| Piece | License | Policy |
|-------|---------|--------|
| **MatAnyone2** weights / upstream | **S-Lab 1.0 — non-commercial** | Adapter only. Set `HYBRID_MATANYONE2_WEIGHTS`. **We do not redistribute weights.** |
| **Concat** | AGPL-3.0 | Ideas only — **no Concat source** |
| **RVM ONNX** | Upstream-dependent | Opt-in: parent `Documents\Videoeditor\models\*.onnx`, `scripts/download_rvm.ps1`, or `HYBRID_RVM_ONNX` |
| Our hybrid code | MIT (this tree) | See NOTICE |

Without RVM ONNX, **Gyors** uses a documented OpenCV GrabCut/center **heuristic fallback** (demo/CI — not ML quality).

---

## Confirmed working start (Windows PowerShell)

User-confirmed while UI already served on `:3847`:

```powershell
cd hybrid_cut
$env:PYTHONPATH="$PWD\backend"
& .\.venv\Scripts\python.exe -m hybrid_editor.main
```

From CapCut root after install/sync:

```powershell
cd $env:USERPROFILE\Documents\Videoeditor
Get-Content .\hybrid_cut\SYNC_VERSION.txt
# expect: 2026-10-13-restore-rvm
.\run_hybrid.ps1
# open http://127.0.0.1:3847
# Default: CPU ORT (real person matte). Optional CUDA after hard probe:
#   .\hybrid_cut\start_hybrid_cuda.ps1   (from Videoeditor)
#   .\start_hybrid_cuda.ps1              (from hybrid_cut)
# Pin: onnxruntime-gpu==1.30.0  (backend\requirements-gpu.txt)
# Compare edges with original Videoeditor: .\run_gpu.ps1 (Tk cutout)
```

One-click from Agent Store:

```powershell
& "$env:LOCALAPPDATA\Cursor\AgentStores\cursor_agent_stores\bc-41930eab-1501-4c19-acf3-0c9d63afbf4d\files\docs\capcut-features\sync_hybrid.ps1"
cd $env:USERPROFILE\Documents\Videoeditor
Get-Content .\hybrid_cut\SYNC_VERSION.txt   # 2026-10-13-restore-rvm
cd hybrid_cut
.\run_hybrid.ps1
```

GitHub clone into CapCut folder:

```powershell
cd $env:USERPROFILE\Documents
git clone https://github.com/hevesitr/HybridCut.git
cd HybridCut
.\install_to_videoeditor.ps1
cd $env:USERPROFILE\Documents\Videoeditor\hybrid_cut
.\run_hybrid.ps1
```

---



## Stamp - preview-fast (`2026-10-13-restore-rvm`)

Gyors Előnézet always shows a person cutout on CPU (hard salvage after soft MobileNet / gray-slab). Soft-matte crush no longer wipes peak~0.32 mattes. Proxy ~480 for fast scrub. Install: `PASTE_PREVIEW_FAST_GITHUB.ps1` (GitHub path; Agent Store Context may lag).

## Stamp - full-body-fast (`2026-10-13-restore-rvm`)

Hole-fill + hair/head protect (no checkerboard crown gaps), CPU Max bake MobileNet@~720 in-RAM (~45s for 10s@24 1080p — no guided upsample / full-HD PNG stream), hard-ish nobg crush (kill milky shoulder halo / ghost edges without reopening head holes), stronger CPU decontaminate/despill, wall-clock–aware Hátravan ETA, and **preview keep-alive** (click/mode re-matte must not blank Cutout). Includes matte-hard salvage.

**Install (pick one):**
- Agent Store: `PASTE_FULL_BODY_FAST_INSTALL.ps1` (or `PASTE_FULL_BODY_FAST_LOCAL.ps1` if Context lag)
- **No Agent Store / reliable:** `PASTE_FULL_BODY_FAST_GITHUB.ps1` — `git pull` `hevesitr/HybridCut` then install

Dist tip after rebuild is hashed in `frontend/dist/`.

## Stamp - matte-hard (`2026-10-13-restore-rvm`)

CPU ORT gray-slab toast fix on top of peak-ui: `hard_person_alpha` salvage (relaxed BG + GrabCut + multi-lobe prior) so Előnézet always shows a person matte; tighter closeup/slab rejection; auto Előnézet on Megnyitás with one retry. Install: `PASTE_MATTE_HARD_INSTALL.ps1`. Dist: `index-B9mlbaHn.js`.

## Stamp - peak-ui (`2026-10-13-restore-rvm`)

CapCut-class chrome on top of peak-cutout + simple-bg7: hero **HybridCut** brand, Sora/DM Sans, dark lime/orange shell, 1·Megnyitás / 2·Előnézet / 3·Export flow, mode/preview/export motion. Gyors preview uses `preview_boost_person_alpha` so the person matte is instantly visible. Single V1 + auto person BG only. Install: `PASTE_PEAK_UI_INSTALL.ps1`. Dist: `index-DcH3y0LK.js`.

## Stamp - simple-bg (`2026-10-13-restore-rvm`)

Tip restart: [`docs/simple-bg-restart.md`](docs/simple-bg-restart.md).

**Radical simplify for Róbert:** one V1 clip only (second drop rejected); focus **háttéreltávolítás**; Gyors/MobileNet default (no Max-on-open); strip AI sáv / Polírozás / B-roll / nobg Mozgatás from default flow. CPU-first ORT + gray-slab guards kept from rvm-back. Delete on the one clip; no Varázsceruza.

## Prior - run-ps1 (superseded)

## Stamp - run-ps1 (historical) (`2026-10-13-restore-rvm`)

Tip restart: [`docs/run-ps1-restart.md`](docs/run-ps1-restart.md).

**Why server never started after rvm-back:** `run_hybrid.ps1` still had a UTF-8 em-dash in a double-quoted Write-Host; PS 5.1 mojibake injected a stray `"` → Missing `}` / Unexpected `)`. Fix: ASCII-only HybridCut `.ps1` messages; single-quoted paren lines; `scripts/ort_present.py` instead of fragile `python -c`. Keeps CPU-first + hard probe from rvm-back.

## Prior - rvm-back (superseded) (`2026-10-11-rvm-back`)

Tip restart: [`docs/rvm-back-restart.md`](docs/rvm-back-restart.md).

**Why toast survived cpu-matte/matte-cpu2:** launch still defaulted CUDA → broken plugin EP / Conv Fallback gray-slab `pha`; soft CPU RVM person mattes were false-empty (cover/mean floors). Fix: **CPU-first** everywhere; CUDA only after hard probe OK; accept structured soft person alpha; clear sticky gray toast on recover.

## Prior - matte-cpu2 (superseded) (`2026-10-11-matte-cpu2`)

Tip restart: [`docs/matte-cpu2-restart.md`](docs/matte-cpu2-restart.md).

## Stamp - cpu-matte (superseded) (`2026-10-11-matte-cpu2`)

After cuda-ps1 + ORT 1.30.0, Maszk was still a gray slab: ORT logged `No registered plugin EP` + `MemcpyTransformer` while the UI showed **RTX 3060**. Probe **soft-OK** (cuDNN present) allowed a half-broken CUDA session. Fix: **no soft-OK**; on plugin EP miss / smoke slab → **CPUExecutionProvider only**; UI chip **CPU ORT**; auto Max when CUDA unusable. P0 = working person matte on CPU.

Restart: [`docs/cpu-matte-restart.md`](docs/cpu-matte-restart.md) · store [`../hybrid-cpu-matte-restart.md`](../hybrid-cpu-matte-restart.md)

## Prior - cuda-ps1 (`2026-10-11-matte-cpu2`)

Windows PowerShell 5.1 failed to parse `start_hybrid_cuda.ps1` after cuda-restore: UTF-8 em-dash `—` became mojibake `â€"` (stray `"`), so `Unexpected token 'reinstall'`. Fix: ASCII-only Write-Host strings, precomputed labels, single-quoted paren messages. Keeps ORT **1.30.0** pin + file probe.

Restart: [`docs/cuda-ps1-restart.md`](docs/cuda-ps1-restart.md) · store [`../hybrid-cuda-ps1-restart.md`](../hybrid-cuda-ps1-restart.md)

## Prior - cuda-restore (`2026-10-11-cuda-restore`)


Morning cutout worked on **`onnxruntime-gpu==1.30.0`**. After wand/paint/matte/cuda-ep stamps, unpinned reinstall pulled **1.31.0** and plugin EP stayed missing (`No registered plugin EP…`). Also: multiline `python -c` probe crashed under PowerShell quoting. Fix: pin **1.30.0** (`requirements-gpu.txt`), file probe `scripts/probe_cuda_ep.py` with clear **OK=1 / RESULT: OK|FAIL**, CPU fallback if still FAIL.

Restart: [`docs/cuda-restore-restart.md`](docs/cuda-restore-restart.md) · store [`../hybrid-cuda-restore-restart.md`](../hybrid-cuda-restore-restart.md)

## Prior — cuda-ep (`2026-10-11-cuda-ep`)

ORT log `No registered plugin EP device found for 'CUDAExecutionProvider'` means CUDA was **listed** but the **plugin EP was not registered**. Broken CUDA path produced uniform gray Maszk + toast. Fix: `probe_cuda_ep_usable` + force **CPU ORT** before RVM inference. Superseded by **cuda-restore** for morning pin + file probe.

Restart (historical): [`docs/cuda-ep-restart.md`](docs/cuda-ep-restart.md)

## Stamp — seed-crash (`2026-10-11-seed-crash`)

After SeedPaint removal, **`onNewProject` still called `setShowLargeSeed(false)`** → ReferenceError caught into the status line next to Assist/Ollama (`setShowLargeSeed is not defined`). That aborted the rest of the Új-projekt UI reset and made Előnézet look broken. Fix: drop all dead seed-modal refs; Max polish must not replace a good RVM matte with a gray slab. Keeps **rvm-matte** fp32-first + CUDA→CPU recovery.

Restart: [`docs/seed-crash-restart.md`](docs/seed-crash-restart.md) · store [`../hybrid-seed-crash-restart.md`](../hybrid-seed-crash-restart.md)

## Stamp — rvm-matte (`2026-10-11-rvm-matte`)

Toast from **matte-visible** was correct (uniform gray Maszk = degenerate all-ones alpha). RVM on RTX 3060 + CUDA ORT still emitted that slab (`MemcpyTransformer` / fp16-first Max / tiny-pha upscale). Fix: **fp32-first** resolve + fp16→fp32 sibling, CapCut `1×1×1×1` cold recurrent, safe `pha` extract (no dust→full resize), CUDA provider options, **CUDA→CPU session** when pha is empty/degenerate.

Restart: [`docs/rvm-matte-restart.md`](docs/rvm-matte-restart.md) · store [`../hybrid-rvm-matte-restart.md`](../hybrid-rvm-matte-restart.md)

---

## Prior — matte-visible (`2026-10-11-matte-visible`)

Screenshots after person-restore: **Maszk** = solid light-gray rectangle on checker; **Cutout** = opaque full source; chip still **Gyors**. Cause: near-uniform / all-ones alpha counted as success → gray slab + false Cutout ✓. Fix: `is_matte_degenerate`, toast on failure (detection only). Superseded by **rvm-matte** for real CUDA inference recovery.

Restart (historical): [`docs/matte-visible-restart.md`](docs/matte-visible-restart.md)

---

## Prior — person-restore (`2026-10-11-person-restore`)

Wand-era face scraps in MaskStore + Gyors skip RVM. Megnyitás purge + Max + Éles. Superseded by **matte-visible** / **rvm-matte** for the gray-slab failure.

Restart (historical): [`docs/person-restore-restart.md`](docs/person-restore-restart.md)

---

## Prior — auto-person (`2026-10-11-auto-person`)

Removed wand/paint UI + Delete-key clip delete. Incomplete for recognition (MaskStore disk not purged; open stayed Gyors). Superseded by **person-restore**.

Restart (historical): [`docs/auto-person-restart.md`](docs/auto-person-restart.md)

---

## Prior — look-peak (`2026-10-11-look-peak`)

On top of `2026-10-11-ai-tracks` + `2026-10-11-person-fix2`. **Visual shell peak only** (CapCut desktop feel): deeper charcoal, lime Export, preview focus, dark timeline + playhead glow, Syne/Figtree, atmospheric grain. **AI sáv + Polírozás retained** from ai-tracks.

Restart: [`docs/look-peak-restart.md`](docs/look-peak-restart.md) · store [`../hybrid-look-peak-restart.md`](../hybrid-look-peak-restart.md)

---

## Prior — ai-tracks (`2026-10-11-ai-tracks`)

On top of person-fix2. **AI sáv + Polírozás** on stack/drop (existing RVM/APEX). Hand-drag multi-track kept; full-person default unchanged. Tip stamp moved to **look-peak** (visual).

Restart: [`docs/ai-tracks-restart.md`](docs/ai-tracks-restart.md) · store [`../hybrid-ai-tracks-restart.md`](../hybrid-ai-tracks-restart.md)

---

## Prior — person-fix2 (`2026-10-11-person-fix2`)

On top of incomplete `2026-10-11-person-auto`. **Full-person auto matte is the rock-solid default:** Megnyitás → Előnézet → RVM keeps **all people** + body parts (hair/hands/feet) → Cutout/Export `*_full_nobg` without Varázsceruza. Face-only wand is **session RAM only** (never disk); clip-select cannot re-arm sticky replace. Max preview/bake long-side raised for sharp 4K. Radír isolation + overlay Mozgatás kept.

Restart: [`docs/person-fix2-restart.md`](docs/person-fix2-restart.md) · store [`../hybrid-person-fix2-restart.md`](../hybrid-person-fix2-restart.md)

---

## Prior — person-auto (`2026-10-11-person-auto`) — incomplete

Partial sticky-seed fix on Megnyitás only; clip-select + disk write of `replace` still broke default person detect. Superseded by **person-fix2**.

Restart (historical): [`docs/person-auto-restart.md`](docs/person-auto-restart.md)

---

## Prior — paint-face (`2026-10-11-paint-face`) — removed in auto-person

Historical: Radír / Ecset / Lasszó / Varázsceruza face-only replace. **Removed in `2026-10-11-auto-person`** — auto full-person RVM only. Nobg **Mozgatás** / Pozíció kept.

Restart (historical): [`docs/paint-face-restart.md`](docs/paint-face-restart.md)

---

## Prior — nobg-layer (`2026-10-11-nobg-layer`)

On top of `2026-10-11-concat-look`. **Movable transparent nobg layers (CapCut/Concat overlay subset):** import `*_full_nobg.mov` / alpha WebM onto V1/V2 with preserved alpha; **Pozíció X/Y** + **Méretérték** + preview **Mozgatás** drag + **Visszaállítás**; preview + bake composite transform over lower track / checker; export card **Nobg a timeline-ra**. No rotation/keyframes/blend modes.

Restart: [`docs/nobg-layer-restart.md`](docs/nobg-layer-restart.md) · store [`../hybrid-nobg-layer-restart.md`](../hybrid-nobg-layer-restart.md)

---

## Prior — concat-look (`2026-10-11-concat-look`)

On top of `2026-10-11-clip-delete`. **Concat visual chrome only** (no effects/text/audio mixer port): charcoal dark + lime primary; projects home with **+ Új projekt** / Megnyitás sidebar; editor shell = big preview + professional timeline (HH:MM:SS:FF ruler, tool strip, L/V/M track chrome) + slim right details (**PROJECT / TIMELINE / CONTENTS**); green **Export** top-right; empty preview „Nincs tartalom a lejátszási fej alatt”. All HybridCut BG-remove kept (Gyors/Max, paint, bake → `C:\bgcut`).

Restart: [`docs/concat-look-restart.md`](docs/concat-look-restart.md) · store [`../hybrid-concat-look-restart.md`](../hybrid-concat-look-restart.md)

---

## Prior — clip-delete (`2026-10-11-clip-delete`)

On top of `2026-10-11-timeline-bg`. **Clip tools back in the rail (apex/concat):** per-row **Töröl** on Klip lista; **Duplikál / Töröl / Vágás / ← → / → B-roll / → V1** next to Be/Ki (not buried under Részletek); Delete/Backspace removes the selected clip; last V1 stays protected. Lime/orange look2 retained.

Restart: [`docs/clip-delete-restart.md`](docs/clip-delete-restart.md) · store [`../hybrid-clip-delete-restart.md`](../hybrid-clip-delete-restart.md)

---

## Prior — timeline-bg (`2026-10-11-timeline-bg`)

On top of `2026-10-11-concat-flow`. **Multi-track timeline + BG remove only:** V1/V2 clip blocks with click-select, drag reorder / vertical track stack, Be/Ki trim handles; preview composites both tracks at playhead; bake uses the same plan; Varázsceruza scanline flood-fill + per-selected-clip seed. Lime/orange look2 retained. Hungarian labels.

Restart: [`docs/timeline-bg-restart.md`](docs/timeline-bg-restart.md) · store [`../hybrid-timeline-bg-restart.md`](../hybrid-timeline-bg-restart.md)

---

## Prior — concat-flow (`2026-10-11-concat-flow`)

On top of `2026-10-10-look2`. **Concat-like project flow:** **Új projekt** clears timeline/media/seed/bake (confirm if dirty) back to full-bleed empty drop; **+ V1 klip** / drop append stacks clips on V1 after existing; B-roll on V2. **Preview fill:** Forrás / Cutout / Maszk use `width/height: 100%` + `object-fit: contain` so proxy frames fill the stage (wipe/Összehasonlítás stays split). Lime/orange look2 shell retained.

Restart: [`docs/concat-flow-restart.md`](docs/concat-flow-restart.md) · store [`../hybrid-concat-flow-restart.md`](../hybrid-concat-flow-restart.md)

## Prior — look2 (`2026-10-10-look2`)

On top of `2026-10-10-look`. **Full-bleed workspace:** empty state and editor use the same viewport-width shell — compact topbar, full-width Megnyitás/Minta CTA row, Gyors/Max as slim horizontal chips in the left rail, drop stage fills remaining width/height. No skinny centered marketing column (`min(720px)` removed). Syne + Figtree, lime `#b8f000` / orange `#ff7a1a` retained.

Restart: [`docs/look2-restart.md`](docs/look2-restart.md) · store [`../hybrid-look2-restart.md`](../hybrid-look2-restart.md)

## Prior — look (`2026-10-10-look`)

On top of `2026-10-10-layout-fix` (+ `start-fix` · `eta-ui`). **Visual direction:** Syne + Figtree, deep olive ink with lime/orange atmosphere, hero-level HybridCut in compact topbar, slim rail (~250–280px), preview-dominant stage, secondary timeline. Gyors/Max keep ETA on the mode cards; duplicate ETA cards removed; 1→2→3 flow refined (underline steps, brand CTAs). Motions: mode-pick, preview-load, export result-in. Dense motor/VRAM logs stay under Részletek.

Restart: [`docs/look-restart.md`](docs/look-restart.md) · store [`../hybrid-look-restart.md`](../hybrid-look-restart.md)

## Prior — layout-fix (`2026-10-10-layout-fix`)

On top of `2026-10-10-start-fix` (+ `eta-ui`). **Critical UX:** editor is one composition — compact topbar (HybridCut + RTX 3060), left slim rail, **preview fills remaining height**, timeline strip secondary. Root cause of the empty dark void: `.app` had `grid-template-rows: auto 1fr` while the DOM had three children (`topbar`, `intel-strip`, `workspace`), so `intel-strip` ate the `1fr` row.

Also: Be/Ki range ETA labeled clearly; multi-hour Max warn for long clips; start-fix launcher retained (no CapCut remount pip).

Restart: [`docs/layout-fix-restart.md`](docs/layout-fix-restart.md) · store [`../hybrid-layout-fix-restart.md`](../hybrid-layout-fix-restart.md)

## Prior — start-fix (`2026-10-10-start-fix`)

On top of `2026-10-10-eta-ui`. `start_hybrid_cuda.ps1` **does not** call CapCut `remount_ort_gpu.ps1` pip upgrade (Windows AV). PATH-injects nvidia cudnn from hybrid/parent site-packages; opt-in `$env:HYBRID_CALL_REMOUNT='1'` is path-only / skip-pip.

## Prior — eta-ui (`2026-10-10-eta-ui`)

On top of `2026-10-10-apex`. CapCut-clean helper UI + **upfront Gyors / Max háttéreltávolítás ETA**.

### ETA (RTX 3060-class)

- Mode cards + export strip show **both** Gyors and Max estimates before bake
- Live update when Be/Ki, clip, fps, or resolution changes
- During bake: remaining time from `written/total` frames (fallback: progress %)
- Hungarian labels: „Kb. 12 mp” / „Kb. 1 perc 20 mp”
- Formula: `frames × sec/frame(mode, resolution) + mux` — calibrated `0.028` / `0.165` s/frame @ 1080p

### Simple helper UX

- Visible 1-2-3: Megnyitás → Előnézet/Cutout → Export (ETA on Export)
- Timeline/tech controls under **Részletek** · lime/orange HybridCut identity kept
- Apex cutout/export quality unchanged

Restart: [`docs/eta-ui-restart.md`](docs/eta-ui-restart.md) · store [`../hybrid-eta-ui-restart.md`](../hybrid-eta-ui-restart.md)

---

## Stamp — apex (`2026-10-10-apex`)

Included in eta-ui. CapCut-clean one-click cutout + stronger Max polish — **no MatAnyone2 weights shipped**.

### Cutout quality (Max + Éles szélek)

- **`APEX_SPEC`** Max default (on top of `PEAK_SPEC`): hair strand recover, micro rim despill, stronger unknown-band / bright-fringe / edge sharpen
- Multi-person keep retained · Gyors scrub stays MobileNet-fast

### One-click UX

- Hero: HybridCut brand-first · Megnyitás → auto Cutout → Exportálás
- Fewer chips (mode + cutout/export) · RVM / Ollama / VRAM under **Részletek**
- Lime `#b8f000` · orange `#ff7a1a` · Sora + Manrope · flow-steps + result card

### Export

- Always `_full_nobg.mov` + checker `_preview.mp4` · progress shows accurate `written/total` frame count

Restart: [`docs/apex-restart.md`](docs/apex-restart.md) · store [`../hybrid-apex-restart.md`](../hybrid-apex-restart.md)

---

## Stamp — peak (`2026-10-10-peak`)

Included in apex. CapCut left-side cutout bar + MatAnyone2 ideas (warmup×10, tight unknown-band hair, fringe/spill).

### Cutout quality (Max + Éles szélek)

- **`PEAK_SPEC`**: stronger hair / decontam / despill + unknown-band refine + bright-fringe kill + edge-gradient sharpen
- Multi-person keep (≥20% of largest) retained from continue
- Residual BG island kill + cyan/white fringe clean on cutout RGB

### Speed (RTX 3060 8GB)

- **Gyors** scrub: MobileNet + proxy/downsample (unchanged fast path)
- **Max** bake: full-res RVM + polish; BGRA streamed to disk before MOV mux

### Export + UX

- Always `C:\bgcut\{stem}_full_nobg.mov` + checker `_preview.mp4` · UI result card · bulletproof `resolve_ffmpeg`

Restart: [`docs/peak-restart.md`](docs/peak-restart.md) · store [`../hybrid-peak-restart.md`](../hybrid-peak-restart.md)

---

## Stamp — continue (`2026-10-10-continue`)

Supersedes `2026-10-05-ui-nobg`. Multi-person Max matte + export reliability + leaner chrome. Included in peak.

### Multi-person Max cutout

- `keep_person_instances_soft` / `suppress_residual_bg` keep **all person-sized** CCs (≥20% of largest), not only the single largest
- Secondary subjects no longer left as a solid BG plate after Max + Éles szélek

### Export reliability

- After bake: always `{stem}_full_nobg.mov` + checker `{stem}_full_nobg_preview.mp4` (synthesized from BGRA if in-memory preview missing)
- Mux fail → clear log + red **Export sikertelen** (never silent `alpha/` success)
- Full In/Out bake · default `C:\bgcut\` · RVM recurrent size reset unchanged

### UI polish

- Compact intel chips (Max/Gyors · RVM · RVM ember · export/seed when needed)
- Hero: one ONNX+ORT chip (Ollama / motor detail under **Részletek**)
- Paint tools stay in chrome above the frame; lime→orange HybridCut identity

### Prior — UI polish + visible nobg (`2026-10-05-ui-nobg`)

- Result card + Explorer + in-app checker `_preview.mp4`
- Slimmer strip / meta-fold / checker motion

### Prior — paint UX + bgcut MOV + RVM (`2026-10-05-paint-fix`)

Supersedes / includes `2026-10-05-bgcut-mov` · `2026-10-05-rvm-state` · prior polish bake paths.

### Primary export — `C:\\bgcut\\{stem}_full_nobg.mov`

- Videoeditor-style `resolve_ffmpeg` (PATH + `FFMPEG_PATH` + common installs)
- Alpha PNG dumps under `C:\\bgcut\\alpha\\` **off by default** (`HYBRID_BGCUT_DUMP_ALPHA=1` to enable)
- Status / Explorer select the `.mov` (not the alpha folder)
- RVM recurrent `r1..r4` reset on H/W or downsample change (`Expand_134` fix)

### Paint UX — removed (`2026-10-11-auto-person`)

Ecset / Radír / Lasszó / Varázsceruza and seed paint chrome are **gone**. Auto full-person RVM only.

### Drop hint

- „Ejtés: klip a timeline-ra” **never** covers a loaded timeline (only empty hero drop).

### Freeze / ORT

- **RVM recurrent reset** when `H×W` or downsample ratio changes (`Expand_*` 26×45 vs 51×90). Full-res `src` + `downsample_ratio` (RVM-native).

## Hybrid polish (prior stamp) — merges three fixes

Supersedes `full-bake-bgcut` · `max-accuracy` · `simple-preview`.

### Full-duration bake + bgcut path

- Exportálás hanggal bakes full In/Out (`max_frames` default **`null`**, not 48)
- Default out dir **`C:\bgcut\`** (`HYBRID_BGCUT_DIR` override)
- Alpha MOV `{stem}_full_nobg.mov` + companion `{stem}_full_nobg_preview.mp4`

### Max cutout accuracy

- **Full-res RVM** for Max bake/preview backbone (no 768 long-side downsample)
- **ResNet50 preferred** when present (`prefer_quality`)
- **Residual BG island kill** via hard-core support (`suppress_residual_bg`) — neck/shoulder leftovers
- **Cyan / white fringe**: CapCut `decontaminate_fringe` + `suppress_color_spill` on cutout RGB
- CapCut Videoeditor refine path (no aggressive morph-open that creates islands)

### Simple preview UX

- **Összehasonlítás**: drag the vertical wipe line on the image.
- Auto person cutout on Előnézet — no manual seed tools.

## Person matte (this stamp)

- **Max without MatAnyone2 weights** → RVM quality pipeline person alpha (never empty fake MatAnyone2)
- Status: **„MatAnyone2 nincs — RVM ember-maszk”** vs **„MatAnyone2 aktív”**
- **Előnézet** / upload / AI Polírozás: auto RVM → **Cutout** when matte ready (toast)
- Manual paint/wand **removed** — auto full-person only
- Empty **Maszk** view: overlay + „Előnézet futtatása”
- Optional local `.pth`: [`docs/matanyone2-weights.md`](docs/matanyone2-weights.md) (`HYBRID_MATANYONE2_WEIGHTS`)

## Hungarian UX + Forrás default

- Preview default: **Forrás** on load — Előnézet after matte → **Cutout**
- View toggle: **Forrás | Maszk | Cutout | Összehasonlítás**
- Weak/empty matte → source underlay + clear „Nincs ember-maszk” cue
- Help line: `1) Videó betöltése 2) Előnézet 3) Exportálás → C:\bgcut\*_full_nobg.mov (teljes hossz)`
- Export: full In/Out (no 48-frame preview cap); default dir `C:\bgcut\`; ProRes/qtrle `{stem}_full_nobg.mov` + companion preview. See [`docs/full-bake-bgcut-restart.md`](docs/full-bake-bgcut-restart.md).

## Phase 5 + cuDNN PATH

- **FastEngine** resolves RVM ONNX from `HYBRID_RVM_ONNX` / parent `models/` (prefers **fp32**)
- `hybrid_editor.cuda_path`: PATH + `os.add_dll_directory` for pip `nvidia-cudnn-cu12` **before** ORT session
- Soft fallback: CUDA/cuDNN `LoadLibrary` failure → **CPU EP** with clear status (no raw ORT crash in UI)
- `run_hybrid.ps1`: auto-install `nvidia-cudnn-cu12` when `cudnn64_*.dll` missing; PATH prepend hybrid+parent
- `start_hybrid_cuda.ps1`: PATH-inject nvidia cudnn from hybrid/parent; **no** CapCut remount pip by default; opt-in `HYBRID_CALL_REMOUNT=1` (path-only)
- Workaround B: `$env:HYBRID_REUSE_PARENT_VENV='1'` (CapCut `.venv` that already works)

---

## Pip / venv notes (Windows)

- `run_hybrid.ps1` does **not** run `pip install --upgrade pip` by default. Opt-in: `$env:HYBRID_UPGRADE_PIP = "1"`.
- `start_hybrid_cuda.ps1` does **not** call CapCut remount pip upgrade (AV on some Windows). PATH inject only.
- Deps install with `--trusted-host pypi.org --trusted-host files.pythonhosted.org` and `--no-cache-dir`.
- Force parent venv (Workaround B): `$env:HYBRID_REUSE_PARENT_VENV = "1"`.
- GPU ORT / cuDNN:

```powershell
cd $env:USERPROFILE\Documents\Videoeditor
$env:HYBRID_RVM_ONNX = "$PWD\models\rvm_resnet50_fp32.onnx"
.\hybrid_cut\start_hybrid_cuda.ps1
# PATH inject only; no remount pip upgrade
# immediate bypass: .\run_hybrid.ps1
# opt-in path-only remount: $env:HYBRID_CALL_REMOUNT='1'; .\hybrid_cut\start_hybrid_cuda.ps1
```

Restart cheat-sheet: [`../hybrid-cudnn-restart.md`](../hybrid-cudnn-restart.md). Hotfix paste: `PASTE_FIX_RUN_HYBRID.ps1`.

---

## Tests

```powershell
cd $env:USERPROFILE\Documents\Videoeditor\hybrid_cut
$env:PYTHONPATH = "$PWD\backend"
& .\.venv\Scripts\python.exe -m pytest backend\tests -q
```
