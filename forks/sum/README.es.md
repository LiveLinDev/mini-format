# `.mini-sum` — Segmentos de resumen de microlección

**Prefijo:** `sum`  **Versión:** 1  **Padre:** —  **Dominio:** educación / microaprendizaje

Segmentos de resumen alineados en el tiempo de una lección grabada (microcontenido SIMA).

## Estructura del registro

```
id:str | t_start:int[0..] | t_end:int[0..] | title:str | summary:str | keywords:list<str>[1..10] | bloom:enum{L1|L2|L3|L4|L5|L6}
```

| # | campo | tipo | notas |
|---|---|---|---|
| 1 | `id` | `str` | núcleo |
| 2 | `t_start` | `int[0..]` | núcleo |
| 3 | `t_end` | `int[0..]` | núcleo |
| 4 | `title` | `str` | núcleo |
| 5 | `summary` | `str` | núcleo |
| 6 | `keywords` | `list<str>[1..10]` | núcleo |
| 7 | `bloom` | `enum{L1|L2|L3|L4|L5|L6}` | núcleo |

## Claves de cabecera

| clave | tipo | requerida | descripción |
|---|---|---|---|
| `d` | `str` | no | fecha de generación AAAAMMDD |
| `l` | `str` | no | código de idioma |
| `t` | `str` | no |  |
| `src` | `str` | no |  |
| `dur` | `int` | no | duración de la lección en segundos |
| `n` | `int` | sí | número de registros |
| `v` | `int` | no | versión del contrato |

## Ejemplo

```
sum|n=12|d=20260603|l=es|t=Biología celular|src=clase-64|dur=2520
s1|0|180|Introducción a la célula|La célula es la unidad básica de la vida; se distinguen procariotas y eucariotas.|célula,procariota,eucariota|L1
s2|180|420|Organelos y funciones|Mitocondria produce energía; el cloroplasto realiza la fotosíntesis; el núcleo guarda el ADN.|mitocondria,cloroplasto,núcleo|L2
…
```

## Fixtures

`fixtures/valid.mini` ↔ `fixtures/canonical.json` (ida y vuelta), `fixtures/escaping.mini` ↔ `fixtures/escaping.json`, y los casos negativos `bad_count.mini`, `bad_arity.mini`, `bad_type.mini`.

## Bloque de prompt

Genera la especificación transferible con `mini prompt sum`.
