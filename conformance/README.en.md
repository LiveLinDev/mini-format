# .mini conformance suite (specification 1.1)

Language-independent cases to check that a `.mini` implementation (Python,
TypeScript or another) behaves as `SPEC.md` requires. Every implementation must
run **the same runner logic** described below.

```bash
python conformance/run_python.py          # summary by category (exits 1 if anything fails)
python conformance/run_python.py -v       # shows the reason for each failure
python conformance/run_python.py -k quotes
python conformance/generate.py            # regenerates cases/*.json
node conformance/run_js.mjs               # same suite against js/mini.js (playground engine)
```

The suite also runs inside `pytest` (`tests/test_conformance.py`), in
`cd ts && npm test` (`ts/test/conformance.test.ts`) and in `node tests/test_js_port.mjs`
(playground engine).

## Files

| Path | Content |
|---|---|
| `cases/<category>.json` | `{"suite", "spec", "category", "cases": [case, ...]}` |
| `generate.py` | Source of the cases. Expectations come from the fixtures published in `forks/*/fixtures` or are handwritten from `SPEC.md`; they are **never** computed by running the implementation. |
| `run_python.py` | Reference runner against `minifmt`. |
| `run_js.mjs` | Runner against `js/mini.js`, the playground engine generated from `ts/src`. |

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
| `dumps` | `dumps(input, contract)` | If `expected.rejected`: the serializer throws an error and, when `expected.errors` exists, its `(code, line)` pair is one of the expected ones (SPEC §9: the parser's code and the line the entry would occupy). If not: the text is byte-for-byte identical to `expected.mini` and that text is accepted in strict mode. |
| `contract` | load `input` as a contract | The errors (E20, line 0) match; `[]` means valid contract. |
| `fork` | check `contract`/`family` against `parent` (family name or embedded contract) | The invariant errors (E21, line 0) match as a set; `[]` means valid fork. |

An unexpected implementation failure (unforeseen exception) counts as a failed case.

## Categories

| Category | Covers |
|---|---|
| `fixtures` | `valid.mini` ↔ `canonical.json` and each `bad_*.mini` of the 14 families |
| `lenient` | each `bad_*.mini` in lenient mode: valid records kept |
| `escapes` | `\|` `\,` (with any separator) `\;` `\*` `\"` `\\` `\n`, invalid and dangling escapes (E09), CRLF, each family's `escaping.mini` |
| `quotes` | CSV-style quoted elements, `""`, marker inside or outside, E09 |
| `lists` | `min`/`max`/`count_key` arity (E07), element types, custom separator, empty elements |
| `mlist` | the four marker rules (E08) and the canonical form of the selection |
| `tuples` | arity (E07), optional components, marker forbidden |
| `optionals` | empty fields, extension tail, empty requireds (E06), empty optional lists (null) |
| `arity` | fewer fields than the core, or excess fields without a later `v` (E05) |
| `types` | int, float, bool, enum, date, decimal and their lexical forms (E06, E10, E13) |
| `unique` | E11 and its interaction with lenient mode |
| `header` | E01, E02, E03, E04, E12, BOM, blank lines, typed, ill-typed, repeated and unknown keys |
| `truncation` | incomplete last record, missing lines, regeneration diagnostics |
| `roundtrip` | canonical serialization and its rejection of invalid objects with the parser's code |
| `contract` | invalid contracts (E20) |
| `fork` | I3/I4 invariants of the forking protocol (E21) |

## Rules added in specification 1.1

Version 1.0 of this suite avoided seven behaviors that `SPEC.md` 1.0 did not
define precisely. SPEC 1.1 fixes a rule for each one (§13 of the specification)
and the suite checks it; `SPEC_1_1_RULES` in `generate.py` lists the cases of each
rule and `tests/test_conformance.py` verifies that they exist.

| Point | 1.1 rule | ADR | Cases (examples) |
|---|---|---|---|
| `\,` with a separator other than `,` | literal comma; `\<sep>` only for the contract's own separator | [0009](../docs/adr/0009-escape-de-coma-con-cualquier-separador.md) | `esc-comma-custom-separator`, `esc-other-separator-invalid` |
| Booleans `yes`/`t`…, integers with `+`, floats `.5` or `1.` | E06; only `true`/`false`/`1`/`0` and ASCII digits | [0010](../docs/adr/0010-formas-lexicas-estrictas-de-escalares.md) | `sc-bool-yes`, `sc-int-plus`, `sc-float-leading-dot` |
| Ill-typed header value (`n=abc`) | code of the type violation (E06), no E03 | [0011](../docs/adr/0011-codigo-de-valor-de-cabecera-mal-tipado.md) | `hdr-n-not-int`, `hdr-n-not-int-lenient` |
| Repeated header keys | E12; the first one counts | [0012](../docs/adr/0012-claves-de-cabecera-repetidas.md) | `hdr-duplicate-key`, `hdr-duplicate-n` |
| Empty list elements and the round-trip of `[""]` | the empty string; the serializer writes `""` | [0013](../docs/adr/0013-elementos-de-lista-vacios.md) | `list-empty-element-middle`, `list-single-empty-string` |
| Empty optional list | null | [0014](../docs/adr/0014-lista-opcional-vacia-es-null.md) | `opt-list-empty-null`, `opt-mlist-empty-null` |
| Serializer error code | the parser's code and the line the entry would occupy | [0015](../docs/adr/0015-errores-del-serializador.md) | `dumps-error-range`, `dumps-error-second-record` |

The 1.1 suite also covers the `date` and `decimal` types
([ADR 0016](../docs/adr/0016-tipos-date-y-decimal.md); cases `date-*`, `decimal-*`,
`dumps-date-decimal`, `contract-date-*`).

The 303 cases of the 1.0 suite are kept with the same expectations; five
`dumps-reject-*` cases now also pin the error code and `contract-unknown-type`
uses `datetime` as the unknown type.
