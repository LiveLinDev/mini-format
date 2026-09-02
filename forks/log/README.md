# `.mini-log` — Service events / incident records

**Prefix:** `log`  **Version:** 1  **Parent:** —  **Domain:** operations / observability

Structured events emitted by services: timestamp, level, service, code, message, tags, trace id and optional duration.

## Record layout

```
ts:str | level:enum{DEBUG|INFO|WARN|ERROR|CRITICAL} | service:str | code:str | message:str | tags:list<str>[0..10] | trace:str? | duration_ms:int[0..]?
```

| # | field | type | notes |
|---|---|---|---|
| 1 | `ts` | `str` | core; ISO-8601 UTC timestamp |
| 2 | `level` | `enum{DEBUG|INFO|WARN|ERROR|CRITICAL}` | core |
| 3 | `service` | `str` | core |
| 4 | `code` | `str` | core |
| 5 | `message` | `str` | core |
| 6 | `tags` | `list<str>[0..10]` | core |
| 7 | `trace` | `str?` | core; optional |
| 8 | `duration_ms` | `int[0..]?` | core; optional |

## Header keys

| key | type | required | description |
|---|---|---|---|
| `d` | `str` | no | generation date YYYYMMDD |
| `env` | `str` | no |  |
| `host` | `str` | no |  |
| `n` | `int` | yes | number of records |
| `v` | `int` | no | contract version |

## Example

```
log|n=12|d=20260603|env=staging|host=sima-app-01
2026-06-03T08:00:01Z|INFO|web|HTTP200|GET /dashboard served|user:26|t-1001|42
2026-06-03T08:00:05Z|INFO|worker|JOB_START|LessonJob 64 started stage transcribe|job:64,stage:transcribe|t-1002|
…
```

## Fixtures

`fixtures/valid.mini` ↔ `fixtures/canonical.json` (round-trip), `fixtures/escaping.mini` ↔ `fixtures/escaping.json`, and the negative cases `bad_count.mini`, `bad_arity.mini`, `bad_type.mini`.

## Prompt block

Generate the transferable specification with `mini prompt log`.
