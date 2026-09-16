# `.mini-ner` — Anotaciones de entidades nombradas

**Prefijo:** `ner`  **Versión:** 1  **Padre:** —  **Dominio:** PLN / etiquetado de datos

Una mención de entidad por línea (patrón relacional: varias líneas comparten un id de documento).

## Estructura del registro

```
doc:str | start:int[0..] | end:int[0..] | text:str | type:enum{PERSON|ORG|LOC|DATE|PRODUCT|CONCEPT|MISC} | conf:float[0..1]
```

| # | campo | tipo | notas |
|---|---|---|---|
| 1 | `doc` | `str` | núcleo |
| 2 | `start` | `int[0..]` | núcleo |
| 3 | `end` | `int[0..]` | núcleo |
| 4 | `text` | `str` | núcleo |
| 5 | `type` | `enum{PERSON|ORG|LOC|DATE|PRODUCT|CONCEPT|MISC}` | núcleo |
| 6 | `conf` | `float[0..1]` | núcleo |

## Claves de cabecera

| clave | tipo | requerida | descripción |
|---|---|---|---|
| `d` | `str` | no | fecha de generación AAAAMMDD |
| `l` | `str` | no | código de idioma |
| `model` | `str` | no |  |
| `schema` | `str` | no |  |
| `n` | `int` | sí | número de registros |
| `v` | `int` | no | versión del contrato |

## Ejemplo

```
ner|n=12|d=20260603|l=en|model=ner-base-2026|schema=ontonotes-lite
d1|0|17|Whisper|PRODUCT|0.98
d1|25|31|OpenAI|ORG|0.99
…
```

## Fixtures

`fixtures/valid.mini` ↔ `fixtures/canonical.json` (ida y vuelta), `fixtures/escaping.mini` ↔ `fixtures/escaping.json`, y los casos negativos `bad_count.mini`, `bad_arity.mini`, `bad_type.mini`.

## Bloque de prompt

Genera la especificación transferible con `mini prompt ner`.
