# .mini: shorter AI responses, JSON for your application

A company receives complaints and questions. To avoid creating support tickets by hand, its app asks AI to interpret each message and generate a record with a title, category and priority. That record is a ticket; the code needs **JSON** to store and assign it.

JSON repeats field names in every ticket. The API counts that text in **tokens**, pieces used to calculate the bill. Fewer response tokens cost less at the same model and rate. TOON also reduces repetition; `.mini` tailors the rules to your domain through a **contract**: fields, order and types declared once. The workflow validates the compact response, repairs it when possible and recovers the same JSON objects.

[Follow support automation](https://mini-format.pmoluna.com/flujo/): 20 customer messages become 20 JSON objects, with a recorded run you can inspect without a key.

In this example, the same output takes 443 JSON tokens, 304 TOON tokens and 278 .mini tokens (`o200k_base`). These are output counts. The .mini prompt has 571 tokens and corrections also cost tokens; measure the full workflow before claiming monetary savings.

## Start here

[Download and extract the package](https://mini-format.pmoluna.com/downloads/mini-format-1.3.2.zip). From the extracted directory:

```sh
python -m pip install --no-index mini_format-1.3.2-py3-none-any.whl
mini setup
```

The wizard guides you through:

1. Spanish or English.
2. A sample JSON response from your AI, your own fields or the included support example.
3. Name and directory: create `contract.json` (rules), `prompt.es.md` / `prompt.en.md` (AI instructions) and `workflow.py` (validation, Repair and JSON conversion).
4. Integration: select the file that calls AI, search your project or choose **I do not have a workflow yet**. The resume command is saved in `README.md` and `GUIA.md`.
5. Test: paste `try-prompt.md` into your AI; it asks for 20 fictional objects. Check the reply before saving real data.

Automatic editing covers a synchronous Python chat completions + `json.loads` pattern. Other SDKs/languages receive a coding-AI guide with actual paths. `Workflow.run` accepts any synchronous callback that takes a prompt and returns text; a CLI bridge is available for other languages.

No workflow yet? Keep the toolkit. Once you create your AI call file, run:

```sh
mini integrate path/to/app.py --bundle .mini --lang en
```

## Try the workflow without a key

```sh
python examples/flujo-soporte/run.py
```

Replay 20 tickets authored by Muse with deliberately inserted demonstration errors. It executes the actual tools and saves `output/soporte/result.json` and `history.json`. No API call is made. For the local form and optional live OpenAI API-key mode: `python examples/flujo-soporte/run.py --serve`.

## Continue when needed

- [Quickstart](https://mini-format.pmoluna.com/docs/quickstart/): from your JSON to your application.
- [Integration and toolkit](BUILD_GUIDE.md): callbacks, repair and command integration.
- [Downloads](https://mini-format.pmoluna.com/downloads/): Python, Node and examples.
- [Specification](SPEC.md) and [toolkit profile](DOMAIN_PROFILE.md): technical reference.

`.mini` adapts to your data. The 14 families are optional examples. Generated toolkits use Python 3.9+ and the `mini-domain/1` profile; the Node/TypeScript library implements base SPEC 1.1. [MIT](LICENSE).
