# Changelog

## 1.2.2

Running `mini` now opens a first-run wizard in a terminal; `mini init` starts it explicitly. It can build a toolkit from JSON, CSV, TSV or XML, or from fields entered interactively. Each generated toolkit includes `GUIA.md` with validation, repair and conversion steps. `mini help` also works.

The core remains on SPEC 1.1. The 14 domain contracts are optional examples in a separate download;
Python and Node packages focus on building and reading a contract for the user's own data.
The site now explains this through one Examples entry point, with the help-desk demo clearly labeled.
Previously prepared fixes below also ship in this release. Proposed ADRs 0017 and 0018 remain proposals.

### Fixed

- Python parser: a header entry written `key\=value` (an escaped `=`) kept a broken key and reported only E09. SPEC
  §3.2 splits at the first UNESCAPED `=` and §5 makes an entry without one E12, which is what the TypeScript library
  and `js/mini.js` already did. Found by the differential fuzz of the V5 audit (20 real divergences).
- `merge_repair` (Python and TypeScript) no longer accepts a correction that repeats the value of a `unique` field of
  another valid record, or of another accepted correction: it leaves the original line unresolved with a note instead of
  turning a valid record into an E11 duplicate. Same rule in both languages, with parity fixtures.
- The instruction block described a list with `max: 0` as unbounded (`∞`); no published contract uses `max: 0`, so no
  existing prompt changes.
- TypeScript `ReaderResult.finalRecords` (the valid last line without LF, as `final_records` in Python) and
  `readRecords` now yields that record too.
- `mini from-json --out`, `to-json --out`, `from-schema --out` and `build` write LF on every OS (they wrote CRLF on
  Windows); `mini tokens` without the extras says how to install them instead of a raw `FileNotFoundError`.
- `js/mini.js` is reproducible: `tools/build_js.mjs` reads the TypeScript sources with LF whatever their on-disk line
  endings, the file was regenerated (the committed one carried 289 CRLF and 3 stray CR, so `build_js.mjs --check` and
  `tests/test_js_port.mjs` failed on every clean checkout), and `.gitattributes` fixes `eol=lf` for `js/mini.js`,
  `*.mjs`, `*.ts`, `*.py`, `*.md` and `*.json`. The bundle does not depend on the Node version in any way that could be
  measured here (only Node 22.14.0 was available): CI now pins Node 22.14.0.
- `tests/test_schema.py` declared the Pydantic model with `Optional[str]` for a field the expected signature types as
  `date`; `pydantic`, `jsonschema` and `hypothesis` are now in the `dev` extra so those tests are not skipped in CI.

### Added

- Conformance suite: 376 cases (4 new ones for the escaped `=` in a header, written from SPEC §3.2, §3.3 and §5).
- Independent decoder (`conformance/oraculo/`), written from the SPEC grammar without importing `minifmt`; it passes the
  307 strict and lenient cases and is the oracle for the new tests.
- Property tests with Hypothesis (per official family and per generated contract: `parse(dumps(o)) = o`, stability of the
  emitted text, oracle and `js/mini.js` agreement, rejection codes), streaming tests that cut every document at every byte
  boundary (Python, TypeScript and `js/mini.js`), process-level CLI and example tests, and adapter tests marked MOCK.
  `tests/conftest.py` makes any non-loopback network connection fail.
- `tools/fuzz_diferencial.py`: differential fuzz Python / `js/mini.js` / oracle with fixed seeds and a time budget
  (`--presupuesto`, at most 120 s), working in a temporary directory.
- `tools/cobertura.py`: line and branch coverage defined separately for Python (`coverage --branch`) and TypeScript
  (`node --experimental-test-coverage`); fails below 90 % of lines and reports branches (TypeScript: 88.71 % to 92.08 %).
- `tools/ejecutar_v5.py`: one command that runs every V5 verification and records an evidence run
  (`evidencia/corridas/v5-<stamp>/`).
- ADR 0017 (outer whitespace, list-element escaping, canonical decimal, header defaults, all-empty records, whitespace
  set) and ADR 0018 (integers beyond 2^53 in TypeScript), both proposals with alternatives, compatibility and acceptance tests.
- CI: Node pinned to 22.14.0, `build_js.mjs --check`, the independent oracle, a 60 s differential fuzz and the coverage gate
  on Linux, Windows and macOS with Python 3.9 and 3.12 (not run here: Actions is private).

### Known and not changed

- SPEC gaps documented by expected-failure tests: strings with outer whitespace and empty strings in optional fields are
  altered by `dumps`/`parse` (D-1, D-2), a non-canonical decimal is emitted as written (D-4), a header key with a `default`
  breaks `dumps(parse(t)) = t` (D-10), a record whose fields are all empty is a blank line (D-11), and the "whitespace" set
  of SPEC §3.5 is undefined (B-1). See ADR 0017.
- Integers beyond +-2^53 lose precision silently in TypeScript and `js/mini.js` (Python is exact); pinned by
  `ts/test/bigint.test.ts`, decision pending in ADR 0018.
- The instruction block (`mini prompt`) still omits enumeration values inside tuples, `unique`, `count_key` and the
  description of non-scalar fields (D-5): changing it would change the prompt sizes already measured in benchmarks.

## 1.2.1

- `--contract` accepts the base-profile contract written by `mini from-schema`, not only the generated
  `mini-domain/1` toolkits: `validate`, `diagnose`, `to-json`, `from-json` and `prompt` read it with the core
  parser, so the contract produced by the CLI can be used by the same CLI
  (`mini validate respuesta.mini --contract contrato_tk.json`). Toolkit contracts keep their own commands.

## 1.2.0

- Offline demonstration (`demo/sin-conexion/demo.py`): contract, generated
  instruction, streaming read of a real archived model answer, diagnostics,
  selective repair and typed objects, with network access blocked; checked by
  `tests/test_demo_sin_conexion.py` (under 3 minutes).
- CI matrix on Linux, Windows and macOS with Python 3.9 and 3.12; coverage gates
  of 90 % for Python (including the AI kit tests) and TypeScript lines; the site
  workflow installs `ts/` development dependencies before building releases.
- `tools/smoke_release.py` installs the npm package inside its own temporary
  project, so npm never resolves an unrelated parent `package.json`.
- JSON Schema and Zod converters map `date` (`format: date`) and `decimal`
  (`format: decimal` or the `x-mini` annotation) with their bounds.
- Publish core SPEC 1.1 (2026-09-17, English and Spanish). It fixes the seven
  behaviors SPEC 1.0 left undefined, each with a normative rule, conformance
  cases and a decision record; every document valid under 1.0 keeps its validity
  and canonical object (SPEC §13):
  - `\,` is a literal comma with any list separator; `\<sep>` only for the
    contract's own separator.
  - Booleans accept only `true`/`false`/`1`/`0`; integers and floats use ASCII
    digits, no leading `+`, and floats need digits on both sides of the point.
  - An ill-typed header value reports the code of its type violation (`n=abc`
    is E06, no longer E06 + E03).
  - A repeated header key is E12; the first occurrence counts.
  - Empty list elements are empty strings and are serialized as `""`, so `[""]`
    round-trips.
  - An empty optional list or marked list is null.
  - The serializer rejects invalid objects with the parser's error code and the
    line the entry would occupy, and verifies every emitted document.
- Add the `date` (`YYYY-MM-DD`, calendar-checked) and `decimal` (exact, canonical
  JSON string) scalar types with optional `min`/`max`, in Python, TypeScript,
  contract validation, prompt blocks and the playground wizard.
- Conformance suite 1.1: 372 cases (303 from 1.0 kept with the same
  expectations), `SPEC_1_1_RULES` index and serializer error-code checks in the
  Python, TypeScript and JavaScript runners.
- Generate the playground engine `js/mini.js` from the TypeScript library
  (`tools/build_js.mjs`) instead of maintaining a hand-written port;
  `tests/test_js_port.mjs` checks that it is up to date and runs every
  conformance case against it (`conformance/run_js.mjs`).
- Add architecture decision records in `docs/adr/` (Spanish) for the positional
  contract, escapes and quotes, marked lists, count keys, lenient mode, forking,
  version tails, the playground engine, the SPEC 1.1 rules and the new types.
- Fix the domain toolkit wrappers (`validator.py`, `repair.py`) on Windows builds
  of Python 3.9, where the built-in `parser` module shadowed the bundled parser.
- TypeScript library (`@mini-format/core`): strict `tsconfig.json`, `npm run typecheck`
  (TypeScript as a devDependency) and `.d.ts` declarations emitted into `dist/` by
  `tools/build_node.mjs`; `exports.types` now points to `dist/index.d.ts`
  (`--no-types` builds JavaScript only). CI installs `ts/` devDependencies and
  runs the type check.
- The compiled ESM is verified to validate documents without Node APIs (a `vm`
  context with browser globals only); only `Registry.load` needs Node.
- Selective repair in TypeScript: `extractDocument`, `repairRequest`, `mergeRepair`
  with the same lines, error codes and request text as `minifmt.ai.repair`,
  checked against fixtures generated from the Python reference.
- Contracts from Zod v4 or JSON Schema (`fromZod`, `fromJsonSchema`) for flat
  records, with explicit E20 errors for non-representable structures or
  constraints. Zod stays a development dependency only.
- Interchangeable model adapters over `fetch` (no SDKs): `OpenAIAdapter` (Chat
  Completions), `OpenAIResponsesAdapter`, `AnthropicAdapter`, `GroqAdapter` and a
  network-free `SimulatedAdapter`, with SSE streaming (`parseSSE`) and
  `streamRecords`, which feeds `createReader` to emit records as they arrive.
  Tests use injected `fetch` and synthetic SSE streams only.
- Add `minifmt.stream` (`Reader`, `create_reader`, `read_records`): an incremental
  Python reader equivalent to the TypeScript `createReader`/`readRecords`. It accepts
  text or UTF-8 bytes split anywhere, emits each record when its line closes, reports
  header, `n`, truncation and incomplete last line, and yields the same records and
  errors as `parse()`. Records are not retained by `read_records`, so peak memory is
  independent of the record count (tested with 200,000 records; 1,000,000 with
  `MINI_STREAM_MILLION=1`). Unlike the TypeScript generator, a final valid line
  without LF is also yielded.
- Add `minifmt.schema` (`from_json_schema`, `to_json_schema`, `from_pydantic`) and the
  `mini from-schema` / `mini to-schema` commands. Required properties become core
  fields and optional ones extensions; one-level objects become tuples; deeper
  nesting is rejected with E20 citing SPEC §12. Contract information absent from
  JSON Schema is kept in `x-mini` annotations, so contract -> schema -> contract is
  lossless. Pydantic remains optional.
- Add `mini bench FILE [-p PREFIX | --contract PATH] [--enc] [--format table|json]`:
  tokens and bytes for .mini, compact/indented JSON, YAML, flattened CSV and the
  official TOON encoder (via Node.js), with the saving relative to compact JSON.
  Missing optional dependencies are reported as unavailable; a missing tokenizer is
  a clear error. It reproduces the archived o200k_base counts of the benchmark.

## 1.1.0

- Build domain toolkits from multiple JSON samples, preserving nested structure,
  absent fields, nulls and arrays through a generated contract.
- Export bilingual prompts, a standalone Python runtime, validation, diagnostics
  and conservative repair tools.
- Ship an offline wheel, compiled Node ESM with bundled families, a toolkit ZIP,
  source archive and SHA-256 checksums directly from the website.
- Compare public JSON snapshots against official nested/flat TOON and other
  formats, with round-trip verification and separate prompt costs.
- Add bilingual onboarding and replace development-status copy with executable
  installation and integration guides while preserving the visual system.
- Fix core forward compatibility: only a newer declared version of the same
  prefix permits unknown trailing fields. Core SPEC 1.0 stays supported.
- Make JavaScript fixture tests work with Windows paths and CRLF checkouts.

Package version, core specification and domain profile are separate identifiers.
Release archives are built from the checkout; this does not imply registry
publication or completion of academic user studies.
