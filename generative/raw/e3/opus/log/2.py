"""Deterministic parser for the .mini format, family 'log' (v1).

Public API:
    parse(text: str) -> dict

The returned object has the shape::

    {
        "prefix": "log",
        "header": {"d": ..., "env": ..., "host": ..., "n": <int>},
        "events": [ {...}, ... ]
    }

Every event is keyed by the positional field names of the family:
``ts``, ``level``, ``service``, ``code``, ``message``, ``tags``,
``trace`` and ``duration_ms``.  A list carrying the ``*`` marker is
returned as ``{"items": [...], "correct": <index>}``; an unmarked list is
returned as a plain list.

Invalid documents raise ``ValueError`` mentioning the offending line.
No third-party imports are used.
"""

import re

FAMILY = "log"

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

REQUIRED_FIELDS = ("ts", "level", "service", "code", "message")
OPTIONAL_FIELDS = ("trace", "duration_ms")

LEVELS = ("DEBUG", "INFO", "WARN", "ERROR", "CRITICAL")

HEADER_KEYS = ("d", "env", "host", "n")

MAX_TAGS = 10

FIELD_SEP = "|"
LIST_SEP = ","
MARKER = "*"
QUOTE = '"'
ESCAPE = "\\"

_ESCAPE_MAP = {
    "|": "|",
    "\\": "\\",
    "n": "\n",
    ",": ",",
    "*": "*",
    '"': '"',
}

_TS_RE = re.compile(
    r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,9})?(?:Z|[+-]\d{2}:\d{2})$"
)

_INT_RE = re.compile(r"^\d+$")


class MiniFormatError(ValueError):
    """Raised when a .mini document violates the family specification."""


def _err(line_no, message):
    return MiniFormatError("line %d: %s" % (line_no, message))


def _split_escaped(value, separator, respect_quotes=False):
    """Split ``value`` on unescaped occurrences of ``separator``.

    Backslash escape sequences are kept verbatim (they are resolved later
    by :func:`_unescape`) so that an escaped separator never splits a
    field.  When ``respect_quotes`` is true, separators inside a
    CSV-style double quoted run are ignored as well.
    """
    parts = []
    buf = []
    in_quotes = False
    i = 0
    length = len(value)
    while i < length:
        ch = value[i]
        if ch == ESCAPE:
            if i + 1 < length:
                buf.append(ch)
                buf.append(value[i + 1])
                i += 2
                continue
            buf.append(ch)
            i += 1
            continue
        if respect_quotes and ch == QUOTE:
            in_quotes = not in_quotes
            buf.append(ch)
            i += 1
            continue
        if ch == separator and not in_quotes:
            parts.append("".join(buf))
            buf = []
            i += 1
            continue
        buf.append(ch)
        i += 1
    parts.append("".join(buf))
    return parts


def _unescape(value, line_no):
    """Resolve the escape sequences allowed in any value."""
    out = []
    i = 0
    length = len(value)
    while i < length:
        ch = value[i]
        if ch == ESCAPE:
            if i + 1 >= length:
                raise _err(line_no, "dangling backslash at the end of a value")
            nxt = value[i + 1]
            out.append(_ESCAPE_MAP.get(nxt, ESCAPE + nxt))
            i += 2
            continue
        out.append(ch)
        i += 1
    return "".join(out)


def _ends_with_plain(value, char):
    """True when ``value`` ends with an unescaped ``char``."""
    if not value:
        return False
    escaped = False
    last_index = -1
    i = 0
    length = len(value)
    while i < length:
        if value[i] == ESCAPE and i + 1 < length:
            last_index = i
            escaped = True
            i += 2
        else:
            last_index = i
            escaped = False
            i += 1
    if escaped or last_index != length - 1:
        return False
    return value[last_index] == char


def _starts_with_plain(value, char):
    return bool(value) and value[0] == char


def _parse_element(raw, line_no, field):
    """Return ``(value, marked)`` for one raw list element."""
    element = raw.strip()
    marked = False
    if _ends_with_plain(element, MARKER):
        marked = True
        element = element[:-1].rstrip()
    if (
        len(element) >= 2
        and _starts_with_plain(element, QUOTE)
        and _ends_with_plain(element, QUOTE)
    ):
        inner = element[1:-1]
        return _unescape(inner.replace(QUOTE + QUOTE, QUOTE), line_no), marked
    if _starts_with_plain(element, QUOTE):
        raise _err(
            line_no,
            "field '%s' has an unterminated quoted element: %r" % (field, raw),
        )
    return _unescape(element, line_no), marked


def _parse_list(raw, line_no, field, max_items):
    """Parse a ','-separated list, honouring quotes, escapes and the marker."""
    if raw.strip() == "":
        return []
    items = []
    correct = None
    elements = _split_escaped(raw, LIST_SEP, respect_quotes=True)
    for index, element in enumerate(elements):
        value, marked = _parse_element(element, line_no, field)
        if marked:
            if correct is not None:
                raise _err(
                    line_no,
                    "field '%s' carries more than one '*' marker" % field,
                )
            correct = index
        items.append(value)
    if max_items is not None and len(items) > max_items:
        raise _err(
            line_no,
            "field '%s' has %d elements, at most %d are allowed"
            % (field, len(items), max_items),
        )
    if correct is None:
        return items
    return {"items": items, "correct": correct}


def _scalar(raw, line_no, field, required):
    value = _unescape(raw.strip(), line_no)
    if value == "":
        if required:
            raise _err(line_no, "field '%s' is mandatory and cannot be empty" % field)
        return None
    return value


def _parse_header(line, line_no=1):
    parts = _split_escaped(line, FIELD_SEP)
    prefix = _unescape(parts[0], line_no).strip()
    if prefix != FAMILY:
        raise _err(
            line_no,
            "header must start with the family prefix %r, found %r" % (FAMILY, prefix),
        )
    header = {}
    for key in HEADER_KEYS:
        header[key] = None
    seen = set()
    for part in parts[1:]:
        raw = part.strip()
        if raw == "":
            raise _err(line_no, "empty header field")
        if "=" not in raw:
            raise _err(line_no, "malformed header field %r, expected 'key=value'" % raw)
        key, _, value = raw.partition("=")
        key = key.strip()
        if key not in header:
            raise _err(line_no, "unknown header key %r" % key)
        if key in seen:
            raise _err(line_no, "duplicated header key %r" % key)
        seen.add(key)
        value = _unescape(value.strip(), line_no)
        if key == "n":
            if not _INT_RE.match(value):
                raise _err(
                    line_no,
                    "header field 'n' must be a non-negative integer, found %r" % value,
                )
            header["n"] = int(value)
        else:
            header[key] = value if value != "" else None
    if header["n"] is None:
        raise _err(line_no, "mandatory header field 'n' is missing")
    return header


def _parse_record(line, line_no):
    fields = _split_escaped(line, FIELD_SEP)
    if len(fields) != len(FIELD_NAMES):
        raise _err(
            line_no,
            "expected %d fields, found %d" % (len(FIELD_NAMES), len(fields)),
        )
    record = {}

    ts = _scalar(fields[0], line_no, "ts", True)
    if not _TS_RE.match(ts):
        raise _err(line_no, "field 'ts' is not a valid ISO-8601 UTC timestamp: %r" % ts)
    record["ts"] = ts

    level = _scalar(fields[1], line_no, "level", True)
    if level not in LEVELS:
        raise _err(
            line_no,
            "field 'level' must be one of %s, found %r" % ("|".join(LEVELS), level),
        )
    record["level"] = level

    record["service"] = _scalar(fields[2], line_no, "service", True)
    record["code"] = _scalar(fields[3], line_no, "code", True)
    record["message"] = _scalar(fields[4], line_no, "message", True)
    record["tags"] = _parse_list(fields[5], line_no, "tags", MAX_TAGS)
    record["trace"] = _scalar(fields[6], line_no, "trace", False)

    duration = fields[7].strip()
    if duration == "":
        record["duration_ms"] = None
    else:
        duration = _unescape(duration, line_no)
        if not _INT_RE.match(duration):
            raise _err(
                line_no,
                "field 'duration_ms' must be an unquoted integer >= 0, found %r"
                % duration,
            )
        record["duration_ms"] = int(duration)

    return record


def parse(text):
    """Parse a .mini document of family 'log' and return its canonical object."""
    if not isinstance(text, str):
        raise MiniFormatError("line 1: input must be a str")
    if text.startswith("﻿"):
        text = text[1:]

    lines = text.split("\n")
    lines = [line[:-1] if line.endswith("\r") else line for line in lines]
    while lines and lines[-1].strip() == "":
        lines.pop()
    if not lines:
        raise _err(1, "document is empty, a header line is required")
    if lines[0].strip() == "":
        raise _err(1, "the first line must be the header")

    header = _parse_header(lines[0], 1)

    events = []
    for offset, line in enumerate(lines[1:]):
        line_no = offset + 2
        if line.strip() == "":
            raise _err(line_no, "blank lines are not allowed between records")
        events.append(_parse_record(line, line_no))

    if len(events) != header["n"]:
        raise _err(
            1,
            "header declares n=%d but the document contains %d record line(s)"
            % (header["n"], len(events)),
        )

    return {"prefix": FAMILY, "header": header, "events": events}
