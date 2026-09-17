# Changelog

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
