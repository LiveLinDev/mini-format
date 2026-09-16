# Public API benchmark

This is a reproducible serialization comparison using unmodified JSON responses
from public APIs. It measures token counts, not LLM generation quality or runtime
latency. The original hand-authored domain benchmark remains available in
`benchmark/results/`; this corpus evaluates the generated domain toolkit.

| Snapshot | Objects | Nature | Selection |
| --- | ---: | --- | --- |
| DummyJSON products | 194 | Published synthetic test data | Complete endpoint, all fields |
| DummyJSON users | 208 | Published synthetic test data | Complete endpoint, all fields |
| JSONPlaceholder comments | 500 | Published synthetic test data | Complete collection |
| USGS earthquakes | 1,000 | Real historical observations | First 1,000 events chronologically in January 2025 |

The corpus contains 1,902 distinct source IDs within their respective datasets.
No duplicated rows, selected favorable fields, or repeated expansion are used.
The endpoints were selected before token measurements. Do not describe the
synthetic datasets as real customer traffic. Sources, selection rules, fetch
times, byte sizes, and SHA-256 hashes are recorded in `sources.json`; see
`THIRD_PARTY.md` for attribution.

## Reproduce offline

From the repository root, using Python 3.9+ and Node.js 22.14+:

```sh
python -m pip install -e ".[bench]"
python benchmark/public/run.py
```

Snapshots are checked against their hashes before use. Running this command does
not contact the source APIs. It writes `results.json` and `results.csv`; every
format must round-trip to identical JSON values and types or the run fails.
Object key order and the spelling of numerically equal JSON numbers are not
semantically significant. Boolean values are compared separately from numbers.
The runtime and benchmark-script hashes are also recorded with each result.

To intentionally refresh the live snapshots and provenance, run
`python benchmark/public/fetch.py`, then rerun the benchmark. Source data and
counts may change. `python benchmark/public/run.py --baselines-only` can verify
the independent baselines without invoking the .mini domain toolkit.

## Equivalent formats and costs

- **.mini:** A contract is inferred from the entire snapshot, and the generated
  domain encoder/decoder serialize and reconstruct that response. It is a
  fitted serialization workload, not a claim about unseen schemas or model
  accuracy. No external value table may be omitted from the measured document.
  Shared values and repeated-string dictionaries are transmitted in the header
  and included in `tokens`; `mini_without_document_factoring_tokens` also shows
  the size when both optimizations are disabled.
- **TOON:** The official vendored v4.1.1 encoder and strict decoder receive the
  full original JSON, including the response wrapper and metadata.
- **Flat TOON:** Two reversible strategies are evaluated. Both flatten nested
  objects into JSON Pointer columns. The first retains arrays as compact JSON
  cells; the second expands array positions into columns, including nested
  objects inside arrays. Missing values have a reserved marker with string
  escaping, and the shared map preserves container types and empty containers.
  The official encoder/decoder process both candidates and the **smaller output
  token count** is selected; both counts and the selected strategy are published
  in `flattening`. This is not proof that all possible TOON preprocessing
  strategies have been optimized.
- **CSV:** Both reversible flat tables also use RFC 4180 quoting, again selecting
  the smaller output and publishing both counts. A transmitted
  `#meta` sidecar retains the full wrapper metadata. Column type information is
  part of the shared schema; absent, null, empty string, and empty array remain
  distinct. This is CSV plus a documented adapter, not schema-free CSV.
- **JSON:** Both compact and two-space-indented UTF-8 serialization are measured.
- **YAML:** PyYAML block style preserves the original values and types.
- **XML:** A compact typed XML mapping distinguishes objects, arrays, strings,
  numbers, booleans, and nulls. Its decoder is included. This is a documented
  generic mapping rather than an optimized domain-specific XML schema.

All strings are counted by the same `o200k_base` tokenizer, with no trailing
newline added for display. Version details are recorded in the result file.
`tokens` is transmitted output size. `shared_schema_tokens` reports the reusable
contract/map, and `payload_plus_schema_tokens` counts the combined text. The
.mini `prompt_tokens` and `payload_plus_prompt_tokens` expose the actual generated
English prompt separately; they are not added again to the contract count.
The baselines' zero `prompt_tokens` means a dedicated generation prompt was not
measured, not that a model needs no instructions. Input-token prices, caching,
number of requests, and output-token prices determine economic break-even.

Weighted corpus savings use `1 - sum(mini tokens) / sum(baseline tokens)`;
per-dataset counts are also published so the large earthquake dataset cannot
hide another dataset's result. Negative savings are retained. A finite corpus
cannot establish that .mini always beats every format, and a smaller serialized
output does not establish correct or cheaper LLM generation by itself.

## Sample coverage check

The result also reports two deterministic holdouts per dataset, independent of
the full-corpus token comparison. First, every fifth record trains the contract
and the remaining records test it (approximately 20% training). Then the roles
are reversed (approximately 80% training). All fields and values remain intact.
An unobserved schema variation must be rejected explicitly, never silently
coerced or discarded. Such rejections are included in `sample_coverage` with
their error code and path; they do not masquerade as successful round-trips.
More representative samples can cover rare variations, but sample inference
cannot establish every valid value of a business domain.
