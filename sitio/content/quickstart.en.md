# Quickstart

Build your domain toolkit once. Then add its prompt to your AI workflow and convert each `.mini` response back into the JSON your application consumes.

## 1. Install

[Download toolkit 1.1.0 (.zip)](/downloads/mini-format-1.1.0.zip) · [Python package (.whl)](/downloads/mini_format-1.1.0-py3-none-any.whl) · [Source code (.zip)](/downloads/mini-format-1.1.0-source.zip)

Requires Python 3.9 or later. The core and generated toolkit use the standard library.

```bash
pip install https://mini-format.pmoluna.com/downloads/mini_format-1.1.0-py3-none-any.whl
mini --help
```

To install offline, download and extract the ZIP, then run `pip install` on the included `.whl` file. With Node 22.6 or later, install the base-profile package: `npm install ./mini-format-core-1.1.0.tgz`. You can also [download it separately](/downloads/mini-format-core-1.1.0.tgz). The generated domain toolkit is Python; the TypeScript and JavaScript libraries implement the base profile.

## 2. Gather JSON examples

Save this as `phones.json`:

```json
[
  {"id": 1, "brand": "Acme", "model": "One", "price": 299, "available": true},
  {"id": 2, "brand": "Acme", "model": "Pro", "price": 499, "available": false}
]
```

Add examples of optional fields, lists, nested objects and null values in additional files. Diverse cases matter more than repeating the same sample.

## 3. Build your .mini

```bash
mini build phones.json --prefix phone --out .mini
```

To combine samples: `mini build phones.json more-phones.json --prefix phone --out .mini`.

The `.mini` directory contains the contract, JSON schema, prompts in both languages, parser, validator, repair tools, examples and manifest. See [Build your toolkit](/docs/build/) for the generated profile and its rules.

## 4. Integrate

Use `.mini/prompt.en.md` as your model's format instruction. Save its response as `response.mini`.

```bash
python .mini/validator.py response.mini
python .mini/parser.py decode response.mini
```

The second command prints the reconstructed JSON. You can also call `loads(text)` and `dumps(object)` after importing the generated `parser.py` module into your application.

## 5. Detect and repair

```bash
python .mini/parser.py diagnose response.mini
python .mini/repair.py response.mini --out corrected.mini
```

Repair normalizes safe wrappers and line endings. It never invents missing values. Changing the declared count requires `--fix-count`; use it only after checking that the received batch is complete. Semantic errors require an application correction or a model retry.

## Included families

The 14 base-profile families remain available: `mini forks`, `mini prompt log --lang en` and `mini validate document.mini`. Their APIs are documented under [Python](/docs/python/), [TypeScript](/docs/typescript/) and [CLI](/docs/cli/).

The [playground](/playground/) lets you explore the base profile and compare formats without installing anything.
