# `.mini-us` — User stories with acceptance criteria

**Prefix:** `us`  **Version:** 1  **Parent:** —  **Domain:** software engineering / agile

Product-backlog stories: epic, role, goal, benefit, acceptance criteria, story points and MoSCoW priority.

## Record layout

```
id:str | epic:str | role:str | goal:str | benefit:str | acceptance:list<str>[1..10] | sp:int[1..100] | priority:enum{must|should|could|wont}
```

| # | field | type | notes |
|---|---|---|---|
| 1 | `id` | `str` | core |
| 2 | `epic` | `str` | core |
| 3 | `role` | `str` | core |
| 4 | `goal` | `str` | core |
| 5 | `benefit` | `str` | core |
| 6 | `acceptance` | `list<str>[1..10]` | core |
| 7 | `sp` | `int[1..100]` | core |
| 8 | `priority` | `enum{must|should|could|wont}` | core |

## Header keys

| key | type | required | description |
|---|---|---|---|
| `d` | `str` | no | generation date YYYYMMDD |
| `l` | `str` | no | language code |
| `t` | `str` | no |  |
| `sprint` | `str` | no |  |
| `n` | `int` | yes | number of records |
| `v` | `int` | no | contract version |

## Example

```
us|n=12|d=20260603|l=en|t=SIMA backlog|sprint=S3
US-01|EP-01|student|upload a recorded lecture|I can study it later in small pieces|audio up to 200 MB accepted,credit estimate shown before confirming|5|must
US-02|EP-01|student|paste a transcript instead of audio|I can skip transcription when I already have notes|plain text accepted,same pipeline from generation stage|3|should
…
```

## Fixtures

`fixtures/valid.mini` ↔ `fixtures/canonical.json` (round-trip), `fixtures/escaping.mini` ↔ `fixtures/escaping.json`, and the negative cases `bad_count.mini`, `bad_arity.mini`, `bad_type.mini`.

## Prompt block

Generate the transferable specification with `mini prompt us`.
