PRIORITIES = {'low', 'medium', 'high', 'critical'}
TYPES = {'functional', 'integration', 'performance', 'security', 'usability', 'regression'}
HEADER_KEYS = {'d', 'l', 't', 'proj', 'n'}
FIELD_NAMES = ['id', 'module', 'title', 'precondition', 'steps',
               'expected', 'priority', 'type', 'automated']


def _is_escaped_at(s, idx):
    # True if s[idx] is "escaped", i.e. preceded by an odd number of
    # consecutive backslashes immediately before it.
    count = 0
    j = idx - 1
    while j >= 0 and s[j] == '\\':
        count += 1
        j -= 1
    return count % 2 == 1


def _unescape(raw, line_no):
    out = []
    i = 0
    n = len(raw)
    while i < n:
        c = raw[i]
        if c == '\\':
            if i + 1 >= n:
                raise ValueError(
                    "line %d: dangling escape character '\\' at end of value" % line_no)
            nxt = raw[i + 1]
            if nxt == '|':
                out.append('|')
            elif nxt == '\\':
                out.append('\\')
            elif nxt == 'n':
                out.append('\n')
            elif nxt == ',':
                out.append(',')
            elif nxt == '*':
                out.append('*')
            else:
                raise ValueError(
                    "line %d: unknown escape sequence '\\%s'" % (line_no, nxt))
            i += 2
        else:
            out.append(c)
            i += 1
    return ''.join(out)


def _split_unescaped(raw, delim, line_no):
    # Split raw text on delim, honouring backslash-escaping so that an
    # escaped delimiter (e.g. '\|') is not treated as a boundary. The
    # returned tokens keep their escape sequences undecoded.
    tokens = []
    buf = []
    i = 0
    n = len(raw)
    while i < n:
        c = raw[i]
        if c == '\\':
            if i + 1 >= n:
                raise ValueError(
                    "line %d: dangling escape character '\\' at end of line" % line_no)
            buf.append(c)
            buf.append(raw[i + 1])
            i += 2
        elif c == delim:
            tokens.append(''.join(buf))
            buf = []
            i += 1
        else:
            buf.append(c)
            i += 1
    tokens.append(''.join(buf))
    return tokens


def _split_list_raw(raw, line_no):
    # Split a list field's raw text on ',' honouring backslash-escaping
    # and CSV-style double-quoting (a quote only opens quoting when it
    # is the first character of a not-yet-started element). Tokens keep
    # their quotes/escape sequences undecoded for later interpretation.
    tokens = []
    buf = []
    i = 0
    n = len(raw)
    in_quotes = False
    started = False
    while i < n:
        c = raw[i]
        if c == '\\':
            if i + 1 >= n:
                raise ValueError(
                    "line %d: dangling escape character '\\' at end of value" % line_no)
            buf.append(c)
            buf.append(raw[i + 1])
            i += 2
            started = True
            continue
        if c == '"':
            if not started:
                in_quotes = True
                started = True
                buf.append(c)
                i += 1
                continue
            elif in_quotes:
                buf.append(c)
                in_quotes = False
                i += 1
                continue
            else:
                buf.append(c)
                i += 1
                continue
        if c == ',' and not in_quotes:
            tokens.append(''.join(buf))
            buf = []
            started = False
            i += 1
            continue
        buf.append(c)
        started = True
        i += 1
    if in_quotes:
        raise ValueError("line %d: unterminated quoted list element" % line_no)
    tokens.append(''.join(buf))
    return tokens


def _decode_list_element(tok, line_no):
    # Returns (value, is_marker).
    if tok.startswith('"'):
        j = 1
        closing = -1
        while j < len(tok):
            if tok[j] == '\\':
                j += 2
                continue
            if tok[j] == '"':
                closing = j
                break
            j += 1
        if closing == -1:
            raise ValueError("line %d: unterminated quoted list element" % line_no)
        inner = tok[1:closing]
        rest = tok[closing + 1:]
        if rest == '*':
            marker = True
        elif rest == '':
            marker = False
        else:
            raise ValueError(
                "line %d: unexpected characters %r after quoted list element" % (line_no, rest))
        value = _unescape(inner, line_no)
        return value, marker
    else:
        if len(tok) > 0 and tok[-1] == '*' and not _is_escaped_at(tok, len(tok) - 1):
            marker = True
            core = tok[:-1]
        else:
            marker = False
            core = tok
        value = _unescape(core, line_no)
        return value, marker


def _parse_list_field(raw, line_no):
    raw_tokens = _split_list_raw(raw, line_no)
    items = []
    marked_index = None
    for idx, tok in enumerate(raw_tokens):
        value, is_marker = _decode_list_element(tok, line_no)
        items.append(value)
        if is_marker:
            if marked_index is not None:
                raise ValueError(
                    "line %d: more than one '*' marker found in list" % line_no)
            marked_index = idx
    if marked_index is not None:
        return {'items': items, 'correct': marked_index}
    return items


def _parse_header(line):
    line_no = 1
    if line == '':
        raise ValueError("line %d: missing header" % line_no)
    raw_fields = _split_unescaped(line, '|', line_no)
    prefix = _unescape(raw_fields[0], line_no)
    if prefix != 'tc':
        raise ValueError(
            "line %d: expected family prefix 'tc', found %r" % (line_no, prefix))
    values = {'d': None, 'l': None, 't': None, 'proj': None, 'n': None}
    seen = set()
    for tok in raw_fields[1:]:
        if '=' not in tok:
            raise ValueError(
                "line %d: malformed header field %r, expected key=value" % (line_no, tok))
        raw_key, _, raw_value = tok.partition('=')
        key = _unescape(raw_key, line_no)
        if key not in HEADER_KEYS:
            raise ValueError("line %d: unknown header key %r" % (line_no, key))
        if key in seen:
            raise ValueError("line %d: duplicate header key %r" % (line_no, key))
        seen.add(key)
        value = _unescape(raw_value, line_no)
        if key == 'n':
            if value == '' or not value.isdigit():
                raise ValueError(
                    "line %d: header field 'n' must be a non-negative integer, found %r"
                    % (line_no, value))
            values['n'] = int(value)
        else:
            values[key] = value if value != '' else None
    if values['n'] is None:
        raise ValueError("line %d: header field 'n' is mandatory" % line_no)
    return prefix, values


def _parse_record(line, line_no):
    raw_fields = _split_unescaped(line, '|', line_no)
    if len(raw_fields) != 9:
        raise ValueError(
            "line %d: expected 9 fields, found %d" % (line_no, len(raw_fields)))

    rec = {}

    id_val = _unescape(raw_fields[0], line_no)
    if id_val == '':
        raise ValueError("line %d: field 'id' is mandatory and cannot be empty" % line_no)
    rec['id'] = id_val

    module_val = _unescape(raw_fields[1], line_no)
    if module_val == '':
        raise ValueError("line %d: field 'module' is mandatory and cannot be empty" % line_no)
    rec['module'] = module_val

    title_val = _unescape(raw_fields[2], line_no)
    if title_val == '':
        raise ValueError("line %d: field 'title' is mandatory and cannot be empty" % line_no)
    rec['title'] = title_val

    precond_val = _unescape(raw_fields[3], line_no)
    if precond_val == '':
        raise ValueError(
            "line %d: field 'precondition' is mandatory and cannot be empty" % line_no)
    rec['precondition'] = precond_val

    steps_raw = raw_fields[4]
    if steps_raw == '':
        raise ValueError(
            "line %d: field 'steps' must contain between 1 and 20 elements" % line_no)
    steps_val = _parse_list_field(steps_raw, line_no)
    count = len(steps_val['items']) if isinstance(steps_val, dict) else len(steps_val)
    if count < 1 or count > 20:
        raise ValueError(
            "line %d: field 'steps' must contain between 1 and 20 elements, found %d"
            % (line_no, count))
    rec['steps'] = steps_val

    expected_val = _unescape(raw_fields[5], line_no)
    if expected_val == '':
        raise ValueError("line %d: field 'expected' is mandatory and cannot be empty" % line_no)
    rec['expected'] = expected_val

    priority_val = _unescape(raw_fields[6], line_no)
    if priority_val not in PRIORITIES:
        raise ValueError(
            "line %d: field 'priority' must be one of %s, found %r"
            % (line_no, sorted(PRIORITIES), priority_val))
    rec['priority'] = priority_val

    type_val = _unescape(raw_fields[7], line_no)
    if type_val not in TYPES:
        raise ValueError(
            "line %d: field 'type' must be one of %s, found %r"
            % (line_no, sorted(TYPES), type_val))
    rec['type'] = type_val

    automated_decoded = _unescape(raw_fields[8], line_no)
    if automated_decoded == 'true':
        rec['automated'] = True
    elif automated_decoded == 'false':
        rec['automated'] = False
    else:
        raise ValueError(
            "line %d: field 'automated' must be 'true' or 'false', found %r"
            % (line_no, automated_decoded))

    return rec


def parse(text: str) -> dict:
    if not isinstance(text, str):
        raise ValueError("input must be a string")

    if text.endswith('\n'):
        text = text[:-1]
    lines = text.split('\n')

    header_line = lines[0]
    prefix, header = _parse_header(header_line)

    record_lines = lines[1:]
    n = header['n']
    if len(record_lines) != n:
        raise ValueError(
            "line 1: header declares n=%d but found %d record line(s)"
            % (n, len(record_lines)))

    cases = []
    for i, line in enumerate(record_lines):
        line_no = i + 2
        if line == '':
            raise ValueError("line %d: blank line is not allowed between records" % line_no)
        cases.append(_parse_record(line, line_no))

    return {'prefix': prefix, 'header': header, 'cases': cases}
