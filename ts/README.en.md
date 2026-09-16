# @mini-format/core — `.mini` TypeScript library

Software release 1.1.0. Modular, typed TypeScript implementation of the `.mini`
core notation (SPEC 1.0):
parser, serializer, specification block for prompts, family (fork) registry and a
streaming read API for token-by-token model responses. No dependencies.

Includes the fourteen core families. Contracts adapted from JSON samples by
`mini build` use a separate `mini-domain/1` profile and their generated Python
parser; this library does not interpret that profile. See the
[builder guide](https://mini-format.pmoluna.com/en/docs/build/) and
[generated profile specification](https://mini-format.pmoluna.com/en/docs/profile/).

Authors: A. E. J. Palma Obispo, E. J. Palomino Santa Cruz (UPC). MIT license.

## Install the package

Requires Node.js ≥ 22.6. Download `mini-format-core-1.1.0.tgz` from Downloads or
extract it from the toolkit ZIP. Install the local file:

```sh
npm install --offline --ignore-scripts --no-audit --no-fund ./mini-format-core-1.1.0.tgz
```

The archive contains compiled JavaScript ESM in `dist/`, contracts for all fourteen
families and TypeScript sources for types. Import it as `@mini-format/core`:
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
`ts/dist/`. The distribution includes typed source files; this step does not
generate `.d.ts` declarations.

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
import { Registry, parse, dumps, specBlock, createReader } from '@mini-format/core';

const reg = Registry.load();            // loads the families bundled with the package
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
res.terminated;    // the stream ended on LF
```

A record is emitted as soon as its line closes with LF. `readRecords(iterable, contrato)`
wraps the same thing as an async generator. The reader uses the same line engine as
`parse`, so the final result is identical no matter how the input is chunked.

Note: if the last line does not end in LF and its last field is still valid
(e.g. clipped text), the record is indistinguishable from a complete one; in that
case `terminated` is `false` and it should be treated as suspect.

## Tests and types

```
cd ts
npm test
# or
node --experimental-strip-types --no-warnings --test test/*.test.ts
```

The public API and its imported modules pass strict checking with TypeScript
7.0.2. Run this from the repository root:

```sh
npx --yes --package typescript@7.0.2 tsc --noEmit --strict --module NodeNext --moduleResolution NodeNext --target ES2022 --allowImportingTsExtensions ts/src/index.ts
```

This command may download the compiler if it is not cached; installing and
running the `.tgz` does not require it. Node's type stripping does not replace
this check.

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

- Integers outside ±2^53 lose precision (JavaScript numbers).
- `Registry.load` requires Node (uses `process.getBuiltinModule`); the rest of the
  library does not depend on Node.
