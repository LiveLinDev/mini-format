# Changelog

## 1.1.0

- Build domain toolkits from multiple JSON samples, preserving nested structure,
  absent fields, nulls and arrays through a generated contract.
- Export bilingual prompts, a standalone Python runtime, validation, diagnostics
  and conservative repair tools.
- Ship an offline wheel, compiled Node ESM with bundled families, a toolkit ZIP,
  source archive and SHA-256 checksums directly from the website.
- Compare public JSON snapshots against official nested/flat TOON and other
  formats, with round-trip verification and separate prompt costs.
- Add bilingual onboarding and replace development-status copy with executable
  installation and integration guides while preserving the visual system.
- Fix core forward compatibility: only a newer declared version of the same
  prefix permits unknown trailing fields. Core SPEC 1.0 stays supported.
- Make JavaScript fixture tests work with Windows paths and CRLF checkouts.

Package version, core specification and domain profile are separate identifiers.
Release archives are built from the checkout; this does not imply registry
publication or completion of academic user studies.
