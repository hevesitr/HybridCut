# HybridCut — greenfield Videoeditor

Modern hybrid cutout editor for **Róbert Hevesi-Tóth**: Concat-inspired host/timeline/prefetch/MaskStore ideas + MatAnyone2-class quality pipeline, without vendoring those codebases.

| | |
|--|--|
| SYNC | `2026-10-10-eta-ui` (see `SYNC_VERSION.txt`) |
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
# expect: 2026-10-10-eta-ui
.\run_hybrid.ps1
# open http://127.0.0.1:3847
# CUDA+cuDNN: .\hybrid_cut\start_hybrid_cuda.ps1
# Compare edges with original Videoeditor: .\run_gpu.ps1 (Tk cutout)
```

One-click from Agent Store:

```powershell
& "$env:LOCALAPPDATA\Cursor\AgentStores\cursor_agent_stores\bc-41930eab-1501-4c19-acf3-0c9d63afbf4d\files\docs\capcut-features\sync_hybrid.ps1"
cd $env:USERPROFILE\Documents\Videoeditor
.\run_hybrid.ps1
```

GitHub clone into CapCut folder:

```powershell
cd $env:USERPROFILE\Documents
git clone https://github.com/hevesitr/HybridCut.git
cd HybridCut
.\install_to_videoeditor.ps1
cd $env:USERPROFILE\Documents\Videoeditor
.\run_hybrid.ps1
```

---

## Stamp — eta-ui (`2026-10-10-eta-ui`)

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

### Paint UX (from paint-fix)

Supersedes stuck overlay / freeze from `2026-10-05-hybrid-polish` simple-preview paint-on-canvas.

### Toolbar chrome (not in the picture)

- **Ecset / Radír / Lasszó / Varázsceruza / Méret** live in a bar **above** the preview frame (chrome), not floating over video pixels.
- Painting still happens on the image; mask canvas is letterbox-aligned to the displayed `<img>`.

### Drop hint

- „Ejtés: klip a timeline-ra” **never** covers a loaded timeline (only empty hero drop).

### Freeze / ORT

- Seed stroke commits are **debounced**; quiet path does not set global `busy` / block React on sync ORT.
- Pointer capture released on up/cancel (no stuck page).
- **RVM recurrent reset** when `H×W` or downsample ratio changes (`Expand_*` 26×45 vs 51×90). Full-res `src` + `downsample_ratio` (RVM-native).

### Varázsceruza

- Flood-fill smart select on click (tolerance slider); capped so it cannot paint the whole face as one blob.
- Lasso closes path and fills the region.

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

- **Kézi finomítás on Előnézet**: Ecset / Radír / Lasszó / Varázsceruza (+ Méret) in chrome **above** Cutout / Maszk / Forrás — paint on the image; stroke auto-commits seed + live cutout.
- **Nagy seed panel** optional (collapsed by default) — no duplicate paint stage required.
- **Összehasonlítás**: drag the vertical wipe line on the image; separate wipe slider chrome removed.

## Person matte (this stamp)

- **Max without MatAnyone2 weights** → RVM quality pipeline person alpha (never empty fake MatAnyone2)
- Status: **„MatAnyone2 nincs — RVM ember-maszk”** vs **„MatAnyone2 aktív”**
- **Előnézet** / upload: auto RVM → switch to **Cutout** when matte ready (toast)
- Manual lasso = **optional refinement** (union with auto) — not required for person removal
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
- `start_hybrid_cuda.ps1`: CapCut `remount_ort_gpu.ps1` if sibling; pip cudnn/ort-gpu; then launch
- Workaround B: `$env:HYBRID_REUSE_PARENT_VENV='1'` (CapCut `.venv` that already works)

---

## Pip / venv notes (Windows)

- `run_hybrid.ps1` does **not** run `pip install --upgrade pip` by default. Opt-in: `$env:HYBRID_UPGRADE_PIP = "1"`.
- Deps install with `--trusted-host pypi.org --trusted-host files.pythonhosted.org` and `--no-cache-dir`.
- Force parent venv (Workaround B): `$env:HYBRID_REUSE_PARENT_VENV = "1"`.
- GPU ORT / cuDNN:

```powershell
cd $env:USERPROFILE\Documents\Videoeditor
$env:HYBRID_RVM_ONNX = "$PWD\models\rvm_mobilenetv3_fp32.onnx"
.\hybrid_cut\start_hybrid_cuda.ps1
# auto: remount if sibling + nvidia-cudnn-cu12 + PATH
# or: .\run_hybrid.ps1  (also auto-installs cudnn when DLL missing)
```

Restart cheat-sheet: [`../hybrid-cudnn-restart.md`](../hybrid-cudnn-restart.md). Hotfix paste: `PASTE_FIX_RUN_HYBRID.ps1`.

---

## Tests

```powershell
cd $env:USERPROFILE\Documents\Videoeditor\hybrid_cut
$env:PYTHONPATH = "$PWD\backend"
& .\.venv\Scripts\python.exe -m pytest backend\tests -q
```
