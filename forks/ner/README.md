# `.mini-ner` — Named-entity annotations

**Prefix:** `ner`  **Version:** 1  **Parent:** —  **Domain:** NLP / data labelling

One entity mention per line (relational pattern: several lines share a document id).

## Record layout

```
doc:str | start:int[0..] | end:int[0..] | text:str | type:enum{PERSON|ORG|LOC|DATE|PRODUCT|CONCEPT|MISC} | conf:float[0..1]
```

| # | field | type | notes |
|---|---|---|---|
| 1 | `doc` | `str` | core |
| 2 | `start` | `int[0..]` | core |
| 3 | `end` | `int[0..]` | core |
| 4 | `text` | `str` | core |
| 5 | `type` | `enum{PERSON|ORG|LOC|DATE|PRODUCT|CONCEPT|MISC}` | core |
| 6 | `conf` | `float[0..1]` | core |

## Header keys

| key | type | required | description |
|---|---|---|---|
| `d` | `str` | no | generation date YYYYMMDD |
| `l` | `str` | no | language code |
| `model` | `str` | no |  |
| `schema` | `str` | no |  |
| `n` | `int` | yes | number of records |
| `v` | `int` | no | contract version |

## Example

```
ner|n=12|d=20260603|l=en|model=ner-base-2026|schema=ontonotes-lite
d1|0|17|Whisper|PRODUCT|0.98
d1|25|31|OpenAI|ORG|0.99
…
```

## Fixtures

`fixtures/valid.mini` ↔ `fixtures/canonical.json` (round-trip), `fixtures/escaping.mini` ↔ `fixtures/escaping.json`, and the negative cases `bad_count.mini`, `bad_arity.mini`, `bad_type.mini`.

## Prompt block

Generate the transferable specification with `mini prompt ner`.
