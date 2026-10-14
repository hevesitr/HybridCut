#!/usr/bin/env python3
"""CLI wrapper: python scripts/diag_face_residue_cli.py --media CLIP --t 1.0"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from hybrid_editor.diag_face_residue import main

if __name__ == "__main__":
    raise SystemExit(main())
