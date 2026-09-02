# Generative validation

Every number in the paper's generative section can be traced here.

| Experiment | What it measures | Where |
|---|---|---|
| E1 serialization fidelity | same 12 items, six formats (JSON, YAML, XML, CSV, TOON tabular, .mini), three models | `raw/e1/<model>/<fmt>/*.txt`, `results/e1_*.csv` |
| Ablation | Haiku 4.5 under the v1 *draft* spec (backslash escaping only) vs v1.0 | `raw/e1_ablation/`, `results/ablation.csv` |
| E2 fork transfer | three forks never seen by the model (tc, log, cls), spec block only | `raw/e2/`, `results/e2_*.csv` |
| E3 parser synthesis | model writes a parser from the spec block; run against fixtures | `raw/e3/<model>/<prefix>/*.py`, `results/e3_samples.csv` |
| E4 break-even | spec-block cost vs per-record saving | `results/e4_breakeven.csv` |
| E5 truncation | records recoverable after random truncation | `results/e5_truncation.csv` |

Models (self-reported ids from their system prompts): `claude-haiku-4-5-20251001`,
`claude-sonnet-5`, `claude-opus-5` (1M context), accessed through the Claude
Agent SDK sub-agent mechanism at its default sampling temperature; each sample is
an independent session that receives only the task text (`agent_tasks/*.txt`)
and writes its answer to a file. Prompts are built by `protocol.py`
(`python generative/protocol.py` regenerates `prompts/`); `run_eval.py` evaluates
the archived outputs; `extra_experiments.py` runs the deterministic experiments.
`raw/e2_v0/` keeps the first `log` run whose neutral content rendering was
ambiguous for list values containing ':' (kept for transparency; superseded by
`raw/e2/*/log`).
