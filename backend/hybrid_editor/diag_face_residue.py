"""Face-front / under-chin BG residue diagnostic (Windows RTX local).

Proves which path fails for grey-green leftovers in front of face / under chin
while checkerboard elsewhere and TWO people remain.

Does **not** tweak crush/threshold/erosion. Cloud Agent cannot run on the user's
RTX 3060 — this module is meant to be executed on the install machine.

Outputs under ``cache/diag_face_residue/<timestamp>/`` (or ``--out``):
report JSON + PNGs (orig RGB, raw RVM α, final α, FG used, magenta/white comps,
ROI overlays, optional official-style vs HybridCut side-by-side).
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import platform
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

import numpy as np

logger = logging.getLogger("hybrid_editor.diag_face_residue")

# Keep fringe-fast2 stamp: soft Gyors path unchanged; this ships diag auto-ROI only.
STAMP_REQUIRED = "2026-10-14-fix-shadow-fringe-fast2"
STAMP_LINEAGE_BASE = "2026-10-14-fix-shadow-fringe-fast2"
DIAG_FEATURE = "diag-face-auto-roi"


@dataclass
class InstallInfo:
    install_root: Path
    sync_version: str
    git_commit: Optional[str]
    python_exe: str
    ort_available: list[str]
    ort_session_providers: list[str]
    model_path: Optional[str]
    frontend_dist_hash: Optional[str]
    frontend_index_js: Optional[str]


def _as_hw_float(
    alpha: Optional[np.ndarray], shape: Optional[tuple[int, int]] = None
) -> Optional[np.ndarray]:
    if alpha is None:
        return None
    a = np.asarray(alpha)
    if a.ndim == 3:
        a = a[..., -1]
    a = a.astype(np.float32)
    if a.size and float(a.max()) > 1.5:
        a = a / 255.0
    a = np.clip(a, 0.0, 1.0)
    if shape is not None and a.shape[:2] != shape:
        import cv2

        a = cv2.resize(a, (shape[1], shape[0]), interpolation=cv2.INTER_LINEAR)
    return a


def _alpha_png(alpha: np.ndarray) -> np.ndarray:
    a = _as_hw_float(alpha)
    assert a is not None
    return (np.clip(a, 0.0, 1.0) * 255.0).astype(np.uint8)


def find_install_root(explicit: Optional[Path] = None) -> Path:
    """Resolve running HybridCut / hybrid_cut install root."""
    if explicit is not None:
        p = Path(explicit).expanduser().resolve()
        if (p / "backend" / "hybrid_editor").is_dir():
            return p
        raise FileNotFoundError(f"Not a HybridCut root: {p}")

    here = Path(__file__).resolve()
    # .../backend/hybrid_editor/diag_face_residue.py → parents[2] = repo/install root
    cand = here.parents[2]
    if (cand / "backend" / "hybrid_editor").is_dir():
        return cand

    home = Path.home()
    for p in (
        home / "Documents" / "Videoeditor" / "hybrid_cut",
        home / "Documents" / "videoeditor" / "hybrid_cut",
        home / "Documents" / "HybridCut",
        home / "Documents" / "hybridcut",
    ):
        if (p / "backend" / "hybrid_editor").is_dir():
            return p.resolve()
    raise FileNotFoundError(
        "Cannot find HybridCut install. Pass --install-root "
        r"(e.g. %USERPROFILE%\Documents\Videoeditor\hybrid_cut)"
    )


def read_sync_version(root: Path) -> str:
    for name in ("SYNC_VERSION.txt", "SYNC_VERSION"):
        f = root / name
        if f.is_file():
            return f.read_text(encoding="utf-8", errors="replace").strip()
    try:
        from hybrid_editor import SYNC_VERSION

        return str(SYNC_VERSION)
    except Exception:  # noqa: BLE001
        return ""


def git_commit_if_available(root: Path) -> Optional[str]:
    try:
        out = subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            cwd=str(root),
            stderr=subprocess.DEVNULL,
            text=True,
            timeout=5,
        )
        return out.strip() or None
    except Exception:  # noqa: BLE001
        return None


def frontend_dist_fingerprint(root: Path) -> tuple[Optional[str], Optional[str]]:
    assets = root / "frontend" / "dist" / "assets"
    if not assets.is_dir():
        return None, None
    matches = sorted(assets.glob("index-*.js"))
    if not matches:
        return None, None
    path = matches[0]
    h = hashlib.sha256(path.read_bytes()).hexdigest()[:16]
    return str(path.resolve()), h


def ort_provider_info(session: Any = None) -> tuple[list[str], list[str]]:
    available: list[str] = []
    active: list[str] = []
    try:
        import onnxruntime as ort

        available = list(ort.get_available_providers())
    except Exception as exc:  # noqa: BLE001
        available = [f"ORT_IMPORT_FAIL:{exc}"]
    if session is not None:
        try:
            active = list(session.get_providers())
        except Exception as exc:  # noqa: BLE001
            active = [f"SESSION_PROVIDERS_FAIL:{exc}"]
    return available, active


def collect_install_info(
    root: Path, *, session: Any = None, model_path: Optional[str] = None
) -> InstallInfo:
    idx, dist_hash = frontend_dist_fingerprint(root)
    avail, active = ort_provider_info(session)
    return InstallInfo(
        install_root=root.resolve(),
        sync_version=read_sync_version(root),
        git_commit=git_commit_if_available(root),
        python_exe=str(Path(sys.executable).resolve()),
        ort_available=avail,
        ort_session_providers=active,
        model_path=model_path,
        frontend_dist_hash=dist_hash,
        frontend_index_js=idx,
    )


def print_install_banner(info: InstallInfo) -> None:
    print("=== HybridCut diag_face_residue — install identity ===")
    print(f"install_root     : {info.install_root}")
    print(f"SYNC_VERSION     : {info.sync_version or '(missing)'}")
    print(f"git_commit       : {info.git_commit or '(not a git checkout)'}")
    print(f"python.exe       : {info.python_exe}")
    print(f"ORT available    : {info.ort_available}")
    print(f"ORT session      : {info.ort_session_providers or '(no session yet)'}")
    print(f"model_path       : {info.model_path or '(unknown)'}")
    print(f"frontend index.js: {info.frontend_index_js or '(no dist)'}")
    print(f"frontend hash    : {info.frontend_dist_hash or '(n/a)'}")
    print(f"platform         : {platform.platform()}")
    if info.sync_version != STAMP_REQUIRED:
        print(
            f"WARNING: stamp is {info.sync_version!r}, expected {STAMP_REQUIRED!r}. "
            "Prior fringe-fix acceptance claims are invalid until you install that stamp."
        )
    print("NOTE: Cloud Agent did NOT run this on your RTX 3060.")
    print("======================================================")


def purge_mask_preview_cache_for_media(root: Path, media_path: Path) -> dict[str, Any]:
    """Purge ONLY MaskStore + in-memory-style preview caches for this clip.

    Never deletes original videos.
    """
    from hybrid_editor.cache.mask_store import mask_dir, media_key

    report: dict[str, Any] = {
        "media": str(media_path.resolve()),
        "media_key": media_key(media_path),
        "purged": [],
        "skipped": [],
    }
    # Disk MaskStore for this media
    md = mask_dir(root, media_path, subject="person")
    if md.is_dir():
        shutil.rmtree(md, ignore_errors=True)
        report["purged"].append(str(md))
    else:
        report["skipped"].append(f"mask_dir_missing:{md}")

    # Proxy lane cold cache for this stem (preview decode — not original video)
    stem = Path(media_path).stem
    proxy = root / "cache" / "proxy" / stem
    if proxy.is_dir():
        shutil.rmtree(proxy, ignore_errors=True)
        report["purged"].append(str(proxy))
    else:
        report["skipped"].append(f"proxy_missing:{proxy}")

    # Session-ish preview image dumps if present (never media originals)
    for extra in (
        root / "cache" / "preview" / stem,
        root / "cache" / "preview" / media_key(media_path),
    ):
        if extra.is_dir():
            shutil.rmtree(extra, ignore_errors=True)
            report["purged"].append(str(extra))

    return report


def default_face_rois(
    h: int, w: int
) -> dict[str, tuple[int, int, int, int]]:
    """Legacy static center-right ROIs (fallback only).

    Prefer ``auto_face_rois`` which uses person cores + residue blobs so a
    face-front blotch does not require --roi-face / --roi-chin.
    """
    # Center-right portrait bias (~55-78% x, mid face y)
    fx0 = int(w * 0.52)
    fx1 = int(w * 0.78)
    fy0 = int(h * 0.28)
    fy1 = int(h * 0.52)
    cx0 = int(w * 0.50)
    cx1 = int(w * 0.80)
    cy0 = int(h * 0.50)
    cy1 = int(h * 0.68)
    return {
        "face_front": (fx0, fy0, fx1, fy1),
        "under_chin": (cx0, cy0, cx1, cy1),
    }


def _clamp_xyxy(
    box: tuple[int, int, int, int], h: int, w: int
) -> tuple[int, int, int, int]:
    x0, y0, x1, y1 = box
    x0 = int(max(0, min(w - 1, x0)))
    y0 = int(max(0, min(h - 1, y0)))
    x1 = int(max(0, min(w, x1)))
    y1 = int(max(0, min(h, y1)))
    if x1 <= x0 + 2:
        x1 = min(w, x0 + 3)
    if y1 <= y0 + 2:
        y1 = min(h, y0 + 3)
    return x0, y0, x1, y1


def _pad_xyxy(
    box: tuple[int, int, int, int],
    h: int,
    w: int,
    *,
    pad_frac: float = 0.18,
    min_w: int = 96,
    min_h: int = 72,
) -> tuple[int, int, int, int]:
    x0, y0, x1, y1 = box
    bw, bh = max(1, x1 - x0), max(1, y1 - y0)
    px = max(4, int(bw * pad_frac))
    py = max(4, int(bh * pad_frac))
    need_w = max(0, min_w - bw)
    need_h = max(0, min_h - bh)
    px = max(px, need_w // 2 + 1)
    py = max(py, need_h // 2 + 1)
    return _clamp_xyxy((x0 - px, y0 - py, x1 + px, y1 + py), h, w)


def person_hard_bboxes(
    alpha: np.ndarray,
    *,
    hard_thresh: float = 0.55,
    min_area_frac: float = 0.004,
    relative_frac: float = 0.10,
) -> list[tuple[int, int, int, int]]:
    """Kept person instance bboxes (xyxy) from hard alpha cores, largest first."""
    import cv2

    from hybrid_editor.engines.videoeditor_polish import _person_instance_ids

    a = _as_hw_float(alpha)
    assert a is not None
    h, w = a.shape
    hard_t = float(np.clip(hard_thresh, 0.40, 0.85))
    hard = (a >= hard_t).astype(np.uint8) * 255
    if int(hard.max()) < 1:
        hard = (a >= max(0.35, hard_t - 0.12)).astype(np.uint8) * 255
    if int(hard.max()) < 1:
        return []
    n, labels, stats, _ = cv2.connectedComponentsWithStats(hard, connectivity=8)
    min_area = max(32, int(h * w * float(min_area_frac)))
    keep_ids = _person_instance_ids(
        labels, stats, n, min_area=min_area, relative_frac=relative_frac
    )
    boxes: list[tuple[int, int, int, int, int]] = []
    for i in keep_ids:
        x = int(stats[i, cv2.CC_STAT_LEFT])
        y = int(stats[i, cv2.CC_STAT_TOP])
        bw = int(stats[i, cv2.CC_STAT_WIDTH])
        bh = int(stats[i, cv2.CC_STAT_HEIGHT])
        area = int(stats[i, cv2.CC_STAT_AREA])
        boxes.append((area, x, y, x + bw, y + bh))
    boxes.sort(reverse=True)
    return [_clamp_xyxy((x0, y0, x1, y1), h, w) for _, x0, y0, x1, y1 in boxes]


def rois_from_person_bbox(
    person_xyxy: tuple[int, int, int, int], h: int, w: int
) -> dict[str, tuple[int, int, int, int]]:
    """Face-front / under-chin boxes from one person hard-core bbox.

    Extends above the hard-core top: face-front fog often sits just outside
    core (mid-alpha blotch) so a tight core crop misses it.
    """
    x0, y0, x1, y1 = person_xyxy
    bw, bh = max(1, x1 - x0), max(1, y1 - y0)
    # Reach above hard core for nose/mouth fog that is not a>=0.55
    y_face0 = y0 - int(bh * 0.22)
    face = _clamp_xyxy(
        (
            x0 + int(bw * 0.08),
            y_face0,
            x0 + int(bw * 0.92),
            y0 + int(bh * 0.42),
        ),
        h,
        w,
    )
    chin = _clamp_xyxy(
        (
            x0 + int(bw * 0.05),
            y0 + int(bh * 0.28),
            x0 + int(bw * 0.95),
            y0 + int(bh * 0.62),
        ),
        h,
        w,
    )
    return {"face_front": face, "under_chin": chin}


def _roi_signal_score(
    alpha: np.ndarray,
    src_bgr: np.ndarray,
    box: tuple[int, int, int, int],
    *,
    color_thr: float = 30.0,
) -> float:
    """Higher = more mid-alpha BG-like / residue signal inside the box.

    Deliberately ignores solid person alpha (mean α high) so person-core crops
    do not outrank an actual grey-green blotch.
    """
    from hybrid_editor.diag_shadow_fringe import estimate_bg_bgr

    a = _as_hw_float(alpha, src_bgr.shape[:2])
    assert a is not None
    h, w = a.shape
    x0, y0, x1, y1 = _clamp_xyxy(box, h, w)
    sl = a[y0:y1, x0:x1]
    if sl.size < 16:
        return 0.0
    bg = estimate_bg_bgr(src_bgr, a)
    dist = np.sqrt(
        ((src_bgr[y0:y1, x0:x1].astype(np.float32) - bg) ** 2).sum(axis=2)
    )
    mid = (sl > 0.10) & (sl < 0.90)
    bg_like = dist <= float(color_thr)
    mid_bg = mid & bg_like
    soft_res = (sl >= 0.12) & (sl <= 0.85) & bg_like
    # Exclude deep hard core from the reward (person interior)
    soft_res = soft_res & (sl < 0.55)
    mid_bg = mid_bg & (sl < 0.85)
    cover = float(soft_res.mean())
    mid_frac = float(mid_bg.mean())
    mean_mid = float(sl[mid_bg].mean()) if mid_bg.any() else 0.0
    mean_soft = float(sl[soft_res].mean()) if soft_res.any() else 0.0
    hard_frac = float((sl >= 0.55).mean())
    # Penalize boxes that are mostly solid person with little mid-BG fog.
    score = cover * (0.45 + mean_soft) + mid_frac * (0.35 + mean_mid)
    if hard_frac > 0.55 and cover < 0.04:
        score *= 0.35
    return float(score)


def residue_blob_boxes(
    src_bgr: np.ndarray,
    alpha: np.ndarray,
    *,
    min_area: int = 80,
    max_blobs: int = 8,
) -> list[tuple[int, int, int, int, float]]:
    """BG-residue components as tight face-sized windows around blob centroids."""
    import cv2

    from hybrid_editor.diag_shadow_fringe import bg_residue_mask

    mask, _stats = bg_residue_mask(
        src_bgr, alpha, color_thr=30.0, a_lo=0.10, a_hi=0.88
    )
    h, w = mask.shape
    u8 = (mask.astype(np.uint8) * 255)
    if int(u8.max()) < 1:
        return []
    n, labels, cc, _ = cv2.connectedComponentsWithStats(u8, connectivity=8)
    a = _as_hw_float(alpha, (h, w))
    assert a is not None
    frame_area = float(h * w)
    win = max(72, int(min(h, w) * 0.16))
    blobs: list[tuple[float, int, int, int, int]] = []
    for i in range(1, n):
        area = int(cc[i, cv2.CC_STAT_AREA])
        if area < int(min_area):
            continue
        # Whole-body soft-edge rings are huge; keep but down-weight later
        m = labels == i
        ys, xs = np.where(m)
        if xs.size < 8:
            continue
        cx = int(np.median(xs))
        cy = int(np.median(ys))
        # Density-weighted: prefer mid-alpha fog over faint edge dust
        mean_a = float(a[m].mean()) if m.any() else 0.0
        cover_frac = float(area) / frame_area
        score = float(area) * (0.25 + mean_a)
        if cover_frac > 0.08:
            score *= 0.25
        half = win // 2
        x0, y0 = cx - half, cy - int(half * 0.85)
        x1, y1 = cx + half, cy + int(half * 0.85)
        box = _pad_xyxy((x0, y0, x1, y1), h, w, pad_frac=0.06, min_w=win, min_h=int(win * 0.75))
        blobs.append((score, box[0], box[1], box[2], box[3]))
    blobs.sort(reverse=True)
    out: list[tuple[int, int, int, int, float]] = []
    for score, x0, y0, x1, y1 in blobs[: max(1, int(max_blobs))]:
        out.append((x0, y0, x1, y1, float(score)))
    return out


def _chin_below_face(
    face: tuple[int, int, int, int], h: int, w: int
) -> tuple[int, int, int, int]:
    x0, y0, x1, y1 = face
    fh = max(1, y1 - y0)
    fw = max(1, x1 - x0)
    cy0 = y1 - int(fh * 0.15)
    cy1 = y1 + int(fh * 0.75)
    cx0 = x0 - int(fw * 0.05)
    cx1 = x1 + int(fw * 0.05)
    return _clamp_xyxy((cx0, cy0, cx1, cy1), h, w)


def auto_face_rois(
    h: int,
    w: int,
    *,
    alpha: Optional[np.ndarray] = None,
    src_bgr: Optional[np.ndarray] = None,
) -> tuple[dict[str, tuple[int, int, int, int]], dict[str, Any]]:
    """Pick face_front / under_chin without manual ROI.

    Ranking (evidence from dump 20261014_204456): static center-right can miss
    the blotch while full-frame residue_cover > 0. Prefer residue blobs near
    person heads, then per-person upper-body boxes, then legacy default.
    """
    meta: dict[str, Any] = {
        "method": "default_center_right",
        "candidates": [],
        "person_bboxes": [],
        "residue_blobs": [],
    }
    legacy = default_face_rois(h, w)
    if alpha is None or src_bgr is None:
        return legacy, meta

    a = _as_hw_float(alpha, (h, w))
    assert a is not None
    persons = person_hard_bboxes(a)
    meta["person_bboxes"] = [list(p) for p in persons]
    blobs = residue_blob_boxes(src_bgr, a)
    meta["residue_blobs"] = [
        {"box_xyxy": [b[0], b[1], b[2], b[3]], "score": round(b[4], 2)} for b in blobs
    ]

    candidates: list[tuple[str, dict[str, tuple[int, int, int, int]]]] = [
        ("default_center_right", legacy)
    ]
    for i, pb in enumerate(persons[:4]):
        candidates.append((f"person_{i}", rois_from_person_bbox(pb, h, w)))
    for i, (x0, y0, x1, y1, _sc) in enumerate(blobs[:4]):
        face = _pad_xyxy((x0, y0, x1, y1), h, w)
        chin = _chin_below_face(face, h, w)
        # Prefer residue blobs that sit in the upper half of a person bbox
        near_head = False
        for pb in persons:
            px0, py0, px1, py1 = pb
            mid_x = 0.5 * (x0 + x1)
            mid_y = 0.5 * (y0 + y1)
            if px0 <= mid_x <= px1 and py0 <= mid_y <= (py0 + 0.55 * (py1 - py0)):
                near_head = True
                break
        tag = f"residue_blob_{i}" + ("_near_head" if near_head else "")
        candidates.append((tag, {"face_front": face, "under_chin": chin}))

    best_name = "default_center_right"
    best_rois = legacy
    best_score = -1.0
    ranked: list[dict[str, Any]] = []
    for name, rois in candidates:
        face_s = _roi_signal_score(a, src_bgr, rois["face_front"])
        chin_s = _roi_signal_score(a, src_bgr, rois["under_chin"])
        # Face blotch dominates; chin is secondary. Near-head residue gets a bump.
        bump = 1.15 if "near_head" in name else 1.0
        if name.startswith("residue_blob"):
            bump *= 1.10
        score = bump * (face_s * 1.35 + chin_s)
        ranked.append(
            {
                "name": name,
                "score": round(float(score), 5),
                "face_score": round(float(face_s), 5),
                "chin_score": round(float(chin_s), 5),
                "face_front": list(rois["face_front"]),
                "under_chin": list(rois["under_chin"]),
            }
        )
        if score > best_score:
            best_score = score
            best_name = name
            best_rois = rois
    ranked.sort(key=lambda r: r["score"], reverse=True)
    meta["method"] = best_name
    meta["candidates"] = ranked[:8]
    meta["best_score"] = round(float(best_score), 5)
    return best_rois, meta


def probe_peak_residue_times(
    media: Path,
    rvm: Any,
    *,
    downsample: float,
    t_hint: float,
    fps: float,
    duration_hint: Optional[float] = None,
) -> dict[str, Any]:
    """Light time probe when requested frame has little global residue.

    Samples a small set of times around ``t_hint`` (and early clip) using the
    same RVM downsample - no manual -T picking.
    """
    from hybrid_editor.diag_shadow_fringe import bg_residue_mask
    from hybrid_editor.media.video_io import read_frame_at

    times = [float(t_hint)]
    for dt in (-1.0, -0.5, 0.5, 1.0, 1.5, 2.0):
        times.append(max(0.0, float(t_hint) + dt))
    for t in (0.0, 0.5, 1.0, 1.5, 2.0, 2.5, 3.0):
        times.append(float(t))
    # Unique preserve order
    seen: set[float] = set()
    uniq: list[float] = []
    for t in times:
        key = round(t, 3)
        if key in seen:
            continue
        seen.add(key)
        uniq.append(float(t))
        if len(uniq) >= 10:
            break

    samples: list[dict[str, Any]] = []
    best_t = float(t_hint)
    best_cover = -1.0
    for t in uniq:
        try:
            bgr, t_read = read_frame_at(media, t)
            if bgr is None:
                continue
            rvm.reset()
            pha = rvm.matte(bgr, downsample=float(downsample), prefer_native=False)
            _mask, st = bg_residue_mask(bgr, pha)
            cover = float(st.get("residue_cover", 0.0))
            mean_a = float(st.get("residue_mean_alpha", 0.0))
            samples.append(
                {
                    "t_sec": round(float(t_read), 3),
                    "residue_cover": cover,
                    "residue_mean_alpha": mean_a,
                }
            )
            score = cover * (0.25 + mean_a)
            if score > best_cover:
                best_cover = score
                best_t = float(t_read)
        except Exception as exc:  # noqa: BLE001
            samples.append({"t_sec": round(float(t), 3), "error": str(exc)[:160]})
    return {
        "probed": True,
        "samples": samples,
        "best_t_sec": round(float(best_t), 3),
        "best_score": round(float(max(best_cover, 0.0)), 5),
        "fps": fps,
        "duration_hint": duration_hint,
    }


def parse_roi(s: str) -> tuple[int, int, int, int]:
    parts = [int(x.strip()) for x in s.replace(";", ",").split(",")]
    if len(parts) != 4:
        raise ValueError(f"ROI must be x0,y0,x1,y1 — got {s!r}")
    x0, y0, x1, y1 = parts
    if x1 <= x0 or y1 <= y0:
        raise ValueError(f"ROI empty: {s!r}")
    return x0, y0, x1, y1


def roi_stats(
    alpha: np.ndarray,
    src_bgr: np.ndarray,
    box: tuple[int, int, int, int],
    *,
    color_thr: float = 30.0,
    hard_thresh: float = 0.55,
    halo_px: int = 12,
) -> dict[str, Any]:
    """Mean α + suppress-gate breakdown for one ROI (why fog may survive)."""
    import cv2

    from hybrid_editor.diag_shadow_fringe import estimate_bg_bgr

    a = _as_hw_float(alpha, src_bgr.shape[:2])
    assert a is not None
    h, w = a.shape
    x0, y0, x1, y1 = box
    x0, y0 = max(0, x0), max(0, y0)
    x1, y1 = min(w, x1), min(h, y1)
    if x1 <= x0 or y1 <= y0:
        return {"error": "empty_roi", "box": list(box)}

    # Replicate suppress_bg_color_residue gates (read-only — no param tweak).
    hard_t = float(np.clip(hard_thresh, 0.40, 0.85))
    hard = (a >= hard_t).astype(np.uint8) * 255
    if int(hard.max()) < 1:
        hard = (a >= max(0.35, hard_t - 0.12)).astype(np.uint8) * 255
    core = np.zeros((h, w), dtype=np.uint8)
    if int(hard.max()) >= 1:
        n, labels, stats, _ = cv2.connectedComponentsWithStats(hard, connectivity=8)
        from hybrid_editor.engines.videoeditor_polish import _person_instance_ids

        min_area = max(32, int(h * w * 0.004))
        keep_ids = _person_instance_ids(
            labels, stats, n, min_area=min_area, relative_frac=0.10
        )
        for i in keep_ids:
            core = cv2.bitwise_or(core, (labels == i).astype(np.uint8) * 255)
    px = max(5, int(halo_px))
    if px % 2 == 0:
        px += 1
    k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (px, px))
    hair_halo = cv2.dilate(core, k, iterations=2) if int(core.max()) else core
    bg = estimate_bg_bgr(src_bgr, a)
    dist = np.sqrt(((src_bgr.astype(np.float32) - bg) ** 2).sum(axis=2))
    mid = (a > 0.10) & (a < 0.90)
    thr_in = float(color_thr) * 0.72
    thr_out = float(color_thr)
    in_halo = hair_halo > 0
    residue_eligible = mid & (
        ((in_halo) & (dist <= thr_in)) | ((~in_halo) & (dist <= thr_out))
    )
    residue_eligible = residue_eligible & (a < 0.92) & (core == 0)

    sl_a = a[y0:y1, x0:x1]
    sl_dist = dist[y0:y1, x0:x1]
    sl_core = core[y0:y1, x0:x1] > 0
    sl_halo = in_halo[y0:y1, x0:x1]
    sl_mid = mid[y0:y1, x0:x1]
    sl_res = residue_eligible[y0:y1, x0:x1]
    sl_bgr = src_bgr[y0:y1, x0:x1].astype(np.float32)
    bg_like = sl_dist <= thr_out
    # Gate failure taxonomy for mid-α BG-looking pixels in ROI
    mid_bg = sl_mid & bg_like
    blocked_by_core = mid_bg & sl_core
    blocked_by_halo_thr = mid_bg & (~sl_core) & sl_halo & (sl_dist > thr_in)
    eligible = mid_bg & sl_res

    return {
        "box_xyxy": [x0, y0, x1, y1],
        "mean_alpha": round(float(sl_a.mean()), 4),
        "median_alpha": round(float(np.median(sl_a)), 4),
        "frac_mid_alpha": round(float(sl_mid.mean()), 4),
        "frac_hard_core": round(float(sl_core.mean()), 4),
        "frac_in_hair_halo": round(float(sl_halo.mean()), 4),
        "mean_dist_to_bg": round(float(sl_dist.mean()), 2),
        "frac_bg_like_thr_out": round(float(bg_like.mean()), 4),
        "frac_residue_eligible": round(float(sl_res.mean()), 4),
        "mid_bg_frac": round(float(mid_bg.mean()), 4),
        "mid_bg_blocked_by_core_frac": round(float(blocked_by_core.mean()), 4),
        "mid_bg_blocked_by_halo_tight_thr_frac": round(
            float(blocked_by_halo_thr.mean()), 4
        ),
        "mid_bg_eligible_frac": round(float(eligible.mean()), 4),
        "roi_mean_bgr": [round(float(x), 1) for x in sl_bgr.reshape(-1, 3).mean(axis=0)],
        "estimated_bg_bgr": [round(float(x), 1) for x in bg.tolist()],
        "gates": {
            "color_thr": color_thr,
            "thr_in_halo": thr_in,
            "thr_out_halo": thr_out,
            "hard_thresh": hard_t,
            "halo_px": halo_px,
        },
        "hypothesis_hint": _roi_hypothesis(
            float(blocked_by_core.mean()),
            float(blocked_by_halo_thr.mean()),
            float(eligible.mean()),
            float(sl_a.mean()),
        ),
    }


def _roi_hypothesis(
    blocked_core: float, blocked_halo: float, eligible: float, mean_a: float
) -> str:
    if blocked_core >= 0.08:
        return (
            "face_fog_classified_as_person_core — mid/high α BG fog is inside "
            "hard core (a>=hard_thresh) so suppress_bg_color_residue skips it "
            "(residue requires core==0). Needs local confirm via dumps; do not "
            "blindly raise crush."
        )
    if blocked_halo >= 0.08:
        return (
            "plate_color_mismatch_inside_hair_halo — ROI is inside hair_halo so "
            "only dist<=thr_in (~0.72*color_thr) qualifies; greenish-grey near "
            "face may not match border-estimated BG plate."
        )
    if eligible >= 0.05 and mean_a >= 0.15:
        return (
            "eligible_but_weak_near_core_damp — pixels match residue mask but "
            "near-core damp keeps ~45%+ of α (strength*0.55). Visible fog can remain."
        )
    if mean_a >= 0.35:
        return (
            "high_roi_alpha — check raw vs final PNG; if raw already high, RVM "
            "soft fog; if only final high, post grew it (unexpected for Gyors)."
        )
    return (
        "low_mid_bg_signal_in_roi — auto ROI still weak here; check residue_blobs / "
        "person_bboxes in report.auto_roi and path_hint (may need nearby t probe)."
    )


def composite_over_solid(
    bgr: np.ndarray, alpha: np.ndarray, bg_bgr: tuple[int, int, int]
) -> np.ndarray:
    from hybrid_editor.diag_shadow_fringe import composite_over_solid as _c

    return _c(bgr, alpha, bg_bgr)


def draw_roi_overlay(
    bgr: np.ndarray, rois: dict[str, tuple[int, int, int, int]]
) -> np.ndarray:
    import cv2

    out = bgr.copy()
    colors = {"face_front": (0, 255, 255), "under_chin": (255, 128, 0)}
    for name, (x0, y0, x1, y1) in rois.items():
        c = colors.get(name, (0, 255, 0))
        cv2.rectangle(out, (x0, y0), (x1, y1), c, 2)
        cv2.putText(
            out, name, (x0, max(16, y0 - 6)), cv2.FONT_HERSHEY_SIMPLEX, 0.5, c, 1
        )
    return out


def official_style_rvm_matte(
    bgr: np.ndarray,
    session: Any,
    *,
    downsample_ratio: float,
    assume_rgb_input: bool,
    input_name: str = "src",
) -> np.ndarray:
    """Minimal PeterL1n-style preprocess/infer (no HybridCut post).

    Used only to side-by-side compare BGR/RGB + ds variants vs HybridCut path.
    """
    from hybrid_editor.media.video_io import normalize_alpha

    if assume_rgb_input:
        rgb_u8 = np.ascontiguousarray(bgr[:, :, ::-1])
    else:
        # Intentionally wrong (BGR as if RGB) — diagnostic contrast only
        rgb_u8 = np.ascontiguousarray(bgr)
    rgb = rgb_u8.astype(np.float32) * (1.0 / 255.0)
    h, w = int(rgb.shape[0]), int(rgb.shape[1])
    x = np.ascontiguousarray(np.transpose(rgb, (2, 0, 1))[None, ...], dtype=np.float32)
    inputs = {i.name: i for i in session.get_inputs()}
    feeds: dict[str, Any] = {}
    # src
    src_key = input_name if input_name in inputs else next(iter(inputs))
    feeds[src_key] = x
    # recurrent zeros
    for name in ("r1i", "r2i", "r3i", "r4i"):
        if name in inputs:
            shape = [d if isinstance(d, int) and d > 0 else 1 for d in inputs[name].shape]
            # RVM rec often [1,C,H,W] dynamic — use small zeros; HybridCut uses cold_recurrent
            try:
                from hybrid_editor.engines.fast_rvm import cold_recurrent

                feeds[name] = cold_recurrent(np.float32)
            except Exception:  # noqa: BLE001
                feeds[name] = np.zeros(shape, dtype=np.float32)
    if "downsample_ratio" in inputs:
        feeds["downsample_ratio"] = np.array(
            [float(downsample_ratio)], dtype=np.float32
        )
    outs = session.run(None, feeds)
    # pha usually first or named
    pha = outs[0]
    for i, meta in enumerate(session.get_outputs()):
        n = str(getattr(meta, "name", "") or "").lower()
        if "pha" in n or n == "alpha":
            pha = outs[i]
            break
    a = np.asarray(pha)
    if a.ndim == 4:
        a = a[0, 0]
    elif a.ndim == 3:
        a = a[0] if a.shape[0] <= 4 else a[..., 0]
    a = normalize_alpha(a)
    if a.shape[:2] != (h, w):
        import cv2

        a = cv2.resize(a, (w, h), interpolation=cv2.INTER_LINEAR)
    return a.astype(np.float32)


def run_diag(
    *,
    media: Path,
    t_sec: Optional[float] = None,
    frame_index: Optional[int] = None,
    install_root: Optional[Path] = None,
    out_dir: Optional[Path] = None,
    roi_face: Optional[str] = None,
    roi_chin: Optional[str] = None,
    compare_official: bool = True,
    purge_cache: bool = True,
    mode: str = "gyors",
) -> Path:
    import cv2

    root = find_install_root(install_root)
    backend = root / "backend"
    if str(backend) not in sys.path:
        sys.path.insert(0, str(backend))

    media = Path(media).expanduser().resolve()
    if not media.is_file():
        raise FileNotFoundError(media)

    stamp = time.strftime("%Y%m%d_%H%M%S")
    if out_dir is None:
        out = root / "cache" / "diag_face_residue" / stamp
    else:
        out = Path(out_dir).expanduser().resolve() / stamp
    out.mkdir(parents=True, exist_ok=True)

    purge_report: dict[str, Any] = {"skipped": True}
    if purge_cache:
        purge_report = purge_mask_preview_cache_for_media(root, media)
        print(f"Purged mask/preview cache (not videos): {purge_report['purged']}")

    from hybrid_editor.engines.fast_rvm import FastEngine
    from hybrid_editor.engines.max_quality import MaxQualityEngine
    from hybrid_editor.engines.videoeditor_polish import suppress_bg_color_residue
    from hybrid_editor.media.video_io import read_frame_at

    eng: Any
    if mode == "max":
        eng = MaxQualityEngine()
    else:
        eng = FastEngine(prefer_quality=False)

    report: dict[str, Any] = {
        "stamp_required": STAMP_REQUIRED,
        "cloud_agent_ran_on_user_3060": False,
        "media": str(media),
        "t_sec": t_sec,
        "frame_index": frame_index,
        "mode": mode,
        "purge": purge_report,
        "out_dir": str(out),
    }

    try:
        info_media = eng.open_media(media)
        fps = float(getattr(info_media, "fps", None) or 25.0)
        if frame_index is not None:
            t_use = float(frame_index) / max(fps, 1e-6)
        else:
            t_use = float(t_sec or 0.0)
        report["t_sec_resolved"] = t_use
        report["fps"] = fps

        bgr, t_read = read_frame_at(media, t_use)
        if bgr is None:
            raise RuntimeError(f"failed to decode frame at t={t_use}")
        report["t_sec_read"] = float(t_read)
        h, w = int(bgr.shape[0]), int(bgr.shape[1])

        # Prefer Gyors FastEngine path for raw vs post separation
        fast = getattr(eng, "_fast", None) or eng
        rvm = getattr(fast, "_rvm", None)
        model_path = str(getattr(rvm, "model_path", None) or "") or None
        session = getattr(rvm, "session", None)
        info = collect_install_info(root, session=session, model_path=model_path)
        report["install"] = {
            "install_root": str(info.install_root),
            "sync_version": info.sync_version,
            "git_commit": info.git_commit,
            "python_exe": info.python_exe,
            "ort_available": info.ort_available,
            "ort_session_providers": info.ort_session_providers,
            "model_path": info.model_path,
            "frontend_dist_hash": info.frontend_dist_hash,
            "frontend_index_js": info.frontend_index_js,
        }
        print_install_banner(info)

        # --- True raw RVM (no post) vs HybridCut final ---
        raw_alpha: Optional[np.ndarray] = None
        final_alpha: Optional[np.ndarray] = None
        fgr = None
        ds = 0.25
        if rvm is not None and hasattr(fast, "_downsample_for"):
            rvm.reset()
            ds = float(fast._downsample_for(bgr))  # noqa: SLF001
            raw_alpha = rvm.matte(bgr, downsample=ds, prefer_native=False)
            fgr = getattr(rvm, "last_fgr_bgr", None)
            report["downsample_used"] = ds
        else:
            # Fallback: engine matte only (cannot split raw)
            final_alpha = fast._matte(bgr)  # noqa: SLF001
            raw_alpha = getattr(fast, "last_raw_pha", None) or final_alpha
            report["warning"] = "rvm_unavailable_raw_may_equal_final"

        # Auto time probe when global residue is weak and user did not lock --frame
        time_probe: dict[str, Any] = {"probed": False}
        if (
            frame_index is None
            and rvm is not None
            and raw_alpha is not None
            and roi_face is None
            and roi_chin is None
        ):
            from hybrid_editor.diag_shadow_fringe import bg_residue_mask as _bgm

            _m0, st0 = _bgm(bgr, raw_alpha)
            cover0 = float(st0.get("residue_cover", 0.0) or 0.0)
            if cover0 < 0.0015:
                print(
                    f"Global residue_cover={cover0:.4f} at t={t_use:.3f} "
                    "- probing nearby times for peak residue (no manual -T)."
                )
                time_probe = probe_peak_residue_times(
                    media, rvm, downsample=ds, t_hint=t_use, fps=fps
                )
                best_t = float(time_probe.get("best_t_sec", t_use))
                if abs(best_t - float(t_use)) > 0.05:
                    bgr2, t_read2 = read_frame_at(media, best_t)
                    if bgr2 is not None:
                        bgr = bgr2
                        h, w = int(bgr.shape[0]), int(bgr.shape[1])
                        t_use = float(t_read2)
                        report["t_sec_resolved"] = t_use
                        report["t_sec_read"] = float(t_read2)
                        report["t_sec_auto_adjusted_from"] = float(t_sec or 0.0)
                        rvm.reset()
                        raw_alpha = rvm.matte(
                            bgr, downsample=ds, prefer_native=False
                        )
                        fgr = getattr(rvm, "last_fgr_bgr", None)
                        print(f"Auto-selected t={t_use:.3f} for higher residue signal")
        report["time_probe"] = time_probe

        if rvm is not None and raw_alpha is not None and final_alpha is None:
            # HybridCut post only (same function as production) - soft Gyors path
            final_alpha = suppress_bg_color_residue(
                raw_alpha,
                bgr,
                color_thr=30.0,
                strength=0.82,
                hard_thresh=0.55,
                halo_px=12,
                min_area_frac=0.004,
                relative_frac=0.10,
            )
            # Also run engine _matte for parity (should match final if soft residue on)
            try:
                engine_final = fast._matte(bgr)  # noqa: SLF001
                report["engine_matte_vs_manual_post_mae"] = round(
                    float(
                        np.mean(
                            np.abs(
                                engine_final.astype(np.float32)
                                - np.asarray(final_alpha, dtype=np.float32)
                            )
                        )
                    ),
                    5,
                )
            except Exception as exc:  # noqa: BLE001
                report["engine_matte_error"] = str(exc)[:200]

        from hybrid_editor.engines.peak_cutout import cutout_rgb_for_alpha

        fg_used = cutout_rgb_for_alpha(bgr, final_alpha, fgr, mix=0.82)

        auto_meta: dict[str, Any] = {"method": "manual_override"}
        if roi_face or roi_chin:
            rois = default_face_rois(h, w)
            if roi_face:
                rois["face_front"] = parse_roi(roi_face)
            if roi_chin:
                rois["under_chin"] = parse_roi(roi_chin)
            auto_meta = {
                "method": "manual_override",
                "note": "explicit --roi-face/--roi-chin; auto ranking skipped",
            }
        else:
            rois, auto_meta = auto_face_rois(h, w, alpha=raw_alpha, src_bgr=bgr)
        report["auto_roi"] = auto_meta
        print(
            f"auto_roi method={auto_meta.get('method')} "
            f"score={auto_meta.get('best_score', 'n/a')}"
        )

        report["rois"] = {}
        for name, box in rois.items():
            report["rois"][name] = {
                "raw": roi_stats(raw_alpha, bgr, box),
                "final": roi_stats(final_alpha, bgr, box),
            }
            ra = report["rois"][name]["raw"]["mean_alpha"]
            fa = report["rois"][name]["final"]["mean_alpha"]
            print(
                f"ROI {name}: raw_mean_α={ra:.4f}  final_mean_α={fa:.4f}  "
                f"hint={report['rois'][name]['final'].get('hypothesis_hint', '')[:80]}"
            )

        # Birth-site classification (raw vs post vs composite vs UI cache)
        from hybrid_editor.diag_shadow_fringe import bg_residue_mask

        raw_m, raw_s = bg_residue_mask(bgr, raw_alpha)
        fin_m, fin_s = bg_residue_mask(bgr, final_alpha)
        report["bg_residue_raw"] = raw_s
        report["bg_residue_final"] = fin_s
        report["post_vs_raw_residue_delta_cover"] = round(
            float(fin_s["residue_cover"]) - float(raw_s["residue_cover"]), 4
        )

        face_raw = report["rois"]["face_front"]["raw"]["mean_alpha"]
        face_fin = report["rois"]["face_front"]["final"]["mean_alpha"]
        chin_raw = report["rois"]["under_chin"]["raw"]["mean_alpha"]
        chin_fin = report["rois"]["under_chin"]["final"]["mean_alpha"]
        face_elig = float(
            report["rois"]["face_front"]["raw"].get("mid_bg_eligible_frac", 0.0) or 0.0
        )
        global_cover = float(raw_s.get("residue_cover", 0.0) or 0.0)

        if face_raw >= 0.25 and abs(face_fin - face_raw) < 0.04:
            path_hint = "raw_or_suppress_miss — raw already foggy; suppress barely changed face ROI"
        elif face_raw < 0.15 and face_fin >= 0.25:
            path_hint = "post_grew — unexpected for Gyors soft path"
        elif face_fin < 0.12 and face_raw >= 0.25:
            path_hint = "suppress_ok_alpha — if UI still shows fog → FG RGB spill or UI cache"
        elif face_fin < 0.12 and global_cover >= 0.002 and face_elig < 0.01:
            path_hint = (
                "roi_miss_global_residue — full-frame mid-BG residue exists but "
                "selected face ROI still clean; inspect auto_roi candidates / PNGs"
            )
        elif face_fin < 0.12:
            path_hint = (
                "alpha_clean_in_roi — if UI bad → wrong frame, UI cache, or "
                "residue outside even auto person/blob ROIs"
            )
        else:
            path_hint = "mixed — inspect PNGs + ROI hypothesis_hint"
        report["path_hint"] = path_hint
        report["face_front_delta_alpha"] = round(float(face_fin - face_raw), 4)
        report["under_chin_delta_alpha"] = round(float(chin_fin - chin_raw), 4)

        # --- PNG dumps ---
        def _w(name: str, img: np.ndarray) -> None:
            cv2.imwrite(str(out / name), img)

        _w("00_orig_rgb.png", bgr)
        _w("01_raw_rvm_alpha.png", _alpha_png(raw_alpha))
        _w("02_final_alpha.png", _alpha_png(final_alpha))
        _w("03_fg_used_rgb.png", fg_used)
        _w("04_comp_final_on_magenta.png", composite_over_solid(fg_used, final_alpha, (255, 0, 255)))
        _w("05_comp_final_on_white.png", composite_over_solid(fg_used, final_alpha, (255, 255, 255)))
        _w("06_comp_raw_on_magenta.png", composite_over_solid(bgr, raw_alpha, (255, 0, 255)))
        _w("07_comp_src_final_on_magenta.png", composite_over_solid(bgr, final_alpha, (255, 0, 255)))
        _w("08_roi_overlay.png", draw_roi_overlay(bgr, rois))
        _w("09_residue_mask_raw.png", (raw_m.astype(np.uint8) * 255))
        _w("10_residue_mask_final.png", (fin_m.astype(np.uint8) * 255))

        # Optional official-style comparison
        if compare_official and session is not None:
            variants = []
            for label, ds, as_rgb in (
                ("official_rgb_ds025", 0.25, True),
                ("official_rgb_ds040", 0.40, True),
                ("wrong_bgr_as_rgb_ds025", 0.25, False),
            ):
                try:
                    a_var = official_style_rvm_matte(
                        bgr, session, downsample_ratio=ds, assume_rgb_input=as_rgb
                    )
                    _w(f"20_{label}_alpha.png", _alpha_png(a_var))
                    _w(
                        f"21_{label}_comp_magenta.png",
                        composite_over_solid(bgr, a_var, (255, 0, 255)),
                    )
                    variants.append(
                        {
                            "label": label,
                            "downsample_ratio": ds,
                            "assume_rgb_input": as_rgb,
                            "face_front_mean_alpha": roi_stats(
                                a_var, bgr, rois["face_front"]
                            )["mean_alpha"],
                            "under_chin_mean_alpha": roi_stats(
                                a_var, bgr, rois["under_chin"]
                            )["mean_alpha"],
                        }
                    )
                except Exception as exc:  # noqa: BLE001
                    variants.append({"label": label, "error": str(exc)[:240]})
            report["official_style_variants"] = variants
            # Side-by-side: HybridCut raw | official rgb ds | wrong BGR
            try:
                panels = [
                    _alpha_png(raw_alpha),
                    cv2.imread(str(out / "20_official_rgb_ds025_alpha.png"), cv2.IMREAD_GRAYSCALE),
                    cv2.imread(
                        str(out / "20_wrong_bgr_as_rgb_ds025_alpha.png"),
                        cv2.IMREAD_GRAYSCALE,
                    ),
                ]
                if all(p is not None for p in panels):
                    # to BGR for concat label strip
                    panels_bgr = [cv2.cvtColor(p, cv2.COLOR_GRAY2BGR) for p in panels]
                    for img, lab in zip(
                        panels_bgr,
                        ("hybrid_raw", "official_rgb", "bgr_as_rgb"),
                    ):
                        cv2.putText(
                            img,
                            lab,
                            (8, 24),
                            cv2.FONT_HERSHEY_SIMPLEX,
                            0.7,
                            (0, 255, 255),
                            2,
                        )
                    _w("22_alpha_side_by_side.png", np.concatenate(panels_bgr, axis=1))
            except Exception as exc:  # noqa: BLE001
                report["side_by_side_error"] = str(exc)[:200]

        # Two-person check on final hard cores
        hard = (final_alpha >= 0.55).astype(np.uint8) * 255
        n, _lab, st, _ = cv2.connectedComponentsWithStats(hard, connectivity=8)
        areas = sorted(
            [int(st[i, cv2.CC_STAT_AREA]) for i in range(1, n)], reverse=True
        )
        report["person_hard_cc_areas"] = areas[:8]
        report["two_people_hard_cores"] = bool(
            len(areas) >= 2 and areas[1] >= max(40, int(areas[0] * 0.08))
        )

        (out / "report.json").write_text(
            json.dumps(report, indent=2), encoding="utf-8"
        )
        print(f"path_hint: {path_hint}")
        print(f"Wrote {out}")
        print(f"Report: {out / 'report.json'}")
        return out
    finally:
        try:
            eng.close()
        except Exception:  # noqa: BLE001
            pass


def main(argv: Optional[list[str]] = None) -> int:
    import argparse

    ap = argparse.ArgumentParser(
        description="HybridCut face-front / under-chin BG residue diagnostic"
    )
    ap.add_argument("--media", required=True, help="Video path (original kept intact)")
    ap.add_argument("--t", type=float, default=None, help="Time seconds")
    ap.add_argument("--frame", type=int, default=None, help="Frame index (overrides --t)")
    ap.add_argument("--install-root", default=None, help="HybridCut / hybrid_cut root")
    ap.add_argument(
        "--out",
        default=None,
        help="Parent output dir (default: <root>/cache/diag_face_residue)",
    )
    ap.add_argument(
        "--roi-face",
        default=None,
        help="Optional face_front ROI x0,y0,x1,y1 (default: auto person+residue)",
    )
    ap.add_argument(
        "--roi-chin",
        default=None,
        help="Optional under_chin ROI x0,y0,x1,y1 (default: auto person+residue)",
    )
    ap.add_argument(
        "--no-official-compare",
        action="store_true",
        help="Skip official-style RVM side-by-side",
    )
    ap.add_argument(
        "--no-purge",
        action="store_true",
        help="Do not purge MaskStore/preview cache for this clip",
    )
    ap.add_argument("--mode", choices=("gyors", "max"), default="gyors")
    args = ap.parse_args(argv)

    if args.t is None and args.frame is None:
        args.t = 0.0

    try:
        run_diag(
            media=Path(args.media),
            t_sec=args.t,
            frame_index=args.frame,
            install_root=Path(args.install_root) if args.install_root else None,
            out_dir=Path(args.out) if args.out else None,
            roi_face=args.roi_face,
            roi_chin=args.roi_chin,
            compare_official=not args.no_official_compare,
            purge_cache=not args.no_purge,
            mode=args.mode,
        )
        return 0
    except Exception as exc:  # noqa: BLE001
        print(f"FAIL: {exc}", file=sys.stderr)
        logger.exception("diag_face_residue failed")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
