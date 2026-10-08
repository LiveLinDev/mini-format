# Connect .mini to your AI call

Start with [mini setup](https://mini-format.pmoluna.com/docs/quickstart/): language, sample JSON, name and directory. The toolkit contains a contract, prompts and a portable Python workflow with no external runtime dependencies.

## Wizard or command

In `mini setup`, choose **Select my file** to locate your AI-call code or **Search my project** to find it. Review the proposed change or connect supported Python with an original backup. **I do not have a workflow yet** keeps the resume command in `README.md` and `GUIA.md`.

Once you have the file, you can also run:

```sh
mini integrate app.py --bundle .mini --lang en
```

Locate AI calls and JSON parsing. The command writes `integration/INTEGRATE.md` with actual paths and `change.diff` for compatible code. Repeat with `--apply` to apply it.

Automatic editing recognizes a synchronous Python `client.chat.completions.create(...)` assignment followed by `json.loads(response.choices[0].message.content)`. The response must have no other uses. It keeps the client, model, messages and parameters, removes `response_format`, reads the generated prompt and connects the workflow. A backup is kept in `integration/app.py.before`; a bridge is created beside the source file.

It also recognizes a `requests.post(...)` or `httpx.post(...)` call whose `json=` argument is a chat dictionary with `messages` and `response_format` (OpenAI-compatible APIs such as DeepSeek). Only that call changes and goes through the bridge: the request is sent without `response_format`, with the .mini prompt as a last system message, and the app receives a response of the same shape whose content is the validated JSON; `usage` adds up every call. Other requests and HTTP errors are unchanged. When the provider reports `finish_reason = "length"`, the last line is discarded, complete records are kept and only the missing ones are requested.

Other SDKs/languages, streaming, tools and asynchronous functions receive a coding-AI guide and need an application-specific callback or bridge.

## Keep your provider with a callback

A function receives a prompt and returns text. Use your existing AI call without JSON-only output mode:

```python
import importlib.util
from pathlib import Path

bundle = Path('.mini').resolve()
spec = importlib.util.spec_from_file_location('my_mini_flow', bundle / 'workflow.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
flow = module.Workflow(bundle, lang='en')

def generate(prompt):
    response = client.chat.completions.create(
        model=model,
        messages=[{'role': 'user', 'content': prompt}],
    )
    return response.choices[0].message.content

data = flow.run(generate, task, expected_records=20)
# data: JSON-compatible application data.
# flow.last_run: response, diagnostics, correction and result.
```

`task` includes actual inputs and business instructions. Credentials remain in your application. The callback is used for generation and correction; keep necessary business instructions in both calls.

## What happens

1. Read prompt.en.md and append it to the task.
2. Obtain .mini from AI and validate.
3. Repair safe wrappers, BOM and CRLF.
4. Ask the same callback to replace invalid lines, preserving valid lines. Header/count errors request a complete regeneration.
5. Revalidate and check expected_records when provided.
6. Return JSON only on success.

At most one correction is requested by default. `max_repairs=0` disables it. Pending errors raise `WorkflowError`; `error.report` and `flow.last_run` expose diagnostics. No invented data or silent count reduction. Validation checks structure/types, not the truth of the AI interpretation.

## Async Python and Node

Use `await flow.run_async(generate, task, expected_records=20)` with an async Python callback.

In Node, import `Workflow` from `./.mini/workflow.mjs` and call `await new Workflow().run(generate, task, {expectedRecords: 20})`. The callback keeps any SDK. This bridge runs the same generated Python runtime and requires Python. It validates, repairs, requests a correction and returns JSON. `lastRun` holds the history.

## Other languages

Pipe text to `python .mini/workflow.py -`. Exit 0 yields JSON on stdout; exit 1 yields history and diagnostics on stderr. Connect semantic retries in the calling application; the CLI only repairs safe wrappers and parses, without AI calls.

```sh
python .mini/workflow.py response.mini --out result.json --expected-records 20
```

`--history file.json` optionally saves the run. It may contain application data, but no API key: the runtime never receives credentials.

## Reproducible test

`python examples/flujo-soporte/run.py` replays the 20 illustrative tickets and correction with the actual tools. `--serve` opens the local form with optional live AI and an API key held in memory. [See the history](https://mini-format.pmoluna.com/flujo/).

Rebuild in a new directory for changing data: `mini build sample.json more.json --prefix ticket --out .mini-v2 --lang en`. Do not edit the contract by hand. Samples cannot prove unobserved rules.

The generated mini-domain/1 profile uses its own Python parser. Base Python/TypeScript libraries implement SPEC 1.1. Families are optional. [Domain reference](/docs/profile/).
