"""Deterministic parser for the .mini text format, family 'tc' v1.

Document shape
--------------
Line 1 (header):   tc|n=<int>|d=<str>?|l=<str>?|t=<str>?|proj=<str>?
Lines 2..n+1:      one record per line, 9 '|'-separated fields:
    id | module | title | precondition | steps | expected |
    priority | type | automated

`steps` is a ','-separated list (1..20 elements); an element that
contains the separator may be quoted CSV-style or may escape it as '\\,'.
An unescaped trailing '*' marks the element (a literal asterisk is '\\*').

Escapes valid in any value: '\\|', '\\\\', '\\n' (plus '\\,', '\\*', '\\"'
and '\\;' for the structural characters).

`parse(text)` returns {'prefix', 'header', 'cases': [...]} and raises
ValueError (mentioning the offending line) for any invalid document.
"""

FAMILY = "tc"

FIELD_NAMES = (
    "id",
    "module",
    "title",
    "precondition",
    "steps",
    "expected",
    "priority",
    "type",
    "automated",
)

LIST_FIELDS = ("steps",)
TUPLE_FIELDS = ()
BOOL_FIELDS = ("automated",)

ENUMS = {
    "priority": ("low", "medium", "high", "critical"),
    "type": (
        "functional",
        "integration",
        "performance",
        "security",
        "usability",
        "regression",
    ),
}

LIST_LIMITS = {"steps": (1, 20)}

HEADER_KEYS = ("d", "l", "t", "proj", "n")
HEADER_OPTIONAL_KEYS = ("d", "l", "t", "proj")

FIELD_SEP = "|"
LIST_SEP = ","
TUPLE_SEP = ";"
MARKER = "*"
QUOTE = '"'
ESCAPABLE = {
    "|": "|",
    "\\": "\\",
    "n": "\n",
    ",": ",",
    ";": ";",
    "*": "*",
    '"': '"',
}

DIGITS = "0123456789"


def _fail(line_no, message):
    """Raise a ValueError that always reports the offending line."""
    raise ValueError("line %d: %s" % (line_no, message))


def _is_int(token):
    return len(token) > 0 and all(ch in DIGITS for ch in token)


def _split_escaped(value, sep, line_no):
    """Split on unescaped occurrences of `sep`, keeping escape pairs intact."""
    parts = []
    buf = []
    i = 0
    size = len(value)
    while i < size:
        ch = value[i]
        if ch == "\\":
            if i + 1 >= size:
                _fail(line_no, "dangling backslash at end of value")
            buf.append(ch)
            buf.append(value[i + 1])
            i += 2
            continue
        if ch == sep:
            parts.append("".join(buf))
            buf = []
            i += 1
            continue
        buf.append(ch)
        i += 1
    parts.append("".join(buf))
    return parts


def _unescape(value, line_no):
    """Resolve the escape sequences of a raw (already split) value."""
    out = []
    i = 0
    size = len(value)
    while i < size:
        ch = value[i]
        if ch == "\\":
            if i + 1 >= size:
                _fail(line_no, "dangling backslash at end of value")
            nxt = value[i + 1]
            if nxt not in ESCAPABLE:
                _fail(line_no, "unknown escape sequence '\\%s'" % nxt)
            out.append(ESCAPABLE[nxt])
            i += 2
            continue
        out.append(ch)
        i += 1
    return "".join(out)


def _strip_marker(segment, line_no):
    """Detect an unescaped trailing '*' on a raw list element."""
    i = 0
    size = len(segment)
    marked = False
    while i < size:
        ch = segment[i]
        if ch == "\\":
            if i + 1 >= size:
                _fail(line_no, "dangling backslash at end of list element")
            i += 2
            continue
        if ch == MARKER and i == size - 1:
            marked = True
        i += 1
    if marked:
        return segment[:-1], True
    return segment, False


def _split_collection(raw, sep, line_no, field_name):
    """Split a list/tuple value honouring CSV quoting, escapes and markers.

    Returns a list of (raw_element, marked) pairs, elements still escaped.
    """
    elements = []
    i = 0
    size = len(raw)
    while True:
        if i < size and raw[i] == QUOTE:
            j = i + 1
            buf = []
            closed = False
            while j < size:
                ch = raw[j]
                if ch == "\\":
                    if j + 1 >= size:
                        _fail(
                            line_no,
                            "dangling backslash inside quoted element of field"
                            " '%s'" % field_name,
                        )
                    buf.append(ch)
                    buf.append(raw[j + 1])
                    j += 2
                    continue
                if ch == QUOTE:
                    if j + 1 < size and raw[j + 1] == QUOTE:
                        buf.append(QUOTE)
                        j += 2
                        continue
                    closed = True
                    j += 1
                    break
                buf.append(ch)
                j += 1
            if not closed:
                _fail(
                    line_no,
                    "unterminated quoted element in field '%s'" % field_name,
                )
            marked = False
            if j < size and raw[j] == MARKER:
                marked = True
                j += 1
            if j < size and raw[j] != sep:
                _fail(
                    line_no,
                    "unexpected text after the closing quote in field '%s'"
                    % field_name,
                )
            elements.append(("".join(buf), marked))
            if j >= size:
                break
            i = j + 1
            if i == size:
                elements.append(("", False))
                break
            continue

        buf = []
        j = i
        while j < size:
            ch = raw[j]
            if ch == "\\":
                if j + 1 >= size:
                    _fail(
                        line_no,
                        "dangling backslash in field '%s'" % field_name,
                    )
                buf.append(ch)
                buf.append(raw[j + 1])
                j += 2
                continue
            if ch == sep:
                break
            buf.append(ch)
            j += 1
        segment, marked = _strip_marker("".join(buf), line_no)
        elements.append((segment, marked))
        if j >= size:
            break
        i = j + 1
        if i == size:
            elements.append(("", False))
            break
    return elements


def _parse_collection(raw, sep, line_no, field_name, quoted_ok=True):
    pairs = _split_collection(raw, sep, line_no, field_name)
    items = []
    correct = None
    for index, (segment, marked) in enumerate(pairs):
        if segment == "":
            _fail(
                line_no,
                "empty element at position %d in field '%s'"
                % (index + 1, field_name),
            )
        if marked:
            if correct is not None:
                _fail(
                    line_no,
                    "field '%s' carries more than one '*' marker" % field_name,
                )
            correct = index
        items.append(_unescape(segment, line_no))
    if not quoted_ok:
        pass
    limits = LIST_LIMITS.get(field_name)
    if limits is not None:
        low, high = limits
        if len(items) < low or len(items) > high:
            _fail(
                line_no,
                "field '%s' must hold between %d and %d elements, found %d"
                % (field_name, low, high, len(items)),
            )
    if correct is None:
        return items
    return {"items": items, "correct": correct}


def _parse_bool(raw, line_no, field_name):
    if raw == "true":
        return True
    if raw == "false":
        return False
    _fail(
        line_no,
        "field '%s' must be the boolean 'true' or 'false', found %r"
        % (field_name, raw),
    )


def _parse_header(line, line_no=1):
    parts = _split_escaped(line, FIELD_SEP, line_no)
    prefix = parts[0]
    if prefix != FAMILY:
        _fail(
            line_no,
            "the document must start with the family prefix '%s', found %r"
            % (FAMILY, prefix),
        )
    if len(parts) < 2:
        _fail(line_no, "header is missing the mandatory 'n' field")

    header = {}
    for entry in parts[1:]:
        if entry.strip() == "":
            _fail(line_no, "empty entry in the header")
        if "=" not in entry:
            _fail(
                line_no,
                "malformed header entry %r (expected key=value)" % entry,
            )
        key, _, value = entry.partition("=")
        key = key.strip()
        if key not in HEADER_KEYS:
            _fail(line_no, "unknown header key %r" % key)
        if key in header:
            _fail(line_no, "duplicate header key %r" % key)
        header[key] = value

    if "n" not in header:
        _fail(line_no, "header is missing the mandatory 'n' field")

    raw_n = header["n"].strip()
    if not _is_int(raw_n):
        _fail(
            line_no,
            "header field 'n' must be an integer, found %r" % header["n"],
        )
    declared = int(raw_n)

    result = {"n": declared}
    for key in HEADER_OPTIONAL_KEYS:
        raw_value = header.get(key)
        if raw_value is None or raw_value == "":
            result[key] = None
        else:
            result[key] = _unescape(raw_value, line_no)
    return result, declared


def _parse_record(line, line_no):
    parts = _split_escaped(line, FIELD_SEP, line_no)
    if len(parts) != len(FIELD_NAMES):
        _fail(
            line_no,
            "record must have exactly %d fields, found %d"
            % (len(FIELD_NAMES), len(parts)),
        )

    record = {}
    for name, raw in zip(FIELD_NAMES, parts):
        if raw == "":
            _fail(line_no, "field '%s' is mandatory and cannot be empty" % name)
        if name in LIST_FIELDS:
            record[name] = _parse_collection(raw, LIST_SEP, line_no, name)
            continue
        if name in TUPLE_FIELDS:
            record[name] = _parse_collection(raw, TUPLE_SEP, line_no, name)
            continue
        value = _unescape(raw, line_no)
        if name in BOOL_FIELDS:
            record[name] = _parse_bool(raw, line_no, name)
            continue
        if name in ENUMS:
            allowed = ENUMS[name]
            if value not in allowed:
                _fail(
                    line_no,
                    "field '%s' must be one of {%s}, found %r"
                    % (name, "|".join(allowed), value),
                )
        record[name] = value
    return record


def parse(text: str) -> dict:
    """Parse a .mini 'tc' document and return its canonical JSON object."""
    if not isinstance(text, str):
        raise ValueError("line 1: the document must be a text string")

    data = text.replace("\r\n", "\n").replace("\r", "\n")
    if data.startswith("﻿"):
        data = data[1:]

    lines = data.split("\n")
    while lines and lines[-1].strip() == "":
        lines.pop()
    if not lines:
        raise ValueError("line 1: empty document, the header line is missing")

    header, declared = _parse_header(lines[0], 1)

    records = []
    for offset, raw_line in enumerate(lines[1:]):
        line_no = offset + 2
        if raw_line.strip() == "":
            _fail(line_no, "blank lines are not allowed inside the document")
        records.append((line_no, raw_line))

    if declared != len(records):
        _fail(
            1,
            "header declares n=%d but the document holds %d record lines"
            % (declared, len(records)),
        )

    cases = [_parse_record(raw_line, line_no) for line_no, raw_line in records]

    return {"prefix": FAMILY, "header": header, "cases": cases}
