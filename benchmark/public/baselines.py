"""Reversible baselines, including explicit flattening/CSV schema accounting.

No record, wrapper metadata, empty value, or JSON type may be dropped. The
flattening map is reusable context, measured separately just like a .mini fork.
"""
from __future__ import annotations

import csv
import io
import json
import subprocess
import xml.etree.ElementTree as ET
from typing import Any

_ABSENT = object()


def compact(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), allow_nan=False)


def equivalent(left: Any, right: Any) -> bool:
    """JSON semantic equality: key order irrelevant, bool is not a number."""
    if isinstance(left, bool) or isinstance(right, bool):
        return type(left) is type(right) and left == right
    if isinstance(left, (int, float)) and isinstance(right, (int, float)):
        return left == right
    if type(left) is not type(right):
        return False
    if isinstance(left, dict):
        return left.keys() == right.keys() and all(equivalent(left[k], right[k]) for k in left)
    if isinstance(left, list):
        return len(left) == len(right) and all(equivalent(a, b) for a, b in zip(left, right))
    return left == right


def _leaves(value: Any, path: tuple = (), *, expand_arrays=False) -> dict[tuple, Any]:
    if isinstance(value, dict) and value:
        out = {}
        for key, child in value.items():
            out.update(_leaves(child, (*path, key), expand_arrays=expand_arrays))
        return out
    if expand_arrays and isinstance(value, list) and value:
        out = {}
        for index, child in enumerate(value):
            out.update(_leaves(child, (*path, index), expand_arrays=True))
        return out
    return {path: value}


def _pointer(path: tuple) -> str:
    return "/" + "/".join(str(key).replace("~", "~0").replace("/", "~1") for key in path)


def _path(pointer: str) -> list[str]:
    return [key.replace("~1", "/").replace("~0", "~") for key in pointer[1:].split("/")]


def _kind(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "bool"
    if isinstance(value, (int, float)):
        return "number"
    if isinstance(value, str):
        return "str"
    return "json"


def flatten(document: Any, records_key: str | None, *, expand_arrays=False) -> tuple[Any, dict]:
    records = document[records_key] if records_key is not None else document
    leaves = [_leaves(row, expand_arrays=expand_arrays) for row in records]
    paths = list(dict.fromkeys(path for row in leaves for path in row))
    columns = []
    for path in paths:
        values = [row[path] for row in leaves if path in row]
        kinds = set(_kind(value) for value in values)
        # Composite cells use JSON, not delimiter joining; arrays retain all types.
        codec = "json" if "json" in kinds else "native"
        csv_type = next(iter(kinds)) if len(kinds) == 1 else "json"
        column = {"name": _pointer(path), "codec": codec, "csv_type": csv_type}
        if expand_arrays:
            column["path"] = list(path)
        columns.append(column)
    if len({column["name"] for column in columns}) != len(columns):
        raise ValueError("Flattening has ambiguous numeric object keys/array indices; use the unexpanded strategy")
    rows = []
    for row in leaves:
        cells = {}
        for path, column in zip(paths, columns):
            if path not in row:
                value = "~"
            elif column["codec"] == "json":
                value = compact(row[path])
            else:
                value = row[path]
                if isinstance(value, str) and value.startswith("~"):
                    value = "~" + value
            cells[column["name"]] = value
        rows.append(cells)
    result = {**document, records_key: rows} if records_key is not None else rows
    return result, {"records_key": records_key, "missing": "~", "columns": columns}


def _assign(row, parts, value):
    target = row
    for index, part in enumerate(parts):
        last = index == len(parts) - 1
        if isinstance(part, int):
            while len(target) <= part:
                target.append(_ABSENT)
            if last:
                target[part] = value
            else:
                if target[part] is _ABSENT:
                    target[part] = [] if isinstance(parts[index + 1], int) else {}
                target = target[part]
        elif last:
            target[part] = value
        else:
            target = target.setdefault(part, [] if isinstance(parts[index + 1], int) else {})


def unflatten(document: Any, schema: dict) -> Any:
    key = schema["records_key"]
    records = document[key] if key is not None else document
    rows = []
    for flat in records:
        row = {}
        for column in schema["columns"]:
            value = flat[column["name"]]
            if value == "~":
                continue
            if column["codec"] == "json":
                value = json.loads(value)
            elif isinstance(value, str) and value.startswith("~~"):
                value = value[1:]
            _assign(row, column.get("path", _path(column["name"])), value)
        rows.append(row)
    return {**document, key: rows} if key is not None else rows


def toon_batch(documents: list, bridge, node: str = "node") -> list[dict]:
    result = subprocess.run(
        [node, "--experimental-strip-types", "--experimental-transform-types", str(bridge)],
        input=compact(documents).encode("utf-8"), capture_output=True, check=True,
    )
    return json.loads(result.stdout.decode("utf-8"))


def csv_encode(flat: Any, schema: dict) -> str:
    key = schema["records_key"]
    rows = flat[key] if key is not None else flat
    metadata = {k: v for k, v in flat.items() if k != key} if key is not None else None
    buffer = io.StringIO(newline="")
    # Sidecar is included in the transmitted token count, not silently discarded.
    if metadata is not None:
        buffer.write("#meta " + compact(metadata) + "\n")
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow([column["name"] for column in schema["columns"]])
    for row in rows:
        values = []
        for column in schema["columns"]:
            value = row[column["name"]]
            if value == "~" or column["codec"] == "json" or column["csv_type"] == "str":
                values.append(value)
            else:
                values.append(compact(value))
        writer.writerow(values)
    return buffer.getvalue().rstrip("\n")


def csv_decode(text: str, schema: dict) -> Any:
    key = schema["records_key"]
    metadata = None
    if key is not None:
        line, text = text.split("\n", 1)
        if not line.startswith("#meta "):
            raise ValueError("Missing CSV wrapper metadata")
        metadata = json.loads(line[6:])
    rows = []
    for row in csv.DictReader(io.StringIO(text, newline="")):
        for column in schema["columns"]:
            value = row[column["name"]]
            if value != "~" and column["codec"] != "json" and column["csv_type"] != "str":
                row[column["name"]] = json.loads(value)
        rows.append(row)
    flat = {**metadata, key: rows} if key is not None else rows
    return unflatten(flat, schema)


def xml_encode(value: Any) -> str:
    def element(item):
        if isinstance(item, dict):
            node = ET.Element("object")
            for key, child in item.items():
                entry = ET.SubElement(node, "entry", {"key": key})
                entry.append(element(child))
        elif isinstance(item, list):
            node = ET.Element("array")
            node.extend(element(child) for child in item)
        else:
            node = ET.Element(_kind(item))
            node.text = item if isinstance(item, str) else compact(item)
        return node
    return ET.tostring(element(value), encoding="unicode", short_empty_elements=True)


def xml_decode(text: str) -> Any:
    def value(node):
        if node.tag == "object":
            return {entry.attrib["key"]: value(entry[0]) for entry in node}
        if node.tag == "array":
            return [value(child) for child in node]
        return node.text or "" if node.tag == "str" else json.loads(node.text or "null")
    return value(ET.fromstring(text))
