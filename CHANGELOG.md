# Changelog

## 1.2.0 (sin publicar)

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
