# Experiments V1 (token efficiency) and V4 (cost model)

Both experiments are deterministic and **do not call any language model**: they
serialize synthetic data, count tokens with local tokenizers and combine those
counts with published prices.

```bash
python experiments/v1_tokens/run.py    # ≈ 2 min: tokens, savings, instruction, break-even in tokens, figures
python experiments/v4_costos/run.py    # < 10 s: costs, annual savings, monetary break-even (runs V1 if missing)
```

Requirements: those of the benchmark (`tiktoken` or the vocabularies in `benchmark/vocab`,
PyYAML, `regex`, Node ≥ 22 for the official TOON encoder) plus `numpy` and
`matplotlib`. They do not modify `benchmark/` or `src/`; they only import them.

| Path | Content |
|---|---|
| `comun.py` | seeded data generator, tokenizers, bootstrap, break-even point interpolation |
| `v1_tokens/run.py`, `v1_tokens/instruccion.py` | V1 experiment and instruction blocks (.mini and JSON Schema) |
| `v1_tokens/results/*.csv` | V1 raw data and summaries |
| `v1_tokens/results/instrucciones_muestra/` | exact instruction texts measured (`a` and `cls` families) |
| `v4_costos/precios.json` | prices per million tokens with URL and retrieval date |
| `v4_costos/run.py`, `v4_costos/results/*.csv` | V4 experiment and its results |
| `*/figures/*.png` | figures (text in Spanish) |

## 1. Baseline reproduction

`v1_tokens/run.py` re-serializes the 14 domains with n = 12 and the original protocol
(`domains.expand`), counts with `o200k_base` and compares cell by cell against
`benchmark/results/summary_12.csv`. In addition, `python benchmark/run_benchmark.py`
was run on this tree and `git status` came out clean (the published CSVs regenerate
identically).

| Token change of .mini (mean of 14 domains) | Published | Reproduced | Per-domain range (reproduced) |
|---|---|---|---|
| .mini vs compact JSON | −33.8% | −33.8% | −39.5 to −27.3% |
| .mini vs TOON (official, as-is) | −37.4% | −37.4% | −48.3 to −2.3% |
| .mini vs flattened TOON | −7.0% | −7.0% | −18.6 to 0.0% |
| .mini vs flattened CSV | +5.0% | +5.1% | −8.4 to +14.5% |

All 168 cells (tokens per format and percentages per domain) match exactly
(`linea_base_n12.csv`). The only difference is rounding in the CSV aggregate: the
published 5.0% is the mean of the percentages already rounded to one decimal (5.04%);
the unrounded mean is 5.06%.

## 2. V1 protocol

* **Domains:** the 14 families in `forks/`.
* **Sizes:** n ∈ {1, 5, 10, 25, 50, 100, 250} records per document.
* **Data:** the existing generators only have 12 base records per domain. Two
  variants are used:
  * `muestreo` (main): identifiers and header from `domains.expand(prefix, n)`;
    each record's content comes from blocks of 12 base records shuffled with
    `random.Random("20260914:<prefix>")`. It keeps n = 1 from always being the first
    record and the order from being periodic.
  * `ciclo` (sensitivity): exactly `domains.expand`, the published protocol.
* **Formats:** indented JSON, compact JSON, YAML, XML, flattened CSV, official TOON
  (as-is and flattened, v4.1.1 reference encoder in `benchmark/toon_ref`) and .mini.
* **Tokenizers:** `o200k_base` and `cl100k_base` (tiktoken). Third tokenizer:
  `r50k_base` (GPT-2), loaded from `whisper/assets/gpt2.tiktoken`, which was already
  installed and whose sha256 (`306cd27f…`) matches the official `r50k_base` hash
  in `tiktoken_ext`. Nothing was downloaded. `~/.cache/huggingface` only holds
  `sentence-transformers/clip-ViT-B-32`: its CLIP tokenizer lowercases everything and
  normalizes whitespace, so it is useless for measuring text formats.
* **Metrics:** tokens per document and per record; savings = 1 − T(.mini)/T(format)
  per domain; mean, median, range and 95% percentile bootstrap CI (10,000 resamples
  of the 14 domains, seed 20260914). Round-trip: `minifmt.roundtrip_ok`
  (object → .mini → object, plus text stability) for .mini and the official
  decoder for TOON.

**Round-trip:** 196 .mini documents and 392 TOON (2 variants × 14 domains × 7 sizes);
zero failures.

### 2.1 .mini savings by tokenizer (n = 100, `muestreo` variant)

Mean over 14 domains [95% CI]. A positive value means .mini uses fewer tokens.

| .mini vs | o200k_base | cl100k_base | r50k_base (GPT-2) |
|---|---|---|---|
| Indented JSON | 59.3 [56.8; 61.8] | 58.2 [55.4; 61.0] | 73.6 [71.0; 76.1] |
| Compact JSON | **34.8 [32.7; 36.9]** | 32.7 [30.4; 35.1] | 30.4 [27.9; 33.0] |
| YAML | 45.6 [42.6; 48.8] | 44.6 [41.4; 47.9] | 42.2 [39.2; 45.1] |
| XML | 63.1 [60.1; 66.0] | 61.8 [58.3; 65.2] | 67.4 [63.6; 70.8] |
| Flattened CSV | −2.6 [−4.7; −0.4] | −3.3 [−5.2; −1.2] | −1.0 [−2.3; 0.4] |
| TOON (official, as-is) | 37.4 [28.7; 44.1] | 36.1 [27.3; 43.0] | 42.9 [34.1; 50.0] |
| Flattened TOON (tabular) | 2.0 [−0.1; 4.4] | 1.3 [−0.8; 3.6] | 3.3 [1.6; 5.0] |

Medians, ranges and the other sizes are in `v1_tokens/results/ahorro_resumen.csv`.
Against compact JSON, per-domain savings run from 27.9% to 41.7% (o200k, n = 100).

### 2.2 How savings change with n (o200k_base, `muestreo`)

| .mini vs | n=1 | n=5 | n=10 | n=25 | n=50 | n=100 | n=250 |
|---|---|---|---|---|---|---|---|
| Indented JSON | 55.3 | 57.9 | 58.5 | 59.1 | 59.2 | 59.3 | 59.3 |
| Compact JSON | 27.0 | 32.5 | 33.5 | 34.4 | 34.6 | 34.8 | 34.9 |
| YAML | 36.9 | 43.1 | 44.3 | 45.3 | 45.5 | 45.6 | 45.7 |
| XML | 50.3 | 59.8 | 61.6 | 62.6 | 62.9 | 63.1 | 63.2 |
| Flattened CSV | −26.2 | −8.6 | −5.5 | −3.6 | −3.0 | −2.6 | −2.4 |
| Official TOON | 34.8 | 37.0 | 37.3 | 37.5 | 37.4 | 37.4 | 37.4 |
| Flattened TOON | 30.5 | 13.1 | 8.1 | 4.3 | 2.8 | 2.0 | 1.6 |

* Against formats that repeat structure in every record (JSON, YAML, XML), savings
  **grow with n** and stabilize from n ≈ 25: the .mini header amortizes and the
  per-record saving is constant (linear fit T(n) = a + b·n with R² ≥ 0.9999).
* Against tabular formats (CSV, flattened TOON), .mini's advantage **shrinks with
  n**: with small documents the CSV/TOON column header weighs; with large documents
  both converge to ≈ 40 tokens per record (.mini 40.1; flattened TOON 41.0;
  CSV 39.3 at n = 100). CSV carries no document metadata or types, so its header
  is not comparable (at n = 1, CSV omits the whole .mini header).
* **`ciclo` vs `muestreo` sensitivity:** at n = 100 the means agree to ±0.1 points;
  at n = 1 they differ by at most 1.3 points (which record is used changes).
* **Tokenizer sensitivity:** against compact JSON, cl100k gives 2.1 points less than
  o200k and r50k 4.4 points less; against indented JSON r50k gives much more (73.6%)
  because GPT-2 encodes each indentation space separately (8 spaces = 8 tokens in
  r50k versus 1 in o200k).

Figures: `v1_tokens/figures/fig1_ahorro_vs_n.png`, `fig2_tokens_por_registro.png`,
`fig3_ahorro_por_dominio_n100.png`.
## 3. Instruction overhead and break-even point

Blocks measured per family and language (`v1_tokens/instruccion.py`):

* `mini_spec`: `spec_block(contract, lang)` unchanged; `mini_spec_ejemplo`: with a 1-record example.
* `json_schema`: instruction sentence + JSON Schema derived from the contract (compact; with the
  same types, enumerations, ranges, arities and descriptions as the .mini block;
  without `additionalProperties:false`, which favors JSON).
* `json_schema_ejemplo`: schema + the same 1-record example in compact JSON.
* `json_ejemplo`: sentence + only the JSON example (minimal instruction, the worst case for .mini).

Mean instruction tokens (14 domains):

| Tokenizer / language | mini_spec | mini_spec_ejemplo | json_schema | json_schema_ejemplo | json_ejemplo |
|---|---|---|---|---|---|
| o200k / es | 416 | 495 | 289 | 394 | 137 |
| o200k / en | 372 | 450 | 287 | 391 | 134 |
| cl100k / es | 441 | 523 | 280 | 385 | 138 |
| cl100k / en | 370 | 450 | 277 | 380 | 132 |

The .mini specification is longer than the schema in 12 of 14 families. The exceptions
are `a` and `q`, with tuple header and lists: in `a` the schema is longer in both
languages; in `q` it is longer in English, and in Spanish .mini exceeds it by only 17 tokens (o200k).

**Token break-even point** (`equilibrio_tokens*.csv`): smallest n per call with
ΔO(n) = T_JSON(n) − T_.mini(n) ≥ ΔI = I_.mini − I_JSON, interpolated over the measured grid.
Compact JSON output; o200k; median [min; max] of 14 domains:

| .mini instruction vs JSON | es | en |
|---|---|---|
| mini_spec vs json_schema | 7.8 [1; 13.7] | 5.6 [1; 10.0] |
| mini_spec_ejemplo vs json_schema_ejemplo | 6.7 [1; 12.5] | 4.5 [1; 8.8] |
| mini_spec vs json_ejemplo | 14.8 [5.8; 25.4] | 12.7 [4.7; 21.8] |
| mini_spec_ejemplo vs json_ejemplo | 19.0 [9.3; 29.8] | 16.8 [8.2; 26.1] |

With cl100k the medians rise (10.2 and 17.4 in Spanish for rows 1 and 3); with r50k,
to 14.0 and 21.3.

**Monetary break-even point** (`v4_costos/results/equilibrio_dinero.csv`,
`equilibrio_curva_razon.csv`): the condition becomes p_out·ΔO(n) ≥ p_in_ef·ΔI; only
the ratio ρ = p_in_ef/p_out matters. Without cache, ρ = 0.12–0.25 in the models
consulted and the median n* drops to **1.0–1.9 records** (mini_spec vs json_schema) or 1.7–3.6
(vs json_ejemplo); the worst domain needs at most 3.2 and 6.1 records. **With prompt
cache** (ρ = 0.005–0.02) the instruction pays off from the first record in every
family. Cache assumption: steady state, every call reads the instruction from cache;
the initial write (1.25× input at Anthropic), hourly storage (Google), cache lifetime
and minimum cacheable tokens — which may require the full system prompt to exceed a
threshold — are not counted. Groq publishes no cache price, so the cached scenario
uses the regular price.

## 4. V4 — cost model

`costo_llamada = I_f·p_in_ef + O_f(k)·p_out`, `costo_1000 = (1000/k)·costo_llamada`, mean
of 14 domains, o200k tokens, Spanish instruction (`mini_spec` for .mini and `json_schema`
for JSON). Only the part of the cost that **depends on the format** counts: the task's
input content is the same for every format and stays out.

Prices (USD per million tokens) read on the official pages on **2026-09-15**. The
session started Sep 14, but the reading happened after midnight; see `precios.json`
for detail.

| Provider | Model | Input | Cached input | Output | Source |
|---|---|---|---|---|---|
| OpenAI | GPT-5.4 (short context) | 2.50 | 0.25 | 15.00 | developers.openai.com/api/docs/pricing |
| OpenAI | GPT-5.4 mini | 0.75 | 0.075 | 4.50 | same |
| OpenAI | GPT-5 mini | 0.25 | 0.025 | 2.00 | same |
| Anthropic | Claude Opus 5 | 5.00 | 0.50 | 25.00 | platform.claude.com/docs/en/about-claude/pricing |
| Anthropic | Claude Sonnet 5 | 2.00 | 0.20 | 10.00 | same |
| Anthropic | Claude Haiku 4.5 | 1.00 | 0.10 | 5.00 | same |
| Google | Gemini 3.5 Flash | 1.50 | 0.15 | 9.00 | ai.google.dev/gemini-api/docs/pricing |
| Google | Gemini 3.1 Pro Preview (≤200k) | 2.00 | 0.20 | 12.00 | same |
| Google | Gemini 2.5 Flash | 0.30 | 0.03 | 2.50 | same |
| Groq | GPT OSS 120B | 0.15 | not published | 0.60 | console.groq.com/docs/models |
| Groq | GPT OSS 20B | 0.075 | not published | 0.30 | same |
| DeepSeek | DeepSeek V4.1 Flash (peak hour) | 0.30 | 0.006 | 1.20 | api-docs.deepseek.com/quick_start/pricing |

**Cost per 1,000 records and annual .mini savings vs compact JSON** (25 records per call):

| Model | JSON USD/1000 | .mini USD/1000 | Savings | Annual savings 10k reg. | 1 million | 100 million | Savings with cache |
|---|---|---|---|---|---|---|---|
| GPT-5.4 | 0.9601 | 0.6559 | 31.7% | 3.04 | 304 | 30,415 | 33.8% |
| GPT-5.4 mini | 0.2880 | 0.1968 | 31.7% | 0.91 | 91 | 9,124 | 33.8% |
| GPT-5 mini | 0.1270 | 0.0861 | 32.3% | 0.41 | 41 | 4,098 | 33.9% |
| Claude Opus 5 | 1.6097 | 1.1071 | 31.2% | 5.03 | 503 | 50,267 | 33.7% |
| Claude Sonnet 5 | 0.6439 | 0.4428 | 31.2% | 2.01 | 201 | 20,107 | 33.7% |
| Claude Haiku 4.5 | 0.3219 | 0.2214 | 31.2% | 1.01 | 101 | 10,053 | 33.7% |
| Gemini 3.5 Flash | 0.5760 | 0.3935 | 31.7% | 1.82 | 182 | 18,249 | 33.8% |
| Gemini 3.1 Pro Preview | 0.7680 | 0.5247 | 31.7% | 2.43 | 243 | 24,332 | 33.8% |
| Gemini 2.5 Flash | 0.1587 | 0.1074 | 32.3% | 0.51 | 51 | 5,129 | 33.9% |
| GPT OSS 120B (Groq) | 0.0390 | 0.0271 | 30.6% | 0.12 | 12 | 1,191 | 30.6%* |
| GPT OSS 20B (Groq) | 0.0195 | 0.0135 | 30.6% | 0.06 | 6 | 596 | 30.6%* |
| DeepSeek V4.1 Flash | 0.0780 | 0.0541 | 30.6% | 0.24 | 24 | 2,382 | 34.0% |

\* no cache price published. Annual amounts in USD, without cache.

* The savings **percentage** depends almost only on the input/output ratio and the call
  size; the **amount** scales with the output price.
* With k records per call, savings vs compact JSON without cache run from −2.6% to
  9.2% at k = 1 (with a single record and no cache, .mini comes out 2.6% more expensive on models
  with input/output ratio 0.25: GPT OSS and DeepSeek; with cache, 24–27% savings), 25.5–29.3% at k = 10, 30.6–32.3% at k = 25 and 33.4–33.9% at k = 100.
* Against the other formats (k = 25, no cache): indented JSON + JSON Schema 55.5–57.0%;
  counting output only because their instruction was not measured, YAML 44.9%, XML 61.2%,
  official TOON 41.4%, flattened TOON 4.6% and CSV −2.6%
  (`ahorro_anual.csv`).

Figures: `v4_costos/figures/fig1_costo_1000_registros.png`, `fig2_ahorro_anual_1M.png`,
`fig3_equilibrio_vs_razon_precios.png`.

## 5. Assumptions and threats to validity

**Construct validity**
* Token counts are measured on **ideal** documents produced by serializers, not real model
  outputs. A model may add text, errors or retries; V2/V3 evaluate that with real
  generation and are not included here.
* Output is compared against the equivalent instruction, but the quality or validity each
  instruction achieves is not measured. A JSON Schema used with *structured outputs* may be
  billed or processed differently depending on the provider.
* CSV and flattened TOON lose metadata (CSV) or need schema flattening; they are not
  complete semantic equivalents.

**Internal validity**
* Counts are exact for `o200k_base`, `cl100k_base` and `r50k_base`. For the models,
  `o200k_base` is exact on GPT-5 mini (tiktoken assigns it that vocabulary) and on gpt-oss
  (`o200k_harmony`, identical text encoding, verified). On GPT-5.4 and GPT-5.4 mini o200k is
  **assumed**, because tiktoken 0.13 does not publish the mapping. For **Anthropic, Google and
  DeepSeek the tokens are an approximation**: each provider uses its own tokenizer, and
  Anthropic's page warns that Claude 4.7 and later generate around 30% more tokens for the
  same text. The savings percentage is expected to be more stable than the absolute amount
  (the three measured tokenizers vary 4.4 points against compact JSON), but this is unverified.
* Break-even point: linear interpolation over n ∈ {1, 5, 10, 25, 50, 100, 250}; an n* ≤ 1
  value is reported as 1.

**External validity**
* Each domain has only 12 base records; with n > 12 the content repeats and only the
  identifiers change. The curves measure serialization length, not semantic diversity.
  Domains with longer texts per record will show less relative savings, and domains with
  short fields, more.
* There are 14 domains and seven are in Spanish: the bootstrap CI describes variation across
  these domains, not a population of domains.
* Prices change often (e.g. Google announces increases for 2027-01-01 on some models).
  Results hold for the retrieval date; just edit `precios.json` and re-run V4.
* The cached scenario is an optimistic bound: it ignores writing, storage, lifetime
  and minimum cacheable size.

**Pending**
* Third tokenizer from a **current** open language model (Llama 3, Qwen, Mistral):
  none is cached locally and nothing was downloaded. `r50k_base` (GPT-2, open model) serves
  as the third tokenizer, but it is from 2019 and does not represent the 128k-to-200k-token
  vocabularies of current models.
* Groq cache price (not published) and Mistral prices (not consulted).
