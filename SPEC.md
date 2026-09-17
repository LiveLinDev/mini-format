# .mini Specification

**Version:** 1.1 · **Date:** 2026-09-17 · **Status:** Stable; supersedes 1.0 and keeps every 1.0 document valid (§13) · **License:** MIT
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
back to an equal object (§9, round-trip), and rejects every object that is not
valid under the contract with the error code of §9. A **conforming fork**
satisfies the invariants of §10. The conformance suite (`conformance/`) fixes the
expected result of each rule; the design decisions behind the rules, with their
evidence, are recorded in `docs/adr/`.

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
| `\,` | a literal comma, whatever the list separator (so a literal list separator when the separator is `,`) |
| `\<sep>` for the contract's separator | a literal list separator |
| `\*` | a literal asterisk (needed only when an element would otherwise end in `*`) |
| `\"` | a literal quotation mark (needed only when an element would otherwise start with `"`) |
| `\\` | a literal backslash |
| `\n` | a line break inside a value |

Escape sequences MUST be recognised in every position. A generator MUST escape
`|`, `\` and line breaks in every value, and MUST protect the list separator
and a trailing `*` inside list elements, either with the escapes above or with
quoting (§3.4). Escaping the list separator in a scalar field is unnecessary
but harmless (over-escaping is idempotent-safe). `\,` is valid in every
contract, also when the list separator is another character (over-escaping a
comma never breaks a document); `\<sep>` is valid only for the contract's own
separator, so `\;` in a contract whose separator is `,` is E09. A backslash
followed by any other character, or a trailing backslash, is an error (E09).

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

An empty list element may be written bare (`a,,b`, or a trailing separator as
in `a,`) or quoted (`""`); both denote the empty string. A field that holds a
single bare empty element cannot be told apart from an empty field (§6), so the
canonical serializer writes every empty-string element as `""`: `[""]` is
emitted as `""` and parses back to `[""]`. This is the only case in which the
serializer emits quotes.

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
escape     ::= "\" ( "|" | "," | SEP | "*" | '"' | "\" | "n" )
char       ::= any Unicode scalar except "|", "\", LF
```

Lexical forms of the scalar types (§6), applied to the value after escapes are
resolved and surrounding whitespace is trimmed:

```
int        ::= "-"? DIGIT+
float      ::= "-"? DIGIT+ ( "." DIGIT+ )? ( ( "e" | "E" ) ( "+" | "-" )? DIGIT+ )?
bool       ::= "true" | "false" | "1" | "0"
date       ::= DIGIT DIGIT DIGIT DIGIT "-" DIGIT DIGIT "-" DIGIT DIGIT
decimal    ::= "-"? DIGIT+ ( "." DIGIT+ )?
DIGIT      ::= "0" | "1" | "2" | "3" | "4" | "5" | "6" | "7" | "8" | "9"   -- ASCII only
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
* A key MUST NOT appear more than once in the header. Every repeated occurrence
  is E12; the first occurrence is the one that counts (a lenient parser keeps its
  value).
* A value of a typed key that does not match its type is reported on the header
  line with the code of that violation (E06, E07, E10, E13), as in a record. In
  particular `n=abc` or an empty `n=` is E06, not E03: E03 means that `n` is
  absent. When `n` is present but invalid, the record count is not checked (no
  E04). E12 is reserved for entries without `=`, missing required keys and
  repeated keys.

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
| `int` | `-?[0-9]+` | integer | optional `min`/`max` (E13); ASCII digits; leading zeros allowed; no `+` |
| `float` | JSON number | number | integral values may omit `.0`; leading zeros allowed; `+1`, `.5`, `1.`, `NaN`, `Infinity` are E06 |
| `bool` | `true` / `false` | boolean | `1`/`0` accepted on input; no other form (`yes`, `y`, `t`, `True`) is accepted (E06) |
| `enum` | one of the declared values | string | E10 otherwise |
| `date` | `YYYY-MM-DD` | string | an existing day of the proleptic Gregorian calendar, 0001-01-01 to 9999-12-31 (E06); optional `min`/`max` as `"YYYY-MM-DD"` (E13) |
| `decimal` | `-?[0-9]+(\.[0-9]+)?` | string | exact base-10 number, no exponent (E06); optional `min`/`max` as decimal strings or integers, compared exactly (E13) |
| `list<T>` | `e1,e2,…` | array | `min`/`max`/`count_key` arity (E07) |
| `mlist<T>` | `e1*,e2,…` | array **plus** a sibling `selected` key | marker rule: `exactly_one` (default), `at_least_one`, `at_most_one`, `any` (E08) |
| `tuple(a:T,b:U,…)` | `a,b,…` | object `{a:…, b:…}` | fixed arity (E07); one level of nesting without nesting syntax |

An empty field denotes null and is valid only for optional fields (E06). This
holds for every type: an empty optional list, marked list or tuple is null (for a
marked list, both sibling keys are null). An empty *required* list or marked list
denotes the empty list, subject to `min` and to the marker rule (E07, E08); an
empty required tuple is E07. The canonical value of an empty optional list is
therefore null, never `[]`. A field declared `unique` MUST NOT repeat its value
within a document (E11).

List and tuple elements are decoded with their item or component type. An
empty list element is the empty string for `str` items and a type error for any
other item type (E06; E10 for `enum` items). An empty tuple component is null
when the component is optional and E06 otherwise.

`date` and `decimal` travel as strings in the canonical object so that no
implementation converts them through binary floating point or a time zone. The
canonical `date` is the text itself. The canonical `decimal` removes the leading
zeros of the integer part and the sign of a zero value and keeps every
fractional digit, because the scale can be meaningful (`007.50` → `"7.50"`,
`-0.0` → `"0.0"`). In a contract, the `min`/`max` of a `date` are `"YYYY-MM-DD"`
strings and those of a `decimal` are decimal strings or integers whose absolute
value is below 2^53; any other bound makes the contract invalid (E20).

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

`records_key` is declared by the contract (e.g. `items`, `cases`). Values of
`date` and `decimal` fields are strings (§6). A marked
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
| E06 | scalar value (in a record or a typed header entry) does not match its type (§4, §6), or a required value is empty |
| E07 | list / tuple arity outside `min`/`max`, or ≠ `count_key`, or ≠ tuple size |
| E08 | marker count violates the marked-list rule |
| E09 | invalid escape sequence or trailing backslash |
| E10 | value not in the enumeration |
| E11 | duplicate value in a `unique` field |
| E12 | header entry without `=`, missing required header key, or repeated header key |
| E13 | numeric, decimal or date value outside `min`/`max` |
| E20 | the contract itself is invalid |
| E21 | fork invariant violated |

## 9. Round-trip

For every contract *C* and every canonical object *o* valid under *C*:
`parse(dumps(o, C), C) = o` and `dumps(parse(t, C), C) = t` for every document
*t* emitted by the serializer. This property — not compactness — is the
acceptance criterion of a `.mini` family: a compression that does not round-trip
is an abbreviation, not a serialization.

A serializer MUST NOT emit a document that the parser would reject. Given an
object that is not valid under the contract, it MUST fail with an error that
carries the code the parser reports for the same violation (§8) and the physical
line the offending entry would occupy in the output: 1 for the header and
*i* + 2 for the record at 0-based position *i*. For example, a null or missing
required value is E06, a value outside the enumeration E10, a value outside
`min`/`max` E13, a list of the wrong length E07, a selection that breaks the
marker rule or is not a valid index E08, a repeated `unique` value E11 and a
missing required header key E12. A serializer MAY accept non-canonical
equivalents of a valid value (for example `[]` for an empty optional list, which
it writes as an empty field and which parses back as null).

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
* **Recorded decisions.** Every rule above that involved a choice (positional
  contract, escapes and quotes, marker, count key, lenient mode, forking,
  version tail, the clarifications of 1.1 and the `date`/`decimal` types) has an
  architecture decision record with its context, alternatives and evidence in
  `docs/adr/`.
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

## 13. Changes in 1.1

Version 1.1 (2026-09-17) fixes the points that 1.0 left undefined and adds two
scalar types. Each change has a normative rule above, at least one case in the
conformance suite and a decision record.

| Point left open by 1.0 | Rule in 1.1 | Section | ADR |
|---|---|---|---|
| `\,` when the separator is not `,` | always a literal comma; `\<sep>` only for the contract's separator | §3.3 | 0009 |
| Booleans other than `true`/`false`/`1`/`0`, integers with `+`, floats such as `.5` or `1.` | rejected (E06); ASCII digits only | §4, §6 | 0010 |
| Code of an ill-typed header value (`n=abc`) | code of the type violation (E06…), no E03 | §5 | 0011 |
| Repeated header keys | E12; the first occurrence counts | §5 | 0012 |
| Empty list elements (`a,,b`, trailing separator) and the round-trip of `[""]` | the empty string; serialized as `""` | §3.4, §6 | 0013 |
| Empty optional list | null (as for every optional field) | §6 | 0014 |
| Error code of the serializer for invalid objects | the parser's code and the line the entry would occupy | §9 | 0015 |
| Dates and exact decimals | new types `date` and `decimal`, canonical JSON strings | §6 | 0016 |

**Compatibility.** A document valid under 1.0 is valid under 1.1 and produces the
same canonical object. The changes only touch inputs whose result 1.0 did not
define: forms outside the §6 table that implementations happened to accept
(`yes`, `+5`, `.5`), headers with a repeated key (whose canonical object 1.0
did not determine), and the error code reported for documents and objects that
were already invalid. `\,` with another separator and bare empty elements were
already accepted, and 1.1 fixes their meaning without rejecting them; an empty
optional list becomes null, as the 1.0 sentence "an empty field denotes null"
already stated. The 303 cases of the 1.0 conformance suite remain in the 1.1
suite with the same expectations; five serializer cases now also state the error
code, and the invalid-contract case that used `date` as an unknown type now uses
`datetime`. A 1.0 contract remains a valid 1.1 contract; a contract that uses
`date` or `decimal` requires a 1.1 implementation.
