# HybridCut restart — full bake + bgcut MOV

Stamp: **`2026-10-05-bgcut-mov`** (supersedes `2026-10-05-full-bake-bgcut`; includes RVM state fix)

See also: [bgcut-mov-restart.md](./bgcut-mov-restart.md)

## After pull / sync

```powershell
cd $env:USERPROFILE\Documents\HybridCut
git pull
.\install_to_videoeditor.ps1
cd $env:USERPROFILE\Documents\Videoeditor
$env:HYBRID_RVM_ONNX = "$PWD\models\rvm_resnet50_fp32.onnx"
.\hybrid_cut\start_hybrid_cuda.ps1
# http://127.0.0.1:3847
```

## Export check

1. Load a ~10s clip — In `0` / Out `~10`.
2. **Exportálás hanggal**.
3. Progress must count toward **full frame count** (never stop at `/48`).
4. Primary file: **`C:\bgcut\{stem}_full_nobg.mov`** (not `alpha\`).
5. Companion: `{stem}_full_nobg_preview.mp4`.
6. Optional: `$env:HYBRID_BGCUT_DIR = "D:\exports"`.
