# NOTICE

## HybridCut (this tree)

Original code in `docs/hybrid-editor/` is provided for the Videoeditor project (Róbert Hevesi-Tóth).

## Third-party — not vendored

### Concat (jub0t/Concat)

- License: **AGPL-3.0**
- We adapt **architecture ideas** (MaskStore, prefetch, infer≠render, shared export plan).
- **No Concat source code** is copied into this repository.

### MatAnyone 2 (pq-yang/MatAnyone2)

- License: **S-Lab License 1.0 — non-commercial** for code and checkpoints.
- We implement an **optional adapter** and independent quality helpers inspired by published techniques (warmup, guidance trimap, temporal prior).
- **Weights are not redistributed.** Users who are allowed to use the weights under S-Lab 1.0 may point `HYBRID_MATANYONE2_WEIGHTS` at a local file.
- We do **not** claim redistributable rights to MatAnyone2 weights.

### Robust Video Matting (RVM) ONNX

- Obtain weights from upstream; respect that project's license.
- Configure via `HYBRID_RVM_ONNX` or opt-in `scripts/download_rvm.ps1` → `models/`.
- Without ONNX / ORT, FastEngine uses our **OpenCV heuristic fallback** (demo/CI only).
