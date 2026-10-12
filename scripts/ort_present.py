#!/usr/bin/env python3
"""Print 1 if onnxruntime is importable, else 0. Avoids python -c PS quoting."""

from __future__ import annotations

import importlib.util


def main() -> int:
    print("1" if importlib.util.find_spec("onnxruntime") else "0")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
