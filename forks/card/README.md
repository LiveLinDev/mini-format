# `.mini-card` — Flashcards (spaced repetition)

**Prefix:** `card`  **Version:** 1  **Parent:** —  **Domain:** education / microlearning

One flashcard per line: front, back, optional hint, tags, Bloom level and an initial ease factor for spaced repetition.

## Record layout

```
id:str | topic:str | front:str | back:str | hint:str? | tags:list<str>[0..8] | bloom:enum{L1|L2|L3|L4|L5|L6} | ease:float[1.3..3.0]
```

| # | field | type | notes |
|---|---|---|---|
| 1 | `id` | `str` | core |
| 2 | `topic` | `str` | core |
| 3 | `front` | `str` | core |
| 4 | `back` | `str` | core |
| 5 | `hint` | `str?` | core; optional |
| 6 | `tags` | `list<str>[0..8]` | core |
| 7 | `bloom` | `enum{L1|L2|L3|L4|L5|L6}` | core |
| 8 | `ease` | `float[1.3..3.0]` | core |

## Header keys

| key | type | required | description |
|---|---|---|---|
| `d` | `str` | no | generation date YYYYMMDD |
| `l` | `str` | no | language code |
| `t` | `str` | no |  |
| `src` | `str` | no | source lesson id |
| `n` | `int` | yes | number of records |
| `v` | `int` | no | contract version |

## Example

```
card|n=12|d=20260603|l=es|t=repaso transversal|src=clase-64
c1|Biología|¿Qué organelo realiza la fotosíntesis?|El cloroplasto, gracias a la clorofila.|Pigmento verde|célula,plantas|L1|2.5
c2|Química|¿Qué mide el pH?|La acidez o basicidad de una solución (0-14).|Iones H+|soluciones,ácidos|L2|2.5
…
```

## Fixtures

`fixtures/valid.mini` ↔ `fixtures/canonical.json` (round-trip), `fixtures/escaping.mini` ↔ `fixtures/escaping.json`, and the negative cases `bad_count.mini`, `bad_arity.mini`, `bad_type.mini`.

## Prompt block

Generate the transferable specification with `mini prompt card`.
