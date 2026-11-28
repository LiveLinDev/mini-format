# Generated domain profile: mini-domain/1

[Español](DOMAIN_PROFILE.es.md) · [Integration guide](BUILD_GUIDE.md)

This document specifies the generated JSON-domain profile shipped with software
release 1.2.3. It does not replace [core SPEC 1.1](SPEC.md). Core families and their
conformance corpus retain their established syntax and parsers. Generated domain
documents use the runtime bundled by `mini build` or `minifmt.domain`.

## Contract

`contract.json` contains `profile: "mini-domain/1"`, a prefix, version `1`, the
recursive schema, selected `record_path` (array of object keys or null), and
`schema_id`. The fingerprint is the first twelve hexadecimal SHA-256 characters
of compact UTF-8 JSON containing, in order, `profile`, `prefix`, `version`,
`schema`, `record_path`. Field order is significant. Informational sample counts
do not change the schema identity. Load contracts from a trusted build: the short
fingerprint is a compatibility guard, not cryptographic authentication.

Types are object, array, string, integer, number, boolean and open `json`.
Objects contain ordered fields with `name`, `optional`, `schema`; arrays have
`items`; `nullable` allows null. Unknown object keys are rejected. An open JSON
node intentionally preserves arbitrary JSON, including new keys.

Inference combines every supplied complete document. Missing members become
optional; observed nulls allow null. Null-only, empty-list item and heterogeneous
types remain open JSON. Numeric mixtures widen integer to number. Observed
constant values are never installed as permanent domain defaults.

## Wire document

UTF-8, LF-separated physical lines, with one optional final LF:

```text
phone|v=1|n=2|h=<schema_id>
<record 1 cells>
<record 2 cells>
```

The header contains the prefix, required `v`, `n`, `h`, optional wrapper `m`,
optional shared-column table `d` and optional string-dictionary table `e`.
Unknown or duplicate header names are errors. `n` must match the exact record
count. Wrong fingerprints fail instead of attempting another schema.

Rows use `|`-separated cells, without a repeated record tag. Required non-nullable
objects are recursively flattened in schema order; empty required objects are
reconstructed from the schema. Optional/nullable objects retain a positional
cell. For scalar, array, open-JSON or nullable-object records, one cell represents
the complete record. A row with zero transmitted columns is `-`.

Field escaping applies to every header and row cell: `\\` is backslash, `\|` a
pipe, `\n` a newline and `\r` a carriage return. Other escapes are invalid. Spaces
are data, not optional formatting.

## Cell values

`?` means an absent optional member; `~` means null. They are distinct from an
empty string, zero and false. Strings normally have no quotes. Empty strings,
literal `?` or `~`, and strings beginning with a quote use a JSON string instead.
Then field escaping is applied. Non-finite numbers and duplicate JSON object
keys are rejected. Integers and numbers retain their JSON values without coercion.

Nested objects are positional JSON arrays in field order. An absent optional
member inside such an array is `{}`. An open JSON node wraps its non-null value
in `[value]`, so an actual empty object cannot collide with the absence marker.
Nested arrays transform items recursively; null remains null. Apply JSON encoding
first, then the outer field escaping.

For a collection nested within a root object, `m` is the positional JSON encoding
of the complete wrapper with the selected collection replaced by `[]`. Metadata
is transmitted, not recovered from training samples. Root arrays have no `m`;
other roots contain exactly one record and no `m`.

## Explicit per-document optimization

`d` is JSON `[[columnIndex, encodedCell], ...]`, with zero-based column indexes.
Those columns are omitted from every row and restored from the header. Values
are computed from the current document and validated with the same schema.

`e` is JSON `[[columnIndex, [encodedStringCell, ...]], ...]`. A dictionary column
stays present in each row but contains a zero-based decimal dictionary index.
Only string columns qualify. Dictionaries are transmitted in full; they never
reference a hidden training vocabulary. A column cannot appear in both `d` and
`e`. Invalid/duplicate indexes are errors. Header JSON receives the same field
escaping as other cells.

The encoder uses these options only when its byte-cost estimate is favorable.
`encode(value, contract, shared=False)` disables `d`;
`encode(value, contract, dictionaries=False)` disables `e`. Pass both flags to
disable both optimizations. Token savings still depend on the tokenizer; byte
savings are not a universal token guarantee.

## Compact rows for model replies

For a root array of flat objects with required, non-null scalar fields, the
model can reply with rows alone. Choose a string column to place last and pass
the record count the application expects.

For compatible samples, the toolkit writes `compact_last_text_field` in
`setup.json`. This recommends the column that saved the most quoting and
escaping when placed last in the sample. You can pass it to the workflow.

```python
data = flow.run(generate, task, expected_records=20, last_text_field="title")
```

In the generated `workflow.mjs`, pass `{expectedRecords: 20, lastTextField: "title"}`.
The workflow checks the columns, types and record count against the toolkit
contract. Python's `last_run["mini"]` and Node's `lastRun.mini` hold the
`.mini` document with its header. `encode_rows` and `decode_rows` also support
direct use with the contract. Measure prompts, replies and retries with your
model and data to choose a mode.

If the application already knows fields such as IDs and the task preserves input
order, pass those fields for each row. The model emits only the other columns.
The workflow validates the known values and restores them by position before
returning the complete JSON.

```python
data = flow.run(
    generate, task, expected_records=2, last_text_field="title",
    known_rows=[{"id": 91}, {"id": 7}],
)
```

In Node, use `{expectedRecords: 2, lastTextField: "title", knownRows: [{id: 91}, {id: 7}]}`.
Every known row must have the same fields. Keep IDs in the model output when the
task may reorder the rows.

For flat text, integer, and boolean columns, the Spanish prompt lists each
generated column once and shows how to write a literal backslash. For one to
24 expected rows with `known_rows`, the prompt groups values by line and
shows an example in column order. If one field remains, it asks for one JSON
string per row. When comparing against JSON or CSV, include the instructions,
reply, and retries through exact recovery.

For 25 to 48 rows with two text fields left to generate, the Spanish workflow
requests one JSON array per line. This keeps spaces inside either field without
moving part of a value to the following column. The toolkit validates both
strings and restores the known fields before returning JSON.
If one row is invalid and the source ends with one JSON record per line whose
known fields match the expected order, the workflow can request that record
alone. It keeps the other rows and validates the complete result again.

For one row with two text fields remaining, the Spanish workflow can request a
compact CSV row. It uses space-separated JSON strings when the task contains
escape sequences other than quotes. Both paths validate the result, restore
known fields, and store the `.mini` document.

### Positional rows with a provider schema

For the same flat lists, `flow.run_positional(generate, task, expected_records=20)`
requests a JSON array of rows without keys and restores the named objects.
`generate(prompt, schema)` passes the schema to the provider. For example, use
it as `format` in Ollama. The Node method is
`flow.runPositional(generate, task, {expectedRecords: 20})`. The workflow
checks types and counts and keeps a validated `.mini` document in the history.

For providers that require a JSON object in their native output schema, use
`flow.run_columnar(generate, task, expected_records=20)`. Each field is sent
once with its list of values. A single record uses scalars. `known_rows` restores
application-owned fields, and `allowed_values` specifies valid field choices.
In Node, call `runColumnar` with `expectedRecords`, `knownRows`, and `allowedValues`.

### Compact rows with a native output schema

For flat records with known choices and a free-text field, use a provider
whose schema supports `pattern`. The model writes each row as a single string
in `r`. The application restores IDs and validates the values.

```python
data = flow.run_native_rows(
    generate, task, expected_records=2, last_text_field="title",
    known_rows=[{"id": 7}, {"id": 9}],
    allowed_values={"status": ["open", "closed"]},
)
```

Declare the choices for every field the model writes before the final text
field. The text takes up the rest of the string, including spaces, quotes, and
line breaks. For a single record, `r` is a string. In Node, call `runNativeRows`
with `expectedRecords`, `lastTextField`, `knownRows`, and `allowedValues`.
Pass the schema to the provider from the callback as in `run_columnar`.

Use `reuse_schema=True` in Python or `reuseSchema: true` in Node to send the
same schema when the row count changes. Keep the order of the allowed values
and the same projected fields so the provider can reuse its cache. In this
mode, `r` is always an array and the SDK validates the exact row count before
returning JSON. Regenerate the toolkit with the current package to use it.

## Compact transport for existing JSON

`minifmt.transport.dumps(value, count=counter)` chooses the lowest-cost
representation among compact JSON, rows with a compact contract, and tabular
sections. JSON responses with a table and metadata can use the adaptive
mini-domain/2 codec or a single table section with integer sequences. The
counter includes the wrapper and contract. `loads(text)` reconstructs the JSON and can validate it
against a domain contract. Use this path for data the application already has.

In tables of scalar values, the header can store the start and step of an
integer sequence. The decoder restores those values in row order.

```sh
python -m minifmt.transport encode data.json --tokenizer o200k_base > data.txt
python -m minifmt.transport decode data.txt
```

For a table the model will read, use `dumps(value, for_model=True)` or
`encode --for-model`. It keeps IDs and row counts explicit and uses compact
JSON if it is shorter or the data does not fit the table layout.
An object with multiple compatible tables can use blocks separated by a blank
line under a `++` metadata header. `loads` restores the complete JSON and
validates the columns and record count of each table.
In `++` blocks, headers omit `:s` for text fields.

For lists with repeated titles or descriptions, use `dumps(value, text_refs=True)`
or `encode --text-refs`. The encoder checks whether a dictionary `@refs` reduces
the size and can use a `+++` block. A `:r` column contains dictionary keys.
Tell the model to look up each `:r` field in `@refs` and copy the text.
`loads` recovers the exact values.

For repeated questions about one document, place the `dumps` text at the start
of the input and append each question. An identical prefix lets providers
that support prompt caching reuse it.

The default minimizes UTF-8 bytes. In Python, supply a function that returns the
token count for your model. The CLI requires `tiktoken` for `--tokenizer`.

## Validation and evolution

Decode checks contract identity, escapes, column counts, field types, nullability,
required members, wrapper shape and record count. Errors expose stable `D_*`
codes, physical line and JSON path. `diagnose` reports recoverable and rejected
lines. `repair` fixes explicit transport wrappers, including the exact Markdown
heading from the generated contract prompt when it appears before the document.
`apply_replacements` merges externally corrected invalid lines and validates the
complete document.

If a first response from the model arrives as a complete JSON array or object,
the standard workflow can validate it against the same contract and expected
record count and convert it to .mini locally. The history keeps the original
response as JSON. A provider's truncation signal takes precedence.

New fields are not silently ignored. Rebuild with representative examples in a
new directory and distribute its prompt, contract and parser together. Structural
validation does not prove a model's factual accuracy or business-rule compliance.
