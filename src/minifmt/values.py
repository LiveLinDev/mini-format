"""Typed decoding/encoding of scalar values according to a Field (SPEC §6)."""
from __future__ import annotations

import datetime
import decimal
import math
import re
from typing import Any, Optional

from .contract import Field
from .errors import E_ENUM, E_RANGE, E_TYPE, MiniError

# SPEC 1.1 §6: ASCII digits only; no leading '+'; floats need digits on both
# sides of the point (``.5`` and ``1.`` are E06).  Leading zeros are allowed.
_INT_RE = re.compile(r"-?[0-9]+")
_FLOAT_RE = re.compile(r"-?[0-9]+(\.[0-9]+)?([eE][+-]?[0-9]+)?")
_DECIMAL_RE = re.compile(r"(-?)([0-9]+)(?:\.([0-9]+))?")
_DATE_RE = re.compile(r"([0-9]{4})-([0-9]{2})-([0-9]{2})")
_TRUE = {"true", "1"}
_FALSE = {"false", "0"}
RANGED_TYPES = ("int", "float", "decimal", "date")


def valid_date(text: str) -> bool:
    """``YYYY-MM-DD`` naming an existing proleptic Gregorian day (0001-9999)."""
    m = _DATE_RE.fullmatch(text)
    if not m:
        return False
    try:
        datetime.date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    except ValueError:
        return False
    return True


def normalize_decimal(text: str) -> Optional[str]:
    """Canonical text of an exact decimal, or None if ``text`` is not one.

    Leading zeros of the integer part are dropped and a negative zero loses its
    sign; the fractional digits (the scale) are preserved: ``-007.50`` ->
    ``-7.50``, ``-0.0`` -> ``0.0``.
    """
    m = _DECIMAL_RE.fullmatch(text)
    if not m:
        return None
    sign, whole, frac = m.group(1), m.group(2).lstrip("0") or "0", m.group(3)
    if whole == "0" and (frac is None or set(frac) == {"0"}):
        sign = ""
    return sign + whole + ("." + frac if frac is not None else "")


def decimal_bound(value: Any) -> Optional[str]:
    """Canonical text of a decimal ``min``/``max`` in a contract, or None if invalid.

    Bounds are decimal strings or integral JSON numbers (|x| < 2**53, so that
    every implementation reads the same value)."""
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return str(value) if abs(value) < 2 ** 53 else None
    if isinstance(value, float):
        return str(int(value)) if value.is_integer() and abs(value) < 2 ** 53 else None
    if isinstance(value, str):
        return normalize_decimal(value)
    return None


def decode_scalar(text: str, f: Field, lineno: int, fname: Optional[str] = None) -> Any:
    """Convert the (already unescaped) text of a scalar to its typed value."""
    name = fname or f.name
    t = f.type if f.type not in ("list", "mlist") else f.item
    values = f.values if f.type != "list" and f.type != "mlist" else f.item_values
    if t == "str":
        return text
    if t == "int":
        if not _INT_RE.fullmatch(text):
            raise MiniError(E_TYPE, lineno, f"expected int, got '{text}'", name)
        v = int(text)
        _check_range(v, f, lineno, name)
        return v
    if t == "float":
        if not _FLOAT_RE.fullmatch(text):
            raise MiniError(E_TYPE, lineno, f"expected number, got '{text}'", name)
        v = float(text)
        if math.isnan(v) or math.isinf(v):
            raise MiniError(E_TYPE, lineno, "non-finite number", name)
        _check_range(v, f, lineno, name)
        return v
    if t == "bool":
        if text in _TRUE:
            return True
        if text in _FALSE:
            return False
        raise MiniError(E_TYPE, lineno, f"expected true/false/1/0, got '{text}'", name)
    if t == "enum":
        if values is None or text not in values:
            raise MiniError(E_ENUM, lineno, f"'{text}' not in {{{'|'.join(values or [])}}}", name)
        return text
    if t == "date":
        if not valid_date(text):
            raise MiniError(E_TYPE, lineno, f"expected date YYYY-MM-DD, got '{text}'", name)
        _check_range(text, f, lineno, name)
        return text
    if t == "decimal":
        norm = normalize_decimal(text)
        if norm is None:
            raise MiniError(E_TYPE, lineno, f"expected decimal, got '{text}'", name)
        _check_range(norm, f, lineno, name)
        return norm
    raise MiniError(E_TYPE, lineno, f"unsupported scalar type {t}", name)  # pragma: no cover


def _check_range(v: Any, f: Field, lineno: int, name: str) -> None:
    if f.type not in RANGED_TYPES:
        return
    if f.type == "decimal":
        lo = None if f.min is None else decimal.Decimal(decimal_bound(f.min))
        hi = None if f.max is None else decimal.Decimal(decimal_bound(f.max))
        dv = decimal.Decimal(v)
        if lo is not None and dv < lo:
            raise MiniError(E_RANGE, lineno, f"{v} < min {f.min}", name)
        if hi is not None and dv > hi:
            raise MiniError(E_RANGE, lineno, f"{v} > max {f.max}", name)
        return
    # int/float compare numerically; dates compare as YYYY-MM-DD strings
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
    """Normalise a value coming from canonical JSON before serialising.

    Values that cannot represent the declared type raise E06, the code the
    parser reports for the same violation (SPEC 1.1 §9)."""
    t = f.item if item else f.type
    if value is None:
        return None
    try:
        if t == "int":
            if isinstance(value, float) and not value.is_integer():
                raise ValueError(value)
            if isinstance(value, str) and not _INT_RE.fullmatch(value.strip()):
                raise ValueError(value)
            return int(value)
        if t == "float":
            v = float(value)
            if math.isnan(v) or math.isinf(v):
                raise ValueError(value)
            return v
    except (TypeError, ValueError):
        raise MiniError(E_TYPE, 0, f"expected {t}, got {value!r}", f.name) from None
    if t == "bool":
        return bool(value)
    if t == "date" and isinstance(value, datetime.date) and not isinstance(value, datetime.datetime):
        return value.isoformat()
    if t == "decimal":
        if isinstance(value, decimal.Decimal) and value.is_finite():
            return format(value, "f")
        if isinstance(value, int) and not isinstance(value, bool):
            return str(value)
        if not isinstance(value, str):
            raise MiniError(E_TYPE, 0, f"decimal values are strings, got {value!r}", f.name)
    return str(value)


def scalar_equal(a: Any, b: Any) -> bool:
    if isinstance(a, (int, float)) and isinstance(b, (int, float)) and not isinstance(a, bool) and not isinstance(b, bool):
        return math.isclose(float(a), float(b), rel_tol=1e-12, abs_tol=1e-12)
    return a == b
