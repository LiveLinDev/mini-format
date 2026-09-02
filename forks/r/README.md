# `.mini-r` — Analytic rubric criteria

**Prefix:** `r`  **Version:** 1  **Parent:** —  **Domain:** education / assessment

One rubric criterion per line with k ordered performance levels (k declared in the header), a weight and the evidence to inspect.

## Record layout

```
id:str | dimension:str | criterion:str | levels:list<str> | weight:float[0..1] | evidence:str
```

| # | field | type | notes |
|---|---|---|---|
| 1 | `id` | `str` | core |
| 2 | `dimension` | `str` | core |
| 3 | `criterion` | `str` | core |
| 4 | `levels` | `list<str>` | core; ordered level descriptors |
| 5 | `weight` | `float[0..1]` | core |
| 6 | `evidence` | `str` | core |

## Header keys

| key | type | required | description |
|---|---|---|---|
| `d` | `str` | no | generation date YYYYMMDD |
| `l` | `str` | no | language code |
| `t` | `str` | no |  |
| `k` | `int` | yes | number of performance levels |
| `scale` | `str` | no |  |
| `n` | `int` | yes | number of records |
| `v` | `int` | no | contract version |

## Example

```
r|n=12|d=20260603|l=en|t=Argumentative essay|k=4|scale=0-3
r1|Argument|Thesis clarity|absent or unclear,stated but vague,clear and focused,clear\, focused and original|0.2|Introduction paragraph
r2|Argument|Use of evidence|no evidence,evidence unrelated to claims,relevant evidence,relevant\, well-integrated evidence|0.2|Body paragraphs
…
```

## Fixtures

`fixtures/valid.mini` ↔ `fixtures/canonical.json` (round-trip), `fixtures/escaping.mini` ↔ `fixtures/escaping.json`, and the negative cases `bad_count.mini`, `bad_arity.mini`, `bad_type.mini`.

## Prompt block

Generate the transferable specification with `mini prompt r`.
