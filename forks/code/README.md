# `.mini-code` — Programming exercises with tests

**Prefix:** `code`  **Version:** 1  **Parent:** —  **Domain:** education / programming

Auto-gradable programming exercises: statement, language, test expressions, expected type and hints.

## Record layout

```
id:str | bloom:enum{L1|L2|L3|L4|L5|L6} | topic:str | statement:str | lang:enum{python|javascript|java|sql|c|cpp|go} | tests:list<str>[1..10] | expected:str | hints:list<str>[0..5]
```

| # | field | type | notes |
|---|---|---|---|
| 1 | `id` | `str` | core |
| 2 | `bloom` | `enum{L1|L2|L3|L4|L5|L6}` | core |
| 3 | `topic` | `str` | core |
| 4 | `statement` | `str` | core |
| 5 | `lang` | `enum{python|javascript|java|sql|c|cpp|go}` | core |
| 6 | `tests` | `list<str>[1..10]` | core; boolean test expressions |
| 7 | `expected` | `str` | core |
| 8 | `hints` | `list<str>[0..5]` | core |

## Header keys

| key | type | required | description |
|---|---|---|---|
| `d` | `str` | no | generation date YYYYMMDD |
| `l` | `str` | no | language code |
| `t` | `str` | no |  |
| `n` | `int` | yes | number of records |
| `v` | `int` | no | contract version |

## Example

```
code|n=12|d=20260603|l=en|t=Intro programming lab 3
c1|L3|lists|Write a function maximum(xs) that returns the largest number in a non-empty list.|python|maximum([2\,8\,3])==8,maximum([-1\,-5])==-1|int or float|iterate once,track the best so far
c2|L3|strings|Write is_palindrome(s) ignoring case and spaces.|python|is_palindrome('Anita lava la tina'),not is_palindrome('hello')|bool|normalize first
…
```

## Fixtures

`fixtures/valid.mini` ↔ `fixtures/canonical.json` (round-trip), `fixtures/escaping.mini` ↔ `fixtures/escaping.json`, and the negative cases `bad_count.mini`, `bad_arity.mini`, `bad_type.mini`.

## Prompt block

Generate the transferable specification with `mini prompt code`.
