# `.mini-log` — Eventos de servicio / registros de incidentes

**Prefijo:** `log`  **Versión:** 1  **Padre:** —  **Dominio:** operaciones / observabilidad

Eventos estructurados emitidos por servicios: marca de tiempo, nivel, servicio, código, mensaje, etiquetas, id de traza y duración opcional.

## Estructura del registro

```
ts:str | level:enum{DEBUG|INFO|WARN|ERROR|CRITICAL} | service:str | code:str | message:str | tags:list<str>[0..10] | trace:str? | duration_ms:int[0..]?
```

| # | campo | tipo | notas |
|---|---|---|---|
| 1 | `ts` | `str` | núcleo; marca de tiempo ISO-8601 UTC |
| 2 | `level` | `enum{DEBUG|INFO|WARN|ERROR|CRITICAL}` | núcleo |
| 3 | `service` | `str` | núcleo |
| 4 | `code` | `str` | núcleo |
| 5 | `message` | `str` | núcleo |
| 6 | `tags` | `list<str>[0..10]` | núcleo |
| 7 | `trace` | `str?` | núcleo; opcional |
| 8 | `duration_ms` | `int[0..]?` | núcleo; opcional |

## Claves de cabecera

| clave | tipo | requerida | descripción |
|---|---|---|---|
| `d` | `str` | no | fecha de generación AAAAMMDD |
| `env` | `str` | no |  |
| `host` | `str` | no |  |
| `n` | `int` | sí | número de registros |
| `v` | `int` | no | versión del contrato |

## Ejemplo

```
log|n=12|d=20260603|env=staging|host=sima-app-01
2026-06-03T08:00:01Z|INFO|web|HTTP200|GET /dashboard served|user:26|t-1001|42
2026-06-03T08:00:05Z|INFO|worker|JOB_START|LessonJob 64 started stage transcribe|job:64,stage:transcribe|t-1002|
…
```

## Fixtures

`fixtures/valid.mini` ↔ `fixtures/canonical.json` (ida y vuelta), `fixtures/escaping.mini` ↔ `fixtures/escaping.json`, y los casos negativos `bad_count.mini`, `bad_arity.mini`, `bad_type.mini`.

## Bloque de prompt

Genera la especificación transferible con `mini prompt log`.
