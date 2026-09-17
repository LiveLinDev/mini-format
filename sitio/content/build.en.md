# Build your toolkit

`mini build` turns JSON samples into a domain contract and executable Python tools. The contract ships with your application; the prompt tells the model how to write compact responses.

```bash
mini build phones.json catalog.json --prefix phone --out .mini
```

## Generated files

| File | Purpose |
|---|---|
| `contract.json` | Field order, types, encoding and domain structure. |
| `schema.json` | Reference JSON schema inferred from samples. |
| `prompt.es.md`, `prompt.en.md` | Model format instruction. |
| `parser.py` | Encodes JSON and reconstructs original JSON from `.mini`. |
| `validator.py` | Checks structure, types and records. |
| `repair.py` | Applies safe corrections and returns diagnostics. |
| `example.json`, `example.mini` | Verifiable round-trip example. |
| `manifest.json`, `README.md` | Profile, inventory and usage guide. |

## Representative samples

Inference discovers observed structure; it cannot guess business rules. Include missing and present fields, nulls, empty and populated lists, nested objects and every type you accept. Review the generated contract before integration. Keep a version of the toolkit per domain so every response remains reproducible.

A field appearing only once may be optional. A value shared by every example does not automatically become a business rule. Frequent values may receive a reversible encoding without banning new values.

## Two explicit profiles

The **SPEC 1.1 base profile** retains the 14 families and their Python, JavaScript and TypeScript parsers. The **generated `mini-domain/1` profile** adds the mapping required to preserve JSON structures and adapt encoding to the domain. Use its `parser.py`, not a base-profile parser that does not know the generated contract.

## Workflow

```bash
python .mini/parser.py encode input.json
python .mini/parser.py decode response.mini
python .mini/validator.py response.mini
python .mini/parser.py diagnose response.mini
python .mini/repair.py response.mini --out corrected.mini
```

`decode` prints application-ready JSON. `diagnose` explains failures; `repair` preserves content and applies deterministic changes only. To explicitly accept the number of received records: `python .mini/repair.py response.mini --out corrected.mini --fix-count`.

A semantically incorrect value has no universal repair: use the report and retry prompt to ask the model for a correction. Never silently discard data or fill in unknown information.

To apply per-line corrections, save an object such as `{"2": "corrected .mini line"}` in `corrections.json` and run:

```bash
python .mini/parser.py apply response.mini corrections.json --out corrected.mini
```

Only lines diagnosed as invalid may be replaced. The complete document is validated again before it is written.

## Measure complete savings

Compare identical JSON with the same tokenizer. Count contract instructions, outputs and retries. Reuse amortizes the contract; small batches or non-repetitive data may not offset it. Read the [methodology](/docs/metodologia/) and repeat the measurement with your samples.
