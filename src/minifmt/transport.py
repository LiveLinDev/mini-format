"""Choose a reversible representation for JSON before sending it to a model.

This self-contained transport is opt-in. The classic and domain .mini
parsers continue to use their existing wire formats.
"""
from __future__ import annotations

import argparse
import csv
from io import StringIO
from itertools import groupby
import json
from os.path import commonprefix
from pathlib import Path
import re
import sys

from . import domain

_TYPES = ("string", "integer", "number", "boolean", "json", "object", "array")
_KEY = re.compile(r"[A-Za-z_][A-Za-z_0-9./-]*")
_INTEGER = re.compile(r"0|-?[1-9][0-9]*")
_TREE = {"|\n", "\t\n", "1|\n", "1\t\n"}
_SERIES_FIELD = re.compile(rf"({_KEY.pattern})(?:=({_INTEGER.pattern}):({_INTEGER.pattern}))?")
_TABLE_TYPES = {"s": "string", "i": "integer", "n": "number", "b": "boolean"}
_TABLE_HEAD = re.compile(rf"({_KEY.pattern})\[(0|[1-9][0-9]*)\] (.+)")
_TABLE_FIELD = re.compile(rf"({_KEY.pattern})(?::([sinb]))?")


def _schema_wire(node):
    kind = node["type"]
    code = _TYPES.index(kind)
    if node.get("nullable"):
        code = ~code
    if kind == "array":
        return [code, _schema_wire(node["items"])]
    if kind == "object":
        fields = [[f["name"], _schema_wire(f["schema"])] + ([1] if f["optional"] else [])
                  for f in node["fields"]]
        return [code, *fields]
    return code


def _schema_node(wire):
    code, *details = wire if isinstance(wire, list) else [wire]
    if type(code) is not int or not -len(_TYPES) <= code < len(_TYPES):
        raise ValueError("invalid schema type")
    kind = _TYPES[~code if code < 0 else code]
    node = {"type": kind}
    if kind == "array":
        child, = details
        node["items"] = _schema_node(child)
    elif kind == "object":
        fields = []
        names = set()
        for name, child, *optional in details:
            if (not isinstance(name, str) or name in names
                    or (optional and (len(optional) != 1 or type(optional[0]) is not int or optional[0] != 1))):
                raise ValueError("invalid schema field")
            fields.append({"name": name, "optional": bool(optional), "schema": _schema_node(child)})
            names.add(name)
        node["fields"] = fields
    elif details:
        raise ValueError("unexpected scalar schema arguments")
    if code < 0:
        node["nullable"] = True
    return node


def _schema_contract(data):
    prefix, path, schema = data
    if not isinstance(prefix, str) or not re.fullmatch(r"[A-Za-z][A-Za-z0-9_-]*", prefix):
        raise ValueError("invalid contract prefix")
    if path is not None and (not isinstance(path, list) or any(not isinstance(key, str) for key in path)):
        raise ValueError("invalid record path")
    contract = {"profile": domain.PROFILE, "version": 1, "prefix": prefix,
                "record_path": path, "schema": _schema_node(schema)}
    contract["schema_id"] = domain._fingerprint(contract)
    return contract


def _csv_rows(rows, delimiter):
    handle = StringIO(newline="")
    writer = csv.writer(handle, delimiter=delimiter, lineterminator="\r\n")
    writer.writerows(rows)
    return handle.getvalue()[:-2]


def _integer_sequence(items):
    if all(_INTEGER.fullmatch(item) and len(item) <= 32 for item in items):
        nums = list(map(int, items))
        start, step = nums[0], nums[1] - nums[0]
        if step and all(num == start + i * step for i, num in enumerate(nums)):
            return [start, step]
    return None


def _column_patterns(items):
    if (sequence := _integer_sequence(items)) is not None:
        yield "s", sequence
    runs = [[sum(1 for _ in group), item] for item, group in groupby(items)]
    if len(runs) * 3 < len(items):
        yield "g", runs
    prefix = commonprefix(items)
    if len(prefix) >= 3:
        yield "p", prefix
    suffix = commonprefix([item[::-1] for item in items])[::-1]
    if len(suffix) >= 3:
        yield "a", suffix


def _rows_wire(sidecar, header, columns, delimiter, changes):
    visible = []
    for index, col in enumerate(columns):
        method, extra = changes.get(index, (None, None))
        if method == "p":
            col = [item[len(extra):] for item in col]
        elif method == "a":
            col = [item[:-len(extra)] for item in col]
        elif method in ("s", "g"):
            continue
        visible.append(col)
    marker = [sidecar, header, len(columns), delimiter, changes]
    return ":" + domain._json(marker) + "\n" + _csv_rows(zip(*visible), delimiter)


def _best_rows(sidecar, mini, score):
    header, *body = mini.split("\n")
    if len(body) < 2:
        return None
    rows = [domain._split(line, number) for number, line in enumerate(body, 2)]
    columns = list(zip(*rows))
    if not columns or any(len(row) != len(columns) for row in rows):
        return None
    plain = {delimiter: _rows_wire(sidecar, header, columns, delimiter, {}) for delimiter in (",", "\t", "|")}
    delimiter = min(plain, key=lambda key: score(plain[key]))
    best = plain[delimiter]
    best_score = score(best)
    changes = {}
    for index, column in enumerate(columns):
        for method, value in _column_patterns(column):
            proposed = dict(changes)
            proposed[index] = (method, value)
            if sum(rule[0] in ("s", "g") for rule in proposed.values()) == len(columns):
                continue
            wire = _rows_wire(sidecar, header, columns, delimiter, proposed)
            wire_score = score(wire)
            if wire_score < best_score:
                best, best_score, changes = wire, wire_score, proposed
    return best


def _restore_rows(metadata, body):
    sidecar, header, width, delimiter, raw_changes = metadata
    if delimiter not in (",", "\t", "|") or type(width) is not int or width < 1:
        raise ValueError("invalid table metadata")
    changes = {}
    for key, rule in raw_changes.items():
        if not re.fullmatch(r"0|[1-9][0-9]*", key) or int(key) >= width:
            raise ValueError("invalid table column index")
        changes[int(key)] = rule
    removed = sum(rule[0] in ("s", "g") for rule in changes.values())
    rows = list(csv.reader(StringIO(body, newline=""), delimiter=delimiter, strict=True))
    if width <= removed or not rows or any(len(row) != width - removed for row in rows):
        raise ValueError("invalid table width or missing rows")
    visible = iter(zip(*rows))
    columns = []
    for index in range(width):
        method, value = changes.get(index, (None, None))
        if method == "s":
            start, step = value
            if type(start) is not int or type(step) is not int or not step:
                raise ValueError("invalid integer sequence")
            col = [str(start + i * step) for i in range(len(rows))]
        elif method == "g":
            if any(type(n) is not int or n < 1 or not isinstance(cell, str) for n, cell in value):
                raise ValueError("invalid table run")
            if sum(n for n, _ in value) != len(rows):
                raise ValueError("table run count does not match rows")
            col = [cell for n, cell in value for _ in range(n)]
        else:
            col = next(visible)
            if method == "p":
                col = [value + cell for cell in col]
            elif method == "a":
                col = [cell + value for cell in col]
            elif method is not None:
                raise ValueError("unknown table column rule")
        columns.append(col)
    mini = "\n".join([header, *("|".join(map(domain._escape, row)) for row in zip(*columns))])
    return domain.decode(mini, _schema_contract(sidecar))


def _scalar(value):
    if not isinstance(value, str):
        return domain._json(value)
    if (not value or value != value.strip(" ") or value.startswith(('"', "[", "{"))
            or any(ord(c) < 32 for c in value)):
        return domain._json(value)
    try:
        domain._strict_json(value)
    except ValueError:
        return value
    return domain._json(value)


def _read_scalar(value):
    try:
        return domain._strict_json(value)
    except ValueError:
        return value


def _table_fields(value):
    if not isinstance(value, list) or len(value) < 2 or not all(isinstance(row, dict) for row in value):
        return None
    fields = list(value[0])
    if fields and all(_KEY.fullmatch(key) for key in fields) and all(row.keys() == value[0].keys() for row in value):
        return fields
    return None


def _series_rows(value):
    fields = _table_fields(value)
    if not fields or any(isinstance(cell, (list, dict)) for row in value for cell in row.values()):
        return None
    columns = {key: [row[key] for row in value] for key in fields}
    tail = max(reversed(fields), key=lambda key: sum(isinstance(cell, str) and " " in cell for cell in columns[key]))
    fields.remove(tail)
    fields.append(tail)
    header, visible = [], []
    for field in fields:
        atoms = [_scalar(cell) for cell in columns[field]]
        sequence = _integer_sequence(atoms) if field != tail else None
        if sequence:
            start, step = sequence
            header.append(f"{field}={start}:{step}")
        else:
            header.append(field)
            if field != tail:
                atoms = [domain._json(cell) if isinstance(cell, str) and " " in cell else atom
                         for cell, atom in zip(columns[field], atoms)]
            visible.append(atoms)
    if len(visible) == len(fields):
        return None
    return "^" + " ".join(header) + "\n" + "\n".join(" ".join(row) for row in zip(*visible))


def _read_series(header, body):
    matches = [_SERIES_FIELD.fullmatch(part) for part in header.split(" ")]
    if any(match is None for match in matches):
        raise ValueError("invalid sequence table column")
    fields = [match[1] for match in matches]
    sequences = {match[1]: (int(match[2]), int(match[3])) for match in matches if match[2] is not None}
    if (len(set(fields)) != len(fields) or not sequences or fields[-1] in sequences
            or any(step == 0 for _, step in sequences.values())):
        raise ValueError("invalid sequence table layout")
    visible = [field for field in fields if field not in sequences]
    lines = body.split("\n")
    if len(lines) < 2:
        raise ValueError("a sequence table requires at least two rows")

    def scalar(text):
        if not text or text.startswith(("[", "{")):
            raise ValueError("expected a scalar value")
        return domain._strict_json(text) if text.startswith('"') else _read_scalar(text)

    rows = []
    for position, line in enumerate(lines):
        if "\r" in line:
            raise ValueError("encode carriage returns as a JSON escape")
        row = {name: start + position * step for name, (start, step) in sequences.items()}
        index = 0
        for field in visible[:-1]:
            match = domain._ROW_ATOM.match(line, index)
            if match is None or match.end() == len(line):
                raise ValueError("sequence table row is missing a column")
            row[field] = scalar(match[0].rstrip(" \t"))
            index = match.end()
        row[visible[-1]] = scalar(line[index:])
        rows.append({field: row[field] for field in fields})
    return rows


def _tree_table(name, rows, fields, sep, pad, score):
    encoded = [{key: _scalar(row[key]) for key in fields} for row in rows]
    if any(sep in cell for row in encoded for cell in row.values()):
        return None

    def emit(defaults):
        columns = [key + "=" + defaults[key] if key in defaults else key for key in fields]
        return [pad + name + "[" + sep.join(columns) + "]",
                *(pad + " " + sep.join(row[key] for key in fields if key not in defaults) for row in encoded)]

    defaults, best = {}, emit({})
    for key in fields:
        if len(defaults) + 1 == len(fields):
            break
        if all(row[key] == encoded[0][key] for row in encoded[1:]):
            candidate = {**defaults, key: encoded[0][key]}
            lines = emit(candidate)
            if score("\n".join(lines)) < score("\n".join(best)):
                defaults, best = candidate, lines
    return best


def _tree(value, sep, score):
    def visit(obj, level):
        pad = " " * level
        lines = []
        for key, item in obj.items():
            name = key if _KEY.fullmatch(key) else domain._json(key)
            leaf = [pad + name + " " + _scalar(item)]
            candidate = None
            if isinstance(item, dict) and item:
                candidate = [pad + name + ":", *visit(item, level + 1)]
            elif fields := _table_fields(item):
                candidate = _tree_table(name, item, fields, sep, pad, score)
            if candidate is not None and score("\n".join(candidate)) < score("\n".join(leaf)):
                leaf = candidate
            lines.extend(leaf)
        return lines

    wrapped = not isinstance(value, dict)
    source = {"_": value} if wrapped else value
    return ("1" if wrapped else "") + sep + "\n" + "\n".join(visit(source, 0))


def _read_tree(head, body):
    wrapped, sep = head.startswith("1"), head[-1]
    lines = body.split("\n") if body else []

    def visit(start, level):
        obj = {}
        pad = " " * level
        while start < len(lines) and lines[start].startswith(pad) and lines[start][level:level+1] != " ":
            line = lines[start][level:]
            if line.startswith('"'):
                key, end = json.JSONDecoder().raw_decode(line)
            else:
                match = _KEY.match(line)
                if not match:
                    raise ValueError("invalid section key")
                key, end = match.group(), match.end()
            tail = line[end:]
            start += 1
            if tail == ":":
                value, start = visit(start, level + 1)
            elif tail.startswith("[") and tail.endswith("]"):
                cols = [col.partition("=") for col in tail[1:-1].split(sep)]
                names = [name for name, _, _ in cols]
                if any(not _KEY.fullmatch(name) for name in names) or len(set(names)) != len(names):
                    raise ValueError("invalid table field")
                active = [name for name, eq, _ in cols if not eq]
                const = {name: _read_scalar(cell) for name, eq, cell in cols if eq}
                value = []
                while start < len(lines) and lines[start].startswith(pad + " "):
                    row = lines[start][level+1:].split(sep)
                    if len(row) != len(active):
                        raise ValueError("table row does not match its fields")
                    value.append({**const, **dict(zip(active, map(_read_scalar, row)))})
                    start += 1
            elif tail.startswith(" "):
                value = _read_scalar(tail[1:])
            else:
                raise ValueError("invalid section row")
            if key in obj:
                raise ValueError("duplicate section key")
            obj[key] = value
        return obj, start

    result, end = visit(0, 0)
    if end != len(lines) or (wrapped and result.keys() != {"_"}):
        raise ValueError("invalid section layout")
    return result["_"] if wrapped else result


def _encode(value, contract, score, sections=True):
    sidecar = [contract["prefix"], contract["record_path"], _schema_wire(contract["schema"])]
    schema_text = domain._json(sidecar) + "\n"
    contract = _schema_contract(sidecar)
    mini = domain.encode(value, contract)
    positional = domain._json(domain._pack(value, contract["schema"]))
    options = [domain._json(value), "=" + schema_text + mini, "~" + schema_text + positional]
    if contract["record_path"]:
        adaptive = domain.encode_v2(value, contract, token_counter=score)
        options.append("=" + schema_text + adaptive)
    if (rows := _best_rows(sidecar, mini, score)) is not None:
        options.append(rows)
    if (series := _series_rows(value)) is not None:
        options.append(series)
    options.extend(_tree(value, sep, score) for sep in ("\t", "|"))
    if sections and isinstance(value, dict):
        keys = [key for key, item in value.items() if _table_fields(item)]
        parts = []
        if len(keys) >= 2:
            parts = [(key, _encode(value[key], domain.infer_contract([value[key]], prefix="rows"), score, False))
                     for key in keys]
        elif keys and (series := _series_rows(value[keys[0]])) is not None:
            parts.append((keys[0], series))
        if parts:
            section_keys = {key for key, _ in parts}
            base = {key: item for key, item in value.items() if key not in section_keys}
            header = [base, [[key, len(part)] for key, part in parts]]
            options.append("#" + domain._json(header) + "\n" + "".join(part for _, part in parts))
    return min(options, key=score)


def _model_table(name, rows):
    if not _KEY.fullmatch(name) or not _table_fields(rows):
        return None
    contract = domain.infer_contract([rows], prefix="rows")
    tail = domain._recommend_compact_tail([rows], contract)
    if tail is None:
        return None
    fields = domain._compact_fields(contract, tail)
    codes = {kind: code for code, kind in _TABLE_TYPES.items()}
    headings = " ".join(f"{field['name']}:{codes[field['schema']['type']]}" for field in fields)
    encoded = domain.encode_rows(rows, contract, last_text_field=tail)
    # A table with one text column can contain literal Markdown fence lines.
    if encoded.startswith("```") and encoded.endswith("\n```"):
        first, _, rest = encoded.partition("\n")
        encoded = f"{domain._json(first)}\n{rest}"
    return f"{name}[{len(rows)}] {headings}\n{encoded}"


def _compact_model_block(body):
    header, _, rows = body.partition("\n")
    name, *fields = header.split(" ")
    headings = " ".join(field.removesuffix(":s") for field in fields)
    return f"{name} {headings}\n " + rows.replace("\n", "\n ")


def _read_model_block(body, *, implicit_strings=False):
    header, _, table = body.partition("\n")
    match = _TABLE_HEAD.fullmatch(header)
    if match is None:
        raise ValueError("invalid model table header")
    name, count, headings = match.groups()
    fields = [_TABLE_FIELD.fullmatch(cell) for cell in headings.split(" ")]
    if any(field is None or (not implicit_strings and field.group(2) is None) for field in fields):
        raise ValueError("invalid model table field")
    entries = [field.groups() for field in fields]
    wire = [6, [5, *[[key, _TYPES.index(_TABLE_TYPES[code or "s"])] for key, code in entries]]]
    contract = _schema_contract(["rows", [], wire])
    rows = domain.decode_rows(table, contract, last_text_field=entries[-1][0], expected_records=int(count))
    return name, rows


def _read_model_table(metadata, body):
    name, rows = _read_model_block(body)
    if metadata == "":
        return rows
    root = domain._strict_json(metadata)
    if not isinstance(root, dict) or name in root:
        raise ValueError("invalid model table metadata")
    return {**root, name: rows}


def _read_model_tables(metadata, body):
    root = domain._strict_json(metadata)
    if not isinstance(root, dict):
        raise ValueError("invalid model table metadata")
    blocks = body.replace("\r\n", "\n").rstrip("\n").split("\n\n")
    if len(blocks) < 2:
        raise ValueError("expected at least two model tables")
    for block in blocks:
        name, rows = _read_model_block(block, implicit_strings=True)
        if name in root:
            raise ValueError("duplicate model table")
        root[name] = rows
    return root


def dumps(value, contract=None, *, count=None, for_model=False):
    """Encode JSON losslessly. With for_model, keep IDs and row counts explicit."""
    if count is None:
        count = lambda text: len(text.encode("utf-8"))
    contract = domain.infer_contract([value]) if contract is None else domain._contract(contract)
    if for_model:
        domain._pack(value, contract["schema"])
        options = [domain._json(value)]
        if isinstance(value, dict):
            tables = {}
            for name, rows in value.items():
                candidate = _model_table(name, rows)
                if candidate is not None:
                    tables[name] = candidate
                    metadata = {key: cell for key, cell in value.items() if key != name}
                    options.append(f"+{domain._json(metadata)}\n{candidate}")
            if len(tables) > 1:
                metadata = {key: cell for key, cell in value.items() if key not in tables}
                names = sorted(tables, key=lambda name: (len(value[name]), name))
                blocks = "\n\n".join(_compact_model_block(tables[name]) for name in names)
                options.append(f"++{domain._json(metadata)}\n{blocks}")
        else:
            candidate = _model_table("records", value)
            if candidate is not None:
                options.append("+\n" + candidate)
        return min(options, key=count)
    return _encode(value, contract, count)


def _decode(text):
    header, newline, body = text.partition("\n")
    if header + newline in _TREE:
        return _read_tree(header, body)
    if header.startswith("="):
        return domain.decode(body, _schema_contract(domain._strict_json(header[1:])))
    if header.startswith("~"):
        schema = _schema_contract(domain._strict_json(header[1:]))["schema"]
        return domain._unpack(domain._strict_json(body), schema)
    if header.startswith(":"):
        return _restore_rows(domain._strict_json(header[1:]), body)
    if header.startswith("^"):
        return _read_series(header[1:], body)
    if header.startswith("++"):
        return _read_model_tables(header[2:], body)
    if header.startswith("+"):
        return _read_model_table(header[1:], body)
    if header.startswith("#"):
        base, descriptors = domain._strict_json(header[1:])
        if not isinstance(base, dict):
            raise ValueError("invalid document envelope")
        size = 0
        for key, count in descriptors:
            if not isinstance(key, str) or key in base or type(count) is not int or not 0 < count <= len(body) - size:
                raise ValueError("invalid document section")
            base[key] = _decode(body[size:size+count])
            size += count
        if size != len(body):
            raise ValueError("trailing content after document sections")
        return base
    return domain._strict_json(text)


def loads(text, contract=None):
    """Read transport text and optionally validate the result against a domain contract."""
    try:
        data = _decode(text)
        domain._check_json(data)
        if contract is not None:
            domain._pack(data, domain._contract(contract)["schema"])
        return data
    except domain.DomainError:
        raise
    except (ValueError, TypeError, IndexError, KeyError, AttributeError, csv.Error, RecursionError) as error:
        raise domain.DomainError("D_VALUE", f"invalid transport: {error}") from error


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=("encode", "decode"))
    parser.add_argument("file", help="UTF-8 file or - for stdin")
    parser.add_argument("--tokenizer", help="use an installed tokenizer instead of UTF-8 byte size")
    parser.add_argument("--for-model", action="store_true", help="encode a table with explicit IDs and row counts")
    args = parser.parse_args(argv)
    text = sys.stdin.buffer.read().decode("utf-8") if args.file == "-" else Path(args.file).read_bytes().decode("utf-8")
    try:
        if args.operation == "encode":
            count = None
            if args.tokenizer:
                from .tokens import get_tokenizer
                tokenizer = get_tokenizer(args.tokenizer)
                if tokenizer.backend != "tiktoken":
                    raise ValueError("an exact token count requires tiktoken")
                count = tokenizer.count
            output = dumps(domain._strict_json(text), count=count, for_model=args.for_model)
        else:
            output = domain._json(loads(text))
    except ValueError as error:
        parser.exit(1, f"{error}\n")
    sys.stdout.buffer.write(output.encode("utf-8"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
