# Errata de V7 (escalamiento por lote)

Fecha: 2026-09-30. Flujo de implementación v1 (rama `stream/v1`).
**Los datos crudos no se han modificado** (`llamadas.jsonl`, `meta.json`, `costo_real.json`,
`por_lote.csv` y `resumen.csv` siguen como estaban). Las correcciones están aquí y en los archivos
derivados `results/deepseek/errata.json` y `results/deepseek_volumen/errata.json`, que genera
`python experiments/v1_tokens/errata_v7_v8.py --escribir` y que comprueba
`tests/test_v1_consistencia.py`. Las llamadas son reales (DeepSeek, 2026-09-17) y las hicieron los autores
originales; aquí solo se releen, no se repiten.

## V7-E1. `lote_maximo_sin_perdida` de .mini dice 300 y el dato real es 200

* **Dice:** `results/deepseek/resumen.csv:3` (`mini,24,3705,…,300`).
* **Dato:** `results/deepseek/por_lote.csv:16`: con lote 300 el aprovechamiento de .mini es 93,3 %
  (3 llamadas, 2 cortadas). El mayor lote con aprovechamiento 100 % es **200**.
* **Causa:** `analizar.py:85` llama «buenas» a las llamadas con `aprovechados == solicitados` y
  `analizar.py:99` toma el mayor lote con **alguna** llamada buena (en L=300 una de tres salió completa).
  La salida legible del mismo script usa la definición correcta por lote (`analizar.py:117`), igual que
  `sitio/construir.py:838`, que muestra 200; y el volumen de 20.000 registros se ejecutó con L=200.
* **Corrección:** `lote_maximo_sin_perdida`: json = 100, mini = **200**. Para json el valor archivado (100)
  es correcto. Un lote «sin pérdida» es aquel en el que TODAS las repeticiones aprovechan todos los registros.

## V7-E2. `deepseek_volumen/meta.json` describe 1 de las 2 invocaciones

* **Dice:** `results/deepseek_volumen/meta.json:12-24`: `formatos: ["json"]`, `tamanos: [100]`,
  `llamadas: 200`, `usd_gastado: 1.6823`, ventana 22:45:06 a 22:54:06 UTC.
* **Dato:** `llamadas.jsonl` tiene **300** llamadas: 200 de json (lote 100; 20.000 registros; 1,6823 USD
  estimados con precio de lista) y **100 de mini** (lote 200; 20.000 registros; 0,7359 USD estimados), que
  no tienen `meta.json` ni ventana horaria (`llamadas.jsonl` no guarda fecha por llamada).
* **Corrección:** el manifiesto por invocación está en `results/deepseek_volumen/errata.json`. Total
  estimado con precio de lista: 2,4182 USD, igual al `estimado_con_precios_publicados_usd` de
  `costo_real.json:9`; tokens 1.138.042 de entrada y 1.730.641 de salida (coinciden con `costo_real.json`).

## V7-E3. El coste real de 0,78 USD no se puede verificar desde el repositorio

`results/deepseek_volumen/costo_real.json:5` declara 0,78 USD como diferencia del saldo del proveedor; el
saldo no está publicado ni hay captura. La estimación con el precio de lista (2,4182 USD, línea 9) sí se
reproduce desde `llamadas.jsonl`. Hasta aportar captura o factura, 0,78 USD es **«declarado, no
verificable»**, y el precio de referencia sobreestima unas 3,1 veces el importe declarado.

## V7-E4. Entradas repetidas y no comparables entre proveedores

`results/deepseek/meta.json:34` y `results/deepseek_volumen/meta.json:26`: «80 mensajes distintos,
repetidos». Los 3.705 registros por formato del barrido y los 20.000 del volumen reutilizan esos 80
mensajes (no son muestras independientes). Groq usó otra entrada (`results/groq/meta.json:29`, combinatoria
v2): las cifras de los dos proveedores no son comparables entre sí. El barrido de Groq es parcial por límites
de tasa (11 respuestas válidas de 48).

## V7-E5. Qué significa «payload» y por qué las cifras de V7 no se suman a las de V1

En la documentación del proyecto «payload» se usó con dos sentidos. Se fija este vocabulario:

| Término | Definición |
|---|---|
| `contenido_hojas` | cota inferior de contenido: cada valor hoja tokenizado por separado y sumado (columna `payload` de `benchmark/results/summary_12.csv`); no es un texto enviado |
| `documento` | texto completo del documento transmitido, sin contrato, mapa ni prompt (lo que se llamaba «solo payload», 35,64 %) |
| `estructura_compartida` | contrato o mapa de aplanado necesario para decodificar |
| `prompt_reutilizable` | bloque de instrucción de cada solicitud |
| `total` | conteo del texto completo enviado; no la suma de fragmentos |

Las cifras de V7 (p. ej. −63 % de tokens de salida por registro) son **tokens que informa el proveedor**
(su propio tokenizador) sobre respuestas generadas por el modelo; no son conteos locales de un documento
serializado (V1: −34,8 % a n=100 y −33,8 % a n=12, con o200k_base). No son intercambiables.

## Alcance

V7 es un estudio **exploratorio** de escalamiento y coste: un proveedor funcional, un modelo, una tarea
sintética, 3 repeticiones, sin referencia de exactitud. No es V2 ni V3 y no debe citarse como tal.
