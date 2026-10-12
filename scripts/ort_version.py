#!/usr/bin/env python3
"""Print installed onnxruntime-gpu / onnxruntime version (one line). No -c quoting."""

from __future__ import annotations

import importlib.metadata as md


def main() -> int:
    for name in ("onnxruntime-gpu", "onnxruntime"):
        try:
            print(md.version(name))
            return 0
        except Exception:
            continue
    print("")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
