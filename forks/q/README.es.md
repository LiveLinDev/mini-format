# `.mini-q` — Ítems de quiz formativo (evaluación + retroalimentación)

**Prefijo:** `q`  **Versión:** 1  **Padre:** a  **Dominio:** educación / evaluación formativa

Familia derivada de 'a': el mismo núcleo, más retroalimentación, pista y objetivo de aprendizaje al final para que un quiz pueda explicar cada respuesta.

## Estructura del registro

```
id:str | bloom:enum{L1|L2|L3|L4|L5|L6} | topic:str | statement:str | options:mlist<str>[2..6]*1 | irt:tuple(a:float,b:float,c:float) | difficulty:int[1..5] | cat:tuple(area:str,exposure_cap:float,demand:enum) || feedback:str? | hint:str? | objective:str?
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
| 9 | `feedback` | `str?` | extensión; opcional; explicación mostrada tras responder |
| 10 | `hint` | `str?` | extensión; opcional |
| 11 | `objective` | `str?` | extensión; opcional; objetivo de aprendizaje |

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
q|n=12|m=IRT3PL|d=20260603|l=es|t=cuestionario formativo|bd=1,1,1,1,1,1|cat=0,-3,3,0.3,12,SH|k=4
i1|L1|Biología|¿Dónde ocurre principalmente la fotosíntesis?|cloroplastos*,núcleo,mitocondria,ribosoma|0.9,-1,0.25|1|biología,0.2,low|La fotosíntesis ocurre en los cloroplastos, donde está la clorofila.|Piensa en el pigmento verde.|Identificar organelos vegetales
i2|L2|Química|¿Qué representa el pH de una solución?|acidez o basicidad*,masa molecular,temperatura,presión osmótica|1.1,-0.3,0.25|2|química,0.2,medium|El pH mide la concentración de iones hidrógeno: acidez o basicidad.|Escala de 0 a 14.|Interpretar la escala de pH
…
```

## Fixtures

`fixtures/valid.mini` ↔ `fixtures/canonical.json` (ida y vuelta), `fixtures/escaping.mini` ↔ `fixtures/escaping.json`, y los casos negativos `bad_count.mini`, `bad_arity.mini`, `bad_marker.mini`, `bad_type.mini`.

## Bloque de prompt

Genera la especificación transferible con `mini prompt q`.
