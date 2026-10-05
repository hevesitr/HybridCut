# HybridCut restart — full bake + bgcut

Stamp: **`2026-10-05-full-bake-bgcut`**

## After pull / sync

```powershell
cd $env:USERPROFILE\Documents\Videoeditor
$env:HYBRID_RVM_ONNX = "$PWD\models\rvm_resnet50_fp32.onnx"   # or mobilenet
.\hybrid_cut\start_hybrid_cuda.ps1
# http://127.0.0.1:3847
```

## Export check

1. Load a ~10s clip — In `0` / Out `~10`.
2. **Exportálás hanggal**.
3. Progress must count toward **full frame count** (e.g. `Max bake 120/240`), never stop at `/48`.
4. Files under **`C:\bgcut\`**:
   - `{stem}_full_nobg.mov` (alpha)
   - `{stem}_full_nobg_preview.mp4` (H.264 companion)
5. Optional override: `$env:HYBRID_BGCUT_DIR = "D:\exports"`.

## If still short

Confirm UI build is new (`SYNC_VERSION.txt` = `2026-10-05-full-bake-bgcut`) and hard-refresh the browser (cached `index-*.js` may still send `max_frames: 48`).
