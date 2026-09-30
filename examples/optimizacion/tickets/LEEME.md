# Tickets de soporte (hilo de «Cómo funciona»)

* Caso: **REPRESENTATIVO**.
* Datos de referencia (10 registros): los 10 tickets del hilo de «Cómo funciona» (examples/mesa-de-ayuda/grabaciones/mini/ok.mini; procedencia asistido_ia, no verificable). Sintético.
* Las «respuestas» son la serialización determinista de esos datos, no salida de un modelo.
* Las instrucciones las producen las herramientas reales: `mini from-schema` + `spec_block` (general), `mini build` (`make_prompt`, perfil mini-domain/1) y, para el especializado, `spec_block` sobre el contrato diseñado a mano y una plantilla compacta propia (`instruccion_compacta`, sin validar con un modelo real).
* El mapa (`mapa.json`) vive en la aplicación: el núcleo de .mini no lo conoce. También se imprime en la instrucción, así que sus tokens se cuentan.

```bash
python examples/optimizacion/reconstruir.py tickets
```
