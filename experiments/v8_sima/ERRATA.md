# Errata de V8 (integración en SIMA con deepseek-chat)

Fecha: 2026-09-30. Flujo de implementación v1 (rama `stream/v1`).
**`datos.json`, `resumen.json`, `analizar.py` y el README no se han modificado.** La verificación está en
`experiments/v8_sima/errata.json` (generado por `python experiments/v1_tokens/errata_v7_v8.py --escribir`) y la
comprueba `tests/test_v1_consistencia.py`.

## V8-E1. Conciliación de las clases completas: 343 + 5 + 2 = 350

**Estado: reconciliado con los contadores de `datos.json` y con la reejecución del lector sobre las
respuestas crudas disponibles; NO reconciliado registro a registro (pendiente).**

| Concepto | Valor | Dónde |
|---|---:|---|
| Ítems pedidos | 350 | suma de `clases[].bloques[].pedidos` |
| Válidos al llegar | 343 | suma de `recibidos` (`resumen.json:83`; `analizar.py:48`) |
| Líneas inválidas | 7 (5 E07, 2 E05) | suma de `lineas_invalidas` |
| Reparadas reenviando solo la línea | 5 | suma de `reparados` (las 5 son E07) |
| Repuestas como faltantes | 2 | suma de `recuperados` (las 2 son E05, bloque 1 de 3 de la clase 8) |
| Entregados | 350 | suma de `finales` |
| Bloques / llamadas | 31 / 38 | `clases[].bloques[]` |

* Identidad comprobada en **cada uno de los 31 bloques**: `pedidos = recibidos + inválidas` y
  `finales = recibidos + reparadas + recuperadas`; y en total 343 + 5 + 2 = 350 = pedidos = finales.
* `minifmt.parse(respuesta, contrato a, strict=False)` sobre las **17** respuestas crudas conservadas
  (clases 6, 7 y 8) reproduce exactamente `recibidos` y las líneas inválidas con su código (17 de 17).
* **Pendiente:** las clases 3 y 5 no conservan la respuesta cruda por bloque (lo dice el README) y nunca se
  guardaron las respuestas de reparación ni de reposición, de modo que los 5 + 2 ítems añadidos y los 343
  válidos de 14 bloques no se pueden reconstruir registro a registro desde el repositorio.
* El README (`README.md:32`) escribe «343 válidas al llegar, 7 líneas rechazadas… 5 reparadas… se entregaron las
  350»: es coherente con los contadores.

## V8-E2. Vocabulario confuso: «rechazadas» y «recibidos»

`README.md:32` llama «líneas rechazadas» a las 7 líneas inválidas; en `datos.json` el campo `rechazados`
cuenta otra cosa (líneas cuya reparación se rechazó: 1). `recibidos` es «líneas válidas al llegar» (343),
no «líneas recibidas» (350). Se recomienda citar siempre «líneas inválidas» y «válidas al llegar».

## V8-E3. Cosas que el archivo no dice

* Las clases se numeran 3, 5, 6, 7, 8: los ids 1, 2 y 4 no figuran y no se sabe si fueron ejecuciones
  descartadas (los ids 1 a 3 de `comparaciones` son otra serie).
* El coste (`costo_usd`) solo está en las 6 respuestas de las comparaciones pareadas (suma 0,015362 USD);
  las clases completas no lo registran y el método de cálculo es el de SIMA (repositorio externo,
  `sima_commit 2b47e17`, no disponible aquí).
* El ahorro de los bancos (30,6 a 32,8 %) es el mismo contenido generado en .mini y **reserializado** a JSON
  compacto y contado con o200k_base: compara representaciones, no dos generaciones.
* Con 40 preguntas el JSON se corta en 4.000 tokens (1 corrida): el «0 utilizables» depende de ese tope.

## V8-E4. Qué significa «payload»

Mismo vocabulario que en `experiments/v7_escalamiento/ERRATA.md` (V7-E5): `contenido_hojas`, `documento`,
`estructura_compartida`, `prompt_reutilizable` y `total`. Las cifras de V8 son tokens que informa el proveedor
(salida de las comparaciones) o conteos o200k_base de los bancos; no se mezclan con los de V1.

## Alcance

V8 es un caso de integración con un proveedor, un contrato y dos textos, sin réplicas independientes ni
exactitud frente a referencia (V6a del plan, no V2/V3). `experiments/README.en.md` no recibió la sección
V8 (fuera de la propiedad de este flujo: ver el informe).
