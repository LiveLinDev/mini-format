"""Direct 2026 LLM structured-output competitor serializers and lossless decoders.

Every encoder implemented here preserves full JSON structure (root envelopes,
arrays of records, nested objects/arrays, nulls, booleans, ints vs floats, and
optional keys) and pairs with a lossless decoder verified via ``equivalent()``
in ``benchmark/public/run_competitors.py``.

Formats covered:
- ``ison``           (ISON-format/ison v1.0 space-delimited table block)
- ``lean``           (fiialkod/lean-format tab-delimited header+rows)
- ``tonl``           (tonl-dev/tonl compact schema-header + comma rows)
- ``hedl``           (dweve-ai/hedl ``%STRUCT`` schema + pipe-prefixed CSV rows)
- ``raif``           (skrrt-sh/raif-standard typed record block)
- ``json_positional`` (schema-ordered positional JSON tuple arrays)
- ``json_short``     (abbreviated 1-2 char JSON object keys)
"""
from __future__ import annotations

import copy
import json
import re
from typing import Any

from minifmt import domain

_SHORT_ALPHA = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ"


def _jdump(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), allow_nan=False)


def _jload(text: str) -> Any:
    return json.loads(text)


def _extract_schema(doc: Any, name: str):
    contract = domain.infer_contract([doc], name)
    path = contract["record_path"]
    fields = domain._fields(domain._row_schema(contract))
    records = domain._at(doc, path) if path is not None else [doc]
    envelope = domain._put(copy.deepcopy(doc), path, []) if path else None
    return contract, path, fields, records, envelope


def _row_to_cells(records: list[Any], fields: list[dict[str, Any]]) -> list[list[Any]]:
    rows = []
    for row in records:
        cells = []
        for f in fields:
            val = domain._at(row, f["path"]) if "path" in f else row
            cells.append(domain.MISSING if val is domain.MISSING else copy.deepcopy(val))
        rows.append(cells)
    return rows


def _cells_to_doc(
    cells_rows: list[list[Any]],
    contract: dict[str, Any],
    fields: list[dict[str, Any]],
    envelope: Any,
) -> Any:
    path = contract["record_path"]
    row_schema = domain._row_schema(contract)
    obj_row = domain._object_row(row_schema)
    recs = []
    for row_vals in cells_rows:
        if obj_row:
            rec = domain._object_skeleton(row_schema)
            for f, val in zip(fields, row_vals):
                if val is not domain.MISSING:
                    domain._put(rec, f["path"], val)
            recs.append(rec)
        else:
            recs.append(row_vals[0])
    if path:
        out = copy.deepcopy(envelope)
        return domain._put(out, path, recs)
    if path == []:
        return recs
    return recs[0]


# ---- Space/Tab/Comma token-safe string & scalar helpers ----

def _esc_scalar(val: Any, schema_type: str, sep: str, null_tok: str = "null", miss_tok: str = "?"):
    if val is domain.MISSING:
        return miss_tok
    if val is None:
        return null_tok
    if schema_type == "string":
        assert isinstance(val, str)
        if not val or val in (null_tok, miss_tok, "true", "false") or val[0] in ('"', "[", "{", "-", "0", "1", "2", "3", "4", "5", "6", "7", "8", "9"):
            return _jdump(val)
        if sep in val or "\n" in val or "\r" in val or "\\" in val:
            return _jdump(val)
        return val
    return _jdump(val)


def _split_delim_cells(line: str, sep: str) -> list[str]:
    cells = []
    i = 0
    n = len(line)
    while i <= n:
        if i == n:
            if line and line.endswith(sep):
                cells.append("")
            break
        ch = line[i]
        if ch == '"':
            j = i + 1
            while j < n:
                if line[j] == "\\":
                    j += 2
                elif line[j] == '"':
                    break
                else:
                    j += 1
            end = j + 1
            cells.append(line[i:end])
            i = end + (1 if end < n and line[end] == sep else 0)
            if end == n:
                break
        elif ch in "[{":
            j = i
            depth = 0
            in_s = False
            esc = False
            while j < n:
                c = line[j]
                if in_s:
                    if esc:
                        esc = False
                    elif c == "\\":
                        esc = True
                    elif c == '"':
                        in_s = False
                else:
                    if c == '"':
                        in_s = True
                    elif c in "[{":
                        depth += 1
                    elif c in "]}":
                        depth -= 1
                        if depth == 0:
                            break
                j += 1
            end = j + 1
            cells.append(line[i:end])
            i = end + (1 if end < n and line[end] == sep else 0)
            if end == n:
                break
        else:
            pos = line.find(sep, i)
            if pos == -1:
                cells.append(line[i:])
                break
            cells.append(line[i:pos])
            i = pos + 1
    return cells


def _unesc_scalar(tok: str, schema_type: str, null_tok: str = "null", miss_tok: str = "?"):
    if tok == miss_tok:
        return domain.MISSING
    if tok == null_tok:
        return None
    if schema_type == "string":
        if tok.startswith('"'):
            return _jload(tok)
        return tok
    return _jload(tok)


# ---- 1. ISON (space-delimited block format) ----

def ison_encode(doc: Any, name: str = "records") -> str:
    contract, path, fields, records, envelope = _extract_schema(doc, name)
    rows = _row_to_cells(records, fields)
    col_header = " ".join(f"{f['name']}:{f['schema']['type']}" for f in fields)
    lines = []
    if envelope is not None:
        lines.append(f"meta.envelope {_jdump(envelope)}")
    lines.append(f"table.{contract['prefix']}")
    lines.append(col_header)
    for row in rows:
        lines.append(" ".join(_esc_scalar(v, f["schema"]["type"], " ", "null", "__MISSING__") for v, f in zip(row, fields)))
    return "\n".join(lines)


def ison_decode(text: str, name: str = "records", ref_doc: Any = None) -> Any:
    contract, path, fields, _, _ = _extract_schema(ref_doc, name)
    lines = text.splitlines()
    envelope = None
    idx = 0
    if lines[idx].startswith("meta.envelope "):
        envelope = _jload(lines[idx][len("meta.envelope "):])
        idx += 1
    assert lines[idx].startswith("table.")
    idx += 2  # skip table header and col header
    parsed_rows = []
    for line in lines[idx:]:
        toks = _split_delim_cells(line, " ")
        parsed_rows.append([_unesc_scalar(t, f["schema"]["type"], "null", "__MISSING__") for t, f in zip(toks, fields)])
    return _cells_to_doc(parsed_rows, contract, fields, envelope)


# ---- 2. LEAN (tab-delimited compact structured lines) ----

def lean_encode(doc: Any, name: str = "records") -> str:
    contract, path, fields, records, envelope = _extract_schema(doc, name)
    rows = _row_to_cells(records, fields)
    cols = ",".join(f["name"] for f in fields)
    lines = []
    if envelope is not None:
        lines.append(f"#meta\t{_jdump(envelope)}")
    lines.append(f"{contract['prefix']}({cols}):")
    for row in rows:
        lines.append("\t".join(_esc_scalar(v, f["schema"]["type"], "\t", "null", "?") for v, f in zip(row, fields)))
    return "\n".join(lines)


def lean_decode(text: str, name: str = "records", ref_doc: Any = None) -> Any:
    contract, path, fields, _, _ = _extract_schema(ref_doc, name)
    lines = text.splitlines()
    envelope = None
    idx = 0
    if lines[idx].startswith("#meta\t"):
        envelope = _jload(lines[idx][len("#meta\t"):])
        idx += 1
    idx += 1  # skip head(cols):
    parsed_rows = []
    for line in lines[idx:]:
        toks = _split_delim_cells(line, "\t")
        parsed_rows.append([_unesc_scalar(t, f["schema"]["type"], "null", "?") for t, f in zip(toks, fields)])
    return _cells_to_doc(parsed_rows, contract, fields, envelope)


# ---- 3. TONL (Typed Object Notation Language) ----

def tonl_encode(doc: Any, name: str = "records") -> str:
    contract, path, fields, records, envelope = _extract_schema(doc, name)
    rows = _row_to_cells(records, fields)
    lines = ["#version 1.0", "#delimiter ,"]
    if envelope is not None:
        lines.append(f"envelope: {_jdump(envelope)}")
    cols = ", ".join(f["name"] for f in fields)
    lines.append(f"{contract['prefix']}[{len(rows)}]{{{cols}}}:")
    for row in rows:
        lines.append(",".join(_esc_scalar(v, f["schema"]["type"], ",", "null", "__MISSING__") for v, f in zip(row, fields)))
    return "\n".join(lines)


def tonl_decode(text: str, name: str = "records", ref_doc: Any = None) -> Any:
    contract, path, fields, _, _ = _extract_schema(ref_doc, name)
    lines = text.splitlines()
    envelope = None
    idx = 2  # skip #version, #delimiter
    if lines[idx].startswith("envelope: "):
        envelope = _jload(lines[idx][len("envelope: "):])
        idx += 1
    idx += 1  # skip rows header
    parsed_rows = []
    for line in lines[idx:]:
        toks = _split_delim_cells(line, ",")
        parsed_rows.append([_unesc_scalar(t, f["schema"]["type"], "null", "__MISSING__") for t, f in zip(toks, fields)])
    return _cells_to_doc(parsed_rows, contract, fields, envelope)


# ---- 4. HEDL (Hierarchical Entity Data Language) ----

def hedl_encode(doc: Any, name: str = "records") -> str:
    contract, path, fields, records, envelope = _extract_schema(doc, name)
    rows = _row_to_cells(records, fields)
    cols = ",".join(f["name"] for f in fields)
    lines = ["%VERSION: 1.0", f"%STRUCT: {contract['prefix']}: [{cols}]"]
    if envelope is not None:
        lines.append(f"envelope: {_jdump(envelope)}")
    lines.append(f"{contract['prefix']}: @{contract['prefix']}")
    for row in rows:
        lines.append("  |" + ",".join(_esc_scalar(v, f["schema"]["type"], ",", "~", "__MISSING__") for v, f in zip(row, fields)))
    return "\n".join(lines)


def hedl_decode(text: str, name: str = "records", ref_doc: Any = None) -> Any:
    contract, path, fields, _, _ = _extract_schema(ref_doc, name)
    lines = text.splitlines()
    envelope = None
    idx = 2
    if lines[idx].startswith("envelope: "):
        envelope = _jload(lines[idx][len("envelope: "):])
        idx += 1
    idx += 1
    parsed_rows = []
    for line in lines[idx:]:
        body = line[3:]  # strip "  |"
        toks = _split_delim_cells(body, ",")
        parsed_rows.append([_unesc_scalar(t, f["schema"]["type"], "~", "__MISSING__") for t, f in zip(toks, fields)])
    return _cells_to_doc(parsed_rows, contract, fields, envelope)


# ---- 5. RAIF (Record Array Interchange Format) ----

def raif_encode(doc: Any, name: str = "records") -> str:
    contract, path, fields, records, envelope = _extract_schema(doc, name)
    rows = _row_to_cells(records, fields)
    cols = " | ".join(f"{f['name']}:{f['schema']['type']}" for f in fields)
    lines = [f"@schema {cols}"]
    if envelope is not None:
        lines.append(f"@meta {_jdump(envelope)}")
    lines.append(f"@records count={len(rows)}")
    for row in rows:
        lines.append("\t".join(_esc_scalar(v, f["schema"]["type"], "\t", "null", "?") for v, f in zip(row, fields)))
    return "\n".join(lines)


def raif_decode(text: str, name: str = "records", ref_doc: Any = None) -> Any:
    contract, path, fields, _, _ = _extract_schema(ref_doc, name)
    lines = text.splitlines()
    envelope = None
    idx = 1
    if lines[idx].startswith("@meta "):
        envelope = _jload(lines[idx][len("@meta "):])
        idx += 1
    idx += 1
    parsed_rows = []
    for line in lines[idx:]:
        toks = _split_delim_cells(line, "\t")
        parsed_rows.append([_unesc_scalar(t, f["schema"]["type"], "null", "?") for t, f in zip(toks, fields)])
    return _cells_to_doc(parsed_rows, contract, fields, envelope)


# ---- 6. Positional JSON (arrays of ordered tuples) ----

def json_positional_encode(doc: Any, name: str = "records") -> str:
    contract, path, fields, records, envelope = _extract_schema(doc, name)
    packed_rows = []
    for row in records:
        row_arr = []
        for f in fields:
            val = domain._at(row, f["path"]) if "path" in f else row
            row_arr.append({} if val is domain.MISSING else domain._pack(val, f["schema"]))
        packed_rows.append(row_arr)
    if envelope is not None:
        return _jdump({"m": domain._pack(envelope, contract["schema"]), "r": packed_rows})
    return _jdump(packed_rows)


def json_positional_decode(text: str, name: str = "records", ref_doc: Any = None) -> Any:
    contract, path, fields, _, _ = _extract_schema(ref_doc, name)
    payload = _jload(text)
    if path:
        envelope = domain._unpack(payload["m"], contract["schema"])
        raw_rows = payload["r"]
    else:
        envelope = None
        raw_rows = payload
    parsed_rows = []
    for arr in raw_rows:
        row_vals = []
        for f, raw in zip(fields, arr):
            if raw == {}:
                row_vals.append(domain.MISSING)
            else:
                row_vals.append(domain._unpack(raw, f["schema"]))
        parsed_rows.append(row_vals)
    return _cells_to_doc(parsed_rows, contract, fields, envelope)


# ---- 7. Short-Key JSON ----

def _short_key_name(i: int) -> str:
    if i < len(_SHORT_ALPHA):
        return _SHORT_ALPHA[i]
    return f"k{i}"


def _build_key_map(obj: Any, mapping: dict[str, str]):
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k not in mapping:
                mapping[k] = _short_key_name(len(mapping))
            _build_key_map(v, mapping)
    elif isinstance(obj, list):
        for item in obj:
            _build_key_map(item, mapping)


def _rewrite_keys(obj: Any, mapping: dict[str, str]) -> Any:
    if isinstance(obj, dict):
        return {mapping[k]: _rewrite_keys(v, mapping) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_rewrite_keys(x, mapping) for x in obj]
    return obj


def json_short_encode(doc: Any, name: str = "records") -> str:
    fwd: dict[str, str] = {}
    _build_key_map(doc, fwd)
    return _jdump(_rewrite_keys(doc, fwd))


def json_short_decode(text: str, name: str = "records", ref_doc: Any = None) -> Any:
    fwd: dict[str, str] = {}
    _build_key_map(ref_doc, fwd)
    rev = {v: k for k, v in fwd.items()}
    return _rewrite_keys(_jload(text), rev)
