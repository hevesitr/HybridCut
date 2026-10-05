# HybridCut restart — bgcut MOV primary

Feature stamp: **`2026-10-05-bgcut-mov`**. Final shipped SYNC: **`2026-10-05-paint-fix`** (includes this + `2026-10-05-rvm-state` + paint toolbar/Varázsceruza).

## After pull / sync

```powershell
cd $env:USERPROFILE\Documents\HybridCut
git pull
Get-Content .\SYNC_VERSION.txt   # 2026-10-05-paint-fix
.\install_to_videoeditor.ps1
cd $env:USERPROFILE\Documents\Videoeditor
$env:HYBRID_RVM_ONNX = "$PWD\models\rvm_resnet50_fp32.onnx"
.\hybrid_cut\start_hybrid_cuda.ps1
# http://127.0.0.1:3847
```

## Export check (primary = MOV)

1. Load a clip — In `0` / Out full duration.
2. **Exportálás hanggal**.
3. Status must show the full path: `C:\bgcut\{stem}_full_nobg.mov`.
4. **Megnyitás Explorerben (.mov)** selects that file (not `alpha\`).
5. Files under **`C:\bgcut\`**:
   - `{stem}_full_nobg.mov` — **primary** (ProRes → qtrle → png alpha)
   - `{stem}_full_nobg_preview.mp4` — optional checker/composite + audio
6. `C:\bgcut\alpha\` PNG dumps are **off by default**. Debug only: `$env:HYBRID_BGCUT_DUMP_ALPHA = "1"`.
7. Optional override: `$env:HYBRID_BGCUT_DIR = "D:\exports"`.
8. If MOV missing: set `$env:FFMPEG_PATH = "C:\ffmpeg\bin\ffmpeg.exe"` (HybridCut now resolves common installs, not PATH-only).

## Root cause fixed

Bake always wrote `alpha/*.png` first and used `shutil.which("ffmpeg")` only for MOV mux. On Windows GUI launches ffmpeg often isn't on PATH → mux silently skipped → Explorer showed only the alpha folder.
