def parse(text: str) -> dict:
    lines = text.split('\n')
    if lines and lines[-1] == '':
        lines.pop()

    if not lines:
        raise ValueError("line 1: empty document, missing header")

    header_line = lines[0]
    record_lines = lines[1:]

    header = _parse_header(header_line)

    for offset, line in enumerate(record_lines):
        if line == '':
            raise ValueError(f"line {offset + 2}: blank line is not allowed between records")

    n = header['n']
    if len(record_lines) != n:
        raise ValueError(
            f"line 1: header declares n={n} but found {len(record_lines)} record line(s)"
        )

    messages = []
    for offset, line in enumerate(record_lines):
        line_no = offset + 2
        messages.append(_parse_record(line, line_no))

    return {
        'prefix': 'cls',
        'header': header,
        'messages': messages,
    }


def _err(line_no, message):
    raise ValueError(f"line {line_no}: {message}")


def _split_top_level(s, delim):
    """Split s on unescaped occurrences of delim, leaving escape sequences
    (backslash + next char) intact in the resulting parts for later
    field-specific unescaping."""
    parts = []
    buf = []
    i = 0
    n = len(s)
    while i < n:
        c = s[i]
        if c == '\\' and i + 1 < n:
            buf.append(c)
            buf.append(s[i + 1])
            i += 2
            continue
        if c == delim:
            parts.append(''.join(buf))
            buf = []
            i += 1
            continue
        buf.append(c)
        i += 1
    parts.append(''.join(buf))
    return parts


_SCALAR_ESCAPES = {'|': '|', '\\': '\\', 'n': '\n'}
_LIST_ESCAPES = {'|': '|', '\\': '\\', 'n': '\n', ',': ',', '*': '*'}


def _unescape(raw, line_no, allowed):
    result = []
    i = 0
    n = len(raw)
    while i < n:
        c = raw[i]
        if c == '\\':
            if i + 1 >= n:
                _err(line_no, "dangling '\\' escape at end of value")
            nc = raw[i + 1]
            if nc not in allowed:
                _err(line_no, f"invalid escape sequence '\\{nc}'")
            result.append(allowed[nc])
            i += 2
            continue
        result.append(c)
        i += 1
    return ''.join(result)


def _unescape_scalar(raw, line_no):
    return _unescape(raw, line_no, _SCALAR_ESCAPES)


def _is_int_literal(s):
    if s == '':
        return False
    i = 0
    if s[0] == '-':
        i = 1
    if i >= len(s):
        return False
    for ch in s[i:]:
        if ch < '0' or ch > '9':
            return False
    return True


def _is_float_literal(s):
    if s == '':
        return False
    i = 0
    n = len(s)
    if s[i] == '-':
        i += 1
    if i >= n:
        return False
    seen_digit = False
    seen_dot = False
    while i < n:
        ch = s[i]
        if '0' <= ch <= '9':
            seen_digit = True
            i += 1
            continue
        if ch == '.' and not seen_dot:
            seen_dot = True
            i += 1
            continue
        return False
    return seen_digit


def _parse_header(line):
    line_no = 1
    parts = _split_top_level(line, '|')
    if not parts or parts[0] != 'cls':
        _err(line_no, "header must start with 'cls'")

    allowed_keys = {'d', 'l', 'model', 'k', 'n'}
    fields = {}
    for part in parts[1:]:
        if '=' not in part:
            _err(line_no, f"malformed header field '{part}'")
        key, _, value = part.partition('=')
        if key not in allowed_keys:
            _err(line_no, f"unknown header field '{key}'")
        if key in fields:
            _err(line_no, f"duplicate header field '{key}'")
        fields[key] = value

    if 'n' not in fields:
        _err(line_no, "missing mandatory header field 'n'")

    n_raw = fields['n']
    if not _is_int_literal(n_raw):
        _err(line_no, "header field 'n' must be an integer")
    n_val = int(n_raw)

    def opt_str(key):
        if key not in fields or fields[key] == '':
            return None
        return _unescape_scalar(fields[key], line_no)

    def opt_int(key):
        if key not in fields or fields[key] == '':
            return None
        v = fields[key]
        if not _is_int_literal(v):
            _err(line_no, f"header field '{key}' must be an integer")
        return int(v)

    header = {
        'd': opt_str('d'),
        'l': opt_str('l'),
        'model': opt_str('model'),
        'k': opt_int('k'),
        'n': n_val,
    }
    return header


def _parse_list(raw, line_no):
    """Parse a ','-separated list of string elements where any element may
    carry a trailing unescaped '*' marker (selected). Elements may be
    CSV-style double-quoted to embed a raw ',' (the '*' marker, if present,
    goes right after the closing quote). Returns (items, marked_indices)."""
    items = []
    marked = []
    i = 0
    n = len(raw)
    idx = 0
    while True:
        value_chars = []
        if i < n and raw[i] == '"':
            i += 1
            closed = False
            while i < n:
                c = raw[i]
                if c == '\\' and i + 1 < n:
                    nc = raw[i + 1]
                    if nc not in _LIST_ESCAPES:
                        _err(line_no, f"invalid escape sequence '\\{nc}' in list element")
                    value_chars.append(_LIST_ESCAPES[nc])
                    i += 2
                    continue
                if c == '"':
                    i += 1
                    closed = True
                    break
                value_chars.append(c)
                i += 1
            if not closed:
                _err(line_no, "unterminated quoted list element")
        else:
            while i < n:
                c = raw[i]
                if c == '\\' and i + 1 < n:
                    nc = raw[i + 1]
                    if nc not in _LIST_ESCAPES:
                        _err(line_no, f"invalid escape sequence '\\{nc}' in list element")
                    value_chars.append(_LIST_ESCAPES[nc])
                    i += 2
                    continue
                if c == ',' or c == '*':
                    break
                value_chars.append(c)
                i += 1

        marker = False
        if i < n and raw[i] == '*':
            marker = True
            i += 1

        items.append(''.join(value_chars))
        if marker:
            marked.append(idx)
        idx += 1

        if i < n:
            if raw[i] == ',':
                i += 1
                continue
            _err(line_no, f"unexpected character '{raw[i]}' in list")
        break

    return items, marked


def _parse_record(line, line_no):
    parts = _split_top_level(line, '|')
    if len(parts) != 5:
        _err(line_no, f"expected 5 fields, found {len(parts)}")

    id_raw, text_raw, labels_raw, conf_raw, rationale_raw = parts

    if id_raw == '':
        _err(line_no, "field 'id' is mandatory")
    rec_id = _unescape_scalar(id_raw, line_no)

    if text_raw == '':
        _err(line_no, "field 'text' is mandatory")
    text = _unescape_scalar(text_raw, line_no)

    if labels_raw == '':
        _err(line_no, "field 'labels' is mandatory")
    items, marked = _parse_list(labels_raw, line_no)
    if len(marked) < 1:
        _err(line_no, "field 'labels' must have at least one selected (*) element")
    labels = {'items': items, 'correct': marked}

    if conf_raw == '':
        _err(line_no, "field 'conf' is mandatory")
    if not _is_float_literal(conf_raw):
        _err(line_no, "field 'conf' must be a number")
    conf = float(conf_raw)
    if conf < 0.0 or conf > 1.0:
        _err(line_no, "field 'conf' must be within [0, 1]")

    if rationale_raw == '':
        rationale = None
    else:
        rationale = _unescape_scalar(rationale_raw, line_no)

    return {
        'id': rec_id,
        'text': text,
        'labels': labels,
        'conf': conf,
        'rationale': rationale,
    }
