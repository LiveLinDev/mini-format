# Generated domain profile: mini-domain/1

[Español](DOMAIN_PROFILE.es.md) · [Integration guide](BUILD_GUIDE.md)

This document specifies the generated JSON-domain profile shipped with software
release 1.1.0. It does not replace [core SPEC 1.0](SPEC.md). Core families and their
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

## Validation and evolution

Decode checks contract identity, escapes, column counts, field types, nullability,
required members, wrapper shape and record count. Errors expose stable `D_*`
codes, physical line and JSON path. `diagnose` reports recoverable and rejected
lines; `repair` only fixes explicit transport wrappers. `apply_replacements`
merges externally corrected invalid lines and validates the complete document.

New fields are not silently ignored. Rebuild with representative examples in a
new directory and distribute its prompt, contract and parser together. Structural
validation does not prove a model's factual accuracy or business-rule compliance.
