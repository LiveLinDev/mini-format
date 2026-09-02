"""Typed decoding/encoding of scalar values according to a Field."""
from __future__ import annotations

import math
import re
from typing import Any, List, Optional

from .contract import Field
from .errors import E_ENUM, E_RANGE, E_TYPE, MiniError

_INT_RE = re.compile(r"^[+-]?\d+$")
_FLOAT_RE = re.compile(r"^[+-]?(\d+\.?\d*|\.\d+)([eE][+-]?\d+)?$")
_TRUE = {"true", "1", "yes", "y", "t"}
_FALSE = {"false", "0", "no", "n", "f"}


def decode_scalar(text: str, f: Field, lineno: int, fname: Optional[str] = None) -> Any:
    """Convert the (already unescaped) text of a scalar to its typed value."""
    name = fname or f.name
    t = f.type if f.type not in ("list", "mlist") else f.item
    values = f.values if f.type != "list" and f.type != "mlist" else f.item_values
    if t == "str":
        return text
    if t == "int":
        if not _INT_RE.match(text):
            raise MiniError(E_TYPE, lineno, f"expected int, got '{text}'", name)
        v = int(text)
        _check_range(v, f, lineno, name)
        return v
    if t == "float":
        if not _FLOAT_RE.match(text):
            raise MiniError(E_TYPE, lineno, f"expected number, got '{text}'", name)
        v = float(text)
        if math.isnan(v) or math.isinf(v):
            raise MiniError(E_TYPE, lineno, "non-finite number", name)
        _check_range(v, f, lineno, name)
        return v
    if t == "bool":
        low = text.strip().lower()
        if low in _TRUE:
            return True
        if low in _FALSE:
            return False
        raise MiniError(E_TYPE, lineno, f"expected true/false, got '{text}'", name)
    if t == "enum":
        if values is None or text not in values:
            raise MiniError(E_ENUM, lineno, f"'{text}' not in {{{'|'.join(values or [])}}}", name)
        return text
    raise MiniError(E_TYPE, lineno, f"unsupported scalar type {t}", name)  # pragma: no cover


def _check_range(v: float, f: Field, lineno: int, name: str) -> None:
    if f.type in ("int", "float"):
        if f.min is not None and v < f.min:
            raise MiniError(E_RANGE, lineno, f"{v} < min {f.min}", name)
        if f.max is not None and v > f.max:
            raise MiniError(E_RANGE, lineno, f"{v} > max {f.max}", name)


def encode_scalar(value: Any, f: Field, item: bool = False) -> str:
    """Canonical textual form of a typed value (before escaping)."""
    t = f.item if item else f.type
    if value is None:
        return ""
    if t == "bool":
        return "true" if value else "false"
    if t == "int":
        return str(int(value))
    if t == "float":
        return format_number(value)
    return str(value)


def format_number(x: Any) -> str:
    """Shortest exact representation; integral floats lose the '.0'."""
    if isinstance(x, bool):
        return "true" if x else "false"
    if isinstance(x, int):
        return str(x)
    xf = float(x)
    if xf.is_integer() and abs(xf) < 1e15:
        return str(int(xf))
    s = repr(xf)
    if "e" in s or "E" in s:
        # expand small exponents for readability/token stability
        s2 = f"{xf:.15f}".rstrip("0").rstrip(".")
        if float(s2) == xf:
            return s2
    return s


def coerce_from_json(value: Any, f: Field, item: bool = False) -> Any:
    """Normalise a value coming from canonical JSON before serialising."""
    t = f.item if item else f.type
    if value is None:
        return None
    if t == "int":
        return int(value)
    if t == "float":
        return float(value)
    if t == "bool":
        return bool(value)
    return str(value)


def scalar_equal(a: Any, b: Any) -> bool:
    if isinstance(a, (int, float)) and isinstance(b, (int, float)) and not isinstance(a, bool) and not isinstance(b, bool):
        return math.isclose(float(a), float(b), rel_tol=1e-12, abs_tol=1e-12)
    return a == b
