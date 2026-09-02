"""Deterministic parser for the .mini format, family 'a' v1.

Assessment items (multiple choice, Bloom + IRT 3PL + CAT metadata).

Public API::

    parse(text: str) -> dict

The returned object has the shape::

    {"prefix": "a", "header": {...}, "items": [record, ...]}

Every record is an object keyed by the field names of the specification
(``id``, ``bloom``, ``topic``, ``statement``, ``options``, ``irt``,
``difficulty``, ``cat``).  A list carrying the ``*`` selection marker is
returned as ``{"items": [...], "correct": <index>}``.

Any invalid document raises :class:`MiniFormatError` (a subclass of
``ValueError``) whose message always starts with ``line <n>:``.

Only the standard library is used.
"""

import re

__all__ = ["parse", "MiniFormatError"]


PREFIX = "a"

HEADER_KEYS = ("n", "m", "d", "l", "t", "bd", "cat", "k")
HEADER_REQUIRED = ("n",)
HEADER_INT_KEYS = ("n", "k")
HEADER_SEQ_KEYS = ("bd", "cat")

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

BLOOM_LEVELS = ("L1", "L2", "L3", "L4", "L5", "L6")
DEMAND_VALUES = ("low", "medium", "high")

IRT_FIELDS = ("a", "b", "c")
CAT_FIELDS = ("area", "exposure_cap", "demand")

OPTIONS_MIN = 2
OPTIONS_MAX = 6

DIFFICULTY_MIN = 1
DIFFICULTY_MAX = 5

FIELD_SEP = "|"
ITEM_SEP = ","
MARKER = "*"
QUOTE = '"'
ESCAPE = "\\"

_INT_RE = re.compile(r"^[+-]?\d+$")
_FLOAT_RE = re.compile(r"^[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?$")

_ESCAPE_MAP = {
    "n": "\n",
    ESCAPE: ESCAPE,
    FIELD_SEP: FIELD_SEP,
    ITEM_SEP: ITEM_SEP,
    MARKER: MARKER,
    QUOTE: QUOTE,
}


class MiniFormatError(ValueError):
    """Raised for any document that does not conform to family 'a' v1."""


def _err(line, message):
    raise MiniFormatError("line %d: %s" % (line, message))


# ---------------------------------------------------------------------------
# low level scanning helpers
# ---------------------------------------------------------------------------


def _split_fields(text, line):
    """Split a physical line on unescaped ``|``.

    Quotes are *not* significant at this level: scalar fields are never
    quoted, so a stray double quote must not swallow field separators.
    Escape sequences are preserved verbatim; they are decoded later.
    """
    parts = []
    buf = []
    i = 0
    size = len(text)
    while i < size:
        ch = text[i]
        if ch == ESCAPE:
            if i + 1 >= size:
                _err(line, "dangling escape character '\\' at end of line")
            buf.append(ch)
            buf.append(text[i + 1])
            i += 2
            continue
        if ch == FIELD_SEP:
            parts.append("".join(buf))
            buf = []
            i += 1
            continue
        buf.append(ch)
        i += 1
    parts.append("".join(buf))
    return parts


def _pop_marker(raw):
    """Return ``(raw_without_marker, marked)`` for an unquoted element.

    The trailing ``*`` only counts as the selection marker when it is not
    itself escaped (a literal trailing asterisk is written ``\\*``).
    """
    size = len(raw)
    if size == 0:
        return raw, False
    i = 0
    last_plain = -1
    while i < size:
        if raw[i] == ESCAPE and i + 1 < size:
            i += 2
            continue
        last_plain = i
        i += 1
    if last_plain == size - 1 and raw[size - 1] == MARKER:
        return raw[: size - 1], True
    return raw, False


def _split_elements(text, line, allow_marker, what):
    """Split a list/tuple value on unescaped ``,``.

    CSV-style quoting is honoured when an element *starts* with a double
    quote; inside such an element ``""`` denotes a literal quote and the
    selection marker, when present, follows the closing quote.

    Returns a list of ``(raw_element, marked)`` pairs with escape
    sequences still intact.
    """
    elements = []
    size = len(text)
    if size == 0:
        return elements
    i = 0
    while True:
        marked = False
        if i < size and text[i] == QUOTE:
            i += 1
            buf = []
            closed = False
            while i < size:
                ch = text[i]
                if ch == ESCAPE:
                    if i + 1 >= size:
                        _err(line, "dangling escape character '\\' in %s" % what)
                    buf.append(ch)
                    buf.append(text[i + 1])
                    i += 2
                    continue
                if ch == QUOTE:
                    if i + 1 < size and text[i + 1] == QUOTE:
                        buf.append(QUOTE)
                        i += 2
                        continue
                    i += 1
                    closed = True
                    break
                buf.append(ch)
                i += 1
            if not closed:
                _err(line, "unterminated quoted element in %s" % what)
            raw = "".join(buf)
            if i < size and text[i] == MARKER:
                if not allow_marker:
                    _err(line, "selection marker '*' is not allowed in %s" % what)
                marked = True
                i += 1
            if i < size and text[i] != ITEM_SEP:
                _err(
                    line,
                    "unexpected text after quoted element in %s" % what,
                )
        else:
            buf = []
            while i < size:
                ch = text[i]
                if ch == ESCAPE:
                    if i + 1 >= size:
                        _err(line, "dangling escape character '\\' in %s" % what)
                    buf.append(ch)
                    buf.append(text[i + 1])
                    i += 2
                    continue
                if ch == ITEM_SEP:
                    break
                buf.append(ch)
                i += 1
            raw = "".join(buf)
            if allow_marker:
                raw, marked = _pop_marker(raw)
        elements.append((raw, marked))
        if i < size and text[i] == ITEM_SEP:
            i += 1
            continue
        break
    return elements


def _unescape(raw, line):
    """Decode the escape sequences valid in any value."""
    if ESCAPE not in raw:
        return raw
    out = []
    i = 0
    size = len(raw)
    while i < size:
        ch = raw[i]
        if ch == ESCAPE:
            if i + 1 >= size:
                _err(line, "dangling escape character '\\' at end of value")
            nxt = raw[i + 1]
            out.append(_ESCAPE_MAP.get(nxt, nxt))
            i += 2
            continue
        out.append(ch)
        i += 1
    return "".join(out)


# ---------------------------------------------------------------------------
# scalar coercion
# ---------------------------------------------------------------------------


def _as_int(text, line, what):
    token = text.strip()
    if not _INT_RE.match(token):
        _err(line, "%s must be an integer, got %r" % (what, text))
    return int(token)


def _as_float(text, line, what):
    token = text.strip()
    if _INT_RE.match(token):
        return float(int(token))
    if not _FLOAT_RE.match(token):
        _err(line, "%s must be a number, got %r" % (what, text))
    return float(token)


def _coerce_scalar(text):
    """Header list/tuple members: numbers unquoted, booleans true/false."""
    token = text.strip()
    if token == "true":
        return True
    if token == "false":
        return False
    if _INT_RE.match(token):
        return int(token)
    if _FLOAT_RE.match(token):
        return float(token)
    return text


# ---------------------------------------------------------------------------
# header
# ---------------------------------------------------------------------------


def _parse_header(raw_line, line):
    tokens = _split_fields(raw_line, line)
    prefix = tokens[0].strip()
    if prefix != PREFIX:
        _err(line, "expected family prefix %r, got %r" % (PREFIX, prefix))
    if len(tokens) < 2:
        _err(line, "header must declare the mandatory key 'n'")

    header = dict((key, None) for key in HEADER_KEYS)
    seen = set()

    for token in tokens[1:]:
        entry = token.strip()
        if entry == "":
            _err(line, "empty header entry")
        if "=" not in entry:
            _err(line, "malformed header entry %r, expected 'key=value'" % entry)
        key, _, value = entry.partition("=")
        key = key.strip()
        if key == "":
            _err(line, "header entry with an empty key")
        if key not in HEADER_KEYS:
            _err(line, "unknown header key %r" % key)
        if key in seen:
            _err(line, "duplicated header key %r" % key)
        seen.add(key)
        value = value.strip()

        if value == "":
            if key in HEADER_REQUIRED:
                _err(line, "header key %r must not be empty" % key)
            header[key] = None
            continue

        if key in HEADER_INT_KEYS:
            header[key] = _as_int(value, line, "header key %r" % key)
        elif key in HEADER_SEQ_KEYS:
            members = _split_elements(
                value, line, False, "header key %r" % key
            )
            header[key] = [
                _coerce_scalar(_unescape(raw, line)) for raw, _ in members
            ]
        else:
            header[key] = _unescape(value, line)

    for key in HEADER_REQUIRED:
        if header.get(key) is None:
            _err(line, "missing mandatory header key %r" % key)

    if header["n"] < 0:
        _err(line, "header key 'n' must not be negative")

    return header


# ---------------------------------------------------------------------------
# records
# ---------------------------------------------------------------------------


def _scalar_field(raw, line, name):
    value = _unescape(raw, line)
    if value == "":
        _err(line, "field %r is mandatory and must not be empty" % name)
    return value


def _parse_options(raw, line):
    elements = _split_elements(raw, line, True, "field 'options'")
    count = len(elements)
    if count < OPTIONS_MIN or count > OPTIONS_MAX:
        _err(
            line,
            "field 'options' must hold between %d and %d elements, got %d"
            % (OPTIONS_MIN, OPTIONS_MAX, count),
        )
    items = []
    correct = None
    for index, (element, marked) in enumerate(elements):
        text = _unescape(element, line)
        if text == "":
            _err(line, "field 'options' contains an empty element")
        items.append(text)
        if marked:
            if correct is not None:
                _err(
                    line,
                    "field 'options' carries more than one '*' marker "
                    "(positions %d and %d)" % (correct, index),
                )
            correct = index
    if correct is None:
        _err(line, "field 'options' must carry exactly one '*' marker")
    return {"items": items, "correct": correct}


def _parse_irt(raw, line):
    elements = _split_elements(raw, line, False, "field 'irt'")
    if len(elements) != len(IRT_FIELDS):
        _err(
            line,
            "field 'irt' must hold exactly %d members (a,b,c), got %d"
            % (len(IRT_FIELDS), len(elements)),
        )
    values = {}
    for name, (element, _) in zip(IRT_FIELDS, elements):
        text = _unescape(element, line)
        if text.strip() == "":
            _err(line, "member 'irt.%s' is mandatory and must not be empty" % name)
        values[name] = _as_float(text, line, "member 'irt.%s'" % name)
    return values


def _parse_cat(raw, line):
    elements = _split_elements(raw, line, False, "field 'cat'")
    if len(elements) != len(CAT_FIELDS):
        _err(
            line,
            "field 'cat' must hold exactly %d members "
            "(area,exposure_cap,demand), got %d"
            % (len(CAT_FIELDS), len(elements)),
        )
    area = _unescape(elements[0][0], line)
    if area == "":
        _err(line, "member 'cat.area' is mandatory and must not be empty")
    exposure_raw = _unescape(elements[1][0], line)
    if exposure_raw.strip() == "":
        _err(line, "member 'cat.exposure_cap' is mandatory and must not be empty")
    exposure = _as_float(exposure_raw, line, "member 'cat.exposure_cap'")
    demand = _unescape(elements[2][0], line)
    if demand not in DEMAND_VALUES:
        _err(
            line,
            "member 'cat.demand' must be one of %s, got %r"
            % ("|".join(DEMAND_VALUES), demand),
        )
    return {"area": area, "exposure_cap": exposure, "demand": demand}


def _parse_record(raw_line, line):
    parts = _split_fields(raw_line, line)
    if len(parts) != len(RECORD_FIELDS):
        _err(
            line,
            "record must hold exactly %d fields, got %d"
            % (len(RECORD_FIELDS), len(parts)),
        )

    record = {}
    record["id"] = _scalar_field(parts[0], line, "id")

    bloom = _unescape(parts[1], line)
    if bloom not in BLOOM_LEVELS:
        _err(
            line,
            "field 'bloom' must be one of %s, got %r"
            % ("|".join(BLOOM_LEVELS), bloom),
        )
    record["bloom"] = bloom

    record["topic"] = _scalar_field(parts[2], line, "topic")
    record["statement"] = _scalar_field(parts[3], line, "statement")
    record["options"] = _parse_options(parts[4], line)
    record["irt"] = _parse_irt(parts[5], line)

    difficulty_raw = _unescape(parts[6], line)
    if difficulty_raw.strip() == "":
        _err(line, "field 'difficulty' is mandatory and must not be empty")
    difficulty = _as_int(difficulty_raw, line, "field 'difficulty'")
    if difficulty < DIFFICULTY_MIN or difficulty > DIFFICULTY_MAX:
        _err(
            line,
            "field 'difficulty' must be in [%d..%d], got %d"
            % (DIFFICULTY_MIN, DIFFICULTY_MAX, difficulty),
        )
    record["difficulty"] = difficulty

    record["cat"] = _parse_cat(parts[7], line)
    return record


# ---------------------------------------------------------------------------
# entry point
# ---------------------------------------------------------------------------


def parse(text):
    """Parse a family 'a' v1 .mini document and return its canonical object."""
    if not isinstance(text, str):
        raise MiniFormatError("line 1: input must be a string of UTF-8 text")

    body = text.replace("\r\n", "\n").replace("\r", "\n")
    if body.startswith("﻿"):
        body = body[1:]

    lines = body.split("\n")
    while lines and lines[-1].strip() == "":
        lines.pop()
    if not lines:
        raise MiniFormatError("line 1: empty document, header line is missing")

    header = _parse_header(lines[0], 1)

    record_lines = lines[1:]
    for offset, raw_line in enumerate(record_lines):
        if raw_line.strip() == "":
            _err(offset + 2, "blank lines are not allowed between records")

    declared = header["n"]
    if declared != len(record_lines):
        _err(
            1,
            "header declares n=%d but the document holds %d record lines"
            % (declared, len(record_lines)),
        )

    records = []
    for offset, raw_line in enumerate(record_lines):
        records.append(_parse_record(raw_line, offset + 2))

    return {"prefix": PREFIX, "header": header, "items": records}
