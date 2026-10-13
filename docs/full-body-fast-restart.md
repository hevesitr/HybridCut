# full-body-fast restart

Stamp: `2026-10-13-preview-fast`

## What changed

- **Hole-fill:** `fill_person_holes` on polish + CPU Max crush — crown/head gaps stay opaque.
- **CPU Max ~45s:** MobileNet@~720 in-RAM bake when `HYBRID_ORT_PROVIDER=cpu` (or live CPU ORT). No guided upsample / PNG stream. Status tag: `CPU Max~720`.
- **Hard-ish nobg:** `_crush_soft_shadow_alpha` zeros ghosts/far BG, kills soft rim outside solid core, `harden_foggy_halo` collapses milky mid-band. `CPU_MAX_SPEC` tighter residual + stronger decontaminate/despill.
- **Honest ETA:** remaining chip blends observed wall-clock spf after ~8 frames so a slow path cannot keep showing ~44s.

## Install (Windows)

```powershell
# Prefer Agent Store PASTE (no PAT):
# paste PASTE_FULL_BODY_FAST_INSTALL.ps1 into PowerShell

Get-Content "$env:USERPROFILE\Documents\Videoeditor\hybrid_cut\SYNC_VERSION.txt"
# expect: 2026-10-13-preview-fast
```

Dist tip: `index-D_S52bYl.js`.

## Verify

1. Előnézet — full person silhouette, no crown checkerboard holes.
2. Max Export on CPU ORT — status shows `CPU Max~720`, ~45s for ~10s 1080p24 (not ~10 min).
3. nobg.mov — clean hard-ish edges, no grey/green shoulder halo or ghost duplicate.

## No Agent Store

Use `PASTE_FULL_BODY_FAST_GITHUB.ps1` or:

```powershell
cd $env:USERPROFILE\Documents\HybridCut
git pull origin main
Get-Content .\SYNC_VERSION.txt
.\PASTE_FULL_BODY_FAST_INSTALL.ps1
```
