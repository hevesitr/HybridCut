#!/usr/bin/env python3
"""Probe CUDAExecutionProvider registration for HybridCut start_hybrid_cuda.ps1.

Prints KEY=value lines (ASCII). Exit 0 always so PowerShell can parse OK=0/1.
Never use python -c for this — Windows PowerShell quoting breaks multiline -c.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path


def _emit(key: str, value: str) -> None:
    safe = " ".join(str(value).replace("\r", " ").replace("\n", " ").split())
    print(f"{key}={safe}")


def main() -> int:
    root = Path(os.environ.get("HYBRID_ROOT", "")).resolve()
    if not root.is_dir():
        # scripts/ → hybrid_cut root
        root = Path(__file__).resolve().parents[1]
    backend = root / "backend"
    if str(backend) not in sys.path:
        sys.path.insert(0, str(backend))

    try:
        from hybrid_editor.cuda_path import (  # noqa: WPS433
            PREFERRED_ORT_GPU_VERSION,
            available_ort_providers,
            inject_nvidia_pip_libs,
            ort_gpu_pin_ok,
            ort_package_version,
            probe_cuda_ep_usable,
        )

        inject_nvidia_pip_libs()
        import onnxruntime as ort  # type: ignore

        ver = ort_package_version(ort)
        pin_ok, pin_detail = ort_gpu_pin_ok(ort)
        providers = available_ort_providers(ort)
        listed = "CUDAExecutionProvider" in providers
        # Prefer an RVM ONNX for gray-slab smoke (Identity alone can false-OK).
        model_path = None
        for env_name in ("HYBRID_RVM_ONNX", "VIDEOEDITOR_RVM_ONNX"):
            raw = os.environ.get(env_name, "").strip()
            if raw and Path(raw).is_file():
                model_path = Path(raw)
                break
        if model_path is None:
            for name in (
                "rvm_mobilenetv3_fp32.onnx",
                "rvm_resnet50_fp32.onnx",
                "rvm_mobilenetv3_fp16.onnx",
            ):
                cand = root / "models" / name
                if cand.is_file():
                    model_path = cand
                    break
        ok, detail = probe_cuda_ep_usable(
            ort, model_path=model_path, use_cache=False
        )
        # Belt: never OK=1 when detail/plugin text contradicts (soft heuristics).
        detail_l = (detail or "").lower()
        if ok and (
            "no registered plugin ep" in detail_l
            or "gray-slab" in detail_l
            or "gray slab" in detail_l
        ):
            ok = False
            detail = detail or "probe contradicted OK"

        _emit("ORT_VERSION", ver)
        _emit("PIN", PREFERRED_ORT_GPU_VERSION)
        _emit("PIN_OK", "1" if pin_ok else "0")
        _emit("PIN_DETAIL", pin_detail[:300])
        _emit("LISTED", "1" if listed else "0")
        _emit("MODEL", str(model_path) if model_path else "")
        _emit("OK", "1" if ok else "0")
        _emit("DETAIL", detail[:400])
        _emit("PROVIDERS", ",".join(providers))
        _emit("RESULT", "OK" if ok else "FAIL")
    except Exception as exc:  # noqa: BLE001
        _emit("ORT_VERSION", "")
        _emit("PIN", "1.30.0")
        _emit("PIN_OK", "0")
        _emit("PIN_DETAIL", str(exc)[:300])
        _emit("LISTED", "0")
        _emit("MODEL", "")
        _emit("OK", "0")
        _emit("DETAIL", str(exc)[:400])
        _emit("PROVIDERS", "")
        _emit("RESULT", "FAIL")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
