# `.mini-cls` — Multi-label text classification outputs

**Prefix:** `cls`  **Version:** 1  **Parent:** —  **Domain:** NLP / support triage

Classifier outputs: the label set is written in full and the predicted labels carry *, so both the label space and the prediction are self-describing.

## Record layout

```
id:str | text:str | labels:mlist<str>*1+ | conf:float[0..1] | rationale:str?
```

| # | field | type | notes |
|---|---|---|---|
| 1 | `id` | `str` | core |
| 2 | `text` | `str` | core |
| 3 | `labels` | `mlist<str>*1+` | core |
| 4 | `conf` | `float[0..1]` | core |
| 5 | `rationale` | `str?` | core; optional |

## Header keys

| key | type | required | description |
|---|---|---|---|
| `d` | `str` | no | generation date YYYYMMDD |
| `l` | `str` | no | language code |
| `model` | `str` | no |  |
| `k` | `int` | no | labels in the label set |
| `n` | `int` | yes | number of records |
| `v` | `int` | no | contract version |

## Example

```
cls|n=12|d=20260603|l=en|model=cls-support-2026|k=6
m1|The quiz froze after question 4, is that a known issue?|question*,feedback,bug*,request,praise,other|0.91|reports a malfunction and asks
m2|Great flashcards, they saved my week!|question,feedback,bug,request,praise*,other|0.97|
…
```

## Fixtures

`fixtures/valid.mini` ↔ `fixtures/canonical.json` (round-trip), `fixtures/escaping.mini` ↔ `fixtures/escaping.json`, and the negative cases `bad_count.mini`, `bad_arity.mini`, `bad_marker.mini`, `bad_type.mini`.

## Prompt block

Generate the transferable specification with `mini prompt cls`.
