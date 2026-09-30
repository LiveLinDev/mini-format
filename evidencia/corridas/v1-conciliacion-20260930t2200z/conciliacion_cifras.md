# Conciliación de cifras de ahorro de V1

Cada cifra se deriva de un archivo de resultados; las cuatro miden cosas distintas y no son intercambiables.

| Cifra citada | Recalculada | Estadístico | Conjunto | Tokenizador | Qué cuenta | Denominador |
|---|---:|---|---|---|---|---|
| 33,8 % | 33,81 % | media aritmética de 14 ahorros por dominio (cada dominio pesa igual) | 14 dominios x 12 registros base (168 registros escritos a mano; q extiende a a), protocolo 'ciclo' | o200k_base | documento (sin contrato, sin mapa, sin prompt) | tokens de JSON compacto de cada dominio (n=12); la media no tiene un denominador único; Σ = 10.714 |
| 34,8 % | 34,81 % | media aritmética de 14 ahorros por dominio | 14 dominios x 100 registros por dominio, variante 'muestreo'; los 12 registros base se REPITEN (8 pasadas + 4) con identificadores nuevos | o200k_base | documento (sin contrato, sin mapa, sin prompt) | tokens de JSON compacto de cada dominio (n=100); Σ = 85.401 |
| 34,99 % | 34,99 % | agregado por suma (1 - Σ tokens .mini / Σ tokens JSON compacto) sobre los 4 snapshots | 4 snapshots públicos con SHA-256 (DummyJSON products y users, JSONPlaceholder comments, USGS earthquakes): 1.902 objetos únicos, sin repetición | o200k_base | documento + contrato compartido (estructura) de .mini frente al documento de JSON compacto | Σ tokens de JSON compacto (documento; su esquema no se cuenta: JSON es autodescriptivo); Σ = 468.849 |
| 35,64 % | 35,64 % | agregado por suma (1 - Σ tokens .mini / Σ tokens JSON compacto) sobre los 4 snapshots | 4 snapshots públicos con SHA-256 (DummyJSON products y users, JSONPlaceholder comments, USGS earthquakes): 1.902 objetos únicos, sin repetición | o200k_base | documento (sin contrato, sin mapa, sin prompt) | Σ tokens de JSON compacto (documento); Σ = 468.849 |

## Lecturas de las mismas series con otra estadística

* 33,8 %: agregado por suma de la misma serie = 33,53 %.
* 34,8 %: agregado por suma de la misma serie = 34,31 %.
* 35,64 %: con el prompt de .mini frente al documento JSON = 34,61 % (nota: con el prompt de generación de .mini (en inglés) frente al documento JSON sin instrucción: la asimetría perjudica a .mini).

## Archivos de origen

* **33,8 %** (linea_base_n12.media_por_dominio): evidencia/corridas/v1-linea_base_n12-20260930t2200z/benchmark_results/summary_12.csv (columna mini_vs_json_compact_pct, redondeada a 1 decimal); evidencia/corridas/v1-linea_base_n12-20260930t2200z/benchmark_results/tokens.csv (tokens sin redondear). Comando: `python benchmark/run_benchmark.py`.
* **34,8 %** (serie_n100_muestreo.media_por_dominio): evidencia/corridas/v1-serie_n-20260930t2200z/archivado_pipeline/ahorro_resumen.csv (fila o200k_base / muestreo / n=100 / json_compact, columna media); evidencia/corridas/v1-serie_n-20260930t2200z/archivado_pipeline/tokens.csv (tokens por dominio). Comando: `python experiments/v1_tokens/run.py`.
* **34,99 %** (publico.suma.documento_mas_contrato): evidencia/corridas/v1-publicos-20260930t2200z/results_o200k_base.json (campos formats.mini.payload_plus_schema_tokens y formats.json_compact.tokens; no se guarda como campo: se calcula). Comando: `python benchmark/public/run.py`.
* **35,64 %** (publico.suma.documento_sin_contrato): evidencia/corridas/v1-publicos-20260930t2200z/results_o200k_base.json (campo summary.weighted_savings_pct.json_compact). Comando: `python benchmark/public/run.py`.

## Vocabulario (la palabra «payload» tenía dos significados)

* **contenido_hojas**: Cota inferior de contenido: cada valor hoja del objeto se tokeniza por separado y se suman los conteos (benchmark/formats.py::payload_tokens; columna `payload` de benchmark/results/summary_12.csv). No es un texto que se envíe a un modelo.
* **documento**: Texto completo del documento transmitido (encabezado, metadatos, sintaxis y contenido), sin contrato, mapa ni prompt. Es lo que los documentos del equipo llamaban 'solo payload' (35,64 %).
* **estructura_compartida**: Contrato (.mini: JSON compacto del contrato) o mapa de aplanado (CSV reversible, TOON plano) que el receptor necesita para decodificar. 0 para JSON, YAML, XML tipado y TOON nativo, que son autodescriptivos.
* **prompt_reutilizable**: Bloque de instrucción que acompaña a cada solicitud: spec_block del contrato para .mini; instrucción + JSON Schema (json_schema) para JSON compacto. Se solapa con la estructura compartida (describe el mismo contrato en lenguaje natural): no se suman.
* **total**: Conteo del texto completo enviado: tokenizer.count(estructura_o_prompt + '\n' + documento). No es la suma de conteos de fragmentos.

## Ahorro de .mini frente a JSON compacto según la unidad contada

| Serie | Tokenizador | Unidad | Media por dominio | Agregado por suma |
|---|---|---|---:|---:|
| n12_ciclo | o200k_base | documento | 33,80 % | 33,53 % |
| n12_ciclo | o200k_base | documento + estructura compartida | -12,42 % | -9,68 % |
| n12_ciclo | o200k_base | documento + prompt (es) | 8,99 % | 12,17 % |
| n12_ciclo | o200k_base | documento + prompt (en) | 13,47 % | 16,19 % |
| n12_ciclo | cl100k_base | documento | 31,63 % | 30,88 % |
| n12_ciclo | cl100k_base | documento + estructura compartida | -13,55 % | -10,99 % |
| n12_ciclo | cl100k_base | documento + prompt (es) | 4,08 % | 7,38 % |
| n12_ciclo | cl100k_base | documento + prompt (en) | 11,36 % | 13,86 % |
| n12_ciclo | r50k_base | documento | 29,47 % | 28,56 % |
| n12_ciclo | r50k_base | documento + estructura compartida | -15,27 % | -11,81 % |
| n12_ciclo | r50k_base | documento + prompt (es) | -3,47 % | 0,84 % |
| n12_ciclo | r50k_base | documento + prompt (en) | 9,10 % | 11,94 % |
| n100_muestreo | o200k_base | documento | 34,81 % | 34,31 % |
| n100_muestreo | o200k_base | documento + estructura compartida | 28,98 % | 28,88 % |
| n100_muestreo | o200k_base | documento + prompt (es) | 30,52 % | 30,75 % |
| n100_muestreo | o200k_base | documento + prompt (en) | 31,29 % | 31,42 % |
| n100_muestreo | cl100k_base | documento | 32,74 % | 31,71 % |
| n100_muestreo | cl100k_base | documento + estructura compartida | 27,05 % | 26,47 % |
| n100_muestreo | cl100k_base | documento + prompt (es) | 28,02 % | 27,84 % |
| n100_muestreo | cl100k_base | documento + prompt (en) | 29,26 % | 28,91 % |
| n100_muestreo | r50k_base | documento | 30,43 % | 29,17 % |
| n100_muestreo | r50k_base | documento + estructura compartida | 24,80 % | 24,12 % |
| n100_muestreo | r50k_base | documento + prompt (es) | 24,71 % | 24,61 % |
| n100_muestreo | r50k_base | documento + prompt (en) | 26,92 % | 26,46 % |

Para JSON compacto la estructura compartida es 0 (es autodescriptivo), pero su instrucción equivalente (JSON Schema) no lo es: por eso se publican las tres unidades y ninguna se elige por su resultado. El desglose por dominio y tokenizador está en `desglose_dominio_tokenizador.csv`.
