# Contributing

Thanks for helping `.mini` grow. There are three kinds of contribution.

## A new fork (most welcome)

1. Read [FORKING.md](FORKING.md).
2. `mini new-fork <prefix> [--from <parent>] --add ...` and edit the contract.
3. Add `fixtures/valid.mini`, `fixtures/canonical.json`, `fixtures/escaping.mini`, `fixtures/escaping.json` and the negative cases.
4. Write `README.md` (purpose, layout table, example) — `benchmark/make_forks.py::write_readme` shows the expected shape.
5. Run `mini check-forks`, `python -m unittest discover -s tests`, `node tests/test_js_port.mjs`.
6. Open a PR titled `fork: <prefix> — <name>`. Add your fork to the benchmark by giving it 12 base records in `benchmark/domains.py` (optional but appreciated).

Prefix naming: short, lowercase, unique. Do not reuse a prefix with an
incompatible layout — that is a new prefix.

## Implementation changes

Both implementations (Python `src/minifmt`, TypeScript `ts/src`) must stay in
agreement: any change to the rules needs the mirror change in the other
implementation, a spec update in `SPEC.md` and `SPEC.es.md`, a conformance case
in `conformance/generate.py` and, when the change is a decision, an ADR in
`docs/adr/`. `js/mini.js` (the playground engine) is generated from `ts/src` with
`node --no-warnings tools/build_js.mjs`; never edit it by hand. Error codes are
part of the public contract; do not renumber them.

## Benchmark and validation

Please report tokenizer, corpus, serializers and baseline for any new number.
Keep raw model outputs under `generative/raw/` so every figure stays
traceable. TOON must be produced with the vendored official encoder.

## Code of conduct

Be kind, precise and reproducible.
