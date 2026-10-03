# From your JSON to a .mini workflow

A support app receives messages. AI extracts one ticket per message. The app needs **JSON** to store and assign tickets; `.mini` reduces repetition in the AI response and then converts to that same JSON.

[See the 20-ticket use case first](/flujo/). Replay it without an API key and inspect validation and repair.

## 1. Install and open the wizard

[Download the package](/downloads/mini-format-1.3.0.zip) and extract it. From that directory:

```sh
python -m pip install --no-index mini_format-1.3.0-py3-none-any.whl
mini setup
```

The wizard asks for **Spanish or English first**. Choose JSON your AI already generated, define fields or use the support example. Include representative fields and types; add samples for optional fields and different structures.

Choose a short name and a new directory such as `.mini`. The contract defines fields and types; the prompt explains the AI output format. Both are generated.

## 2. Test before integration

Open `.mini/try-prompt.md` and paste its **contents** into your AI. It includes the format in your selected language and requests 20 fictional records for the same use case. A file path alone does not give AI those instructions.

Save the response as `response.mini` and check it:

```sh
python .mini/validator.py response.mini
```

The first response may already be valid. Repair removes Markdown wrappers, BOM and Windows line endings. Incorrect types or missing data require an AI correction.

```sh
python .mini/repair.py response.mini --out corrected.mini
```

Pending errors mean no usable repaired response was produced. [The complete example](/flujo/) shows the workflow requesting only the incorrect line, then checking the whole result again.

## 3. Connect your application workflow

Choose **Integration** in `mini setup`, or run:

```sh
mini integrate path/to/app.py --bundle .mini --lang en
```

Locate the call requesting JSON. The command prepares `integration/INTEGRATE.md` with actual contract and prompt paths and a diff for compatible code. Add `--apply` for the synchronous Python chat completions followed by `json.loads` pattern; it retains a backup.

For other SDKs, asynchronous code or languages, give the guide to your coding AI. Read the generated prompt, change the call's output format and connect its callback to `Workflow.run`. Disable API JSON-only mode to receive .mini.

**The complete flow:** task → AI → .mini → validate → Repair → optional AI correction → revalidate → JSON. The app gets data only when the entire response validates. Require an expected record count to block incomplete batches.

[See integration code](/docs/build/).

## 4. Replay a complete run

From the package directory:

```sh
python examples/flujo-soporte/run.py
```

There are 20 messages, a saved .mini response and a one-line correction. The actual workflow delivers `output/soporte/result.json` and saves `history.json`. Responses were authored by Muse; errors were inserted for illustration, not to measure AI reliability.

For the local form with recorded and live AI modes:

```sh
python examples/flujo-soporte/run.py --serve
```

Open the printed address. The form asks for an API key and model only in live mode. The key stays in memory and is not stored in history. Real calls and corrections have provider costs. Integrate your own callback to keep your provider.

## What about savings?

The same 20-ticket output takes 443 JSON tokens, 304 TOON tokens and 278 .mini tokens with `o200k_base`. The .mini prompt has 571 tokens; retries are extra. Fewer output tokens alone do not prove lower total cost, especially for small batches. [Explore costs](/economia/).

<details><summary>Already familiar with .mini: commands and references</summary>

`mini build sample.json --prefix ticket --out .mini --lang en` creates the same toolkit without the wizard. Multiple sample files are accepted. For JSON Schema, see `mini from-schema --help` and the [base profile](/docs/spec/).

The [14 sample families](/docs/forks/) are optional. The [playground](/playground/) is for base-format practice. Generated toolkits use Python; [Node/TypeScript](/docs/typescript/) implements base SPEC 1.1.

</details>
