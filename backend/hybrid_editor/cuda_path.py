"""Put pip-installed NVIDIA CUDA/cuDNN DLLs on PATH before onnxruntime loads.

Same idea as CapCut ``matting/cuda_path.py`` / ``remount_ort_gpu.ps1``:
Windows ``.venv/Lib/site-packages/nvidia/cudnn/bin/cudnn64_*.dll`` (9.x may nest
further). Also searches parent ``Documents\\Videoeditor\\.venv`` when HybridCut
runs from a nested ``hybrid_cut`` tree with its own incomplete venv.
"""

from __future__ import annotations

import os
import site
import sys
from pathlib import Path
from typing import Any, Iterable, Optional
import base64
import logging


_NVIDIA_PKG_ORDER = (
    "cuda_runtime",
    "cublas",
    "cudnn",
    "cuda_nvrtc",
    "cufft",
    "curand",
    "cusolver",
    "cusparse",
    "nvjitlink",
    "cuda_cupti",
)

_WIN_CUDNN_GLOBS = ("cudnn64_*.dll", "cudnn*.dll")
_UNIX_CUDNN_GLOBS = ("libcudnn.so.9*", "libcudnn.so.8*", "libcudnn.so")

_CUDNN_ERR_MARKERS = (
    "cudnn64_",
    "libcudnn",
    "cudnn is unavailable",
    "cudnn is not",
    "error 126",
    "error 2",
    "loadlibrary failed",
    "cuda execution provider",
    "cannot load cudnn",
    # ORT 1.19+ plugin EP (ort-cuda): listed in get_available_providers but not registered.
    "no registered plugin ep",
    "no registered plugin ep device",
    "plugin ep device",
    "ort-cuda",
)

CUDA_EP = "CUDAExecutionProvider"
CPU_EP = "CPUExecutionProvider"

# Morning-working ORT GPU wheel on Windows / RTX 3060 (plugin EP).
PREFERRED_ORT_GPU_VERSION = "1.30.0"

# Hungarian install hint when CUDA EP plugin is missing (honest UI / toast title).
CUDA_EP_MISSING_HINT_HU = (
    "CPU ORT: CUDA EP plugin nincs regisztrálva (nincs valódi CUDA). "
    "Javítás Windows: pip uninstall onnxruntime onnxruntime-gpu -y; "
    "pip install onnxruntime-gpu==1.30.0; pip install nvidia-cudnn-cu12; "
    "cudnn64_9.dll legyen a PATH-on (.\\start_hybrid_cuda.ps1 vagy remount_ort_gpu.ps1). "
    "Ne használj 1.31.x-et, ha a plugin EP hiányzik. "
    "Addig RVM CPU-n fut — ember-maszk készül, csak lassabb."
)


def ort_package_version(ort: Any = None) -> str:
    """Return installed onnxruntime / onnxruntime-gpu version string (or '')."""
    if ort is not None:
        ver = getattr(ort, "__version__", None)
        if ver:
            return str(ver)
    try:
        import importlib.metadata as md

        for name in ("onnxruntime-gpu", "onnxruntime"):
            try:
                return str(md.version(name))
            except Exception:
                continue
    except Exception:
        pass
    try:
        inject_nvidia_pip_libs()
        import onnxruntime as _ort  # type: ignore

        return str(getattr(_ort, "__version__", "") or "")
    except Exception:
        return ""


def ort_gpu_pin_ok(ort: Any = None) -> tuple[bool, str]:
    """True when installed ORT version matches the morning-working pin."""
    ver = ort_package_version(ort)
    pin = PREFERRED_ORT_GPU_VERSION
    if not ver:
        return False, f"onnxruntime nincs telepítve — pip install onnxruntime-gpu=={pin}"
    if ver == pin:
        return True, f"onnxruntime-gpu=={ver} (pin OK)"
    return False, (
        f"onnxruntime=={ver} (nem a reggeli pin {pin}). "
        f"pip uninstall onnxruntime onnxruntime-gpu -y; "
        f"pip install onnxruntime-gpu=={pin}"
    )


def _prepend_env_path(env_key: str, folder: Path) -> None:
    try:
        folder_s = str(folder.resolve())
    except Exception:
        folder_s = str(folder)
    cur = os.environ.get(env_key, "")
    parts = [p for p in cur.split(os.pathsep) if p] if cur else []
    if folder_s not in parts:
        os.environ[env_key] = folder_s + (os.pathsep + cur if cur else "")


def _parent_videoeditor_site_packages() -> list[Path]:
    """CapCut parent / Documents\\Videoeditor .venv site-packages (cudnn often lives there)."""
    roots: list[Path] = []
    here = Path(__file__).resolve()
    # .../hybrid_cut/backend/hybrid_editor/cuda_path.py → parents[2]=hybrid_cut, [3]=Videoeditor
    candidates: list[Path] = []
    for up in here.parents:
        candidates.append(up)
        if up.name.lower() == "hybrid_cut" and up.parent.is_dir():
            candidates.append(up.parent)
    home = Path.home()
    candidates.extend(
        [
            home / "Documents" / "Videoeditor",
            home / "Documents" / "videoeditor",
        ]
    )
    for base in candidates:
        for site_pkg in (
            base / ".venv" / "Lib" / "site-packages",
            base
            / ".venv"
            / "lib"
            / f"python{sys.version_info.major}.{sys.version_info.minor}"
            / "site-packages",
            base / "Lib" / "site-packages",
        ):
            if site_pkg.is_dir():
                roots.append(site_pkg)
    return roots


def _site_package_roots() -> list[Path]:
    roots: list[Path] = []
    try:
        import nvidia  # type: ignore

        for p in getattr(nvidia, "__path__", []) or []:
            roots.append(Path(p).parent)
    except Exception:
        pass
    for mod_name in (
        "nvidia.cudnn",
        "nvidia.cublas",
        "nvidia.cuda_runtime",
        "nvidia.cuda_nvrtc",
        "nvidia.cufft",
    ):
        try:
            mod = __import__(mod_name, fromlist=["*"])
            for p in getattr(mod, "__path__", []) or []:
                roots.append(Path(p).parent.parent)
        except Exception:
            continue
    try:
        import sysconfig

        for key in ("purelib", "platlib"):
            val = sysconfig.get_paths().get(key)
            if val:
                roots.append(Path(val))
    except Exception:
        pass
    try:
        for p in site.getsitepackages() if hasattr(site, "getsitepackages") else []:
            roots.append(Path(p))
    except Exception:
        pass
    try:
        us = site.getusersitepackages()
        if us:
            roots.append(Path(us))
    except Exception:
        pass
    roots.append(Path(sys.prefix) / "Lib" / "site-packages")
    roots.append(
        Path(sys.prefix)
        / "lib"
        / f"python{sys.version_info.major}.{sys.version_info.minor}"
        / "site-packages"
    )
    here = Path(__file__).resolve()
    for up in here.parents:
        for cand in (
            up / ".venv" / "Lib" / "site-packages",
            up
            / ".venv"
            / "lib"
            / f"python{sys.version_info.major}.{sys.version_info.minor}"
            / "site-packages",
            up / "Lib" / "site-packages",
        ):
            if cand.is_dir():
                roots.append(cand)
    roots.extend(_parent_videoeditor_site_packages())

    out: list[Path] = []
    seen: set[str] = set()
    for r in roots:
        try:
            key = str(r.resolve()).lower()
        except Exception:
            key = str(r).lower()
        if key not in seen:
            seen.add(key)
            out.append(r)
    return out


def _pkg_sort_key(pkg_name: str) -> tuple[int, str]:
    try:
        return (_NVIDIA_PKG_ORDER.index(pkg_name), pkg_name)
    except ValueError:
        return (len(_NVIDIA_PKG_ORDER), pkg_name)


def iter_nvidia_lib_dirs() -> Iterable[Path]:
    found: list[Path] = []
    seen: set[str] = set()
    for root in _site_package_roots():
        nvidia = root / "nvidia"
        if not nvidia.is_dir():
            continue
        try:
            pkgs = [p for p in nvidia.iterdir() if p.is_dir()]
        except Exception:
            continue
        pkgs.sort(key=lambda p: _pkg_sort_key(p.name))
        for pkg in pkgs:
            for sub in ("bin", "lib"):
                d = pkg / sub
                if not d.is_dir():
                    continue
                try:
                    key = str(d.resolve()).lower()
                except Exception:
                    key = str(d).lower()
                if key in seen:
                    continue
                seen.add(key)
                found.append(d)
            try:
                for d in pkg.rglob("bin"):
                    if d.is_dir():
                        key = str(d.resolve()).lower()
                        if key not in seen:
                            seen.add(key)
                            found.append(d)
                for d in pkg.rglob("lib"):
                    if d.is_dir():
                        key = str(d.resolve()).lower()
                        if key not in seen:
                            seen.add(key)
                            found.append(d)
            except Exception:
                pass
    return found


def find_cudnn_files() -> list[Path]:
    hits: list[Path] = []
    seen: set[str] = set()
    globs = tuple(dict.fromkeys(_WIN_CUDNN_GLOBS + _UNIX_CUDNN_GLOBS))

    def _add(cand: Path) -> None:
        if not cand.is_file():
            return
        name = cand.name.lower()
        if not (name.startswith("cudnn64_") or name.startswith("libcudnn")):
            return
        if cand.suffix.lower() in {".h", ".py", ".pyc"}:
            return
        key = str(cand).lower()
        if key not in seen:
            seen.add(key)
            hits.append(cand)

    for folder in iter_nvidia_lib_dirs():
        for pattern in globs:
            try:
                for cand in folder.glob(pattern):
                    _add(cand)
            except Exception:
                continue

    if not hits:
        for root in _site_package_roots():
            nvidia = root / "nvidia"
            if not nvidia.is_dir():
                continue
            for pattern in globs:
                try:
                    for cand in nvidia.rglob(pattern):
                        _add(cand)
                except Exception:
                    continue

    def _rank(p: Path) -> tuple[int, str]:
        n = p.name.lower()
        if "cudnn64_9" in n or "libcudnn.so.9" in n:
            return (0, n)
        if "cudnn64_8" in n or "libcudnn.so.8" in n:
            return (1, n)
        return (2, n)

    hits.sort(key=_rank)
    return hits


_DLL_DIRS_ADDED: set[str] = set()


def _add_dll_directory(folder: Path) -> None:
    """Windows 3.8+: os.add_dll_directory so LoadLibrary finds cudnn64_*.dll.

    PATH alone is often not enough for onnxruntime-gpu's CUDA EP on modern Python.
    """
    if not sys.platform.startswith("win"):
        return
    if not hasattr(os, "add_dll_directory"):
        return
    try:
        key = str(folder.resolve()).lower()
    except Exception:
        key = str(folder).lower()
    if key in _DLL_DIRS_ADDED:
        return
    try:
        os.add_dll_directory(str(folder))  # type: ignore[attr-defined]
        _DLL_DIRS_ADDED.add(key)
    except (OSError, FileNotFoundError, AttributeError):
        pass


def inject_ort_provider_dirs() -> list[str]:
    """Put onnxruntime_providers_cuda.dll directory on PATH / add_dll_directory.

    ORT 1.19+ loads CUDA as a **plugin EP**. Listed CUDAExecutionProvider with
    missing ``onnxruntime_providers_cuda.dll`` → 'No registered plugin EP device'.
    PATH/cuDNN alone is not enough — the provider DLL folder must be visible.
    """
    added: list[str] = []
    try:
        roots: list[Path] = []
        try:
            import onnxruntime as ort  # type: ignore

            p = Path(getattr(ort, "__file__", "") or "").resolve().parent
            if p.is_dir():
                roots.append(p)
                roots.append(p / "capi")
        except Exception:
            pass
        for site_root in _site_package_roots():
            for cand in (
                site_root / "onnxruntime" / "capi",
                site_root / "onnxruntime",
            ):
                if cand.is_dir():
                    roots.append(cand)
        seen: set[str] = set()
        for folder in roots:
            try:
                key = str(folder.resolve()).lower()
            except Exception:
                key = str(folder).lower()
            if key in seen:
                continue
            seen.add(key)
            _prepend_env_path("PATH", folder)
            _add_dll_directory(folder)
            if not sys.platform.startswith("win"):
                _prepend_env_path("LD_LIBRARY_PATH", folder)
            added.append(str(folder))
            try:
                for dll in folder.glob("onnxruntime_providers_cuda*"):
                    _prepend_env_path("PATH", dll.parent)
                    _add_dll_directory(dll.parent)
            except Exception:
                pass
    except Exception:
        return added
    return added


def inject_nvidia_pip_libs() -> list[str]:
    """Prepend pip NVIDIA CUDA/cuDNN bins + ORT provider dirs. Never raises."""
    added: list[str] = []
    try:
        for folder in iter_nvidia_lib_dirs():
            _prepend_env_path("PATH", folder)
            _add_dll_directory(folder)
            if not sys.platform.startswith("win"):
                _prepend_env_path("LD_LIBRARY_PATH", folder)
            added.append(str(folder))
        for dll in find_cudnn_files():
            _prepend_env_path("PATH", dll.parent)
            _add_dll_directory(dll.parent)
            if not sys.platform.startswith("win"):
                _prepend_env_path("LD_LIBRARY_PATH", dll.parent)
            s = str(dll.parent)
            if s not in added:
                added.append(s)
        for s in inject_ort_provider_dirs():
            if s not in added:
                added.append(s)
    except Exception:
        return added
    return added


def dll_on_path(name: str) -> Optional[Path]:
    for part in os.environ.get("PATH", "").split(os.pathsep):
        if not part:
            continue
        cand = Path(part) / name
        if cand.is_file():
            return cand
    return None


def pip_cudnn_present() -> tuple[bool, str]:
    inject_nvidia_pip_libs()
    for name in ("cudnn64_9.dll", "cudnn64_8.dll"):
        hit = dll_on_path(name)
        if hit is not None:
            return True, f"cuDNN OK (PATH) · {hit}"
    files = find_cudnn_files()
    if files:
        return True, f"cuDNN OK (pip file) · {files[0]}"
    dirs = list(iter_nvidia_lib_dirs())
    if dirs:
        return False, (
            f"nvidia pip dirs={len(dirs)} but no cudnn64_*.dll — "
            "pip install nvidia-cudnn-cu12  or  .\\start_hybrid_cuda.ps1 / parent remount_ort_gpu.ps1"
        )
    return False, (
        "nvidia-cudnn-cu12 not in hybrid/parent venv — "
        "pip install nvidia-cudnn-cu12  or reuse parent Videoeditor .venv"
    )


def is_cudnn_or_cuda_ep_error(exc: BaseException) -> bool:
    """True when ORT CUDA EP failed due to missing cuDNN / CUDA DLL / plugin EP."""
    text = str(exc).lower()
    if not text:
        return False
    return any(m in text for m in _CUDNN_ERR_MARKERS)


def is_plugin_ep_missing_text(text: str) -> bool:
    """True for ORT warning/error: CUDA EP requested but plugin device not registered."""
    t = (text or "").lower()
    if not t:
        return False
    return (
        "no registered plugin ep" in t
        or ("plugin ep" in t and "cuda" in t and ("not found" in t or "no registered" in t))
    )


def brief_ort_error(exc: BaseException, limit: int = 180) -> str:
    raw = str(exc)
    brief = raw.split("Status Message:")[-1].strip() if "Status Message:" in raw else raw
    brief = " ".join(brief.split())
    return brief[:limit]


def available_ort_providers(ort: Any = None) -> list[str]:
    """Safe ``get_available_providers()`` — broken wheels may lack the API."""
    if ort is None:
        try:
            inject_nvidia_pip_libs()
            import onnxruntime as ort  # type: ignore
        except Exception:
            return []
    fn = getattr(ort, "get_available_providers", None)
    if not callable(fn):
        return []
    try:
        return list(fn())
    except Exception:
        return [CPU_EP]


class _OrtWarningCatcher:
    """Capture ORT/C++ warnings that Python exceptions miss (plugin EP).

    ORT's C++ logger writes to the **OS stderr FD**, bypassing ``sys.stderr``.
    A Python-only tee therefore misses ``No registered plugin EP device…`` and
    the probe can falsely print ``OK=1``. We dup2 the real FD into a temp file
    for the critical section, then replay bytes to the restored stderr.
    """

    def __init__(self) -> None:
        self.messages: list[str] = []
        self._handler: Any = None
        self._prev_level: Optional[int] = None
        self._stderr = sys.stderr
        self._buf: list[str] = []
        self._fd_capture = False
        self._stderr_fd: Optional[int] = None
        self._saved_fd: Optional[int] = None
        self._tmp: Any = None

    def __enter__(self) -> "_OrtWarningCatcher":
        import tempfile

        class _H(logging.Handler):
            def __init__(self, sink: list[str]) -> None:
                super().__init__(level=logging.DEBUG)
                self._sink = sink

            def emit(self, record: logging.LogRecord) -> None:
                try:
                    self._sink.append(record.getMessage())
                except Exception:
                    pass

        self._handler = _H(self.messages)
        self._buf = []

        class _StderrTee:
            def __init__(self, real: Any, sink: list[str]) -> None:
                self._real = real
                self._sink = sink

            def write(self, s: str) -> int:
                try:
                    self._sink.append(s)
                except Exception:
                    pass
                return self._real.write(s)

            def flush(self) -> None:
                self._real.flush()

            def __getattr__(self, name: str) -> Any:
                return getattr(self._real, name)

        # Native FD capture first (ORT C++), then Python tee on top.
        try:
            self._stderr_fd = sys.stderr.fileno()
            self._tmp = tempfile.TemporaryFile()
            self._saved_fd = os.dup(self._stderr_fd)
            os.dup2(self._tmp.fileno(), self._stderr_fd)
            self._fd_capture = True
        except Exception:
            self._fd_capture = False
            self._tmp = None
            self._saved_fd = None

        sys.stderr = _StderrTee(self._stderr, self._buf)  # type: ignore[assignment]
        root = logging.getLogger()
        self._prev_level = root.level
        root.setLevel(logging.DEBUG)
        root.addHandler(self._handler)
        for name in ("onnxruntime", "onnxruntime.capi", "Default"):
            logging.getLogger(name).addHandler(self._handler)
            logging.getLogger(name).setLevel(logging.DEBUG)
        return self

    def __exit__(self, *args: Any) -> None:
        try:
            sys.stderr = self._stderr  # type: ignore[has-type]
        except Exception:
            pass
        if getattr(self, "_buf", None):
            self.messages.extend(self._buf)
        # Restore OS stderr FD and merge captured C++ bytes into messages.
        if self._fd_capture and self._tmp is not None and self._saved_fd is not None:
            try:
                try:
                    sys.stderr.flush()
                except Exception:
                    pass
                os.dup2(self._saved_fd, int(self._stderr_fd or 2))
                os.close(self._saved_fd)
                self._saved_fd = None
                self._tmp.flush()
                self._tmp.seek(0)
                raw = self._tmp.read()
                if raw:
                    try:
                        text = raw.decode("utf-8", errors="replace")
                    except Exception:
                        text = str(raw)
                    self.messages.append(text)
                    # Replay so start_hybrid_cuda.ps1 / console still see the warning.
                    try:
                        self._stderr.write(text)
                        self._stderr.flush()
                    except Exception:
                        try:
                            os.write(int(self._stderr_fd or 2), raw)
                        except Exception:
                            pass
            except Exception:
                pass
            try:
                self._tmp.close()
            except Exception:
                pass
            self._tmp = None
            self._fd_capture = False
        if self._handler is None:
            return
        root = logging.getLogger()
        try:
            root.removeHandler(self._handler)
        except Exception:
            pass
        for name in ("onnxruntime", "onnxruntime.capi", "Default"):
            try:
                logging.getLogger(name).removeHandler(self._handler)
            except Exception:
                pass
        if self._prev_level is not None:
            try:
                root.setLevel(self._prev_level)
            except Exception:
                pass

    def captured_text(self) -> str:
        return "\n".join(self.messages)

    def plugin_ep_missing(self) -> bool:
        return is_plugin_ep_missing_text(self.captured_text())


# Tiny Identity ONNX (1×1×1×1 float) — generated with onnx helper; no runtime dep.
_TINY_IDENTITY_ONNX_B64 = (
    "CAg6YgoQCgF4EgF5IghJZGVudGl0eRIUaHlicmlkX2N1ZGFfZXBfcHJvYmVaGwoBeBIWChQIARIQ"
    "CgIIAQoCCAEKAggBCgIIAWIbCgF5EhYKFAgBEhAKAggBCgIIAQoCCAEKAggBQgQKABAN"
)


def build_tiny_identity_onnx() -> bytes:
    """Tiny ONNX Identity model for CUDA EP session probes (no RVM weights needed)."""
    try:
        from onnx import TensorProto, helper  # type: ignore

        x = helper.make_tensor_value_info("x", TensorProto.FLOAT, [1, 1, 1, 1])
        y = helper.make_tensor_value_info("y", TensorProto.FLOAT, [1, 1, 1, 1])
        node = helper.make_node("Identity", ["x"], ["y"])
        graph = helper.make_graph([node], "hybrid_cuda_ep_probe", [x], [y])
        model = helper.make_model(graph, opset_imports=[helper.make_opsetid("", 13)])
        model.ir_version = 8
        return model.SerializeToString()
    except Exception:
        return base64.b64decode(_TINY_IDENTITY_ONNX_B64)


_CUDA_EP_PROBE_CACHE: Optional[tuple[bool, str]] = None


def clear_cuda_ep_probe_cache() -> None:
    """Reset cached CUDA EP probe (tests / after remount)."""
    global _CUDA_EP_PROBE_CACHE
    _CUDA_EP_PROBE_CACHE = None


def set_cuda_ep_probe_cache(ok: bool, detail: str) -> None:
    """Force probe cache (e.g. after RVM load forces CPU-only)."""
    global _CUDA_EP_PROBE_CACHE
    _CUDA_EP_PROBE_CACHE = (bool(ok), str(detail))


def probe_cuda_ep_usable(
    ort: Any = None,
    *,
    model_path: Optional[Path] = None,
    device_id: int = 0,
    use_cache: bool = True,
) -> tuple[bool, str]:
    """Return whether CUDA EP is **actually registered** (not merely listed).

    Newer ORT builds log::
        No registered plugin EP device found for 'CUDAExecutionProvider' with device_id=0
    while ``get_available_providers()`` may still mention CUDA. That path yields
    gray-slab RVM mattes — treat as **not usable** and fall back to CPU.

    **No soft-OK:** listed CUDA + cuDNN present is NOT enough. The probe session
    must activate ``CUDAExecutionProvider`` with **no** plugin-EP warning. A
    half-broken CUDA session (MemcpyTransformer + all-ones pha) is worse than CPU.

    Result is process-cached (status polls must stay cheap).
    """
    global _CUDA_EP_PROBE_CACHE
    if use_cache and _CUDA_EP_PROBE_CACHE is not None:
        return _CUDA_EP_PROBE_CACHE

    inject_nvidia_pip_libs()
    if ort is None:
        try:
            import onnxruntime as ort  # type: ignore
        except Exception as exc:
            result = (False, f"onnxruntime import failed: {exc}")
            _CUDA_EP_PROBE_CACHE = result
            return result

    providers = available_ort_providers(ort)
    if CUDA_EP not in providers:
        result = (
            False,
            f"CUDAExecutionProvider nincs a get_available_providers()-ben: {providers}. "
            + CUDA_EP_MISSING_HINT_HU,
        )
        _CUDA_EP_PROBE_CACHE = result
        return result

    # Prefer tiny Identity (fast). Optional model_path only if tiny build fails.
    model_bytes: Optional[bytes] = None
    model_str: Optional[str] = None
    try:
        model_bytes = build_tiny_identity_onnx()
    except Exception:
        model_bytes = None
    if model_bytes is None and model_path is not None and Path(model_path).is_file():
        model_str = str(model_path)
    if model_bytes is None and model_str is None:
        result = (False, "CUDA EP probe model unavailable")
        _CUDA_EP_PROBE_CACHE = result
        return result

    so = ort.SessionOptions()
    try:
        so.log_severity_level = 2  # WARNING — surface plugin EP line
    except Exception:
        pass
    try:
        so.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_BASIC
    except Exception:
        pass

    cuda_opts = {
        "device_id": int(device_id),
        "do_copy_in_default_stream": True,
    }
    # CUDA-only — never [CUDA, CPU]. A dual list can half-activate MemcpyTransformer.
    provider_list: list[Any] = [(CUDA_EP, cuda_opts)]

    catcher = _OrtWarningCatcher()
    session = None
    err: Optional[BaseException] = None
    with catcher:
        try:
            if model_str is not None:
                session = ort.InferenceSession(
                    model_str, sess_options=so, providers=provider_list
                )
            else:
                session = ort.InferenceSession(
                    model_bytes, sess_options=so, providers=provider_list
                )
        except Exception as exc:  # noqa: BLE001
            err = exc

    if catcher.plugin_ep_missing():
        result = (
            False,
            "ORT: No registered plugin EP device for CUDAExecutionProvider. "
            + CUDA_EP_MISSING_HINT_HU,
        )
        _CUDA_EP_PROBE_CACHE = result
        return result

    if err is not None:
        brief = brief_ort_error(err)
        _, cudnn_detail = pip_cudnn_present()
        # NEVER soft-OK: cudnn present + probe fail still means CUDA unusable.
        # Soft-OK previously claimed CUDA while plugin EP was missing → gray slab.
        if is_cudnn_or_cuda_ep_error(err) or is_plugin_ep_missing_text(str(err)):
            result = (
                False,
                f"CUDA EP session fail: {brief}. {CUDA_EP_MISSING_HINT_HU}",
            )
        else:
            result = (
                False,
                f"CUDA EP session fail: {brief}. {cudnn_detail}. "
                + CUDA_EP_MISSING_HINT_HU,
            )
        _CUDA_EP_PROBE_CACHE = result
        return result

    try:
        active = list(session.get_providers())
    except Exception as exc:
        result = (False, f"get_providers failed: {exc}")
        _CUDA_EP_PROBE_CACHE = result
        return result
    if not active or active[0] != CUDA_EP:
        result = (
            False,
            f"CUDA kérve, de session active={active}. {CUDA_EP_MISSING_HINT_HU}",
        )
        _CUDA_EP_PROBE_CACHE = result
        return result

    # Run Identity once — session that lists CUDA but cannot execute is unusable.
    try:
        import numpy as np

        x = np.zeros((1, 1, 1, 1), dtype=np.float32)
        run_catcher = _OrtWarningCatcher()
        with run_catcher:
            outs = session.run(None, {"x": x})
        # Merge create+run captures — plugin warning may appear on either side.
        merged = catcher.captured_text() + "\n" + run_catcher.captured_text()
        if is_plugin_ep_missing_text(merged) or run_catcher.plugin_ep_missing():
            result = (
                False,
                "ORT: No registered plugin EP device for CUDAExecutionProvider "
                "(failed during Identity run). " + CUDA_EP_MISSING_HINT_HU,
            )
            _CUDA_EP_PROBE_CACHE = result
            return result
        if not outs or outs[0] is None:
            result = (False, "CUDA EP Identity run returned empty")
            _CUDA_EP_PROBE_CACHE = result
            return result
    except Exception as exc:  # noqa: BLE001
        brief = brief_ort_error(exc)
        result = (
            False,
            f"CUDA EP Identity run fail: {brief}. {CUDA_EP_MISSING_HINT_HU}",
        )
        _CUDA_EP_PROBE_CACHE = result
        return result

    # Final hard reject: any plugin-EP text seen during this probe → never OK=1.
    if is_plugin_ep_missing_text(catcher.captured_text()):
        result = (
            False,
            "ORT: No registered plugin EP device for CUDAExecutionProvider. "
            + CUDA_EP_MISSING_HINT_HU,
        )
        _CUDA_EP_PROBE_CACHE = result
        return result

    # Optional RVM smoke: Identity can pass while real Conv ops Fallback → gray pha.
    if model_path is not None and Path(model_path).is_file():
        stem = Path(model_path).stem.lower()
        if "rvm" in stem:
            smoke_ok, smoke_detail = _probe_rvm_cuda_smoke(
                ort, Path(model_path), device_id=device_id
            )
            if not smoke_ok:
                _CUDA_EP_PROBE_CACHE = (False, smoke_detail)
                return False, smoke_detail

    result = (True, f"CUDA EP OK · active={active[0]} · listed={providers}")
    _CUDA_EP_PROBE_CACHE = result
    return result


def _probe_rvm_cuda_smoke(
    ort: Any, model_path: Path, *, device_id: int = 0
) -> tuple[bool, str]:
    """CUDA-only RVM session + synthetic person — FAIL on plugin warn or gray-slab pha."""
    import numpy as np

    so = ort.SessionOptions()
    try:
        so.log_severity_level = 2
    except Exception:
        pass
    try:
        so.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_BASIC
    except Exception:
        pass
    provider_list: list[Any] = [
        (
            CUDA_EP,
            {
                "device_id": int(device_id),
                "do_copy_in_default_stream": True,
            },
        )
    ]
    catcher = _OrtWarningCatcher()
    session = None
    err: Optional[BaseException] = None
    with catcher:
        try:
            session = ort.InferenceSession(
                str(model_path), sess_options=so, providers=provider_list
            )
        except Exception as exc:  # noqa: BLE001
            err = exc
    if catcher.plugin_ep_missing() or is_plugin_ep_missing_text(catcher.captured_text()):
        return (
            False,
            "ORT: No registered plugin EP device for CUDAExecutionProvider "
            "(RVM smoke). " + CUDA_EP_MISSING_HINT_HU,
        )
    if err is not None:
        return (
            False,
            f"CUDA RVM smoke session fail: {brief_ort_error(err)}. "
            + CUDA_EP_MISSING_HINT_HU,
        )
    try:
        active = list(session.get_providers())
    except Exception as exc:
        return False, f"RVM smoke get_providers failed: {exc}"
    if not active or active[0] != CUDA_EP:
        return (
            False,
            f"CUDA RVM smoke active={active} (not CUDA). {CUDA_EP_MISSING_HINT_HU}",
        )

    h, w = 96, 72
    bgr = np.zeros((h, w, 3), dtype=np.uint8)
    bgr[:] = (36, 36, 40)
    yy, xx = np.ogrid[:h, :w]
    cy, cx = h // 2, w // 2
    mask = ((yy - cy) / max(1, h * 0.32)) ** 2 + ((xx - cx) / max(1, w * 0.22)) ** 2 <= 1.0
    bgr[mask] = (170, 150, 130)
    rgb = bgr[:, :, ::-1].astype(np.float32) * (1.0 / 255.0)
    x = np.ascontiguousarray(np.transpose(rgb, (2, 0, 1))[None, ...])
    z = np.zeros((1, 1, 1, 1), dtype=np.float32)
    feeds: dict[str, Any] = {
        "src": x,
        "r1i": z.copy(),
        "r2i": z.copy(),
        "r3i": z.copy(),
        "r4i": z.copy(),
        "downsample_ratio": np.array([0.5], dtype=np.float32),
    }
    try:
        declared = {i.name for i in session.get_inputs()}
        feeds = {k: v for k, v in feeds.items() if k in declared}
    except Exception:
        pass
    run_catcher = _OrtWarningCatcher()
    try:
        with run_catcher:
            outs = session.run(None, feeds)
    except Exception as exc:  # noqa: BLE001
        return (
            False,
            f"CUDA RVM smoke run fail: {brief_ort_error(exc)}. "
            + CUDA_EP_MISSING_HINT_HU,
        )
    if run_catcher.plugin_ep_missing() or is_plugin_ep_missing_text(
        catcher.captured_text() + "\n" + run_catcher.captured_text()
    ):
        return (
            False,
            "ORT: No registered plugin EP device for CUDAExecutionProvider "
            "(RVM smoke run). " + CUDA_EP_MISSING_HINT_HU,
        )
    if not outs:
        return False, "CUDA RVM smoke returned no outputs"
    # Prefer named pha; else outs[1] (fgr, pha, …).
    pha = None
    try:
        for meta, o in zip(session.get_outputs(), outs):
            name = str(getattr(meta, "name", "") or "").lower()
            if name in {"pha", "alpha", "matte"} and isinstance(o, np.ndarray):
                pha = o
                break
    except Exception:
        pha = None
    if pha is None:
        pha = outs[1] if len(outs) > 1 else outs[0]
    arr = np.asarray(pha, dtype=np.float32)
    if arr.ndim == 4:
        alpha = arr[0, 0]
    else:
        alpha = np.squeeze(arr).astype(np.float32)
        if alpha.ndim == 3:
            alpha = alpha[0]
    if alpha.ndim != 2:
        return (
            False,
            "CUDA RVM smoke pha not HxW (gray-slab / wrong tensor). "
            + CUDA_EP_MISSING_HINT_HU,
        )
    try:
        from hybrid_editor.media.video_io import is_matte_degenerate, is_matte_empty

        if is_matte_empty(alpha) or is_matte_degenerate(alpha):
            return (
                False,
                "CUDA RVM smoke matte was gray-slab / empty "
                "(MemcpyTransformer / plugin EP). " + CUDA_EP_MISSING_HINT_HU,
            )
    except Exception as exc:  # noqa: BLE001
        # If helpers unavailable, use a cheap uniform check.
        if float(np.asarray(alpha).std()) < 0.04:
            return (
                False,
                f"CUDA RVM smoke pha near-uniform (std<{0.04}); {exc}. "
                + CUDA_EP_MISSING_HINT_HU,
            )
    return True, "CUDA RVM smoke OK"


# Early inject on import (before InferenceSession). Safe if packages absent.
_EARLY = inject_nvidia_pip_libs()
