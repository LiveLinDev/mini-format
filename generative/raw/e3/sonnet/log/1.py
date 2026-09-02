def parse(text: str) -> dict:
    LEVELS = {"DEBUG", "INFO", "WARN", "ERROR", "CRITICAL"}
    ESCAPE_MAP = {"|": "|", "\\": "\\", "n": "\n", ",": ",", "*": "*"}

    def split_escaped(s, sep):
        parts = []
        buf = []
        i = 0
        n = len(s)
        while i < n:
            c = s[i]
            if c == "\\" and i + 1 < n:
                buf.append(s[i:i + 2])
                i += 2
                continue
            if c == sep:
                parts.append("".join(buf))
                buf = []
                i += 1
                continue
            buf.append(c)
            i += 1
        parts.append("".join(buf))
        return parts

    def unescape(s, line_no):
        out = []
        i = 0
        n = len(s)
        while i < n:
            c = s[i]
            if c == "\\":
                if i + 1 >= n:
                    raise ValueError(
                        "line {}: dangling escape character at end of value".format(line_no)
                    )
                nc = s[i + 1]
                if nc not in ESCAPE_MAP:
                    raise ValueError(
                        "line {}: unknown escape sequence '\\{}'".format(line_no, nc)
                    )
                out.append(ESCAPE_MAP[nc])
                i += 2
            else:
                out.append(c)
                i += 1
        return "".join(out)

    def parse_list_field(raw, line_no):
        if raw == "":
            return []

        elements = []
        i = 0
        n = len(raw)
        while True:
            if i < n and raw[i] == '"':
                j = i + 1
                buf = []
                closed = False
                while j < n:
                    c = raw[j]
                    if c == "\\" and j + 1 < n:
                        buf.append(raw[j:j + 2])
                        j += 2
                        continue
                    if c == '"':
                        closed = True
                        j += 1
                        break
                    buf.append(c)
                    j += 1
                if not closed:
                    raise ValueError(
                        "line {}: unterminated quoted list element".format(line_no)
                    )
                marker = False
                if j < n and raw[j] == "*":
                    marker = True
                    j += 1
                if j < n and raw[j] != ",":
                    raise ValueError(
                        "line {}: unexpected characters after quoted list element".format(line_no)
                    )
                value = unescape("".join(buf), line_no)
                elements.append((value, marker))
                if j < n:
                    i = j + 1
                    continue
                break
            else:
                tokens = []
                j = i
                while j < n:
                    c = raw[j]
                    if c == "\\" and j + 1 < n:
                        tokens.append(raw[j:j + 2])
                        j += 2
                        continue
                    if c == ",":
                        break
                    tokens.append(c)
                    j += 1
                marker = False
                if tokens and tokens[-1] == "*":
                    marker = True
                    tokens = tokens[:-1]
                value = unescape("".join(tokens), line_no)
                elements.append((value, marker))
                if j < n:
                    i = j + 1
                    continue
                break

        if len(elements) > 10:
            raise ValueError(
                "line {}: list field has more than 10 elements".format(line_no)
            )

        marked_indices = [idx for idx, (_, m) in enumerate(elements) if m]
        if len(marked_indices) > 1:
            raise ValueError(
                "line {}: more than one marked ('*') list element".format(line_no)
            )
        values = [v for v, _ in elements]
        if len(marked_indices) == 1:
            return {"items": values, "correct": marked_indices[0]}
        return values

    if text == "":
        raise ValueError("line 1: empty document, missing header")

    lines = text.split("\n")
    if lines and lines[-1] == "":
        lines.pop()
    if not lines:
        raise ValueError("line 1: empty document, missing header")

    header_line = lines[0]
    header_tokens = split_escaped(header_line, "|")
    if not header_tokens or header_tokens[0] != "log":
        raise ValueError("line 1: invalid header, expected 'log' prefix")

    prefix = header_tokens[0]
    header_fields = {"d": None, "env": None, "host": None, "n": None}
    seen_keys = set()
    for tok in header_tokens[1:]:
        if "=" not in tok:
            raise ValueError("line 1: malformed header field '{}'".format(tok))
        key, _, value = tok.partition("=")
        if key not in ("d", "env", "host", "n"):
            raise ValueError("line 1: unknown header key '{}'".format(key))
        if key in seen_keys:
            raise ValueError("line 1: duplicate header key '{}'".format(key))
        seen_keys.add(key)
        if key == "n":
            try:
                n_val = int(value)
            except ValueError:
                raise ValueError("line 1: header field 'n' is not a valid integer")
            header_fields["n"] = n_val
        else:
            header_fields[key] = unescape(value, 1)

    if header_fields["n"] is None:
        raise ValueError("line 1: missing mandatory header field 'n'")

    record_lines = lines[1:]
    n_expected = header_fields["n"]
    if len(record_lines) != n_expected:
        raise ValueError(
            "line 1: header declares n={} but document has {} record line(s)".format(
                n_expected, len(record_lines)
            )
        )

    events = []
    for offset, line in enumerate(record_lines):
        line_no = offset + 2
        if line == "":
            raise ValueError("line {}: blank line is not allowed".format(line_no))

        fields = split_escaped(line, "|")
        if len(fields) != 8:
            raise ValueError(
                "line {}: expected 8 fields, found {}".format(line_no, len(fields))
            )

        (raw_ts, raw_level, raw_service, raw_code, raw_message,
         raw_tags, raw_trace, raw_duration) = fields

        if raw_ts == "":
            raise ValueError("line {}: field 'ts' is mandatory".format(line_no))
        ts = unescape(raw_ts, line_no)

        if raw_level == "":
            raise ValueError("line {}: field 'level' is mandatory".format(line_no))
        level = unescape(raw_level, line_no)
        if level not in LEVELS:
            raise ValueError("line {}: invalid level '{}'".format(line_no, level))

        if raw_service == "":
            raise ValueError("line {}: field 'service' is mandatory".format(line_no))
        service = unescape(raw_service, line_no)

        if raw_code == "":
            raise ValueError("line {}: field 'code' is mandatory".format(line_no))
        code = unescape(raw_code, line_no)

        if raw_message == "":
            raise ValueError("line {}: field 'message' is mandatory".format(line_no))
        message = unescape(raw_message, line_no)

        tags = parse_list_field(raw_tags, line_no)

        if raw_trace == "":
            trace = None
        else:
            trace = unescape(raw_trace, line_no)

        if raw_duration == "":
            duration_ms = None
        else:
            duration_text = unescape(raw_duration, line_no)
            try:
                duration_ms = int(duration_text)
            except ValueError:
                raise ValueError(
                    "line {}: field 'duration_ms' is not a valid integer".format(line_no)
                )
            if duration_ms < 0:
                raise ValueError(
                    "line {}: field 'duration_ms' must be >= 0".format(line_no)
                )

        events.append({
            "ts": ts,
            "level": level,
            "service": service,
            "code": code,
            "message": message,
            "tags": tags,
            "trace": trace,
            "duration_ms": duration_ms,
        })

    return {
        "prefix": prefix,
        "header": header_fields,
        "events": events,
    }
