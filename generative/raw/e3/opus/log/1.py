"""Deterministic parser for the .mini format, family 'log' (v1).

Document shape::

    log|d=<str>?, env=<str>?, host=<str>?, n=<int>
    <record line> x n

Every record line carries 8 positional fields separated by '|'::

    ts | level | service | code | message | tags | trace | duration_ms

`parse(text)` returns {'prefix', 'header', 'events'} and raises ValueError
(always mentioning the offending 1-based line number) on invalid input.
"""

FAMILY = "log"

LEVELS = ("DEBUG", "INFO", "WARN", "ERROR", "CRITICAL")

FIELD_NAMES = (
    "ts",
    "level",
    "service",
    "code",
    "message",
    "tags",
    "trace",
    "duration_ms",
)

ARITY = len(FIELD_NAMES)

HEADER_KEYS = ("d", "env", "host", "n")

OPTIONAL_FIELDS = ("trace", "duration_ms")

MAX_TAGS = 10

DIGITS = "0123456789"

FIELD_SEP = "|"
LIST_SEP = ","
MARKER = "*"
QUOTE = '"'
ESCAPE = "\\"

_SIMPLE_ESCAPES = {
    "n": "\n",
    "|": "|",
    "\\": "\\",
    ",": ",",
    "*": "*",
    '"': '"',
}


def _err(lineno, message):
    """Build the ValueError used for every rejection."""
    return ValueError("line %d: %s" % (lineno, message))


def _is_int(text):
    """True when *text* is a non-empty run of ASCII digits."""
    if not text:
        return False
    for ch in text:
        if ch not in DIGITS:
            return False
    return True


def _split_fields(raw):
    """Split a physical line on '|' separators that are not escaped."""
    parts = []
    buf = []
    i = 0
    size = len(raw)
    while i < size:
        ch = raw[i]
        if ch == ESCAPE and i + 1 < size:
            buf.append(raw[i:i + 2])
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


def _split_list(raw, lineno):
    """Split a list value on ',' honouring escapes and CSV-style quoting."""
    items = []
    buf = []
    in_quotes = False
    i = 0
    size = len(raw)
    while i < size:
        ch = raw[i]
        if ch == ESCAPE and i + 1 < size:
            buf.append(raw[i:i + 2])
            i += 2
            continue
        if ch == QUOTE:
            if in_quotes:
                if i + 1 < size and raw[i + 1] == QUOTE:
                    buf.append(QUOTE + QUOTE)
                    i += 2
                    continue
                in_quotes = False
                buf.append(ch)
                i += 1
                continue
            if "".join(buf).strip() == "":
                in_quotes = True
            buf.append(ch)
            i += 1
            continue
        if ch == LIST_SEP and not in_quotes:
            items.append("".join(buf))
            buf = []
            i += 1
            continue
        buf.append(ch)
        i += 1
    if in_quotes:
        raise _err(lineno, "unterminated quoted list element")
    items.append("".join(buf))
    return items


def _trailing_backslashes(raw, end):
    """Count the backslashes immediately before index *end*."""
    count = 0
    j = end - 1
    while j >= 0 and raw[j] == ESCAPE:
        count += 1
        j -= 1
    return count


def _take_marker(raw):
    """Return (value_without_marker, marked) for a raw list element."""
    if raw.endswith(MARKER) and _trailing_backslashes(raw, len(raw) - 1) % 2 == 0:
        return raw[:-1], True
    return raw, False


def _unquote(raw):
    """Remove CSV-style surrounding double quotes, un-doubling inner quotes."""
    if len(raw) >= 2 and raw.startswith(QUOTE) and raw.endswith(QUOTE):
        if _trailing_backslashes(raw, len(raw) - 1) % 2 == 0:
            return raw[1:-1].replace(QUOTE + QUOTE, QUOTE)
    return raw


def _unescape(raw):
    """Apply the escapes valid in any value: \\| \\\\ \\n \\, \\* ."""
    out = []
    i = 0
    size = len(raw)
    while i < size:
        ch = raw[i]
        if ch == ESCAPE and i + 1 < size:
            nxt = raw[i + 1]
            if nxt in _SIMPLE_ESCAPES:
                out.append(_SIMPLE_ESCAPES[nxt])
            else:
                out.append(ESCAPE)
                out.append(nxt)
            i += 2
            continue
        out.append(ch)
        i += 1
    return "".join(out)


def _scalar(raw):
    """Decode a scalar field: trim the outer whitespace, then unescape."""
    return _unescape(raw.strip())


def _parse_list(raw, lineno):
    """Decode a list field, returning a list or {'items', 'correct'}."""
    if raw.strip() == "":
        return []
    raw_items = _split_list(raw, lineno)
    if len(raw_items) > MAX_TAGS:
        raise _err(
            lineno,
            "list 'tags' holds %d elements, the maximum is %d"
            % (len(raw_items), MAX_TAGS),
        )
    items = []
    correct = None
    for index, raw_item in enumerate(raw_items):
        body, marked = _take_marker(raw_item.strip())
        if marked:
            if correct is not None:
                raise _err(lineno, "list 'tags' carries more than one '*' marker")
            correct = index
        items.append(_unescape(_unquote(body.strip())))
    if correct is None:
        return items
    return {"items": items, "correct": correct}


def _parse_header(raw, lineno=1):
    """Validate the header line and return (prefix, header_dict)."""
    parts = _split_fields(raw)
    prefix = _unescape(parts[0].strip())
    if prefix != FAMILY:
        raise _err(
            lineno,
            "header must start with the family prefix %r, found %r" % (FAMILY, prefix),
        )
    header = {"d": None, "env": None, "host": None, "n": None}
    seen = set()
    for part in parts[1:]:
        if part.strip() == "":
            raise _err(lineno, "empty key=value pair in the header")
        if "=" not in part:
            raise _err(lineno, "header entry %r is not of the form key=value" % part.strip())
        key, _, value = part.partition("=")
        key = key.strip()
        if key not in HEADER_KEYS:
            raise _err(lineno, "unknown header key %r" % key)
        if key in seen:
            raise _err(lineno, "duplicated header key %r" % key)
        seen.add(key)
        decoded = _unescape(value.strip())
        if key == "n":
            if not _is_int(decoded):
                raise _err(lineno, "header key 'n' must be a non-negative integer, found %r" % decoded)
            header["n"] = int(decoded)
        else:
            header[key] = decoded if decoded != "" else None
    if header["n"] is None:
        raise _err(lineno, "header is missing the mandatory key 'n'")
    return prefix, header


def _parse_record(raw, lineno):
    """Validate and decode a single record line."""
    parts = _split_fields(raw)
    if len(parts) != ARITY:
        raise _err(
            lineno,
            "record must hold exactly %d fields separated by '|', found %d"
            % (ARITY, len(parts)),
        )
    record = {}
    for name, chunk in zip(FIELD_NAMES, parts):
        if name == "tags":
            record[name] = _parse_list(chunk, lineno)
            continue
        value = _scalar(chunk)
        if value == "":
            if name not in OPTIONAL_FIELDS:
                raise _err(lineno, "field %r is mandatory and cannot be empty" % name)
            record[name] = None
            continue
        if name == "level":
            if value not in LEVELS:
                raise _err(
                    lineno,
                    "field 'level' must be one of %s, found %r"
                    % ("|".join(LEVELS), value),
                )
        elif name == "duration_ms":
            if not _is_int(value):
                raise _err(
                    lineno,
                    "field 'duration_ms' must be an integer >= 0, found %r" % value,
                )
            value = int(value)
        record[name] = value
    return record


def parse(text):
    """Parse a .mini document of family 'log' into its canonical JSON object."""
    if not isinstance(text, str):
        raise _err(1, "input must be a string")
    if text.startswith("﻿"):
        text = text[1:]
    lines = text.splitlines()
    while lines and lines[-1].strip() == "":
        lines.pop()
    if not lines:
        raise _err(1, "empty document: the header line is required")
    prefix, header = _parse_header(lines[0], 1)
    body = lines[1:]
    for offset, line in enumerate(body):
        if line.strip() == "":
            raise _err(offset + 2, "blank lines are not allowed between records")
    if header["n"] != len(body):
        raise _err(
            1,
            "header declares n=%d but the document holds %d record lines"
            % (header["n"], len(body)),
        )
    events = []
    for offset, line in enumerate(body):
        events.append(_parse_record(line, offset + 2))
    return {"prefix": prefix, "header": header, "events": events}
