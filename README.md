# .mini: shorter AI responses, JSON for your application

If your app asks AI for lists of structured data, `.mini` can reduce response tokens. A contract defines the fields once; AI returns their values in a compact format. The workflow validates, repairs and converts the result to the JSON your app uses.

**One use case:** turn 20 support messages into 20 tickets with a title, category and priority. The app needs JSON to store, filter and assign them. [See the complete workflow](https://mini-format.pmoluna.com/flujo/): input, response, correction and history.

In this example, the same output takes 443 JSON tokens, 304 TOON tokens and 278 .mini tokens (`o200k_base`). These are output counts. The .mini prompt has 571 tokens and corrections also cost tokens; measure the full workflow before claiming monetary savings.

## Start here

[Download and extract the package](https://mini-format.pmoluna.com/downloads/mini-format-1.3.0.zip). From the extracted directory:

```sh
python -m pip install --no-index mini_format-1.3.0-py3-none-any.whl
mini setup
```

The wizard guides you through:

1. Spanish or English.
2. A sample JSON response from your AI, your own fields or the included support example.
3. Name and directory: generate a contract, prompt, validator, Repair and `workflow.py`.
4. Test: ask your AI for 20 fictional records with the generated prompt and validate the reply.
5. Integration: locate your project's AI call and prepare its workflow connection.

Automatic editing covers a synchronous Python chat completions + `json.loads` pattern. Other SDKs/languages receive a coding-AI guide with actual paths. `Workflow.run` accepts any synchronous callback that takes a prompt and returns text; a CLI bridge is available for other languages.

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
