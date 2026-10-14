# diag_face_residue — face-front / under-chin BG fog

**Stamp required:** `2026-10-14-fix-shadow-fringe-fast2` (soft Gyors unchanged)  
**Feature:** `diag-face-auto-roi`  
**Branch:** `cursor/diag-face-auto-roi-6533` (on `cursor/diag-face-residue-5ffd` / fringe-fast2)

Prior fringe fix **failed acceptance** (user): close-up still shows **large grey-green** leftovers in front of face (nose-mouth) and under chin; checkerboard elsewhere; **both people** must remain.

Dump `20261014_204456` proved fixed center-right auto ROIs can report `alpha_clean_in_roi` while full-frame `residue_cover` is non-zero — **ROI miss**, not a crush tip. This pack **auto-selects** face/chin ROIs from person hard cores + BG-residue blobs (and lightly probes nearby times when residue is near-zero). **Do not** ask for Paint / `-RoiFace` as the primary path.

This package **does not** randomly tweak crush / threshold / erosion.  
**Cloud Agent did not run on your RTX 3060** — local GPU re-run required before any "javitva" claim.

---

## PowerShell one-liner

```powershell
cd $env:USERPROFILE\Documents\Videoeditor\hybrid_cut
Get-Content .\SYNC_VERSION.txt
# MUST be: 2026-10-14-fix-shadow-fringe-fast2

.\scripts\diag_face_residue.ps1 -Media "C:\29308762a.webm" -T 1.0
```

Optional ROI override (pixels, xyxy) only for lab experiments — **not required**:

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
| `SYNC_VERSION` | Must match `2026-10-14-fix-shadow-fringe-fast2` |
| `auto_roi` | Method + ranked person/residue candidates |
| `time_probe` | Nearby-t samples when global residue was weak |
| Cache purge | **Only** MaskStore + proxy/preview for **this clip** |

ROI JSON (`report.json` → `rois.face_front` / `under_chin`) plus top-level `auto_roi.method` / `candidates`.

---

## How to interpret (`path_hint`)

| Hint | Meaning |
|------|---------|
| `raw_or_suppress_miss` | Raw α already foggy in face ROI; suppress barely changed it |
| `post_grew` | Final worse than raw — unexpected on Gyors |
| `suppress_ok_alpha` | α cleaned but UI still grey-green → FG RGB spill or UI cache |
| `roi_miss_global_residue` | Full-frame mid-BG residue exists but selected face ROI still clean |
| `alpha_clean_in_roi` | Clean ROI and little/no global residue — wrong frame / UI / residual miss |
| `mixed` | Read PNGs + per-ROI `hypothesis_hint` |

**Forbidden:** global crush/erosion tippelés, keep-largest-person only, claiming "javitva" without local GPU acceptance.

---

## Code notes

- Production wire unchanged: soft Gyors `suppress_bg_color_residue`.
- Diag: `auto_face_rois` ranks center-right fallback, per-person upper boxes (extended above hard core), and residue-blob centroid windows.
