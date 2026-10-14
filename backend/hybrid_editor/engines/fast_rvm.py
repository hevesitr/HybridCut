"""FastEngine — real ORT RVM when HYBRID_RVM_ONNX / models path set.

Fallback: documented OpenCV GrabCut-center heuristic (scaffold / CI / no weights).
CUDA EP preferred; VRAM guard prevents Fast+Max CUDA together on 8GB.
Preview path uses disk MaskStore + scrub decode prefetch (AHEAD≈8).
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any, Optional

import cv2
import numpy as np

from hybrid_editor import ROOT
from hybrid_editor.cache import FrameCache, MaskStore, ScrubPrefetcher, mask_dir
from hybrid_editor.cache.proxy_lanes import Lane, ProxyLaneCache
from hybrid_editor.engines.base import (
    BakeResult,
    EngineCapabilities,
    EngineMode,
    MattingEngine,
    MediaInfo,
    PreviewFrame,
    ProgressCb,
)
from hybrid_editor.engines.vram import acquire_cuda, release_cuda
from hybrid_editor.export.composer import (
    AudioSegment,
    finalize_bgcut_exports,
    media_has_audio,
    write_preview_mp4,
)
from hybrid_editor.media.video_io import (
    downscale_long_side,
    encode_preview_pair,
    encode_source_only_preview,
    is_matte_empty,
    probe_video,
    read_frame_at,
    read_frame_index,
)

logger = logging.getLogger(__name__)

HEURISTIC_NOTE = (
    "Heuristic fallback (OpenCV GrabCut + center prior): used when no RVM ONNX is "
    "found (HYBRID_RVM_ONNX / hybrid models/ / parent Documents\\Videoeditor\\models) "
    "or onnxruntime fails to load. Not ML-quality — place rvm_*.onnx or set "
    "HYBRID_RVM_ONNX; install onnxruntime-gpu in the active venv for CUDA."
)


def _env_path(name: str) -> Optional[Path]:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return None
    p = Path(raw).expanduser()
    return p if p.is_file() else None


def _env_dir(name: str) -> Optional[Path]:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return None
    p = Path(raw).expanduser()
    return p if p.is_dir() else None


# Gyors / scrub: MobileNet first (speed). Override with HYBRID_RVM_ONNX.
# Prefer fp32 — CUDA EP + torch-jit-export fp16 often MemcpyTransformers to a flat pha.
_RVM_NAMES_FAST = (
    "rvm_mobilenetv3_fp32.onnx",
    "rvm_mobilenetv3.onnx",
    "rvm_mobilenetv3_fp16.onnx",
    "rvm_resnet50_fp32.onnx",
    "rvm_resnet50_fp16.onnx",
)
# Max / export: ResNet50 first when present (sharper person edges). CapCut BEST/RECOMMENDED.
# fp32 before fp16: RTX 3060 ORT CUDA + fp16 RVM has produced all-ones / gray-slab mattes.
_RVM_NAMES_QUALITY = (
    "rvm_resnet50_fp32.onnx",
    "rvm_resnet50.onnx",
    "rvm_resnet50_fp16.onnx",
    "rvm_mobilenetv3_fp32.onnx",
    "rvm_mobilenetv3.onnx",
    "rvm_mobilenetv3_fp16.onnx",
)
# Back-compat alias
_RVM_NAMES = _RVM_NAMES_FAST


def resolve_rvm_input_dtype(session: Any = None, model_path: Optional[Path] = None) -> np.dtype:
    """Pick float16 vs float32 for RVM ORT feeds (src + recurrent).

    Priority:
    1. ORT ``src`` input type meta (``tensor(float16)`` / ``tensor(float)``)
    2. Filename hint (``fp16`` / ``fp32`` in stem)
    3. Default float32
    """
    if session is not None:
        try:
            for inp in session.get_inputs():
                if getattr(inp, "name", None) != "src":
                    continue
                typ = (getattr(inp, "type", None) or "").lower()
                if "float16" in typ:
                    return np.dtype(np.float16)
                if "float" in typ:  # tensor(float) == float32
                    return np.dtype(np.float32)
        except Exception:  # noqa: BLE001
            pass
    if model_path is not None:
        stem = Path(model_path).stem.lower()
        if "fp16" in stem:
            return np.dtype(np.float16)
        if "fp32" in stem:
            return np.dtype(np.float32)
    return np.dtype(np.float32)


def rvm_fp32_sibling(model_path: Path) -> Optional[Path]:
    """If ``*fp16*.onnx`` has a same-dir fp32 twin, return it (CUDA-stable path)."""
    p = Path(model_path)
    stem = p.stem
    lower = stem.lower()
    if "fp16" not in lower:
        return None
    for repl in ("fp32", "fp32"):
        cand = p.with_name(lower.replace("fp16", repl) + p.suffix)
        # Preserve original casing attempt + lowercase stem
        for c in (p.with_name(stem.replace("fp16", "fp32").replace("FP16", "fp32") + p.suffix), cand):
            if c.is_file() and c.resolve() != p.resolve():
                return c
    return None


def cold_recurrent(dtype: np.dtype) -> np.ndarray:
    """RVM cold-start r1i..r4i — always 1×1×1×1 (CapCut / PeterL1n export)."""
    return np.zeros((1, 1, 1, 1), dtype=dtype)


def _first_rvm_in_dir(models_dir: Path, *, prefer: str = "fast") -> Optional[Path]:
    if not models_dir.is_dir():
        return None
    names = _RVM_NAMES_QUALITY if prefer == "quality" else _RVM_NAMES_FAST
    for name in names:
        cand = models_dir / name
        if cand.is_file():
            return cand
    found = sorted(models_dir.glob("rvm_*.onnx"))
    return found[0] if found else None


def parent_videoeditor_roots() -> list[Path]:
    """CapCut Videoeditor roots that may hold models/ + .venv (Windows nested hybrid_cut)."""
    roots: list[Path] = []
    # Nested install: Documents\Videoeditor\hybrid_cut → parent Documents\Videoeditor
    parent = ROOT.parent
    if parent.name.lower() in {"videoeditor", "hybrid_cut"} or (parent / "models").is_dir():
        roots.append(parent)
    if parent.parent.name.lower() == "videoeditor":
        roots.append(parent.parent)
    home = Path.home()
    for cand in (
        home / "Documents" / "Videoeditor",
        home / "Documents" / "videoeditor",
    ):
        if cand.is_dir():
            roots.append(cand)
    # Dedup preserve order
    out: list[Path] = []
    seen: set[str] = set()
    for r in roots:
        key = str(r.resolve()) if r.exists() else str(r)
        if key not in seen:
            seen.add(key)
            out.append(r)
    return out


def resolve_rvm_onnx(*, prefer: str = "fast") -> Optional[Path]:
    """Locate RVM ONNX: env → hybrid models/ → parent Videoeditor models/ → USERPROFILE.

    prefer:
      - ``fast``: MobileNet first (Gyors scrub)
      - ``quality``: ResNet50 first when present (Max / sharp export)

    Explicit ``HYBRID_RVM_ONNX`` / ``VIDEOEDITOR_RVM_ONNX`` always wins.
    Does not download or redistribute weights. Parent CapCut tree often already has
    ``Documents\\Videoeditor\\models\\rvm_*.onnx`` from the Tk cutout app.
    """
    prefer = (prefer or "fast").strip().lower()
    if prefer not in {"fast", "quality"}:
        prefer = "fast"

    for env_name in ("HYBRID_RVM_ONNX", "VIDEOEDITOR_RVM_ONNX"):
        model = _env_path(env_name)
        if model is not None:
            return model

    for dir_env in ("HYBRID_MODELS_DIR", "VIDEOEDITOR_MODELS", "VIDEOEDITOR_MODELS_DIR"):
        d = _env_dir(dir_env)
        if d is not None:
            hit = _first_rvm_in_dir(d, prefer=prefer)
            if hit is not None:
                return hit

    hit = _first_rvm_in_dir(ROOT / "models", prefer=prefer)
    if hit is not None:
        return hit

    for root in parent_videoeditor_roots():
        hit = _first_rvm_in_dir(root / "models", prefer=prefer)
        if hit is not None:
            return hit

    return None


def probe_ort_runtime() -> dict[str, Any]:
    """ORT / CUDA EP probe for UI status chips.

    ``cuda_ep`` is True only when the CUDA **plugin EP is actually registered**
    (session can activate CUDAExecutionProvider) — not merely listed.
    """
    try:
        from hybrid_editor.cuda_path import (
            CUDA_EP_MISSING_HINT_HU,
            inject_nvidia_pip_libs,
            pip_cudnn_present,
            probe_cuda_ep_usable,
        )

        inject_nvidia_pip_libs()
        cudnn_ok, cudnn_detail = pip_cudnn_present()
    except Exception as exc:  # noqa: BLE001
        cudnn_ok, cudnn_detail = False, f"cuda_path unavailable: {exc}"
        CUDA_EP_MISSING_HINT_HU = (
            "CPU ORT: CUDA EP plugin hiányzik — onnxruntime-gpu + cudnn PATH."
        )
        probe_cuda_ep_usable = None  # type: ignore[assignment]

    prefer = os.environ.get("HYBRID_RVM_PREFER", "fast").strip().lower() or "fast"
    onnx = resolve_rvm_onnx(prefer=prefer if prefer in {"fast", "quality"} else "fast")
    info: dict[str, Any] = {
        "onnx_found": onnx is not None,
        "onnx_path": str(onnx) if onnx else None,
        "onnx_name": onnx.name if onnx else None,
        "onnx_prefer": prefer,
        "ort_available": False,
        "cuda_ep": False,
        "cuda_ep_listed": False,
        "cuda_ep_registered": False,
        "providers": [],
        "prefer": os.environ.get("HYBRID_ORT_PROVIDER", "cpu").strip().lower() or "cpu",
        "source": None,
        "cudnn_ok": cudnn_ok,
        "cudnn_detail": cudnn_detail,
        "cuda_fallback": None,
        "cuda_ep_detail": None,
        "ort_label_hu": "ORT —",
    }
    if onnx is not None:
        try:
            onnx_res = onnx.resolve()
            hybrid_models = (ROOT / "models").resolve()
            if hybrid_models in onnx_res.parents or onnx_res.parent == hybrid_models:
                info["source"] = "hybrid_models"
            elif any(
                (r / "models").resolve() in onnx_res.parents
                or onnx_res.parent == (r / "models").resolve()
                for r in parent_videoeditor_roots()
                if (r / "models").exists()
            ):
                info["source"] = "parent_videoeditor"
            elif os.environ.get("HYBRID_RVM_ONNX") or os.environ.get("VIDEOEDITOR_RVM_ONNX"):
                info["source"] = "env"
            else:
                info["source"] = "discovered"
        except Exception:  # noqa: BLE001
            info["source"] = "discovered"
    try:
        import onnxruntime as ort  # type: ignore

        providers = list(ort.get_available_providers())
        info["ort_available"] = True
        info["providers"] = providers
        listed = "CUDAExecutionProvider" in providers
        info["cuda_ep_listed"] = listed
        # Skip heavy session probe when env forces CPU.
        force_cpu = info["prefer"] in {"cpu", "cpuexecutionprovider"}
        if force_cpu:
            info["cuda_ep"] = False
            info["cuda_ep_registered"] = False
            info["cuda_ep_detail"] = "HYBRID_ORT_PROVIDER=cpu"
            info["ort_label_hu"] = "CPU ORT"
        elif listed and probe_cuda_ep_usable is not None:
            ok, detail = probe_cuda_ep_usable(ort, model_path=onnx)
            info["cuda_ep_registered"] = bool(ok)
            info["cuda_ep"] = bool(ok)
            info["cuda_ep_detail"] = detail
            if ok:
                info["ort_label_hu"] = "RVM CUDA"
            else:
                info["cuda_fallback"] = detail or CUDA_EP_MISSING_HINT_HU
                info["ort_label_hu"] = "CPU ORT"
        elif listed:
            # Probe helper unavailable — be honest: listed ≠ registered.
            info["cuda_ep"] = False
            info["cuda_ep_registered"] = False
            info["cuda_ep_detail"] = "CUDA listed; registration not verified"
            info["ort_label_hu"] = "CPU ORT?"
        else:
            info["cuda_ep"] = False
            info["cuda_ep_registered"] = False
            info["cuda_ep_detail"] = f"CUDA EP not listed: {providers}"
            info["ort_label_hu"] = "CPU ORT"
            info["cuda_fallback"] = CUDA_EP_MISSING_HINT_HU
    except Exception as exc:  # noqa: BLE001
        info["ort_error"] = str(exc)
        info["ort_label_hu"] = "ORT hiba"
    return info


def solid_bg_person_alpha(bgr: np.ndarray) -> np.ndarray:
    """Key a dominant uniform background via corner samples (blue/green screen).

    classic RVM-friendly scenes (solid blue behind a close-up) must not leave the
    user on gray-slab toast when MobileNet/ResNet fail on CPU. Corners avoid the
    hair/shoulder rim that poisons full-border stats on talking-head close-ups.
    """
    h, w = bgr.shape[:2]
    if h < 16 or w < 16:
        return np.zeros((h, w), dtype=np.float32)
    cs = max(4, min(h, w) // 10)
    corners = np.concatenate(
        [
            bgr[:cs, :cs].reshape(-1, 3),
            bgr[:cs, -cs:].reshape(-1, 3),
            bgr[-cs:, :cs].reshape(-1, 3),
            bgr[-cs:, -cs:].reshape(-1, 3),
        ],
        axis=0,
    )
    cf = corners.astype(np.float32)
    bg = np.median(cf, axis=0)
    corner_std = float(cf.std(axis=0).mean())
    # Busy / textured corners → not a solid plate; skip chroma path.
    if corner_std > 28.0:
        return np.zeros((h, w), dtype=np.float32)
    dist = np.sqrt(((bgr.astype(np.float32) - bg) ** 2).sum(axis=2))
    corner_dist = np.concatenate(
        [
            dist[:cs, :cs].ravel(),
            dist[:cs, -cs:].ravel(),
            dist[-cs:, :cs].ravel(),
            dist[-cs:, -cs:].ravel(),
        ]
    )
    # Absolute threshold from clean corner noise — not full-border percentiles
    # (close-up hair on the rim inflated thr above person distance).
    thr_lo = max(22.0, float(np.percentile(corner_dist, 90)) * 2.2 + corner_std)
    thr_hi = max(thr_lo + 18.0, thr_lo * 2.0)
    alpha = np.clip((dist - thr_lo) / (thr_hi - thr_lo), 0.0, 1.0).astype(np.float32)
    soft = (alpha > 0.35).astype(np.uint8) * 255
    k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
    soft = cv2.morphologyEx(soft, cv2.MORPH_OPEN, k, iterations=1)
    soft = cv2.morphologyEx(soft, cv2.MORPH_CLOSE, k, iterations=2)
    alpha = np.maximum(
        alpha * 0.35, cv2.GaussianBlur(soft.astype(np.float32) / 255.0, (0, 0), 1.6)
    )
    rim = max(2, min(h, w) // 80)
    alpha[:rim, :] *= 0.12
    alpha[-rim:, :] *= 0.12
    alpha[:, :rim] *= 0.12
    alpha[:, -rim:] *= 0.12
    return np.clip(alpha, 0.0, 1.0).astype(np.float32)


def heuristic_person_alpha(bgr: np.ndarray) -> np.ndarray:
    """Soft person-ish matte without ML — scaffold / CI / CPU-RVM failure fallback.

    Prefers **all** skin/body blobs (multi-person), not a single center oval, so
    secondary subjects survive when RVM weights are missing. Close-up face/hair
    frames (high skin cover) use a tighter center prior so the rim stays punched.
    """
    h, w = bgr.shape[:2]
    hsv = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)
    skin = cv2.inRange(hsv, (0, 30, 50), (25, 180, 255))
    skin2 = cv2.inRange(hsv, (160, 30, 50), (180, 180, 255))
    skin = cv2.bitwise_or(skin, skin2)
    # Clothing / body mass: mid-sat non-green (avoid grass BG) + warm/neutral
    body = cv2.inRange(hsv, (0, 20, 35), (40, 200, 245))
    body2 = cv2.inRange(hsv, (140, 15, 35), (180, 200, 245))
    body = cv2.bitwise_or(body, body2)
    lab = cv2.cvtColor(bgr, cv2.COLOR_BGR2LAB)
    skin_frac = float((skin > 0).mean())
    closeup = skin_frac >= 0.12  # talking-head / face-fill often lands here
    # Multi-lobed prior: left / center / right thirds (group shots)
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    priors = []
    fracs = (0.50,) if closeup else (0.28, 0.50, 0.72)
    rx = 0.42 if closeup else 0.28
    ry = 0.55 if closeup else 0.48
    cy0 = 0.48 if closeup else 0.52
    for cx_frac in fracs:
        cx, cy = w * cx_frac, h * cy0
        dist = np.sqrt(((xx - cx) / (w * rx)) ** 2 + ((yy - cy) / (h * ry)) ** 2)
        priors.append(np.clip(1.0 - dist, 0.0, 1.0))
    center = np.maximum.reduce(priors)
    edges = cv2.Canny(cv2.GaussianBlur(lab[:, :, 0], (5, 5), 0), 40, 120)
    edges = cv2.dilate(edges, np.ones((3, 3), np.uint8), iterations=1)
    mask = np.full((h, w), cv2.GC_PR_BGD, np.uint8)
    mask[center > (0.35 if closeup else 0.50)] = cv2.GC_PR_FGD
    mask[body > 0] = cv2.GC_PR_FGD
    mask[skin > 0] = cv2.GC_FGD
    # Narrower hard-BGD rim on close-ups so hair near edges is not erased.
    border = max(2, min(h, w) // (55 if closeup else 40))
    mask[:border, :] = cv2.GC_BGD
    mask[-border:, :] = cv2.GC_BGD
    mask[:, :border] = cv2.GC_BGD
    mask[:, -border:] = cv2.GC_BGD
    try:
        bgd = np.zeros((1, 65), np.float64)
        fgd = np.zeros((1, 65), np.float64)
        small = bgr
        scale = 1.0
        if max(h, w) > 640:
            scale = 640.0 / max(h, w)
            small = cv2.resize(bgr, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_AREA)
            mask_s = cv2.resize(mask, (small.shape[1], small.shape[0]), interpolation=cv2.INTER_NEAREST)
        else:
            mask_s = mask
        cv2.grabCut(small, mask_s, None, bgd, fgd, 2, cv2.GC_INIT_WITH_MASK)
        gc = np.where((mask_s == cv2.GC_FGD) | (mask_s == cv2.GC_PR_FGD), 1.0, 0.0).astype(np.float32)
        if scale != 1.0:
            gc = cv2.resize(gc, (w, h), interpolation=cv2.INTER_LINEAR)
    except Exception:
        gc = center * 0.55 + (skin.astype(np.float32) / 255.0) * 0.25 + (
            body.astype(np.float32) / 255.0
        ) * 0.20
    if closeup:
        alpha = (
            0.55 * gc
            + 0.22 * center
            + 0.16 * (skin.astype(np.float32) / 255.0)
            + 0.07 * (edges.astype(np.float32) / 255.0)
        )
    else:
        alpha = (
            0.70 * gc
            + 0.12 * center
            + 0.10 * (skin.astype(np.float32) / 255.0)
            + 0.08 * (edges.astype(np.float32) / 255.0)
        )
    alpha = cv2.GaussianBlur(alpha, (0, 0), sigmaX=1.6 if not closeup else 2.2)
    # Keep every person-sized blob from the soft prior (not only the largest)
    try:
        from hybrid_editor.engines.videoeditor_polish import keep_person_instances_soft

        alpha = keep_person_instances_soft(alpha, min_area_frac=0.004, relative_frac=0.10)
    except Exception:
        pass
    # Guarantee punched rim so close-up never collapses to an all-ones gray slab.
    rim = max(2, min(h, w) // 80)
    alpha[:rim, :] *= 0.15
    alpha[-rim:, :] *= 0.15
    alpha[:, :rim] *= 0.15
    alpha[:, -rim:] *= 0.15
    return np.clip(alpha, 0.0, 1.0).astype(np.float32)


def relaxed_bg_person_alpha(bgr: np.ndarray) -> np.ndarray:
    """Person vs background via border-median distance — works on textured plates.

    solid_bg_person_alpha bails when corner_std is high (outdoor / busy rooms).
    matte-hard still needs a silhouette when CPU RVM emits a gray slab: sample the
    full border ring, estimate BG, keep pixels that differ — multi-person OK.
    """
    h, w = bgr.shape[:2]
    if h < 16 or w < 16:
        return np.zeros((h, w), dtype=np.float32)
    b = max(3, min(h, w) // 25)
    border = np.concatenate(
        [
            bgr[:b, :].reshape(-1, 3),
            bgr[-b:, :].reshape(-1, 3),
            bgr[:, :b].reshape(-1, 3),
            bgr[:, -b:].reshape(-1, 3),
        ],
        axis=0,
    ).astype(np.float32)
    bg = np.median(border, axis=0)
    dist = np.sqrt(((bgr.astype(np.float32) - bg) ** 2).sum(axis=2))
    # Percentile thr from border distances — robust to texture.
    bdist = np.concatenate(
        [
            dist[:b, :].ravel(),
            dist[-b:, :].ravel(),
            dist[:, :b].ravel(),
            dist[:, -b:].ravel(),
        ]
    )
    thr_lo = float(np.percentile(bdist, 70)) + 12.0
    thr_hi = max(thr_lo + 24.0, float(np.percentile(bdist, 92)) + 18.0)
    alpha = np.clip((dist - thr_lo) / max(1e-3, thr_hi - thr_lo), 0.0, 1.0).astype(
        np.float32
    )
    soft = (alpha > 0.35).astype(np.uint8) * 255
    k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (7, 7))
    # Close only — open punches hair/crown holes on textured BG.
    soft = cv2.morphologyEx(soft, cv2.MORPH_CLOSE, k, iterations=3)
    alpha = np.maximum(
        alpha * 0.45, cv2.GaussianBlur(soft.astype(np.float32) / 255.0, (0, 0), 2.0)
    )
    rim = max(2, min(h, w) // 90)
    alpha[:rim, :] *= 0.20
    alpha[-rim:, :] *= 0.20
    alpha[:, :rim] *= 0.20
    alpha[:, -rim:] *= 0.20
    return np.clip(alpha, 0.0, 1.0).astype(np.float32)


def hard_person_alpha(bgr: np.ndarray) -> np.ndarray:
    """Always-on person salvage for CPU ORT gray-slab / empty ladder failures.

    Guarantees a non-degenerate, non-empty silhouette so Előnézet never sticks on
    "Hibás maszk (egyenletes szürke lap)" for people-on-background footage.
    Order: GrabCut heuristic → relaxed BG distance → multi-lobe prior (+ skin).
    """
    from hybrid_editor.media.video_io import (
        is_matte_degenerate,
        is_matte_empty,
        is_matte_good_enough,
        is_matte_sliver,
    )

    h, w = bgr.shape[:2]
    candidates: list[np.ndarray] = []
    try:
        candidates.append(heuristic_person_alpha(bgr))
    except Exception:  # noqa: BLE001
        pass
    try:
        candidates.append(solid_bg_person_alpha(bgr))
    except Exception:  # noqa: BLE001
        pass
    try:
        candidates.append(relaxed_bg_person_alpha(bgr))
    except Exception:  # noqa: BLE001
        pass

    best: Optional[np.ndarray] = None
    best_score = -1.0
    for cand in candidates:
        if cand is None or cand.shape[:2] != (h, w):
            continue
        if is_matte_empty(cand) or is_matte_degenerate(cand) or is_matte_sliver(cand):
            continue
        cover = float((cand > 0.15).mean())
        std = float(cand.std())
        # preview-fast: mid cover (0.15–0.75) beats near-full milky plates that
        # look like the gray Maszk slab even when not formally degenerate.
        if cover < 0.02 or cover > 0.82:
            score = std * 0.35 + float(cand.max()) * 0.15
        else:
            score = cover * 2.2 + std * 2.0 + float(cand.max()) * 0.6
            # Bonus for two-person / indoor structured mattes.
            if 0.18 <= cover <= 0.70 and std >= 0.12:
                score += 1.2
        if is_matte_good_enough(cand):
            score += 1.5
        if score > best_score:
            best_score = score
            best = cand
    if best is not None and not is_matte_empty(best) and not is_matte_degenerate(best):
        try:
            from hybrid_editor.engines.videoeditor_polish import fill_person_holes

            filled = fill_person_holes(best, min_fg=0.16, close_px=11, fill_value=0.90)
            # Keep fill only when it does not collapse into a strip or slab.
            if (
                not is_matte_empty(filled)
                and not is_matte_degenerate(filled)
                and not is_matte_sliver(filled)
            ):
                best = filled
        except Exception:  # noqa: BLE001
            pass
        # If fill bloated into a near-slab, keep pre-fill candidate.
        if is_matte_degenerate(best) or float((best > 0.15).mean()) > 0.90:
            best = candidates[0] if candidates else best
        if not is_matte_sliver(best):
            return np.clip(best, 0.0, 1.0).astype(np.float32)

    # Absolute last resort: visible multi-lobe prior so UI always shows recognition.
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    priors = []
    for cx_frac in (0.32, 0.50, 0.68):
        cx, cy = w * cx_frac, h * 0.52
        dist = np.sqrt(((xx - cx) / (w * 0.26)) ** 2 + ((yy - cy) / (h * 0.46)) ** 2)
        priors.append(np.clip(1.0 - dist, 0.0, 1.0))
    prior = np.maximum.reduce(priors)
    hsv = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)
    skin = cv2.inRange(hsv, (0, 25, 45), (25, 190, 255))
    skin2 = cv2.inRange(hsv, (160, 25, 45), (180, 190, 255))
    skin = cv2.bitwise_or(skin, skin2)
    alpha = np.clip(0.72 * prior + 0.28 * (skin.astype(np.float32) / 255.0), 0.0, 1.0)
    alpha = cv2.GaussianBlur(alpha, (0, 0), sigmaX=2.0)
    rim = max(3, min(h, w) // 60)
    alpha[:rim, :] *= 0.08
    alpha[-rim:, :] *= 0.08
    alpha[:, :rim] *= 0.08
    alpha[:, -rim:] *= 0.08
    # Lift peak so Cutout/Maszk clearly show a person blob.
    peak = float(alpha.max())
    if peak > 1e-4 and peak < 0.55:
        alpha = np.clip(alpha * (0.75 / peak), 0.0, 1.0)
    try:
        from hybrid_editor.engines.videoeditor_polish import fill_person_holes

        alpha = fill_person_holes(alpha, min_fg=0.16, close_px=13, fill_value=0.90)
    except Exception:  # noqa: BLE001
        pass
    return alpha.astype(np.float32)


class _OrtRvmSession:
    """RVM ONNX session — CPU-first; CUDA only when HYBRID_ORT_PROVIDER=cuda.

    RTX 3060 note: ORT CUDA + ``torch-jit-export`` RVM (esp. fp16) can emit
    MemcpyTransformer / Conv Fallback warnings and a **uniform / all-ones pha**.
    Default launch is CPUExecutionProvider so Előnézet never hits that path.
    When CUDA is requested we prefer fp32 weights, CapCut-style ``1×1×1×1`` cold
    recurrent, safe ``pha`` extract, and rebuild CPU-only on gray-slab smoke.
    """

    def __init__(self, model_path: Path) -> None:
        from hybrid_editor.cuda_path import (
            CUDA_EP_MISSING_HINT_HU,
            _OrtWarningCatcher,
            brief_ort_error,
            inject_nvidia_pip_libs,
            is_cudnn_or_cuda_ep_error,
            is_plugin_ep_missing_text,
            pip_cudnn_present,
            probe_cuda_ep_usable,
        )

        # Must run BEFORE InferenceSession — LoadLibrary looks up cudnn64_*.dll via PATH.
        inject_nvidia_pip_libs()
        import onnxruntime as ort  # type: ignore

        model_path = Path(model_path)
        # Auto-prefer fp32 twin for CUDA stability unless user opts into fp16.
        allow_fp16 = os.environ.get("HYBRID_RVM_ALLOW_FP16", "").strip().lower() in {
            "1",
            "true",
            "yes",
            "on",
        }
        if not allow_fp16:
            sib = rvm_fp32_sibling(model_path)
            if sib is not None:
                logger.info(
                    "RVM: preferring fp32 sibling over fp16 for CUDA-stable pha (%s → %s)",
                    model_path.name,
                    sib.name,
                )
                model_path = sib

        prefer = os.environ.get("HYBRID_ORT_PROVIDER", "cpu").strip().lower() or "cpu"
        avail = list(ort.get_available_providers())
        providers: list[Any] = []
        uses_cuda = False
        self.fallback_note: Optional[str] = None

        # CPU-first: never auto-pick CUDA just because it is listed (plugin EP often broken).
        want_cuda = prefer in {"cuda", "gpu", "cudaexecutionprovider"}
        if prefer == "dml" and "DmlExecutionProvider" in avail:
            providers.append("DmlExecutionProvider")
            want_cuda = False
        elif prefer in {"cpu", "cpuexecutionprovider", ""}:
            want_cuda = False

        # Probe plugin EP **before** RVM inference — listed CUDA ≠ registered CUDA.
        # Missing ort-cuda plugin → gray-slab pha; fall back to CPUExecutionProvider now.
        # CRITICAL: when CUDA is unusable, providers must be CPU-ONLY (never [CUDA, CPU]).
        # A dual list still logs MemcpyTransformer and can emit all-ones gray pha.
        if want_cuda and "CUDAExecutionProvider" in avail:
            ok, detail = probe_cuda_ep_usable(ort, model_path=model_path)
            if ok:
                providers.append(self._cuda_provider_tuple())
                uses_cuda = True
            else:
                self.fallback_note = (
                    f"CUDA→CPU: {detail}"
                    if detail.startswith("CUDA") or detail.startswith("ORT")
                    else f"CUDA→CPU: plugin EP hiányzik — {detail}"
                )
                if CUDA_EP_MISSING_HINT_HU not in self.fallback_note:
                    self.fallback_note = f"{self.fallback_note} · {CUDA_EP_MISSING_HINT_HU}"
                logger.warning(
                    "RVM: CUDA EP not actually registered — CPU-only session before inference. %s",
                    detail,
                )
                if os.environ.get("HYBRID_ORT_PROVIDER", "").strip().lower() != "cpu":
                    os.environ["HYBRID_ORT_PROVIDER"] = "cpu"
                try:
                    from hybrid_editor.cuda_path import set_cuda_ep_probe_cache

                    set_cuda_ep_probe_cache(False, detail)
                except Exception:  # noqa: BLE001
                    pass
        elif want_cuda and "CUDAExecutionProvider" not in avail:
            self.fallback_note = (
                f"CUDA→CPU: CUDAExecutionProvider nincs listázva ({avail}). "
                f"{CUDA_EP_MISSING_HINT_HU}"
            )
            logger.warning("%s", self.fallback_note)
            os.environ["HYBRID_ORT_PROVIDER"] = "cpu"

        if uses_cuda:
            # CUDA path: CUDA first, CPU listed only as ORT safety net — but we
            # immediately rebuild CPU-only if plugin EP / smoke matte fails.
            providers.append("CPUExecutionProvider")
        else:
            providers = ["CPUExecutionProvider"]

        if uses_cuda:
            acquire_cuda("fast-ort", detail=str(model_path))
        self._uses_cuda = uses_cuda
        self._cpu_session: Any = None
        self._ort = ort
        self.model_path = model_path
        self._r1 = self._r2 = self._r3 = self._r4 = None
        self._rec_key: Optional[tuple[int, int, float]] = None
        self.last_fgr_bgr: Optional[np.ndarray] = None
        # Set when CUDA→CPU rebuild must drop Gyors MaskStore / sticky matte_error.
        self._masks_stale = False
        self._matte_gen = 0
        so = ort.SessionOptions()
        so.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
        try:
            so.log_severity_level = 2 if uses_cuda else 3
        except Exception:  # noqa: BLE001
            pass
        self._so = so

        catcher = _OrtWarningCatcher()
        try:
            with catcher:
                self.session = ort.InferenceSession(
                    str(model_path), sess_options=so, providers=providers
                )
        except Exception as exc:  # noqa: BLE001
            if uses_cuda:
                release_cuda("fast-ort")
                self._uses_cuda = False
            if uses_cuda and (
                is_cudnn_or_cuda_ep_error(exc) or is_plugin_ep_missing_text(str(exc))
            ):
                brief = brief_ort_error(exc)
                _, cudnn_detail = pip_cudnn_present()
                self.fallback_note = (
                    f"CUDA→CPU: cuDNN/CUDA EP unavailable ({brief}). "
                    f"{cudnn_detail}. {CUDA_EP_MISSING_HINT_HU}"
                )
                logger.warning("%s", self.fallback_note)
                try:
                    self.session = ort.InferenceSession(
                        str(model_path),
                        sess_options=so,
                        providers=["CPUExecutionProvider"],
                    )
                except Exception:
                    raise RuntimeError(self.fallback_note) from exc
            else:
                raise

        # Plugin EP warning during create → destroy half-broken CUDA, CPU-only.
        if uses_cuda and catcher.plugin_ep_missing():
            logger.warning(
                "RVM: ORT plugin EP warning during session create — forcing CPU-only EP"
            )
            self._rebuild_cpu_only(
                "CUDA→CPU: No registered plugin EP device for CUDAExecutionProvider. "
                + CUDA_EP_MISSING_HINT_HU,
                so,
            )
            uses_cuda = False

        self.provider = self.session.get_providers()[0]
        self.input_dtype = resolve_rvm_input_dtype(self.session, model_path)
        if uses_cuda and "CUDA" not in str(self.provider):
            if self._uses_cuda:
                release_cuda("fast-ort")
            self._uses_cuda = False
            if self.fallback_note is None:
                self.fallback_note = (
                    "CUDA→CPU: CUDA EP listed but session active provider is CPU — "
                    + CUDA_EP_MISSING_HINT_HU
                )
            os.environ["HYBRID_ORT_PROVIDER"] = "cpu"
            # Rebuild so provider list is CPU-only (drop lingering CUDA EP).
            self._rebuild_cpu_only(self.fallback_note, so)
        elif self._uses_cuda:
            # Half-broken CUDA can claim active EP then emit MemcpyTransformer gray pha.
            # Smoke once at load; on slab → CPU-only (never keep the CUDA session).
            self._smoke_cuda_or_force_cpu()
            self.provider = self.session.get_providers()[0]
            self.input_dtype = resolve_rvm_input_dtype(self.session, model_path)

    @staticmethod
    def _cuda_provider_tuple() -> Any:
        """CUDA EP options tuned for RTX 3060 RVM (avoid flaky default copies)."""
        opts = {
            "device_id": int(os.environ.get("HYBRID_CUDA_DEVICE", "0") or "0"),
            "arena_extend_strategy": "kNextPowerOfTwo",
            "cudnn_conv_algo_search": os.environ.get(
                "HYBRID_CUDNN_CONV_ALGO", "DEFAULT"
            )
            or "DEFAULT",
            "do_copy_in_default_stream": True,
        }
        # Soft VRAM cap (~3.5GB) so Fast+scrub leaves headroom on 8GB cards.
        try:
            mem_gb = float(os.environ.get("HYBRID_RVM_GPU_MEM_GB", "3.5") or "3.5")
            if mem_gb > 0:
                opts["gpu_mem_limit"] = int(mem_gb * (1024**3))
        except ValueError:
            pass
        return ("CUDAExecutionProvider", opts)

    def _rebuild_cpu_only(self, note: str, so: Any = None) -> None:
        """Destroy any CUDA/Memcpy session; create CPUExecutionProvider-only."""
        from hybrid_editor.cuda_path import set_cuda_ep_probe_cache

        if self._uses_cuda:
            try:
                release_cuda("fast-ort")
            except Exception:  # noqa: BLE001
                pass
            self._uses_cuda = False
        sess_opts = so if so is not None else getattr(self, "_so", None)
        self.session = self._ort.InferenceSession(
            str(self.model_path),
            sess_options=sess_opts,
            providers=["CPUExecutionProvider"],
        )
        active = list(self.session.get_providers())
        if not active or "CPU" not in str(active[0]):
            raise RuntimeError(
                f"CPU-only rebuild failed — active providers={active}"
            )
        self.provider = active[0]
        self._cpu_session = self.session
        self.fallback_note = note
        # Invalidate Gyors MaskStore / seed caches that may hold CUDA gray-slab.
        self._masks_stale = True
        self._matte_gen = int(getattr(self, "_matte_gen", 0)) + 1
        os.environ["HYBRID_ORT_PROVIDER"] = "cpu"
        set_cuda_ep_probe_cache(False, note)
        self.reset()
        logger.warning("%s", note)
        # Prove CPU path can emit a structured person matte (or heuristic will).
        self._verify_cpu_matte_after_rebuild()

    def _verify_cpu_matte_after_rebuild(self) -> None:
        """After CUDA→CPU: cold CPU smoke; log if still empty (heuristic covers preview)."""
        from hybrid_editor.media.video_io import is_matte_degenerate, is_matte_empty

        h, w = 128, 96
        bgr = np.zeros((h, w, 3), dtype=np.uint8)
        bgr[:] = (36, 36, 40)
        yy, xx = np.ogrid[:h, :w]
        cy, cx = h // 2, w // 2
        mask = ((yy - cy) / max(1, h * 0.32)) ** 2 + ((xx - cx) / max(1, w * 0.22)) ** 2 <= 1.0
        bgr[mask] = (170, 150, 130)
        try:
            alpha = None
            for ds in (0.5, 1.0, 0.25):
                self.reset()
                a = self._run_once(self.session, bgr, ds, cold=True)
                if not is_matte_empty(a) and not is_matte_degenerate(a):
                    alpha = a
                    break
            if alpha is None:
                logger.warning(
                    "RVM CPU smoke still empty/slab after rebuild (%s) — "
                    "preview will use heuristic person alpha (no sticky CUDA toast).",
                    self.model_path.name,
                )
            else:
                logger.info(
                    "RVM CPU smoke OK after CUDA→CPU (%s) std=%.3f cover=%.3f",
                    self.model_path.name,
                    float(alpha.std()),
                    float((alpha > 0.15).mean()),
                )
        except Exception as exc:  # noqa: BLE001
            logger.warning("RVM CPU smoke after rebuild failed: %s", exc)

    def _smoke_cuda_or_force_cpu(self) -> None:
        """At load: if CUDA RVM emits empty/gray-slab pha, force CPU-only immediately."""
        from hybrid_editor.media.video_io import is_matte_degenerate, is_matte_empty

        h, w = 128, 96
        bgr = np.zeros((h, w, 3), dtype=np.uint8)
        bgr[:] = (36, 36, 40)
        # Soft person-like ellipse — enough structure for RVM / heuristic.
        yy, xx = np.ogrid[:h, :w]
        cy, cx = h // 2, w // 2
        mask = ((yy - cy) / max(1, h * 0.32)) ** 2 + ((xx - cx) / max(1, w * 0.22)) ** 2 <= 1.0
        bgr[mask] = (170, 150, 130)
        try:
            # Direct CUDA run (skip matte() CPU promote) to decide whether to keep EP.
            alpha = self._run_once(self.session, bgr, 0.5, cold=True)
        except Exception as exc:  # noqa: BLE001
            self._rebuild_cpu_only(
                f"CUDA→CPU: CUDA smoke matte failed ({exc}). "
                "Forcing CPUExecutionProvider only.",
                getattr(self, "_so", None),
            )
            return
        if is_matte_empty(alpha) or is_matte_degenerate(alpha):
            self._rebuild_cpu_only(
                "CUDA→CPU: CUDA smoke matte was gray-slab / empty "
                "(MemcpyTransformer / plugin EP) — CPUExecutionProvider only.",
                getattr(self, "_so", None),
            )

    def reset(self) -> None:
        self._r1 = self._r2 = self._r3 = self._r4 = None
        self._rec_key = None
        self.last_fgr_bgr = None

    def close(self) -> None:
        self.reset()
        self.session = None  # type: ignore
        self._cpu_session = None
        if self._uses_cuda:
            release_cuda("fast-ort")
            self._uses_cuda = False

    @staticmethod
    def _is_expand_broadcast_error(exc: BaseException) -> bool:
        """ORT Expand / broadcast failures from mismatched recurrent spatial dims."""
        msg = str(exc).lower()
        return (
            "expand" in msg
            or "cannot broadcast" in msg
            or "broadcast" in msg
            or ("shape" in msg and ("mismatch" in msg or "incompatible" in msg))
        )

    def _zero_recurrent_feeds(
        self, feeds: dict[str, Any], inputs: dict[str, Any], dtype: np.dtype
    ) -> None:
        """CapCut-safe cold feeds — always 1×1×1×1 (never invent channel/spatial from meta)."""
        z = cold_recurrent(dtype)
        for name in ("r1i", "r2i", "r3i", "r4i"):
            if name in inputs:
                feeds[name] = z.copy()

    def _ensure_cpu_session(self) -> Any:
        """Lazy CPU EP session for CUDA→CPU matte recovery (same ONNX weights)."""
        if self._cpu_session is not None:
            return self._cpu_session
        if self.session is None:
            return None
        try:
            self._cpu_session = self._ort.InferenceSession(
                str(self.model_path),
                sess_options=self._so,
                providers=["CPUExecutionProvider"],
            )
            logger.warning(
                "RVM: created CPU EP fallback session (%s) after bad CUDA pha",
                self.model_path.name,
            )
            return self._cpu_session
        except Exception as exc:  # noqa: BLE001
            logger.warning("RVM CPU fallback session failed: %s", exc)
            return None

    def _promote_cpu(self, note: str) -> None:
        """Switch primary session to CPU-only after CUDA produced a useless matte."""
        if self._ort is not None and getattr(self, "model_path", None) is not None:
            try:
                self._rebuild_cpu_only(note, getattr(self, "_so", None))
                return
            except Exception as exc:  # noqa: BLE001
                logger.warning("RVM CPU rebuild failed (%s) — lazy CPU twin", exc)
        cpu = self._ensure_cpu_session()
        if cpu is None:
            return
        self.session = cpu
        self.provider = "CPUExecutionProvider"
        if self._uses_cuda:
            release_cuda("fast-ort")
            self._uses_cuda = False
        self.fallback_note = note
        self.reset()
        os.environ["HYBRID_ORT_PROVIDER"] = "cpu"
        try:
            from hybrid_editor.cuda_path import set_cuda_ep_probe_cache

            set_cuda_ep_probe_cache(False, note)
        except Exception:  # noqa: BLE001
            pass
        logger.warning("%s", note)

    @staticmethod
    def _rec_feed_safe(rec: Optional[np.ndarray], dtype: np.dtype) -> np.ndarray:
        """Never feed CUDA a stale / non-finite / odd-rank recurrent tensor."""
        z = cold_recurrent(dtype)
        if rec is None:
            return z
        try:
            arr = np.asarray(rec)
            if arr.ndim != 4 or any(int(d) < 1 for d in arr.shape):
                return z
            if not np.isfinite(arr.astype(np.float32, copy=False)).all():
                return z
            return np.ascontiguousarray(arr, dtype=dtype)
        except Exception:  # noqa: BLE001
            return z

    def _extract_pha(
        self, outs: list[Any], session: Any, h: int, w: int
    ) -> np.ndarray:
        """Pull person alpha — CapCut positional fgr,pha,r1.. first; never upscale dust."""
        pha = None
        try:
            out_metas = list(session.get_outputs())
        except Exception:  # noqa: BLE001
            out_metas = []
        names = [str(getattr(m, "name", "") or "").lower() for m in out_metas]
        # CapCut / PeterL1n layout: fgr, pha, r1o, r2o, r3o, r4o
        if (
            len(outs) >= 2
            and len(names) >= 2
            and names[0] in {"fgr", "foreground", ""}
            and names[1] in {"pha", "alpha", "matte", "output_pha", ""}
            and isinstance(outs[1], np.ndarray)
        ):
            pha = outs[1]
        if pha is None:
            for meta, o in zip(out_metas, outs):
                name = str(getattr(meta, "name", "") or "").lower()
                if name in {"pha", "alpha", "matte", "output_pha"} and isinstance(
                    o, np.ndarray
                ):
                    pha = o
                    break
        if pha is None:
            for o in outs:
                if not isinstance(o, np.ndarray) or o.ndim != 4 or o.shape[1] != 1:
                    continue
                # Full-res (or near) C=1 only — skip recurrent grids / 1×1 dust.
                if o.shape[2] >= max(8, h // 4) and o.shape[3] >= max(8, w // 4):
                    pha = o
                    break
        if pha is None:
            pha = outs[1] if len(outs) > 1 else outs[0]

        arr = np.asarray(pha)
        # CapCut: pha[0, 0] when NCHW
        if arr.ndim == 4 and arr.shape[0] >= 1 and arr.shape[1] >= 1:
            alpha = arr[0, 0].astype(np.float32, copy=False)
        else:
            alpha = np.squeeze(arr).astype(np.float32)
            if alpha.ndim == 3:
                alpha = alpha[0]
        if alpha.ndim != 2:
            # Scalar / 1-D garbage (Memcpy / wrong tensor) → empty, not a resized slab.
            return np.zeros((h, w), dtype=np.float32)
        ah, aw = int(alpha.shape[0]), int(alpha.shape[1])
        # Refuse to bilinear-upsample tiny maps to full frame (classic all-ones slab).
        if ah < max(8, h // 8) or aw < max(8, w // 8):
            logger.warning(
                "RVM pha spatial %dx%d too small for src %dx%d — treating as empty",
                aw,
                ah,
                w,
                h,
            )
            return np.zeros((h, w), dtype=np.float32)
        if (ah, aw) != (h, w):
            alpha = cv2.resize(alpha, (w, h), interpolation=cv2.INTER_LINEAR)
        if not np.isfinite(alpha).all():
            alpha = np.nan_to_num(alpha, nan=0.0, posinf=1.0, neginf=0.0)
        return alpha.astype(np.float32, copy=False)

    def _store_recurrent(self, outs: list[Any], dtype: np.dtype) -> None:
        if len(outs) < 6:
            return
        # Named r1o.. when present; else CapCut positional outs[2:6]
        try:
            metas = list(self.session.get_outputs()) if self.session is not None else []
        except Exception:  # noqa: BLE001
            metas = []
        by_name = {
            str(getattr(m, "name", "") or "").lower(): o
            for m, o in zip(metas, outs)
            if isinstance(o, np.ndarray)
        }
        r1 = by_name.get("r1o", outs[2])
        r2 = by_name.get("r2o", outs[3])
        r3 = by_name.get("r3o", outs[4])
        r4 = by_name.get("r4o", outs[5])
        self._r1 = self._rec_feed_safe(r1, dtype)
        self._r2 = self._rec_feed_safe(r2, dtype)
        self._r3 = self._rec_feed_safe(r3, dtype)
        self._r4 = self._rec_feed_safe(r4, dtype)

    def _run_once(
        self,
        session: Any,
        bgr: np.ndarray,
        downsample: float,
        *,
        cold: bool = False,
    ) -> np.ndarray:
        from hybrid_editor.media.video_io import normalize_alpha

        dtype = self.input_dtype
        # BGR→RGB + scale in float32 then cast (matches CapCut multiply path).
        rgb_u8 = np.ascontiguousarray(bgr[:, :, ::-1])
        rgb = rgb_u8.astype(np.float32) * (1.0 / 255.0)
        h, w = int(rgb.shape[0]), int(rgb.shape[1])
        ds = float(downsample) if downsample < 1.0 else 1.0
        ds_key = round(ds, 4)
        rec_key = (h, w, ds_key)
        if cold or (self._rec_key is not None and self._rec_key != rec_key):
            self._r1 = self._r2 = self._r3 = self._r4 = None
        self._rec_key = rec_key

        x = np.ascontiguousarray(np.transpose(rgb, (2, 0, 1))[None, ...], dtype=dtype)
        feeds: dict[str, Any] = {
            "src": x,
            "r1i": self._rec_feed_safe(None if cold else self._r1, dtype),
            "r2i": self._rec_feed_safe(None if cold else self._r2, dtype),
            "r3i": self._rec_feed_safe(None if cold else self._r3, dtype),
            "r4i": self._rec_feed_safe(None if cold else self._r4, dtype),
            "downsample_ratio": np.array([ds], dtype=np.float32),
        }
        # Only feed inputs the graph declares (some exports omit ratio name variants).
        inputs = {i.name: i for i in session.get_inputs()}
        feeds = {k: v for k, v in feeds.items() if k in inputs}
        if "downsample_ratio" in inputs and "downsample_ratio" not in feeds:
            feeds["downsample_ratio"] = np.array([ds], dtype=np.float32)

        try:
            outs = session.run(None, feeds)
        except Exception as exc:  # noqa: BLE001
            if not self._is_expand_broadcast_error(exc):
                raise
            logger.warning(
                "RVM Expand/broadcast at %dx%d ds=%.4f — reset recurrent and retry once: %s",
                h,
                w,
                ds,
                exc,
            )
            self.reset()
            self._rec_key = rec_key
            for name in ("r1i", "r2i", "r3i", "r4i"):
                if name in inputs:
                    feeds[name] = cold_recurrent(dtype)
            outs = session.run(None, feeds)

        alpha = self._extract_pha(outs, session, h, w)
        alpha = normalize_alpha(alpha)
        # peak-cutout: keep last RVM fgr for edge color recover (no extra inference).
        try:
            from hybrid_editor.engines.peak_cutout import extract_fgr_bgr

            self.last_fgr_bgr = extract_fgr_bgr(outs, session, h, w)
        except Exception:  # noqa: BLE001
            self.last_fgr_bgr = None
        # Only keep recurrent when pha looks structured — garbage state poisons the next frame.
        from hybrid_editor.media.video_io import is_matte_degenerate, is_matte_empty

        if not is_matte_empty(alpha) and not is_matte_degenerate(alpha):
            self._store_recurrent(outs, dtype)
        else:
            self._r1 = self._r2 = self._r3 = self._r4 = None
        return alpha

    def matte(
        self,
        bgr: np.ndarray,
        downsample: float = 0.25,
        *,
        prefer_native: bool = False,
    ) -> np.ndarray:
        """Run RVM on one frame.

        Passes **full-resolution** ``src`` + ``downsample_ratio`` (RVM-native), matching
        CapCut Videoeditor ``matting/rvm_onnx.py``. On CUDA all-ones / flat pha (common
        with MemcpyTransformer + fp16), cold-retry then CPU EP (same weights).

        simple-bg4 CPU Gyors: ladder starts at 0.5 (not native 1.0) so we do not burn
        multiple full-res ORT passes on every failed MobileNet frame. Uniform all-ones
        slabs skip the rest of the ds ladder (same garbage at every ratio).
        Never upsamples the src tensor — caller must pass native or downscaled BGR.
        """
        if self.session is None:
            raise RuntimeError("ORT session closed")
        from hybrid_editor.media.video_io import (
            is_matte_degenerate,
            is_matte_empty,
            is_uniform_slab,
        )

        ds0 = float(downsample) if downsample < 1.0 else 1.0
        on_cpu = (not bool(self._uses_cuda)) and ("CPU" in str(self.provider))
        ds_ladder: list[float] = []
        if on_cpu and prefer_native:
            order = (1.0, 0.5, ds0, 0.25)
        elif on_cpu:
            # Gyors/CPU: cheap ratios first — native last (only if needed).
            order = (0.5, ds0, 0.25, 1.0)
        else:
            order = (ds0, 0.5, 1.0, 0.25)
        for d in order:
            dd = float(min(1.0, max(0.125, d)))
            if dd not in ds_ladder:
                ds_ladder.append(dd)

        alpha = self._run_once(self.session, bgr, ds_ladder[0], cold=True)
        if not is_matte_empty(alpha) and not is_matte_degenerate(alpha):
            return alpha
        # Uniform gray slab is independent of downsample — don't burn CPU on retries.
        if is_uniform_slab(alpha):
            logger.warning(
                "RVM pha uniform slab on %s — skip ds ladder (alternate/chroma next)",
                self.provider,
            )
            return alpha

        # Cold recurrent retry on the active provider (stale r1–r4 → slab / empty).
        logger.warning(
            "RVM pha useless on %s (empty/degenerate) — cold-start retry",
            self.provider,
        )
        for ds in ds_ladder[1:]:
            self.reset()
            alpha = self._run_once(self.session, bgr, ds, cold=True)
            if not is_matte_empty(alpha) and not is_matte_degenerate(alpha):
                return alpha
            if is_uniform_slab(alpha):
                return alpha

        # CUDA MemcpyTransformer / fp16 path → CPU EP (known-good for PeterL1n export).
        cuda_active = self._uses_cuda or "CUDA" in str(self.provider)
        if cuda_active:
            cpu = self._ensure_cpu_session()
            if cpu is not None:
                logger.warning(
                    "RVM CUDA pha still useless — CPU EP retry (%s)",
                    self.model_path.name,
                )
                cpu_ladder: list[float] = []
                for d in (0.5, ds0, 0.25, 1.0):
                    dd = float(min(1.0, max(0.125, d)))
                    if dd not in cpu_ladder:
                        cpu_ladder.append(dd)
                for ds in cpu_ladder:
                    self.reset()
                    alpha_cpu = self._run_once(cpu, bgr, ds, cold=True)
                    if not is_matte_empty(alpha_cpu) and not is_matte_degenerate(alpha_cpu):
                        self._promote_cpu(
                            "CUDA→CPU: RVM pha was uniform/empty on CUDA EP "
                            "(MemcpyTransformer / fp16) — using CPUExecutionProvider for mattes."
                        )
                        return alpha_cpu
                    alpha = alpha_cpu
                    if is_uniform_slab(alpha_cpu):
                        break

        return alpha


class FastEngine(MattingEngine):
    mode = EngineMode.GYORS

    def __init__(self, *, prefer_quality: bool = False) -> None:
        self._media: Optional[MediaInfo] = None
        self._rvm: Optional[_OrtRvmSession] = None
        self._backend = "heuristic"
        self._status_note: Optional[str] = None
        self._mask_store: Optional[MaskStore] = None
        self._frame_cache = FrameCache(48)
        self._prefetch = ScrubPrefetcher(ahead=8)
        self._lanes: Optional[ProxyLaneCache] = None
        self._last_frame_idx = 0
        # preview-fast: CPU scrub proxy ~480 (was 720) — Előnézet must feel instant.
        try:
            self._proxy_long = int(os.environ.get("HYBRID_PROXY_LONG", "480") or "480")
        except ValueError:
            self._proxy_long = 480
        self._proxy_long = max(320, min(960, self._proxy_long))
        # Gyors scrub: MobileNet + low ds. Max backbone: ResNet when available.
        # Max bake defaults to FULL-RES RVM (ds=1.0) — 768 long was leaving residual BG islands.
        self._prefer_quality = bool(prefer_quality)
        self._matte_downsample = 0.40 if self._prefer_quality else 0.25
        # Preview may use a long-side cap; bake sets full_res_matte=True → ds=1.0.
        self._matte_target_long = 1080 if self._prefer_quality else 480
        self._full_res_matte = False
        if self._prefer_quality:
            env_long = os.environ.get("HYBRID_MAX_RVM_LONG", "").strip().lower()
            if env_long in {"0", "full", "native", "1.0", "fullres"}:
                self._full_res_matte = True
                self._matte_target_long = 10**9
            elif env_long.isdigit():
                self._matte_target_long = max(480, int(env_long))
            else:
                # Default Max: full-res inference (RTX 3060 handles 1080p ResNet).
                self._full_res_matte = True
                self._matte_target_long = 10**9
        self._load_rvm()

    def set_full_res_matte(self, enabled: bool = True) -> None:
        """Max bake: force native-resolution RVM (no long-side downsample)."""
        was = bool(getattr(self, "_full_res_matte", False))
        self._full_res_matte = bool(enabled)
        if self._full_res_matte:
            self._matte_target_long = 10**9
        elif self._prefer_quality:
            self._matte_target_long = 1080
        # Preview↔full-res switches change RVM internal spatial size — drop recurrent.
        if was != self._full_res_matte and self._rvm is not None:
            self._rvm.reset()

    def _on_cpu_ort(self) -> bool:
        """True when live RVM session is CPU (or heuristic) — not CUDA EP."""
        if self._rvm is None:
            return True
        if bool(getattr(self._rvm, "_uses_cuda", False)):
            return False
        return "CPU" in str(getattr(self._rvm, "provider", "CPU") or "CPU")

    def _gyors_bake_proxy(self) -> tuple[bool, int]:
        """CPU Gyors bake: downscale BGR before ORT (full-res src was ~2s/frame).

        Root cause of ~8 min / 10s@1080p24: ``bake()`` fed native 1080p ``src`` into
        CPU MobileNet every frame (downsample_ratio alone still ships a huge tensor).
        Mirror Max CPU fast-path: long-side 480–720 (default 640), soft pha unchanged.

        Opt out: ``HYBRID_GYORS_BAKE_FULLRES=1``. Tune: ``HYBRID_GYORS_BAKE_LONG``.
        CUDA EP (probe OK) keeps native decode — GPU bandwidth handles 1080p.
        """
        raw = (os.environ.get("HYBRID_GYORS_BAKE_FULLRES") or "").strip().lower()
        if raw in {"1", "true", "yes", "full", "fullres"}:
            return False, 10**9
        prefer = (os.environ.get("HYBRID_ORT_PROVIDER") or "cpu").strip().lower()
        force_cpu_env = prefer in {"cpu", "cpuexecutionprovider", ""}
        if not force_cpu_env and not self._on_cpu_ort():
            return False, 10**9
        try:
            bake_long = int(os.environ.get("HYBRID_GYORS_BAKE_LONG", "640") or "640")
        except ValueError:
            bake_long = 640
        bake_long = max(480, min(720, bake_long))
        return True, bake_long

    def _load_rvm(self) -> None:
        prefer = "quality" if self._prefer_quality else "fast"
        model = resolve_rvm_onnx(prefer=prefer)
        if model is None:
            self._backend = "heuristic"
            self._status_note = HEURISTIC_NOTE
            logger.info(HEURISTIC_NOTE)
            return
        try:
            self._rvm = _OrtRvmSession(model)
            self._backend = f"ort-rvm:{self._rvm.provider}"
            note = getattr(self._rvm, "fallback_note", None)
            self._status_note = note
            if note:
                logger.warning("FastEngine ORT RVM loaded with fallback: %s (%s)", model, note)
            else:
                logger.info("FastEngine ORT RVM loaded: %s (%s)", model, self._rvm.provider)
            # simple-bg2: always prove CPU/ORT person matte at load (not only after CUDA→CPU).
            # If smoke is empty/slab, keep session — preview_frame heuristic still recovers.
            try:
                if "CPU" in str(getattr(self._rvm, "provider", "")):
                    self._rvm._verify_cpu_matte_after_rebuild()  # noqa: SLF001
            except Exception as smoke_exc:  # noqa: BLE001
                logger.warning("RVM CPU load smoke skipped: %s", smoke_exc)
        except Exception as exc:  # noqa: BLE001
            from hybrid_editor.cuda_path import brief_ort_error, is_cudnn_or_cuda_ep_error

            brief = brief_ort_error(exc)
            if is_cudnn_or_cuda_ep_error(exc):
                msg = (
                    f"ORT CUDA/cuDNN failed ({brief}) — falling back to heuristic. "
                    "Install nvidia-cudnn-cu12 in hybrid .venv, run .\\start_hybrid_cuda.ps1, "
                    "or $env:HYBRID_REUSE_PARENT_VENV='1' after CapCut remount_ort_gpu.ps1."
                )
            else:
                msg = f"ORT RVM unavailable ({brief}) — {HEURISTIC_NOTE}"
            logger.warning("%s", msg)
            self._rvm = None
            self._backend = "heuristic"
            self._status_note = msg

    def capabilities(self) -> EngineCapabilities:
        # Live provider (CUDA→CPU promote must not keep advertising CUDA).
        if self._rvm is not None:
            live = str(getattr(self._rvm, "provider", "") or "")
            if live:
                self._backend = f"ort-rvm:{live}"
            note = getattr(self._rvm, "fallback_note", None)
            if note:
                self._status_note = note
        detail = (
            f"ORT RVM via HYBRID_RVM_ONNX / parent Videoeditor models/ "
            f"/ models/*.onnx ({self._backend})."
            if self._rvm
            else HEURISTIC_NOTE
        )
        note = getattr(self, "_status_note", None)
        if note:
            detail = f"{detail} {note}" if self._rvm else note
        name = (
            "Max minőségű RVM (ResNet preferált)"
            if self._prefer_quality
            else "Gyors mód (RVM / Fast · lágyebb scrub)"
        )
        return EngineCapabilities(
            mode=self.mode,
            name=name,
            backend=self._backend,
            available=True,
            license_note="RVM ONNX: follow upstream license; heuristic fallback is ours (MIT).",
            vram_hint_gb=3.5 if self._rvm and "CUDA" in self._backend and self._prefer_quality else (
                3.0 if self._rvm and "CUDA" in self._backend else 0.5
            ),
            detail=detail,
            weights_path=str(self._rvm.model_path) if self._rvm else None,
        )

    def reset(self) -> None:
        if self._rvm:
            self._rvm.reset()

    def close(self) -> None:
        self._prefetch.shutdown()
        self._frame_cache.clear()
        if self._lanes:
            self._lanes.cancel_cold()
            self._lanes.clear()
        if self._mask_store:
            self._mask_store.clear_memory()
        if self._rvm:
            self._rvm.close()
            self._rvm = None

    def open_media(self, path: Path) -> MediaInfo:
        self.reset()
        self._frame_cache.clear()
        if self._lanes:
            self._lanes.cancel_cold()
            self._lanes.clear()
        self._media = probe_video(path)
        store_dir = mask_dir(ROOT, self._media.path, subject="person")
        model_id = Path(self._rvm.model_path).stem if self._rvm else "heuristic"
        self._mask_store = MaskStore(store_dir, model_id=model_id)
        # Drop wand-era / face-only disk caches so Gyors/Max never skip ORT
        # with a poisoned part-matte (person-restore).
        self._mask_store.purge()
        cold = ROOT / "cache" / "proxy" / Path(self._media.path).stem
        self._lanes = ProxyLaneCache(
            hot_size=12,
            warm_size=48,
            cold_dir=cold,
            max_long=self._proxy_long,
        )
        self._prefetch.bind(
            self._decode_proxy_idx,
            frame_count=self._media.frame_count,
            max_long=self._proxy_long,
        )
        # Non-blocking COLD lane encode (sparse) — never blocks UI
        self._lanes.start_cold_encode(
            read_fn=lambda i: self._decode_proxy_idx(i, self._proxy_long),
            frame_count=self._media.frame_count,
            stride=max(1, int(round((self._media.fps or 25.0) / 4.0))),
        )
        return self._media

    def _decode_proxy_idx(self, frame_idx: int, max_long: int) -> Optional[np.ndarray]:
        if self._media is None:
            return None
        idx = int(frame_idx)
        if self._lanes is not None:
            hit = self._lanes.get(idx)
            if hit is not None:
                return hit
        key = (self._media.path, idx, int(max_long))
        hit = self._frame_cache.get(key)
        if hit is not None:
            if self._lanes is not None:
                self._lanes.put(idx, hit, lane=Lane.WARM)
            return hit
        raw = read_frame_index(Path(self._media.path), idx)
        if raw is None:
            return None
        proxy = downscale_long_side(raw, max_long)
        self._frame_cache.put(key, proxy)
        if self._lanes is not None:
            self._lanes.put(idx, proxy, lane=Lane.WARM)
        return proxy

    def _downsample_for(self, bgr: np.ndarray) -> float:
        """RVM downsample ratio — PeterL1n 256–512 guidance + full-body bias.

        Max bake / prefer_quality with full_res_matte → 1.0 (native).
        On CPU ORT after CUDA→CPU, prefer a higher ratio — MobileNet at 0.25
        often emits empty pha while 0.5–1.0 yields a real silhouette.
        """
        if getattr(self, "_full_res_matte", False):
            return 1.0
        h, w = bgr.shape[:2]
        from hybrid_editor.engines.peak_cutout import rvm_auto_downsample_ratio

        # Map long-side target into PeterL1n auto ratio (full-body default).
        try:
            target = float(self._matte_target_long)
        except Exception:
            target = 480.0
        if target >= 10**8:
            return 1.0
        # Clamp target into official 256–512 band for stage-1.
        target_clamped = float(min(512.0, max(256.0, min(target, 512.0))))
        if getattr(self, "_prefer_quality", False):
            target_clamped = min(512.0, max(target_clamped, 432.0))
        ds = rvm_auto_downsample_ratio(h, w, full_body=True, target_long=target_clamped)
        on_cpu = False
        if self._rvm is not None:
            on_cpu = (not bool(getattr(self._rvm, "_uses_cuda", False))) and (
                "CPU" in str(getattr(self._rvm, "provider", ""))
            )
        if on_cpu:
            # PeterL1n: 0.25 @1080 is correct; forcing 0.5+ made CPU Gyors crawl.
            # Allow override; default stays at official auto ratio (no floor).
            try:
                min_ds = float(os.environ.get("HYBRID_CPU_RVM_MIN_DS", "0") or "0")
            except ValueError:
                min_ds = 0.0
            if min_ds > 0:
                ds = float(min(1.0, max(ds, min_ds)))
        return ds

    def _iter_alternate_rvm_paths(self) -> list[Path]:
        """Other RVM ONNX weights to try when the active model slabs/empties.

        simple-bg3: MobileNet on some 1080p close-ups emits empty/flat pha on CPU;
        ResNet fp32 often recovers (and vice versa). Prefer ResNet fp32 next.
        """
        current: Optional[Path] = None
        if self._rvm is not None and getattr(self._rvm, "model_path", None):
            current = Path(self._rvm.model_path)
        cur_key = str(current.resolve()) if current and current.is_file() else ""
        # Prefer quality (ResNet) when primary was MobileNet / empty.
        prefer = "quality"
        if current is not None and "resnet" in current.name.lower():
            prefer = "fast"
        found: list[Path] = []
        seen: set[str] = set()
        # Explicit twin names first (fp32 before fp16).
        twin_names = (
            (
                "rvm_resnet50_fp32.onnx",
                "rvm_resnet50.onnx",
                "rvm_resnet50_fp16.onnx",
                "rvm_mobilenetv3_fp32.onnx",
                "rvm_mobilenetv3.onnx",
                "rvm_mobilenetv3_fp16.onnx",
            )
            if prefer == "quality"
            else (
                "rvm_mobilenetv3_fp32.onnx",
                "rvm_mobilenetv3.onnx",
                "rvm_mobilenetv3_fp16.onnx",
                "rvm_resnet50_fp32.onnx",
                "rvm_resnet50.onnx",
                "rvm_resnet50_fp16.onnx",
            )
        )
        search_dirs: list[Path] = [ROOT / "models"]
        for r in parent_videoeditor_roots():
            search_dirs.append(r / "models")
        for d in search_dirs:
            if not d.is_dir():
                continue
            for name in twin_names:
                cand = d / name
                if not cand.is_file():
                    continue
                key = str(cand.resolve())
                if key == cur_key or key in seen:
                    continue
                seen.add(key)
                found.append(cand)
            for cand in sorted(d.glob("rvm_*.onnx")):
                key = str(cand.resolve())
                if key == cur_key or key in seen:
                    continue
                seen.add(key)
                found.append(cand)
        return found

    def _try_alternate_rvm(self, bgr: np.ndarray) -> Optional[np.ndarray]:
        """Load next RVM ONNX on CPU; promote it if pha is non-empty (OSS trust)."""
        from hybrid_editor.media.video_io import is_matte_degenerate

        ds = self._downsample_for(bgr)
        # Gyors / OSS: never force native full-res on alternate (CPU cost bomb).
        prefer_native = bool(getattr(self, "_full_res_matte", False))
        for alt in self._iter_alternate_rvm_paths():
            sess: Optional[_OrtRvmSession] = None
            try:
                # Force CPU for alternate — user already on CPU when primary failed.
                prev = os.environ.get("HYBRID_ORT_PROVIDER")
                os.environ["HYBRID_ORT_PROVIDER"] = "cpu"
                try:
                    sess = _OrtRvmSession(alt)
                finally:
                    if prev is not None:
                        os.environ["HYBRID_ORT_PROVIDER"] = prev
                    else:
                        os.environ.pop("HYBRID_ORT_PROVIDER", None)
                alpha = sess.matte(bgr, downsample=ds, prefer_native=prefer_native)
                # PeterL1n / rembg: soft MobileNet pha is valid — do not good_enough-gate.
                if is_matte_empty(alpha) or is_matte_degenerate(alpha):
                    logger.warning(
                        "Alternate RVM %s still empty/slab — trying next",
                        alt.name,
                    )
                    sess.close()
                    continue
                # Promote successful alternate (esp. ResNet fp32 after MobileNet slab).
                old = self._rvm
                self._rvm = sess
                self._backend = f"ort-rvm:{sess.provider}"
                self._status_note = (
                    f"RVM auto-switch → {alt.name} (CPU) — prior model empty/slab"
                )
                logger.warning(
                    "RVM auto-switch: %s → %s (usable person matte on CPU)",
                    Path(old.model_path).name if old else "none",
                    alt.name,
                )
                if old is not None:
                    try:
                        old.close()
                    except Exception:  # noqa: BLE001
                        pass
                return alpha
            except Exception as exc:  # noqa: BLE001
                logger.warning("Alternate RVM %s failed: %s", alt.name, exc)
                if sess is not None:
                    try:
                        sess.close()
                    except Exception:  # noqa: BLE001
                        pass
        return None

    def _matte(self, bgr: np.ndarray) -> np.ndarray:
        """Person alpha — OSS-simple path (PeterL1n RVM / rembg default).

        Official RVM: model(src, *rec, ds) → pha; compose fgr*pha. No crush ladder,
        no good_enough reject of soft MobileNet, no hard_person on the happy path.
        rembg: session.predict → naive_cutout; alpha_matting/post only if requested.

        HybridCut restore-rvm: trust non-empty, non-degenerate pha. Ladder only when
        ORT returns empty/slab. hard_person_alpha is last-resort for gray-slab UI only.
        """
        from hybrid_editor.media.video_io import (
            is_matte_degenerate,
            matte_failure_reason,
        )

        # Preview / Gyors: never prefer_native (full-frame CPU ORT). Max bake sets flag.
        prefer_native = bool(getattr(self, "_full_res_matte", False))
        alpha: Optional[np.ndarray] = None
        if self._rvm is not None:
            try:
                alpha = self._rvm.matte(
                    bgr,
                    downsample=self._downsample_for(bgr),
                    prefer_native=prefer_native,
                )
            except Exception as exc:  # noqa: BLE001
                logger.warning("RVM matte failed — trying alternate / chroma / heuristic: %s", exc)
                alpha = None
        if alpha is not None and not is_matte_empty(alpha) and not is_matte_degenerate(alpha):
            # Soft pha is the product (RVM paper / rembg naive_cutout).
            return alpha
        if alpha is not None:
            why = matte_failure_reason(alpha) or "empty"
            kind = "degenerate slab" if is_matte_degenerate(alpha) else "empty"
            logger.warning(
                "RVM returned %s matte on %s (%s) — alternate / chroma / heuristic",
                kind,
                self._backend,
                why,
            )
        alt = self._try_alternate_rvm(bgr)
        if alt is not None and not is_matte_empty(alt) and not is_matte_degenerate(alt):
            return alt
        chroma = solid_bg_person_alpha(bgr)
        if not is_matte_empty(chroma) and not is_matte_degenerate(chroma):
            self._status_note = (
                (self._status_note + " · " if self._status_note else "")
                + "solid-BG chroma fallback (blue/green screen)"
            )
            logger.warning("RVM empty/slab — solid-BG chroma person matte recovered")
            return chroma
        heur = heuristic_person_alpha(bgr)
        if not is_matte_empty(heur) and not is_matte_degenerate(heur):
            return heur
        # Last resort only — never run on soft MobileNet that already had a person.
        hard = hard_person_alpha(bgr)
        self._status_note = (
            (self._status_note + " · " if self._status_note else "")
            + "hard person salvage (CPU ladder)"
        )
        logger.warning("RVM/chroma empty — hard_person_alpha salvage for visible Cutout")
        return hard

    def preview_frame(self, t_sec: float) -> PreviewFrame:
        """Gyors Előnézet — OSS-fast: proxy decode → one RVM → encode soft pha.

        Mirrors PeterL1n inference.py / rembg remove(default): no crush, no boost,
        no sliver wipe of soft mattes. Salvage only when pha is empty/degenerate.
        """
        if self._media is None:
            raise RuntimeError("No media open")
        fps = self._media.fps or 25.0
        frame_idx = int(round(max(0.0, t_sec) * fps))
        direction = 1 if frame_idx >= self._last_frame_idx else -1
        self._last_frame_idx = frame_idx
        self._prefetch.nudge(frame_idx, direction=direction, max_long=self._proxy_long)

        # Prefer proxy-sized decode from HOT/WARM/COLD lanes (~480 long, RVM~512 band)
        bgr = self._decode_proxy_idx(frame_idx, self._proxy_long)
        if bgr is not None and self._lanes is not None:
            self._lanes.put(frame_idx, bgr, lane=Lane.HOT)
        if bgr is None:
            if self._rvm:
                self._rvm.reset()
            bgr, t = read_frame_at(Path(self._media.path), t_sec)
        else:
            t = min(t_sec, self._media.duration_sec)

        # After CUDA→CPU rebuild: drop any gray-slab MaskStore / force re-infer.
        if self._rvm is not None and getattr(self._rvm, "_masks_stale", False):
            if self._mask_store is not None:
                try:
                    self._mask_store.purge()
                except Exception:  # noqa: BLE001
                    self._mask_store.clear_memory()
            self._rvm._masks_stale = False  # noqa: SLF001
            logger.info("MaskStore purged after CUDA→CPU — forcing fresh CPU/heuristic infer")

        alpha = None
        from_store = False
        matte_error: Optional[str] = None
        recovered = False
        from hybrid_editor.media.video_io import is_matte_degenerate

        if self._mask_store is not None:
            cached = self._mask_store.get_alpha(t, shape=bgr.shape[:2])
            if (
                cached is not None
                and not is_matte_empty(cached)
                and not is_matte_degenerate(cached)
            ):
                alpha = cached
                from_store = True
            elif cached is not None and (
                is_matte_degenerate(cached) or is_matte_empty(cached)
            ):
                try:
                    self._mask_store.purge()
                except Exception:  # noqa: BLE001
                    self._mask_store.clear_memory()
        if alpha is None:
            if self._rvm:
                self._rvm.reset()  # seek: don't smear recurrent state
            try:
                alpha = self._matte(bgr)
                if (
                    self._mask_store is not None
                    and not is_matte_empty(alpha)
                    and not is_matte_degenerate(alpha)
                ):
                    self._mask_store.put_async(t, alpha)
            except Exception as exc:  # noqa: BLE001
                matte_error = str(exc)[:240]
                logger.warning("preview matte failed — heuristic fallback: %s", matte_error)
                try:
                    alpha = heuristic_person_alpha(bgr)
                    if not is_matte_empty(alpha) and not is_matte_degenerate(alpha):
                        matte_error = None
                        recovered = True
                    if (
                        self._mask_store is not None
                        and not is_matte_empty(alpha)
                        and not is_matte_degenerate(alpha)
                    ):
                        self._mask_store.put_async(t, alpha)
                except Exception as exc2:  # noqa: BLE001
                    matte_error = f"{matte_error}; heuristic: {str(exc2)[:120]}"
                    alpha = np.zeros(bgr.shape[:2], dtype=np.float32)

        from hybrid_editor.media.video_io import matte_failure_reason

        # Only salvage true empty/slab — never replace soft MobileNet with GrabCut.
        if alpha is None or is_matte_empty(alpha) or is_matte_degenerate(alpha):
            try:
                salvaged = hard_person_alpha(bgr)
                if not is_matte_empty(salvaged) and not is_matte_degenerate(salvaged):
                    alpha = salvaged
                    matte_error = None
                    recovered = True
                    logger.warning("preview hard salvage replaced empty/slab matte")
            except Exception as salvage_exc:  # noqa: BLE001
                logger.warning("preview hard salvage failed: %s", salvage_exc)
        if alpha is not None and is_matte_empty(alpha) and matte_error is None:
            matte_error = matte_failure_reason(alpha)
        infer_h, infer_w = int(bgr.shape[0]), int(bgr.shape[1])
        # OSS: encode soft pha as-is (no preview_boost, no crush).
        try:
            jpg, png, w, h, src, empty = encode_preview_pair(bgr, alpha)
        except Exception as exc:  # noqa: BLE001
            logger.warning("preview encode failed — source-only: %s", exc)
            jpg, png, w, h, src, empty = encode_source_only_preview(bgr)
            matte_error = matte_error or str(exc)[:240]
            empty = True
        if empty or alpha is None or is_matte_empty(alpha):
            try:
                forced = hard_person_alpha(bgr)
                if not is_matte_empty(forced) and not is_matte_degenerate(forced):
                    alpha = forced
                    jpg, png, w, h, src, empty = encode_preview_pair(bgr, forced)
                    matte_error = None
                    recovered = True
                    logger.warning("preview restore-rvm: forced hard_person after empty encode")
            except Exception as force_exc:  # noqa: BLE001
                logger.warning("preview force salvage failed: %s", force_exc)
        if empty or is_matte_empty(alpha):
            empty = True
            if matte_error is None and alpha is not None:
                matte_error = matte_failure_reason(alpha)
        else:
            matte_error = None
            recovered = True
        # Optional diag (HYBRID_DIAG_MATTE / HYBRID_DIAG_ALPHA_DUMP) — off by default.
        try:
            from hybrid_editor.diag_matte import log_matte_trigger, maybe_dump_alpha_pair

            log_matte_trigger(
                where="FastEngine.preview_frame",
                t_sec=t,
                matte_error=matte_error,
                matte_empty=bool(empty),
                recovered=bool(recovered and not empty),
                alpha=alpha,
                extra={
                    "from_store": from_store,
                    "backend": self._backend,
                    "infer_wh": [infer_w, infer_h],
                },
            )
            if empty or matte_error:
                maybe_dump_alpha_pair(
                    tag="gyors_preview",
                    t_sec=t,
                    raw_alpha=alpha,
                    post_alpha=None,
                )
        except Exception:  # noqa: BLE001
            pass
        lane_meta = self._lanes.status() if self._lanes else {}
        src_w = int(self._media.width) if self._media else infer_w
        src_h = int(self._media.height) if self._media else infer_h
        meta: dict[str, Any] = {
            "mode": self.mode.value,
            "mask_store": from_store,
            "prefetch_ahead": 8,
            "frame_idx": frame_idx,
            "proxy_lanes": lane_meta,
            "matte_empty": empty,
            "matte_recovered": bool(recovered and not empty),
            "preview_boost": False,
            "oss_fast_matte": True,
            "source_width": src_w,
            "source_height": src_h,
            "infer_width": infer_w,
            "infer_height": infer_h,
            "stamp": "2026-10-14-restore-rvm-fast",
        }
        if matte_error and empty:
            meta["matte_error"] = matte_error
            meta["source_fallback"] = True
        note = getattr(self, "_status_note", None) or (
            getattr(self._rvm, "fallback_note", None) if self._rvm else None
        )
        if note:
            meta["cuda_fallback"] = note
        return PreviewFrame(
            t_sec=t,
            width=w,
            height=h,
            jpeg_b64=jpg,
            alpha_png_b64=png,
            engine="FastEngine",
            backend=self._backend,
            meta=meta,
            source_jpeg_b64=src,
        )

    def bake(
        self,
        out_dir: Path,
        *,
        max_frames: Optional[int] = None,
        progress: Optional[ProgressCb] = None,
        in_sec: float = 0.0,
        out_sec: Optional[float] = None,
    ) -> BakeResult:
        if self._media is None:
            raise RuntimeError("No media open")
        out_dir = Path(out_dir)
        from hybrid_editor.export.bgcut import alpha_dump_dir, dump_alpha_frames_enabled
        from hybrid_editor.diag_matte import ExportStageTimer

        dump_alpha = dump_alpha_frames_enabled()
        alpha_dir = alpha_dump_dir(out_dir) if dump_alpha else None
        if alpha_dir is not None:
            alpha_dir.mkdir(parents=True, exist_ok=True)
        timer = ExportStageTimer("FastEngine.bake")
        self.reset()
        path = Path(self._media.path)
        fps = self._media.fps or 25.0
        start_t = max(0.0, float(in_sec))
        end_t = float(out_sec) if out_sec is not None and out_sec > 0 else self._media.duration_sec
        end_t = max(start_t, end_t)

        # CPU Gyors: matte at long-side ~640 (not full 1080p src). Soft pha kept.
        cpu_fast, bake_long = self._gyors_bake_proxy()
        if cpu_fast:
            self.set_full_res_matte(False)
            self._matte_target_long = bake_long
            logger.warning(
                "CPU Gyors bake fast-path: MobileNet long=%d (was full-res src ~2s/frame; "
                "set HYBRID_GYORS_BAKE_FULLRES=1 to restore slow path)",
                bake_long,
            )

        cap = cv2.VideoCapture(str(path))
        if not cap.isOpened():
            raise RuntimeError(f"Cannot open {path}")
        # Seek to in point
        cap.set(cv2.CAP_PROP_POS_MSEC, start_t * 1000.0)
        written = 0
        limit = max_frames if max_frames is not None else 10**9
        if limit <= 0:
            limit = 10**9
        total_est = int(max(1, round((end_t - start_t) * fps)))
        try:
            n_cont = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
            if n_cont > 0 and fps > 1e-6:
                i0 = int(max(0, round(start_t * fps)))
                i1 = int(min(n_cont, max(i0 + 1, round(end_t * fps))))
                total_est = max(1, i1 - i0)
        except Exception:
            pass
        if max_frames is not None:
            total_est = min(total_est, max_frames)
        frames_bgr: list[np.ndarray] = []
        frames_alpha: list[np.ndarray] = []
        frames_bgra: list[np.ndarray] = []
        timer.mark("seek_open")
        try:
            idx = 0
            while written < limit:
                ok, bgr = cap.read()
                if not ok or bgr is None:
                    break
                cur_t = start_t + (idx / fps)
                if cur_t > end_t + 1e-6:
                    break
                # Downscale BEFORE ORT on CPU — do not feed 1080p float src.
                if cpu_fast:
                    bgr_m = downscale_long_side(bgr, bake_long)
                else:
                    bgr_m = bgr
                # Soft RVM pha only — no apex polish / no matte-safe crush.
                alpha = self._matte(bgr_m)
                a8 = (np.clip(alpha, 0, 1) * 255).astype(np.uint8)
                if alpha_dir is not None:
                    cv2.imwrite(str(alpha_dir / f"{idx:06d}.png"), a8)
                # Skip MaskStore PNG thrash during bake (scrub cache is for preview).
                # Keep proxy-sized frames for preview mp4 (memory-safe)
                proxy_long = int(bake_long) if cpu_fast else 720
                proxy = downscale_long_side(bgr_m, proxy_long)
                a_p = cv2.resize(
                    alpha, (proxy.shape[1], proxy.shape[0]), interpolation=cv2.INTER_LINEAR
                )
                frames_bgr.append(proxy)
                frames_alpha.append(a_p)
                a3 = (a_p * 255).astype(np.uint8)
                bgra = cv2.cvtColor(proxy, cv2.COLOR_BGR2BGRA)
                bgra[:, :, 3] = a3
                frames_bgra.append(bgra)
                written += 1
                idx += 1
                if written > total_est:
                    total_est = written
                if progress:
                    pct = min(0.85, written / max(total_est, 1))
                    tag = f"Gyors~{bake_long}" if cpu_fast else "Gyors bake"
                    progress(pct, f"{tag} {written}/{total_est} frame")
        finally:
            cap.release()
        timer.mark("matte_loop")

        preview_mp4 = None
        prores = None
        audio_ok = False
        if written:
            if progress:
                progress(0.9, "Export preview.mp4 + audio…")
            audio_segs = [
                AudioSegment(
                    path=str(path),
                    in_sec=start_t,
                    out_sec=end_t,
                    timeline_start_sec=0.0,
                )
            ]
            preview_mp4 = write_preview_mp4(
                frames_bgr,
                frames_alpha,
                out_dir / "preview.mp4",
                fps=fps,
                audio_segments=audio_segs,
                audio_duration_sec=end_t - start_t,
            )
            audio_ok = bool(preview_mp4) and media_has_audio(preview_mp4)
            timer.mark("preview_mp4")
            if progress:
                progress(0.95, "Export C:\\bgcut *_full_nobg.mov…")
            # Always write Videoeditor-style alpha MOV (ProRes → qtrle fallback).
            prores, companion = finalize_bgcut_exports(
                media_stem=path.stem,
                out_dir=out_dir,
                preview_mp4=preview_mp4,
                frames_bgra=frames_bgra,
                fps=fps,
            )
            timer.mark("prores_mov")
            if companion:
                preview_mp4 = companion
            if progress:
                progress(1.0, "Bake kész")
        timing = timer.finish()

        audio_note = " · audio AAC" if audio_ok else ""
        mov_note = f" · {prores}" if prores else " · HIÁNYZIK: *_full_nobg.mov"
        dur_note = f" · {end_t - start_t:.2f}s / {written} frame"
        cpu_note = f" · CPU Gyors@{bake_long}" if cpu_fast else ""
        ok = written > 0 and bool(prores)
        msg_core = (
            f"Kész: {Path(prores).name}" if prores else "SIKERTELEN: nincs *_full_nobg.mov (ffmpeg?)"
        )
        bake_range = {
            "in_sec": start_t,
            "out_sec": end_t,
            "audio": audio_ok,
            "duration_sec": end_t - start_t,
            "max_frames_cap": max_frames,
            "mov_path": prores,
            "cpu_gyors_fast": bool(cpu_fast),
            "gyors_bake_long": bake_long if cpu_fast else None,
            "soft_alpha": True,
            "mask_store_bake": False,
        }
        if timing:
            bake_range["diag_timing"] = timing
        return BakeResult(
            ok=ok,
            out_dir=str(out_dir.resolve()),
            frames_written=written,
            engine="FastEngine",
            backend=self._backend,
            message=(
                f"{msg_core}{audio_note}{mov_note}{dur_note}{cpu_note} ({self._backend})"
            ),
            alpha_preview=(
                str(alpha_dir / "000000.png") if alpha_dir is not None and written else None
            ),
            preview_mp4=preview_mp4,
            prores_mov=prores,
            bake_range=bake_range,
        )
