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
    media_has_audio,
    try_prores_alpha,
    write_preview_mp4,
)
from hybrid_editor.media.video_io import (
    downscale_long_side,
    encode_preview_pair,
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


# Prefer fp32 first (fewer ORT dtype / CUDA edge cases). Override with HYBRID_RVM_ONNX.
_RVM_NAMES = (
    "rvm_mobilenetv3_fp32.onnx",
    "rvm_mobilenetv3.onnx",
    "rvm_mobilenetv3_fp16.onnx",
    "rvm_resnet50_fp32.onnx",
    "rvm_resnet50_fp16.onnx",
)


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


def _first_rvm_in_dir(models_dir: Path) -> Optional[Path]:
    if not models_dir.is_dir():
        return None
    for name in _RVM_NAMES:
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


def resolve_rvm_onnx() -> Optional[Path]:
    """Locate RVM ONNX: env → hybrid models/ → parent Videoeditor models/ → USERPROFILE.

    Does not download or redistribute weights. Parent CapCut tree often already has
    ``Documents\\Videoeditor\\models\\rvm_*.onnx`` from the Tk cutout app.
    """
    for env_name in ("HYBRID_RVM_ONNX", "VIDEOEDITOR_RVM_ONNX"):
        model = _env_path(env_name)
        if model is not None:
            return model

    for dir_env in ("HYBRID_MODELS_DIR", "VIDEOEDITOR_MODELS", "VIDEOEDITOR_MODELS_DIR"):
        d = _env_dir(dir_env)
        if d is not None:
            hit = _first_rvm_in_dir(d)
            if hit is not None:
                return hit

    hit = _first_rvm_in_dir(ROOT / "models")
    if hit is not None:
        return hit

    for root in parent_videoeditor_roots():
        hit = _first_rvm_in_dir(root / "models")
        if hit is not None:
            return hit

    return None


def probe_ort_runtime() -> dict[str, Any]:
    """Lightweight ORT / CUDA EP probe for UI status chips (no session load)."""
    try:
        from hybrid_editor.cuda_path import inject_nvidia_pip_libs, pip_cudnn_present

        inject_nvidia_pip_libs()
        cudnn_ok, cudnn_detail = pip_cudnn_present()
    except Exception as exc:  # noqa: BLE001
        cudnn_ok, cudnn_detail = False, f"cuda_path unavailable: {exc}"

    onnx = resolve_rvm_onnx()
    info: dict[str, Any] = {
        "onnx_found": onnx is not None,
        "onnx_path": str(onnx) if onnx else None,
        "onnx_name": onnx.name if onnx else None,
        "ort_available": False,
        "cuda_ep": False,
        "providers": [],
        "prefer": os.environ.get("HYBRID_ORT_PROVIDER", "cuda").strip().lower() or "cuda",
        "source": None,
        "cudnn_ok": cudnn_ok,
        "cudnn_detail": cudnn_detail,
        "cuda_fallback": None,
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
        info["cuda_ep"] = "CUDAExecutionProvider" in providers
    except Exception as exc:  # noqa: BLE001
        info["ort_error"] = str(exc)
    return info


def heuristic_person_alpha(bgr: np.ndarray) -> np.ndarray:
    """Soft person-ish matte without ML — scaffold / CI fallback only."""
    h, w = bgr.shape[:2]
    hsv = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)
    skin = cv2.inRange(hsv, (0, 30, 50), (25, 180, 255))
    skin2 = cv2.inRange(hsv, (160, 30, 50), (180, 180, 255))
    skin = cv2.bitwise_or(skin, skin2)
    lab = cv2.cvtColor(bgr, cv2.COLOR_BGR2LAB)
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    cx, cy = w * 0.5, h * 0.55
    dist = np.sqrt(((xx - cx) / (w * 0.35)) ** 2 + ((yy - cy) / (h * 0.45)) ** 2)
    center = np.clip(1.0 - dist, 0.0, 1.0)
    edges = cv2.Canny(cv2.GaussianBlur(lab[:, :, 0], (5, 5), 0), 40, 120)
    edges = cv2.dilate(edges, np.ones((3, 3), np.uint8), iterations=1)
    mask = np.full((h, w), cv2.GC_PR_BGD, np.uint8)
    mask[center > 0.55] = cv2.GC_PR_FGD
    mask[skin > 0] = cv2.GC_FGD
    border = max(4, min(h, w) // 40)
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
        gc = center * 0.7 + (skin.astype(np.float32) / 255.0) * 0.3
    alpha = 0.75 * gc + 0.15 * center + 0.10 * (edges.astype(np.float32) / 255.0)
    alpha = cv2.GaussianBlur(alpha, (0, 0), sigmaX=2.0)
    return np.clip(alpha, 0.0, 1.0).astype(np.float32)


class _OrtRvmSession:
    """RVM ONNX session — CUDA EP preferred when available."""

    def __init__(self, model_path: Path) -> None:
        from hybrid_editor.cuda_path import (
            brief_ort_error,
            inject_nvidia_pip_libs,
            is_cudnn_or_cuda_ep_error,
            pip_cudnn_present,
        )

        # Must run BEFORE InferenceSession — LoadLibrary looks up cudnn64_9.dll via PATH.
        inject_nvidia_pip_libs()
        import onnxruntime as ort  # type: ignore

        prefer = os.environ.get("HYBRID_ORT_PROVIDER", "cuda").strip().lower()
        avail = list(ort.get_available_providers())
        providers: list[str] = []
        uses_cuda = False
        if prefer == "cuda" and "CUDAExecutionProvider" in avail:
            providers.append("CUDAExecutionProvider")
            uses_cuda = True
        elif prefer == "dml" and "DmlExecutionProvider" in avail:
            providers.append("DmlExecutionProvider")
        elif prefer == "cpu":
            pass
        elif "CUDAExecutionProvider" in avail and prefer != "cpu":
            providers.append("CUDAExecutionProvider")
            uses_cuda = True
        providers.append("CPUExecutionProvider")

        if uses_cuda:
            acquire_cuda("fast-ort", detail=str(model_path))
        self._uses_cuda = uses_cuda
        self.fallback_note: Optional[str] = None
        so = ort.SessionOptions()
        so.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
        try:
            self.session = ort.InferenceSession(
                str(model_path), sess_options=so, providers=providers
            )
        except Exception as exc:  # noqa: BLE001
            if uses_cuda:
                release_cuda("fast-ort")
                self._uses_cuda = False
            # Soft fallback: missing cudnn64_*.dll / CUDA EP load → retry CPU (UI stays up).
            if uses_cuda and is_cudnn_or_cuda_ep_error(exc):
                brief = brief_ort_error(exc)
                _, cudnn_detail = pip_cudnn_present()
                self.fallback_note = (
                    f"CUDA→CPU: cuDNN/CUDA EP unavailable ({brief}). "
                    f"{cudnn_detail}. Fix: pip install nvidia-cudnn-cu12 in active venv, "
                    "or .\\start_hybrid_cuda.ps1 / parent remount_ort_gpu.ps1, "
                    "or $env:HYBRID_REUSE_PARENT_VENV='1'."
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
        self.provider = self.session.get_providers()[0]
        self._r1 = self._r2 = self._r3 = self._r4 = None
        self.model_path = model_path
        self.input_dtype = resolve_rvm_input_dtype(self.session, model_path)
        # If CUDA was requested but session fell back to CPU, release slot
        if uses_cuda and "CUDA" not in self.provider:
            if self._uses_cuda:
                release_cuda("fast-ort")
            self._uses_cuda = False
            if self.fallback_note is None:
                self.fallback_note = (
                    "CUDA EP listed but session active provider is CPU — "
                    "check cudnn64_9.dll on PATH (nvidia-cudnn-cu12)."
                )

    def reset(self) -> None:
        self._r1 = self._r2 = self._r3 = self._r4 = None

    def close(self) -> None:
        self.reset()
        self.session = None  # type: ignore
        if self._uses_cuda:
            release_cuda("fast-ort")
            self._uses_cuda = False

    def matte(self, bgr: np.ndarray, downsample: float = 0.25) -> np.ndarray:
        if self.session is None:
            raise RuntimeError("ORT session closed")
        dtype = self.input_dtype
        # Resize in float32 for OpenCV, cast to model dtype before ORT.
        rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB).astype(np.float32) / 255.0
        h, w = rgb.shape[:2]
        if downsample < 1.0:
            nh, nw = max(1, int(h * downsample)), max(1, int(w * downsample))
            nh, nw = nh - nh % 4, nw - nw % 4
            nh, nw = max(4, nh), max(4, nw)
            src = cv2.resize(rgb, (nw, nh), interpolation=cv2.INTER_AREA)
        else:
            src = rgb
            nh, nw = h, w
        x = np.ascontiguousarray(np.transpose(src, (2, 0, 1))[None, ...], dtype=dtype)
        feeds: dict[str, Any] = {"src": x}
        inputs = {i.name: i for i in self.session.get_inputs()}
        for name, rec in (("r1i", self._r1), ("r2i", self._r2), ("r3i", self._r3), ("r4i", self._r4)):
            if name in inputs:
                shape = [d if isinstance(d, int) else 1 for d in inputs[name].shape]
                if rec is None:
                    feeds[name] = np.zeros(shape, dtype=dtype)
                else:
                    feeds[name] = np.ascontiguousarray(rec, dtype=dtype)
        if "downsample_ratio" in inputs:
            # RVM exports keep downsample_ratio as float32 even for fp16 graphs.
            feeds["downsample_ratio"] = np.array(
                [downsample if downsample < 1 else 1.0], dtype=np.float32
            )
        outs = self.session.run(None, feeds)
        pha = None
        for o in outs:
            if isinstance(o, np.ndarray) and o.ndim >= 3:
                if o.ndim == 4 and o.shape[1] == 1:
                    pha = o
                    break
        if pha is None:
            pha = outs[1] if len(outs) > 1 else outs[0]
        alpha = np.squeeze(pha).astype(np.float32)
        if alpha.ndim == 3:
            alpha = alpha[0]
        if alpha.shape != (h, w):
            alpha = cv2.resize(alpha, (w, h), interpolation=cv2.INTER_LINEAR)
        # Recurrent outputs — common export layout fgr, pha, r1o..r4o
        if len(outs) >= 6:
            self._r1 = np.ascontiguousarray(outs[2], dtype=dtype)
            self._r2 = np.ascontiguousarray(outs[3], dtype=dtype)
            self._r3 = np.ascontiguousarray(outs[4], dtype=dtype)
            self._r4 = np.ascontiguousarray(outs[5], dtype=dtype)
        return np.clip(alpha, 0.0, 1.0)


class FastEngine(MattingEngine):
    mode = EngineMode.GYORS

    def __init__(self) -> None:
        self._media: Optional[MediaInfo] = None
        self._rvm: Optional[_OrtRvmSession] = None
        self._backend = "heuristic"
        self._status_note: Optional[str] = None
        self._mask_store: Optional[MaskStore] = None
        self._frame_cache = FrameCache(48)
        self._prefetch = ScrubPrefetcher(ahead=8)
        self._lanes: Optional[ProxyLaneCache] = None
        self._last_frame_idx = 0
        self._proxy_long = int(os.environ.get("HYBRID_PROXY_LONG", "720") or "720")
        self._load_rvm()

    def _load_rvm(self) -> None:
        model = resolve_rvm_onnx()
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
        detail = (
            f"ORT RVM via HYBRID_RVM_ONNX / parent Videoeditor models/ "
            f"/ models/*.onnx ({self._backend})."
            if self._rvm
            else HEURISTIC_NOTE
        )
        note = getattr(self, "_status_note", None)
        if note:
            detail = f"{detail} {note}" if self._rvm else note
        return EngineCapabilities(
            mode=self.mode,
            name="Gyors mód (RVM / Fast)",
            backend=self._backend,
            available=True,
            license_note="RVM ONNX: follow upstream license; heuristic fallback is ours (MIT).",
            vram_hint_gb=3.0 if self._rvm and "CUDA" in self._backend else 0.5,
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

    def _matte(self, bgr: np.ndarray) -> np.ndarray:
        if self._rvm is not None:
            return self._rvm.matte(bgr, downsample=0.25)
        return heuristic_person_alpha(bgr)

    def preview_frame(self, t_sec: float) -> PreviewFrame:
        if self._media is None:
            raise RuntimeError("No media open")
        fps = self._media.fps or 25.0
        frame_idx = int(round(max(0.0, t_sec) * fps))
        direction = 1 if frame_idx >= self._last_frame_idx else -1
        self._last_frame_idx = frame_idx
        self._prefetch.nudge(frame_idx, direction=direction, max_long=self._proxy_long)

        # Prefer proxy-sized decode from HOT/WARM/COLD lanes
        bgr = self._decode_proxy_idx(frame_idx, self._proxy_long)
        if bgr is not None and self._lanes is not None:
            self._lanes.put(frame_idx, bgr, lane=Lane.HOT)
        if bgr is None:
            if self._rvm:
                self._rvm.reset()
            bgr, t = read_frame_at(Path(self._media.path), t_sec)
        else:
            t = min(t_sec, self._media.duration_sec)

        # MaskStore hit → skip ORT
        alpha = None
        from_store = False
        if self._mask_store is not None:
            alpha = self._mask_store.get_alpha(t, shape=bgr.shape[:2])
            from_store = alpha is not None
        if alpha is None:
            if self._rvm:
                self._rvm.reset()  # seek: don't smear recurrent state
            alpha = self._matte(bgr)
            if self._mask_store is not None:
                self._mask_store.put_async(t, alpha)

        jpg, png, w, h, src = encode_preview_pair(bgr, alpha)
        lane_meta = self._lanes.status() if self._lanes else {}
        return PreviewFrame(
            t_sec=t,
            width=w,
            height=h,
            jpeg_b64=jpg,
            alpha_png_b64=png,
            engine="FastEngine",
            backend=self._backend,
            meta={
                "mode": self.mode.value,
                "mask_store": from_store,
                "prefetch_ahead": 8,
                "frame_idx": frame_idx,
                "proxy_lanes": lane_meta,
            },
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
        alpha_dir = out_dir / "alpha"
        alpha_dir.mkdir(parents=True, exist_ok=True)
        self.reset()
        path = Path(self._media.path)
        fps = self._media.fps or 25.0
        start_t = max(0.0, float(in_sec))
        end_t = float(out_sec) if out_sec is not None and out_sec > 0 else self._media.duration_sec
        end_t = max(start_t, end_t)

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
        if max_frames is not None:
            total_est = min(total_est, max_frames)
        frames_bgr: list[np.ndarray] = []
        frames_alpha: list[np.ndarray] = []
        frames_bgra: list[np.ndarray] = []
        try:
            idx = 0
            while written < limit:
                ok, bgr = cap.read()
                if not ok or bgr is None:
                    break
                cur_t = start_t + (idx / fps)
                if cur_t > end_t + 1e-6:
                    break
                alpha = self._matte(bgr)
                a8 = (np.clip(alpha, 0, 1) * 255).astype(np.uint8)
                cv2.imwrite(str(alpha_dir / f"{idx:06d}.png"), a8)
                if self._mask_store is not None:
                    self._mask_store.put(cur_t, alpha)
                # Keep proxy-sized frames for preview mp4 (memory-safe)
                proxy = downscale_long_side(bgr, 720)
                a_p = cv2.resize(alpha, (proxy.shape[1], proxy.shape[0]), interpolation=cv2.INTER_LINEAR)
                frames_bgr.append(proxy)
                frames_alpha.append(a_p)
                a3 = (a_p * 255).astype(np.uint8)
                bgra = cv2.cvtColor(proxy, cv2.COLOR_BGR2BGRA)
                bgra[:, :, 3] = a3
                frames_bgra.append(bgra)
                written += 1
                idx += 1
                if progress:
                    progress(min(0.85, written / max(total_est, 1)), f"Gyors bake {written}/{total_est}")
        finally:
            cap.release()

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
            if os.environ.get("HYBRID_EXPORT_PRORES", "").strip() in {"1", "true", "yes"}:
                if progress:
                    progress(0.95, "Export ProRes alpha…")
                prores = try_prores_alpha(frames_bgra, out_dir / "master_alpha.mov", fps=fps)
            if progress:
                progress(1.0, "Bake kész")

        audio_note = " · audio AAC" if audio_ok else ""
        return BakeResult(
            ok=written > 0,
            out_dir=str(out_dir.resolve()),
            frames_written=written,
            engine="FastEngine",
            backend=self._backend,
            message=f"Wrote {written} alpha frames + preview{audio_note} ({self._backend})",
            alpha_preview=str(alpha_dir / "000000.png") if written else None,
            preview_mp4=preview_mp4,
            prores_mov=prores,
            bake_range={"in_sec": start_t, "out_sec": end_t, "audio": audio_ok},
        )
