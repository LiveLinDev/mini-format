# @mini-format/core — `.mini` TypeScript library

Modular, typed TypeScript implementation of the `.mini` notation (SPEC 1.0):
parser, serializer, specification block for prompts, family (fork) registry and a
streaming read API for token-by-token model responses. No dependencies.

Authors: A. E. J. Palma Obispo, E. J. Palomino Santa Cruz (UPC). MIT license.

## Requirements

- Node.js ≥ 22.6 (tested with 22.23). The code runs directly with
  `--experimental-strip-types`; no build step needed.
- Syntax is limited to erasable TypeScript (no `enum`, `namespace` or
  parameter-properties; imports with explicit `.ts` extension), so the same code
  compiles with `tsc` whenever `.js` and `.d.ts` output is wanted.

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
│   └── index.ts       public API
└── test/
    ├── fixtures.test.ts     parity with forks/*/fixtures and validation rules
    ├── roundtrip.test.ts    parse(dumps(obj)) == obj, codec, number formatting
    ├── stream.test.ts       random 1–7 character chunks == parse
    ├── truncation.test.ts   truncated outputs
    ├── conformance.test.ts  ../conformance/ runner (skipped if missing)
    └── helpers.ts
```

## Usage

```ts
import { Registry, parse, dumps, specBlock, createReader } from './src/index.ts';

const reg = Registry.load();            // discovers ../forks/*/contract.json
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
res.terminated;    // the stream ended on LF
```

A record is emitted as soon as its line closes with LF. `readRecords(iterable, contrato)`
wraps the same thing as an async generator. The reader uses the same line engine as
`parse`, so the final result is identical no matter how the input is chunked.

Note: if the last line does not end in LF and its last field is still valid
(e.g. clipped text), the record is indistinguishable from a complete one; in that
case `terminated` is `false` and it should be treated as suspect.

## Tests

```
cd ts
npm test
# or
node --experimental-strip-types --no-warnings --test test/*.test.ts
```

The shared conformance suite is read from `../conformance/cases/` (or the path in
`MINI_CONFORMANCE_DIR`); if the folder does not exist, the suite is skipped. The runner
reproduces the logic of `conformance/run_python.py`. The only API mapping: in lenient
mode the reference throws when the document cannot be built (E01); TS returns a
headerless `Document` with E01, and the runner treats it as "not built".

As in the reference, escapes are also validated in lenient mode (E09 and the record
is discarded), an invalid escape in the header is E09 inside validation, and a
rejected line does not reserve its `unique` value.

## Decisions where `js/mini.js`, the Python reference and the SPEC differ

Criterion: if the SPEC decides, follow the SPEC; otherwise follow the Python reference.

| Topic | Python | JS | TS |
|---|---|---|---|
| Empty document in lenient mode | always throws | returns document without `canonical()` | returns `Document` with E01 (SPEC §8) |
| Invalid escape in the header | E09 inside validation (fixed) | raw `MiniError` outside `parse` | E09 inside validation |
| Invalid escape in a record, lenient mode | E09 and record discarded (fixed) | keeps the literal text | E09 and record discarded |
| Rejected line with `unique` value | does not reserve it (fixed) | reserves it | does not reserve it |
| Trailing `\n` on an int/float (`5\n`) | accepts (`$` of `re` + `int()`) | rejects | rejects, E06 (SPEC: `-?[0-9]+`) |
| Unicode digits in numbers | accepts (`\d` Unicode) | rejects | rejects |
| `clave\=valor` in header (lenient) | broken key | E12 | E12 (first unescaped `=`, SPEC §3.2) |
| Whitespace | `str.isspace()` | JS `\s` | `str.isspace()` |
| Contract validation (unknown types, separator, marker, tuples) | strict (E20) | lax | strict (E20) |
| Non-ASCII prefix letters | accepts | rejects | rejects (SPEC §4) |
| Float formatting (1e21, 1e-7) | expands without exponent when exact | `String(x)` | like Python |
| `float` signature/spec with `max: 3.0` | `3.0` | `3` | `3` (JSON.parse cannot tell them apart) |
| List range in `specBlock` with `max: 0` | `∞` | `0` | like Python |
| `__proto__` keys in header/records | kept | lost | kept |

## Limitations

- No type checking in this environment (no `tsc`); the types were written
  for `strict` but have not been verified with the compiler.
- Integers outside ±2^53 lose precision (JavaScript numbers).
- `Registry.load` requires Node (uses `process.getBuiltinModule`); the rest of the
  library does not depend on Node.
