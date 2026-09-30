# Arnés experimental V2 / V3b / V4 — generación, truncamiento, latencia y costo

Arnés para medir, con modelos de varios proveedores, si una salida estructurada llega **válida** cuando un equipo pide
JSON (con instrucción mínima, con el contrato en el prompt o con restricción nativa) o `.mini` (con su biblioteca), y
qué cambia si se permite **una** reparación selectiva. Sigue el Plan de Validación v3 (§5 V2, §6 V3b, §7.1 V4).

> **Estado (30/09/2026).** El arnés está completo para V2, V3b y V4 y se ha ejecutado **solo** con el adaptador
> **simulado** y con material **asistido por IA** de prueba. **No se ha llamado a ningún proveedor real**, no hay
> ningún presupuesto autorizado y no hay resultados del estudio. Las cifras de este directorio salen del simulador, cuyas
> tasas de falla son supuestos: validan el arnés, no dicen nada de formatos ni de modelos reales.
>
> Lo que falta para el estudio real no es código: hace falta (1) una persona que **autorice el presupuesto** en el YAML,
> (2) **tarifas verificadas** para todos los modelos (hoy `groq:llama-3.3-70b-versatile` no tiene tarifa verificada),
> (3) claves de API y (4) las decisiones que se listan en «Qué necesita el equipo».

## Contenido

```
experiments/generativo/
├── run.py                  CLI: ejecutar · dry-run · preparar · preparar-reparacion · importar · evidencia
├── analyze.py              análisis: conglomerados, latencia, costo, meta V2, comparaciones, figuras
├── configs/
│   ├── piloto.yaml         4 tareas × 3 modelos × 6 repeticiones (+ V3b)
│   └── estudio.yaml        matriz PROPUESTA del estudio (no autorizada)
├── arnes/
│   ├── tareas.py           catálogo de tareas desde forks/ (+ estrés controlado)
│   ├── brazos.py           prompts y lectores de A, A0, B, C, D y de los brazos X+1
│   ├── json_tolerante.py   escáner tolerante y reparación selectiva para JSON
│   ├── reparar.py          una ronda de reparación, común a .mini y JSON (+ auditoria.py)
│   ├── metricas.py         sintaxis, contrato, exactitud y validez final
│   ├── ejecucion.py        matriz, almacén JSONL, ejecutor con llamada controlada
│   ├── presupuesto.py      presupuesto, autorización, libro de gasto
│   ├── tarifas.py · usage.py   tarifas verificadas y usage por categorías
│   ├── plan.py             orden aleatorizado, hashes, estado del estudio, candado
│   ├── costos.py           dry-run: recuento de llamadas y costo esperado/máximo
│   ├── importacion.py      material asistido por IA
│   ├── evidencia.py        corridas V2/V3b/V4 con tools/evidencia_lib
│   ├── simulador.py        extensión del adaptador simulado para las condiciones del Plan
│   └── estadistica.py · truncamiento.py
├── tests/                  177 pruebas (red bloqueada en todas; una se activa solo si está el cálculo de economía)
└── resultados/simulado/
    ├── piloto/                   piloto SIMULADO vigente (reproducible a HEAD)
    └── piloto_historico_0cfa477/ el del arnés anterior: HISTÓRICO, ya no se reproduce (ver su LEEME)
```

`src/minifmt/ai/` (propiedad del núcleo) aporta `repair.py` (reparación `.mini`) y los adaptadores.

## Los dos comandos

Desde la raíz del repositorio (Python ≥ 3.9; `pyyaml`, `matplotlib`, `tiktoken`; `openai` solo para OpenAI real).

**1. Local, sin API y sin gasto (adaptador simulado):**

```bash
python experiments/generativo/run.py ejecutar --config configs/piloto.yaml --adapter simulado --emitir-evidencia
```

Escribe `resultados/simulado/piloto/`, el análisis y las corridas `evidencia/corridas/v2-…`, `v3b-…` y `v4-…` (el manifiesto
registra el commit y si el árbol de código estaba limpio; las salidas que la propia corrida sobrescribe no cuentan como código
modificado) con
procedencia `simulado` y resultado `no_evaluable`. El piloto se reproduce **bit a bit** (en simulado los tiempos locales
no se miden: el reloj es constante; la latencia de API es sintética y va marcada como simulada).

**2. Con API (solo si TODO lo siguiente está en orden; si no, se rechaza con un error claro y sin ninguna llamada):**

```bash
export OPENAI_API_KEY=… ANTHROPIC_API_KEY=… GROQ_API_KEY=…
python experiments/generativo/run.py ejecutar --config configs/piloto.yaml --adapter real --confirmar-real \
       --max-costo-usd 5 --tarifas evidencia/tarifas/tarifas.json
```

| Se rechaza si… | Dónde se declara |
|---|---|
| `presupuesto.autorizado_usd <= 0` (el valor por defecto es 0) | bloque `presupuesto` del YAML |
| falta `presupuesto.firmado_por` o `presupuesto.fecha` | ídem |
| falta `--max-costo-usd`, o es mayor que lo autorizado | línea de comandos |
| alguna tarifa necesaria es `no_verificada` o no existe | `evidencia/tarifas/tarifas.json` (flujo de infraestructura) o `--tarifas` |
| el costo esperado no cabe en el tope | dry-run |
| falta alguna variable de entorno de clave, o falta `--confirmar-real` | entorno / línea de comandos |

El bloque del YAML (todo en cero por defecto):

```yaml
presupuesto:
  autorizado_usd: 0          # > 0 solo lo escribe quien autoriza
  por_celda_max_usd: null    # tope del peor caso de una celda (generación + reparación)
  firmado_por: ""
  fecha: ""
```

La barrera no está solo en el CLI: `Ejecutor` en modo real exige una `Autorizacion` que únicamente puede crear
`presupuesto.validar_autorizacion`, y **toda** llamada pasa por `Ejecutor._llamar`.

Otros subcomandos: `dry-run` (recuento y costo sin ejecutar), `preparar` / `preparar-reparacion` / `importar` (material
asistido por IA), `evidencia` (emite las corridas de un directorio ya analizado). Códigos de salida: `0` correcto;
`2` rechazado antes de empezar (configuración, autorización, tarifas, claves, diseño distinto al del manifiesto,
directorio en uso); `3` abortado durante la ejecución (proyección del presupuesto, fallos seguidos); `4` interrumpido
(SIGINT/SIGTERM) con el estado guardado. Sin subcomando se entiende `ejecutar` (compatibilidad).

## Diseño experimental

### Condiciones (brazos)

Todas reciben **el mismo mensaje de usuario** (instrucción + documento de origen) y el mismo registro de ejemplo; solo
cambia la instrucción de formato y el lector.

| Brazo | Instrucción de formato | Lector |
|---|---|---|
| **A** JSON mínimo | «Devuelve solo JSON: un objeto con la clave `<registros>` …, con los campos: a, b, c». Sin tipos, rangos, ejemplo ni reglas | `json.loads` (quita cercas de código); si falla, se pierde el documento entero (con aviso) |
| **B** JSON con contrato | forma + lista de campos con tipo, rango y opcionales + ejemplo + descripción del dominio | igual que A |
| **C** JSON nativo | igual que B + esquema JSON estricto en el modo nativo del proveedor | igual que A |
| **D** `.mini` | `spec_block(contrato, "es", ejemplo)` + cabecera a usar | `extract_document` + `minifmt.parse(..., strict=False)` |
| **X+1** (A+1, B+1, C+1, D+1) | UNA reparación selectiva de la **misma** respuesta de X (no otra muestra) | el de X sobre el documento reparado |
| **A0** (control, fuera del Plan) | «una línea por registro, campos separados por `\|`» escrito a mano | `split('\|')` ingenuo |

* **C solo donde el modelo la admite.** Un modelo con `estructurado: false` deja C y C+1 como celdas `no_aplicable`
  (con motivo, en `plan.jsonl` y `celdas_faltantes.jsonl`); nunca se sustituyen por generación sin restricción. Un HTTP
  400/422 del proveedor en C se conserva como `error_tecnico` con la marca `posible_no_aplicable`.
* **Paridad de contrato.** B/C dicen lo mismo que el bloque `.mini` (rangos de lista, descripción, formato de fechas y
  decimales). Ninguno de los dos enseña la unicidad de `id`; se mide igual en todos.
* **El esquema de C no expresa rangos ni unicidad** (solo tipos, enumeraciones y campos obligatorios): C no hace cumplir
  el contrato completo y la validez se mide contra el contrato en todos los brazos.
* **Reparación equivalente para JSON.** El Plan exige comparaciones equivalentes; si solo `.mini` pudiera reparar, la
  ventaja del formato se confundiría con la de la estrategia. A+1/B+1/C+1 usan `json_tolerante`: un escáner respeta
  cadenas y llaves (acepta una comilla suelta o un salto de línea crudo), separa los objetos, marca los rechazados
  (sintaxis, contrato o identidad repetida), envía **solo esos** con su diagnóstico y fusiona sin sobrescribir lo válido.
  Consecuencia que hay que leer con cuidado: ese escáner también rescata los objetos completos de un JSON **truncado**,
  de modo que en V3b B+1 no equivale a B (B es el lector estricto, todo o nada).
* **Sin texto de origen en la reparación** (`incluir_entrada: false`): no puede recuperar un registro cortado.

### Tareas y datos de referencia

22 tareas (14 de extracción y 8 generativas) desde `forks/<prefijo>/` (contrato + `fixtures/canonical.json`). El registro 1
es el ejemplo común y los demás son la carga; la referencia se conoce registro a registro y **no depende del prompt** (el
prompt se construye del contrato y del ejemplo). Son **datos sintéticos del proyecto**: el manifiesto los etiqueta
`sintetico: true` con el SHA-256 de cada `contract.json` y `canonical.json`. La **estresación controlada** añade, de forma
determinista, comillas, barras, comas, saltos de línea y asteriscos finales (traza en `Tarea.estres`). Amenaza: los
fixtures son públicos (posible contaminación de entrenamiento).

### Orden, semilla y congelación

* El orden de ejecución se **baraja con una semilla registrada** (`controles.semilla_orden`, por defecto derivada de
  `semilla`); cada X+1 va justo detrás de su X. Queda en `plan.jsonl` y en el manifiesto (`orden.semilla`, `orden_sha256`).
* `manifiesto.json` congela con SHA-256 la configuración, **cada prompt**, los contratos, las referencias, los límites de
  salida por celda, las tarifas usadas, el código del arnés y el del núcleo (`nucleo_minifmt_sha256`: un cambio del lector
  `.mini` se ve). El manifiesto es inmutable: reanudar con un diseño distinto se rechaza salvo `--nueva-version "motivo"`
  (queda el manifiesto anterior, `manifiesto.v1.json`, y `versiones.jsonl`). El presupuesto **no** forma parte del diseño.
* Un directorio no mezcla adaptadores (simulado/real) ni procesos (`ejecucion.lock`).

### V3b (generación real con límite de salida)

Cada celda guarda `v3b`: `limite_salida`, `stop_reason`, `usage`, `respuesta_bruta` y `truncada`. La política del límite
(`experimentos.v3b.politica_limite`) es `comun_por_tarea` por defecto — el **mismo** límite para todos los brazos de la
tarea, `fraccion × mediana` de las salidas de referencia de los brazos presentes—, o `fraccion_por_brazo` (la anterior: cada
formato se corta a la mitad de su salida) o `fijo`. La política y la fracción son **provisionales** hasta el piloto real. V3b
se analiza aparte (columna `experimento` y corrida propia) y **no es V3a** (cortar un texto existente): esa es
`experiments/truncamiento/`. La tabla «V3a heredada» de `analyze.py` es exploratoria y deja el denominador cero vacío.

## Métricas (nunca fusionadas)

| Métrica | Definición |
|---|---|
| `sintaxis_ok` | el documento se pudo leer (A/B/C: `json.loads`; D: cabecera reconocida) |
| `validos_contrato` | registros aceptados que cumplen tipos, enumeraciones, rangos, aridades, marcadores y unicidad |
| `exactos_contenido` | (solo extracción) registros idénticos a la referencia tras normalizar |
| `validos_finales` | `min(validos_contrato, solicitados)`; el exceso va a `excedentes` |
| **validez final** | `validos_finales / solicitados`: el denominador son **todos** los registros solicitados, los ausentes cuentan |

Además, por registro: `correctos`, `incorrectos_sin_aviso` (aceptados con algún campo distinto **+ espurios**),
`perdidos_detectados` / `perdidos_sin_aviso`. Y por respuesta, el **desenlace**, que nunca se elimina:
`ok · formato_invalido · vacia · truncada · negativa · error_tecnico` (si concurren varios, prevalece el primero de:
error técnico, negativa, vacía, truncada, formato inválido).

**Reparación.** No sobrescribe válidos ni inventa o duplica identidades. `merge_repair` del núcleo compara líneas enteras
(su garantía de identidad la añade otro flujo); por eso el arnés **audita sobre el texto**, con independencia de la
fusión: `validos_sobrescritos`, `identidades_duplicadas_finales` e `identidades_inventadas` (`None`, no 0, si el contrato
no tiene campo `unique`). La fusión JSON rechaza por sí misma las correcciones que duplican o inventan una identidad
(`correcciones_rechazadas_identidad`).

### Usage, solicitud y costo

Cada muestra lleva la estructura **`solicitud`** acordada con el flujo de infraestructura:

```jsonc
{"id": "...", "grupo": "id de la generación original", "registros_solicitados": 11, "registros_validos_finales": 10,
 "intentos": [{"fase": "generacion|reparacion|validacion|otro", "modelo": "...", "proveedor": "...", "latencia_s": 1.8,
               "usage": {"entrada_sin_cache": 800, "entrada_cache_lectura": 200, "entrada_cache_escritura": 0,
                         "salida": 500, "razonamiento": null, "razonamiento_incluido_en_salida": true, "otros_usd": {}},
               "estado": "ok|error", "status": null, "costo_usd": "0.00182"}]}
```

* Un **brazo X+1 es una solicitud completa y autosuficiente**: sus `intentos` incluyen la generación de X (marcada
  `compartido_con`) y la reparación. Por eso `grupo` es el **propio `id`** y `familia` enlaza con la generación original:
  agrupar por `grupo` (como hace `experiments/economia/calculo.py`) no cuenta dos veces una generación. Las solicitudes
  de X y de X+1 de una misma familia son **estrategias alternativas sobre la misma respuesta**: no se suman entre sí (la
  generación aparece en las dos). El gasto real sale del libro, que cuenta cada llamada una sola vez. Una prueba alimenta
  el cálculo de economía con estas solicitudes y comprueba que da la misma cifra que el arnés (se activa cuando ese módulo
  está en la rama). Un intento fallido lleva `usage: null` (no se sabe qué se facturó), así que el cálculo de economía lo
  marca «usage no informado»; el análisis del arnés lo excluye y cuenta como gasto incierto los fallos sin código HTTP.
* **Sin doble conteo:** Anthropic informa entrada sin caché, lectura y escritura de caché por separado; en OpenAI, Groq y
  DeepSeek `prompt_tokens` incluye la caché (se resta) y `completion_tokens` incluye el razonamiento (no se suma otra vez).
  Si el proveedor no entrega usage, el usage es `null`.
* **Costo:** `tarifas.py` consume `evidencia/tarifas/tarifas.json` (estructura acordada). Tarifa `no_verificada` o ausente
  implica costo `null` («tarifa no verificada»); **no existe ningún precio por defecto** (se eliminó el `precios.json`
  provisional). La fórmula oficial de los informes vive en `experiments/economia`; la de este módulo sirve para el control
  de gasto, el dry-run y el costo por solicitud del análisis, y usa la misma estructura.
* **Tokens:** hay tres cosas distintas y nunca se mezclan: el **conteo local** de texto (`o200k_base`, una aproximación para
  Anthropic, Google y DeepSeek), el conteo de solicitud del proveedor y el **usage** de una llamada real. La entrada del
  dry-run es el conteo local × un factor supuesto por proveedor; se cuentan los textos **completos** enviados.
* **Latencia del flujo completo** = generación + validación + reparación + entrega, por muestra; el análisis da mediana,
  p95 (rango más cercano) y `n`, sin los errores técnicos. El manifiesto registra concurrencia (1, el runner es
  secuencial), calentamiento (ninguno), red y exclusiones. En simulado la latencia de API es sintética y está marcada.

## Controles de gasto

1. **Proyección antes de cada llamada.** Se comprueba `gastado + incierto + peor caso de la llamada ≤ tope` (peor caso =
   cota de la entrada al precio más alto + `max_tokens` × precio de salida) y el peor caso de la celda contra
   `por_celda_max_usd`. Si no cabe, **no se llama**: nunca se descubre el exceso después de gastar.
2. **Libro** (`libro.jsonl`, append-only con `fsync`): inicio y fin de cada llamada. Una llamada iniciada y no terminada
   (proceso matado) se cuenta al peor caso como gasto **incierto** al reanudar; un fallo sin código HTTP (tiempo agotado)
   también, porque pudo facturarse.
3. **Reintentos** (`controles.reintentos_por_llamada`): los hace el arnés (los de los adaptadores se desactivan), cada uno se
   proyecta contra el tope y queda como intento `estado: error` con su `status`. Un error se **conserva como muestra**
   (`desenlace: error_tecnico`); si es reintentable, la celda se repite al reanudar y sus intentos fallidos se arrastran.
4. **Detención segura.** La primera señal (SIGINT/SIGTERM) termina la llamada en curso, guarda y sale con código 4; la
   segunda la interrumpe y cuenta su peor caso como incierto. Quedan `estado_estudio.json`
   (`en_curso · completo · parcial · interrumpido · abortado`, con recuento por estado) y `celdas_faltantes.jsonl` con el
   **motivo** de cada celda: `pendiente` (interrupción, `--limite`, error reintentable), `bloqueado` (presupuesto, fallos
   seguidos, base sin respuesta) o `no_aplicable`. La suma por estado es el total de celdas (hay una prueba).
5. **Reanudación idempotente:** se salta cada `id` ya hecho; una línea final a medio escribir se aísla y se repite.

## Material asistido por IA (importar)

Para respuestas ya generadas por una IA en sesión (sin API, sin gasto, sin usage). Flujo:

```bash
python experiments/generativo/run.py preparar --tareas ext-cls,gen-card --brazos A,B,D --repeticiones 3 \
       --modelo-declarado NOMBRE --salida prompts.jsonl            # prompts EXACTOS y su prompt_id
# … quien genera responde y devuelve respuestas.jsonl …
python experiments/generativo/run.py importar respuestas.jsonl --salida resultados/asistido_ia/piloto --emitir-evidencia
# para A+1/B+1/D+1: pedir las reparaciones que hagan falta e importarlas en una segunda pasada
python experiments/generativo/run.py preparar-reparacion respuestas.jsonl --salida reparaciones.jsonl
```

Formato de cada línea de `respuestas.jsonl` (`importar` acepta también un directorio con varios `*.jsonl`):

| Campo | Contenido |
|---|---|
| `celda_id` | identificador de la celda (el de `preparar`; se conserva como `celda_id_origen`) |
| `dominio` | **id de tarea** (`ext-cls`, `gen-card`, …) |
| `condicion` | `A`, `B`, `D`, `A0` o, en la segunda pasada, `A+1`, `B+1`, `D+1` (con `respuesta_bruta` = la respuesta de la **reparación**). `C` es `no_aplicable` |
| `repeticion` | entero ≥ 1 |
| `prompt_id` | el que entregó `preparar`; si no coincide con el prompt vigente la fila se rechaza (se respondió a otro prompt) |
| `respuesta_bruta` | el texto **exacto**, sin limpiar (cercas, prosa y errores incluidos) |
| `modelo_declarado` | lo que declara quien genera; no se verifica |
| `parametros` | objeto libre (`temperature` / `max_tokens` se leen si están) |
| `fecha_utc` | ISO 8601 |
| `experimento` | opcional, `v2` por defecto |

```json
{"celda_id": "v2/ext-cls/D/asistido_ia:NOMBRE/r001", "dominio": "ext-cls", "condicion": "D", "repeticion": 1, "prompt_id": "ext-cls/D/3fa9c1d20b7e", "respuesta_bruta": "cls|n=11|…", "modelo_declarado": "NOMBRE", "parametros": {"temperature": 0.7}, "fecha_utc": "2026-09-30T12:00:00Z"}
```

Pasan por el **mismo** lector y el mismo analizador. Las muestras llevan `procedencia: "asistido_ia"`, `usage: null`,
`tokens_*: null`, costo vacío («sin usage ni factura de API») y el conteo local aparte (`tokens_locales_aprox`, una
aproximación). Las filas inválidas (duplicadas, campos que faltan, dominio desconocido, `prompt_id` que no corresponde,
línea ilegible) **no se descartan**: quedan en `importacion.json` con su motivo. Una corrida importada es siempre
`asistido_ia` / `no_evaluable` y el análisis lo rotula en tablas y figuras.

## Análisis (`analyze.py`)

Escribe en `<resultados>/analisis/`: `resumen_brazos.csv`, `resumen_brazo_modelo.csv`, `resumen_brazo_tarea.csv`,
`comparaciones_pareadas.csv`, `reparacion.csv`, `desenlaces.csv`, `latencia_costo.csv`, `solicitudes.jsonl`,
`meta_v2.json`, `v3a_truncamiento*.csv` (heredada), `resumen.md` y cinco figuras.

* **Incertidumbre agrupada.** Bootstrap de **conglomerados** (por solicitud y por documento/tarea; 1 000 réplicas, semilla
  fija), nunca por registro o campo. La sintaxis usa Wilson por muestra. Una prueba comprueba que, con correlación interna
  fuerte, el IC por conglomerado es más ancho que el de tratar cada registro como independiente.
* **Comparaciones pareadas** por (tarea, modelo, repetición): formato (B/C/A frente a D, también con reparación en ambos) y
  estrategia (X frente a X+1, sobre la misma respuesta). Están rotuladas **exploratorias** (sin corrección por
  comparaciones múltiples).
* **Denominador cero = vacío** (`None`), nunca 0; el costo por 1 000 válidos con denominador cero informa el fallo y el
  costo incurrido.
* **Meta V2** (`meta_v2.json`): criterio **fijado en el código antes de analizar** —validez final ≥ 95 % por (brazo, modelo)
  en ≥ 3 modelos de ≥ 2 proveedores— y solo evaluable con material `api_real`; con simulado o asistido por IA el resultado
  es `no_evaluable`.
* El costo se **recalcula** con `--tarifas` desde el usage por categorías de cada intento.

### Piloto con el adaptador simulado (SIMULADO — solo valida el arnés)

`configs/piloto.yaml`: 3 tareas de extracción (`ext-log`, `ext-cls`, `ext-tc`) y 1 generativa (`gen-card`); 3 modelos
etiquetados como OpenAI, Anthropic y Groq (perfiles simulados medio, fuerte y débil; Groq sin modo estructurado); 6
repeticiones en V2 y 3 en V3b. Ejecuta **792 celdas** (396 de generación + 396 de reparación, de las que el libro registra
607 llamadas al adaptador) y deja **72 celdas `no_aplicable`** (C y C+1 de Groq). Validez final simulada del piloto
(`resultados/simulado/piloto/analisis/resumen_brazos.csv`, IC 95 % bootstrap por solicitud):

| Brazo (SIMULADO) | extracción | generativa |
|---|---|---|
| A | 67,3 [55,4–77,8] | 58,6 [38,4–76,8] |
| A+1 | 82,3 [72,4–90,6] | 79,3 [59,6–95,0] |
| B | 72,9 [61,3–83,2] | 79,8 [61,6–94,4] |
| B+1 | 89,1 [80,0–96,3] | 86,4 [70,7–98,5] |
| C | 99,2 [98,5–100,0] | 100,0 [100,0–100,0] |
| C+1 | 99,2 [98,5–100,0] | 100,0 [100,0–100,0] |
| D | 91,4 [88,1–94,3] | 94,4 [90,4–97,5] |
| D+1 | 96,6 [93,6–98,7] | 98,0 [95,5–100,0] |

**No se debe leer como una comparación de formatos**: son las tasas de falla que el simulador supone
(`DEFAULT_PROFILE`, `TASAS_ARNES`). Por qué las cifras del piloto de la versión anterior de este README (`0cfa477`) ya no
valen: el piloto versionado **no se reproducía a HEAD** porque el lector `.mini` del núcleo cambió (SPEC 1.1: `parser`,
`values`, `serializer`, `codec`, `contract`) y el lector forma parte del tratamiento del brazo D; además el diseño cambió. El
anterior queda como `piloto_historico_0cfa477` (marcado, sin citar) y el vigente se regenera con el comando 1. La prueba
`test_el_piloto_se_reproduce_a_head` lo vigila; para no bloquear arreglos legítimos del núcleo, las filas D y D+1 solo
avisan y el resto (JSON y su reparación, que son del arnés) debe coincidir exactamente.

## Recuento de llamadas del estudio (dry-run, sin ejecutar nada)

`python experiments/generativo/run.py dry-run --config configs/estudio.yaml`

| Concepto | Cuenta | De dónde sale |
|---|---|---|
| V2 primarias **nominales** | **6 720** | 14 tareas × 4 modelos × 30 repeticiones × 4 brazos (A, B, C, D) |
| celdas C **no aplicables** | −420 | `groq:llama-3.3-70b-versatile` no declara modo estructurado (14 × 30) |
| V2 primarias **a ejecutar** | **6 300** | 6 720 − 420 |
| V3b primarias a ejecutar | 2 100 | 14 × 10 repeticiones × 15 (4 modelos × 4 brazos − 1 sin C) |
| **Total de primarias** | **8 400** | 6 300 + 2 100 |
| Reparaciones (máximo) | 8 400 | una ronda por celda A+1, B+1, C+1, D+1, y solo si la respuesta base tiene algo que reparar |

El dry-run imprime además el costo esperado y máximo por modelo **solo con tarifas verificadas**; para los modelos sin
ella dice «tarifa no verificada». Aquí no se citan importes: dependen del archivo de tarifas, que mantiene el flujo de
infraestructura. Con la matriz propuesta, el modelo `groq:llama-3.3-70b-versatile` no tiene tarifa verificada: la corrida
real **se rechazaría** hasta sustituir el modelo o verificarla.

## Adaptadores

Interfaz común (`minifmt.ai.adapters.base.Adapter`):
`generate(system, user, *, max_tokens, temperature, response_format=None, seed=None) -> {"text", "input_tokens",
"output_tokens", "latency_ms", "raw", "stop_reason", "model", "provider"}`; `response_format` es neutro
(`{"type": "json_schema", "name", "schema"}`) y cada adaptador lo traduce (OpenAI `json_schema` estricto; Anthropic
`output_config.format`; Groq `response_format`). Claves solo de `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `GROQ_API_KEY`: no se
imprimen ni se guardan (el log pasa por `redact`; hay una prueba que busca la clave en todos los archivos de resultados).
Los adaptadores reales se crean **sin reintentos propios**: los reintentos son del arnés. El adaptador simulado
(`SimuladorArnes`) añade `json_minimo` y `repair_json`.

## Qué necesita el equipo para ejecutarlo

1. **Autorizar el presupuesto** (quien corresponda rellena `presupuesto` del YAML). El tope de 5 / 40 USD del Charter es una
   propuesta, no una autorización.
2. **Tarifas verificadas** de todos los modelos elegidos (p. ej. la de `llama-3.3-70b-versatile`, o sustituirlo), y confirmar
   disponibilidad, `json_schema` estricto (sobre todo Groq), `temperature` y razonamiento por defecto. Modelos que razonan
   (`gpt-oss-120b`) pueden agotar `max_tokens` pensando: revisar el límite de V3b.
3. **Claves** en variables de entorno de la máquina que ejecuta.
4. **Decisiones abiertas:** política y fracción del límite de V3b (con el piloto real), si la reparación incluye el texto de
   origen (`incluir_entrada`), paralelismo (el runner es secuencial: el estudio completo son del orden de decenas de horas) y
   la tasa de reparación esperada por brazo (`estimacion.tasa_reparacion_esperada` acepta un valor por brazo).
5. Ejecutar primero `--limite 20`, revisar a mano algunas respuestas de cada brazo, luego el piloto real y solo después el
   estudio.

## Equivalencia con los experimentos previos (E1–E5)

Los experimentos de `generative/` usaron modelos de **un solo proveedor**, n = 6–10 por celda y lectura estricta. **E1**
(fidelidad) corresponde a V2 extracción con B y D; **E2** corresponde al brazo D sobre 14 forks; **E3** (síntesis de parser) fuera de alcance;
**E4** (punto de equilibrio) corresponde a tokens facturados por brazo con el usage por categorías; **E5** (truncamiento) corresponde a V3a (otro
flujo, `experiments/truncamiento/`) y V3b (aquí, truncamiento real por `max_tokens`).

## Riesgos y amenazas a la validez

* **Simulación:** las tasas de falla del simulador son inventadas; lo simulado nunca se mezcla ni se cita junto a lo real
  (directorio, marca en muestras, manifiesto, tablas y figuras, y `no_evaluable` en la evidencia).
* **Asimetría de validación:** el lector `.mini` valida el contrato al leer; el lector JSON de A/B/C solo valida la
  sintaxis. Por eso se separan sintaxis, contrato y exactitud, y se añaden los brazos X+1 (validación + reparación) en ambos
  formatos.
* **Escáner tolerante de A+1/B+1/C+1:** rescata objetos de un JSON truncado; compararlo con B en V3b mezcla «reparar» y
  «leer con tolerancia». V3a (otro flujo) trae los lectores JSON parcial y JSON Lines.
* **Reparación sin texto de origen:** no recupera líneas cortadas y gasta llamadas en ellas.
* **Estrés artificial** y **fixtures públicos** (contaminación posible).
* **Tokenizador y factores** del dry-run aproximados; el costo máximo supone agotar `max_tokens`.
* **Modelos cambiantes:** ids, precios y comportamiento pueden variar; el manifiesto guarda la configuración, los hashes y
  las tarifas usadas, y cada muestra guarda el `model` que devuelve la API.
* **Latencia:** se mide en el cliente (incluye red y colas del proveedor); concurrencia 1.

## Qué cambió respecto a la versión anterior

Brazo A (pipe) -> A0 opcional y A = JSON mínimo · D+R -> D+1 · reparación también para JSON · métricas separadas y validez
sobre lo solicitado · presupuesto autorizado, proyección previa, libro, reintentos registrados, detención segura, estado y
celdas faltantes · orden aleatorizado y hashes del diseño · usage por categorías y costo por solicitud · IC por
conglomerados, mediana y p95 · dry-run con recuento · importación de material asistido por IA · corridas con
`tools/evidencia_lib` · se elimina `precios.json`. Las 60 pruebas anteriores se conservan (con los cambios intencionales:
A->A0, D+R->D+1, presupuesto por proyección y errores conservados como muestra) y se añaden 117.
