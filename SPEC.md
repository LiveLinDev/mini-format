# .mini Specification

**Version:** 1.0 · **Date:** 2026-09-01 · **Status:** Stable · **License:** MIT
**Authors:** Adrián E. J. Palma Obispo, Erick J. Palomino Santa Cruz (Universidad Peruana de Ciencias Aplicadas)

---

## 1. Abstract

`.mini` is a line-oriented, positional, forkable text notation for structured
outputs produced by generative language models in **closed domains**. A
`.mini` document is a header line that names a *contract* (a family prefix)
and declares the record count, followed by exactly one record per line whose
fields are separated by `|` and whose meaning is given by position. Because
sender and receiver share the contract, the document never repeats field
names, braces, brackets, quotation marks or indentation; its structural cost is
the minimum needed to keep every record independently validatable and
deterministically convertible to a canonical JSON object.

`.mini` is not a single format but a **family of contracts** governed by a
forking protocol. Any record-oriented domain — assessment items, flashcards,
rubrics, survey items, test cases, log events, entity annotations, catalogue
rows, classification outputs, user stories — obtains its own contract without
writing a parser: the reference implementation interprets the contract.

## 2. Conformance

The key words MUST, MUST NOT, SHOULD and MAY are to be interpreted as in RFC
2119. A **conforming parser** accepts every document valid under a contract,
rejects every invalid document with at least one of the error codes of §8, and
produces the canonical object of §7. A **conforming serializer** produces, for
every canonical object valid under a contract, a document that the parser maps
back to an equal object (§9, round-trip). A **conforming fork** satisfies the
invariants of §10.

## 3. Lexical structure

### 3.1 Encoding and lines

A document is UTF-8 text. An optional leading byte-order mark MUST be ignored.
Lines are separated by LF (U+000A); a CR (U+000D) immediately preceding an LF
MUST be ignored. Lines that are empty or contain only whitespace are not
significant and MUST be skipped. The first significant line is the **header**;
every following significant line is a **record**.

### 3.2 Structural characters

| Character | Role | Scope |
|---|---|---|
| `\|` | field separator | header and records |
| *list separator* (`,` by default; one character fixed by the contract) | separates elements of a list, marked list or tuple | inside list-typed fields only |
| `*` | selection marker | only as the last character of a list element |
| `\` | escape character | everywhere |
| `"` | quoted-element delimiter | only as the first character of a list element |
| `=` | key/value separator | header entries, first unescaped occurrence |

No other character has structural meaning. Colons, brackets, braces, spaces
and tabs are literal content; a quotation mark that is not the first character
of a list element is literal.

### 3.3 Escape sequences

| Sequence | Denotes |
|---|---|
| `\|` | a literal vertical bar |
| `\,` (or `\<sep>` for the contract's separator) | a literal list separator |
| `\*` | a literal asterisk (needed only when an element would otherwise end in `*`) |
| `\"` | a literal quotation mark (needed only when an element would otherwise start with `"`) |
| `\\` | a literal backslash |
| `\n` | a line break inside a value |

Escape sequences MUST be recognised in every position. A generator MUST escape
`|`, `\` and line breaks in every value, and MUST protect the list separator
and a trailing `*` inside list elements, either with the escapes above or with
quoting (§3.4). Escaping the list separator in a scalar field is unnecessary
but harmless (over-escaping is idempotent-safe). A backslash followed by any
other character, or a trailing backslash, is an error (E09).

### 3.4 Quoted list elements

A list element MAY be enclosed in double quotes, CSV style: `"impacto, justicia
y evidencia"*`. Inside the quotes the list separator and `*` are literal and a
doubled quote `""` denotes one quotation mark; the selection marker, if any,
follows the closing quote (`"…"*`) or, equivalently, immediately precedes it
(`"…*"`); a literal asterisk in that position is written `\*`. Backslash escapes remain active inside quotes (`|`
and `\` must still be escaped). An unbalanced quote, or text between the
closing quote and the next separator, is an error (E09). Quoting and escaping
are equivalent notations for the same value; the canonical serializer emits
the escaped form.

### 3.5 Whitespace

Leading and trailing whitespace of a field, of a list element and of a header
value is not significant and MUST be trimmed. Internal whitespace is preserved.
Scalar fields are never quoted.

## 4. Grammar

```
document   ::= header ( LF record )* LF?
header     ::= prefix ( "|" entry )*
entry      ::= key "=" value
prefix     ::= [A-Za-z] [A-Za-z0-9_-]*
key        ::= [A-Za-z_] [A-Za-z0-9_]*
record     ::= value ( "|" value )*
value      ::= ( char | escape )*                 -- may be empty
list       ::= ( element ( SEP element )* )?       -- interpretation of a list-typed value
element    ::= ( bare | quoted ) "*"?
bare       ::= value                               -- must not start with an unescaped '"'
quoted     ::= '"' ( qchar | '""' | escape )* '"'
qchar      ::= any Unicode scalar except '"', "|", "\", LF
escape     ::= "\" ( "|" | SEP | "*" | '"' | "\" | "n" )
char       ::= any Unicode scalar except "|", "\", LF
```

`SEP` is the contract's list separator. The grammar is regular at the line
level: a record is recognised by a single left-to-right pass that resolves
escapes and splits on unescaped `|`; a list-typed field is then split on
unescaped `SEP`. No look-ahead beyond one character is required, so parsing is
deterministic and linear in the length of the line.

## 5. Header

The header is `prefix|key=value|key=value…`.

* `prefix` names the contract (family). It MUST match a registered contract.
* `n` MUST be present and MUST equal the number of record lines (E03/E04).
* `v` MAY be present and names the contract version (default 1).
* Other keys are typed by the contract (scalar, list or tuple). Unknown keys
  are accepted and kept as strings, which lets producers attach provenance
  (model, date, language, topic) without changing the contract.
* A header key MAY act as a **count key**: a list field whose contract entry
  declares `count_key: "k"` MUST have exactly `k` elements in every record
  (E07). This turns a delimiter collision inside a list into a detectable error.

## 6. Records and field types

A contract defines an ordered list of **core** fields followed by an ordered
list of **extension** fields. A record MUST contain every core field (E05) and
MAY contain a prefix of the extension fields; missing extensions are null. If
the header `v` is less than or equal to the contract version, a record MUST NOT
contain more fields than the contract declares (E05). If the same-prefix header
declares a higher `v`, the parser MUST lexically validate the complete record,
decode the known field prefix, and ignore only unknown trailing fields.

| Type | Text form | Canonical JSON | Notes |
|---|---|---|---|
| `str` | literal text | string | |
| `int` | `-?[0-9]+` | integer | optional `min`/`max` (E13) |
| `float` | JSON number | number | integral values may omit `.0` |
| `bool` | `true` / `false` | boolean | `1`/`0` accepted on input |
| `enum` | one of the declared values | string | E10 otherwise |
| `list<T>` | `e1,e2,…` | array | `min`/`max`/`count_key` arity (E07) |
| `mlist<T>` | `e1*,e2,…` | array **plus** a sibling `selected` key | marker rule: `exactly_one` (default), `at_least_one`, `at_most_one`, `any` (E08) |
| `tuple(a:T,b:U,…)` | `a,b,…` | object `{a:…, b:…}` | fixed arity (E07); one level of nesting without nesting syntax |

An empty field denotes null and is valid only for optional fields (E06). A
field declared `unique` MUST NOT repeat its value within a document (E11).

The **marked list** is the idiom that replaces a separate "answer" field: the
selected element carries a one-character suffix, keeping the selection attached
to its content. For `exactly_one`/`at_most_one` the canonical `selected` value
is an index (or null); for `at_least_one`/`any` it is an ascending list of
indices.

## 7. Canonical object

A parser MUST produce:

```json
{ "prefix": "<prefix>",
  "header": { "n": <int>, "v": <int>, ...typed header entries... },
  "<records_key>": [ { "<field>": <value>, ... }, ... ] }
```

`records_key` is declared by the contract (e.g. `items`, `cases`). A marked
list `options` with selection key `correct` yields two sibling keys
`"options": [...]` and `"correct": <index>`. A tuple yields a nested object.
Canonical numbers compare numerically (`-1` ≡ `-1.0`).

## 8. Validation and error codes

Validation is **local** (each record is checked on its own line) and
**global** (count and uniqueness). A parser MUST report the 1-based line number
of every error. Strict parsers collect all errors and reject the document;
lenient parsers return the valid records together with the error list, which
enables partial recovery of long generated outputs.

| Code | Condition |
|---|---|
| E01 | no header line |
| E02 | header prefix does not match the contract |
| E03 | header lacks `n` |
| E04 | number of record lines ≠ `n` |
| E05 | record has fewer fields than the core, or has excess fields without declaring a document version newer than the contract |
| E06 | scalar value does not match its type, or a required value is empty |
| E07 | list / tuple arity outside `min`/`max`, or ≠ `count_key`, or ≠ tuple size |
| E08 | marker count violates the marked-list rule |
| E09 | invalid escape sequence or trailing backslash |
| E10 | value not in the enumeration |
| E11 | duplicate value in a `unique` field |
| E12 | malformed or missing required header entry |
| E13 | numeric value outside `min`/`max` |
| E20 | the contract itself is invalid |
| E21 | fork invariant violated |

## 9. Round-trip

For every contract *C* and every canonical object *o* valid under *C*:
`parse(dumps(o, C), C) = o` and `dumps(parse(t, C), C) = t` for every document
*t* emitted by the serializer. This property — not compactness — is the
acceptance criterion of a `.mini` family: a compression that does not round-trip
is an abbreviation, not a serialization.

## 10. Forking protocol

A **fork** is a new contract derived from a parent. It keeps parsability by
construction if it satisfies five invariants, all machine-checkable by the
reference registry (`mini check-forks`):

| # | Invariant | Rule |
|---|---|---|
| I1 | Local line | one line = one complete, independently valid record |
| I2 | Header | prefix and `n` are mandatory; required header keys of the parent stay required |
| I3 | Stable core | the child's field list starts with the parent's full field list (core + extensions), same names, same order, same types, same list separator |
| I4 | Tail extension | new fields are appended after the inherited ones and are optional |
| I5 | Round-trip | the child ships fixtures (`valid.mini` ↔ `canonical.json`, `escaping.mini`, negative cases) that pass §9 |

Consequences. An older parser reads later documents of the **same prefix** when
the header declares a higher `v`: it validates the complete line, decodes the
fields it knows, and ignores the unknown tail. A fork uses a different prefix:
the record is first parsed with the child contract chosen by record dispatch,
after which the application MAY project its inherited prefix to the parent
schema; this is not direct parsing of the child document with the parent
contract. The child contract also accepts records without its optional
extensions when they are emitted under the child prefix. Reordering, retyping
or removing an inherited field is a breaking change and MUST be published under
a **new prefix**, never as a new version of the same prefix. Compatible growth
(appending extensions or optional header keys) increments `v`.

A fork is published as a folder `forks/<prefix>/` containing `contract.json`,
`README.md` and `fixtures/`. The specification block that a generative model
needs to produce the fork is derived mechanically from the contract
(`mini prompt <prefix>`); a fork therefore consists of data, not code.

## 11. Design rationale

* **Position instead of names.** In a closed domain both sides know the
  schema; repeating `"statement"`, `"options"`, `"correct"` in every record is
  pure overhead. Moving the schema to the contract, declared once, is what makes
  the per-record cost approach the content itself.
* **One byte, one role.** `|` never appears inside lists, the separator never
  appears at field level, and `*` is only a suffix. This strict separation of
  levels is what keeps the grammar regular and the parser one-pass.
* **Two equivalent protections for the list separator.** Version 0 (2026-06)
  used CSV-style quoting only; generative validation showed that a weaker model
  sometimes omitted the quotes and produced silent delimiter collisions. A
  draft of version 1 replaced quoting by backslash escaping only; a second
  round of validation showed that the same class of model ignores an unfamiliar
  escape but reliably applies CSV quoting, which it has seen in vast amounts of
  training data. Version 1.0 therefore accepts both notations (§3.3, §3.4),
  emits the escaped form canonically, and adds the count key of §5, which
  turns any residual collision into a detectable arity error instead of a
  silent corruption.
* **Marker as suffix.** The selection travels with its content, which avoids
  index/content misalignment during generation and allows local verification.
* **Append-only evolution.** The same discipline used by binary protocols and
  evolvable schemas (new fields only at the end; older readers ignore the tail
  only when the same prefix declares a later `v`) gives forward and backward
  compatibility without additional negotiation.

## 12. Limitations (by design)

`.mini` does not represent deep hierarchies, many-to-many relations inside a
record, heterogeneous records in one document, or schemas that evolve during a
conversation. Relations are expressed with the relational pattern (a second
family whose records reference identifiers of the first, e.g. `card` records
pointing to `a` items) or with one-level `tuple` fields. Formal interoperability
standards (e.g. QTI for assessment) remain the target of the canonical object,
not of the wire format. Token savings are tokenizer- and language-dependent;
the reference benchmark reports the tokenizer, corpus, serializers and baseline
of every figure.
