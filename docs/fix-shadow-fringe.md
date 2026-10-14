# HybridCut fix-shadow-fringe

Stamp: **`2026-10-14-fix-shadow-fringe-fast2`**  
Combined branch: `cursor/fix-shadow-fringe-fast2-2eca`  
Base: `cursor/restore-rvm-fast2-b680` @ `231778d` (honest Max CPU ETA) + fringe residue fix  
Scope: **BG residue strips/blotches on cutout** + fast2 ETA honesty. Soft hair kept. **Both people kept.**

**Cloud Agent cannot prove Windows GPU.** Local validation required. Do **not** claim “javítva” without local proof.

---

## User visual (acceptance target)

| Observation | Implication |
|-------------|-------------|
| Blonde **right hair edge**: light greenish-grey BG strip | Mid-α leftovers whose RGB ≈ plate BG |
| Brunette **face side**: larger irregular light BG blotch | Same — not total matte failure |
| Rest of frame = checkerboard | Far BG α ≈ 0 already works |
| Two people | Never keep-largest-blob only |

---

## Protocol (followed — no random crush)

1. **Dump same frame:** `orig RGB`, `raw RVM α`, `final α`, `FG RGB used`, composites on **white / black / magenta** (+ residue mask).  
2. **ROI inspect:** mid-α pixels with RGB ≈ estimated BG → `residue_mean_alpha` / `raw_alpha_too_high_in_bg`.  
3. **If raw bad:** (I/O / ds / resize) — not required for this synthetic; soft RVM fog is expected mid-α on plate color.  
4. **If raw good / final bad:** ablate post — Gyors had almost no post; residue present in **raw**.  
5. **If α good / composite bad:** FG RGB spill — also real on soft hair (source RGB still has BG under soft α).  
6. **No global aggressive thresh/erosion**; soft hair; both people.  
7. Acceptance: both people, BG strips reduced, no hard hair cut, no new flicker, preview+export.

### Proven birth site (code + synthetic)

| Layer | Evidence |
|-------|----------|
| Raw α in BG-colored ROIs | **Too high** (`birth_site_hint=raw_alpha_bg_residue`) — soft mid-α fog on plate color |
| Soft hair band | Source RGB still holds BG → greenish strip on checker even with “valid” soft α |
| Premul double-multiply | **Not** primary (checker elsewhere clean; residue is light plate color, not black rim) |
| Keep-largest | Forbidden — multi-person cores via `_person_instance_ids` |

Synthetic unit: `backend/tests/test_shadow_fringe.py` (two people + strip + blotch).

---

## Minimal fix

1. **`suppress_bg_color_residue`** — damp only mid-α pixels matching plate BG, outside multi-person hair halo. Soft non-BG hair near cores kept. Opt-out: `HYBRID_SOFT_BG_RESIDUE=0`.  
2. **`cutout_rgb_for_alpha`** — RVM `fgr` on soft edges + light decontam/despill (straight α, no double-multiply).  
3. Gyors preview/bake + Max CPU-fast use repaired FG RGB for checker / BGRA.  
4. Diag: `HYBRID_DIAG_SHADOW=1` → `shadow_fringe/<tag>/` dumps + `metrics.json`.

Bake speed: no extra ORT pass — one color-aware α damp + RGB blend per frame (vs restore-rvm-fast). Soft α / Gyors~640 unchanged.

---

## Diagnostics (Windows)

```powershell
cd $env:USERPROFILE\Documents\HybridCut
git fetch origin
git checkout cursor/fix-shadow-fringe-2eca
git pull origin cursor/fix-shadow-fringe-2eca
Get-Content .\SYNC_VERSION.txt   # 2026-10-14-fix-shadow-fringe

$env:HYBRID_DIAG_SHADOW = '1'
$env:HYBRID_DIAG_DIR = "$env:USERPROFILE\Documents\HybridCut_diag"
.\install_to_videoeditor.ps1
cd $env:USERPROFILE\Documents\Videoeditor
.\hybrid_cut\start_hybrid_cuda.ps1
# Scrub to the bad two-person frame — Ctrl+F5
# Or: python scripts\diag_shadow_frame.py --media PATH\to\clip.mp4 --t 1.0
# Dumps: ...\shadow_fringe\<tag>\  (magenta composites + 14_bg_residue_mask.png + metrics.json)
```

| `birth_site_hint` | Meaning |
|-------------------|--------|
| `raw_alpha_bg_residue` | mid-α already high on BG-colored pixels (this fix’s primary target) |
| `post_alpha_grew_residue` | post feather/blur/dilate/temporal grew the blotch |
| `fg_rgb_source_spill` | soft α OK; source RGB still has BG (fgr/decontam) |
| `premul_double_multiply` | used RGB worse + premul score high |

Paste: `PASTE_FIX_SHADOW_FRINGE_GITHUB.ps1` / `PASTE_FIX_SHADOW_FRINGE_INSTALL.ps1`

---

## Local validate

1. Cutout: both people present; hair-edge greenish strip + face-side blotch reduced.  
2. Soft hair not hard-cut; no new flicker on scrub.  
3. `*_full_nobg.mov` on white/magenta in Premiere/Resolve — same.  
4. Optional diag on the problem frame; Gyors bake time not badly worse than restore-rvm-fast.
