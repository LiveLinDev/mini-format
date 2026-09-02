# .mini — forkable, token-efficient notation for LLM structured outputs

[![spec](https://img.shields.io/badge/spec-1.0-2a78d6)](SPEC.md) [![forks](https://img.shields.io/badge/forks-14-1baf7a)](forks/) [![license](https://img.shields.io/badge/license-MIT-lightgrey)](LICENSE)

`.mini` is a line-oriented, positional notation for the **structured outputs of
generative language models in closed domains**: one header line that names a
*contract* and declares the record count, then exactly one record per line with
fields separated by `|`.

```
a|n=2|m=IRT3PL|d=20260603|l=es|t=demo|k=4
i1|L1|Biología|¿Dónde ocurre la fotosíntesis?|cloroplastos*,núcleo,mitocondria,ribosoma|0.9,-1,0.25|1|biología,0.2,low
i2|L3|Matemática|Si 3x+6=18, ¿cuál es x?|4*,6,8,12|1.4,0.2,0.2|3|matemática,0.25,medium
```

Because sender and receiver share the contract, nothing structural is repeated:
no keys, braces, brackets, quotes or indentation. On 14 domains the same data
costs **34 % fewer output tokens than compact JSON** (27–40 %), 37 % fewer than
TOON applied to the nested object, and 7 % fewer than TOON's best tabular case —
within a few percent of raw CSV while keeping typed lists, tuples, a selection
marker, a record count and a validating parser
([benchmark](benchmark/results/summary_12.csv)).

`.mini` is not one format but a **family**: a new domain gets its own contract
(`forks/<prefix>/contract.json`) and the reference implementation interprets it —
parser, serializer, validator, prompt block and fork checker are all derived from
the contract. Fourteen forks ship in this repository (assessment items, quizzes,
flashcards, lecture segments, concept maps, rubrics, surveys, programming
exercises, test cases, user stories, event logs, NER annotations, catalogue rows,
classification outputs).

## Try it

* **Playground** (no install): open [`playground/index.html`](playground/index.html) — validate documents, convert JSON ↔ .mini, compare token counts against JSON/YAML/XML/CSV and the *official* TOON encoder, and design a fork with the wizard.
* **Python**

```bash
git clone https://github.com/<you>/mini-format && cd mini-format
pip install -e .                 # or: PYTHONPATH=src
mini forks                       # list contracts
mini validate forks/a/fixtures/valid.mini
mini to-json forks/tc/fixtures/valid.mini | head
mini prompt log --lang es        # specification block for a generative model
mini check-forks                 # CI check: invariants + fixtures round-trip
```

```python
from minifmt import Registry, parse, dumps
reg = Registry.load()
doc = parse(text, reg.get("a"))          # -> Document; doc.to_canonical() is plain JSON
text = dumps(obj, reg.get("a"))          # canonical JSON -> .mini
```

* **JavaScript**: `js/mini.js` is a dependency-free port (browser + node) that passes the same fixtures as the Python implementation (`node tests/test_js_port.mjs`).

## Create a fork

```bash
mini new-fork quiz2 --from a --add "feedback:str" "level:enum{easy|hard}"
# edit forks/quiz2/contract.json, add fixtures/valid.mini + fixtures/canonical.json
mini check-forks
```

Five invariants keep every fork parsable by construction — one line = one
record; header with prefix and `n`; inherited fields never change; new fields
only at the tail; fixtures round-trip. See [FORKING.md](FORKING.md) and
[CONTRIBUTING.md](CONTRIBUTING.md). A fork is **data, not code**: to
contribute one, open a pull request with a folder under `forks/`.

## Repository layout

| Path | Content |
|---|---|
| `SPEC.md` | Specification 1.0 (grammar, escaping, types, error codes, forking protocol) |
| `src/minifmt/` | Reference implementation (Python ≥ 3.9, no dependencies) + `mini` CLI |
| `js/mini.js` | JavaScript port |
| `forks/` | 14 contracts with fixtures and READMEs; `registry.json` |
| `benchmark/` | Token benchmark (8 formats × 14 domains × 6 sizes × 2 tokenizers), official TOON encoder bridge, figures |
| `generative/` | Generative validation protocol, raw model outputs, results |
| `playground/` | Single-file interactive playground (GitHub Pages ready) |
| `tests/` | Python and JS conformance tests |

## Reproduce the experiments

```bash
python benchmark/make_forks.py        # regenerate contracts + fixtures (idempotent)
python benchmark/run_benchmark.py     # tokens.csv, summary_12.csv, roundtrip.csv (≈30 s)
python generative/run_eval.py         # re-evaluate the archived model outputs
python generative/extra_experiments.py# ablation, break-even, truncation recovery
python benchmark/make_figures.py      # figures for the paper
python -m unittest discover -s tests  # 25 tests incl. 4 000 fuzzed round-trips
node tests/test_js_port.mjs           # cross-implementation conformance
```

Token counting uses `tiktoken` when installed and otherwise an exact
pure-Python BPE over the vendored official `o200k_base` / `cl100k_base` rank
files (`benchmark/vocab/`, sha256 verified); both reproduce the published
counts to the token. TOON is encoded with the official reference implementation
(v4.1.1, spec 4.1) vendored under `benchmark/toon_ref/vendor` and run through
Node ≥ 22 type stripping — no npm install needed.

## Citation

> A. E. J. Palma Obispo and E. J. Palomino Santa Cruz, ".mini: a forkable, token-efficient notation for structured outputs of generative models," Universidad Peruana de Ciencias Aplicadas, 2026.

Advisors: Fidel Eugenio García Rojas (specialised), Ronald Mejía Tarazona (methodological).

## License

MIT. Vendored third-party material keeps its own license: TOON reference implementation (MIT, Johann Schopplich), tokenizer rank files (MIT, OpenAI / gpt-tokenizer).
