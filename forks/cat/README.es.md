# `.mini-cat` — Fichas de catálogo de productos

**Prefijo:** `cat`  **Versión:** 1  **Padre:** —  **Dominio:** comercio electrónico

Filas de catálogo con precio, moneda, stock, etiquetas y valoración opcional.

## Estructura del registro

```
sku:str | name:str | category:str | price:float[0..] | currency:enum{USD|PEN|EUR} | stock:int[0..] | tags:list<str>[0..10] | rating:float[0..5]?
```

| # | campo | tipo | notas |
|---|---|---|---|
| 1 | `sku` | `str` | núcleo |
| 2 | `name` | `str` | núcleo |
| 3 | `category` | `str` | núcleo |
| 4 | `price` | `float[0..]` | núcleo |
| 5 | `currency` | `enum{USD|PEN|EUR}` | núcleo |
| 6 | `stock` | `int[0..]` | núcleo |
| 7 | `tags` | `list<str>[0..10]` | núcleo |
| 8 | `rating` | `float[0..5]?` | núcleo; opcional |

## Claves de cabecera

| clave | tipo | requerida | descripción |
|---|---|---|---|
| `d` | `str` | no | fecha de generación AAAAMMDD |
| `store` | `str` | no |  |
| `cur` | `str` | no | moneda por defecto |
| `n` | `int` | sí | número de registros |
| `v` | `int` | no | versión del contrato |

## Ejemplo

```
cat|n=12|d=20260603|store=campus-shop|cur=USD
SKU-1001|Wireless headset|audio|89.9|USD|120|bluetooth,noise-cancelling|4.5
SKU-1002|USB-C hub 7-in-1|accessories|39.99|USD|300|usb-c,hdmi|4.2
…
```

## Fixtures

`fixtures/valid.mini` ↔ `fixtures/canonical.json` (ida y vuelta), `fixtures/escaping.mini` ↔ `fixtures/escaping.json`, y los casos negativos `bad_count.mini`, `bad_arity.mini`, `bad_type.mini`.

## Bloque de prompt

Genera la especificación transferible con `mini prompt cat`.
