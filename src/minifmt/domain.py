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
MISSING = object()


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


def _split(line, lineno):
    cells, current, index = [], [], 0
    while index < len(line):
        char = line[index]
        if char == "\\":
            index += 1
            if index >= len(line) or line[index] not in "\\|nr":
                raise DomainError("D_ESCAPE", "allowed field escapes: \\\\, \\|, \\n, \\r", line=lineno)
            current.append({"n": "\n", "r": "\r"}.get(line[index], line[index]))
        elif char == "|":
            cells.append("".join(current))
            current = []
        else:
            current.append(char)
        index += 1
    cells.append("".join(current))
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


def _uncell(text, schema, path):
    if text == "?":
        return MISSING
    if text == "~":
        return _unpack(None, schema, path)
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


def encode(value, contract=None, *, shared=True, dictionaries=True):
    """Serialize a JSON value without coercion, missing-field loss or key loss."""
    contract = _contract(contract)
    _pack(value, contract["schema"])
    path = contract["record_path"]
    records = _at(value, path) if path is not None else [value]
    schema, fields = _row_schema(contract), _fields(_row_schema(contract))
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
    for cell in cells[1:]:
        key, sep, value = cell.partition("=")
        if not sep or key in header or key not in {"v", "n", "h", "m", "d", "e"}:
            raise DomainError("D_HEADER", f"unknown, duplicate or malformed header field {key}", line=1)
        header[key] = value
    if header.get("v") != "1" or header.get("h") != contract["schema_id"]:
        raise DomainError("D_CONTRACT", "wrong profile version or schema fingerprint; use the matching generated bundle", line=1)
    if not re.fullmatch(r"0|[1-9][0-9]*", header.get("n", "")):
        raise DomainError("D_COUNT", "n must be a non-negative integer", line=1)
    schema, fields = _row_schema(contract), _fields(_row_schema(contract))
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
                defaults[index] = cell
        except (ValueError, TypeError) as exc:
            raise DomainError("D_HEADER", str(exc), line=1) from exc
    codebooks = {}
    if "e" in header:
        try:
            pairs = _strict_json(header["e"])
            if not isinstance(pairs, list):
                raise ValueError("e must be an array of [column index, string-cell vocabulary] pairs")
            for pair in pairs:
                if not isinstance(pair, list) or len(pair) != 2:
                    raise ValueError("malformed vocabulary")
                index, values = pair
                if (type(index) is not int or not 0 <= index < len(fields) or index in defaults or index in codebooks
                        or fields[index]["schema"]["type"] != "string"):
                    raise ValueError("invalid, shared or duplicate vocabulary column")
                if not isinstance(values, list) or not values or not all(isinstance(value, str) for value in values) or len(set(values)) != len(values):
                    raise ValueError("vocabulary must contain unique encoded string cells")
                for cell in values:
                    item = _uncell(cell, fields[index]["schema"], "$/vocabulary")
                    if item is MISSING and not fields[index]["optional"]:
                        raise ValueError("vocabulary cannot omit a required field")
                codebooks[index] = values
        except (ValueError, TypeError) as exc:
            raise DomainError("D_HEADER", str(exc), line=1) from exc
    rows = []
    for lineno, line in enumerate(lines[1:], 2):
        try:
            expected = len(fields) - len(defaults)
            row_cells = [] if expected == 0 and line == "-" else _split(line, lineno)
            if len(row_cells) != expected:
                raise DomainError("D_ARITY", f"expected {expected} cells, received {len(row_cells)}")
            row, offset = _object_skeleton(schema) if _object_row(schema) else {}, 0
            for index, field in enumerate(fields):
                raw = defaults[index] if index in defaults else row_cells[offset]
                if index not in defaults:
                    offset += 1
                if index in codebooks:
                    if not re.fullmatch(r"0|[1-9][0-9]*", raw) or int(raw) >= len(codebooks[index]):
                        raise DomainError("D_ENUM", f"invalid vocabulary index for {field['name']}")
                    raw = codebooks[index][int(raw)]
                item = _uncell(raw, field["schema"], f"$/{lineno-2}/{field['name']}")
                if item is MISSING:
                    if not field["optional"]:
                        raise DomainError("D_REQUIRED", f"missing required field {field['name']}")
                else:
                    if _object_row(schema):
                        _put(row, field["path"], item)
                    else:
                        row[field["name"]] = item
            rows.append(row if _object_row(schema) else row["$value"])
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
    # Isolate records only once the complete header was accepted.  Each test
    # uses the same schema, wrapper and shared columns, with n=1 for that row.
    if initial.line >= 2 or initial.code == "D_COUNT":
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
    else:
        errors = [initial.to_dict()]
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
    """Repair transport wrappers only; count changes require explicit opt-in.

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
    stripped = text.strip("\n")
    fence = re.fullmatch(r"```(?:mini|text)?[ \t]*\n([\s\S]*?)\n```", stripped)
    if fence:
        text = fence.group(1)
        changes.append("removed complete Markdown code fence")
    report = diagnose(text, contract)
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


def make_prompt(contract, lang="en", example=None):
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
        title = "Contrato de dominio .mini"
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
        title = ".mini domain contract"
    header = f"{contract['prefix']}|v=1|n=<record count>|h={contract['schema_id']}"
    path = contract["record_path"]
    extra = ""
    if path:
        extra = ("\nLa cabecera requiere m=<JSON posicional del documento completo con la colección de registros sustituida por []>. "
                 if lang == "es" else "\nThe header requires m=<positional JSON of the complete wrapper with the record collection replaced by []>. ")
        extra += "record_path=" + _json(path) + ". Escape m using the same field rules."
    text = f"# {title}\n\n{intro}\n\nProfile: {PROFILE}\nHeader: `{header}`{extra}\n\n"
    text += "\n".join(f"{index+1}. {rule}" for index, rule in enumerate(rules))
    text += "\n\nColumns (zero-based; paths use JSON Pointer escaping):\n" + "\n".join(f"{index}: {field['name']} ({field['schema']['type']}{', optional' if field['optional'] else ''})" for index, field in enumerate(fields))
    text += "\n\nSchema:\n```json\n" + _json(contract["schema"]) + "\n```\n"
    if example is not None:
        text += "\nExample / Ejemplo:\n```mini\n" + encode(example, contract) + "\n```\n"
    return text


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


def build_bundle(samples, prefix="data", out=".mini", *, source_names=None, record_path=None):
    """Write a portable bundle to a new/empty directory; never overwrite work."""
    destination = Path(out)
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
    files = {
        "contract.json": json.dumps(contract, ensure_ascii=False, indent=2) + "\n",
        "schema.json": json.dumps(json_schema(contract), ensure_ascii=False, indent=2) + "\n",
        "prompt.en.md": make_prompt(contract, "en", example),
        "prompt.es.md": make_prompt(contract, "es", example),
        "parser.py": source,
        "validator.py": '"""Validate a .mini response with the bundled contract."""\n' + _WRAPPER_IMPORT + 'if __name__ == "__main__":\n    raise SystemExit(main(["validate", *sys.argv[1:]]))\n',
        "repair.py": '"""Repair only unambiguous transport wrappers; never fabricate data."""\n' + _WRAPPER_IMPORT + 'if __name__ == "__main__":\n    raise SystemExit(main(["repair", *sys.argv[1:]]))\n',
        "example.json": json.dumps(example, ensure_ascii=False, indent=2) + "\n",
        "example.mini": encode(example, contract) + "\n",
        "README.md": f"# {prefix} · .mini domain bundle\n\nProfile `{PROFILE}`. Python 3.9+; standard library only.\n"
                     "This generated profile uses its own bundled parser; it is not a core .mini 1.0 family.\n\n"
                     "```sh\npython parser.py encode input.json --out request.mini\npython parser.py decode response.mini --out response.json\n"
                     "python validator.py response.mini\npython parser.py diagnose response.mini\npython repair.py response.mini --out corrected.mini\n```\n\n"
                     "Use prompt.en.md or prompt.es.md in your model's instructions. Keep the original task and expected record count in the workflow.\n"
                     "API: `loads(text)`, `dumps(value)`, `diagnose(text)`, `repair(text, fix_count=False)`, `apply_replacements(text, replacements)` from parser.py.\n"
                     "`schema.json` exports JSON Schema 2020-12 for validation and integration.\n\n"
                     "Missing members, null, false, zero and empty strings remain distinct. More representative samples improve coverage; "
                     "they cannot prove constraints for unseen data. New fields/types are rejected: rebuild in a new directory with additional samples.\n"
                     "Observed constants are never silently frozen. Shared columns and repeated-string vocabularies are declared explicitly in each document.\n"
                     "Repair removes complete Markdown fences, BOM and CRLF only. It never fills values or guesses records. "
                     "`--fix-count` explicitly accepts the records present and resets n after every record validates; check completeness yourself.\n"
                     "Failed repair returns per-line diagnostics and a selective regeneration prompt. Apply returned line replacements with "
                     "`python parser.py apply response.mini corrections.json --out corrected.mini`; every unchanged line is preserved and the complete result must validate. "
                     "No invalid output file is written.\n\n"
                     "Training examples can contain private data: review example.json/mini, prompts and contract before sharing this bundle.\n"
                     "Measure tokens with the actual tokenizer, prompt and request pattern; no encoding wins on every JSON document.\n",
    }
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
        if command == "apply":
            p.add_argument("corrections")
        if command == "decode":
            p.add_argument("--compact", action="store_true")
        if command == "repair":
            p.add_argument("--fix-count", action="store_true")
    p = sub.add_parser("prompt")
    p.add_argument("--lang", choices=("en", "es"), default="en")
    p.add_argument("--contract")
    args = ap.parse_args(argv)
    try:
        contract = load_contract(args.contract)
        if args.command == "prompt":
            print(make_prompt(contract, args.lang))
            return 0
        # newline='' keeps transport problems visible to diagnose/repair.
        with Path(args.file).open(encoding="utf-8", newline="") as handle:
            text = handle.read()
        if args.command == "encode":
            output = encode(_strict_json(text.lstrip("\ufeff")), contract)
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
            output = report["text"]
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
