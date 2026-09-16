# `.mini-tc` — Casos de prueba de software

**Prefijo:** `tc`  **Versión:** 1  **Padre:** —  **Dominio:** ingeniería de software / QA

Casos de prueba manuales o automatizados: módulo, título, precondición, pasos ordenados, resultado esperado, prioridad, tipo y marca de automatización.

## Estructura del registro

```
id:str | module:str | title:str | precondition:str | steps:list<str>[1..20] | expected:str | priority:enum{low|medium|high|critical} | type:enum{functional|integration|performance|security|usability|regression} | automated:bool
```

| # | campo | tipo | notas |
|---|---|---|---|
| 1 | `id` | `str` | núcleo |
| 2 | `module` | `str` | núcleo |
| 3 | `title` | `str` | núcleo |
| 4 | `precondition` | `str` | núcleo |
| 5 | `steps` | `list<str>[1..20]` | núcleo |
| 6 | `expected` | `str` | núcleo |
| 7 | `priority` | `enum{low|medium|high|critical}` | núcleo |
| 8 | `type` | `enum{functional|integration|performance|security|usability|regression}` | núcleo |
| 9 | `automated` | `bool` | núcleo |

## Claves de cabecera

| clave | tipo | requerida | descripción |
|---|---|---|---|
| `d` | `str` | no | fecha de generación AAAAMMDD |
| `l` | `str` | no | código de idioma |
| `t` | `str` | no |  |
| `proj` | `str` | no |  |
| `n` | `int` | sí | número de registros |
| `v` | `int` | no | versión del contrato |

## Ejemplo

```
tc|n=12|d=20260603|l=en|t=SIMA release 1.2 regression|proj=SIMA
TC-001|auth|Login with valid credentials|User registered and active|open /login,enter valid email and password,click Sign in|Dashboard is shown and session cookie is set|high|functional|true
TC-002|auth|Login with wrong password|User registered|open /login,enter valid email and wrong password,click Sign in|Error message; no session created|high|functional|true
…
```

## Fixtures

`fixtures/valid.mini` ↔ `fixtures/canonical.json` (ida y vuelta), `fixtures/escaping.mini` ↔ `fixtures/escaping.json`, y los casos negativos `bad_count.mini`, `bad_arity.mini`, `bad_type.mini`.

## Bloque de prompt

Genera la especificación transferible con `mini prompt tc`.
