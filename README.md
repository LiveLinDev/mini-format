# mini-format

Build a compact output format for your JSON domain. Supply representative samples
once; get a reusable contract, prompts, parser, validator and repair tools. Ask
your model for `.mini`, then recover your original JSON structure.

[Website](https://mini-format.pmoluna.com) · [Documentation](https://mini-format.pmoluna.com/docs/) · [Downloads](https://mini-format.pmoluna.com/downloads/) · [Español](README.es.md)

## Download and install

Download the [complete toolkit](https://mini-format.pmoluna.com/downloads/mini-format-1.1.0.zip)
and extract it. Python 3.9 or later is required; the wheel installs offline without
runtime dependencies:

```bash
python -m pip install --no-index mini_format-1.1.0-py3-none-any.whl
mini build examples/phones.json examples/phones-extra.json --prefix phone --out .mini
```

Or install directly from the site:

```bash
python -m pip install https://mini-format.pmoluna.com/downloads/mini_format-1.1.0-py3-none-any.whl
```

The ZIP contains the Python wheel, a Node package, examples, documentation and the
MIT license. [SHA-256 checksums](https://mini-format.pmoluna.com/downloads/SHA256SUMS.txt)
and [source code](https://mini-format.pmoluna.com/downloads/mini-format-1.1.0-source.zip)
are available on the same site. No GitHub account is required.

## Build once, reuse

`mini build` combines samples to infer field order, types, nested objects, arrays
and optional values. More representative examples cover more cases in your domain;
samples cannot guarantee that every possible future value has been observed.

The generated `.mini/` folder includes a contract, English/Spanish prompts, a
standalone Python parser, validation, diagnostics, repair tools and example
round-trips. The receiving system can run the parser without installing mini-format.

```bash
mini from-json examples/phones.json --contract .mini/contract.json --out phones.mini
mini validate phones.mini --contract .mini/contract.json
mini to-json phones.mini --contract .mini/contract.json --out phones.roundtrip.json
mini diagnose phones.mini --contract .mini/contract.json
```

Put the generated prompt in your model instructions. Repair fixes only unambiguous
formatting and prepares targeted regeneration for unresolved errors; it never
invents missing business data. See the [integration guide](BUILD_GUIDE.md).

## Python and TypeScript

Fourteen predefined core families remain available for assessments, flashcards,
lessons, rubrics, surveys, code exercises, logs, catalogues and other domains.

```python
from minifmt import Registry, parse, dumps
contract = Registry.load().get("a")
document = parse(text, contract)
canonical_json = document.to_canonical()
```

Node 22.6+ can install the compiled ESM package, including TypeScript source types
and the same families:

```bash
npm install ./mini-format-core-1.1.0.tgz
```

```javascript
import { Registry, parse, createReader } from '@mini-format/core';
const contract = Registry.load().get('a');
const document = parse(text, contract);
```

A dependency-free browser port is in `js/mini.js`. The generated domain toolkit
uses its own standalone runtime and explicit `mini-domain/1` profile. Existing
core families keep [SPEC 1.0](SPEC.md); see the [domain profile](DOMAIN_PROFILE.md)
and [forking protocol](FORKING.md).

## Measured efficiency

A shared contract removes repeated field names. Savings depend on record shape,
escaping, repeated values and tokenizer. The [public benchmark](benchmark/public/README.md)
compares complete, reversible JSON against compact/pretty JSON, official nested
and flattened TOON, YAML, XML and CSV, reporting contract/prompt overhead separately.
The [original 14-domain results](benchmark/results/summary_12.csv) remain a separate
core-format experiment. Token savings alone do not establish model accuracy,
lower latency or an advantage for every possible JSON document.

## Development

Extract the source archive, then run:

```bash
python -m pip install -e ".[bench,release]"
python -m unittest discover -s tests
python conformance/run_python.py
node tests/test_js_port.mjs
node --experimental-strip-types --test ts/test/*.test.ts
mini check-forks
python tools/build_release.py --output dist
python sitio/construir.py
```

Release construction requires Node 22.13+. The core and generated Python parser
use the standard library. The optional `bench` extra installs exact tokenization
(`tiktoken` and a local `regex` fallback), YAML and plotting; `release` installs
build tools. See [contributing](CONTRIBUTING.md) and [changes](CHANGELOG.md).

## Research and license

A. E. J. Palma Obispo and E. J. Palomino Santa Cruz, Universidad Peruana de Ciencias
Aplicadas, 2026. Advisors: Jorge Luis Mayta Guillermo and Ronald Mejía Tarazona.

MIT. Tokenizer vocabularies, official TOON 4.1.1 and public datasets retain their
own licenses and provenance recorded alongside each resource.
