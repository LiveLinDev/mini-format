"""Lexical layer of .mini: escaping, field splitting and list splitting.

Structural characters
---------------------
``|``  field separator (header and records)
``<sep>`` list separator inside list/mlist/tuple fields (``,`` by default,
        configurable per contract)
``*``  selection marker, valid only as the *suffix* of a list element
``\\`` escape character
LF     record separator (a preceding CR is ignored)

Escape sequences (recognised in any position): ``\\|`` ``\\,`` ``\\*`` ``\\\\``
``\\n``.  Escaping is *idempotent-safe*: a value that over-escapes a comma in a
scalar field still decodes correctly, so generators may apply the rules
uniformly if they prefer.  Only ``|``, ``\\`` and line breaks must be escaped
everywhere; the list separator and a trailing ``*`` must be escaped only
inside list elements.
"""
from __future__ import annotations

from typing import List, Tuple

from .errors import E_ESCAPE, MiniError

FIELD_SEP = "|"
MARKER = "*"
ESCAPE = "\\"

Tok = Tuple[str, bool]  # (character, was_escaped)


def tokenize(line: str, sep: str, lineno: int, strict: bool = True) -> List[Tok]:
    """Turn a physical line into (char, escaped) pairs, resolving escapes."""
    out: List[Tok] = []
    i, n = 0, len(line)
    while i < n:
        ch = line[i]
        if ch == ESCAPE:
            if i + 1 >= n:
                raise MiniError(E_ESCAPE, lineno, "dangling backslash at end of line")
            nxt = line[i + 1]
            if nxt == "n":
                out.append(("\n", True))
            elif nxt in (FIELD_SEP, MARKER, ESCAPE, sep, ",", '"'):
                out.append((nxt, True))
            elif strict:
                raise MiniError(E_ESCAPE, lineno, f"invalid escape sequence '\\{nxt}'")
            else:  # lenient: keep both characters literally
                out.append((ESCAPE, True))
                out.append((nxt, True))
            i += 2
        else:
            out.append((ch, False))
            i += 1
    return out


def split_on(toks: List[Tok], delim: str) -> List[List[Tok]]:
    parts: List[List[Tok]] = [[]]
    for ch, esc in toks:
        if ch == delim and not esc:
            parts.append([])
        else:
            parts[-1].append((ch, esc))
    return parts


def strip_toks(toks: List[Tok]) -> List[Tok]:
    """Remove unescaped leading/trailing whitespace (not significant)."""
    a, b = 0, len(toks)
    while a < b and toks[a][0].isspace() and not toks[a][1]:
        a += 1
    while b > a and toks[b - 1][0].isspace() and not toks[b - 1][1]:
        b -= 1
    return toks[a:b]


def text_of(toks: List[Tok]) -> str:
    return "".join(ch for ch, _ in toks)


def split_fields(line: str, sep: str, lineno: int, strict: bool = True) -> List[List[Tok]]:
    return [strip_toks(p) for p in split_on(tokenize(line, sep, lineno, strict), FIELD_SEP)]


QUOTE = '"'


def split_list(toks: List[Tok], sep: str, lineno: int = 0) -> List[Tuple[str, bool]]:
    """Split a list field into (element_text, marked) pairs.

    An empty field yields an empty list.  A trailing unescaped ``*`` on an
    element sets ``marked``.  An element may be enclosed in double quotes
    (CSV style): inside the quotes the separator and ``*`` are literal and a
    doubled quote ``""`` denotes one quote; the marker may follow the closing
    quote.  Backslash escapes are always honoured (they were resolved by the
    tokenizer before this function runs).
    """
    if not toks:
        return []
    out: List[Tuple[str, bool]] = []
    i, n = 0, len(toks)
    while True:
        # skip leading unescaped whitespace
        while i < n and toks[i][0].isspace() and not toks[i][1]:
            i += 1
        if i < n and toks[i][0] == QUOTE and not toks[i][1]:
            # quoted element
            i += 1
            buf: List[str] = []
            closed = False
            while i < n:
                ch, esc = toks[i]
                if ch == QUOTE and not esc:
                    if i + 1 < n and toks[i + 1][0] == QUOTE and not toks[i + 1][1]:
                        buf.append(QUOTE)
                        i += 2
                        continue
                    closed = True
                    i += 1
                    break
                buf.append(ch)
                i += 1
            if not closed:
                raise MiniError(E_ESCAPE, lineno, "unbalanced double quote in list element")
            marked = False
            # a marker written just before the closing quote ("foo*") is accepted too
            if buf and buf[-1] == MARKER and not toks[i - 2][1]:
                marked = True
                buf.pop()
            while i < n and toks[i][0].isspace() and not toks[i][1]:
                i += 1
            if i < n and toks[i][0] == MARKER and not toks[i][1]:
                marked = True
                i += 1
            while i < n and toks[i][0].isspace() and not toks[i][1]:
                i += 1
            if i < n and not (toks[i][0] == sep and not toks[i][1]):
                raise MiniError(E_ESCAPE, lineno, "text after closing quote in list element")
            out.append(("".join(buf), marked))
        else:
            # bare element up to the next unescaped separator
            j = i
            while j < n and not (toks[j][0] == sep and not toks[j][1]):
                j += 1
            part = strip_toks(toks[i:j])
            marked = False
            if part and part[-1][0] == MARKER and not part[-1][1]:
                marked = True
                part = strip_toks(part[:-1])
            out.append((text_of(part), marked))
            i = j
        if i >= n:
            break
        i += 1  # consume separator
        if i >= n:  # trailing separator -> empty last element
            out.append(("", False))
            break
    return out


# ------------------------------------------------------------------ encoding
def escape_scalar(value: str) -> str:
    """Escape a value that lives directly in a field (not inside a list)."""
    return (value.replace(ESCAPE, ESCAPE + ESCAPE)
                 .replace(FIELD_SEP, ESCAPE + FIELD_SEP)
                 .replace("\r\n", "\n").replace("\r", "\n").replace("\n", ESCAPE + "n"))


def escape_element(value: str, sep: str) -> str:
    """Escape a list element: like a scalar, plus the separator, a trailing *
    and a leading double quote (which would otherwise open a quoted element).

    The empty string is written ``""`` (SPEC 1.1 Â§3.4): a bare empty element
    is indistinguishable from an empty list when it is the only element."""
    if value == "":
        return QUOTE + QUOTE
    s = escape_scalar(value).replace(sep, ESCAPE + sep)
    if s.endswith(MARKER):
        s = s[:-1] + ESCAPE + MARKER
    if s.startswith('"'):
        s = ESCAPE + s
    return s
