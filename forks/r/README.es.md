# `.mini-r` — Criterios de rúbrica analítica

**Prefijo:** `r`  **Versión:** 1  **Padre:** —  **Dominio:** educación / evaluación

Un criterio de rúbrica por línea con k niveles de desempeño ordenados (k declarado en la cabecera), un peso y la evidencia a inspeccionar.

## Estructura del registro

```
id:str | dimension:str | criterion:str | levels:list<str> | weight:float[0..1] | evidence:str
```

| # | campo | tipo | notas |
|---|---|---|---|
| 1 | `id` | `str` | núcleo |
| 2 | `dimension` | `str` | núcleo |
| 3 | `criterion` | `str` | núcleo |
| 4 | `levels` | `list<str>` | núcleo; descriptores de nivel ordenados |
| 5 | `weight` | `float[0..1]` | núcleo |
| 6 | `evidence` | `str` | núcleo |

## Claves de cabecera

| clave | tipo | requerida | descripción |
|---|---|---|---|
| `d` | `str` | no | fecha de generación AAAAMMDD |
| `l` | `str` | no | código de idioma |
| `t` | `str` | no |  |
| `k` | `int` | sí | número de niveles de desempeño |
| `scale` | `str` | no |  |
| `n` | `int` | sí | número de registros |
| `v` | `int` | no | versión del contrato |

## Ejemplo

```
r|n=12|d=20260603|l=en|t=Argumentative essay|k=4|scale=0-3
r1|Argument|Thesis clarity|absent or unclear,stated but vague,clear and focused,clear\, focused and original|0.2|Introduction paragraph
r2|Argument|Use of evidence|no evidence,evidence unrelated to claims,relevant evidence,relevant\, well-integrated evidence|0.2|Body paragraphs
…
```

## Fixtures

`fixtures/valid.mini` ↔ `fixtures/canonical.json` (ida y vuelta), `fixtures/escaping.mini` ↔ `fixtures/escaping.json`, y los casos negativos `bad_count.mini`, `bad_arity.mini`, `bad_type.mini`.

## Bloque de prompt

Genera la especificación transferible con `mini prompt r`.
