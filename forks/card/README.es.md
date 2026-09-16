# `.mini-card` — Tarjetas (repetición espaciada)

**Prefijo:** `card`  **Versión:** 1  **Padre:** —  **Dominio:** educación / microaprendizaje

Una tarjeta por línea: anverso, reverso, pista opcional, etiquetas, nivel de Bloom y un factor de facilidad inicial para repetición espaciada.

## Estructura del registro

```
id:str | topic:str | front:str | back:str | hint:str? | tags:list<str>[0..8] | bloom:enum{L1|L2|L3|L4|L5|L6} | ease:float[1.3..3.0]
```

| # | campo | tipo | notas |
|---|---|---|---|
| 1 | `id` | `str` | núcleo |
| 2 | `topic` | `str` | núcleo |
| 3 | `front` | `str` | núcleo |
| 4 | `back` | `str` | núcleo |
| 5 | `hint` | `str?` | núcleo; opcional |
| 6 | `tags` | `list<str>[0..8]` | núcleo |
| 7 | `bloom` | `enum{L1|L2|L3|L4|L5|L6}` | núcleo |
| 8 | `ease` | `float[1.3..3.0]` | núcleo |

## Claves de cabecera

| clave | tipo | requerida | descripción |
|---|---|---|---|
| `d` | `str` | no | fecha de generación AAAAMMDD |
| `l` | `str` | no | código de idioma |
| `t` | `str` | no |  |
| `src` | `str` | no | id de la lección de origen |
| `n` | `int` | sí | número de registros |
| `v` | `int` | no | versión del contrato |

## Ejemplo

```
card|n=12|d=20260603|l=es|t=repaso transversal|src=clase-64
c1|Biología|¿Qué organelo realiza la fotosíntesis?|El cloroplasto, gracias a la clorofila.|Pigmento verde|célula,plantas|L1|2.5
c2|Química|¿Qué mide el pH?|La acidez o basicidad de una solución (0-14).|Iones H+|soluciones,ácidos|L2|2.5
…
```

## Fixtures

`fixtures/valid.mini` ↔ `fixtures/canonical.json` (ida y vuelta), `fixtures/escaping.mini` ↔ `fixtures/escaping.json`, y los casos negativos `bad_count.mini`, `bad_arity.mini`, `bad_type.mini`.

## Bloque de prompt

Genera la especificación transferible con `mini prompt card`.
