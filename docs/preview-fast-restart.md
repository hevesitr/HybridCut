# preview-fast restart

Stamp: `2026-10-13-matte-safe`

## Root cause

CPU MobileNet soft mattes often peak ~0.25-0.35. `_crush_soft_shadow_alpha` required hard>=0.36, found no core, zeroed the whole frame → empty Előnézet + "Hibás maszk (egyenletes szürke lap)" toast.

## Fix

- Adaptive crush core + never-return-empty
- Gyors/Max preview force `hard_person_alpha` if still empty
- Proxy long default 480; CPU preview ≤720
- Prefer mid-cover salvage for 2-person indoor

## Install (GitHub — reliable)

```powershell
cd $env:USERPROFILE\Documents\HybridCut
git pull origin main
Get-Content .\SYNC_VERSION.txt
.\PASTE_PREVIEW_FAST_GITHUB.ps1
```
