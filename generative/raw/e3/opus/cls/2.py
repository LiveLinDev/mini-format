"""Deterministic parser for the .mini format, family 'cls' (v1).

Multi-label text classification outputs.  The parser validates the header
and the declared record count, validates the arity of every record, resolves
the list / quoting / '*' marker syntax and applies the escape rules.

Public API:  parse(text: str) -> dict
"""

FAMILY = "cls"

FIELD_NAMES = ("id", "text", "labels", "conf", "rationale")
OPTIONAL_FIELDS = ("rationale",)
RECORD_ARITY = len(FIELD_NAMES)

HEADER_STR_KEYS = ("d", "l", "model")
HEADER_INT_KEYS = ("k", "n")
HEADER_KEYS = HEADER_STR_KEYS + HEADER_INT_KEYS

ESCAPABLE = {
    "n": "\n",
    "\\": "\\",
    "|": "|",
    ",": ",",
    "*": "*",
    '"': '"',
}


def _err(lineno, message):
    """Build a ValueError that always reports the offending line."""
    return ValueError("line %d: %s" % (lineno, message))


def _is_digits(s):
    return len(s) > 0 and all("0" <= c <= "9" for c in s)


def _parse_int(raw, lineno, key):
    s = raw
    if s.startswith("+") or s.startswith("-"):
        body = s[1:]
    else:
        body = s
    if not _is_digits(body):
        raise _err(lineno, "header key %r expects an integer, got %r" % (key, raw))
    return int(s, 10)


def _parse_float(raw, lineno, field):
    s = raw
    if s == "":
        raise _err(lineno, "field %r must not be empty" % field)
    i = 0
    if s[i] in "+-":
        i += 1
    int_digits = 0
    while i < len(s) and "0" <= s[i] <= "9":
        i += 1
        int_digits += 1
    frac_digits = 0
    if i < len(s) and s[i] == ".":
        i += 1
        while i < len(s) and "0" <= s[i] <= "9":
            i += 1
            frac_digits += 1
    if int_digits == 0 and frac_digits == 0:
        raise _err(lineno, "field %r is not a valid number: %r" % (field, raw))
    if i < len(s) and s[i] in "eE":
        i += 1
        if i < len(s) and s[i] in "+-":
            i += 1
        exp_digits = 0
        while i < len(s) and "0" <= s[i] <= "9":
            i += 1
            exp_digits += 1
        if exp_digits == 0:
            raise _err(lineno, "field %r is not a valid number: %r" % (field, raw))
    if i != len(s):
        raise _err(lineno, "field %r is not a valid number: %r" % (field, raw))
    try:
        return float(s)
    except ValueError:
        raise _err(lineno, "field %r is not a valid number: %r" % (field, raw))


def _unescape(value, lineno, where):
    """Apply the escape rules valid in any value."""
    out = []
    i = 0
    n = len(value)
    while i < n:
        c = value[i]
        if c == "\\":
            if i + 1 >= n:
                raise _err(lineno, "dangling backslash in %s" % where)
            nxt = value[i + 1]
            if nxt not in ESCAPABLE:
                raise _err(lineno, "unknown escape '\\%s' in %s" % (nxt, where))
            out.append(ESCAPABLE[nxt])
            i += 2
            continue
        out.append(c)
        i += 1
    return "".join(out)


def _split_fields(raw, lineno):
    """Split a physical line on unescaped '|' separators."""
    parts = []
    cur = []
    i = 0
    n = len(raw)
    while i < n:
        c = raw[i]
        if c == "\\":
            if i + 1 >= n:
                raise _err(lineno, "dangling backslash at end of line")
            cur.append(c)
            cur.append(raw[i + 1])
            i += 2
            continue
        if c == "|":
            parts.append("".join(cur))
            cur = []
            i += 1
            continue
        cur.append(c)
        i += 1
    parts.append("".join(cur))
    return parts


def _split_list(raw, lineno):
    """Split a list value on unescaped ',' honouring CSV-style quoting."""
    elements = []
    cur = []
    i = 0
    n = len(raw)
    in_quotes = False
    at_start = True
    while i < n:
        c = raw[i]
        if c == "\\":
            if i + 1 >= n:
                raise _err(lineno, "dangling backslash in field 'labels'")
            cur.append(c)
            cur.append(raw[i + 1])
            i += 2
            at_start = False
            continue
        if in_quotes:
            if c == '"':
                if i + 1 < n and raw[i + 1] == '"':
                    cur.append('"')
                    cur.append('"')
                    i += 2
                    continue
                in_quotes = False
                cur.append(c)
                i += 1
                continue
            cur.append(c)
            i += 1
            continue
        if c == '"' and at_start:
            in_quotes = True
            cur.append(c)
            i += 1
            at_start = False
            continue
        if c == ",":
            elements.append("".join(cur))
            cur = []
            at_start = True
            i += 1
            continue
        cur.append(c)
        i += 1
        at_start = False
    if in_quotes:
        raise _err(lineno, "unterminated double quote in field 'labels'")
    elements.append("".join(cur))
    return elements


def _strip_marker(element):
    """Return (element_without_marker, marked) for a raw list element."""
    if element.endswith("*"):
        backslashes = 0
        j = len(element) - 2
        while j >= 0 and element[j] == "\\":
            backslashes += 1
            j -= 1
        if backslashes % 2 == 0:
            return element[:-1], True
    return element, False


def _unquote(element, lineno):
    """Remove CSV-style outer quotes, collapsing doubled inner quotes."""
    if len(element) >= 2 and element.startswith('"') and element.endswith('"'):
        inner = element[1:-1]
        out = []
        i = 0
        n = len(inner)
        while i < n:
            c = inner[i]
            if c == "\\":
                if i + 1 >= n:
                    raise _err(lineno, "dangling backslash in field 'labels'")
                out.append(c)
                out.append(inner[i + 1])
                i += 2
                continue
            if c == '"':
                if i + 1 < n and inner[i + 1] == '"':
                    out.append('"')
                    i += 2
                    continue
                raise _err(lineno, "stray double quote inside quoted list element")
            out.append(c)
            i += 1
        return "".join(out)
    return element


def _parse_marked_list(raw, lineno):
    if raw == "":
        raise _err(lineno, "field 'labels' must not be empty")
    raw_elements = _split_list(raw, lineno)
    items = []
    correct = []
    for index, raw_element in enumerate(raw_elements):
        body, marked = _strip_marker(raw_element)
        if body == "":
            raise _err(lineno, "empty element at position %d in field 'labels'" % index)
        body = _unquote(body, lineno)
        items.append(_unescape(body, lineno, "field 'labels'"))
        if marked:
            correct.append(index)
    if not correct:
        raise _err(lineno, "field 'labels' has no element marked with '*'")
    return {"items": items, "correct": correct}


def _parse_header(raw, lineno):
    parts = _split_fields(raw, lineno)
    prefix = parts[0]
    if prefix != FAMILY:
        raise _err(lineno, "expected family prefix %r, got %r" % (FAMILY, prefix))
    header = {}
    for token in parts[1:]:
        if token == "":
            raise _err(lineno, "empty header entry")
        if "=" not in token:
            raise _err(lineno, "malformed header entry %r (expected key=value)" % token)
        key, _, value = token.partition("=")
        if key not in HEADER_KEYS:
            raise _err(lineno, "unknown header key %r" % key)
        if key in header:
            raise _err(lineno, "duplicate header key %r" % key)
        if key in HEADER_INT_KEYS:
            header[key] = _parse_int(value, lineno, key)
        else:
            if value == "":
                raise _err(lineno, "header key %r must not be empty" % key)
            header[key] = _unescape(value, lineno, "header key %r" % key)
    if "n" not in header:
        raise _err(lineno, "header is missing the mandatory key 'n'")
    if header["n"] < 0:
        raise _err(lineno, "header key 'n' must not be negative")
    if "k" in header and header["k"] < 0:
        raise _err(lineno, "header key 'k' must not be negative")
    return prefix, header


def _parse_record(raw, lineno):
    fields = _split_fields(raw, lineno)
    if len(fields) != RECORD_ARITY:
        raise _err(
            lineno,
            "record has %d field(s), expected %d" % (len(fields), RECORD_ARITY),
        )
    record = {}
    for name, value in zip(FIELD_NAMES, fields):
        if value == "" and name not in OPTIONAL_FIELDS:
            raise _err(lineno, "field %r must not be empty" % name)
        if name == "labels":
            record[name] = _parse_marked_list(value, lineno)
        elif name == "conf":
            conf = _parse_float(value, lineno, name)
            if conf < 0.0 or conf > 1.0:
                raise _err(lineno, "field 'conf' must lie in [0, 1], got %r" % value)
            record[name] = conf
        else:
            if value == "":
                record[name] = None
            else:
                record[name] = _unescape(value, lineno, "field %r" % name)
    return record


def parse(text):
    """Parse a .mini document of family 'cls' into its canonical object."""
    if not isinstance(text, str):
        raise ValueError("line 1: input must be a string")

    body = text
    if body.startswith("﻿"):
        body = body[1:]
    lines = body.split("\n")
    lines = [line[:-1] if line.endswith("\r") else line for line in lines]

    while lines and lines[-1].strip() == "":
        lines.pop()
    if not lines:
        raise ValueError("line 1: document is empty")

    prefix, header = _parse_header(lines[0], 1)

    records = []
    for offset, raw in enumerate(lines[1:]):
        lineno = offset + 2
        if raw.strip() == "":
            raise _err(lineno, "blank line is not allowed between records")
        records.append(_parse_record(raw, lineno))

    if header["n"] != len(records):
        raise _err(
            1,
            "header declares n=%d but the document contains %d record line(s)"
            % (header["n"], len(records)),
        )

    return {"prefix": prefix, "header": header, "messages": records}
