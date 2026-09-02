# `.mini-s` — Survey items (Likert)

**Prefix:** `s`  **Version:** 1  **Parent:** —  **Domain:** research instruments

Likert-type survey items grouped by construct, with scale size, anchor labels and reverse-scoring flag.

## Record layout

```
id:str | construct:str | statement:str | scale:int[2..11] | anchors:list<str> | reverse:bool
```

| # | field | type | notes |
|---|---|---|---|
| 1 | `id` | `str` | core |
| 2 | `construct` | `str` | core |
| 3 | `statement` | `str` | core |
| 4 | `scale` | `int[2..11]` | core |
| 5 | `anchors` | `list<str>` | core |
| 6 | `reverse` | `bool` | core |

## Header keys

| key | type | required | description |
|---|---|---|---|
| `d` | `str` | no | generation date YYYYMMDD |
| `l` | `str` | no | language code |
| `t` | `str` | no |  |
| `k` | `int` | no | anchors per item |
| `n` | `int` | yes | number of records |
| `v` | `int` | no | contract version |

## Example

```
s|n=12|d=20260603|l=en|t=Post-pilot satisfaction survey|k=2
q1|Usefulness|The platform helps me review lectures faster.|5|strongly disagree,strongly agree|false
q2|Usefulness|Generated quizzes reflect the lecture content.|5|strongly disagree,strongly agree|false
…
```

## Fixtures

`fixtures/valid.mini` ↔ `fixtures/canonical.json` (round-trip), `fixtures/escaping.mini` ↔ `fixtures/escaping.json`, and the negative cases `bad_count.mini`, `bad_arity.mini`, `bad_type.mini`.

## Prompt block

Generate the transferable specification with `mini prompt s`.
