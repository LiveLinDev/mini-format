# Download mini-format 1.3.1

The toolkit includes everything needed to build your own format from a data file or by defining fields in the interactive guide. MIT licensed; no account or private repository access required.

Recommended download: [complete .zip package](/downloads/mini-format-1.3.1.zip). Includes the installer, a 20-ticket example with history and a local form. Then run `mini setup`.

<details><summary>Other packages and technical reference</summary>

| Download | Contents |
|---|---|
| [Complete toolkit .zip](/downloads/mini-format-1.3.1.zip) | Python package, Node package, integration examples, specifications and guides. |
| [Python .whl](/downloads/mini_format-1.3.1-py3-none-any.whl) | `mini` CLI, base profile and toolkit builder. Python 3.9+. |
| [Node / TypeScript .tgz](/downloads/mini-format-core-1.3.1.tgz) | Base-profile parser, validator, serializer and streaming. Node 22.6+. |
| [14 sample families .zip](/downloads/mini-format-1.3.1-example-families.zip) | Optional contracts and fixtures to study or adapt. Not bundled with Python or Node. |
| [Source code .zip](/downloads/mini-format-1.3.1-source.zip) | Implementations, tests, contracts and reproducible public benchmark. |

</details>

## Install Python

```bash
python -m pip install https://mini-format.pmoluna.com/downloads/mini_format-1.3.1-py3-none-any.whl
mini setup
```

`mini` starts the interactive guide: it accepts JSON, CSV, TSV and XML, or lets you define fields without a file. It creates a folder with `GUIA.md`, examples, prompts, converter and validator. To install offline, run this from the extracted directory:

```bash
python -m pip install --no-index mini_format-1.3.1-py3-none-any.whl
```

## Install Node

Download the `.tgz` or extract it from the toolkit, then run:

```bash
npm install ./mini-format-core-1.3.1.tgz
```

Import the library with `import { Registry, parse } from '@mini-format/core'`. The generated domain toolkit uses Python; this library implements the SPEC 1.1 base profile.

## Verify your download

[SHA256SUMS.txt](/downloads/SHA256SUMS.txt) lists hashes for all five packages. The [JSON manifest](/downloads/manifest.json) includes the version, file sizes and SHA-256 hashes.

In PowerShell: `Get-FileHash .\mini-format-1.3.1.zip -Algorithm SHA256`. On Linux: `sha256sum mini-format-1.3.1.zip`. On macOS: `shasum -a 256 mini-format-1.3.1.zip`. Compare the result with the checksum file.

Continue with [Quickstart](/docs/quickstart/) or [Build your toolkit](/docs/build/). To use the optional families, see [how to load them](/docs/forks/).
