# .mini conformance suite (specification 1.0)

Language-independent cases to check that a `.mini` implementation (Python,
TypeScript or another) behaves as `SPEC.md` requires. Every implementation must
run **the same runner logic** described below.

```bash
python conformance/run_python.py          # summary by category (exits 1 if anything fails)
python conformance/run_python.py -v       # shows the reason for each failure
python conformance/run_python.py -k quotes
python conformance/generate.py            # regenerates cases/*.json
```

The suite also runs inside `pytest` (`tests/test_conformance.py`).

## Files

| Path | Content |
|---|---|
| `cases/<category>.json` | `{"suite", "spec", "category", "cases": [case, ...]}` |
| `generate.py` | Source of the cases. Expectations come from the fixtures published in `forks/*/fixtures` or are handwritten from `SPEC.md`; they are **never** computed by running the implementation. |
| `run_python.py` | Reference runner against `minifmt`. |

Cases using `family` read `forks/<family>/contract.json` from the repository root.

## Case format

```json
{
  "id": "quote-doubled",
  "category": "quotes",
  "description": "\"\" inside quotes is one quote",
  "mode": "strict",
  "family": "a",
  "contract": { "...": "embedded contract, alternative to family" },
  "parent": "a",
  "input": "mk|n=1\n\"dijo \"\"sí\"\"\"*,no|a*|a|1",
  "expected": {
    "canonical": { "prefix": "mk", "header": {"n": 1, "v": 1}, "rows": [ ... ] },
    "errors": [ {"code": "E08", "line": 2} ],
    "mini": "expected .mini text when serializing",
    "rejected": true,
    "diagnostics": { "invalid_lines": [3], "missing_records": 0 }
  }
}
```

* Each case has **exactly one** of `family` (official family name) or `contract`
  (embedded contract with the same schema as `contract.json`), except `contract`
  mode, which uses neither.
* `input` is `.mini` text (`strict` and `lenient` modes), a canonical object
  (`dumps` mode), a contract (`contract` mode) or `null` (`fork` mode).
* `expected` only contains the keys that apply to the mode.

## Mode semantics (runner logic)

Common comparisons:

* **Errors**: compared as a **set of distinct `(code, line)` pairs**; order and
  repetition do not matter. `line` is the physical line (1-based, counting skipped
  blank lines); document errors (E01, E04) and contract/fork errors (E20, E21) use
  line `0`.
* **Canonical**: structural equality; object keys are compared as a set and numbers
  numerically (`-1` ≡ `-1.0`, 1e-12 tolerance). A record's missing fields count as
  `null`; a marked list appears as two sibling keys (elements and selection).

| Mode | Action | Passes if |
|---|---|---|
| `strict` | `parse(input, contract, strict)` | If `expected.errors` exists: the document is rejected and the pairs match. If not: it is accepted, the canonical matches `expected.canonical` and, when `expected.mini` exists, `dumps(canonical) == mini` and `parse(mini)` yields the same canonical again (round-trip). |
| `lenient` | `parse(input, contract, lenient)` | If `expected.canonical` exists: a document is returned with those valid records (and the header read), and its errors match `expected.errors` (empty list = no errors). If there is no `canonical`: the document cannot be built (e.g. E01) and the errors match. If `expected.diagnostics` exists: the rejected lines (ascending, without the header) and the missing records (`n` − record lines, minimum 0) match. |
| `dumps` | `dumps(input, contract)` | If `expected.rejected`: the serializer throws an error (the code is not compared). If not: the text is byte-for-byte identical to `expected.mini` and that text is accepted in strict mode. |
| `contract` | load `input` as a contract | The errors (E20, line 0) match; `[]` means valid contract. |
| `fork` | check `contract`/`family` against `parent` (family name or embedded contract) | The invariant errors (E21, line 0) match as a set; `[]` means valid fork. |

An unexpected implementation failure (unforeseen exception) counts as a failed case.

## Categories

| Category | Covers |
|---|---|
| `fixtures` | `valid.mini` ↔ `canonical.json` and each `bad_*.mini` of the 14 families |
| `lenient` | each `bad_*.mini` in lenient mode: valid records kept |
| `escapes` | `\|` `\,` `\;` `\*` `\"` `\\` `\n`, invalid and dangling escapes (E09), CRLF, each family's `escaping.mini` |
| `quotes` | CSV-style quoted elements, `""`, marker inside or outside, E09 |
| `lists` | `min`/`max`/`count_key` arity (E07), element types, custom separator |
| `mlist` | the four marker rules (E08) and the canonical form of the selection |
| `tuples` | arity (E07), optional components, marker forbidden |
| `optionals` | empty fields, extension tail, empty requireds (E06) |
| `arity` | fewer fields than the core, or excess fields without a later `v` (E05) |
| `types` | int, float, bool, enum (E06, E10, E13) |
| `unique` | E11 and its interaction with lenient mode |
| `header` | E01, E02, E03, E04, E12, BOM, blank lines, typed and unknown keys |
| `truncation` | incomplete last record, missing lines, regeneration diagnostics |
| `roundtrip` | canonical serialization and its rejection of invalid objects |
| `contract` | invalid contracts (E20) |
| `fork` | I3/I4 invariants of the forking protocol (E21) |

## Points not pinned by the suite

The suite deliberately avoids behavior that `SPEC.md` 1.0 does not define precisely;
it awaits a decision:

* `\,` when the contract separator is not `,` (the grammar excludes it; the
  reference implementation accepts it).
* Booleans other than `true`/`false`/`1`/`0` (the reference also accepts
  `yes`/`no`/`y`/`n`/`t`/`f`), integers with `+` and floats like `.5` or `1.`.
* Error code of a mistyped header value (`n=abc` produces E06 and E03 in the
  reference; the §8 table suggests E12).
* Duplicate header keys (the reference keeps the last).
* Empty list elements (`a,,b` or trailing separator): the reference accepts them
  as the empty string, which breaks the round-trip of `[""]`.
* Empty optional list: the reference returns `[]`, not `null`.
* Serializer error code for invalid objects.
