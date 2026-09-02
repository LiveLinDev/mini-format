def parse(text: str) -> dict:
    """Parse a .mini document of family 'cls' v1 (multi-label text
    classification outputs) into the canonical JSON-shaped dict:
        {'prefix': str, 'header': {...}, 'messages': [record, ...]}
    Raises ValueError (mentioning the offending line number) on any
    invalid input.
    """
    if not isinstance(text, str):
        raise ValueError("line 1: input must be a string")

    lines = text.splitlines()
    if len(lines) == 0:
        raise ValueError("line 1: empty document")

    prefix, header = _parse_header(lines[0], 1)
    n = header['n']
    if n < 0:
        raise ValueError("line 1: 'n' must be a non-negative integer")

    record_lines = lines[1:]
    if len(record_lines) != n:
        raise ValueError(
            f"line 1: header declares n={n} but found "
            f"{len(record_lines)} record line(s)"
        )

    messages = []
    for offset, raw_line in enumerate(record_lines):
        line_no = offset + 2
        messages.append(_parse_record(raw_line, line_no))

    return {'prefix': prefix, 'header': header, 'messages': messages}


# ---------------------------------------------------------------------------
# Header
# ---------------------------------------------------------------------------

_HEADER_ALLOWED_KEYS = {'d', 'l', 'model', 'k', 'n'}


def _parse_header(line, line_no):
    parts = _split_escaped(line, '|')
    if not parts or parts[0] != 'cls':
        raise ValueError(
            f"line {line_no}: header must start with the 'cls' family tag"
        )
    prefix = parts[0]

    raw_fields = {}
    for token in parts[1:]:
        if '=' not in token:
            raise ValueError(
                f"line {line_no}: malformed header field '{token}'"
            )
        key, _, raw_val = token.partition('=')
        if key not in _HEADER_ALLOWED_KEYS:
            raise ValueError(
                f"line {line_no}: unknown header field '{key}'"
            )
        if key in raw_fields:
            raise ValueError(
                f"line {line_no}: duplicate header field '{key}'"
            )
        raw_fields[key] = raw_val

    if 'n' not in raw_fields or raw_fields['n'] == '':
        raise ValueError(
            f"line {line_no}: mandatory header field 'n' is missing"
        )

    header = {}

    for key in ('d', 'l', 'model'):
        raw_val = raw_fields.get(key, '')
        header[key] = _unescape(raw_val, line_no) if raw_val != '' else None

    raw_k = raw_fields.get('k', '')
    if raw_k == '':
        header['k'] = None
    else:
        try:
            header['k'] = int(raw_k)
        except ValueError:
            raise ValueError(
                f"line {line_no}: header field 'k' is not a valid integer: "
                f"'{raw_k}'"
            )

    try:
        header['n'] = int(raw_fields['n'])
    except ValueError:
        raise ValueError(
            f"line {line_no}: header field 'n' is not a valid integer: "
            f"'{raw_fields['n']}'"
        )

    return prefix, header


# ---------------------------------------------------------------------------
# Records
# ---------------------------------------------------------------------------

def _parse_record(line, line_no):
    fields = _split_escaped(line, '|')
    if len(fields) != 5:
        raise ValueError(
            f"line {line_no}: expected 5 fields, found {len(fields)}"
        )
    raw_id, raw_text, raw_labels, raw_conf, raw_rationale = fields

    if raw_id == '':
        raise ValueError(
            f"line {line_no}: mandatory field 'id' cannot be empty"
        )
    rec_id = _unescape(raw_id, line_no)

    if raw_text == '':
        raise ValueError(
            f"line {line_no}: mandatory field 'text' cannot be empty"
        )
    rec_text = _unescape(raw_text, line_no)

    if raw_labels == '':
        raise ValueError(
            f"line {line_no}: mandatory field 'labels' cannot be empty"
        )
    rec_labels = _parse_labels(raw_labels, line_no)

    if raw_conf == '':
        raise ValueError(
            f"line {line_no}: mandatory field 'conf' cannot be empty"
        )
    try:
        conf_val = float(raw_conf)
    except ValueError:
        raise ValueError(
            f"line {line_no}: field 'conf' is not a valid number: "
            f"'{raw_conf}'"
        )
    if not (0.0 <= conf_val <= 1.0):
        raise ValueError(
            f"line {line_no}: field 'conf' out of range [0,1]: {conf_val}"
        )

    if raw_rationale == '':
        rec_rationale = None
    else:
        rec_rationale = _unescape(raw_rationale, line_no)

    return {
        'id': rec_id,
        'text': rec_text,
        'labels': rec_labels,
        'conf': conf_val,
        'rationale': rec_rationale,
    }


def _parse_labels(raw, line_no):
    raw_items = _split_list(raw, line_no)
    items = []
    correct = []
    for idx, raw_item in enumerate(raw_items):
        if raw_item == '':
            raise ValueError(
                f"line {line_no}: 'labels' list contains an empty element"
            )
        value, marked = _parse_list_element(raw_item, line_no)
        items.append(value)
        if marked:
            correct.append(idx)
    if not correct:
        raise ValueError(
            f"line {line_no}: 'labels' list has no selected (*) element"
        )
    return {'items': items, 'correct': correct}


def _parse_list_element(raw, line_no):
    if raw.startswith('"'):
        n = len(raw)
        i = 1
        buf = []
        closed = False
        while i < n:
            c = raw[i]
            if c == '\\' and i + 1 < n:
                buf.append(raw[i:i + 2])
                i += 2
                continue
            if c == '"':
                closed = True
                i += 1
                break
            buf.append(c)
            i += 1
        if not closed:
            raise ValueError(
                f"line {line_no}: unterminated quoted list element"
            )
        inner_raw = ''.join(buf)
        rest = raw[i:]
        if rest == '':
            marked = False
        elif rest == '*':
            marked = True
        else:
            raise ValueError(
                f"line {line_no}: unexpected characters after quoted list "
                f"element: '{rest}'"
            )
        value = _unescape(inner_raw, line_no)
        return value, marked

    resolved = _resolve_chars(raw, line_no)
    marked = False
    if resolved and resolved[-1][0] == '*' and not resolved[-1][1]:
        marked = True
        resolved = resolved[:-1]
    value = ''.join(ch for ch, _ in resolved)
    return value, marked


# ---------------------------------------------------------------------------
# Low-level escaping / splitting helpers
# ---------------------------------------------------------------------------

_ESCAPE_MAP = {
    '|': '|',
    '\\': '\\',
    'n': '\n',
    '*': '*',
    ',': ',',
}


def _resolve_chars(raw, line_no):
    """Resolve escape sequences in raw text, returning a list of
    (char, was_escaped) pairs."""
    chars = []
    i = 0
    n = len(raw)
    while i < n:
        c = raw[i]
        if c == '\\':
            if i + 1 >= n:
                raise ValueError(
                    f"line {line_no}: dangling escape character at end of "
                    f"value"
                )
            nxt = raw[i + 1]
            if nxt not in _ESCAPE_MAP:
                raise ValueError(
                    f"line {line_no}: unknown escape sequence '\\{nxt}'"
                )
            chars.append((_ESCAPE_MAP[nxt], True))
            i += 2
            continue
        chars.append((c, False))
        i += 1
    return chars


def _unescape(raw, line_no):
    return ''.join(ch for ch, _ in _resolve_chars(raw, line_no))


def _split_escaped(s, sep):
    """Split s on unescaped occurrences of sep. Backslash-prefixed pairs
    are treated as opaque units so an escaped separator is not split on.
    No escape-validity checking is done here; that happens later when the
    individual field values are unescaped."""
    parts = []
    cur = []
    i = 0
    n = len(s)
    while i < n:
        c = s[i]
        if c == '\\' and i + 1 < n:
            cur.append(s[i:i + 2])
            i += 2
            continue
        if c == sep:
            parts.append(''.join(cur))
            cur = []
            i += 1
            continue
        cur.append(c)
        i += 1
    parts.append(''.join(cur))
    return parts


def _split_list(s, line_no):
    """Split a labels list on unescaped commas, honouring CSV-style
    double-quoted elements (which may contain unescaped commas) and the
    '\\,' escape."""
    parts = []
    cur = []
    i = 0
    n = len(s)
    while i < n:
        c = s[i]
        if c == '"' and not cur:
            j = i + 1
            buf = ['"']
            closed = False
            while j < n:
                cc = s[j]
                if cc == '\\' and j + 1 < n:
                    buf.append(s[j:j + 2])
                    j += 2
                    continue
                if cc == '"':
                    buf.append(cc)
                    j += 1
                    closed = True
                    break
                buf.append(cc)
                j += 1
            if not closed:
                raise ValueError(
                    f"line {line_no}: unterminated quoted list element"
                )
            cur.append(''.join(buf))
            i = j
            continue
        if c == '\\' and i + 1 < n:
            cur.append(s[i:i + 2])
            i += 2
            continue
        if c == ',':
            parts.append(''.join(cur))
            cur = []
            i += 1
            continue
        cur.append(c)
        i += 1
    parts.append(''.join(cur))
    return parts
