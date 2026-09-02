_ESCAPES = {'|': '|', '\\': '\\', 'n': '\n', ',': ',', '*': '*'}

_BLOOM_LEVELS = {'L1', 'L2', 'L3', 'L4', 'L5', 'L6'}

_KNOWN_HEADER_KEYS = {'n', 'm', 'd', 'l', 't', 'bd', 'cat', 'k'}
_STR_HEADER_KEYS = {'m', 'd', 'l', 't'}


def _unescape(raw, line_no, context):
    out = []
    i = 0
    n = len(raw)
    while i < n:
        ch = raw[i]
        if ch == '\\':
            if i + 1 >= n:
                raise ValueError(
                    "line %d: dangling escape character in %s" % (line_no, context)
                )
            nxt = raw[i + 1]
            if nxt not in _ESCAPES:
                raise ValueError(
                    "line %d: unknown escape sequence '\\%s' in %s"
                    % (line_no, nxt, context)
                )
            out.append(_ESCAPES[nxt])
            i += 2
        else:
            out.append(ch)
            i += 1
    return ''.join(out)


def _split_escaped(s, sep):
    parts = []
    cur = []
    i = 0
    n = len(s)
    while i < n:
        ch = s[i]
        if ch == '\\' and i + 1 < n:
            cur.append(ch)
            cur.append(s[i + 1])
            i += 2
            continue
        if ch == sep:
            parts.append(''.join(cur))
            cur = []
            i += 1
            continue
        cur.append(ch)
        i += 1
    parts.append(''.join(cur))
    return parts


def _split_list_raw(s, line_no, context):
    """Split a comma-separated list of raw (still-escaped) elements,
    honoring CSV-style double-quoted elements (which may contain a
    literal comma) and backslash-escaped separators."""
    elements = []
    cur = []
    i = 0
    n = len(s)
    at_start = True
    while i < n:
        ch = s[i]
        if at_start and ch == '"':
            j = i + 1
            buf = []
            closed = False
            while j < n:
                c2 = s[j]
                if c2 == '\\' and j + 1 < n:
                    buf.append(c2)
                    buf.append(s[j + 1])
                    j += 2
                    continue
                if c2 == '"':
                    closed = True
                    j += 1
                    break
                buf.append(c2)
                j += 1
            if not closed:
                raise ValueError(
                    "line %d: unterminated quoted element in %s" % (line_no, context)
                )
            elem_raw = '"' + ''.join(buf) + '"'
            if j < n and s[j] == '*':
                elem_raw += '*'
                j += 1
            if j < n:
                if s[j] != ',':
                    raise ValueError(
                        "line %d: unexpected character after quoted element in %s"
                        % (line_no, context)
                    )
                j += 1
            elements.append(elem_raw)
            i = j
            cur = []
            at_start = True
            continue
        if ch == '\\' and i + 1 < n:
            cur.append(ch)
            cur.append(s[i + 1])
            i += 2
            at_start = False
            continue
        if ch == ',':
            elements.append(''.join(cur))
            cur = []
            i += 1
            at_start = True
            continue
        cur.append(ch)
        i += 1
        at_start = False
    elements.append(''.join(cur))
    return elements


def _parse_option_element(raw, line_no):
    if raw.startswith('"'):
        i = 1
        n = len(raw)
        buf = []
        closed = False
        while i < n:
            c = raw[i]
            if c == '\\' and i + 1 < n:
                buf.append(c)
                buf.append(raw[i + 1])
                i += 2
                continue
            if c == '"':
                closed = True
                i += 1
                break
            buf.append(c)
            i += 1
        if not closed:
            raise ValueError("line %d: unterminated quoted option" % line_no)
        content_raw = ''.join(buf)
        rest = raw[i:]
        if rest == '*':
            selected = True
        elif rest == '':
            selected = False
        else:
            raise ValueError(
                "line %d: malformed option element '%s'" % (line_no, raw)
            )
        content = _unescape(content_raw, line_no, "field 'options'")
        return content, selected
    else:
        selected = False
        body = raw
        if raw.endswith('*'):
            k = len(raw) - 1
            j = k - 1
            nback = 0
            while j >= 0 and raw[j] == '\\':
                nback += 1
                j -= 1
            if nback % 2 == 0:
                selected = True
                body = raw[:-1]
        content = _unescape(body, line_no, "field 'options'")
        return content, selected


def _parse_generic_scalar(raw):
    if raw == 'true':
        return True
    if raw == 'false':
        return False
    try:
        return int(raw)
    except ValueError:
        pass
    try:
        return float(raw)
    except ValueError:
        pass
    return raw


def _parse_options(raw, line_no):
    raw_elements = _split_list_raw(raw, line_no, "field 'options'")
    items = []
    correct = None
    for elem_raw in raw_elements:
        content, selected = _parse_option_element(elem_raw, line_no)
        if selected:
            if correct is not None:
                raise ValueError(
                    "line %d: more than one option marked as selected" % line_no
                )
            correct = len(items)
        items.append(content)
    if not (2 <= len(items) <= 6):
        raise ValueError(
            "line %d: field 'options' must have between 2 and 6 elements, got %d"
            % (line_no, len(items))
        )
    if correct is None:
        raise ValueError("line %d: no option marked as selected" % line_no)
    return {'items': items, 'correct': correct}


def _parse_irt(raw, line_no):
    parts = _split_escaped(raw, ',')
    if len(parts) != 3:
        raise ValueError(
            "line %d: field 'irt' must have exactly 3 components, got %d"
            % (line_no, len(parts))
        )
    result = {}
    for key, part in zip(('a', 'b', 'c'), parts):
        if part == '':
            raise ValueError("line %d: field 'irt.%s' cannot be empty" % (line_no, key))
        p = _unescape(part, line_no, "field 'irt.%s'" % key)
        try:
            result[key] = float(p)
        except ValueError:
            raise ValueError("line %d: field 'irt.%s' must be a number" % (line_no, key))
    return result


def _parse_cat_record(raw, line_no):
    parts = _split_escaped(raw, ',')
    if len(parts) != 3:
        raise ValueError(
            "line %d: field 'cat' must have exactly 3 components, got %d"
            % (line_no, len(parts))
        )
    area_raw, exposure_raw, demand_raw = parts
    if area_raw == '':
        raise ValueError("line %d: field 'cat.area' cannot be empty" % line_no)
    area = _unescape(area_raw, line_no, "field 'cat.area'")

    if exposure_raw == '':
        raise ValueError("line %d: field 'cat.exposure_cap' cannot be empty" % line_no)
    exposure_str = _unescape(exposure_raw, line_no, "field 'cat.exposure_cap'")
    try:
        exposure_cap = float(exposure_str)
    except ValueError:
        raise ValueError(
            "line %d: field 'cat.exposure_cap' must be a number" % line_no
        )

    if demand_raw == '':
        raise ValueError("line %d: field 'cat.demand' cannot be empty" % line_no)
    demand = _unescape(demand_raw, line_no, "field 'cat.demand'")

    return {'area': area, 'exposure_cap': exposure_cap, 'demand': demand}


def _parse_record(line, line_no):
    fields = _split_escaped(line, '|')
    if len(fields) != 8:
        raise ValueError(
            "line %d: expected 8 fields, got %d" % (line_no, len(fields))
        )

    (raw_id, raw_bloom, raw_topic, raw_statement,
     raw_options, raw_irt, raw_difficulty, raw_cat) = fields

    if raw_id == '':
        raise ValueError("line %d: field 'id' is mandatory and cannot be empty" % line_no)
    item_id = _unescape(raw_id, line_no, "field 'id'")

    if raw_bloom == '':
        raise ValueError("line %d: field 'bloom' is mandatory and cannot be empty" % line_no)
    bloom = _unescape(raw_bloom, line_no, "field 'bloom'")
    if bloom not in _BLOOM_LEVELS:
        raise ValueError("line %d: invalid bloom level '%s'" % (line_no, bloom))

    if raw_topic == '':
        raise ValueError("line %d: field 'topic' is mandatory and cannot be empty" % line_no)
    topic = _unescape(raw_topic, line_no, "field 'topic'")

    if raw_statement == '':
        raise ValueError(
            "line %d: field 'statement' is mandatory and cannot be empty" % line_no
        )
    statement = _unescape(raw_statement, line_no, "field 'statement'")

    if raw_options == '':
        raise ValueError(
            "line %d: field 'options' is mandatory and cannot be empty" % line_no
        )
    options = _parse_options(raw_options, line_no)

    if raw_irt == '':
        raise ValueError("line %d: field 'irt' is mandatory and cannot be empty" % line_no)
    irt = _parse_irt(raw_irt, line_no)

    if raw_difficulty == '':
        raise ValueError(
            "line %d: field 'difficulty' is mandatory and cannot be empty" % line_no
        )
    difficulty_str = _unescape(raw_difficulty, line_no, "field 'difficulty'")
    try:
        difficulty = int(difficulty_str)
    except ValueError:
        raise ValueError("line %d: field 'difficulty' must be an integer" % line_no)
    if not (1 <= difficulty <= 5):
        raise ValueError(
            "line %d: field 'difficulty' must be in range [1..5]" % line_no
        )

    if raw_cat == '':
        raise ValueError("line %d: field 'cat' is mandatory and cannot be empty" % line_no)
    cat = _parse_cat_record(raw_cat, line_no)

    return {
        'id': item_id,
        'bloom': bloom,
        'topic': topic,
        'statement': statement,
        'options': options,
        'irt': irt,
        'difficulty': difficulty,
        'cat': cat,
    }


def _parse_header(header_line):
    tokens = _split_escaped(header_line, '|')
    if not tokens or tokens[0] != 'a':
        raise ValueError("line 1: invalid prefix, expected 'a'")

    header = {
        'n': None, 'm': None, 'd': None, 'l': None, 't': None,
        'bd': None, 'cat': None, 'k': None,
    }
    seen = set()

    for tok in tokens[1:]:
        if '=' not in tok:
            raise ValueError("line 1: malformed header field '%s'" % tok)
        key, value = tok.split('=', 1)
        if key not in _KNOWN_HEADER_KEYS:
            raise ValueError("line 1: unknown header field '%s'" % key)
        if key in seen:
            raise ValueError("line 1: duplicate header field '%s'" % key)
        seen.add(key)

        if key == 'n':
            if value == '':
                raise ValueError("line 1: field 'n' is mandatory and cannot be empty")
            try:
                header['n'] = int(value)
            except ValueError:
                raise ValueError("line 1: field 'n' must be an integer")
        elif key == 'k':
            if value == '':
                header['k'] = None
            else:
                try:
                    header['k'] = int(value)
                except ValueError:
                    raise ValueError("line 1: field 'k' must be an integer")
        elif key in _STR_HEADER_KEYS:
            header[key] = None if value == '' else _unescape(
                value, 1, "header field '%s'" % key
            )
        else:  # 'bd' or 'cat'
            if value == '':
                header[key] = None
            else:
                raw_parts = _split_escaped(value, ',')
                parsed = []
                for p in raw_parts:
                    up = _unescape(p, 1, "header field '%s'" % key)
                    parsed.append(_parse_generic_scalar(up))
                header[key] = parsed

    if 'n' not in seen:
        raise ValueError("line 1: missing mandatory field 'n'")

    return header


def parse(text: str) -> dict:
    if text is None:
        raise ValueError("line 1: empty document")

    lines = text.split('\n')
    if lines and lines[-1] == '':
        lines = lines[:-1]
    if not lines:
        raise ValueError("line 1: empty document")

    for idx, ln in enumerate(lines, start=1):
        if ln == '':
            raise ValueError("line %d: blank line not allowed" % idx)

    header_line = lines[0]
    record_lines = lines[1:]

    header = _parse_header(header_line)

    if header['n'] != len(record_lines):
        raise ValueError(
            "line 1: n=%s does not match number of record lines (%d)"
            % (header['n'], len(record_lines))
        )

    items = []
    for offset, rec_line in enumerate(record_lines):
        line_no = offset + 2
        items.append(_parse_record(rec_line, line_no))

    return {'prefix': 'a', 'header': header, 'items': items}
