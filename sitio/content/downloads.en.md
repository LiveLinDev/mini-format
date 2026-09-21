# Download mini-format 1.2.1

The toolkit includes everything needed to build a domain format from JSON samples and run it locally. MIT licensed; no account or private repository access required.

| Download | Contents |
|---|---|
| [Complete toolkit .zip](/downloads/mini-format-1.2.1.zip) | Python package, Node package, examples, specifications and guides. |
| [Python .whl](/downloads/mini_format-1.2.1-py3-none-any.whl) | `mini` CLI, base profile, 14 families and toolkit builder. Python 3.9+. |
| [Node / TypeScript .tgz](/downloads/mini-format-core-1.2.1.tgz) | Base-profile parser, validator, serializer and streaming. Node 22.6+. |
| [Source code .zip](/downloads/mini-format-1.2.1-source.zip) | Implementations, tests, contracts and reproducible public benchmark. |

## Install Python

```bash
python -m pip install https://mini-format.pmoluna.com/downloads/mini_format-1.2.1-py3-none-any.whl
mini build examples/phones.json examples/phones-extra.json --prefix phone --out .mini
```

The second command uses examples from the ZIP. To install offline, run this from the extracted directory:

```bash
python -m pip install --no-index mini_format-1.2.1-py3-none-any.whl
```

## Install Node

Download the `.tgz` or extract it from the toolkit, then run:

```bash
npm install ./mini-format-core-1.2.1.tgz
```

Import the library with `import { Registry, parse } from '@mini-format/core'`. The generated domain toolkit uses Python; this library implements the SPEC 1.1 base profile.

## Verify your download

[SHA256SUMS.txt](/downloads/SHA256SUMS.txt) lists hashes for all four packages. The [JSON manifest](/downloads/manifest.json) includes the version, file sizes and SHA-256 hashes.

In PowerShell: `Get-FileHash .\mini-format-1.2.1.zip -Algorithm SHA256`. On Linux: `sha256sum mini-format-1.2.1.zip`. On macOS: `shasum -a 256 mini-format-1.2.1.zip`. Compare the result with the checksum file.

Continue with [Quickstart](/docs/quickstart/) or [Build your toolkit](/docs/build/).
