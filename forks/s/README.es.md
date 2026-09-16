# `.mini-s` — Ítems de encuesta (Likert)

**Prefijo:** `s`  **Versión:** 1  **Padre:** —  **Dominio:** instrumentos de investigación

Ítems de encuesta tipo Likert agrupados por constructo, con tamaño de escala, etiquetas de anclaje y marca de puntuación invertida.

## Estructura del registro

```
id:str | construct:str | statement:str | scale:int[2..11] | anchors:list<str> | reverse:bool
```

| # | campo | tipo | notas |
|---|---|---|---|
| 1 | `id` | `str` | núcleo |
| 2 | `construct` | `str` | núcleo |
| 3 | `statement` | `str` | núcleo |
| 4 | `scale` | `int[2..11]` | núcleo |
| 5 | `anchors` | `list<str>` | núcleo |
| 6 | `reverse` | `bool` | núcleo |

## Claves de cabecera

| clave | tipo | requerida | descripción |
|---|---|---|---|
| `d` | `str` | no | fecha de generación AAAAMMDD |
| `l` | `str` | no | código de idioma |
| `t` | `str` | no |  |
| `k` | `int` | no | anclajes por ítem |
| `n` | `int` | sí | número de registros |
| `v` | `int` | no | versión del contrato |

## Ejemplo

```
s|n=12|d=20260603|l=en|t=Post-pilot satisfaction survey|k=2
q1|Usefulness|The platform helps me review lectures faster.|5|strongly disagree,strongly agree|false
q2|Usefulness|Generated quizzes reflect the lecture content.|5|strongly disagree,strongly agree|false
…
```

## Fixtures

`fixtures/valid.mini` ↔ `fixtures/canonical.json` (ida y vuelta), `fixtures/escaping.mini` ↔ `fixtures/escaping.json`, y los casos negativos `bad_count.mini`, `bad_arity.mini`, `bad_type.mini`.

## Bloque de prompt

Genera la especificación transferible con `mini prompt s`.
