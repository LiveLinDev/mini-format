# `.mini-us` — Historias de usuario con criterios de aceptación

**Prefijo:** `us`  **Versión:** 1  **Padre:** —  **Dominio:** ingeniería de software / ágil

Historias del backlog de producto: épica, rol, objetivo, beneficio, criterios de aceptación, puntos de historia y prioridad MoSCoW.

## Estructura del registro

```
id:str | epic:str | role:str | goal:str | benefit:str | acceptance:list<str>[1..10] | sp:int[1..100] | priority:enum{must|should|could|wont}
```

| # | campo | tipo | notas |
|---|---|---|---|
| 1 | `id` | `str` | núcleo |
| 2 | `epic` | `str` | núcleo |
| 3 | `role` | `str` | núcleo |
| 4 | `goal` | `str` | núcleo |
| 5 | `benefit` | `str` | núcleo |
| 6 | `acceptance` | `list<str>[1..10]` | núcleo |
| 7 | `sp` | `int[1..100]` | núcleo |
| 8 | `priority` | `enum{must|should|could|wont}` | núcleo |

## Claves de cabecera

| clave | tipo | requerida | descripción |
|---|---|---|---|
| `d` | `str` | no | fecha de generación AAAAMMDD |
| `l` | `str` | no | código de idioma |
| `t` | `str` | no |  |
| `sprint` | `str` | no |  |
| `n` | `int` | sí | número de registros |
| `v` | `int` | no | versión del contrato |

## Ejemplo

```
us|n=12|d=20260603|l=en|t=SIMA backlog|sprint=S3
US-01|EP-01|student|upload a recorded lecture|I can study it later in small pieces|audio up to 200 MB accepted,credit estimate shown before confirming|5|must
US-02|EP-01|student|paste a transcript instead of audio|I can skip transcription when I already have notes|plain text accepted,same pipeline from generation stage|3|should
…
```

## Fixtures

`fixtures/valid.mini` ↔ `fixtures/canonical.json` (ida y vuelta), `fixtures/escaping.mini` ↔ `fixtures/escaping.json`, y los casos negativos `bad_count.mini`, `bad_arity.mini`, `bad_type.mini`.

## Bloque de prompt

Genera la especificación transferible con `mini prompt us`.
