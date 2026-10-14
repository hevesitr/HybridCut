# matte-safe restart

Stamp: `2026-10-14-restore-rvm-fast`

## Root cause

preview-fast crush used an adaptive hard core. Soft MobileNet often has a bright vertical ridge; crush treated that ridge as the only person and zeroed the soft body - jagged strip on checkerboard (TELE HIBAVAL).

## Fix

- Soft-body protect (a>0.14) instead of hard-ridge core
- Reject sliver mattes (`is_matte_sliver`); restore pre-crush silhouette
- Keep person pixels over aggressive rim kill

## Install (GitHub)

```powershell
cd $env:USERPROFILE\Documents\HybridCut
git pull origin main
Get-Content .\SYNC_VERSION.txt
# expect: 2026-10-14-restore-rvm-fast
.\install_to_videoeditor.ps1
cd $env:USERPROFILE\Documents\Videoeditor\hybrid_cut
.\run_hybrid.ps1
```
