# `.mini-tc` — Software test cases

**Prefix:** `tc`  **Version:** 1  **Parent:** —  **Domain:** software engineering / QA

Manual or automated test cases: module, title, precondition, ordered steps, expected result, priority, type and automation flag.

## Record layout

```
id:str | module:str | title:str | precondition:str | steps:list<str>[1..20] | expected:str | priority:enum{low|medium|high|critical} | type:enum{functional|integration|performance|security|usability|regression} | automated:bool
```

| # | field | type | notes |
|---|---|---|---|
| 1 | `id` | `str` | core |
| 2 | `module` | `str` | core |
| 3 | `title` | `str` | core |
| 4 | `precondition` | `str` | core |
| 5 | `steps` | `list<str>[1..20]` | core |
| 6 | `expected` | `str` | core |
| 7 | `priority` | `enum{low|medium|high|critical}` | core |
| 8 | `type` | `enum{functional|integration|performance|security|usability|regression}` | core |
| 9 | `automated` | `bool` | core |

## Header keys

| key | type | required | description |
|---|---|---|---|
| `d` | `str` | no | generation date YYYYMMDD |
| `l` | `str` | no | language code |
| `t` | `str` | no |  |
| `proj` | `str` | no |  |
| `n` | `int` | yes | number of records |
| `v` | `int` | no | contract version |

## Example

```
tc|n=12|d=20260603|l=en|t=SIMA release 1.2 regression|proj=SIMA
TC-001|auth|Login with valid credentials|User registered and active|open /login,enter valid email and password,click Sign in|Dashboard is shown and session cookie is set|high|functional|true
TC-002|auth|Login with wrong password|User registered|open /login,enter valid email and wrong password,click Sign in|Error message; no session created|high|functional|true
…
```

## Fixtures

`fixtures/valid.mini` ↔ `fixtures/canonical.json` (round-trip), `fixtures/escaping.mini` ↔ `fixtures/escaping.json`, and the negative cases `bad_count.mini`, `bad_arity.mini`, `bad_type.mini`.

## Prompt block

Generate the transferable specification with `mini prompt tc`.
