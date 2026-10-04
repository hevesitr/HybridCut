# HybridCut

Modern hybrid cutout editor for **Róbert Hevesi-Tóth**: Concat-inspired host/timeline/prefetch/MaskStore ideas + MatAnyone2-class quality pipeline, without vendoring those codebases.

| | |
|--|--|
| SYNC | `2026-10-04-hybrid-phase4-audio` (see `SYNC_VERSION.txt`) |
| Install target | `%USERPROFILE%\Documents\Videoeditor\hybrid_cut` |
| CapCut root | `%USERPROFILE%\Documents\Videoeditor` + root `run_hybrid.ps1` |
| Stack | **Python FastAPI** engines + **Vite/React** UI (built `frontend/dist`) |
| Modes | **Gyors** (ORT RVM scrub) · **Max** (seed + quality bake / MatAnyone2 adapter) |
| Target | Windows + NVIDIA RTX 3060 8GB · local / free only (Ollama `llama3`) |

---

## Magyar / Hungarian — telepítés

```powershell
cd $env:USERPROFILE\Documents
git clone https://github.com/hevesitr/HybridCut.git
cd HybridCut
.\install_to_videoeditor.ps1
cd $env:USERPROFILE\Documents\Videoeditor
Get-Content .\hybrid_cut\SYNC_VERSION.txt
# elvart: 2026-10-04-hybrid-phase4-audio
.\run_hybrid.ps1
# nyisd: http://127.0.0.1:3847
```

Vagy futtasd a klonbol: `cd $env:USERPROFILE\Documents\HybridCut` majd `.\run_hybrid.ps1`.

**Elokovetelmenyek:** Python 3.12 (`py -3.12` vagy `python`), FFmpeg a PATH-on. Opcionalis GPU: `pip install onnxruntime-gpu` + `.\scripts\download_rvm.ps1`.

---

## English — install

```powershell
cd $env:USERPROFILE\Documents
git clone https://github.com/hevesitr/HybridCut.git
cd HybridCut
.\install_to_videoeditor.ps1
cd $env:USERPROFILE\Documents\Videoeditor
Get-Content .\hybrid_cut\SYNC_VERSION.txt
# expect: 2026-10-04-hybrid-phase4-audio
.\run_hybrid.ps1
# open http://127.0.0.1:3847
```

Or run from the clone: `cd $env:USERPROFILE\Documents\HybridCut` then `.\run_hybrid.ps1`.

**Prerequisites:** Python 3.12 on PATH (`py -3.12` or `python`), FFmpeg on PATH. Optional GPU: `pip install onnxruntime-gpu` + `.\scripts\download_rvm.ps1`.

`install_to_videoeditor.ps1` copies this tree into `Documents\Videoeditor\hybrid_cut` (skips `.git`, `.venv`, `node_modules`, `__pycache__`, weights) and writes the CapCut-root `run_hybrid.ps1`.

---

## License blockers (read first)

| Piece | License | Policy |
|-------|---------|--------|
| **MatAnyone2** weights / upstream | **S-Lab 1.0 — non-commercial** | Adapter only. Set `HYBRID_MATANYONE2_WEIGHTS`. **We do not redistribute weights.** |
| **Concat** | AGPL-3.0 | Ideas only — **no Concat source** |
| **RVM ONNX** | Upstream-dependent | Opt-in: `scripts/download_rvm.ps1` or `HYBRID_RVM_ONNX` |
| Our hybrid code | MIT (this tree) | See NOTICE |

Without RVM ONNX, **Gyors** uses a documented OpenCV GrabCut/center **heuristic fallback** (demo/CI — not ML quality).

---

## Shipped (Phase 4)

- Bake / preview MP4 with **source audio AAC** (FFmpeg)
- Max **seed paint** persists across scrub + reload (disk + overlay bind)
- **V1 + V2 B-roll** FramePlan stub + dual-lane timeline
- Proxy HOT/WARM enlarge; smarter status chips (Gyors/Max/seed/B-roll/audio)
- Ollama assist stub → `http://127.0.0.1:11434` / `llama3`

---

## Tests

```powershell
cd $env:USERPROFILE\Documents\Videoeditor\hybrid_cut
.\.venv\Scripts\Activate.ps1
$env:PYTHONPATH = "$PWD\backend"
pytest backend\tests -q
```
