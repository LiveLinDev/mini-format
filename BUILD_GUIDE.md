# From JSON samples to a production workflow

[Español](BUILD_GUIDE.es.md) · [Domain profile](DOMAIN_PROFILE.md)

## 1. Install locally

Extract the toolkit ZIP from the site's Downloads section. With Python 3.9+:

```sh
python -m pip install --no-index mini_format-1.2.0-py3-none-any.whl
mini build examples/phones.json examples/phones-extra.json --prefix phone --out .mini
```

The builder reads local files. It does not send samples to a model or external
service and does not require an API key, Git or a hosted repository. A build
refuses to overwrite a nonempty output directory.

## 2. Use representative samples

Pass complete JSON documents, not fragments with metadata removed. Include the
different shapes you expect: optional members, nulls, empty arrays, Unicode,
different numeric values and nested objects. Sample order determines field order.
Missing members are different from `null`, `false`, `0` and `""`.

Root arrays are treated as record collections. For an object wrapping several
arrays, automatic selection chooses the object collection with the largest total
record count across the samples, among paths present in every sample. Select the
intended collection explicitly when needed:

```sh
mini build first.json second.json --prefix product --records /data/products --out .mini-products
```

`--records` is a JSON Pointer through object members (`~1` for `/`, `~0` for `~`).
Wrapper metadata and nested lists are preserved. A scalar or object without a
selected record array is still supported as a single-record document.

## 3. Keep the generated bundle together

| File | Purpose |
|---|---|
| `contract.json` | Positional schema, selected collection and contract fingerprint |
| `schema.json` | JSON Schema 2020-12 for integration with other validators |
| `prompt.en.md`, `prompt.es.md` | Model instructions and a small encoding example |
| `parser.py` | Standalone encoder, strict decoder, diagnosis and selective repair |
| `validator.py`, `repair.py` | Convenient validation and safe-repair commands |
| `example.json`, `example.mini` | Matching sample input/output |
| `manifest.json` | Sample counts, filenames and generated-file SHA-256 checksums |

Review examples and prompts before sharing: they can contain your original
private data. Keep the matching contract with the runtime. The fingerprint detects
an accidental schema mismatch; it is not an authentication mechanism.

## 4. Integrate with your model

Add `prompt.en.md` or `prompt.es.md` to your model's instructions alongside your
original task. State the expected record count and business requirements. Receive
plain `.mini` output and decode it using the generated runtime:

```sh
python .mini/parser.py decode response.mini --out response.json
python .mini/validator.py response.mini
```

The runtime uses only Python's standard library; mini-format does not need to be
installed on the receiving machine. For an import-based integration:

```python
import importlib.util
from pathlib import Path

spec = importlib.util.spec_from_file_location("phone_parser", ".mini/parser.py")
parser = importlib.util.module_from_spec(spec)
spec.loader.exec_module(parser)
text = Path("response.mini").read_text(encoding="utf-8")
data = parser.loads(text)  # raises DomainError; never returns invalid JSON
```

Before calling a paid model, test serialization with your own JSON:

```sh
python .mini/parser.py encode input.json --out input.mini
python .mini/parser.py decode input.mini --out restored.json
```

## 5. Detect and repair without guessing

```sh
python .mini/parser.py diagnose response.mini
python .mini/repair.py response.mini --out repaired.mini
```

Safe automatic repair removes a UTF-8 BOM, normalizes CRLF and unwraps a complete
Markdown code fence. It does not fabricate missing fields, choose business values
or silently discard records. A failed repair exits nonzero and does not write an
output file. Diagnostics identify physical line numbers, errors, valid lines and
recoverable record counts.

If record lines remain invalid, use the returned `repair_prompt`, original task,
original response and contract with your model or a human reviewer. Save the
returned JSON map of line numbers to corrected `.mini` lines as `corrections.json`:

```sh
python .mini/parser.py apply response.mini corrections.json --out corrected.mini
```

Only diagnosed invalid lines may change. The complete merged document must pass
validation before a file is written. Header/schema failures require checking the
whole response. `--fix-count` is an explicit opt-in to accept the records actually
present; it cannot prove that a truncated model response is complete.

Exit status: `0` success, `1` invalid diagnosis/unresolved repair, `2` input,
contract or command failure. Use `--out` to write UTF-8 files safely on Windows.

## 6. Evolve and measure

Unseen fields in inferred objects or incompatible types fail clearly. Rebuild into a new directory
with the old and new representative samples, then update prompt and parser
together. Null-only and mixed-type fields remain open JSON because the samples
do not establish a narrower type. Samples infer shape, not business constraints
such as stock limits, unique identifiers or semantic correctness.

An empty object remains a closed object with no known members; add samples with
its intended fields before using it with populated objects. An array observed
only empty has open JSON items, and mixed-type nodes accept arbitrary JSON rather
than enforcing a union of the observed types. Review `schema.json` to decide
whether that permissiveness matches your application's validation needs.

Compare against your best existing format using the actual tokenizer and complete
request: reusable prompt/schema cost plus generated output. Measure model accuracy,
retry rate and latency in your own integration. Public token benchmarks demonstrate
serialization efficiency, not that every model generates this notation perfectly.

The generated `mini-domain/1` profile is supported by the Python toolkit. The
separate TypeScript/browser core supports the fourteen SPEC 1.1 families; do not
pass generated-domain files to that parser. See [profile compatibility](DOMAIN_PROFILE.md).
