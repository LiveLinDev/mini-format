# V1 (tokens y fidelidad): cómo se reproduce, sin red y sin API

Este archivo describe el procedimiento que reproduce V1 con datos congelados, tres tokenizadores y
reversibilidad verificada. No sustituye a `experiments/README.md` (que no se toca aquí).

## Un comando

```bash
python tools/ejecutar_v1.py                # completo
python tools/ejecutar_v1.py --con-v5       # completo + V5 (ancho del registro) con r50k_base
python tools/ejecutar_v1.py --rapido       # 3 dominios, n=1, 12, 100 (pruebas); no da veredicto
```

Requisitos: Python 3.9 o superior con `tiktoken`, `PyYAML`, `numpy` y `regex` (`pip install -e ".[bench]"`),
y Node 22 o superior (TOON oficial). **No hace falta red ni clave**: `benchmark/vocab_local.py` comprueba el
SHA-256 de los tres vocabularios de `benchmark/vocab` contra el oficial, rellena con ellos la caché de tiktoken
y bloquea cualquier conexión saliente (si algún paso intentara descargar, la corrida falla).
`experiments/comun.py::tokenizadores` es estricto: un tokenizador ausente o que cayera al respaldo de Python
puro es un error, no una omisión silenciosa.

La salida va a `evidencia/corridas/<run_id>/` (una carpeta por serie, cada una con `manifiesto.json` del contrato
`mini-format/corrida/1`). Lo archivado (`experiments/v1_tokens/results`, `benchmark/results`,
`benchmark/public/results.json`) **no se toca**: se compara fila a fila y la diferencia queda en el manifiesto.
Para escribir en otro sitio: `--salida-base DIR`. Para fijar el sello: `--sello AAAAMMDDtHHMMz`.

## Tiempo de ejecución (medido)

Medido el 2026-09-30 en Windows 10, Python 3.11.9, Node 22.14.0, tiktoken 0.14.0, con la máquina compartida con
otros procesos; el tiempo de cada paso queda en `resumen.tiempos_s` de cada manifiesto. Completo con `--con-v5`:
**211,1 s** (de ellos, V5: 96,2 s; V1 sin V5: 114,9 s). Por paso: benchmark público con los tres vocabularios
29,1 s, `benchmark/run_benchmark.py` 14,4 s, `experiments/v1_tokens/run.py` 27,8 s (el README de experimentos
dice «≈2 min»), serie con reversibilidad 41,5 s, criterio 0,6 s, conciliación 0,7 s. `--rapido`: unos 35 s
(medido en una ejecución de prueba: 34,4 s).

## Corridas

| Corrida | Qué reproduce | Archivos principales |
|---|---|---|
| `v1-linea_base_n12-<sello>` | `benchmark/run_benchmark.py` y la línea base de `experiments/v1_tokens/run.py` (n=12, 14 dominios); n=12 con los tres tokenizadores y reversibilidad | `benchmark_results/*.csv`, `linea_base_n12*.csv`, `tokens_n12_tres_tokenizadores.csv`, `reversibilidad_n12.csv` |
| `v1-serie_n-<sello>` | serie n = 1, 5, 10, 25, 50, 100, 250 (y 12) en las variantes `muestreo` y `ciclo`, 11 formatos, tres tokenizadores; criterio documental | `archivado_pipeline/*.csv` (mismas tablas que lo archivado), `tokens_largo.csv`, `reversibilidad.csv`, `ahorro_por_referencia.csv`, `criterio_v1_resultado.{json,md}` |
| `v1-publicos-<sello>` | `benchmark/public/run.py` con los 4 snapshots (hash verificado) y cada vocabulario | `results_<tokenizador>.{json,csv}`, `ahorro_publicos_por_tokenizador.csv` |
| `v1-conciliacion-<sello>` | las cuatro cifras 33,8 / 34,8 / 34,99 / 35,64 %, el desglose por dominio y tokenizador, y la verificación de las erratas V7/V8 | `conciliacion_cifras.{json,md}`, `desglose_dominio_tokenizador.csv`, `errata_v7_v8_verificacion.json` |
| `v5-ancho-<sello>` (con `--con-v5`) | `experiments/v5_ancho/correr.py` con los tres tokenizadores | `ancho_largo.csv`, `ancho_resumen.csv`, `meta.json` |

Cada carpeta lleva además `procedencia_datos.json` (fuente, licencia, fecha de captura, hash y carácter sintético
de cada conjunto) y el manifiesto con los conjuntos, contratos y tokenizadores (versión y SHA-256 del
vocabulario), el código ejecutado (`commit` o `snapshot_sha256` si el árbol no estaba limpio), el comando y el
tiempo de cada paso (`resumen.tiempos_s`).

## Reversibilidad antes de contar

`experiments/v1_tokens/reversibilidad.py` decodifica cada texto con un decodificador independiente del
codificador y compara con el objeto original. Un comparador solo entra en una comparación si su documento es
`reversible` o `reversible_normalizado` (normalización nombrada: `None` equivale a clave ausente; el
serializador .mini añade `header.n` y `header.v`). Si es `no_reversible` se cuenta su tamaño pero queda fuera
(`comparacion_valida = False`, `ahorro_por_referencia.csv` lo marca `excluido_no_reversible` con la causa).

Formatos: los 8 archivados (`json_pretty`, `json_compact`, `yaml`, `xml`, `csv`, `toon`, `toon_flat`, `mini`) y 3
comparadores reversibles de `benchmark/public/baselines.py` (`xml_tipado`, `csv_reversible`, `toon_reversible`;
se elige la variante de aplanado con menos tokens entre las reversibles y su mapa se cuenta aparte). La columna
`decodificacion` dice si el formato se decodifica solo (`autocontenida`), con el contrato del dominio
(`con_contrato`: XML y TOON plano de `formats.py`, y el propio .mini) o con un mapa contado aparte (`con_mapa`).

## Criterio documental

La interpretación (fijada antes del análisis, sujeta a aprobación del asesor) está en
[`CRITERIO_V1.md`](CRITERIO_V1.md) y [`criterio_v1.json`](criterio_v1.json); `criterio.py` no contiene otro
umbral. `criterio_v1_resultado.md` publica el veredicto primario y todas las lecturas alternativas (media por
dominio frente a agregado por suma, n=12, `ciclo`, intersección de dominios y efecto de n) con IC95 por
bootstrap de dominios.

## Vocabulario (qué es «payload»)

`contenido_hojas` (cota inferior, hojas tokenizadas por separado; antes la columna `payload` de
`summary_12.csv`), `documento` (texto completo del documento; antes «solo payload»), `estructura_compartida`
(contrato o mapa), `prompt_reutilizable` y `total` (conteo del texto completo enviado, no suma de fragmentos).

## Datos

* 14 dominios de `benchmark/domains.py`: escritos a mano (sintéticos), 12 registros base por dominio (168); `q`
  extiende a `a`. **n > 12 repite esos 12 registros con identificadores nuevos** (`replicacion_de_base`): no son
  muestras independientes.
* 4 snapshots públicos (1.902 objetos únicos): DummyJSON (MIT), JSONPlaceholder (MIT) y USGS (crédito), con
  SHA-256 en `benchmark/public/sources.json` y licencias en `benchmark/public/THIRD_PARTY.md`.
* La muestra independiente de V1 son los 4 snapshots y los 12 registros base, no las series de replicación.

## Pruebas

```bash
python -m pytest -q -p no:cacheprovider tests/test_v1_reversibilidad.py tests/test_v1_criterio.py \
    tests/test_v1_consistencia.py tests/test_v1_ejecutar_rapido.py
```

`test_v1_consistencia.py` recalcula desde los CSV de las corridas las cifras del manifiesto, la conciliación y el
veredicto; `test_v1_ejecutar_rapido.py` ejecuta `--rapido` de extremo a extremo en un directorio temporal.

## Límites

Los tres tokenizadores son de la misma familia BPE de OpenAI: no sustituyen a un tokenizador independiente
(Anthropic, Google, DeepSeek), para los que tiktoken es una aproximación; y son conteos locales de texto, no el
conteo de solicitud ni el `usage` de ningún proveedor. Las erratas de V7 y V8 están en
`experiments/v7_escalamiento/ERRATA.md` y `experiments/v8_sima/ERRATA.md`.
