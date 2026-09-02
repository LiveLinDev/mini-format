# `.mini-map` — Concept map edges

**Prefix:** `map`  **Version:** 1  **Parent:** —  **Domain:** education / knowledge graphs

One directed relation per line (source, relation, target, weight, evidence segment).

## Record layout

```
src:str | rel:enum{is_a|has_part|performs|produces|causes|requires|contrasts|example_of} | dst:str | weight:float[0..1] | evidence:str?
```

| # | field | type | notes |
|---|---|---|---|
| 1 | `src` | `str` | core |
| 2 | `rel` | `enum{is_a|has_part|performs|produces|causes|requires|contrasts|example_of}` | core |
| 3 | `dst` | `str` | core |
| 4 | `weight` | `float[0..1]` | core |
| 5 | `evidence` | `str?` | core; optional; segment id supporting the edge |

## Header keys

| key | type | required | description |
|---|---|---|---|
| `d` | `str` | no | generation date YYYYMMDD |
| `l` | `str` | no | language code |
| `t` | `str` | no |  |
| `src` | `str` | no |  |
| `n` | `int` | yes | number of records |
| `v` | `int` | no | contract version |

## Example

```
map|n=12|d=20260603|l=es|t=Biología celular|src=clase-64
célula|has_part|núcleo|0.9|s2
célula|has_part|mitocondria|0.9|s2
…
```

## Fixtures

`fixtures/valid.mini` ↔ `fixtures/canonical.json` (round-trip), `fixtures/escaping.mini` ↔ `fixtures/escaping.json`, and the negative cases `bad_count.mini`, `bad_arity.mini`, `bad_type.mini`.

## Prompt block

Generate the transferable specification with `mini prompt map`.
