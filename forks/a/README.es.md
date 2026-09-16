# `.mini-a` — Ítems de evaluación (opción múltiple, Bloom + IRT 3PL + metadatos CAT)

**Prefijo:** `a`  **Versión:** 1  **Padre:** —  **Dominio:** educación / evaluación adaptativa

Un ítem de evaluación de opción múltiple por línea, tal como los genera SIMA desde la transcripción de una lección. La opción seleccionada es la respuesta correcta; los parámetros IRT alimentan un test adaptativo computarizado.

## Estructura del registro

```
id:str | bloom:enum{L1|L2|L3|L4|L5|L6} | topic:str | statement:str | options:mlist<str>[2..6]*1 | irt:tuple(a:float,b:float,c:float) | difficulty:int[1..5] | cat:tuple(area:str,exposure_cap:float,demand:enum)
```

| # | campo | tipo | notas |
|---|---|---|---|
| 1 | `id` | `str` | núcleo; identificador del ítem |
| 2 | `bloom` | `enum{L1|L2|L3|L4|L5|L6}` | núcleo; nivel de Bloom |
| 3 | `topic` | `str` | núcleo |
| 4 | `statement` | `str` | núcleo; enunciado de la pregunta |
| 5 | `options` | `mlist<str>[2..6]*1` | núcleo; opciones de respuesta; la correcta lleva * |
| 6 | `irt` | `tuple(a:float,b:float,c:float)` | núcleo |
| 7 | `difficulty` | `int[1..5]` | núcleo |
| 8 | `cat` | `tuple(area:str,exposure_cap:float,demand:enum)` | núcleo |

## Claves de cabecera

| clave | tipo | requerida | descripción |
|---|---|---|---|
| `n` | `int` | sí | número de registros |
| `v` | `int` | no | versión del contrato |
| `m` | `str` | no | modelo psicométrico, p. ej. IRT3PL |
| `d` | `str` | no | fecha de generación AAAAMMDD |
| `l` | `str` | no | código de idioma |
| `t` | `str` | no | tema del banco |
| `bd` | `list` | no | distribución de Bloom L1..L6 |
| `cat` | `tuple` | no |  |
| `k` | `int` | no | opciones por ítem (cada lista de opciones debe tener exactamente k elementos) |

## Ejemplo

```
a|n=12|m=IRT3PL|d=20260603|l=es|t=evaluación transversal|bd=1,1,1,1,1,1|cat=0,-3,3,0.3,12,SH|k=4
i1|L1|Biología|¿Dónde ocurre principalmente la fotosíntesis?|cloroplastos*,núcleo,mitocondria,ribosoma|0.9,-1,0.25|1|biología,0.2,low
i2|L2|Química|¿Qué representa el pH de una solución?|acidez o basicidad*,masa molecular,temperatura,presión osmótica|1.1,-0.3,0.25|2|química,0.2,medium
…
```

## Fixtures

`fixtures/valid.mini` ↔ `fixtures/canonical.json` (ida y vuelta), `fixtures/escaping.mini` ↔ `fixtures/escaping.json`, y los casos negativos `bad_count.mini`, `bad_arity.mini`, `bad_marker.mini`, `bad_type.mini`.

## Bloque de prompt

Genera la especificación transferible con `mini prompt a`.
