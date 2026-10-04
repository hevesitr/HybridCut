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
from typing import Iterable, Optional


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


def inject_nvidia_pip_libs() -> list[str]:
    """Prepend pip NVIDIA CUDA/cuDNN bins to PATH + add_dll_directory. Never raises."""
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
    """True when ORT CUDA EP failed due to missing cuDNN / CUDA DLL load."""
    text = str(exc).lower()
    if not text:
        return False
    return any(m in text for m in _CUDNN_ERR_MARKERS)


def brief_ort_error(exc: BaseException, limit: int = 180) -> str:
    raw = str(exc)
    brief = raw.split("Status Message:")[-1].strip() if "Status Message:" in raw else raw
    brief = " ".join(brief.split())
    return brief[:limit]


# Early inject on import (before InferenceSession). Safe if packages absent.
_EARLY = inject_nvidia_pip_libs()
