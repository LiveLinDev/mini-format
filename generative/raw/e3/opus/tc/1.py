"""Deterministic parser for the .mini format, family 'tc' (software test cases), v1.

Public API: parse(text: str) -> dict

The returned object is shaped:

    {
        "prefix": "tc",
        "header": {"n": <int>, "d": <str|None>, ...},
        "cases": [ {<field name>: <value>, ...}, ... ]
    }

Every invalid document raises ValueError mentioning the offending line number.
No third-party imports are used.
"""

FAMILY = "tc"

HEADER_KEYS = ("d", "l", "t", "proj", "n")
HEADER_REQUIRED = ("n",)

FIELDS = (
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

PRIORITIES = ("low", "medium", "high", "critical")
TYPES = (
    "functional",
    "integration",
    "performance",
    "security",
    "usability",
    "regression",
)

# Escapes valid in any value, plus the list/marker escapes.
ESCAPES = {
    "\\": "\\",
    "|": "|",
    "n": "\n",
    ",": ",",
    "*": "*",
}

FIELD_SEP = "|"
LIST_SEP = ","
QUOTE = '"'
MARKER = "*"

STEPS_MIN = 1
STEPS_MAX = 20


class MiniFormatError(ValueError):
    """Raised for any malformed .mini document; the message names the line."""


def _err(line, message):
    return MiniFormatError("line %d: %s" % (line, message))


# --------------------------------------------------------------------------
# low level scanning helpers
# --------------------------------------------------------------------------


def _split_escaped(raw, sep, line):
    """Split ``raw`` on unescaped occurrences of ``sep``.

    Backslash escape pairs are carried through untouched so that a later
    unescape pass can resolve them; ``\\|`` therefore never splits while
    ``\\\\|`` does.
    """
    parts = []
    buf = []
    i = 0
    size = len(raw)
    while i < size:
        char = raw[i]
        if char == "\\":
            if i + 1 >= size:
                raise _err(line, "dangling backslash at end of value")
            buf.append(char)
            buf.append(raw[i + 1])
            i += 2
            continue
        if char == sep:
            parts.append("".join(buf))
            buf = []
            i += 1
            continue
        buf.append(char)
        i += 1
    parts.append("".join(buf))
    return parts


def _unescape(raw, line):
    """Resolve escape sequences of a single value."""
    out = []
    i = 0
    size = len(raw)
    while i < size:
        char = raw[i]
        if char == "\\":
            if i + 1 >= size:
                raise _err(line, "dangling backslash at end of value")
            nxt = raw[i + 1]
            if nxt not in ESCAPES:
                raise _err(line, "unknown escape sequence '\\%s'" % nxt)
            out.append(ESCAPES[nxt])
            i += 2
            continue
        out.append(char)
        i += 1
    return "".join(out)


def _trailing_backslashes(raw, index):
    """Number of consecutive backslashes ending right before ``index``."""
    count = 0
    pos = index - 1
    while pos >= 0 and raw[pos] == "\\":
        count += 1
        pos -= 1
    return count


# --------------------------------------------------------------------------
# lists (and the '*' marker)
# --------------------------------------------------------------------------


def _parse_element(raw, start, line, name):
    """Parse one list element beginning at ``start``.

    Returns (value, marked, next_position, more) where ``more`` says whether a
    separator was consumed and another element follows.
    """
    size = len(raw)
    marked = False

    if start < size and raw[start] == QUOTE:
        # CSV-style quoted element: the separator is literal inside the quotes
        # and the optional '*' marker goes after the closing quote.
        buf = []
        i = start + 1
        closed = False
        while i < size:
            char = raw[i]
            if char == "\\":
                if i + 1 >= size:
                    raise _err(line, "dangling backslash at end of value")
                buf.append(char)
                buf.append(raw[i + 1])
                i += 2
                continue
            if char == QUOTE:
                if i + 1 < size and raw[i + 1] == QUOTE:
                    buf.append(QUOTE)
                    i += 2
                    continue
                closed = True
                i += 1
                break
            buf.append(char)
            i += 1
        if not closed:
            raise _err(line, "unterminated quoted element in field '%s'" % name)
        if i < size and raw[i] == MARKER:
            marked = True
            i += 1
        if i < size and raw[i] != LIST_SEP:
            raise _err(
                line,
                "unexpected text after quoted element in field '%s'" % name,
            )
        value = _unescape("".join(buf), line)
        if i < size:
            return value, marked, i + 1, True
        return value, marked, i, False

    # Unquoted element: runs up to the next unescaped separator.
    buf = []
    i = start
    while i < size:
        char = raw[i]
        if char == "\\":
            if i + 1 >= size:
                raise _err(line, "dangling backslash at end of value")
            buf.append(char)
            buf.append(raw[i + 1])
            i += 2
            continue
        if char == LIST_SEP:
            break
        buf.append(char)
        i += 1

    chunk = "".join(buf)
    if chunk.endswith(MARKER) and _trailing_backslashes(chunk, len(chunk) - 1) % 2 == 0:
        marked = True
        chunk = chunk[:-1]
    value = _unescape(chunk, line)
    if value == "":
        raise _err(line, "empty element in list field '%s'" % name)
    if i < size:
        return value, marked, i + 1, True
    return value, marked, i, False


def _parse_list(raw, line, name, minimum=STEPS_MIN, maximum=STEPS_MAX):
    """Parse a ','-separated list field, honouring quoting and the marker."""
    if raw == "":
        raise _err(line, "field '%s' is empty but requires at least %d element(s)" % (name, minimum))

    items = []
    correct = None
    pos = 0
    while True:
        value, marked, pos, more = _parse_element(raw, pos, line, name)
        items.append(value)
        if marked:
            if correct is not None:
                raise _err(line, "more than one '*' marker in field '%s'" % name)
            correct = len(items) - 1
        if not more:
            break
        if pos > len(raw):
            break

    if len(items) < minimum or len(items) > maximum:
        raise _err(
            line,
            "field '%s' has %d element(s); expected between %d and %d"
            % (name, len(items), minimum, maximum),
        )

    if correct is None:
        return items
    return {"items": items, "correct": correct}


# --------------------------------------------------------------------------
# scalars
# --------------------------------------------------------------------------


def _scalar(raw, line, name, required=True):
    value = _unescape(raw, line)
    if value == "":
        if required:
            raise _err(line, "field '%s' is empty but mandatory" % name)
        return None
    return value


def _enum(raw, line, name, allowed):
    value = _scalar(raw, line, name)
    if value not in allowed:
        raise _err(
            line,
            "field '%s' has invalid value %r; expected one of {%s}"
            % (name, value, "|".join(allowed)),
        )
    return value


def _boolean(raw, line, name):
    value = _scalar(raw, line, name)
    if value == "true":
        return True
    if value == "false":
        return False
    raise _err(line, "field '%s' must be 'true' or 'false', found %r" % (name, value))


def _integer(raw, line, name):
    value = _unescape(raw, line)
    if value == "":
        raise _err(line, "header key '%s' is empty but mandatory" % name)
    negative = value.startswith("-")
    digits = value[1:] if negative else value
    if digits == "" or not digits.isdigit():
        raise _err(line, "header key '%s' must be an integer, found %r" % (name, value))
    number = int(value)
    if number < 0:
        raise _err(line, "header key '%s' must not be negative" % name)
    return number


# --------------------------------------------------------------------------
# header and records
# --------------------------------------------------------------------------


def _parse_header(raw, line):
    parts = _split_escaped(raw, FIELD_SEP, line)
    prefix = _unescape(parts[0], line)
    if prefix != FAMILY:
        raise _err(line, "expected family prefix %r, found %r" % (FAMILY, prefix))

    header = {}
    for chunk in parts[1:]:
        if chunk == "":
            raise _err(line, "empty header entry")
        pieces = _split_escaped(chunk, "=", line)
        if len(pieces) < 2:
            raise _err(line, "header entry %r is not 'key=value'" % _unescape(chunk, line))
        key = _unescape(pieces[0], line)
        raw_value = "=".join(pieces[1:])
        if key not in HEADER_KEYS:
            raise _err(line, "unknown header key %r" % key)
        if key in header:
            raise _err(line, "duplicated header key %r" % key)
        if key == "n":
            header[key] = _integer(raw_value, line, key)
        else:
            value = _unescape(raw_value, line)
            header[key] = value if value != "" else None

    for key in HEADER_REQUIRED:
        if key not in header:
            raise _err(line, "missing mandatory header key %r" % key)

    return prefix, header


def _parse_record(raw, line):
    parts = _split_escaped(raw, FIELD_SEP, line)
    if len(parts) != len(FIELDS):
        raise _err(
            line,
            "expected %d fields, found %d" % (len(FIELDS), len(parts)),
        )

    record = {
        "id": _scalar(parts[0], line, "id"),
        "module": _scalar(parts[1], line, "module"),
        "title": _scalar(parts[2], line, "title"),
        "precondition": _scalar(parts[3], line, "precondition"),
        "steps": _parse_list(parts[4], line, "steps", STEPS_MIN, STEPS_MAX),
        "expected": _scalar(parts[5], line, "expected"),
        "priority": _enum(parts[6], line, "priority", PRIORITIES),
        "type": _enum(parts[7], line, "type", TYPES),
        "automated": _boolean(parts[8], line, "automated"),
    }
    return record


# --------------------------------------------------------------------------
# document
# --------------------------------------------------------------------------


def parse(text):
    """Parse a .mini document of family 'tc' and return its canonical object."""
    if not isinstance(text, str):
        raise _err(1, "document must be a string")

    if text.startswith("﻿"):
        text = text[1:]

    lines = text.split("\n")
    lines = [item[:-1] if item.endswith("\r") else item for item in lines]

    # A trailing newline (or several) at end of file is tolerated.
    while lines and lines[-1].strip() == "":
        lines.pop()

    if not lines:
        raise _err(1, "empty document: the header line is missing")

    prefix, header = _parse_header(lines[0], 1)

    cases = []
    for offset, raw in enumerate(lines[1:]):
        line = offset + 2
        if raw.strip() == "":
            raise _err(line, "blank line is not allowed between records")
        cases.append(_parse_record(raw, line))

    declared = header["n"]
    if declared != len(cases):
        raise _err(
            1,
            "header declares n=%d but the document has %d record line(s)"
            % (declared, len(cases)),
        )

    return {"prefix": prefix, "header": header, "cases": cases}
