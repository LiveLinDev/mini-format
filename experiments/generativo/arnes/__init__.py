"""Arnés experimental V2 (fiabilidad de generación) y V3 (recuperación ante truncamiento)."""
from __future__ import annotations

import sys
from pathlib import Path

_SRC = Path(__file__).resolve().parents[3] / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))
