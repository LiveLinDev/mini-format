PRIORITIES = {'low', 'medium', 'high', 'critical'}
TYPES = {'functional', 'integration', 'performance', 'security', 'usability', 'regression'}
KNOWN_HEADER_KEYS = {'d', 'l', 't', 'proj', 'n'}


def _unescape(s, line_no):
    out = []
    i = 0
    n = len(s)
    while i < n:
        c = s[i]
        if c == '\\':
            if i + 1 >= n:
                raise ValueError(f"line {line_no}: dangling escape character '\\' at end of value")
            nc = s[i + 1]
            if nc == '\\':
                out.append('\\')
            elif nc == '|':
                out.append('|')
            elif nc == ',':
                out.append(',')
            elif nc == '*':
                out.append('*')
            elif nc == 'n':
                out.append('\n')
            else:
                raise ValueError(f"line {line_no}: unknown escape sequence '\\{nc}'")
            i += 2
            continue
        out.append(c)
        i += 1
    return ''.join(out)


def _split_top(s, delim, line_no):
    # Splits raw (still-escaped) text on unescaped occurrences of delim.
    # Escape pairs ('\' + next char) are kept intact and never treated
    # as a split point, regardless of what the escaped char is.
    parts = []
    cur = []
    i = 0
    n = len(s)
    while i < n:
        c = s[i]
        if c == '\\':
            if i + 1 >= n:
                raise ValueError(f"line {line_no}: dangling escape character '\\' at end of value")
            cur.append(s[i:i + 2])
            i += 2
            continue
        if c == delim:
            parts.append(''.join(cur))
            cur = []
            i += 1
            continue
        cur.append(c)
        i += 1
    parts.append(''.join(cur))
    return parts


def _split_steps_raw(s, line_no):
    # Splits the raw steps field into raw (still-escaped) element tokens on
    # unescaped ',' characters, treating a leading '"' as opening a
    # CSV-style quoted span in which ',' is not a separator. An optional
    # '*' marker may follow the closing quote.
    tokens = []
    i = 0
    n = len(s)
    while True:
        start = i
        if i < n and s[i] == '"':
            j = i + 1
            closed = False
            while j < n:
                cj = s[j]
                if cj == '\\':
                    if j + 1 >= n:
                        raise ValueError(f"line {line_no}: dangling escape character '\\' at end of value")
                    j += 2
                    continue
                if cj == '"':
                    j += 1
                    closed = True
                    break
                j += 1
            if not closed:
                raise ValueError(f"line {line_no}: unterminated quoted list element")
            if j < n and s[j] == '*':
                j += 1
            if j < n and s[j] != ',':
                raise ValueError(f"line {line_no}: unexpected characters after quoted list element")
            tokens.append(s[start:j])
        else:
            j = i
            while j < n:
                cj = s[j]
                if cj == '\\':
                    if j + 1 >= n:
                        raise ValueError(f"line {line_no}: dangling escape character '\\' at end of value")
                    j += 2
                    continue
                if cj == ',':
                    break
                j += 1
            tokens.append(s[start:j])
        if j >= n:
            break
        # s[j] == ','
        i = j + 1
        if i == n:
            tokens.append('')
            break
    return tokens


def _parse_list_element(tok, line_no):
    # Returns (value, is_marked) for one raw steps element.
    if tok.startswith('"'):
        n = len(tok)
        j = 1
        content_end = None
        while j < n:
            cj = tok[j]
            if cj == '\\':
                j += 2
                continue
            if cj == '"':
                content_end = j
                break
            j += 1
        if content_end is None:
            raise ValueError(f"line {line_no}: unterminated quoted list element")
        inner = tok[1:content_end]
        suffix = tok[content_end + 1:]
        if suffix not in ('', '*'):
            raise ValueError(f"line {line_no}: malformed quoted list element")
        is_marked = suffix == '*'
        value = _unescape(inner, line_no)
        return value, is_marked
    else:
        is_marked = False
        core = tok
        if tok.endswith('*'):
            bs_count = 0
            k = len(tok) - 2
            while k >= 0 and tok[k] == '\\':
                bs_count += 1
                k -= 1
            if bs_count % 2 == 0:
                is_marked = True
                core = tok[:-1]
        value = _unescape(core, line_no)
        return value, is_marked


def _parse_steps(raw, line_no):
    if raw == '':
        raise ValueError(f"line {line_no}: field 'steps' is mandatory")
    raw_tokens = _split_steps_raw(raw, line_no)
    items = []
    marked_index = None
    for idx, tok in enumerate(raw_tokens):
        value, is_marked = _parse_list_element(tok, line_no)
        if value == '':
            raise ValueError(f"line {line_no}: steps contains an empty element")
        if is_marked:
            if marked_index is not None:
                raise ValueError(f"line {line_no}: more than one marked element in steps")
            marked_index = idx
        items.append(value)
    if not (1 <= len(items) <= 20):
        raise ValueError(f"line {line_no}: steps must have between 1 and 20 elements, got {len(items)}")
    if marked_index is not None:
        return {'items': items, 'correct': marked_index}
    return items


def _require_str(raw, line_no, field_name):
    if raw == '':
        raise ValueError(f"line {line_no}: field '{field_name}' is mandatory")
    return _unescape(raw, line_no)


def _parse_header(line, line_no):
    if line == '':
        raise ValueError(f"line {line_no}: missing or empty header")
    segments = _split_top(line, '|', line_no)
    if not segments or segments[0] != 'tc':
        raise ValueError(f"line {line_no}: header must start with the 'tc' family tag")
    prefix = segments[0]
    values = {}
    for seg in segments[1:]:
        if '=' not in seg:
            raise ValueError(f"line {line_no}: malformed header field '{seg}'")
        key, _, raw_val = seg.partition('=')
        if key not in KNOWN_HEADER_KEYS:
            raise ValueError(f"line {line_no}: unknown header field '{key}'")
        if key in values:
            raise ValueError(f"line {line_no}: duplicate header field '{key}'")
        values[key] = _unescape(raw_val, line_no)

    if values.get('n', '') == '':
        raise ValueError(f"line {line_no}: header field 'n' is mandatory")
    n_str = values['n']
    if not n_str.isdigit():
        raise ValueError(f"line {line_no}: header field 'n' must be a non-negative integer")
    n = int(n_str)

    header = {
        'd': values.get('d') or None,
        'l': values.get('l') or None,
        't': values.get('t') or None,
        'proj': values.get('proj') or None,
        'n': n,
    }
    return prefix, header, n


def _parse_record(line, line_no):
    raw_fields = _split_top(line, '|', line_no)
    if len(raw_fields) != 9:
        raise ValueError(f"line {line_no}: expected 9 fields, got {len(raw_fields)}")

    rid = _require_str(raw_fields[0], line_no, 'id')
    module = _require_str(raw_fields[1], line_no, 'module')
    title = _require_str(raw_fields[2], line_no, 'title')
    precondition = _require_str(raw_fields[3], line_no, 'precondition')
    steps = _parse_steps(raw_fields[4], line_no)
    expected = _require_str(raw_fields[5], line_no, 'expected')

    priority_raw = raw_fields[6]
    if priority_raw == '':
        raise ValueError(f"line {line_no}: field 'priority' is mandatory")
    priority = _unescape(priority_raw, line_no)
    if priority not in PRIORITIES:
        raise ValueError(f"line {line_no}: invalid priority '{priority}'")

    type_raw = raw_fields[7]
    if type_raw == '':
        raise ValueError(f"line {line_no}: field 'type' is mandatory")
    ttype = _unescape(type_raw, line_no)
    if ttype not in TYPES:
        raise ValueError(f"line {line_no}: invalid type '{ttype}'")

    automated_raw = raw_fields[8]
    if automated_raw == 'true':
        automated = True
    elif automated_raw == 'false':
        automated = False
    else:
        raise ValueError(f"line {line_no}: invalid boolean for 'automated': '{automated_raw}'")

    return {
        'id': rid,
        'module': module,
        'title': title,
        'precondition': precondition,
        'steps': steps,
        'expected': expected,
        'priority': priority,
        'type': ttype,
        'automated': automated,
    }


def parse(text: str) -> dict:
    if text.endswith('\n'):
        text = text[:-1]
    lines = text.split('\n')

    header_line = lines[0]
    prefix, header, n = _parse_header(header_line, 1)

    record_lines = lines[1:]
    if len(record_lines) != n:
        raise ValueError(
            f"line 1: header declares n={n} but found {len(record_lines)} record line(s)"
        )

    cases = []
    for offset, line in enumerate(record_lines):
        line_no = offset + 2
        if line == '':
            raise ValueError(f"line {line_no}: blank line is not allowed")
        cases.append(_parse_record(line, line_no))

    return {'prefix': prefix, 'header': header, 'cases': cases}
