# Comentarios con texto libre largo (JSONPlaceholder)

* Caso: **AHORRO PEQUEÑO (texto libre largo; sin ahorro en el total con lotes pequeños)**.
* Datos de referencia (5 registros): benchmark/public/data/comments.json, tramo de prueba (JSONPlaceholder, MIT). No sintético: datos públicos de prueba.
* Las «respuestas» son la serialización determinista de esos datos, no salida de un modelo.
* Las instrucciones las producen las herramientas reales: `mini from-schema` + `spec_block` (general), `mini build` (`make_prompt`, perfil mini-domain/1) y, para el especializado, `spec_block` sobre el contrato diseñado a mano y una plantilla compacta propia (`instruccion_compacta`, sin validar con un modelo real).
* El mapa (`mapa.json`) vive en la aplicación: el núcleo de .mini no lo conoce. También se imprime en la instrucción, así que sus tokens se cuentan.

```bash
python examples/optimizacion/reconstruir.py comentarios
```
