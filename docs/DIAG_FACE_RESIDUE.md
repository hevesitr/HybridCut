# diag_face_residue — face-front / under-chin BG fog

**Stamp required:** `2026-10-14-fix-shadow-fringe-fast2`  
**Branch:** `cursor/diag-face-residue-5ffd` (on top of `cursor/fix-shadow-fringe-fast2-2eca`)

Prior fringe fix **failed acceptance** (user): close-up still shows **large grey-green** leftovers in front of face (nose–mouth) and under chin; checkerboard elsewhere; **both people** must remain.

This package **does not** randomly tweak crush / threshold / erosion.  
**Cloud Agent did not run on your RTX 3060** — run this locally to prove which path fails.

---

## PowerShell one-liner

```powershell
cd $env:USERPROFILE\Documents\Videoeditor\hybrid_cut
Get-Content .\SYNC_VERSION.txt
# MUST be: 2026-10-14-fix-shadow-fringe-fast2  (else fringe-"fix failed" is not diagnosable)

.\scripts\diag_face_residue.ps1 -Media "D:\path\to\two_person_clip.mp4" -T 1.0
```

Optional ROI (pixels, xyxy) if auto center-right misses the blotch:

```powershell
.\scripts\diag_face_residue.ps1 -Media $clip -T 1.0 `
  -RoiFace "900,220,1180,420" -RoiChin "880,400,1200,560"
```

Output: `cache\diag_face_residue\<timestamp>\` → `report.json` + PNGs.

---

## What it prints / dumps

| Item | Meaning |
|------|---------|
| Absolute `install_root` | Running `Documents\Videoeditor\hybrid_cut` (or HybridCut) |
| `SYNC_VERSION` | Must match fringe-fast2 stamp above |
| `git_commit` | If checkout has `.git` |
| `python.exe` | Resolved venv interpreter |
| ORT providers | Available + session |
| Model path | RVM ONNX |
| Frontend `index-*.js` hash | Dist identity |
| Cache purge | **Only** MaskStore + proxy/preview cache for **this clip** — never original videos |

Per frame:

| File | Content |
|------|---------|
| `00_orig_rgb.png` | Original |
| `01_raw_rvm_alpha.png` | Raw RVM α (**no** `suppress_bg_color_residue`) |
| `02_final_alpha.png` | After HybridCut soft BG residue post |
| `03_fg_used_rgb.png` | FG RGB used for composite |
| `04/05_*_magenta/white` | Final FG×α composites |
| `06_comp_raw_on_magenta` | Raw α × source on magenta |
| `08_roi_overlay.png` | Auto / user face_front + under_chin boxes |
| `20_*` / `22_*` | Optional official-style RGB vs wrong-BGR side-by-side |

ROI JSON (`report.json` → `rois.face_front` / `under_chin`):

- `raw.mean_alpha` / `final.mean_alpha`
- Gate breakdown: `frac_hard_core`, `frac_in_hair_halo`, `mean_dist_to_bg`,
  `mid_bg_blocked_by_core_frac`, `mid_bg_blocked_by_halo_tight_thr_frac`,
  `mid_bg_eligible_frac`, `hypothesis_hint`

---

## How to interpret (`path_hint`)

| Hint | Meaning |
|------|---------|
| `raw_or_suppress_miss` | Raw α already foggy in face ROI; suppress barely changed it → **not** a UI-cache story; look at `hypothesis_hint` (core block / plate mismatch / weak near-core damp) |
| `post_grew` | Final worse than raw — unexpected on Gyors |
| `suppress_ok_alpha` | α cleaned but UI still grey-green → **FG RGB spill** or **stale UI** (re-run with purge; Ctrl+F5) |
| `alpha_clean_in_roi` | Wrong frame / ROI miss / UI cache |
| `mixed` | Read PNGs + per-ROI `hypothesis_hint` |

### Hypotheses (not declared proven without your dumps)

1. **Face fog classified as person core** — blotch α ≥ `hard_thresh` (0.55) → `core==0` fails → `suppress_bg_color_residue` never damps it.  
2. **Plate color mismatch inside hair_halo** — nose/chin sit inside wide hair halo → only `dist <= 0.72*color_thr` qualifies; greenish-grey near face may not match border-estimated BG.  
3. **Eligible but weak near-core damp** — residue matched but near-core damp keeps ~45%+ α.  
4. **Prior diag mislabeled post as raw** — fixed on this branch (`last_raw_pha`); do not trust older `shadow_fringe` dumps that set `post_alpha=None`.  
5. **UI / MaskStore** — this script purges mask+proxy for the clip; if UI still wrong after clean α dumps → frontend preview cache / wrong scrub time.

**Forbidden while reading dumps:** global aggressive crush, large erosion, keep-largest-person only, hiding warnings, proving with an easier video.

---

## Code notes (analysis only)

- Production wire: `FastEngine._matte` → `_soft_bg_residue` → `suppress_bg_color_residue`.  
- Instrumentation fix on this branch: stash `last_raw_pha` before residue; `_maybe_diag_shadow` now dumps raw **and** post.  
- No blind crush/threshold/erosion bump shipped as “the fix.”
