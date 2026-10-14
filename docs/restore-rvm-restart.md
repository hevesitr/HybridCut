# restore-rvm restart

Stamp: `2026-10-14-restore-rvm-fast2`

Gyors Elonezet now follows the open-source simple path (PeterL1n RobustVideoMatting + rembg defaults): one RVM ONNX infer, soft `pha`, encode. Aggressive crush / good_enough / boost ladders that wiped soft MobileNet into gray-slab or strip are gated off preview.

## PowerShell install (GitHub)

```powershell
# ASCII paste: PASTE_RESTORE_RVM_GITHUB.ps1
cd $env:USERPROFILE\Documents
git clone https://github.com/hevesitr/HybridCut.git
cd HybridCut
git pull origin main
Get-Content .\SYNC_VERSION.txt
# expect: 2026-10-14-restore-rvm-fast2
.\install_to_videoeditor.ps1
cd $env:USERPROFILE\Documents\Videoeditor\hybrid_cut
.\start_hybrid_cuda.ps1
# open http://127.0.0.1:3847 then Ctrl+F5
```

Or one-shot:

```powershell
# paste contents of PASTE_RESTORE_RVM_GITHUB.ps1 into PowerShell
```

## What to expect

- Gyors Cutout shows a soft person silhouette quickly on CPU
- No "nincs elokep" gray-slab from crush wiping soft mattes
- Max bake may still polish; preview does not crush
