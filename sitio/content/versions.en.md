# Versions and compatibility

mini-format **1.2.2** distributes the **SPEC 1.1** base profile, which keeps every SPEC 1.0 document valid, and the generated **`mini-domain/1`** domain toolkit. The package version identifies the tools; the contract version identifies the data each parser can read.

## Appended fields

In the base profile, a reader accepts unknown trailing fields only when the prefix matches and the header declares a `v` higher than the contract version. It validates known fields and leaves the unknown tail out of the canonical object. Line escapes must still be valid.

At the same version, extra fields produce `E05`. Changing the core or using a different prefix requires another contract. Forward compatibility does not replace a domain migration.

## Diagnostics

Base-profile errors include a code, line, field and message. These identifiers let you preserve valid records and direct retries to the rejected data.

## Generated toolkit

The contract, prompt and generated tools form one unit. Reuse that unit and version it with your application. When samples change, generate and verify a new version before integrating it. The [toolkit guide](/docs/build/) distinguishes its capabilities from those of the base profile.

## Distribution

[Toolkit ZIP](/downloads/mini-format-1.2.2.zip), [Python wheel](/downloads/mini_format-1.2.2-py3-none-any.whl), [TypeScript package](/downloads/mini-format-core-1.2.2.tgz) and [source code](/downloads/mini-format-1.2.2-source.zip). Downloads require neither an account nor access to a private repository.
