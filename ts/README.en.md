# @mini-format/core — `.mini` TypeScript library

Software release 1.3.1. Modular, typed TypeScript implementation of the `.mini`
core notation (SPEC 1.1):
parser, serializer, specification block for prompts, family (fork) registry, a
streaming read API for token-by-token model responses, selective repair,
contracts from Zod / JSON Schema and interchangeable model adapters (OpenAI,
Anthropic, Groq, simulated) over `fetch`. No runtime dependencies; everything except
`Registry.load` also runs in the browser.

Includes the fourteen core families. Contracts adapted from JSON samples by
`mini build` use a separate `mini-domain/1` profile and their generated Python
parser; this library does not interpret that profile. See the
[builder guide](https://mini-format.pmoluna.com/en/docs/build/) and
[generated profile specification](https://mini-format.pmoluna.com/en/docs/profile/).

Authors: A. E. J. Palma Obispo, E. J. Palomino Santa Cruz (UPC). MIT license.

## Install the package

Requires Node.js ≥ 22.6. Download `mini-format-core-1.3.1.tgz` from Downloads or
extract it from the toolkit ZIP. Install the local file:

```sh
npm install --offline --ignore-scripts --no-audit --no-fund ./mini-format-core-1.3.1.tgz
```

The archive contains compiled JavaScript ESM and `.d.ts` declarations in `dist/`
(`exports.types` points to `dist/index.d.ts`), contracts for all fourteen families
and the TypeScript sources. Import it as `@mini-format/core`:
running TypeScript inside `node_modules`, `--experimental-strip-types` and an npm
registry connection are not required.

## Develop from source

Files in `ts/src/` use erasable TypeScript without `enum`, `namespace` or
parameter-properties, and explicit `.ts` import extensions. Node.js ≥ 22.6 can
run these sources with `--experimental-strip-types`; the distributed package
already contains JavaScript. Tests were verified with Node.js 22.14.0.

To generate ESM from the repository root, use Node.js ≥ 22.13:

```sh
node --no-warnings tools/build_node.mjs
```

The script strips types and rewrites relative `.ts` imports to `.js` in
`ts/dist/`, then emits `.d.ts` declarations with the TypeScript compiler installed
in `ts/node_modules` (run `npm ci` in `ts/` first). `--no-types` builds only the
JavaScript. From `ts/`, `npm run build` does the same.

## Layout

```
ts/
├── package.json
├── src/
│   ├── errors.ts      MiniError (code, line, field), MiniValidationError, E01–E21 codes
│   ├── contract.ts    ContractJSON/Contract/Field types, normalizeContract, signatures, checkFork
│   ├── codec.ts       tokenization, escapes, quotes, field and list splitting
│   ├── values.ts      scalar decoding/encoding, formatNumber
│   ├── parser.ts      parse, Document, LineEngine (line engine), detectPrefix
│   ├── serializer.ts  dumps
│   ├── prompt.ts      specBlock(contract, lang)
│   ├── registry.ts    Registry (from objects or from forks/ with node:fs)
│   ├── stream.ts      createReader, readRecords
│   ├── repair.ts      extractDocument, repairRequest, mergeRepair (selective repair)
│   ├── schema.ts      fromJsonSchema, fromZod
│   ├── adapters.ts    ModelAdapter, OpenAI/Responses/Anthropic/Groq/Simulated, streamRecords
│   ├── sse.ts         parseSSE (Server-Sent Events over fetch)
│   └── index.ts       public API
├── tsconfig.json      strict checking of src/ (tsconfig.test.json adds test/)
└── test/
    ├── fixtures.test.ts     parity with forks/*/fixtures and validation rules
    ├── repair.test.ts       selective repair and parity with minifmt.ai.repair (fixtures/)
    ├── schema.test.ts       contracts from real Zod schemas
    ├── adapters.test.ts     providers with mocked fetch and synthetic SSE streams (no network)
    ├── dist.test.ts         compiled ESM without Node APIs and .d.ts declarations
    ├── roundtrip.test.ts    parse(dumps(obj)) == obj, codec, number formatting
    ├── stream.test.ts       random 1–7 character chunks == parse
    ├── truncation.test.ts   truncated outputs
    ├── conformance.test.ts  ../conformance/ runner (skipped if missing)
    ├── cortes.test.ts       byte cuts at every boundary (ts/src and js/mini.js) == parse
    ├── defectos.test.ts     defects fixed after the V5 audit (unique in repair, max 0, finalRecords) and ADR 0017 proposals
    ├── bigint.test.ts       current behaviour with integers beyond ±2^53 (ADR 0018, proposal)
    ├── esquema_ramas.test.ts  branches of fromJsonSchema/fromZod
    ├── registro.test.ts     Registry on disk and in memory, roundtripOk
    └── helpers.ts
```

## Usage

```ts
import { Registry, parse, dumps, specBlock, createReader } from '@mini-format/core';

const reg = Registry.load('./forks');   // extracted optional families ZIP
const a = reg.get('a');

const doc = parse(texto, a);            // strict: throws MiniValidationError with every error
doc.records;                            // valid records
doc.toCanonical();                      // { prefix, header, items: [...] }

const lenient = parse(texto, a, { strict: false });
lenient.errors;                         // MiniError[] with code, line, field, message
lenient.invalidLines();                 // rejected lines (the ones to regenerate)
lenient.missingRecords;                 // n − record lines (minimum 0)
lenient.diagnostics();                  // report with the same keys as the Python reference

const texto2 = dumps(doc.toCanonical(), a);   // exact round-trip
const prompt = specBlock(a, 'es');            // block for the system prompt
```

Contracts can be passed as a `contract.json` object or already normalized
(`normalizeContract`); every function accepts both.

To run the example directly from `ts/` during development, change the import to
`./src/index.ts` and enable `--experimental-strip-types`.

### Streaming

```ts
const reader = createReader(a, {           // strict: false by default
  onRecord: ({ record, line, index }) => mostrar(record),
  onError: (e) => console.warn(String(e)),
});
for await (const token of respuestaDelModelo) reader.push(token);   // string or Uint8Array
const res = reader.end();
res.document;      // identical to parse(textoCompleto, a, { strict: false })
res.expected;      // n declared in the header
res.received;      // record lines received
res.missing;       // records missing relative to n
res.incomplete;    // last line without LF that did not validate (text, line, errors) or null
res.truncated;     // incomplete or fewer lines than n
res.finalRecords;  // records completed by end() (a valid last line without LF); already in valid/records
res.terminated;    // the stream ended on LF
```

A record is emitted as soon as its line closes with LF. `readRecords(iterable, contrato)`
wraps the same thing as an async generator. The reader uses the same line engine as
`parse`, so the final result is identical no matter how the input is chunked.

Note: if the last line does not end in LF and its last field is still valid
(e.g. clipped text), the record is indistinguishable from a complete one; in that
case `terminated` is `false` and it should be treated as suspect.

### In the browser

`dist/` only imports its own relative modules (no `node:`, `require` or `Buffer`),
so it can be served as-is and imported from a page:

```html
<script type="module">
  import { parse } from './mini-format/dist/index.js';
  const contract = await (await fetch('./forks/cls/contract.json')).json();
  const doc = parse(text, contract, { strict: false });
  console.log(doc.records, doc.errors.map(String));
</script>
```

Pass contracts as objects (`fetch` + `json()`) or with `Registry.from([...])`:
`Registry.load`, `loadContract` and `defaultForksDir` read the disk and require Node.
`test/dist.test.ts` verifies this by loading `dist` in a `vm` context that only has
`TextEncoder`, `TextDecoder` and `URL`.

### Selective repair

Same algorithm and request text as `minifmt.ai.repair` (Python), verified by parity
fixtures:

```ts
import { repairRequest, mergeRepair } from '@mini-format/core';

const req = repairRequest(modelAnswer, contract, 'en');   // only invalid lines + their error codes
if (req.needed) {
  const fix = await adapter.generate({ system: req.system, user: req.user, maxTokens: req.maxTokensHint * 2, temperature: 0 });
  const merged = mergeRepair(modelAnswer, fix.text, contract, req);
  merged.text; merged.ok; merged.replaced; merged.dropped; merged.unresolved;
}
```

`extractDocument` removes prose and code fences before the header; `mergeRepair`
accepts a correction only if it is valid on its own, keeps the original order and
never rewrites `n` (lost records stay visible as E04).

### Contracts from Zod or JSON Schema

```ts
import { z } from 'zod';
import { fromZod } from '@mini-format/core';

const Ticket = z.object({
  id: z.string(),
  priority: z.number().int().min(1).max(5),
  status: z.enum(['open', 'closed']),
  tags: z.array(z.string()).max(4),
  note: z.string().optional(),
});
const contract = fromZod(Ticket, { prefix: 'tk', unique: ['id'] });
```

Zod is not a dependency: `fromZod` calls the schema's `toJSONSchema()` (Zod v4) or the
converter passed in `options.toJSONSchema`, and then `fromJsonSchema`. Only flat
records are supported (SPEC §12): string, integer (with `minimum`/`maximum`), number,
boolean, string enums/literals, lists of scalars (`minItems`/`maxItems`), optional,
nullable or defaulted fields. Nested objects, lists of objects, unions and dates
throw `MiniError` E20; constraints that `.mini` does not validate (`pattern`, `format`,
`minLength`...) also throw unless `unsupported: 'ignore'` is set (they are then
reported in `warnings`). An empty field decodes to `null`: for `.optional()` fields
that are not `.nullable()`, drop `null` keys before calling Zod's `parse`.

### Model adapters

All providers implement the same interface, so replacing one does not change the
rest of the code:

```ts
import { AnthropicAdapter, OpenAIAdapter, streamRecords, specBlock } from '@mini-format/core';
import type { ModelAdapter } from '@mini-format/core';

const adapter: ModelAdapter = new OpenAIAdapter('gpt-4.1-mini');   // or new AnthropicAdapter('claude-...')
const request = { system: specBlock(contract, 'en'), user: 'Classify...', maxTokens: 2000, temperature: 0 };

const it = streamRecords(adapter, contract, request);   // SSE -> createReader: records as they arrive
let step = await it.next();
for (; !step.done; step = await it.next()) show(step.value.record);
step.value.reader;       // ReaderResult (document, errors, truncated...)
step.value.generation;   // { text, inputTokens, outputTokens, stopReason, ... }
```

| Class | Endpoint | Key |
|---|---|---|
| `OpenAIAdapter` | Chat Completions `/v1/chat/completions` | `OPENAI_API_KEY` |
| `OpenAIResponsesAdapter` | Responses `/v1/responses` | `OPENAI_API_KEY` |
| `AnthropicAdapter` | Messages `/v1/messages` (`browser: true` for direct browser calls) | `ANTHROPIC_API_KEY` |
| `GroqAdapter` | OpenAI-compatible `/openai/v1/chat/completions` | `GROQ_API_KEY` |
| `SimulatedAdapter` | no network: fixed or computed answers, deterministic chunking | none |

`generate(request)` returns the full result; `stream(request)` returns an async
iterable of text deltas plus `result`. Options: `apiKey` (otherwise the environment
variable, if `process.env` exists), `fetch` (injectable), `url`, `retries`, `sleep`,
`structured`, `sendTemperature`, `extraBody`, `headers`. `responseFormat`
(`{type: 'json_schema', name, schema}`) is translated to each provider's structured
mode. Error messages are redacted: keys never appear in them. `getAdapter(provider,
model, options)` creates adapters by name. `streamRecords` drops leading prose and
code fences incrementally (like `extractDocument`); pass `extract: false` to disable it.
In the browser, avoid exposing keys: prefer your own proxy via `url`.

## Tests and types

```
cd ts
npm ci             # typescript, zod and @types/node (development only)
npm test
npm run typecheck  # tsc with strict: true over src/ and test/
```

`npm test` uses no network or keys: adapters are exercised with a mocked `fetch`
and synthetic SSE streams per provider. Without `npm ci`, the Zod tests and the
`.d.ts` check are skipped. Repair parity fixtures are regenerated from the Python
reference with `PYTHONPATH=src python ts/test/fixtures/gen_repair_parity.py`.

The shared conformance suite is read from `../conformance/cases/` (or the path in
`MINI_CONFORMANCE_DIR`); if the folder does not exist, the suite is skipped. The runner
reproduces the logic of `conformance/run_python.py`. The only API mapping: in lenient
mode the reference throws when the document cannot be built (E01); TS returns a
headerless `Document` with E01, and the runner treats it as "not built".

As in the reference, escapes are also validated in lenient mode (E09 and the record
is discarded), an invalid escape in the header is E09 inside validation, and a
rejected line does not reserve its `unique` value.

## Implementations and the playground engine

`js/mini.js`, the engine of the playground, is no longer a hand-written port: since
1.2.0 it is generated from `ts/src` by `node --no-warnings tools/build_js.mjs` (a
dependency-free UMD bundle exposing the global `MINI`). `node tests/test_js_port.mjs`
fails when the committed file is out of date and runs every conformance case against
it (`node conformance/run_js.mjs` prints the same report per category). The browser
therefore validates exactly as this library does.

Remaining differences between the Python reference and TypeScript (criterion: if the
SPEC decides, follow the SPEC; otherwise follow the Python reference):

| Topic | Python | TS and `js/mini.js` |
|---|---|---|
| Empty document in lenient mode | always throws | returns `Document` with E01 (SPEC §8) |
| Non-ASCII prefix letters | accepts | rejects (SPEC §4) |
| `float` signature/spec with `max: 3.0` | `3.0` | `3` (JSON.parse cannot tell them apart) |
| Integers outside ±2^53 | exact | lose precision **silently** (use `decimal` for exact values); pending decision: ADR 0018 (proposal), behaviour pinned by `ts/test/bigint.test.ts` |

## Limitations

- Integers outside ±2^53 lose precision (JavaScript numbers).
- `Registry.load` requires Node (uses `process.getBuiltinModule`); the rest of the
  library does not depend on Node.
- `fromZod`/`fromJsonSchema` do not generate `mlist` or `tuple` fields.
- `SimulatedAdapter` does not reproduce the fault profiles of the Python simulator:
  it returns fixed or computed answers (for tests and demos).
