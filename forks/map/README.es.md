# `.mini-map` — Aristas de mapas conceptuales

**Prefijo:** `map`  **Versión:** 1  **Padre:** —  **Dominio:** educación / grafos de conocimiento

Una relación dirigida por línea (origen, relación, destino, peso, segmento de evidencia).

## Estructura del registro

```
src:str | rel:enum{is_a|has_part|performs|produces|causes|requires|contrasts|example_of} | dst:str | weight:float[0..1] | evidence:str?
```

| # | campo | tipo | notas |
|---|---|---|---|
| 1 | `src` | `str` | núcleo |
| 2 | `rel` | `enum{is_a|has_part|performs|produces|causes|requires|contrasts|example_of}` | núcleo |
| 3 | `dst` | `str` | núcleo |
| 4 | `weight` | `float[0..1]` | núcleo |
| 5 | `evidence` | `str?` | núcleo; opcional; id del segmento que respalda la arista |

## Claves de cabecera

| clave | tipo | requerida | descripción |
|---|---|---|---|
| `d` | `str` | no | fecha de generación AAAAMMDD |
| `l` | `str` | no | código de idioma |
| `t` | `str` | no |  |
| `src` | `str` | no |  |
| `n` | `int` | sí | número de registros |
| `v` | `int` | no | versión del contrato |

## Ejemplo

```
map|n=12|d=20260603|l=es|t=Biología celular|src=clase-64
célula|has_part|núcleo|0.9|s2
célula|has_part|mitocondria|0.9|s2
…
```

## Fixtures

`fixtures/valid.mini` ↔ `fixtures/canonical.json` (ida y vuelta), `fixtures/escaping.mini` ↔ `fixtures/escaping.json`, y los casos negativos `bad_count.mini`, `bad_arity.mini`, `bad_type.mini`.

## Bloque de prompt

Genera la especificación transferible con `mini prompt map`.
