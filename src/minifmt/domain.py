"""Build and run standalone, lossless JSON domain forks (mini-domain/1).

The academic .mini 1.0 contracts remain separate.  This profile transports
arbitrary JSON through a learned positional schema; no observed value is
silently promoted to a permanent constant.  This file intentionally imports
only Python's standard library so a generated parser can run on its own.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import math
import re
import sys
from pathlib import Path
from typing import Any

PROFILE = "mini-domain/1"
PROFILE_V2 = "mini-domain/2"
MISSING = object()
_PROMPT_HEADINGS = {
    "es": "# Contrato de dominio .mini",
    "en": "# .mini domain contract",
    "lean_es": "# Salida .mini",
    "lean_en": "# .mini output",
}
_DELIMITERS = {"sp": " ", "cm": ",", "tb": "\t", "pi": "|"}
_DELIM_CODES = {" ": "sp", ",": "cm", "\t": "tb"}
_SEP_ESCS = {"|": "\\|", " ": "\\s", ",": "\\,", "\t": "\\t"}
_SEP_UNESCS = {"\\": "\\", "|": "|", "s": " ", " ": " ", ",": ",", "t": "\t", "n": "\n", "r": "\r"}
_BPE_PROXY_RE = re.compile(r' ?[A-Za-z_]+| ?[0-9]{1,3}|\\[\\|,tsnr]|[^\sA-Za-z0-9_\\]+|\s+')


class DomainError(ValueError):
    """Actionable validation error with stable code, line and JSON path."""

    def __init__(self, code: str, message: str, path: str = "$", line: int = 0):
        self.code, self.path, self.line = code, path, line
        self.message = message
        super().__init__(f"{code} line {line} {path}: {message}")

    def to_dict(self):
        return dict(code=self.code, line=self.line, path=self.path, message=self.message)

    def __str__(self):
        return f"{self.code} line {self.line} {self.path}: {self.message}"


def _json(value):
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), allow_nan=False)


def _strict_json(text):
    def reject_constant(value):
        raise ValueError(f"non-finite JSON number: {value}")

    def unique_keys(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError(f"duplicate JSON key: {key}")
            result[key] = value
        return result

    return json.loads(text, parse_constant=reject_constant, object_pairs_hook=unique_keys)


def _kind(value):
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, int):
        return "integer"
    if isinstance(value, float):
        if not math.isfinite(value):
            raise DomainError("D_TYPE", "JSON numbers must be finite")
        return "number"
    if isinstance(value, str):
        return "string"
    if isinstance(value, dict):
        if not all(isinstance(key, str) for key in value):
            raise DomainError("D_TYPE", "JSON object keys must be strings")
        return "object"
    if isinstance(value, list):
        return "array"
    raise DomainError("D_TYPE", f"not a JSON value: {type(value).__name__}")


def _check_json(value, path="$"):
    kind = _kind(value)
    if kind == "object":
        for key, item in value.items():
            _check_json(item, f"{path}/{key}")
    elif kind == "array":
        for index, item in enumerate(value):
            _check_json(item, f"{path}/{index}")


def _infer(values):
    present = [value for value in values if value is not None]
    if not present:
        # A null-only sample conveys no evidence about the eventual non-null
        # type.  Keep it open, instead of incorrectly inferring a null constant.
        return {"type": "json"}
    kinds = {_kind(value) for value in present}
    nullable = len(present) != len(values)
    if kinds <= {"integer", "number"}:
        node = {"type": "number" if "number" in kinds else "integer"}
    elif len(kinds) != 1:
        node = {"type": "json"}
    else:
        kind = next(iter(kinds))
        node = {"type": kind}
        if kind == "object":
            names = dict.fromkeys(key for value in present for key in value)
            node["fields"] = [
                {"name": name, "optional": any(name not in value for value in present),
                 "schema": _infer([value[name] for value in present if name in value])}
                for name in names
            ]
        elif kind == "array":
            items = [item for value in present for item in value]
            node["items"] = _infer(items) if items else {"type": "json"}
    if nullable:
        node["nullable"] = True
    return node


def _at(value, path):
    for key in path:
        if not isinstance(value, dict) or key not in value:
            return MISSING
        value = value[key]
    return value


def _put(value, path, replacement):
    if not path:
        return replacement
    target = value
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = replacement
    return value


def _array_paths(value, path=()):
    if isinstance(value, list):
        if all(isinstance(item, dict) for item in value):
            yield path
    elif isinstance(value, dict):
        for key, item in value.items():
            yield from _array_paths(item, path + (key,))


def _schema_at(node, path):
    for key in path:
        node = next(field["schema"] for field in node["fields"] if field["name"] == key)
    return node


def _fingerprint(contract):
    semantic = {key: contract[key] for key in ("profile", "prefix", "version", "schema", "record_path")}
    return hashlib.sha256(_json(semantic).encode("utf-8")).hexdigest()[:12]


def infer_contract(samples: list[Any], prefix: str = "data", *, record_path=None) -> dict:
    """Learn one contract from complete JSON documents, not a bag of rows.

    Pass ``[document]`` for one JSON file or ``[document1, document2]`` for
    multiple files.  A root array automatically becomes a record collection.
    In wrappers, the largest object-array present in every sample is selected.
    ``record_path`` can explicitly select a list using a list of object keys.
    """
    if not samples:
        raise DomainError("D_SAMPLES", "provide at least one JSON document")
    if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_-]*", prefix):
        raise DomainError("D_PREFIX", "prefix must match [A-Za-z][A-Za-z0-9_-]*")
    for sample in samples:
        _check_json(sample)
    schema = _infer(samples)
    if record_path is not None:
        selected = list(record_path)
        if not all(isinstance(_at(sample, selected), list) for sample in samples):
            raise DomainError("D_PATH", "record path must select an array in every sample")
    elif all(isinstance(sample, list) for sample in samples):
        selected = []
    elif all(isinstance(sample, dict) for sample in samples):
        candidates = set(_array_paths(samples[0]))
        for sample in samples[1:]:
            candidates.intersection_update(_array_paths(sample))
        selected = list(max(candidates, key=lambda path: (sum(len(_at(s, path)) for s in samples), -len(path), path))) if candidates else None
    else:
        selected = None
    if selected is not None:
        try:
            record_schema = _schema_at(schema, selected)["items"]
        except (KeyError, StopIteration):
            raise DomainError("D_PATH", "record path crosses incompatible sample structures") from None
    else:
        record_schema = schema
    contract = {"profile": PROFILE, "prefix": prefix, "version": 1,
                "schema": schema, "record_path": selected,
                "sample_documents": len(samples),
                "sample_records": sum(len(_at(s, selected)) if selected is not None else 1 for s in samples)}
    contract["schema_id"] = _fingerprint(contract)
    contract["record_fields"] = [field["name"] for field in _fields(record_schema)]
    return contract


def load_contract(path=None):
    path = Path(path) if path else Path(__file__).with_name("contract.json")
    try:
        contract = _strict_json(path.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError) as exc:
        raise DomainError("D_CONTRACT", str(exc)) from exc
    return _contract(contract)


def _contract(contract):
    if contract is None:
        return load_contract()
    if contract.get("profile") != PROFILE:
        raise DomainError("D_CONTRACT", f"expected profile {PROFILE}")
    try:
        if contract.get("schema_id") != _fingerprint(contract):
            raise DomainError("D_CONTRACT", "schema fingerprint does not match; rebuild the bundle after editing its contract")
    except (KeyError, TypeError, ValueError) as exc:
        raise DomainError("D_CONTRACT", f"invalid contract: {exc}") from exc
    return contract


def _pack(value, schema, path="$"):
    kind = schema["type"]
    if value is None:
        if schema.get("nullable") or kind == "json":
            return None
        raise DomainError("D_TYPE", "null was not observed for this field; add representative samples and rebuild", path)
    actual = _kind(value)
    if kind == "json":
        _check_json(value, path)
        # Generic JSON is wrapped once; {} is reserved for an absent optional
        # member in positional arrays, and can never collide with real data.
        return [value]
    if actual != kind and not (kind == "number" and actual == "integer"):
        raise DomainError("D_TYPE", f"expected {kind}, received {actual}", path)
    if kind == "object":
        known = {field["name"] for field in schema["fields"]}
        unknown = set(value) - known
        if unknown:
            raise DomainError("D_UNKNOWN", "unknown fields: " + ", ".join(sorted(unknown)) + "; rebuild with these samples", path)
        result = []
        for field in schema["fields"]:
            name = field["name"]
            if name not in value:
                if not field["optional"]:
                    raise DomainError("D_REQUIRED", f"missing required field {name}", path)
                result.append({})
            else:
                result.append(_pack(value[name], field["schema"], f"{path}/{name}"))
        return result
    if kind == "array":
        return [_pack(item, schema["items"], f"{path}/{index}") for index, item in enumerate(value)]
    return value


def _unpack(value, schema, path="$"):
    kind = schema["type"]
    if value is None:
        if schema.get("nullable") or kind == "json":
            return None
        raise DomainError("D_TYPE", "null is not allowed", path)
    if kind == "json":
        if not isinstance(value, list) or len(value) != 1:
            raise DomainError("D_TYPE", "generic JSON must be wrapped in a one-element array", path)
        _check_json(value[0], path)
        return value[0]
    if kind == "object":
        if not isinstance(value, list) or len(value) != len(schema["fields"]):
            raise DomainError("D_ARITY", f"expected positional object with {len(schema['fields'])} members", path)
        result = {}
        for field, item in zip(schema["fields"], value):
            name = field["name"]
            if item == {}:
                if not field["optional"]:
                    raise DomainError("D_REQUIRED", f"missing required field {name}", path)
            else:
                result[name] = _unpack(item, field["schema"], f"{path}/{name}")
        return result
    if kind == "array":
        if not isinstance(value, list):
            raise DomainError("D_TYPE", "expected array", path)
        return [_unpack(item, schema["items"], f"{path}/{index}") for index, item in enumerate(value)]
    return _pack(value, schema, path)


def _escape(text):
    return text.replace("\\", "\\\\").replace("|", "\\|").replace("\n", "\\n").replace("\r", "\\r")


def _escape_sep(text, sep="|"):
    out = text.replace("\\", "\\\\").replace("\n", "\\n").replace("\r", "\\r")
    if sep:
        out = out.replace(sep, _SEP_ESCS[sep])
    return out


def _estimate_bpe_tokens(text):
    # Pure-stdlib heuristic calibrated to BPE (o200k_base / cl100k_base).
    tokens = 0
    for m in _BPE_PROXY_RE.finditer(text):
        tok = m.group()
        if "|" in tok:
            tokens += len(tok)
        elif tok.startswith(",") and len(tok) > 1:
            tokens += 1 + (len(tok) - 1 + 4) // 5
        else:
            tokens += max(1, (len(tok) + 5) // 6)
    return tokens


_FIELD_PART = re.compile(r"[^\\|]+|\\[\\|nr]|[\\|]")
_FIELD_ESCAPES = {"\\": "\\", "|": "|", "n": "\n", "r": "\r"}


def _split(line, lineno):
    if "\\" not in line:
        return line.split("|")
    cells, current = [], []
    for match in _FIELD_PART.finditer(line):
        part = match.group()
        if part == "|":
            cells.append("".join(current))
            current = []
        elif part.startswith("\\"):
            if len(part) == 1:
                raise DomainError("D_ESCAPE", "allowed field escapes: \\\\, \\|, \\n, \\r", line=lineno)
            current.append(_FIELD_ESCAPES[part[1]])
        else:
            current.append(part)
    cells.append("".join(current))
    return cells


def _unescape_tail(text, lineno):
    if "\\" not in text:
        return text
    out = []
    i = 0
    n = len(text)
    while i < n:
        ch = text[i]
        if ch == "\\":
            if i + 1 >= n or text[i + 1] not in _SEP_UNESCS:
                raise DomainError("D_ESCAPE", "invalid field escape in tail cell", line=lineno)
            out.append(_SEP_UNESCS[text[i + 1]])
            i += 2
        else:
            out.append(ch)
            i += 1
    return "".join(out)


def _split_v2(line, lineno, sep="|", max_cells=None):
    if sep == "|" and max_cells is None:
        return _split(line, lineno)
    if not line:
        return [""]
    cells = []
    n = len(line)
    i = 0
    while True:
        if max_cells is not None and len(cells) == max_cells - 1:
            rest = line[i:]
            cells.append(rest if (sep != "|" and rest.startswith('"')) else _unescape_tail(rest, lineno))
            return cells
        if i == n:
            cells.append("")
            return cells
        if sep != "|" and line[i] == '"':
            j = i + 1
            while j < n:
                ch = line[j]
                if ch == "\\":
                    j += 2
                    if j > n:
                        raise DomainError("D_ESCAPE", "unterminated string escape", line=lineno)
                elif ch == '"':
                    break
                else:
                    j += 1
            if j >= n or line[j] != '"':
                raise DomainError("D_ESCAPE", "unterminated quoted string cell", line=lineno)
            end = j + 1
            if end < n and line[end] != sep:
                raise DomainError("D_ESCAPE", "expected delimiter after quoted cell", line=lineno)
            cells.append(line[i:end])
            if end == n:
                return cells
            i = end + 1
            continue
        if sep != "|" and line[i] in "[{":
            j = i
            depth = 0
            in_str = False
            esc = False
            while j < n:
                ch = line[j]
                if in_str:
                    if esc:
                        esc = False
                    elif ch == "\\":
                        esc = True
                    elif ch == '"':
                        in_str = False
                else:
                    if ch == '"':
                        in_str = True
                    elif ch in "[{":
                        depth += 1
                    elif ch in "]}":
                        depth -= 1
                        if depth == 0:
                            break
                j += 1
            if depth != 0 or j >= n:
                raise DomainError("D_ESCAPE", "unterminated JSON composite cell", line=lineno)
            end = j + 1
            if end < n and line[end] != sep:
                raise DomainError("D_ESCAPE", "expected delimiter after composite cell", line=lineno)
            cells.append(line[i:end])
            if end == n:
                return cells
            i = end + 1
            continue
        buf = []
        hit_sep = False
        while i < n:
            ch = line[i]
            if ch == sep:
                cells.append("".join(buf))
                i += 1
                hit_sep = True
                break
            if ch == "\\":
                if i + 1 >= n or line[i + 1] not in _SEP_UNESCS:
                    raise DomainError("D_ESCAPE", "invalid field escape", line=lineno)
                buf.append(_SEP_UNESCS[line[i + 1]])
                i += 2
            else:
                buf.append(ch)
                i += 1
        if not hit_sep:
            cells.append("".join(buf))
            return cells


def _cell(value, schema, path):
    if value is MISSING:
        return "?"
    if value is None:
        _pack(value, schema, path)
        return "~"
    packed = _pack(value, schema, path)
    if schema["type"] == "string":
        return _json(value) if not value or value in ("?", "~") or value.startswith('"') else value
    return _json(packed)


def _cell_v2(value, schema, path, *, sep="|", zero_empty=False, compact_bools=False,
             prefix_strip=None, is_tail=False, last_physical=False, field_optional=False):
    if value is MISSING:
        if zero_empty and not (sep == " " and last_physical):
            return ""
        return "?"
    if value is None:
        _pack(value, schema, path)
        if zero_empty and not field_optional and not (sep == " " and last_physical):
            return ""
        return "~"
    packed = _pack(value, schema, path)
    kind = schema["type"]
    if compact_bools and kind == "boolean":
        return "1" if packed else "0"
    if kind == "string":
        text = value[len(prefix_strip):] if prefix_strip is not None else value
        if is_tail:
            if (not text or text in ("?", "~") or text.startswith(('"', "\ufeff"))
                    or text != text.strip(" \t\r\n") or "\n" in text or "\r" in text):
                return _json(text)
            return _escape_sep(text, "")
        if sep == "|":
            raw = _json(text) if not text or text in ("?", "~") or text.startswith('"') else text
            return _escape_sep(raw, "|")
        if not text or text in ("?", "~") or text.startswith(('"', "[", "{")) or "\n" in text or "\r" in text:
            return _json(text)
        if sep in text:
            escaped = _escape_sep(text, sep)
            quoted = _json(text)
            return quoted if len(quoted) <= len(escaped) else escaped
        return _escape_sep(text, sep)
    return _escape_sep(_json(packed), "|") if sep == "|" else _json(packed)


def _uncell(text, schema, path, *, compact_bools=False):
    if text == "?":
        return MISSING
    if text == "~":
        return _unpack(None, schema, path)
    if compact_bools and schema["type"] == "boolean":
        if text == "1":
            return True
        if text == "0":
            return False
    if schema["type"] == "string":
        if text.startswith('"'):
            try:
                value = _strict_json(text)
            except ValueError as exc:
                raise DomainError("D_VALUE", f"invalid quoted string: {exc}", path) from exc
        else:
            value = text
        return _unpack(value, schema, path)
    try:
        return _unpack(_strict_json(text), schema, path)
    except (ValueError, TypeError) as exc:
        if isinstance(exc, DomainError):
            raise
        raise DomainError("D_VALUE", str(exc), path) from exc


def _row_schema(contract):
    path = contract["record_path"]
    return _schema_at(contract["schema"], path)["items"] if path is not None else contract["schema"]


def _fields(schema):
    if not _object_row(schema):
        return [{"name": "$value", "path": [], "schema": schema, "optional": False}]
    result = []
    def visit(node, path):
        for field in node["fields"]:
            current = path + [field["name"]]
            child = field["schema"]
            if _object_row(child) and not field["optional"]:
                visit(child, current)
            else:
                name = "/".join(key.replace("~", "~0").replace("/", "~1") for key in current)
                result.append({**field, "name": name, "path": current})
    visit(schema, [])
    return result


def _object_row(schema):
    # Nullable objects need a whole-row cell so a null row cannot be confused
    # with an object whose members happen to be null or absent.
    return schema["type"] == "object" and not schema.get("nullable")


def _object_skeleton(schema):
    # Required empty objects have no leaf columns but must survive round-trip.
    return {field["name"]: _object_skeleton(field["schema"]) for field in schema["fields"]
            if _object_row(field["schema"]) and not field["optional"]}


def _raw_cell(value, schema, path):
    if value is MISSING:
        return MISSING
    if value is None:
        _pack(value, schema, path)
        return None
    return _pack(value, schema, path)


def _select_delimiter_v2(rows_raw, fields, active_indices, defaults_map, codebooks, prefix_map,
                         delta_cols, tail_candidates, compact_bools, zero_empty, explicit_sep=None,
                         token_counter=None):
    seps = [explicit_sep] if explicit_sep is not None else ["|", " ", ",", "\t"]
    sample_n = min(len(rows_raw), 48)
    best = ("|", None, float("inf"))
    for sep in seps:
        tails = [None] if sep == "|" else ([None] + tail_candidates)
        for tail_col in tails:
            row_order = [i for i in active_indices if i != tail_col] + ([tail_col] if tail_col is not None else [])
            if not row_order:
                cand_lines = ["-" for _ in range(sample_n)]
            else:
                cand_lines = []
                deltas_prev = {idx: None for idx in delta_cols}
                for r_idx in range(sample_n):
                    row = rows_raw[r_idx]
                    out_cells = []
                    for pos, col_idx in enumerate(row_order):
                        last_phys = (pos == len(row_order) - 1)
                        is_tail = (col_idx == tail_col)
                        if col_idx in codebooks:
                            out_cells.append(codebooks[col_idx][1][r_idx])
                            continue
                        val = row[col_idx]
                        if col_idx in delta_cols and type(val) is int:
                            prev = deltas_prev[col_idx]
                            enc_val = val if prev is None else (val - prev)
                            deltas_prev[col_idx] = val
                            out_cells.append(str(enc_val))
                            continue
                        out_cells.append(_cell_v2(
                            val, fields[col_idx]["schema"], f"$/{r_idx}/{fields[col_idx]['name']}",
                            sep=sep, zero_empty=zero_empty, compact_bools=compact_bools,
                            prefix_strip=prefix_map.get(col_idx), is_tail=is_tail,
                            last_physical=last_phys, field_optional=fields[col_idx]["optional"],
                        ))
                    cand_lines.append(sep.join(out_cells))
            sample_text = "\n".join(cand_lines)
            score = token_counter(sample_text) if token_counter is not None else _estimate_bpe_tokens(sample_text)
            scale = (len(rows_raw) / sample_n) if sample_n else 1.0
            total_est = score * scale + (0 if sep == "|" else 3.5) + (0 if tail_col is None else 4.5)
            if total_est < best[2]:
                best = (sep, tail_col, total_est)
    return best[0], best[1]


def encode_v2(value, contract=None, *, shared=True, dictionaries=True, delta=True,
              prefix_factor=True, compact_bools=True, zero_empty=True,
              delimiter=None, token_counter=None):
    """Serialize JSON into mini-domain/2 with adaptive BPE-optimal compression (100% lossless)."""
    return encode(value, contract, shared=shared, dictionaries=dictionaries, version=2,
                  delimiter=delimiter, token_counter=token_counter, delta=delta,
                  prefix_factor=prefix_factor, compact_bools=compact_bools, zero_empty=zero_empty)


def encode(value, contract=None, *, shared=True, dictionaries=True, version=1,
           delimiter=None, token_counter=None, delta=True, prefix_factor=True,
           compact_bools=True, zero_empty=True):
    """Serialize a JSON value without coercion, missing-field loss or key loss."""
    if version not in (1, 2):
        raise ValueError("version must be 1 or 2")
    if delimiter is not None and delimiter not in ("|", " ", ",", "\t"):
        raise ValueError("delimiter must be '|', ' ', ',', or '\\t'")
    contract = _contract(contract)
    _pack(value, contract["schema"])
    path = contract["record_path"]
    records = _at(value, path) if path is not None else [value]
    schema, fields = _row_schema(contract), _fields(_row_schema(contract))
    if version == 1:
        rows = []
        for index, row in enumerate(records):
            rows.append([_cell(_at(row, field["path"]) if _object_row(schema) else row,
                               field["schema"], f"$/{index}/{field['name']}") for field in fields])
        header = [contract["prefix"], "v=1", f"n={len(rows)}", "h=" + contract["schema_id"]]
        if path:
            envelope = _put(copy.deepcopy(value), path, [])
            header.append("m=" + _json(_pack(envelope, contract["schema"])))
        defaults = []
        if shared and len(rows) >= 3:
            for index in range(len(fields)):
                cell = rows[0][index]
                if all(row[index] == cell for row in rows[1:]):
                    # Factor only when the actual wire bytes become shorter.
                    cost = len(_escape(_json([index, cell])).encode("utf-8")) + 2
                    saving = len(rows) * (len(_escape(cell).encode("utf-8")) + 1)
                    if saving > cost + 4:
                        defaults.append([index, cell])
        if defaults:
            header.append("d=" + _json(defaults))
        skipped = {index for index, _ in defaults}
        codebooks = []
        encoded_columns = {}
        if dictionaries and len(rows) >= 6:
            for index, field in enumerate(fields):
                if index in skipped or field["schema"]["type"] != "string":
                    continue
                values = list(dict.fromkeys(row[index] for row in rows))
                # This is an explicitly transmitted per-document vocabulary, not
                # an inferred enum.  New values remain legal in future documents.
                if not 2 <= len(values) <= 64 or len(values) * 3 > len(rows):
                    continue
                if sum(len(value) for value in values) < 6 * len(values):
                    continue
                lookup = {value: position for position, value in enumerate(values)}
                column = [str(lookup[row[index]]) for row in rows]
                before = sum(len(_escape(row[index]).encode("utf-8")) for row in rows)
                overhead = len(_escape(_json([index, values])).encode("utf-8")) + 4
                after = sum(len(cell) for cell in column) + overhead
                if before - after > max(32, overhead // 3):
                    codebooks.append([index, values])
                    encoded_columns[index] = column
        if codebooks:
            header.append("e=" + _json(codebooks))
        lines = ["|".join(_escape(cell) for cell in header)]
        for row_index, row in enumerate(rows):
            cells = [encoded_columns[index][row_index] if index in encoded_columns else cell
                     for index, cell in enumerate(row) if index not in skipped]
            lines.append("|".join(_escape(cell) for cell in cells) if cells else "-")
        return "\n".join(lines)

    # ---- mini-domain/2 adaptive codec ----
    rows_raw = []
    for row in records:
        rows_raw.append([_at(row, field["path"]) if _object_row(schema) else row for field in fields])
    nrows = len(rows_raw)
    v1_cells = [[_cell(rows_raw[r][c], fields[c]["schema"], f"$/{r}/{fields[c]['name']}")
                 for c in range(len(fields))] for r in range(nrows)]
    defaults = []
    if shared and nrows >= 2:
        for index in range(len(fields)):
            cell = v1_cells[0][index]
            if all(v1_cells[r][index] == cell for r in range(1, nrows)):
                cost = len(_escape(_json([index, cell])).encode("utf-8")) + 2
                saving = nrows * (len(_escape(cell).encode("utf-8")) + 1)
                if saving > cost + 2:
                    defaults.append([index, cell])
    skipped = {index for index, _ in defaults}

    bool_cols = [i for i, f in enumerate(fields) if i not in skipped and f["schema"]["type"] == "boolean"]
    use_bool = bool(compact_bools and bool_cols and nrows * len(bool_cols) >= 2)

    delta_cols = []
    if delta and nrows >= 3:
        for index, field in enumerate(fields):
            if index in skipped or field["schema"]["type"] != "integer":
                continue
            orig_chars = 0
            delta_chars = 0
            prev = None
            count_int = 0
            for r in range(nrows):
                val = rows_raw[r][index]
                if type(val) is int:
                    count_int += 1
                    orig_chars += len(str(val))
                    dv = val if prev is None else (val - prev)
                    prev = val
                    delta_chars += len(str(dv))
            if count_int >= 3 and delta_chars + 8 < orig_chars:
                delta_cols.append(index)
    delta_set = set(delta_cols)

    # Zero-empty check across remaining optional/nullable cells (excluding delta & defaults)
    empty_count = 0
    if zero_empty:
        for r in range(nrows):
            for c in range(len(fields)):
                val = rows_raw[r][c]
                if c not in skipped and (val is MISSING or (val is None and not fields[c]["optional"])):
                    empty_count += 1
    use_zero = bool(zero_empty and empty_count >= 3)

    codebooks_list = []
    codebooks_map = {}
    if dictionaries and nrows >= 4:
        for index, field in enumerate(fields):
            if index in skipped or index in delta_set:
                continue
            # Use canonical unescaped cell tokens for vocabulary lookup
            col_cells = [v1_cells[r][index] for r in range(nrows)]
            values = list(dict.fromkeys(col_cells))
            max_vocab = min(128, max(2, nrows // 2))
            if not 2 <= len(values) <= max_vocab:
                continue
            if use_zero and all(v in ("?", "~") or len(v) < 2 for v in values):
                continue
            lookup = {val: pos for pos, val in enumerate(values)}
            column = [str(lookup[c]) for c in col_cells]
            before = sum(0 if (use_zero and col_cells[r] in ("?", "~")) else len(col_cells[r].encode("utf-8"))
                         for r in range(nrows))
            overhead = len(_escape(_json([index, values])).encode("utf-8")) + 4
            after = sum(len(c) for c in column) + overhead
            if before - after > max(16, overhead // 3):
                codebooks_list.append([index, values])
                codebooks_map[index] = (values, column)

    prefixes_list = []
    prefix_map = {}
    if prefix_factor and nrows >= 3:
        for index, field in enumerate(fields):
            if index in skipped or index in delta_set or index in codebooks_map or field["schema"]["type"] != "string":
                continue
            strs = [rows_raw[r][index] for r in range(nrows) if isinstance(rows_raw[r][index], str)]
            if len(strs) < 3 or len(strs) * 2 < nrows:
                continue
            s0, s1 = min(strs), max(strs)
            k = 0
            limit = min(len(s0), len(s1))
            while k < limit and s0[k] == s1[k]:
                k += 1
            lcp = s0[:k]
            if len(lcp) < 3:
                continue
            header_cost = len(_escape(_json([index, lcp])).encode("utf-8")) + 3
            if len(strs) * len(lcp) > header_cost + 10:
                prefixes_list.append([index, lcp])
                prefix_map[index] = lcp

    active_indices = [i for i in range(len(fields)) if i not in skipped]
    tail_scores = []
    for index in active_indices:
        if (index not in delta_set and index not in codebooks_map and index not in prefix_map
                and fields[index]["schema"]["type"] == "string"):
            hits = sum(
                1 for r in range(nrows)
                if isinstance(rows_raw[r][index], str) and (" " in rows_raw[r][index] or '"' in rows_raw[r][index])
            )
            if hits >= 2:
                tail_scores.append((hits, index))
    tail_scores.sort(reverse=True)
    tail_candidates = [idx for _, idx in tail_scores[:2]]

    sep, tail_col = _select_delimiter_v2(
        rows_raw, fields, active_indices, dict(defaults), codebooks_map, prefix_map,
        delta_set, tail_candidates, use_bool, use_zero, explicit_sep=delimiter, token_counter=token_counter,
    )

    row_order = [i for i in active_indices if i != tail_col] + ([tail_col] if tail_col is not None else [])
    header = [contract["prefix"], "v=2.0", f"n={nrows}", "h=" + contract["schema_id"]]
    if path:
        envelope = _put(copy.deepcopy(value), path, [])
        header.append("m=" + _json(_pack(envelope, contract["schema"])))
    if sep != "|":
        header.append("s=" + _DELIM_CODES[sep])
    if tail_col is not None:
        header.append(f"tl={tail_col}")
    if use_bool:
        header.append("b=1")
    if use_zero:
        header.append("z=1")
    if defaults:
        header.append("d=" + _json(defaults))
    if prefixes_list:
        header.append("p=" + _json(prefixes_list))
    if delta_cols:
        header.append("dt=" + _json(delta_cols))
    if codebooks_list:
        header.append("e=" + _json(codebooks_list))

    lines = ["|".join(_escape(cell) for cell in header)]
    deltas_prev = {idx: None for idx in delta_set}
    for r_idx in range(nrows):
        if not row_order:
            lines.append("-")
            continue
        row = rows_raw[r_idx]
        cells = []
        for pos, col_idx in enumerate(row_order):
            last_phys = (pos == len(row_order) - 1)
            is_tail = (col_idx == tail_col)
            if col_idx in codebooks_map:
                cells.append(codebooks_map[col_idx][1][r_idx])
                continue
            val = row[col_idx]
            if col_idx in delta_set and type(val) is int:
                prev = deltas_prev[col_idx]
                enc_val = val if prev is None else (val - prev)
                deltas_prev[col_idx] = val
                cells.append(str(enc_val))
                continue
            cells.append(_cell_v2(
                val, fields[col_idx]["schema"], f"$/{r_idx}/{fields[col_idx]['name']}",
                sep=sep, zero_empty=use_zero, compact_bools=use_bool,
                prefix_strip=prefix_map.get(col_idx), is_tail=is_tail,
                last_physical=last_phys, field_optional=fields[col_idx]["optional"],
            ))
        lines.append(sep.join(cells))
    return "\n".join(lines)


def _decode(text, contract, *, allow_count=False):
    contract = _contract(contract)
    if "\r" in text or text.startswith("\ufeff"):
        raise DomainError("D_ENVELOPE", "normalize CRLF/BOM with the repair command", line=1)
    lines = text.split("\n")
    if lines and lines[-1] == "":
        lines.pop()
    if not lines or not lines[0]:
        raise DomainError("D_HEADER", "missing header", line=1)
    cells = _split(lines[0], 1)
    if cells[0] != contract["prefix"]:
        raise DomainError("D_PREFIX", f"expected prefix {contract['prefix']}", line=1)
    header = {}
    all_header_keys = {"v", "n", "h", "m", "d", "e", "s", "tl", "b", "z", "p", "dt"}
    for cell in cells[1:]:
        key, sep_eq, value = cell.partition("=")
        if not sep_eq or key in header or key not in all_header_keys:
            raise DomainError("D_HEADER", f"unknown, duplicate or malformed header field {key}", line=1)
        header[key] = value
    version = header.get("v")
    if version not in ("1", "2.0") or header.get("h") != contract["schema_id"]:
        raise DomainError("D_CONTRACT", "wrong profile version or schema fingerprint; use the matching generated bundle", line=1)
    if version == "1" and any(k in header for k in ("s", "tl", "b", "z", "p", "dt")):
        raise DomainError("D_HEADER", "mini-domain/1 header cannot use mini-domain/2 extensions", line=1)
    if not re.fullmatch(r"0|[1-9][0-9]*", header.get("n", "")):
        raise DomainError("D_COUNT", "n must be a non-negative integer", line=1)
    sep = "|"
    if "s" in header:
        if header["s"] not in _DELIMITERS:
            raise DomainError("D_HEADER", f"unsupported delimiter tag {header['s']}", line=1)
        sep = _DELIMITERS[header["s"]]
    compact_bools = False
    if "b" in header:
        if header["b"] != "1":
            raise DomainError("D_HEADER", "b flag must be 1", line=1)
        compact_bools = True
    zero_empty = False
    if "z" in header:
        if header["z"] != "1":
            raise DomainError("D_HEADER", "z flag must be 1", line=1)
        zero_empty = True

    schema = _row_schema(contract)
    fields = _fields(schema)
    object_rows = _object_row(schema)
    defaults = {}
    if "d" in header:
        try:
            pairs = _strict_json(header["d"])
            if not isinstance(pairs, list):
                raise ValueError("d must be an array of [column index, encoded cell] pairs")
            for pair in pairs:
                if not isinstance(pair, list) or len(pair) != 2:
                    raise ValueError("malformed shared cell")
                index, cell = pair
                if type(index) is not int or not 0 <= index < len(fields) or index in defaults or not isinstance(cell, str):
                    raise ValueError("invalid or duplicate shared column")
                item = _uncell(cell, fields[index]["schema"], "$/shared")
                if item is MISSING and not fields[index]["optional"]:
                    raise ValueError("shared columns cannot omit a required field")
                defaults[index] = (cell, item)
        except (ValueError, TypeError) as exc:
            raise DomainError("D_HEADER", str(exc), line=1) from exc

    prefixes = {}
    if "p" in header:
        try:
            pairs = _strict_json(header["p"])
            if not isinstance(pairs, list):
                raise ValueError("p must be an array of [column index, prefix string] pairs")
            for pair in pairs:
                if not isinstance(pair, list) or len(pair) != 2:
                    raise ValueError("malformed prefix pair")
                index, prefix_str = pair
                if (type(index) is not int or not 0 <= index < len(fields) or index in defaults or index in prefixes
                        or fields[index]["schema"]["type"] != "string" or not isinstance(prefix_str, str) or not prefix_str):
                    raise ValueError("invalid or duplicate prefix column")
                prefixes[index] = prefix_str
        except (ValueError, TypeError) as exc:
            raise DomainError("D_HEADER", str(exc), line=1) from exc

    deltas = {}
    if "dt" in header:
        try:
            col_ids = _strict_json(header["dt"])
            if not isinstance(col_ids, list):
                raise ValueError("dt must be an array of integer column indices")
            for index in col_ids:
                if (type(index) is not int or not 0 <= index < len(fields) or index in defaults
                        or index in deltas or fields[index]["schema"]["type"] != "integer"):
                    raise ValueError("invalid or duplicate delta column")
                deltas[index] = None
        except (ValueError, TypeError) as exc:
            raise DomainError("D_HEADER", str(exc), line=1) from exc

    codebooks = {}
    if "e" in header:
        try:
            pairs = _strict_json(header["e"])
            if not isinstance(pairs, list):
                raise ValueError("e must be an array of [column index, cell vocabulary] pairs")
            for pair in pairs:
                if not isinstance(pair, list) or len(pair) != 2:
                    raise ValueError("malformed vocabulary")
                index, values = pair
                if (type(index) is not int or not 0 <= index < len(fields) or index in defaults
                        or index in codebooks or index in prefixes or index in deltas):
                    raise ValueError("invalid, shared or duplicate vocabulary column")
                if version == "1" and fields[index]["schema"]["type"] != "string":
                    raise ValueError("invalid, shared or duplicate vocabulary column")
                if not isinstance(values, list) or not values or not all(isinstance(value, str) for value in values) or len(set(values)) != len(values):
                    raise ValueError("vocabulary must contain unique encoded string cells")
                decoded_values = []
                for cell in values:
                    item = _uncell(cell, fields[index]["schema"], "$/vocabulary")
                    if item is MISSING and not fields[index]["optional"]:
                        raise ValueError("vocabulary cannot omit a required field")
                    decoded_values.append((cell, item))
                codebooks[index] = decoded_values
        except (ValueError, TypeError) as exc:
            raise DomainError("D_HEADER", str(exc), line=1) from exc

    tail_col = None
    if "tl" in header:
        if not re.fullmatch(r"0|[1-9][0-9]*", header["tl"]):
            raise DomainError("D_HEADER", "tl must be a non-negative integer", line=1)
        tail_col = int(header["tl"])
        if (tail_col >= len(fields) or tail_col in defaults or tail_col in codebooks
                or tail_col in deltas or fields[tail_col]["schema"]["type"] != "string"):
            raise DomainError("D_HEADER", "tl must name an active non-constant string column", line=1)

    active_indices = [index for index in range(len(fields)) if index not in defaults]
    row_order = [index for index in active_indices if index != tail_col] + ([tail_col] if tail_col is not None else [])
    expected = len(row_order)
    rows = []
    for lineno, line in enumerate(lines[1:], 2):
        try:
            if expected == 0 and line == "-":
                row_cells = []
            elif expected == 0:
                row_cells = _split_v2(line, lineno, sep)
            else:
                row_cells = _split_v2(line, lineno, sep, max_cells=(expected if tail_col is not None else None))
            if len(row_cells) != expected:
                raise DomainError("D_ARITY", f"expected {expected} cells, received {len(row_cells)}")
            decoded_by_col = {}
            for index, raw in zip(row_order, row_cells):
                field = fields[index]
                path_str = f"$/{lineno - 2}/{field['name']}"
                if raw == "" and version == "2.0":
                    if not zero_empty:
                        raise DomainError("D_VALUE", "empty cell requires z=1", path_str)
                    if field["optional"]:
                        item = MISSING
                    elif field["schema"].get("nullable") or field["schema"]["type"] == "json":
                        item = None
                    else:
                        raise DomainError("D_REQUIRED", f"empty cell not allowed for required field {field['name']}", path_str)
                elif index in codebooks:
                    vocab = codebooks[index]
                    if not re.fullmatch(r"0|[1-9][0-9]*", raw) or int(raw) >= len(vocab):
                        raise DomainError("D_ENUM", f"invalid vocabulary index for {field['name']}", path_str)
                    raw_cell, item = vocab[int(raw)]
                    if isinstance(item, (dict, list)):
                        item = _uncell(raw_cell, field["schema"], path_str)
                else:
                    item = _uncell(raw, field["schema"], path_str, compact_bools=compact_bools)
                    if index in prefixes and isinstance(item, str):
                        item = prefixes[index] + item
                    if index in deltas and type(item) is int:
                        prev = deltas[index]
                        item = item if prev is None else (prev + item)
                        deltas[index] = item
                decoded_by_col[index] = item

            row = _object_skeleton(schema) if object_rows else {}
            for index, field in enumerate(fields):
                if index in defaults:
                    raw, item = defaults[index]
                    if isinstance(item, (dict, list)):
                        item = _uncell(raw, field["schema"], f"$/{lineno-2}/{field['name']}")
                else:
                    item = decoded_by_col[index]
                if item is MISSING:
                    if not field["optional"]:
                        raise DomainError("D_REQUIRED", f"missing required field {field['name']}")
                else:
                    if object_rows:
                        _put(row, field["path"], item)
                    else:
                        row[field["name"]] = item
            rows.append(row if object_rows else row["$value"])
        except DomainError as exc:
            exc.line = lineno
            raise
    if not allow_count and int(header["n"]) != len(rows):
        raise DomainError("D_COUNT", f"header declares {header['n']} records, found {len(rows)}; verify that no records are missing", line=1)
    path = contract["record_path"]
    if path:
        if "m" not in header:
            raise DomainError("D_HEADER", "missing wrapper metadata m", line=1)
        try:
            envelope = _unpack(_strict_json(header["m"]), contract["schema"])
        except (ValueError, TypeError) as exc:
            if isinstance(exc, DomainError):
                raise
            raise DomainError("D_HEADER", str(exc), line=1) from exc
        if _at(envelope, path) != []:
            raise DomainError("D_HEADER", "wrapper record collection must be empty in m", line=1)
        result = _put(envelope, path, rows)
    elif path == []:
        if "m" in header:
            raise DomainError("D_HEADER", "root arrays cannot carry wrapper metadata", line=1)
        result = rows
    else:
        if len(rows) != 1 or "m" in header:
            raise DomainError("D_COUNT", "scalar/object roots require exactly one record and no m", line=1)
        result = rows[0]
    _pack(result, contract["schema"])
    return result


def decode(text, contract=None):
    """Validate and reconstruct the original JSON shape; never coerce values."""
    return _decode(text, _contract(contract))


def dumps(value, contract=None):
    return encode(value, contract)


def loads(text, contract=None):
    return decode(text, contract)


def diagnose(text, contract=None):
    contract = _contract(contract)
    try:
        value = decode(text, contract)
        path = contract["record_path"]
        count = len(_at(value, path)) if path is not None else 1
        return {"ok": True, "profile": PROFILE, "records": count, "recoverable_records": count,
                "valid_lines": list(range(2, count + 2)), "invalid_lines": [], "errors": []}
    except DomainError as exc:
        initial = exc
    errors, valid_lines, invalid_lines = [], [], []
    lines = text.split("\n")
    if lines and lines[-1] == "":
        lines.pop()
    if initial.code == "D_COUNT":
        # Validate the whole prefix, including its shared fields and metadata,
        # before reporting the rows as recoverable.
        try:
            _decode(text, contract, allow_count=True)
        except DomainError:
            pass
        else:
            errors.append(initial.to_dict())
            valid_lines = list(range(2, len(lines) + 1))
    # Isolate records only once the complete header was accepted.  Each test
    # uses the same schema, wrapper and shared columns, with n=1 for that row.
    if not errors and (initial.line >= 2 or initial.code == "D_COUNT"):
        try:
            header = _split(lines[0], 1)
            single_header = "|".join(_escape("n=1" if cell.startswith("n=") else cell) for cell in header)
            for lineno, line in enumerate(lines[1:], 2):
                try:
                    _decode(single_header + "\n" + line, contract)
                    valid_lines.append(lineno)
                except DomainError as error:
                    if error.line not in (0, 2):
                        raise initial
                    error.line = lineno
                    errors.append(error.to_dict())
                    invalid_lines.append(lineno)
            if initial.code == "D_COUNT":
                errors.insert(0, initial.to_dict())
        except DomainError:
            errors = [initial.to_dict()]
            valid_lines, invalid_lines = [], []
    if not errors:
        errors = [initial.to_dict()]
    if invalid_lines:
        prompt = ("Using the original task and attached .mini contract, return only a JSON object mapping these physical line "
                  "numbers to corrected single-line .mini records: " + _json(invalid_lines) + ". Preserve every other line. "
                  "Never invent unavailable facts. Errors: " + _json(errors))
    else:
        prompt = ("Using the original task and attached .mini contract, verify completeness and regenerate the response. "
                  "Never invent missing facts or records. Errors: " + _json(errors))
    return {"ok": False, "profile": PROFILE, "errors": errors, "valid_lines": valid_lines,
            "invalid_lines": invalid_lines, "recoverable_records": len(valid_lines), "repair_prompt": prompt}


def apply_replacements(text, replacements, contract=None):
    """Merge externally corrected bad lines, then validate the whole document.

    Only lines diagnosed as invalid may change.  This function is the explicit
    model/human repair boundary: the library itself generates no semantic data.
    """
    contract = _contract(contract)
    report = diagnose(text, contract)
    allowed = set(report["invalid_lines"])
    if not isinstance(replacements, dict) or not replacements:
        raise DomainError("D_REPAIR", "provide a non-empty JSON object mapping line numbers to replacement strings")
    lines = text.split("\n")
    for key, replacement in replacements.items():
        try:
            line = int(key)
        except (TypeError, ValueError):
            raise DomainError("D_REPAIR", f"invalid line number {key}") from None
        if str(line) != str(key) or line not in allowed:
            raise DomainError("D_REPAIR", f"line {key} was not diagnosed as invalid")
        if not isinstance(replacement, str) or "\n" in replacement or "\r" in replacement:
            raise DomainError("D_REPAIR", "each replacement must be one physical line", line=line)
        lines[line - 1] = replacement
    corrected = "\n".join(lines)
    decode(corrected, contract)
    return corrected


def repair(text, contract=None, *, fix_count=False):
    """Repair unambiguous transport issues. Count changes require explicit opt-in.

    Missing values, invalid types and unknown facts are never guessed.  Failed
    repair returns diagnostics and a regeneration prompt, not fabricated JSON.
    """
    contract = _contract(contract)
    changes = []
    if text.startswith("\ufeff"):
        text = text[1:]
        changes.append("removed UTF-8 BOM")
    if "\r\n" in text:
        text = text.replace("\r\n", "\n")
        changes.append("normalized CRLF to LF")
    heading_end = text.find("\n")
    if heading_end >= 0 and text[:heading_end] in _PROMPT_HEADINGS.values():
        text = text[heading_end + 1:].lstrip("\n")
        changes.append("removed echoed .mini prompt heading")
    stripped = text.strip("\n")
    fence = re.fullmatch(r"```(?:mini|text)?[ \t]*\n([\s\S]*?)\n```", stripped)
    opened = re.match(r"```(?:mini|text)?[ \t]*\n", stripped)
    if fence:
        text = fence.group(1)
        changes.append("removed complete Markdown code fence")
    elif opened and "\n```" not in stripped[opened.end() - 1:]:
        # A response cut by the output limit inside a fenced block never reaches its closing fence.
        text = stripped[opened.end():]
        changes.append("removed unclosed Markdown code fence")
    # A response saved by a shell or an editor can end with extra empty lines (PowerShell Out-File appends CRLF).
    # An empty physical line never encodes a record (a row without cells is written as "-"), so the extra lines
    # are transport whitespace: keep only the optional final LF of the profile.
    trimmed = re.sub(r"\n{2,}\Z", "\n", text)
    if trimmed != text:
        text = trimmed
        changes.append("removed trailing blank lines")
    report = diagnose(text, contract)
    invalid = set(report["invalid_lines"])
    if invalid and all(error["code"] == "D_ARITY" for error in report["errors"]):
        lines = text.split("\n")
        if all(lines[number - 1].endswith("|") for number in invalid):
            # The empty cell after a final separator is surplus only if
            # the whole document then matches the unchanged schema and count.
            candidate = "\n".join(line[:-1] if number in invalid else line
                                  for number, line in enumerate(lines, 1))
            checked = diagnose(candidate, contract)
            if checked["ok"]:
                text, report = candidate, checked
                changes.append("removed surplus trailing row separators")
    if fix_count and not report["ok"] and report["errors"][0]["code"] == "D_COUNT":
        # Validate every field and the full wrapper before changing n.  This
        # cannot establish whether records were omitted by a model; the caller
        # explicitly chooses to accept the records that are actually present.
        try:
            value = _decode(text, contract, allow_count=True)
            text = encode(value, contract)
            changes.append("reset n to validated present records (caller accepted record count)")
            report = diagnose(text, contract)
        except DomainError:
            pass
    return {"ok": report["ok"], "text": text, "changes": changes, "diagnostics": report,
            **({"repair_prompt": report["repair_prompt"]} if not report["ok"] else {})}


def json_schema(contract):
    def convert(node):
        kind = node["type"]
        if kind == "json":
            return {}
        result = {"type": [kind, "null"] if node.get("nullable") else kind}
        if kind == "object":
            result.update(properties={field["name"]: convert(field["schema"]) for field in node["fields"]},
                          required=[field["name"] for field in node["fields"] if not field["optional"]],
                          additionalProperties=False)
        elif kind == "array":
            result["items"] = convert(node["items"])
        return result
    return {"$schema": "https://json-schema.org/draft/2020-12/schema", "title": contract["prefix"], **convert(contract["schema"])}


def make_lean_prompt(contract, lang="en", example=None):
    """Schema-pruned, anti-reasoning prompt (~75% fewer input tokens, avoids CoT inflation)."""
    contract = _contract(contract)
    row_schema = _row_schema(contract)
    fields = _fields(row_schema)
    path = contract["record_path"]
    has_optional = any(f["optional"] for f in fields)
    has_nullable = any(f["schema"].get("nullable") for f in fields)
    has_nested = any(f["schema"]["type"] in ("object", "array", "json") for f in fields)
    cols = ", ".join(
        f"{f['name']}{'(opt)' if f['optional'] else ''}:{'json' if f['schema']['type'] == 'json' else f['schema']['type']}"
        for f in fields
    )
    heading = _PROMPT_HEADINGS["lean_es" if lang == "es" else "lean_en"]
    header = f"{contract['prefix']}|v=1|n=<count>|h={contract['schema_id']}"
    if path:
        header += "|m=<wrapper_positional_json_with_records_as_[]>"
    if lang == "es":
        lines = [
            heading,
            f"Devuelve SOLO líneas .mini sin Markdown, explicaciones ni razonamiento.",
            f"Cabecera: `{header}`",
            f"Columnas ({len(fields)}, sep `|`): {cols}",
            "Cadenas sin comillas salvo vacía `\"\"` o `?`/`~`/`\"` inicial. Escapa `\\\\`, `\\|`, `\\n`.",
        ]
        if has_optional or has_nullable:
            parts = []
            if has_optional:
                parts.append("`?`=opcional ausente")
            if has_nullable:
                parts.append("`~`=null")
            lines.append(" / ".join(parts) + ".")
        if has_nested:
            lines.append("Objetos/arrays no aplanados en JSON compacto; `json` envuelto `[valor]`.")
    else:
        lines = [
            heading,
            "Output ONLY raw .mini lines. No Markdown fences, preamble, or commentary.",
            f"Header: `{header}`",
            f"Columns ({len(fields)}, sep `|`): {cols}",
            "Strings are bare unless empty `\"\"` or starting with `?`/`~`/`\"`. Escape `\\\\`, `\\|`, `\\n`.",
        ]
        if has_optional or has_nullable:
            parts = []
            if has_optional:
                parts.append("`?`=absent optional")
            if has_nullable:
                parts.append("`~`=null")
            lines.append(" / ".join(parts) + ".")
        if has_nested:
            lines.append("Nested arrays/objects use compact JSON; `json` nodes wrap `[value]`.")
    if example is not None:
        sample = copy.deepcopy(example)
        if path is not None:
            sample = _put(sample, path, _at(sample, path)[:1])
        lines.append("Example:\n" + encode(sample, contract, shared=False, dictionaries=False))
    return "\n".join(lines) + "\n"


def make_prompt(contract, lang="en", example=None, *, lean=False):
    if lean:
        return make_lean_prompt(contract, lang=lang, example=example)
    contract = _contract(contract)
    fields = _fields(_row_schema(contract))
    if lang == "es":
        intro = "Devuelve solamente un documento .mini conforme a este contrato, sin Markdown ni explicaciones."
        rules = [
            "Una cabecera seguida de una línea por registro. Conserva el orden de columnas indicado.",
            "Usa ? sólo para un campo opcional ausente y ~ para null; no son equivalentes. No inventes valores ausentes.",
            'Las cadenas se escriben sin comillas; cadena vacía, ? literal, ~ literal o cadena que empieza con comillas usa una cadena JSON.',
            r"Escapa barra inversa como \\, separador como \|, salto de línea como \n y retorno como \r. No recortes espacios.",
            "Los objetos obligatorios no-nullables se aplanan en columnas según las rutas indicadas. Otros objetos anidados son arrays posicionales según schema; {} representa un miembro opcional ausente.",
            "Números y booleanos usan sintaxis JSON.",
            'Las listas contienen valores transformados recursivamente. Un nodo de tipo json envuelve su valor en [valor]; null sigue siendo null.',
            "No agregues claves ni cambies tipos. Si faltan muestras para un tipo, pide reconstruir el contrato con más ejemplos.",
            "No uses d salvo que agrupes columnas constantes: d es un array JSON de [índice de columna, celda codificada] y esas columnas se omiten de todas las filas.",
            "Opcionalmente e=[ [índice de columna,[celda0,celda1,...]],...] declara un diccionario de cadenas del documento; la columna usa índices enteros desde 0. Una columna no puede estar en d y e.",
            "Si no queda ninguna columna en una fila, escribe -. n cuenta todas las filas, incluso esas filas vacías.",
        ]
    else:
        intro = "Return only one .mini document matching this contract, without Markdown or explanation."
        rules = [
            "One header followed by one physical line per record. Preserve the listed column order.",
            "Use ? only for an absent optional field and ~ for null; they are different. Never invent missing values.",
            'Strings are bare; empty strings, literal ?, literal ~ and strings starting with a quote must use a JSON string.',
            r"Escape backslash as \\, pipe as \|, newline as \n and carriage return as \r. Never trim spaces.",
            "Required non-nullable objects are flattened into columns using the listed paths. Other nested objects become positional arrays according to schema; {} represents an absent optional member.",
            "Numbers and booleans use JSON syntax.",
            "Lists contain recursively transformed values. A json-type node wraps its value as [value]; null remains null.",
            "Do not add keys or change types. Request a rebuilt contract with more samples when a needed structure was not observed.",
            "Omit d unless factoring constant columns: d is a JSON array of [column index, encoded cell] pairs; those columns disappear from every row.",
            "Optional e=[[column index,[cell0,cell1,...]],...] declares per-document string vocabularies; each column then uses zero-based integer indices. A column cannot appear in both d and e.",
            "Write - for a row with no remaining columns. n counts all rows, including these empty rows.",
        ]
    heading = _PROMPT_HEADINGS["es" if lang == "es" else "en"]
    header = f"{contract['prefix']}|v=1|n=<record count>|h={contract['schema_id']}"
    path = contract["record_path"]
    extra = ""
    if path:
        extra = ("\nLa cabecera requiere m=<JSON posicional del documento completo con la colección de registros sustituida por []>. "
                 if lang == "es" else "\nThe header requires m=<positional JSON of the complete wrapper with the record collection replaced by []>. ")
        extra += "record_path=" + _json(path) + ". Escape m using the same field rules."
    text = f"{heading}\n\n{intro}\n\nProfile: {PROFILE}\nHeader: `{header}`{extra}\n\n"
    text += "\n".join(f"{index+1}. {rule}" for index, rule in enumerate(rules))
    text += "\n\nColumns (zero-based; paths use JSON Pointer escaping):\n" + "\n".join(f"{index}: {field['name']} ({field['schema']['type']}{', optional' if field['optional'] else ''})" for index, field in enumerate(fields))
    text += "\n\nSchema:\n```json\n" + _json(contract["schema"]) + "\n```\n"
    if example is not None:
        text += "\nExample / Ejemplo:\n```mini\n" + encode(example, contract) + "\n```\n"
    return text


_ROW_ATOM = re.compile(r'(?:"(?:[^"\\]|\\.)*"|\[[^\n]*\]|\{[^\n]*\}|[^ \t]+)(?:[ \t]+|$)')


def _flat_required_fields(contract, *, allow_nullable=False, allow_wrapped=False):
    row_schema = _row_schema(contract)
    if (not allow_wrapped and contract["record_path"] != []) or contract["record_path"] is None:
        raise DomainError("D_COMPACT_SCHEMA", "compact rows require a record array contract")
    if contract["schema"].get("nullable") or not _object_row(row_schema):
        raise DomainError("D_COMPACT_SCHEMA", "compact rows require an object record schema")
    fields = _fields(row_schema) if allow_nullable else row_schema.get("fields", [])
    if not allow_nullable and any(
        f["optional"] or f["schema"].get("nullable")
        or f["schema"]["type"] not in ("string", "integer", "number", "boolean")
        for f in fields
    ):
        raise DomainError("D_COMPACT_SCHEMA", "compact rows require a root array of flat, required, non-null scalars")
    return fields


def _compact_fields(contract, last_text_field, *, allow_nullable=False, allow_wrapped=False):
    fields = _flat_required_fields(contract, allow_nullable=allow_nullable, allow_wrapped=allow_wrapped)
    tail = next((f for f in fields if f["name"] == last_text_field and f["schema"]["type"] == "string"), None)
    if tail is None:
        raise DomainError("D_COMPACT_SCHEMA", "the last text field must name a string column")
    return [f for f in fields if f is not tail] + [tail]


def _compact_count(expected_records):
    if type(expected_records) is not int or expected_records < 0:
        raise DomainError("D_EXPECTED_COUNT", "compact rows require an explicit nonnegative record count")


def _bare_compact_text(value, *, is_tail=False):
    if not (isinstance(value, str) and bool(value) and value == value.strip(" \t")
            and not value.startswith(('"', "\ufeff")) and value not in ("?", "~")
            and not any(ord(ch) < 32 for ch in value)):
        return False
    if not is_tail and value.startswith(("[", "{")):
        return False
    return True


def _recommend_compact_tail(samples, contract):
    fields = contract["schema"].get("items", {}).get("fields", [])
    names = [field["name"] for field in reversed(fields) if field["schema"]["type"] == "string"]
    if not names:
        return None
    try:
        _compact_fields(contract, names[0])
    except DomainError:
        return None

    savings = dict.fromkeys(names, 0)
    for records in samples:
        for record in records:
            for name in names:
                value = record[name]
                if " " in value and _bare_compact_text(value, is_tail=True):
                    savings[name] += len(_json(value)) - len(value)
    return max(savings, key=savings.__getitem__)


def encode_rows(value, contract=None, *, last_text_field, allow_nullable=False,
                allow_wrapped=False, compact_bools=False):
    """Write space-separated model output for a fixed or extended flat domain contract."""
    contract = _contract(contract)
    fields = _compact_fields(contract, last_text_field, allow_nullable=allow_nullable, allow_wrapped=allow_wrapped)
    _pack(value, contract["schema"])
    path = contract["record_path"]
    records = _at(value, path) if path else value
    row_schema = _row_schema(contract)
    obj_rows = _object_row(row_schema)
    lines = []
    for row_idx, row in enumerate(records):
        cells = []
        for field in fields:
            cell = _at(row, field["path"]) if (obj_rows and "path" in field) else row.get(field["name"], MISSING)
            if cell is MISSING:
                cells.append("?")
            elif cell is None:
                cells.append("~")
            elif compact_bools and field["schema"]["type"] == "boolean":
                cells.append("1" if cell else "0")
            elif field["schema"]["type"] == "string":
                is_tail = (field is fields[-1])
                bare = _bare_compact_text(cell, is_tail=is_tail) and (is_tail or " " not in cell)
                cells.append(cell if bare else _json(cell))
            else:
                cells.append(_json(_pack(cell, field["schema"], f"$/{row_idx}/{field['name']}")))
        lines.append(" ".join(cells))
    return "\n".join(lines)


def decode_rows(text, contract=None, *, last_text_field, expected_records,
                allow_nullable=False, allow_wrapped=False, compact_bools=False):
    """Validate compact model rows and restore the application JSON values."""
    contract = _contract(contract)
    fields = _compact_fields(contract, last_text_field, allow_nullable=allow_nullable, allow_wrapped=allow_wrapped)
    _compact_count(expected_records)
    if not isinstance(text, str):
        raise DomainError("D_VALUE", "compact rows must be text")
    text = text.removeprefix("\ufeff").replace("\r\n", "\n").strip("\n")
    fence = re.fullmatch(r"```(?:mini|text)?[ \t]*\n([\s\S]*?)\n```", text)
    if fence:
        text = fence.group(1)
    lines = [(number, line.strip(" \t")) for number, line in enumerate(text.split("\n"), 1) if line.strip(" \t")]
    if len(lines) != expected_records:
        raise DomainError("D_EXPECTED_COUNT", f"expected {expected_records} records, received {len(lines)}")
    row_schema = _row_schema(contract)
    obj_rows = _object_row(row_schema)
    rows = []
    for line_no, line in lines:
        if "\r" in line:
            raise DomainError("D_VALUE", "encode line breaks inside strings as JSON escapes", line=line_no)
        cells, start = [], 0
        for field in fields[:-1]:
            token = _ROW_ATOM.match(line, start)
            if token is None:
                raise DomainError("D_ARITY", f"missing column {field['name']}", line=line_no)
            cells.append(token.group().rstrip(" \t"))
            start = token.end()
        cells.append(line[start:])
        row = _object_skeleton(row_schema) if obj_rows else {}
        for field, cell in zip(fields, cells):
            name, schema = field["name"], field["schema"]
            path = f"$/{line_no - 1}/{name}"
            if not cell:
                raise DomainError("D_VALUE", "use a quoted JSON string for empty text", path, line_no)
            try:
                value = _uncell(cell, schema, path, compact_bools=compact_bools)
                if value is MISSING:
                    if not field["optional"]:
                        raise DomainError("D_REQUIRED", f"missing required field {name}", path, line_no)
                else:
                    if obj_rows and "path" in field:
                        _put(row, field["path"], value)
                    else:
                        row[name] = value
            except ValueError as exc:
                message = exc.message if isinstance(exc, DomainError) else str(exc)
                raise DomainError("D_VALUE", message, path, line_no) from exc
        rows.append(row)
    return rows


def make_rows_prompt(contract, *, last_text_field, expected_records, lang="en",
                     allow_nullable=False, allow_wrapped=False, compact_bools=False):
    """Describe compact rows without sending the document header or schema JSON."""
    contract = _contract(contract)
    fields = _compact_fields(contract, last_text_field, allow_nullable=allow_nullable, allow_wrapped=allow_wrapped)
    _compact_count(expected_records)
    labels = [f["name"] if re.fullmatch(r"[\w-]+", f["name"]) else _json(f["name"]) for f in fields]
    names, tail = " ".join(labels), labels[-1]
    types = " ".join(
        f"{name}={'0/1' if compact_bools and f['schema']['type'] == 'boolean' else f['schema']['type']}"
        for name, f in zip(labels, fields) if f["schema"]["type"] != "string"
    )
    if lang == "es":
        text = (f"Emite {expected_records} fila(s), una por línea, sin cabecera. Separa con espacios.\n"
                f"Orden obligatorio {names}. {tail} va al final y ocupa el resto de la línea.\n"
                "Usa cadenas JSON para texto vacío, controles, comilla inicial, espacios al borde "
                "o espacios en el texto de columnas previas.\n")
    else:
        text = (f"Emit {expected_records} row(s), one per line, without a header. Separate with spaces.\n"
                f"Required column order {names}. {tail} comes last and takes the rest of the line.\n"
                "Use JSON strings for empty text, controls, a leading quote, spaces at either end, "
                "or spaces within any column before the last.\n")
    if allow_nullable:
        text += ("Usa ? para ausente y ~ para null.\n" if lang == "es" else "Use ? for omitted optional and ~ for null.\n")
    if types:
        text += types + "\n"
    return text


def positional_json_request(task, contract=None, *, expected_records, lang="en", allow_nullable=False):
    """Build instructions and a provider schema for compact JSON tuples."""
    fields = _flat_required_fields(_contract(contract), allow_nullable=allow_nullable, allow_wrapped=allow_nullable)
    _compact_count(expected_records)
    width = len(fields)
    names = ", ".join(field["name"] if re.fullmatch(r"[\w-]+", field["name"]) else _json(field["name"])
                      for field in fields)
    def _prefix_item(field):
        st = field["schema"]
        if st["type"] == "json":
            return {}
        return {"type": [st["type"], "null"]} if st.get("nullable") else {"type": st["type"]}
    schema = {
        "type": "array", "minItems": expected_records, "maxItems": expected_records,
        "items": {"type": "array", "minItems": width, "maxItems": width,
                  "prefixItems": [_prefix_item(field) for field in fields]},
    }
    if lang == "es":
        prompt = (f"Devuelve {expected_records} filas en un array JSON de arrays, sin claves. "
                  f"Orden de cada fila: {names}. Conserva los valores originales de los IDs.")
    else:
        prompt = (f"Return {expected_records} rows as a JSON array of arrays, without keys. "
                  f"Order of each row: {names}. Preserve the original ID values.")
    return {"prompt": prompt + "\n" + task, "schema": schema}


def decode_positional_json(text, contract=None, *, expected_records):
    """Validate positional JSON and restore the named fields from the domain contract."""
    contract = _contract(contract)
    _flat_required_fields(contract)
    _compact_count(expected_records)
    try:
        value = _strict_json(text)
    except (ValueError, TypeError) as exc:
        raise DomainError("D_VALUE", f"invalid positional JSON: {exc}") from exc
    if not isinstance(value, list):
        raise DomainError("D_TYPE", "expected an array of rows")
    if len(value) != expected_records:
        raise DomainError("D_EXPECTED_COUNT", f"expected {expected_records} records, received {len(value)}")
    return _unpack(value, contract["schema"])


# Wrappers load the adjacent parser.py by path: Windows builds of Python 3.9
# compile in the deprecated ``parser`` module, which shadows ``from parser import``.
_WRAPPER_IMPORT = (
    "import importlib.util\nimport sys\nfrom pathlib import Path\n"
    "_spec = importlib.util.spec_from_file_location(\"_mini_bundle_parser\", Path(__file__).resolve().with_name(\"parser.py\"))\n"
    "_module = importlib.util.module_from_spec(_spec)\n"
    "sys.modules[_spec.name] = _module\n"
    "_spec.loader.exec_module(_module)\n"
    "main = _module.main\n"
)


def build_bundle(samples, prefix="data", out=".mini", *, source_names=None, record_path=None, lang="es"):
    """Write a portable bundle to a new/empty directory; never overwrite work."""
    destination = Path(out)
    folder = destination.name
    if destination.exists() and (not destination.is_dir() or any(destination.iterdir())):
        raise DomainError("D_OUTPUT", f"output is not empty: {destination}; choose a new directory")
    contract = infer_contract(samples, prefix, record_path=record_path)
    example = copy.deepcopy(samples[0])
    path = contract["record_path"]
    if path is not None:
        example = _put(example, path, _at(example, path)[:2])
    # Verify every training document before producing an installable artifact.
    for sample in samples:
        if decode(encode(sample, contract), contract) != sample:
            raise DomainError("D_ROUNDTRIP", "internal round-trip verification failed")
    source = Path(__file__).read_text(encoding="utf-8")
    if lang not in ("es", "en"):
        raise ValueError("lang must be es or en")
    workflow_source = Path(__file__).with_name("workflow.py").read_text(encoding="utf-8")
    settings = {"language": lang}
    compact_tail = _recommend_compact_tail(samples, contract)
    if compact_tail is not None:
        settings["compact_last_text_field"] = compact_tail
    files = {
        "contract.json": json.dumps(contract, ensure_ascii=False, indent=2) + "\n",
        "schema.json": json.dumps(json_schema(contract), ensure_ascii=False, indent=2) + "\n",
        "prompt.en.md": make_prompt(contract, "en", example),
        "prompt.es.md": make_prompt(contract, "es", example),
        "prompt.lean.en.md": make_lean_prompt(contract, "en", example),
        "prompt.lean.es.md": make_lean_prompt(contract, "es", example),
        "parser.py": source,
        "validator.py": '"""Validate a .mini response with the bundled contract."""\n' + _WRAPPER_IMPORT + 'if __name__ == "__main__":\n    raise SystemExit(main(["validate", *sys.argv[1:]]))\n',
        "repair.py": '"""Repair only unambiguous transport wrappers; never fabricate data."""\n' + _WRAPPER_IMPORT + 'if __name__ == "__main__":\n    raise SystemExit(main(["repair", *sys.argv[1:]]))\n',
        "workflow.py": workflow_source,
        "workflow.mjs": Path(__file__).with_name("workflow.mjs").read_text(encoding="utf-8"),
        "setup.json": json.dumps(settings, ensure_ascii=False, indent=2) + "\n",
        "try-prompt.md": ("Genera exactamente 20 registros ficticios del mismo caso que la muestra para probar mi aplicación. "
                          "Respeta los campos, tipos y formato siguientes. Devuelve sólo .mini.\n\n" if lang == "es" else
                          "Generate exactly 20 fictional records for the same use case as the sample to test my application. "
                          "Follow the fields, types and output format below. Return only .mini.\n\n") + make_prompt(contract, lang, example),
        "example.json": json.dumps(example, ensure_ascii=False, indent=2) + "\n",
        "example.mini": encode(example, contract) + "\n",

    }
    # The short guide leads with the application flow; reference files remain available.
    files["GUIA.md"] = (
        f"# Tu .mini: {prefix}\n\nTu aplicación ya pide datos estructurados a una IA. "
        "Ahora la IA responde en .mini y el flujo devuelve el mismo JSON que tu aplicación necesita.\n\n"
        "## Qué ha creado setup\n\nUn contrato es la lista de campos, su orden y sus tipos: "
        "`contract.json` guarda esas reglas. Un prompt son instrucciones para la IA: tu código lee "
        "`prompt.es.md` y envía su contenido junto con la tarea. `workflow.py` conecta la generación "
        "con validación, Repair y conversión a JSON. Un registro es un objeto de tu JSON; en soporte, un ticket.\n\n"
        "## 1. Prueba sin API key\n\n`example.json` y `example.mini` representan los mismos datos. "
        "Copia el contenido de `try-prompt.md` a tu IA: ya incluye las reglas para generar 20 registros ficticios. "
        "No basta con dar una ruta a la IA: tu código debe leer el archivo e incluir su contenido.\n\n"
        f'```sh\npython "{folder}/validator.py" respuesta.mini\n'
        f'python "{folder}/repair.py" respuesta.mini --out corregida.mini\n'
        f'python "{folder}/workflow.py" corregida.mini --out resultado.json\n```\n\n'
        "Repair corrige envoltorios, BOM y saltos de línea (D_ENVELOPE). Si faltan datos o un tipo es incorrecto, "
        "hay que pedir una corrección a la IA. No inventa datos ni reduce el número esperado.\n\n"
        "## 2. Integra tu llamada existente\n\n"
        f'```sh\nmini integrate ruta/a/tu/app.py --bundle "{folder}" --lang es\n```\n\n'
        "Revisa `integration/INTEGRATE.md` y el diff preparado. Si la llamada es compatible (SDK de OpenAI con "
        "`chat.completions.create`, o `requests.post`/`httpx.post` a un endpoint de chat con `response_format` JSON, "
        "como DeepSeek), añade `--apply` para conectarlo automáticamente; se conserva una copia del archivo. "
        "Si la respuesta se corta por el límite de tokens, se conservan los registros completos y solo se piden los que faltan. "
        "Otros SDK o lenguajes reciben instrucciones concretas para tu IA de código.\n\n"
        "¿Todavía no tienes un flujo? Conserva este kit. Cuando crees el archivo que llama a la IA, "
        "ejecuta el comando anterior con la ruta de ese archivo. También puedes volver a usar `mini setup` "
        "para otro contrato en una carpeta nueva.\n\n"
        "`workflow.py` acepta cualquier función síncrona `generate(prompt) -> texto`. "
        "Conecta tu llamada con `Workflow(carpeta).run(generate, tarea, expected_records=20)`: "
        "incluye el prompt, valida, repara, pide como máximo una corrección, vuelve a validar y entrega JSON. "
        "Los errores pendientes bloquean la entrega. La API key sigue en tu proveedor; no se guarda en el toolkit.\n\n"
        "Python asíncrono: `await flow.run_async(generate, tarea)`. Node: importa `Workflow` desde `workflow.mjs` "
        "y usa `await flow.run(generate, tarea, {expectedRecords: 20})`; necesita Python para ejecutar el mismo parser.\n\n"
        "En otros lenguajes puedes ejecutar `python workflow.py -` y pasar la respuesta por stdin. "
        "Código 0: JSON por stdout. Código 1: diagnósticos por stderr; conecta el reintento en tu aplicación.\n\n"
        "`Workflow.last_run` permite inspeccionar lo ocurrido. Guarda un historial sólo si quieres conservar tus datos. "
        "La demostración de 20 tickets del paquete está en `examples/flujo-soporte`.\n\n"
        "## Referencia\n\n`contract.json`: campos y tipos. `parser.py`: conversión. `schema.json`: esquema JSON. "
        "`prompt.es.md` / `prompt.en.md`: instrucciones. `manifest.json`: hashes. "
        "Si cambian los datos, reconstruye el contrato con muestras representativas en una carpeta nueva. "
        "Mide el prompt, la salida y los reintentos antes de calcular el ahorro de dinero.\n"
    )
    files["README.md"] = (
        f"# Your .mini: {prefix}\n\nThe AI returns .mini; your application receives its usual JSON. "
        "Python 3.9+, standard library only.\n\n"
        "Setup creates `contract.json` (field order and types), `prompt.en.md` (instructions your code reads "
        "and sends to AI), and `workflow.py` (generation, validation, Repair and JSON delivery). "
        "A record means one object in your JSON: in support, one ticket.\n\n"
        "1. Inspect example.json and example.mini. Paste try-prompt.md into your AI: it includes the format and asks for 20 fictional records.\n"
        "2. Validate the reply; Repair removes safe wrappers, BOM and CRLF (D_ENVELOPE). Wrong types or missing data require a model correction.\n"
        f'3. Run `mini integrate path/to/app.py --bundle "{folder}" --lang en`; inspect integration/INTEGRATE.md and change.diff. '
        "Use --apply for the supported synchronous Python patterns (OpenAI SDK chat.completions.create, or requests.post/httpx.post "
        "to a chat endpoint with a JSON response_format, such as DeepSeek); other providers/languages get coding-AI instructions. "
        "A response cut by the output limit keeps its complete records and only the missing ones are requested.\n\n"
        "No workflow yet? Keep this toolkit. Once you create your AI call file, run the integration command above "
        "with its path. Setup also saves your selected next step at the end of this guide.\n\n"
        f'```sh\npython "{folder}/workflow.py" response.mini --out result.json\n```\n\n'
        "Import Workflow from workflow.py using importlib.util. `Workflow(bundle, lang='en').run(generate, task, expected_records=20)` "
        "accepts any synchronous text callback. It reads prompt.en.md, generates, validates, repairs, optionally requests one model correction, "
        "revalidates and returns JSON-compatible data. last_run holds the inspectable trace. Pending errors block delivery. "
        "Keep credentials with your provider and disable its JSON-only output mode.\n\n"
        "Async Python: `await flow.run_async(generate, task)`. Node: import Workflow from workflow.mjs and call "
        "`await flow.run(generate, task, {expectedRecords: 20})`; Python is required for the same parser runtime.\n\n"
        "Other languages can pipe text to `python workflow.py -`: exit 0 yields JSON on stdout; exit 1 yields diagnostics on stderr. "
        "Connect semantic retries in the calling application.\n\n"
        "Parser API: loads(text), dumps(value), diagnose(text), repair(text), apply_replacements(text, replacements). "
        "No guessing, no silent count adjustment. See examples/flujo-soporte in the download for a complete recorded run. "
        "Review samples before sharing. Rebuild in a new directory for new fields/types. "
        "Measure prompt, output and retries with your tokenizer before estimating monetary savings.\n"
    )
    if compact_tail is not None:
        files["GUIA.md"] += ("\n## Filas compactas\n\n"
                             "En `setup.json`, `compact_last_text_field` indica la columna de texto que más redujo "
                             "el tamaño de la muestra al ir al final. Para probar las filas compactas, "
                             "pasa ese nombre como `last_text_field` en Python o `lastTextField` en Node "
                             "junto con el número de registros esperado. Si tu proveedor admite esquemas "
                             "para filas JSON posicionales, usa `run_positional` en Python o `runPositional` en Node "
                             "con una función `generate(prompt, schema)`.\n")
        files["README.md"] += ("\n## Compact rows\n\n"
                               "In `setup.json`, `compact_last_text_field` names the text column that gave "
                               "the smallest sample when placed last. To try compact rows, "
                               "pass that name as `last_text_field` in Python or `lastTextField` in Node "
                               "with the expected record count. If your provider supports schemas for "
                               "positional JSON rows, call `run_positional` in Python or `runPositional` in Node "
                               "with a `generate(prompt, schema)` callback.\n")
    manifest = {"profile": PROFILE, "schema_id": contract["schema_id"], "sample_documents": len(samples),
                "sample_records": contract["sample_records"], "sources": list(source_names or []),
                "files": {name: hashlib.sha256(content.encode("utf-8")).hexdigest() for name, content in files.items()}}
    files["manifest.json"] = json.dumps(manifest, ensure_ascii=False, indent=2) + "\n"
    destination.mkdir(parents=True, exist_ok=True)
    for name, content in files.items():
        _write_text(destination / name, content)
    return contract


def main(argv=None):
    # Windows pipes otherwise inherit legacy code pages and corrupt Unicode
    # JSON or bilingual prompts.  Embedded callers may supply StringIO instead.
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description="Portable .mini domain parser and validator")
    sub = ap.add_subparsers(dest="command", required=True)
    for command in ("encode", "decode", "validate", "diagnose", "repair", "apply"):
        p = sub.add_parser(command)
        p.add_argument("file")
        p.add_argument("--contract")
        if command in ("encode", "decode", "repair", "apply"):
            p.add_argument("--out")
        if command == "encode":
            p.add_argument("--version", type=int, default=1, choices=(1, 2))
            p.add_argument("--delimiter", choices=("|", " ", ",", "\t"))
        if command == "apply":
            p.add_argument("corrections")
        if command == "decode":
            p.add_argument("--compact", action="store_true")
        if command == "repair":
            p.add_argument("--fix-count", action="store_true")
    p = sub.add_parser("prompt")
    p.add_argument("--lang", choices=("en", "es"), default="en")
    p.add_argument("--lean", action="store_true")
    p.add_argument("--contract")
    args = ap.parse_args(argv)
    try:
        contract = load_contract(args.contract)
        if args.command == "prompt":
            print(make_prompt(contract, args.lang, lean=args.lean))
            return 0
        # newline='' keeps transport problems visible to diagnose/repair.
        with Path(args.file).open(encoding="utf-8", newline="") as handle:
            text = handle.read()
        if args.command == "encode":
            output = encode(_strict_json(text.lstrip("\ufeff")), contract, version=args.version, delimiter=args.delimiter)
        elif args.command == "decode":
            output = json.dumps(decode(text, contract), ensure_ascii=False, indent=None if args.compact else 2, allow_nan=False)
        elif args.command in ("validate", "diagnose"):
            report = diagnose(text, contract)
            print(json.dumps(report, ensure_ascii=False, indent=2))
            return 0 if report["ok"] else 1
        elif args.command == "apply":
            replacements = _strict_json(Path(args.corrections).read_text(encoding="utf-8-sig"))
            output = apply_replacements(text, replacements, contract)
        else:
            report = repair(text, contract, fix_count=args.fix_count)
            if not report["ok"]:
                print(json.dumps(report, ensure_ascii=False, indent=2), file=sys.stderr)
                return 1
            output = report["text"].rstrip("\n")  # the writer below adds the single final LF
            print(json.dumps({"ok": True, "changes": report["changes"]}, ensure_ascii=False), file=sys.stderr)
        if args.out:
            _write_text(Path(args.out), output + "\n")
        else:
            print(output)
        return 0
    except (DomainError, OSError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        return 2


def _write_text(path, text):
    with Path(path).open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(text)


if __name__ == "__main__":
    raise SystemExit(main())
