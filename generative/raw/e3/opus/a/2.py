"""Deterministic parser for the .mini text format, family 'a' (v1).

Family 'a' encodes multiple-choice assessment items enriched with Bloom
level, IRT 3PL parameters and CAT metadata.  One record per line, fields
separated by '|', position carries the semantics.

Public API::

    parse(text) -> {"prefix": str, "header": dict, "items": [record, ...]}

Invalid documents raise :class:`MiniFormatError` (a ``ValueError``) whose
message always reports the offending 1-based line number.
"""

import re

# --------------------------------------------------------------------------
# format constants
# --------------------------------------------------------------------------

PREFIX = "a"

BLOOM_LEVELS = ("L1", "L2", "L3", "L4", "L5", "L6")

HEADER_KEYS = ("n", "m", "d", "l", "t", "bd", "cat", "k")
HEADER_REQUIRED = ("n",)
HEADER_INT_KEYS = ("n", "k")
HEADER_LIST_KEYS = ("bd", "cat")

RECORD_FIELDS = (
    "id",
    "bloom",
    "topic",
    "statement",
    "options",
    "irt",
    "difficulty",
    "cat",
)
RECORD_ARITY = len(RECORD_FIELDS)

OPTIONS_MIN = 2
OPTIONS_MAX = 6

IRT_COMPONENTS = (("a", "float"), ("b", "float"), ("c", "float"))
CAT_COMPONENTS = (("area", "str"), ("exposure_cap", "float"), ("demand", "str"))

DIFFICULTY_MIN = 1
DIFFICULTY_MAX = 5

FIELD_SEP = "|"
LIST_SEP = ","
QUOTE = '"'
MARK = "*"
ESCAPE = "\\"

_INT_RE = re.compile(r"^[+-]?\d+$")
_FLOAT_RE = re.compile(r"^[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?$")

_SIMPLE_ESCAPES = {"n": "\n", "t": "\t", "r": "\r"}


# --------------------------------------------------------------------------
# errors
# --------------------------------------------------------------------------


class MiniFormatError(ValueError):
    """Raised for any malformed .mini document; carries the line number."""

    def __init__(self, line, message):
        self.line = line
        self.detail = message
        ValueError.__init__(self, "line %d: %s" % (line, message))


def _err(line, message):
    raise MiniFormatError(line, message)


# --------------------------------------------------------------------------
# low level scanning
#
# A raw value is turned into a list of (character, was_escaped) pairs.  The
# flag lets the splitters tell a structural separator ( '|', ',', '"', '*' )
# apart from the very same character written as data via a backslash escape.
# --------------------------------------------------------------------------


def _scan(raw, line):
    tokens = []
    i = 0
    size = len(raw)
    while i < size:
        ch = raw[i]
        if ch == ESCAPE:
            if i + 1 >= size:
                _err(line, "dangling escape character '\\' at end of line")
            nxt = raw[i + 1]
            tokens.append((_SIMPLE_ESCAPES.get(nxt, nxt), True))
            i += 2
        else:
            tokens.append((ch, False))
            i += 1
    return tokens


def _text(tokens):
    return "".join(ch for ch, _ in tokens)


def _split_fields(tokens):
    """Split a scanned line on unescaped '|' separators."""
    parts = [[]]
    for token in tokens:
        if token[0] == FIELD_SEP and not token[1]:
            parts.append([])
        else:
            parts[-1].append(token)
    return parts


def _split_elements(tokens, line):
    """Split a scanned field on unescaped ',' separators, CSV quotes aware.

    Characters coming from inside a quoted element are re-emitted as escaped
    tokens so that they can never be mistaken for a separator or for the '*'
    selection marker.
    """
    parts = []
    current = []
    in_quotes = False
    i = 0
    size = len(tokens)
    while i < size:
        ch, escaped = tokens[i]
        if in_quotes:
            if ch == QUOTE and not escaped:
                if i + 1 < size and tokens[i + 1][0] == QUOTE and not tokens[i + 1][1]:
                    current.append((QUOTE, True))
                    i += 2
                    continue
                in_quotes = False
                i += 1
                continue
            current.append((ch, True))
            i += 1
            continue
        if ch == QUOTE and not escaped and not current:
            in_quotes = True
            i += 1
            continue
        if ch == LIST_SEP and not escaped:
            parts.append(current)
            current = []
            i += 1
            continue
        current.append((ch, escaped))
        i += 1
    if in_quotes:
        _err(line, "unterminated double-quoted element")
    parts.append(current)
    return parts


def _is_marked(element):
    return bool(element) and element[-1][0] == MARK and not element[-1][1]


# --------------------------------------------------------------------------
# scalar conversion helpers
# --------------------------------------------------------------------------


def _to_int(raw, line, what):
    value = raw.strip()
    if not _INT_RE.match(value):
        _err(line, "%s must be an integer, found %r" % (what, raw))
    return int(value)


def _to_float(raw, line, what):
    value = raw.strip()
    if not _FLOAT_RE.match(value):
        _err(line, "%s must be a number, found %r" % (what, raw))
    return float(value)


def _coerce(raw):
    """Best-effort typing of a free-form header list/tuple component."""
    value = raw.strip()
    if value == "":
        return None
    if _INT_RE.match(value):
        return int(value)
    if _FLOAT_RE.match(value):
        return float(value)
    if value == "true":
        return True
    if value == "false":
        return False
    return raw


# --------------------------------------------------------------------------
# header
# --------------------------------------------------------------------------


def _parse_header(raw_line):
    line = 1
    tokens = _scan(raw_line, line)
    fields = _split_fields(tokens)

    prefix = _text(fields[0]).strip()
    if prefix == "":
        _err(line, "missing family prefix; the header must start with %r" % PREFIX)
    if prefix != PREFIX:
        _err(line, "unknown family prefix %r; expected %r" % (prefix, PREFIX))

    header = {}
    for key in HEADER_KEYS:
        header[key] = None

    seen = []
    for raw_field in fields[1:]:
        if not raw_field or _text(raw_field).strip() == "":
            _err(line, "empty header attribute; expected 'key=value'")
        eq = -1
        for index, token in enumerate(raw_field):
            if token[0] == "=" and not token[1]:
                eq = index
                break
        if eq < 0:
            _err(
                line,
                "malformed header attribute %r; expected 'key=value'"
                % _text(raw_field),
            )
        key = _text(raw_field[:eq]).strip()
        value_tokens = raw_field[eq + 1:]
        raw_value = _text(value_tokens)

        if key == "":
            _err(line, "header attribute without a name")
        if key not in HEADER_KEYS:
            _err(line, "unknown header key %r" % key)
        if key in seen:
            _err(line, "duplicate header key %r" % key)
        seen.append(key)

        if raw_value.strip() == "":
            if key in HEADER_REQUIRED:
                _err(line, "header key %r is mandatory and cannot be empty" % key)
            header[key] = None
            continue

        if key in HEADER_INT_KEYS:
            header[key] = _to_int(raw_value, line, "header key %r" % key)
        elif key in HEADER_LIST_KEYS:
            elements = _split_elements(value_tokens, line)
            header[key] = [_coerce(_text(element)) for element in elements]
        else:
            header[key] = raw_value

    for key in HEADER_REQUIRED:
        if key not in seen:
            _err(line, "missing mandatory header key %r" % key)
    if header["n"] < 0:
        _err(line, "header key 'n' must not be negative")
    if header["k"] is not None and header["k"] < 0:
        _err(line, "header key 'k' must not be negative")

    return prefix, header


# --------------------------------------------------------------------------
# record components
# --------------------------------------------------------------------------


def _parse_marked_list(tokens, line, label):
    elements = _split_elements(tokens, line)
    if len(elements) < OPTIONS_MIN or len(elements) > OPTIONS_MAX:
        _err(
            line,
            "field %r must hold between %d and %d elements, found %d"
            % (label, OPTIONS_MIN, OPTIONS_MAX, len(elements)),
        )

    items = []
    correct = None
    for index, element in enumerate(elements):
        if _is_marked(element):
            if correct is not None:
                _err(
                    line,
                    "field %r carries more than one '*' marker" % label,
                )
            correct = index
            element = element[:-1]
        value = _text(element)
        if value == "":
            _err(line, "element %d of field %r is empty" % (index + 1, label))
        items.append(value)

    if correct is None:
        _err(line, "field %r must carry exactly one '*' marker" % label)

    return {"items": items, "correct": correct}


def _parse_tuple(tokens, line, label, components):
    elements = _split_elements(tokens, line)
    if len(elements) != len(components):
        _err(
            line,
            "field %r expects exactly %d components, found %d"
            % (label, len(components), len(elements)),
        )

    result = {}
    for (name, kind), element in zip(components, elements):
        raw = _text(element)
        if raw.strip() == "":
            _err(line, "component %r of field %r is empty" % (name, label))
        if kind == "float":
            result[name] = _to_float(raw, line, "component %r of field %r" % (name, label))
        else:
            result[name] = raw
    return result


def _parse_record(raw_line, line):
    tokens = _scan(raw_line, line)
    fields = _split_fields(tokens)
    if len(fields) != RECORD_ARITY:
        _err(
            line,
            "record must have exactly %d fields, found %d"
            % (RECORD_ARITY, len(fields)),
        )

    values = [_text(field) for field in fields]
    for index, name in enumerate(RECORD_FIELDS):
        if values[index].strip() == "":
            _err(line, "field %r is mandatory and cannot be empty" % name)

    record = {}
    record["id"] = values[0]

    bloom = values[1].strip()
    if bloom not in BLOOM_LEVELS:
        _err(
            line,
            "field 'bloom' must be one of %s, found %r"
            % ("|".join(BLOOM_LEVELS), values[1]),
        )
    record["bloom"] = bloom

    record["topic"] = values[2]
    record["statement"] = values[3]
    record["options"] = _parse_marked_list(fields[4], line, "options")
    record["irt"] = _parse_tuple(fields[5], line, "irt", IRT_COMPONENTS)

    difficulty = _to_int(values[6], line, "field 'difficulty'")
    if difficulty < DIFFICULTY_MIN or difficulty > DIFFICULTY_MAX:
        _err(
            line,
            "field 'difficulty' must be in [%d..%d], found %d"
            % (DIFFICULTY_MIN, DIFFICULTY_MAX, difficulty),
        )
    record["difficulty"] = difficulty

    record["cat"] = _parse_tuple(fields[7], line, "cat", CAT_COMPONENTS)
    return record


# --------------------------------------------------------------------------
# document
# --------------------------------------------------------------------------


def parse(text):
    """Parse a .mini family 'a' document and return its canonical object."""
    if not isinstance(text, str):
        _err(1, "input must be a string, found %s" % type(text).__name__)

    if text.startswith("﻿"):
        text = text[1:]

    lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    while lines and lines[-1].strip() == "":
        lines.pop()
    if not lines:
        _err(1, "empty document; a header line is required")

    prefix, header = _parse_header(lines[0])

    record_lines = lines[1:]
    for offset, raw_line in enumerate(record_lines):
        if raw_line.strip() == "":
            _err(offset + 2, "blank lines are not allowed between records")

    declared = header["n"]
    found = len(record_lines)
    if found != declared:
        if found > declared:
            bad_line = declared + 2
        else:
            bad_line = found + 1
        _err(
            bad_line,
            "header declares n=%d but the document contains %d record line(s)"
            % (declared, found),
        )

    items = []
    for offset, raw_line in enumerate(record_lines):
        items.append(_parse_record(raw_line, offset + 2))

    return {"prefix": prefix, "header": header, "items": items}
