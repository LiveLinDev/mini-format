CANONICAL_HEADER_ORDER = ('n', 'm', 'd', 'l', 't', 'bd', 'cat', 'k')
ALLOWED_HEADER_KEYS = set(CANONICAL_HEADER_ORDER)

BLOOM_LEVELS = {'L1', 'L2', 'L3', 'L4', 'L5', 'L6'}

SCALAR_ESCAPES = {'|': '|', '\\': '\\', 'n': '\n'}
LIST_ESCAPES = {'|': '|', '\\': '\\', 'n': '\n', '*': '*', ',': ','}


def split_toplevel(s, sep, line_no, respect_quotes=False):
    parts = []
    buf = []
    i = 0
    n = len(s)
    in_quotes = False
    while i < n:
        c = s[i]
        if c == '\\' and i + 1 < n:
            buf.append(s[i:i + 2])
            i += 2
            continue
        if respect_quotes and c == '"':
            in_quotes = not in_quotes
            buf.append(c)
            i += 1
            continue
        if c == sep and not (respect_quotes and in_quotes):
            parts.append(''.join(buf))
            buf = []
            i += 1
            continue
        buf.append(c)
        i += 1
    parts.append(''.join(buf))
    if respect_quotes and in_quotes:
        raise ValueError("line {}: unterminated quoted value".format(line_no))
    return parts


def tokenize_escaped(s, line_no, allowed):
    units = []
    i = 0
    n = len(s)
    while i < n:
        c = s[i]
        if c == '\\':
            if i + 1 >= n:
                raise ValueError("line {}: trailing backslash".format(line_no))
            nc = s[i + 1]
            if nc not in allowed:
                raise ValueError(
                    "line {}: invalid escape sequence '\\{}'".format(line_no, nc)
                )
            units.append((True, allowed[nc]))
            i += 2
            continue
        units.append((False, c))
        i += 1
    return units


def unescape_scalar(s, line_no):
    units = tokenize_escaped(s, line_no, SCALAR_ESCAPES)
    return ''.join(ch for _, ch in units)


def is_int_literal(s):
    if s == '':
        return False
    t = s[1:] if s[0] in '+-' else s
    return t != '' and t.isdigit()


def is_float_literal(s):
    if s == '':
        return False
    try:
        float(s)
    except ValueError:
        return False
    return ('.' in s) or ('e' in s.lower())


def coerce_scalar(s):
    if s == 'true':
        return True
    if s == 'false':
        return False
    if is_int_literal(s):
        return int(s)
    if is_float_literal(s):
        return float(s)
    return s


def parse_int(raw, line_no, field_name):
    if raw == '':
        raise ValueError("line {}: field '{}' must not be empty".format(line_no, field_name))
    t = raw[1:] if raw[0] in '+-' else raw
    if t == '' or not t.isdigit():
        raise ValueError(
            "line {}: invalid integer for '{}': '{}'".format(line_no, field_name, raw)
        )
    return int(raw)


def parse_float(raw, line_no, field_name):
    try:
        return float(raw)
    except ValueError:
        raise ValueError(
            "line {}: invalid float for '{}': '{}'".format(line_no, field_name, raw)
        )


def parse_generic_list(raw, line_no):
    parts = split_toplevel(raw, ',', line_no, respect_quotes=False)
    result = []
    for p in parts:
        val = unescape_scalar(p, line_no)
        result.append(coerce_scalar(val))
    return result


def parse_options(raw_field, line_no):
    raw_elements = split_toplevel(raw_field, ',', line_no, respect_quotes=True)
    values = []
    correct = None
    for el in raw_elements:
        if el.startswith('"'):
            close_idx = None
            i = 1
            n = len(el)
            while i < n:
                c = el[i]
                if c == '\\' and i + 1 < n:
                    i += 2
                    continue
                if c == '"':
                    close_idx = i
                    break
                i += 1
            if close_idx is None:
                raise ValueError("line {}: unterminated quote in option".format(line_no))
            content_raw = el[1:close_idx]
            remainder = el[close_idx + 1:]
            if remainder == '*':
                marked = True
            elif remainder == '':
                marked = False
            else:
                raise ValueError(
                    "line {}: unexpected characters after quoted option".format(line_no)
                )
            units = tokenize_escaped(content_raw, line_no, LIST_ESCAPES)
            value = ''.join(ch for _, ch in units)
        else:
            units = tokenize_escaped(el, line_no, LIST_ESCAPES)
            marked = bool(units) and units[-1] == (False, '*')
            if marked:
                units = units[:-1]
            value = ''.join(ch for _, ch in units)
        if marked:
            if correct is not None:
                raise ValueError("line {}: multiple selected options".format(line_no))
            correct = len(values)
        values.append(value)
    if correct is None:
        raise ValueError("line {}: no selected option marked".format(line_no))
    if not (2 <= len(values) <= 6):
        raise ValueError(
            "line {}: options must have between 2 and 6 elements, got {}".format(
                line_no, len(values)
            )
        )
    return {'items': values, 'correct': correct}


def parse_header(line, line_no):
    tokens = split_toplevel(line, '|', line_no, respect_quotes=False)
    if not tokens or tokens[0] != 'a':
        raise ValueError(
            "line {}: invalid document prefix, expected 'a'".format(line_no)
        )
    prefix = tokens[0]
    fields = {}
    seen_keys = []
    for tok in tokens[1:]:
        if '=' not in tok:
            raise ValueError(
                "line {}: malformed header field '{}'".format(line_no, tok)
            )
        key, _, raw_val = tok.partition('=')
        if key not in ALLOWED_HEADER_KEYS:
            raise ValueError("line {}: unknown header field '{}'".format(line_no, key))
        if key in fields:
            raise ValueError(
                "line {}: duplicate header field '{}'".format(line_no, key)
            )
        fields[key] = raw_val
        seen_keys.append(key)

    present_canonical = [k for k in CANONICAL_HEADER_ORDER if k in fields]
    if seen_keys != present_canonical:
        raise ValueError("line {}: header fields out of order".format(line_no))

    if 'n' not in fields:
        raise ValueError(
            "line {}: missing mandatory header field 'n'".format(line_no)
        )

    header = {}
    header['n'] = parse_int(fields['n'], line_no, 'n')

    for key in ('m', 'd', 'l', 't'):
        raw = fields.get(key)
        if raw is None or raw == '':
            header[key] = None
        else:
            header[key] = unescape_scalar(raw, line_no)

    raw_bd = fields.get('bd')
    if raw_bd is None or raw_bd == '':
        header['bd'] = None
    else:
        header['bd'] = parse_generic_list(raw_bd, line_no)

    raw_cat = fields.get('cat')
    if raw_cat is None or raw_cat == '':
        header['cat'] = None
    else:
        header['cat'] = parse_generic_list(raw_cat, line_no)

    raw_k = fields.get('k')
    if raw_k is None or raw_k == '':
        header['k'] = None
    else:
        header['k'] = parse_int(raw_k, line_no, 'k')

    return prefix, header


def parse_record(line, line_no):
    fields_raw = split_toplevel(line, '|', line_no, respect_quotes=False)
    if len(fields_raw) != 8:
        raise ValueError(
            "line {}: expected 8 fields, got {}".format(line_no, len(fields_raw))
        )
    (raw_id, raw_bloom, raw_topic, raw_statement,
     raw_options, raw_irt, raw_difficulty, raw_cat) = fields_raw

    for name, raw in (
        ('id', raw_id), ('bloom', raw_bloom), ('topic', raw_topic),
        ('statement', raw_statement), ('options', raw_options),
        ('irt', raw_irt), ('difficulty', raw_difficulty), ('cat', raw_cat),
    ):
        if raw == '':
            raise ValueError(
                "line {}: field '{}' is required and must not be empty".format(
                    line_no, name
                )
            )

    item_id = unescape_scalar(raw_id, line_no)

    bloom = unescape_scalar(raw_bloom, line_no)
    if bloom not in BLOOM_LEVELS:
        raise ValueError("line {}: invalid bloom level '{}'".format(line_no, bloom))

    topic = unescape_scalar(raw_topic, line_no)
    statement = unescape_scalar(raw_statement, line_no)

    options = parse_options(raw_options, line_no)

    irt_parts = split_toplevel(raw_irt, ',', line_no, respect_quotes=False)
    if len(irt_parts) != 3:
        raise ValueError(
            "line {}: irt must have exactly 3 components, got {}".format(
                line_no, len(irt_parts)
            )
        )
    irt = {
        'a': parse_float(unescape_scalar(irt_parts[0], line_no), line_no, 'irt.a'),
        'b': parse_float(unescape_scalar(irt_parts[1], line_no), line_no, 'irt.b'),
        'c': parse_float(unescape_scalar(irt_parts[2], line_no), line_no, 'irt.c'),
    }

    difficulty = parse_int(unescape_scalar(raw_difficulty, line_no), line_no, 'difficulty')
    if not (1 <= difficulty <= 5):
        raise ValueError(
            "line {}: difficulty out of range [1..5]: {}".format(line_no, difficulty)
        )

    cat_parts = split_toplevel(raw_cat, ',', line_no, respect_quotes=False)
    if len(cat_parts) != 3:
        raise ValueError(
            "line {}: cat must have exactly 3 components, got {}".format(
                line_no, len(cat_parts)
            )
        )
    cat = {
        'area': unescape_scalar(cat_parts[0], line_no),
        'exposure_cap': parse_float(
            unescape_scalar(cat_parts[1], line_no), line_no, 'cat.exposure_cap'
        ),
        'demand': unescape_scalar(cat_parts[2], line_no),
    }

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


def parse(text: str) -> dict:
    if text is None:
        raise ValueError("line 1: empty document")

    raw_lines = text.split('\n')
    if raw_lines and raw_lines[-1] == '':
        raw_lines = raw_lines[:-1]

    if not raw_lines:
        raise ValueError("line 1: missing header")

    header_line = raw_lines[0]
    prefix, header = parse_header(header_line, 1)

    record_lines = raw_lines[1:]

    for idx, ln in enumerate(record_lines, start=2):
        if ln == '':
            raise ValueError("line {}: blank lines are not allowed".format(idx))

    if header['n'] != len(record_lines):
        raise ValueError(
            "line 1: n={} does not match {} record line(s)".format(
                header['n'], len(record_lines)
            )
        )

    items = []
    for idx, ln in enumerate(record_lines, start=2):
        items.append(parse_record(ln, idx))

    return {'prefix': prefix, 'header': header, 'items': items}
