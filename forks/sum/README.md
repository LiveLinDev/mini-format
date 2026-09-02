# `.mini-sum` — Micro-lesson summary segments

**Prefix:** `sum`  **Version:** 1  **Parent:** —  **Domain:** education / microlearning

Time-aligned summary segments of a recorded lecture (SIMA microcontent).

## Record layout

```
id:str | t_start:int[0..] | t_end:int[0..] | title:str | summary:str | keywords:list<str>[1..10] | bloom:enum{L1|L2|L3|L4|L5|L6}
```

| # | field | type | notes |
|---|---|---|---|
| 1 | `id` | `str` | core |
| 2 | `t_start` | `int[0..]` | core |
| 3 | `t_end` | `int[0..]` | core |
| 4 | `title` | `str` | core |
| 5 | `summary` | `str` | core |
| 6 | `keywords` | `list<str>[1..10]` | core |
| 7 | `bloom` | `enum{L1|L2|L3|L4|L5|L6}` | core |

## Header keys

| key | type | required | description |
|---|---|---|---|
| `d` | `str` | no | generation date YYYYMMDD |
| `l` | `str` | no | language code |
| `t` | `str` | no |  |
| `src` | `str` | no |  |
| `dur` | `int` | no | lecture duration in seconds |
| `n` | `int` | yes | number of records |
| `v` | `int` | no | contract version |

## Example

```
sum|n=12|d=20260603|l=es|t=Biología celular|src=clase-64|dur=2520
s1|0|180|Introducción a la célula|La célula es la unidad básica de la vida; se distinguen procariotas y eucariotas.|célula,procariota,eucariota|L1
s2|180|420|Organelos y funciones|Mitocondria produce energía; el cloroplasto realiza la fotosíntesis; el núcleo guarda el ADN.|mitocondria,cloroplasto,núcleo|L2
…
```

## Fixtures

`fixtures/valid.mini` ↔ `fixtures/canonical.json` (round-trip), `fixtures/escaping.mini` ↔ `fixtures/escaping.json`, and the negative cases `bad_count.mini`, `bad_arity.mini`, `bad_type.mini`.

## Prompt block

Generate the transferable specification with `mini prompt sum`.
