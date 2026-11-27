---
name: mini-format
description: Serialize, validate, repair, and constrain LLM structured outputs using .mini (domain/2, compact rows, GBNF/Lark/Regex grammars, and KV-cache prompt ordering) to reduce output tokens by 46–60% vs JSON while recovering 99.8% of truncated records.
---

# `.mini` — Compact Token-Efficient LLM Output Protocol

Use this skill when building or optimizing LLM pipelines that emit structured JSON arrays, classifications, extractions, or tabular batches where JSON verbosity wastes output tokens, dollars, and latency.

## Choosing the Right Mode

1. **Flat Required/Nullable Arrays (`compact_rows` / `encode_rows`)**
   - Best when every record fits on one line with a descriptive text field placed last (`titulo`, `summary`, `reason`).
   - Eliminates headers and per-row JSON keys; delivers ~**58.9%** fewer output tokens than compact JSON and **87%** fewer prompt tokens (~70 tok).
   - Python: `Workflow(bundle).run_compact(generate, task, last_text_field="titulo", expected_records=20)`
2. **Adaptive Arbitrary JSON (`mini-domain/2`, `encode_v2`)**
   - Best for deep nested schemas, URLs, coordinate arrays, high-frequency enums, or monotonically increasing IDs/timestamps.
   - Automatically selects optimal BPE delimiter (` `, `,`, `\t`, or `|`), constant-column factoring (`d=`), prefix factoring (`p=`), integer delta encoding (`dt=`), zero-token empty optionals/nulls (`z=1`), compact booleans (`b=1`), and per-document dictionaries (`e=`).
   - 100% lossless JSON round-trip verified by `decode(encode_v2(doc, contract), contract) == doc`.
3. **Provider-Native Tuple Schema (`run_positional`)**
   - Best when OpenAI/Anthropic/Gemini Structured Outputs `json_schema` mode is required and schema compilation must happen strictly server-side (`[[1, "Acceso"], ...]`).
4. **Constrained Local / vLLM Decoding (`grammar.py`)**
   - Zero-retry guaranteed compliance on local or self-hosted endpoints:
     - llama.cpp: `mini grammar .mini/contract.json --format gbnf`
     - vLLM / XGrammar / Outlines: `mini grammar .mini/contract.json --format lark`
     - Regex engines: `mini grammar .mini/contract.json --format regex`

## Production Prompt & KV-Cache Best Practices

- **Prevent Reasoning/CoT Inflation**: Use `prompt_style="lean"` (`prompt.lean.<lang>.md` / `make_lean_prompt`) for small or fast models (Haiku, Mini, Flash) to strip unused nullability/dictionary rules and raw schema JSON.
- **Maximize Prompt Cache Hits**: Pass `kv_cache_first=True` to `Workflow(..., kv_cache_first=True)` or `flow.complete(..., kv_cache_first=True)` so static format instructions sit at byte 0 across multi-turn or batch requests.
- **Safe Deterministic Repair**: Always pass responses through `repair(text, contract)` and `Workflow.process()` — never regex-parse LLM output ad hoc. `repair` fixes BOM, CRLF, Markdown fences, trailing pipes, and echoed headings without inventing missing values.
- **Line-Granular Truncation Recovery**: When `finish_reason == "length"`, `Workflow` validates all complete prefix lines and asks the model *only* for the missing tail count (`n=remaining`).

## CLI Quick Reference

```bash
mini setup                                         # Interactive wizard -> generates portable .mini/ toolkit
mini build sample.json --prefix item --out .mini   # Generate bundle from sample JSON
mini grammar .mini/contract.json --format gbnf     # Compile llama.cpp GBNF grammar
mini integrate app.py --bundle .mini --apply       # Auto-patch OpenAI/requests JSON calls
mini bench sample.json --contract .mini/contract.json
```
