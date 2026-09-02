"""Deterministic parser: .mini text + contract -> canonical JSON object.

The parser validates locally (one record at a time) and globally (record
count).  In strict mode every error is collected and reported with its line
number, then a :class:`MiniValidationError` is raised.  In lenient mode the
valid records are returned together with the list of errors, which enables
partial recovery of large generated documents.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from . import codec
from .contract import Contract, Field
from .errors import (E_ARITY, E_COUNT_MISMATCH, E_HEADER_KEY, E_LIST_ARITY,
                     E_MARKER, E_NO_COUNT, E_NO_HEADER, E_TYPE, E_UNIQUE,
                     E_UNKNOWN_PREFIX, MiniError, MiniValidationError)
from .values import decode_scalar


class MList(tuple):
    """Decoded marked list: (items, selected).  Expanded into two record keys."""
    __slots__ = ()

    def __new__(cls, items, selected):
        return super().__new__(cls, (items, selected))


@dataclass
class Document:
    prefix: str
    version: int
    header: Dict[str, Any]
    records: List[Dict[str, Any]]
    contract: Contract
    errors: List[MiniError] = field(default_factory=list)
    lines: int = 0

    def to_canonical(self) -> Dict[str, Any]:
        return {"prefix": self.prefix, "header": dict(self.header),
                self.contract.records_key: [dict(r) for r in self.records]}

    @property
    def ok(self) -> bool:
        return not self.errors


def _physical_lines(text: str) -> List[Tuple[int, str]]:
    if text.startswith("﻿"):
        text = text[1:]
    out = []
    for i, raw in enumerate(text.split("\n"), start=1):
        line = raw.rstrip("\r")
        if line.strip() == "":
            continue
        out.append((i, line))
    return out


def parse_header(line: str, lineno: int, contract: Contract, strict: bool) -> Tuple[str, Dict[str, Any], List[MiniError]]:
    errs: List[MiniError] = []
    fields = codec.split_fields(line, contract.list_separator, lineno, strict)
    prefix = codec.text_of(fields[0]) if fields else ""
    header: Dict[str, Any] = {}
    for toks in fields[1:]:
        txt = codec.text_of(toks)
        if not txt:
            continue
        if "=" not in txt:
            errs.append(MiniError(E_HEADER_KEY, lineno, f"header entry '{txt}' is not key=value"))
            continue
        # split on the first unescaped '='  (an '=' inside a value is literal)
        eq = next((i for i, (ch, esc) in enumerate(toks) if ch == "=" and not esc), -1)
        key = codec.text_of(codec.strip_toks(toks[:eq]))
        vtoks = codec.strip_toks(toks[eq + 1:])
        hk = contract.header_keys.get(key)
        try:
            if hk is None:
                header[key] = codec.text_of(vtoks)
            elif hk.type == "list":
                header[key] = [decode_scalar(t, hk.as_field(), lineno, key) for t, _ in codec.split_list(vtoks, contract.list_separator, lineno)]
            elif hk.type == "tuple":
                parts = codec.split_list(vtoks, contract.list_separator, lineno)
                if len(parts) != len(hk.items):
                    raise MiniError(E_LIST_ARITY, lineno, f"expected {len(hk.items)} components, got {len(parts)}", key)
                header[key] = {c.name: (decode_scalar(t, c, lineno, f"{key}.{c.name}") if t != "" else None)
                               for c, (t, _) in zip(hk.items, parts)}
            else:
                header[key] = decode_scalar(codec.text_of(vtoks), hk.as_field(), lineno, key)
        except MiniError as e:
            errs.append(e)
    for key, hk in contract.header_keys.items():
        if key not in header:
            if hk.required and key != "n":
                errs.append(MiniError(E_HEADER_KEY, lineno, f"required header key '{key}' missing"))
            elif hk.default is not None:
                header[key] = hk.default
    if "n" not in header:
        errs.append(MiniError(E_NO_COUNT, lineno, "header must declare n=<record count>"))
    return prefix, header, errs


def decode_field(toks: List[codec.Tok], f: Field, lineno: int, sep: str, header: Optional[Dict[str, Any]] = None) -> Any:
    """Decode one field (token list) according to its Field definition."""
    if f.type in ("str", "int", "float", "bool", "enum"):
        txt = codec.text_of(toks)
        if txt == "":
            if f.optional:
                return f.default
            raise MiniError(E_TYPE, lineno, "required value is empty", f.name)
        return decode_scalar(txt, f, lineno)
    if f.type in ("list", "mlist"):
        elems = codec.split_list(toks, sep, lineno)
        if not elems and not f.optional and f.min is not None and f.min > 0:
            raise MiniError(E_LIST_ARITY, lineno, "required list is empty", f.name)
        if f.min is not None and len(elems) < f.min:
            raise MiniError(E_LIST_ARITY, lineno, f"list has {len(elems)} elements, min {int(f.min)}", f.name)
        if f.max is not None and len(elems) > f.max:
            raise MiniError(E_LIST_ARITY, lineno, f"list has {len(elems)} elements, max {int(f.max)}", f.name)
        if f.count_key and header and isinstance(header.get(f.count_key), int) and len(elems) != header[f.count_key]:
            raise MiniError(E_LIST_ARITY, lineno, f"list has {len(elems)} elements but header {f.count_key}={header[f.count_key]}", f.name)
        items = [decode_scalar(t, f, lineno) for t, _ in elems]
        if f.type == "list":
            for _, m in elems:
                if m:
                    raise MiniError(E_MARKER, lineno, "marker * not allowed in a plain list", f.name)
            return items
        marked = [i for i, (_, m) in enumerate(elems) if m]
        if f.marker == "exactly_one" and len(marked) != 1:
            raise MiniError(E_MARKER, lineno, f"exactly one element must carry *, found {len(marked)}", f.name)
        if f.marker == "at_least_one" and len(marked) < 1:
            raise MiniError(E_MARKER, lineno, "at least one element must carry *", f.name)
        if f.marker == "at_most_one" and len(marked) > 1:
            raise MiniError(E_MARKER, lineno, f"at most one element may carry *, found {len(marked)}", f.name)
        if f.marker in ("exactly_one", "at_most_one"):
            return MList(items, marked[0] if marked else None)
        return MList(items, marked)
    if f.type == "tuple":
        parts = codec.split_list(toks, sep, lineno)
        if not parts and f.optional:
            return None
        if len(parts) != len(f.items):
            raise MiniError(E_LIST_ARITY, lineno, f"tuple expects {len(f.items)} components, got {len(parts)}", f.name)
        out: Dict[str, Any] = {}
        for comp, (txt, m) in zip(f.items, parts):
            if m:
                raise MiniError(E_MARKER, lineno, "marker * not allowed inside a tuple", f.name)
            if txt == "":
                if comp.optional:
                    out[comp.name] = comp.default
                    continue
                raise MiniError(E_TYPE, lineno, f"tuple component '{comp.name}' is empty", f.name)
            out[comp.name] = decode_scalar(txt, comp, lineno, f"{f.name}.{comp.name}")
        return out
    raise MiniError(E_TYPE, lineno, f"unsupported field type {f.type}", f.name)  # pragma: no cover


def parse(text: str, contract: Contract, strict: bool = True) -> Document:
    """Parse ``text`` against ``contract``.

    strict=True  -> raise MiniValidationError listing every error.
    strict=False -> return a Document whose ``errors`` lists the problems and
                    whose ``records`` contain only the valid lines.
    """
    lines = _physical_lines(text)
    errors: List[MiniError] = []
    if not lines:
        raise MiniValidationError([MiniError(E_NO_HEADER, 0, "empty document: header missing")])
    hl, htext = lines[0]
    prefix, header, herr = parse_header(htext, hl, contract, strict)
    errors.extend(herr)
    if prefix != contract.prefix:
        errors.append(MiniError(E_UNKNOWN_PREFIX, hl, f"header prefix '{prefix}' does not match contract '{contract.prefix}'"))
    version = int(header.get("v", 1) or 1)
    records: List[Dict[str, Any]] = []
    uniques: Dict[str, Dict[Any, int]] = {f.name: {} for f in contract.fields if f.unique}
    sep = contract.list_separator
    for lineno, line in lines[1:]:
        try:
            toks = codec.split_fields(line, sep, lineno, strict)
        except MiniError as e:
            errors.append(e)
            continue
        nf = len(toks)
        if nf < contract.arity:
            errors.append(MiniError(E_ARITY, lineno, f"record has {nf} fields, core requires {contract.arity}"))
            continue
        if nf > len(contract.fields):
            errors.append(MiniError(E_ARITY, lineno, f"record has {nf} fields, contract allows at most {len(contract.fields)}"))
            continue
        rec: Dict[str, Any] = {}
        rec_errs: List[MiniError] = []
        for i, f in enumerate(contract.fields):
            if i >= nf:
                if f.type == "mlist":
                    rec[f.json_items], rec[f.json_selected] = None, None
                else:
                    rec[f.name] = f.default
                continue
            try:
                val = decode_field(toks[i], f, lineno, sep, header)
            except MiniError as e:
                rec_errs.append(e)
                continue
            if isinstance(val, MList):
                rec[f.json_items], rec[f.json_selected] = val[0], val[1]
            else:
                rec[f.name] = val
        for name, seen in uniques.items():
            v = rec.get(name)
            if v is not None:
                if v in seen:
                    rec_errs.append(MiniError(E_UNIQUE, lineno, f"duplicate value '{v}' (first seen line {seen[v]})", name))
                else:
                    seen[v] = lineno
        if rec_errs:
            errors.extend(rec_errs)
            continue
        records.append(rec)
    n = header.get("n")
    total_records = len(lines) - 1
    if isinstance(n, int) and n != total_records:
        errors.append(MiniError(E_COUNT_MISMATCH, 0, f"header declares n={n} but document has {total_records} record lines"))
    doc = Document(prefix=prefix, version=version, header=header, records=records,
                   contract=contract, errors=errors, lines=len(lines))
    if strict and errors:
        raise MiniValidationError(errors)
    return doc


def detect_prefix(text: str) -> Optional[str]:
    for _, line in _physical_lines(text)[:1]:
        toks = codec.split_fields(line, ",", 1, strict=False)
        return codec.text_of(toks[0]) if toks else None
    return None
