"""Deterministic parser for the .mini format, family 'cls' v1.

Multi-label text classification outputs.  The document is plain UTF-8 text:
the first line is the header ``cls|...`` carrying ``key=value`` parameters
(``n`` is mandatory and must equal the number of record lines), and every
following line is one record made of exactly five '|'-separated fields:

    id | text | labels | conf | rationale?

``labels`` is a ','-separated list whose selected elements carry a trailing
'*'.  Elements containing the list separator may be quoted CSV-style (the
'*' marker then follows the closing quote) or may escape the separator as
'\\,'.  A literal trailing asterisk is written '\\*'.  The escapes '\\|',
'\\\\' and '\\n' are valid inside any value; scalar fields are never quoted.

``parse(text)`` returns {'prefix', 'header', 'messages'} and raises
``ValueError`` mentioning the offending line for any invalid document.
The family defines no tuple-shaped field: every list element is a scalar,
so list parsing yields plain strings plus the '*' marker information.
"""

_PREFIX = "cls"

# Field names, in positional order (names are never written in the document).
_FIELDS = ("id", "text", "labels", "conf", "rationale")

# Fields whose value may be empty (empty field == null).
_OPTIONAL_FIELDS = frozenset(("rationale",))

# Header parameters that carry integers.
_INT_HEADER_KEYS = frozenset(("k", "n"))

# Recognised escape sequences: '\|', '\\' and '\n' are valid in any value;
# '\,' and '\*' additionally disambiguate the list separator and the
# selection marker.  '\"' is accepted inside quoted list elements.
_ESCAPES = {
    "\\": "\\",
    "|": "|",
    "n": "\n",
    ",": ",",
    "*": "*",
    '"': '"',
}

_KEY_CHARS = frozenset(
    "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-."
)


def _err(lineno, message):
    """Build the ValueError used for every rejection, reporting the line."""
    return ValueError("line %d: %s" % (lineno, message))


def _split_escaped(value, separator, lineno):
    """Split on unescaped `separator`, keeping backslash sequences intact."""
    pieces = []
    current = []
    index = 0
    length = len(value)
    while index < length:
        char = value[index]
        if char == "\\":
            if index + 1 >= length:
                raise _err(lineno, "dangling escape character '\\' at end of line")
            current.append(char)
            current.append(value[index + 1])
            index += 2
            continue
        if char == separator:
            pieces.append("".join(current))
            current = []
            index += 1
            continue
        current.append(char)
        index += 1
    pieces.append("".join(current))
    return pieces


def _unescape(value, lineno):
    """Resolve the escape sequences of a scalar value."""
    out = []
    index = 0
    length = len(value)
    while index < length:
        char = value[index]
        if char == "\\":
            if index + 1 >= length:
                raise _err(lineno, "dangling escape character '\\' at end of value")
            following = value[index + 1]
            out.append(_ESCAPES.get(following, "\\" + following))
            index += 2
            continue
        out.append(char)
        index += 1
    return "".join(out)


def _to_int(text, lineno, key):
    body = text[1:] if text[:1] in ("+", "-") else text
    if not body or not body.isdigit():
        raise _err(
            lineno,
            "header parameter %r must be an integer, found %r" % (key, text),
        )
    return int(text)


def _parse_label_element(raw, index, lineno):
    """Parse one list element starting at `index`.

    Returns (value, selected, next_index) where `next_index` points at the
    element separator (or at the end of the field).
    """
    length = len(raw)
    parts = []

    if index < length and raw[index] == '"':
        # CSV-style quoted element: the separator ',' is literal inside the
        # quotes, '""' denotes a literal quote, and the '*' marker (if any)
        # follows the closing quote.
        index += 1
        closed = False
        while index < length:
            char = raw[index]
            if char == "\\":
                if index + 1 >= length:
                    raise _err(lineno, "dangling escape character '\\' at end of value")
                following = raw[index + 1]
                parts.append(_ESCAPES.get(following, "\\" + following))
                index += 2
                continue
            if char == '"':
                if index + 1 < length and raw[index + 1] == '"':
                    parts.append('"')
                    index += 2
                    continue
                index += 1
                closed = True
                break
            parts.append(char)
            index += 1
        if not closed:
            raise _err(
                lineno, "unterminated quoted element in list field 'labels'"
            )
        selected = False
        if index < length and raw[index] == "*":
            selected = True
            index += 1
        if index < length and raw[index] != ",":
            raise _err(
                lineno,
                "unexpected text after the closing quote of an element in "
                "list field 'labels'",
            )
        return "".join(parts), selected, index

    # Unquoted element: read up to the next unescaped ','; a trailing
    # unescaped '*' is the selection marker ('\*' is a literal asterisk).
    trailing_star = False
    while index < length:
        char = raw[index]
        if char == "\\":
            if index + 1 >= length:
                raise _err(lineno, "dangling escape character '\\' at end of value")
            following = raw[index + 1]
            parts.append(_ESCAPES.get(following, "\\" + following))
            trailing_star = False
            index += 2
            continue
        if char == ",":
            break
        parts.append(char)
        trailing_star = char == "*"
        index += 1
    selected = False
    if trailing_star:
        parts.pop()
        selected = True
    return "".join(parts), selected, index


def _parse_labels(raw, lineno):
    """Parse the marked list field into {'items': [...], 'correct': ...}."""
    if raw == "":
        raise _err(lineno, "field 'labels' is required and must not be empty")

    items = []
    marked = []
    index = 0
    length = len(raw)
    while True:
        value, selected, index = _parse_label_element(raw, index, lineno)
        if value == "":
            raise _err(lineno, "empty element in list field 'labels'")
        if selected:
            marked.append(len(items))
        items.append(value)
        if index >= length:
            break
        # raw[index] is the ',' separator here.
        index += 1
        if index >= length:
            raise _err(
                lineno, "list field 'labels' ends with a trailing separator ','"
            )

    if not marked:
        raise _err(
            lineno,
            "field 'labels' carries no selected element: at least one label "
            "must be suffixed with '*'",
        )

    # One selection is reported as its index; a multi-label selection keeps
    # every marked index, in ascending order.
    correct = marked[0] if len(marked) == 1 else marked
    return {"items": items, "correct": correct}


def _parse_conf(raw, lineno):
    if raw == "":
        raise _err(lineno, "field 'conf' is required and must not be empty")
    value = _unescape(raw, lineno).strip()
    if value.startswith('"') or value.endswith('"'):
        raise _err(lineno, "scalar field 'conf' must not be quoted")
    try:
        number = float(value)
    except ValueError:
        raise _err(lineno, "field 'conf' must be a float, found %r" % value)
    if not 0.0 <= number <= 1.0:
        raise _err(lineno, "field 'conf' must lie in [0..1], found %r" % value)
    return number


def _parse_required_scalar(name, raw, lineno):
    if raw == "":
        raise _err(
            lineno, "field %r is required and must not be empty" % name
        )
    return _unescape(raw, lineno)


def _header_chunks(part, lineno):
    """Split a header segment into 'key=value' chunks.

    Parameters are separated by '|'; a segment additionally holding several
    ',' separated 'key=value' pairs is split as well, but only when every
    resulting chunk really looks like a parameter (so a value containing a
    comma is left untouched).
    """
    if "," not in part:
        return [part]
    chunks = _split_escaped(part, ",", lineno)
    for chunk in chunks:
        stripped = chunk.strip()
        key, sep, _ = stripped.partition("=")
        key = key.strip()
        if not sep or not key or not all(char in _KEY_CHARS for char in key):
            return [part]
    return chunks


def _parse_header(line, lineno):
    segments = _split_escaped(line, "|", lineno)
    prefix = _unescape(segments[0], lineno).strip()
    if prefix != _PREFIX:
        raise _err(
            lineno,
            "header must start with the family prefix %r, found %r"
            % (_PREFIX, prefix),
        )

    header = {}
    for segment in segments[1:]:
        for chunk in _header_chunks(segment, lineno):
            chunk = chunk.strip()
            if chunk == "":
                raise _err(lineno, "empty header parameter")
            key, sep, value = chunk.partition("=")
            key = key.strip()
            if not sep or key == "":
                raise _err(
                    lineno,
                    "header parameter %r is not of the form key=value"
                    % _unescape(chunk, lineno),
                )
            if key in header:
                raise _err(lineno, "duplicate header parameter %r" % key)
            value = _unescape(value.strip(), lineno)
            if key in _INT_HEADER_KEYS:
                header[key] = _to_int(value, lineno, key)
            else:
                header[key] = value

    if "n" not in header:
        raise _err(lineno, "header is missing the mandatory parameter 'n'")
    if header["n"] < 0:
        raise _err(lineno, "header parameter 'n' must not be negative")
    if "k" in header and header["k"] < 0:
        raise _err(lineno, "header parameter 'k' must not be negative")
    return prefix, header


def _parse_record(line, lineno):
    fields = _split_escaped(line, "|", lineno)
    if len(fields) != len(_FIELDS):
        raise _err(
            lineno,
            "record must have exactly %d fields separated by '|', found %d"
            % (len(_FIELDS), len(fields)),
        )

    identifier, text, labels, conf, rationale = fields
    record = {
        "id": _parse_required_scalar("id", identifier, lineno),
        "text": _parse_required_scalar("text", text, lineno),
        "labels": _parse_labels(labels, lineno),
        "conf": _parse_conf(conf, lineno),
        "rationale": None if rationale == "" else _unescape(rationale, lineno),
    }
    return record


def parse(text: str) -> dict:
    """Parse a .mini 'cls' document into its canonical JSON object."""
    if not isinstance(text, str):
        raise TypeError("parse() expects a str, got %s" % type(text).__name__)

    if text.startswith("﻿"):
        text = text[1:]

    lines = [
        line[:-1] if line.endswith("\r") else line for line in text.split("\n")
    ]
    # A document may end with newline(s); blank lines between records may not.
    while lines and lines[-1].strip() == "":
        lines.pop()
    if not lines:
        raise _err(1, "document is empty: the header line is mandatory")

    prefix, header = _parse_header(lines[0], 1)

    messages = []
    for offset, line in enumerate(lines[1:]):
        lineno = offset + 2
        if line.strip() == "":
            raise _err(lineno, "blank lines are not allowed between records")
        messages.append(_parse_record(line, lineno))

    declared = header["n"]
    if len(messages) != declared:
        reported = declared + 2 if len(messages) > declared else 1
        raise _err(
            reported,
            "header declares n=%d but the document contains %d record line(s)"
            % (declared, len(messages)),
        )

    return {"prefix": prefix, "header": header, "messages": messages}
