# `.mini-cls` — Salidas de clasificación de texto multietiqueta

**Prefijo:** `cls`  **Versión:** 1  **Padre:** —  **Dominio:** PLN / triaje de soporte

Salidas de clasificador: el conjunto de etiquetas se escribe completo y las etiquetas predichas llevan *, así que tanto el espacio de etiquetas como la predicción se describen solos.

## Estructura del registro

```
id:str | text:str | labels:mlist<str>*1+ | conf:float[0..1] | rationale:str?
```

| # | campo | tipo | notas |
|---|---|---|---|
| 1 | `id` | `str` | núcleo |
| 2 | `text` | `str` | núcleo |
| 3 | `labels` | `mlist<str>*1+` | núcleo |
| 4 | `conf` | `float[0..1]` | núcleo |
| 5 | `rationale` | `str?` | núcleo; opcional |

## Claves de cabecera

| clave | tipo | requerida | descripción |
|---|---|---|---|
| `d` | `str` | no | fecha de generación AAAAMMDD |
| `l` | `str` | no | código de idioma |
| `model` | `str` | no |  |
| `k` | `int` | no | etiquetas del conjunto de etiquetas |
| `n` | `int` | sí | número de registros |
| `v` | `int` | no | versión del contrato |

## Ejemplo

```
cls|n=12|d=20260603|l=en|model=cls-support-2026|k=6
m1|The quiz froze after question 4, is that a known issue?|question*,feedback,bug*,request,praise,other|0.91|reports a malfunction and asks
m2|Great flashcards, they saved my week!|question,feedback,bug,request,praise*,other|0.97|
…
```

## Fixtures

`fixtures/valid.mini` ↔ `fixtures/canonical.json` (ida y vuelta), `fixtures/escaping.mini` ↔ `fixtures/escaping.json`, y los casos negativos `bad_count.mini`, `bad_arity.mini`, `bad_marker.mini`, `bad_type.mini`.

## Bloque de prompt

Genera la especificación transferible con `mini prompt cls`.
