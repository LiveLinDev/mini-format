"""Deterministic parser for the .mini format family 'log' v1
(service events / incident records).

No third-party or external imports are used; validation of digits and
timestamps is done manually below.
"""

_LEVELS = {"DEBUG", "INFO", "WARN", "ERROR", "CRITICAL"}
_ESCAPE_MAP = {'\\': '\\', '|': '|', 'n': '\n', ',': ',', '*': '*'}
_HEADER_KEYS = {'d', 'env', 'host', 'n'}
_MAX_TAGS = 10


def _err(line_no, msg):
    raise ValueError("line {}: {}".format(line_no, msg))


def _is_digits(s):
    if s == '':
        return False
    for ch in s:
        if ch < '0' or ch > '9':
            return False
    return True


def _is_valid_ts(s):
    # Expected shape: YYYY-MM-DDTHH:MM:SS[.fraction]Z
    if len(s) < 20:
        return False
    if s[4] != '-' or s[7] != '-' or s[10] != 'T' or s[13] != ':' or s[16] != ':':
        return False
    if s[-1] != 'Z':
        return False
    date_digits = s[0:4] + s[5:7] + s[8:10] + s[11:13] + s[14:16] + s[17:19]
    if len(date_digits) != 14 or not _is_digits(date_digits):
        return False
    rest = s[19:-1]
    if rest == '':
        return True
    if rest[0] != '.':
        return False
    return _is_digits(rest[1:])


def _unescape(raw, line_no):
    out = []
    i = 0
    n = len(raw)
    while i < n:
        c = raw[i]
        if c == '\\':
            if i + 1 >= n:
                _err(line_no, "dangling escape '\\' at end of value")
            nc = raw[i + 1]
            if nc not in _ESCAPE_MAP:
                _err(line_no, "invalid escape sequence '\\{}'".format(nc))
            out.append(_ESCAPE_MAP[nc])
            i += 2
            continue
        out.append(c)
        i += 1
    return ''.join(out)


def _split_top(line, sep):
    fields = []
    cur = []
    i = 0
    n = len(line)
    while i < n:
        c = line[i]
        if c == '\\' and i + 1 < n:
            cur.append(c)
            cur.append(line[i + 1])
            i += 2
            continue
        if c == sep:
            fields.append(''.join(cur))
            cur = []
            i += 1
            continue
        cur.append(c)
        i += 1
    fields.append(''.join(cur))
    return fields


def _strip_trailing_star(raw):
    """Return (value, is_marked). is_marked is True only if the string
    ends with an UNescaped '*' (an even number of backslashes, possibly
    zero, immediately precede it)."""
    if not raw.endswith('*'):
        return raw, False
    k = len(raw) - 2
    backslashes = 0
    while k >= 0 and raw[k] == '\\':
        backslashes += 1
        k -= 1
    if backslashes % 2 == 1:
        return raw, False
    return raw[:-1], True


def _find_unescaped_quote_end(token):
    i = 1
    n = len(token)
    while i < n:
        c = token[i]
        if c == '\\' and i + 1 < n:
            i += 2
            continue
        if c == '"':
            return i
        i += 1
    return -1


def _split_list_raw(raw, line_no, field_name):
    tokens = []
    buf = []
    i = 0
    n = len(raw)
    in_quotes = False
    while i < n:
        c = raw[i]
        if c == '\\' and i + 1 < n:
            buf.append(c)
            buf.append(raw[i + 1])
            i += 2
            continue
        if not in_quotes and c == '"' and not buf:
            in_quotes = True
            buf.append(c)
            i += 1
            continue
        if in_quotes and c == '"':
            in_quotes = False
            buf.append(c)
            i += 1
            continue
        if not in_quotes and c == ',':
            tokens.append(''.join(buf))
            buf = []
            i += 1
            continue
        buf.append(c)
        i += 1
    if in_quotes:
        _err(line_no, "unterminated quoted element in field '{}'".format(field_name))
    tokens.append(''.join(buf))
    return tokens


def _parse_list_field(raw, line_no, field_name, max_elems):
    if raw == '':
        return []
    tokens = _split_list_raw(raw, line_no, field_name)
    elements = []
    marked_index = None
    for token in tokens:
        if token.startswith('"'):
            end = _find_unescaped_quote_end(token)
            if end == -1:
                _err(line_no, "unterminated quoted element in field '{}'".format(field_name))
            inner_raw = token[1:end]
            rest = token[end + 1:]
            is_marked = False
            if rest == '*':
                is_marked = True
            elif rest != '':
                _err(line_no, "unexpected content '{}' after closing quote in field '{}'".format(rest, field_name))
            value = _unescape(inner_raw, line_no)
        else:
            value_raw, is_marked = _strip_trailing_star(token)
            value = _unescape(value_raw, line_no)
        if is_marked:
            if marked_index is not None:
                _err(line_no, "more than one marked element in field '{}'".format(field_name))
            marked_index = len(elements)
        elements.append(value)
    if len(elements) > max_elems:
        _err(line_no, "field '{}' has {} elements, max {}".format(field_name, len(elements), max_elems))
    if marked_index is not None:
        return {'items': elements, 'correct': marked_index}
    return elements


def _parse_header(line, line_no):
    tokens = _split_top(line, '|')
    if not tokens or tokens[0] != 'log':
        _err(line_no, "header must start with 'log'")
    fields = {}
    for tok in tokens[1:]:
        if '=' not in tok:
            _err(line_no, "malformed header field '{}'".format(tok))
        key, _, value = tok.partition('=')
        if key in fields:
            _err(line_no, "duplicate header field '{}'".format(key))
        fields[key] = value
    for key in fields:
        if key not in _HEADER_KEYS:
            _err(line_no, "unknown header field '{}'".format(key))
    if 'n' not in fields or fields['n'] == '':
        _err(line_no, "header field 'n' is mandatory")
    if not _is_digits(fields['n']):
        _err(line_no, "header field 'n' is not a valid integer: '{}'".format(fields['n']))
    n = int(fields['n'])
    header = {'n': n}
    for key in ('d', 'env', 'host'):
        val = fields.get(key, '')
        header[key] = _unescape(val, line_no) if val != '' else None
    return header, n


def _parse_record(line, line_no):
    fields = _split_top(line, '|')
    if len(fields) != 8:
        _err(line_no, "expected 8 fields, got {}".format(len(fields)))
    raw_ts, raw_level, raw_service, raw_code, raw_message, raw_tags, raw_trace, raw_duration = fields

    if raw_ts == '':
        _err(line_no, "field 'ts' is mandatory")
    ts = _unescape(raw_ts, line_no)
    if not _is_valid_ts(ts):
        _err(line_no, "field 'ts' is not a valid ISO-8601 UTC timestamp: '{}'".format(ts))

    if raw_level == '':
        _err(line_no, "field 'level' is mandatory")
    level = _unescape(raw_level, line_no)
    if level not in _LEVELS:
        _err(line_no, "field 'level' has invalid value '{}'".format(level))

    if raw_service == '':
        _err(line_no, "field 'service' is mandatory")
    service = _unescape(raw_service, line_no)

    if raw_code == '':
        _err(line_no, "field 'code' is mandatory")
    code = _unescape(raw_code, line_no)

    if raw_message == '':
        _err(line_no, "field 'message' is mandatory")
    message = _unescape(raw_message, line_no)

    tags = _parse_list_field(raw_tags, line_no, 'tags', _MAX_TAGS)

    trace = None if raw_trace == '' else _unescape(raw_trace, line_no)

    duration_ms = None
    if raw_duration != '':
        if not _is_digits(raw_duration):
            _err(line_no, "field 'duration_ms' is not a valid non-negative integer: '{}'".format(raw_duration))
        duration_ms = int(raw_duration)

    return {
        'ts': ts,
        'level': level,
        'service': service,
        'code': code,
        'message': message,
        'tags': tags,
        'trace': trace,
        'duration_ms': duration_ms,
    }


def parse(text: str) -> dict:
    if text is None:
        _err(1, "empty document")

    lines = text.split('\n')
    if lines and lines[-1] == '':
        lines = lines[:-1]
    if not lines:
        _err(1, "missing header line")

    header_line = lines[0]
    if header_line.endswith('\r'):
        header_line = header_line[:-1]
    header, n = _parse_header(header_line, 1)

    record_lines = lines[1:]
    cleaned_record_lines = []
    for idx, raw_line in enumerate(record_lines, start=2):
        if raw_line.endswith('\r'):
            raw_line = raw_line[:-1]
        if raw_line == '':
            _err(idx, "blank lines are not allowed")
        cleaned_record_lines.append(raw_line)

    if len(cleaned_record_lines) != n:
        _err(1, "header n={} does not match actual record count {}".format(n, len(cleaned_record_lines)))

    events = []
    for idx, raw_line in enumerate(cleaned_record_lines, start=2):
        events.append(_parse_record(raw_line, idx))

    return {'prefix': 'log', 'header': header, 'events': events}
