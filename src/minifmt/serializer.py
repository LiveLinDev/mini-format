"""Serializer: canonical JSON object + contract -> .mini text.

The serializer is the inverse of the parser.  It is deliberately strict: it
raises on values that do not fit the contract, so that ``dumps(parse(x)) ==
x`` and ``parse(dumps(obj)) == obj`` hold for every valid document (the
round-trip property that distinguishes a serialization from an abbreviation).

SPEC 1.1 Â§9: the error raised for an invalid object is a :class:`MiniError`
carrying the code the parser reports for the same violation and the physical
line the offending entry would occupy (1 = header, i + 2 = record i).  Every
emitted document is verified by a strict parse before it is returned.
"""
from __future__ import annotations

from typing import Any, Dict, Iterable, List, Optional

from . import codec
from .contract import SCALAR_TYPES, Contract, Field
from .errors import E_ENUM, E_MARKER, E_TYPE, MiniError, MiniValidationError
from .parser import parse
from .values import coerce_from_json, encode_scalar


def _enc_list(values: Iterable[Any], f: Field, sep: str, marked: Optional[Iterable[int]] = None) -> str:
    marked_set = set(marked or [])
    out = []
    for i, v in enumerate(values):
        v = coerce_from_json(v, f, item=True)
        s = codec.escape_element(encode_scalar(v, f, item=True), sep)
        if i in marked_set:
            s += codec.MARKER
        out.append(s)
    return sep.join(out)


def encode_field(value: Any, f: Field, sep: str, rec: Optional[Dict[str, Any]] = None) -> str:
    if f.type == "mlist" and rec is not None:
        items = rec.get(f.json_items)
        if items is None:
            if f.optional:
                return ""
            raise MiniError(E_TYPE, 0, "required marked list is null", f.name)
        value = {f.json_items: items, f.json_selected: rec.get(f.json_selected)}
    if value is None:
        if f.optional:
            return ""
        raise MiniError(E_TYPE, 0, "required field is null", f.name)
    if f.type in SCALAR_TYPES:
        v = coerce_from_json(value, f)
        if f.type == "enum" and v not in (f.values or []):
            raise MiniError(E_ENUM, 0, f"'{v}' not in enum", f.name)
        return codec.escape_scalar(encode_scalar(v, f))
    if f.type == "list":
        if not isinstance(value, (list, tuple)):
            raise MiniError(E_TYPE, 0, "list expected", f.name)
        return _enc_list(value, f, sep)
    if f.type == "mlist":
        if isinstance(value, dict):
            items = value.get(f.json_items, [])
            sel = value.get(f.json_selected)
        elif isinstance(value, (list, tuple)) and len(value) == 2:  # [items, selected] shorthand
            items, sel = value
        else:
            raise MiniError(E_TYPE, 0, "marked list expected", f.name)
        if not isinstance(items, (list, tuple)):
            raise MiniError(E_TYPE, 0, "list expected", f.name)
        if sel is None:
            marked: List[int] = []
        elif isinstance(sel, int) and not isinstance(sel, bool):
            marked = [sel]
        elif isinstance(sel, (list, tuple)) and all(isinstance(m, int) and not isinstance(m, bool) for m in sel):
            marked = list(sel)
        else:
            raise MiniError(E_MARKER, 0, f"invalid selection {sel!r}", f.name)
        if f.marker == "exactly_one" and len(marked) != 1:
            raise MiniError(E_MARKER, 0, "exactly one selected element required", f.name)
        if f.marker == "at_least_one" and not marked:
            raise MiniError(E_MARKER, 0, "at least one selected element required", f.name)
        if f.marker == "at_most_one" and len(marked) > 1:
            raise MiniError(E_MARKER, 0, "at most one selected element allowed", f.name)
        for m in marked:
            if not (0 <= m < len(items)):
                raise MiniError(E_MARKER, 0, f"selected index {m} out of range", f.name)
        return _enc_list(items, f, sep, marked)
    if f.type == "tuple":
        if not isinstance(value, dict):
            raise MiniError(E_TYPE, 0, "tuple expects an object", f.name)
        parts = []
        for comp in f.items:
            v = value.get(comp.name)
            if v is None:
                if comp.optional:
                    parts.append("")
                    continue
                raise MiniError(E_TYPE, 0, f"tuple component '{comp.name}' missing", f.name)
            parts.append(codec.escape_element(encode_scalar(coerce_from_json(v, comp), comp), sep))
        return sep.join(parts)
    raise MiniError(E_TYPE, 0, f"unsupported type {f.type}", f.name)  # pragma: no cover


def encode_header(header: Dict[str, Any], contract: Contract, n: int) -> str:
    sep = contract.list_separator
    parts = [contract.prefix]
    hdr = dict(header)
    hdr["n"] = n
    # deterministic order: contract-declared keys first (n after the first key
    # group is fine, but we keep n early for readability), then extra keys.
    ordered = ["n"] + [k for k in contract.header_keys if k in hdr and k != "n"] + [k for k in hdr if k not in contract.header_keys]
    for k in ordered:
        v = hdr[k]
        if v is None:
            continue
        hk = contract.header_keys.get(k)
        if k == "v" and int(v) == 1 and hk is not None and hk.default == 1:
            continue  # default version is implicit
        if hk is None:
            txt = codec.escape_scalar(str(v))
        elif hk.type == "list":
            txt = _enc_list(v, hk.as_field(), sep)
        elif hk.type == "tuple":
            txt = sep.join(codec.escape_element(encode_scalar(coerce_from_json(v.get(c.name), c), c), sep) if v.get(c.name) is not None else "" for c in hk.items)
        else:
            txt = codec.escape_scalar(encode_scalar(coerce_from_json(v, hk.as_field()), hk.as_field()))
        parts.append(f"{k}={txt}")
    return codec.FIELD_SEP.join(parts)


def encode_record(rec: Dict[str, Any], contract: Contract) -> str:
    sep = contract.list_separator
    cells = [encode_field(rec.get(f.name), f, sep, rec) for f in contract.core]
    # extensions: emit up to the last non-null extension (tail may be omitted)
    ext_cells = [encode_field(rec.get(f.name), f, sep, rec) for f in contract.extensions]
    while ext_cells and ext_cells[-1] == "":
        ext_cells.pop()
    return codec.FIELD_SEP.join(cells + ext_cells)


def dumps(obj: Dict[str, Any], contract: Contract) -> str:
    """Serialise a canonical object ``{"header": {...}, "<records_key>": [...]}``.

    Raises :class:`MiniError` with the parser's code and the line the invalid
    entry would occupy when the object is not valid under the contract."""
    records = obj.get(contract.records_key)
    if records is None:
        records = obj.get("records", [])
    if not isinstance(records, (list, tuple)):
        raise MiniError(E_TYPE, 0, f"'{contract.records_key}' must be a list")
    header = obj.get("header") or {}
    if not isinstance(header, dict):
        raise MiniError(E_TYPE, 1, "header must be an object")
    lines = [_at_line(lambda: encode_header(header, contract, len(records)), 1)]
    for i, r in enumerate(records):
        if not isinstance(r, dict):
            raise MiniError(E_TYPE, i + 2, "record must be an object")
        lines.append(_at_line(lambda r=r: encode_record(r, contract), i + 2))
    text = "\n".join(lines)
    try:
        parse(text, contract, strict=True)
    except MiniValidationError as e:
        raise e.errors[0] from None
    return text


def _at_line(encode, lineno: int) -> str:
    try:
        return encode()
    except MiniError as e:
        if not e.line:
            e.line = lineno
        raise
