# Arnés experimental V2 / V3 — generación y truncamiento

Arnés para medir, con modelos reales de varios proveedores:

* **V2 · fiabilidad de generación**: cuántos registros llegan correctos, cuántos
  se corrompen **sin aviso**, cuántos se pierden (con o sin aviso) y cuánto
  cuesta cada condición, cuando un equipo pide salidas estructuradas con su
  propio prompt, con JSON (con y sin modo estructurado nativo) o con `.mini` y
  su biblioteca (con y sin reparación selectiva).
* **V3 · recuperación ante truncamiento**: cuántos registros completos se
  recuperan cuando la salida se corta, (a) con cortes controlados sobre salidas
  guardadas y (b) con llamadas reales a `max_tokens` bajo.

> **Estado.** El arnés está completo y probado, pero **no se ha ejecutado con
> ningún modelo real**. Las únicas cifras de este directorio salen del
> adaptador **simulado** y solo demuestran que el arnés funciona de extremo a
> extremo. No son resultados del estudio y no deben citarse como evidencia.

## Contenido

```
experiments/generativo/
├── run.py                 runner: matriz, dry-run, presupuesto, reanudación
├── analyze.py             tablas con IC 95 % (Wilson), V3a y figuras en español
├── precios.json           precios por modelo (PROVISIONALES, no verificados)
├── configs/
│   ├── piloto.yaml        4 tareas × 3 modelos × 5 brazos × 6 repeticiones (+ V3b)
│   └── estudio.yaml       matriz propuesta para el estudio real
├── arnes/
│   ├── tareas.py          catálogo de tareas a partir de forks/ (+ estrés controlado)
│   ├── brazos.py          prompts y lectores de A, B, C, D, D+R; esquema JSON del brazo C
│   ├── metricas.py        clasificación de cada registro
│   ├── ejecucion.py       configuración, matriz, almacén JSONL, ejecución, oráculo simulado
│   ├── costos.py          estimación de llamadas, tokens y costo
│   ├── truncamiento.py    V3a (cortes controlados)
│   └── estadistica.py     intervalos de Wilson
├── tests/                 pytest (red bloqueada en todas las pruebas)
└── resultados/simulado/piloto/   manifiesto y análisis del piloto SIMULADO

src/minifmt/ai/
├── repair.py              extract_document, repair_request, merge_repair
└── adapters/              interfaz común + OpenAI, Anthropic, Groq y Simulado
```

## Cómo se ejecuta

Desde la raíz del repositorio (Python ≥ 3.9; usa `pyyaml`, `matplotlib`,
`tiktoken` y, solo para OpenAI real, `openai`; ya instalados en el entorno de
trabajo):

```bash
# 1. Estimar llamadas y costo (no llama a nada)
python experiments/generativo/run.py --config configs/estudio.yaml --adapter real --dry-run

# 2. Piloto sin red con el adaptador simulado
python experiments/generativo/run.py --config configs/piloto.yaml --adapter simulado
python experiments/generativo/analyze.py --resultados experiments/generativo/resultados/simulado/piloto

# 3. Ejecución real (cuando el equipo lo decida)
export OPENAI_API_KEY=... ANTHROPIC_API_KEY=... GROQ_API_KEY=...
python experiments/generativo/run.py --config configs/piloto.yaml --adapter real \
       --confirmar-real --max-costo-usd 5
python experiments/generativo/analyze.py --resultados experiments/generativo/resultados/real/piloto

# Pruebas
python -m pytest experiments/generativo/tests -q
```

Opciones del runner:

| Opción | Efecto |
|---|---|
| `--dry-run` | construye todos los prompts, cuenta tokens y muestra llamadas, costo esperado y costo máximo por modelo; no escribe nada |
| `--max-costo-usd X` | aborta **antes** de empezar si el costo esperado supera X, y **durante** la ejecución en cuanto el costo acumulado (según tokens reportados por la API, incluidas las muestras ya guardadas) supera X |
| `--confirmar-real` | obligatorio con `--adapter real`; sin él el runner se niega a llamar |
| `--limite N` | ejecuta como mucho N muestras pendientes (útil para una prueba de humo) |
| `--salida DIR` | directorio de resultados (por defecto `resultados/<adaptador>/<nombre>`) |

Códigos de salida: `0` correcto; `2` abortado antes de empezar (configuración
inválida, presupuesto, falta `--confirmar-real` o faltan variables de entorno);
`3` abortado durante la ejecución (presupuesto o `max_fallos_seguidos`).

**Reanudación.** Cada muestra se escribe en `muestras.jsonl` (una línea, con
`fsync`) en cuanto termina. Al volver a lanzar el mismo comando se saltan los
`id` ya guardados; una línea final a medio escribir se aísla y esa muestra se
repite. Los fallos de llamada van a `fallos.jsonl` y se reintentan en la
siguiente ejecución. El `id` de una muestra es
`<experimento>/<tarea>/<brazo>/<proveedor>:<modelo>/r<rep>`.

**Claves.** Solo se leen de `OPENAI_API_KEY`, `ANTHROPIC_API_KEY` y
`GROQ_API_KEY`. No se imprimen, no se guardan en muestras ni manifiestos, y el
log (`ejecucion.log`) pasa por un formateador que enmascara los valores de esas
variables, patrones `sk-…`/`gsk_…`/`Bearer …` y las cabeceras de autorización.
El arnés no lee archivos `.env`.

## Protocolo

### Tareas

Todas las tareas salen de los forks publicados en `forks/` (contrato +
`fixtures/canonical.json`, 12 registros): el registro 1 es el **ejemplo común**
a todos los brazos y los 11 restantes son la carga de la tarea.

* **Extracción** (`ext-<prefijo>`, 14 disponibles): el modelo recibe un
  *documento de origen* neutro — bloques `campo: valor`, textos multilínea
  entre `<<<` y `>>>`, un elemento de lista por línea y `[x]` para las
  selecciones — y debe transformarlo. La salida esperada se conoce registro a
  registro.
* **Generativa** (`gen-<prefijo>`, 8 disponibles): el modelo genera 11
  registros nuevos del dominio; se evalúa contra el contrato.

**Estrés controlado.** Los fixtures casi no contienen caracteres conflictivos,
que es justo donde aparece la corrupción sin aviso. `tareas.estresar` añade de
forma determinista, en los registros pares, un fragmento realista a un campo de
texto natural (valor original con espacios; nunca el primer campo) —
`(ver "Anexo B", sección 2)`, `| ref. A|B`, un salto de línea con coma,
`C:\datos\nuevo`, `*importante*` — y, en uno de cada tres registros, un
fragmento al primer elemento de una lista de texto (`, incl. "beta"`, `| alt`,
`(a, b)`, `*` final). Cada modificación se valida con ida y vuelta contra el
contrato; la traza queda en `Tarea.estres`.

### Brazos

Todos los brazos reciben **el mismo mensaje de usuario** (instrucción + documento
de origen) y el mismo registro de ejemplo; solo cambia la instrucción de formato
(mensaje de sistema) y el lector.

| Brazo | Instrucción de formato | Lector |
|---|---|---|
| **A** prompt propio | escrita a mano: una línea por registro, campos separados por `\|` en orden, listas y grupos con comas, `*` para seleccionados; sin reglas de escape | `split('\|')` ingenuo; descarta con aviso las líneas con aridad o números inválidos; no valida enumeraciones, conteos ni marcadores; `bool` = `valor == "true"` |
| **B** JSON | forma `{"<clave>": [...]}` con lista de campos y ejemplo de un registro | quita cercas de código y aplica `json.loads`; si falla, se pierde el documento entero (con aviso) |
| **C** JSON estructurado | igual que B + esquema JSON estricto derivado del contrato en el modo nativo del proveedor | igual que B |
| **D** `.mini` | `spec_block(contrato, "es", ejemplo)` + cabecera a usar | `extract_document` + `minifmt.parse(..., strict=False)` |
| **D+R** | reutiliza la salida de D (no genera de nuevo) | como D, tras `repair_request` → llamada → `merge_repair` (hasta `reparacion.max_rondas`) |

Si un modelo no declara `estructurado: true`, el brazo C se **omite** para ese
modelo y la omisión se imprime y queda en `manifiesto.json`; nunca se sustituye
por generación sin restricciones.

### Reparación selectiva (`minifmt.ai`)

`repair_request(documento, contrato, idioma)` localiza el documento dentro de la
respuesta, lo analiza en modo tolerante y construye una solicitud con **solo** las
líneas inválidas y los errores del validador (código, campo, mensaje). El
bloque de especificación va en el mensaje de sistema (estable, cacheable); el
texto de origen solo se añade con `incluir_entrada: true`. Los fragmentos
contiguos de un registro partido por un salto de línea sin escapar se agrupan
en un único ítem. La respuesta esperada es un pequeño documento `.mini`
(`<prefijo>|n=k` + k líneas en el mismo orden, `-` para descartar texto que no
es registro).

`merge_repair(original, respuesta, contrato, solicitud)` acepta una corrección
solo si es válida por sí sola con la cabecera original (así siguen aplicando las
claves de conteo), descarta correcciones que duplican un registro existente y
**nunca reescribe `n`**: si faltan registros (truncamiento), el aviso E04
sigue visible.

### Métricas por muestra

Extracción — cada registro aceptado se empareja con un esperado (voraz, por
número de campos iguales, mínimo la mitad):

| Métrica | Definición |
|---|---|
| `correctos` | aceptado e idéntico tras normalizar (espacios colapsados, `""` ≡ nulo, números por valor, booleanos estrictos) |
| `incorrectos_sin_aviso` | aceptado con algún campo distinto **+ espurios** (aceptados que no existen en la entrada) |
| `perdidos_detectados` | no aceptados, y el lector emitió al menos un aviso en la muestra |
| `perdidos_sin_aviso` | no aceptados sin ningún aviso |
| `parseable` | A: respuesta no vacía; B/C: `json.loads` correcto con la lista esperada; D: cabecera reconocida |
| `exacto` | todos los esperados correctos y ningún espurio |

Generativa: `correctos` = aceptados que cumplen el contrato (tipos JSON
estrictos, enumeraciones, rangos, aridades, marcadores, clave de conteo,
unicidad); `incorrectos_sin_aviso` = aceptados fuera de contrato; `perdidos` =
`max(0, n − aceptados)`. En D los lectores solo devuelven registros válidos, así
que su corrupción sin aviso *contra el contrato* es cero por construcción; la
comparación informativa es la de extracción.

Además, por muestra: tokens de entrada y salida **reportados por la API**,
latencia, `stop_reason`/truncado, llamadas y tokens de reparación y costo (con
los precios de `precios.json`). La muestra D+R suma generación + reparación y
su `costo_incremental_usd` (lo que cuenta para el presupuesto) es solo la
reparación.

### V3 · truncamiento

* **V3a (sin llamadas)** — `analyze.py` corta cada respuesta guardada de V2
  (brazos A–D) en `cortes_por_muestra` posiciones aleatorias (semilla fija por
  muestra, entre el 10 % y el final) y aplica el lector del brazo. Métricas:
  registros correctos recuperados, *ideal* = ⌊fracción cortada × correctos sin
  cortar⌋ (misma aproximación que E5), eficiencia y porcentaje de cortes sin
  ningún registro.
* **V3b (con llamadas)** — experimento `v3b` con
  `max_tokens = fraccion_max_tokens × tokens de la salida de referencia del
  brazo` (50 % por defecto), de modo que cada brazo se corta a mitad de su
  propia salida. Se evalúa con las mismas métricas de V2.

### Semillas y aleatoriedad

Cada muestra tiene semilla `sha256(semilla_config | id)`; se envía como `seed`
a OpenAI y Groq (Anthropic no tiene ese parámetro) y fija las fallas del
simulador. La temperatura es global (`temperatura`) con anulación por modelo;
para modelos que rechazan parámetros de muestreo se declara
`enviar_temperatura: false`.

## Adaptadores

Interfaz común (`minifmt.ai.adapters.base.Adapter`):

```python
generate(system, user, *, max_tokens, temperature, response_format=None, seed=None)
  -> {"text", "input_tokens", "output_tokens", "latency_ms", "raw", "stop_reason", "model", "provider"}
```

`response_format` es neutro (`{"type": "json_schema", "name", "schema"}`) y cada
adaptador lo traduce:

| Adaptador | Transporte | Modo estructurado |
|---|---|---|
| `OpenAIAdapter` | paquete `openai` (Chat Completions, `max_completion_tokens`) | `response_format: json_schema` con `strict: true` |
| `AnthropicAdapter` | HTTPS directo (`httpx` si está, si no `urllib`) a `/v1/messages`, `anthropic-version: 2023-06-01` | `output_config.format: json_schema` |
| `GroqAdapter` | HTTPS directo a `api.groq.com/openai/v1/chat/completions` | `response_format: json_schema` (solo en modelos que lo soportan; declarar por modelo) |
| `SimulatedAdapter` | ninguno | emulado |

Los adaptadores HTTP reintentan 408/409/429/5xx con espera exponencial; los
mensajes de error pasan por `redact`. Los tokens de entrada de Anthropic suman
los de caché (creación y lectura).

### Adaptador simulado

Determinista (hash de semilla + modelo + prompt), sin red. Un **oráculo**
registrado por el runner le dice qué registros de referencia pide cada prompt y
en qué forma; el adaptador los renderiza e inyecta fallas **condicionales** a
que el valor contenga el carácter conflictivo:

* texto: prosa antes/después, cercas de código, truncamiento aleatorio y corte
  real en `max_tokens`;
* registro: omisión, deriva de contenido y deriva de enumeración (no en modo estructurado);
* A: `|` y saltos de línea sin escapar (no hay regla que seguir), fila de encabezado espuria;
* B: comilla o salto de línea crudo dentro de una cadena, coma final;
* D: `|` sin escapar, separador de lista sin proteger, barra invertida simple, salto de línea crudo, `n` incorrecto;
* reparación: corrige con probabilidad `repair_success`; no puede recuperar una
  línea truncada si la solicitud no incluye el texto de origen.

Las tasas (`DEFAULT_PROFILE` en `adapters/simulated.py`) y los multiplicadores
de perfil (`fuerte` 0,4 · `medio` 1 · `debil` 2) son **supuestos del
simulador**. Por eso las diferencias entre brazos en el piloto simulado son
consecuencia de esos supuestos y no dicen nada sobre los formatos reales.

## Análisis

`analyze.py` escribe `resumen_brazos.csv`, `resumen_brazo_modelo.csv`,
`resumen_brazo_tarea.csv`, `reparacion.csv` (D frente a D+R emparejados),
`v3a_truncamiento*.csv`, `resumen.md` y cuatro figuras
(`fig_v2_desenlaces_registros`, `fig_v2_incorrectos_sin_aviso`, `fig_v2_tokens`,
`fig_v3_recuperacion`). Si alguna muestra es simulada, el resumen y todas las
figuras llevan la marca **SIMULADO**.

Las proporciones de registros usan como denominador *esperados + espurios* y
llevan IC 95 % de Wilson. Los registros de una misma muestra no son
independientes, así que esos intervalos son optimistas; para el informe final
conviene complementarlos con un modelo de efectos mixtos o bootstrap por
muestra. Los intervalos por muestra (`parseable`, `exacto`) no tienen ese
problema.

## Piloto con el adaptador simulado (SIMULADO — solo valida el arnés)

`configs/piloto.yaml`: 3 tareas de extracción (`ext-log`, `ext-cls`, `ext-tc`)
y 1 generativa (`gen-card`); 3 modelos etiquetados como OpenAI, Anthropic y Groq
(perfiles simulados medio, fuerte y débil; Groq sin modo estructurado, así que C
se omite); 6 repeticiones en V2 y 3 en V3b. Ejecutó **504 muestras** (396
llamadas de generación simuladas + 29 de reparación en V2 y 31 en V3b) en unos
6 s; el análisis está en `resultados/simulado/piloto/analisis/`.

V2, tareas de extracción (594 registros esperados por brazo; 396 en C):

| Brazo (SIMULADO) | exacto % | correctos % [IC95] | incorrectos sin aviso % | perdidos con aviso % | tokens entrada / salida |
|---|---|---|---|---|---|
| A | 0,0 | 56,8 [52,8–60,7] | 26,1 | 17,1 | 1228 / 449 |
| B | 50,0 | 76,3 [72,7–79,5] | 2,2 | 20,4 | 1239 / 1060 |
| C | 86,1 | 98,7 [97,1–99,5] | 0,8 | 0,0 | 1239 / 850 |
| D | 46,3 | 88,9 [86,1–91,2] | 4,0 | 6,6 | 1543 / 482 |
| D+R | 57,4 | 92,9 [90,6–94,7] | 4,0 | 2,0 | 1838 / 509 |

V3 (SIMULADO): en V3b, B y C no recuperan ningún registro (JSON incompleto), A
recupera 17 % y D 37 % de los registros de extracción; en V3a D y A recuperan
≈ 96 % de lo recuperable y B/C 0 %. La reparación sin texto de origen gasta
llamadas en la línea truncada sin recuperarla (22 llamadas, 2 registros
ganados en V3b de extracción).

Qué valida el piloto: que la matriz se construye y omite C cuando corresponde;
que las fallas inyectadas llegan a cada categoría de métrica (corrupción sin
aviso en A por comas y encabezados espurios, pérdida total con aviso en B,
detección en D, recuperación en D+R); que la reparación selectiva, la fusión y
la reanudación funcionan; que V3a y V3b producen cifras; que el costo nocional
se acumula y el presupuesto aborta. **Qué no valida**: ninguna afirmación sobre
formatos, modelos o proveedores reales.

## Matriz propuesta para el estudio real

`configs/estudio.yaml` (cumple ≥ 3 modelos de ≥ 2 proveedores, ≥ 10 dominios y
≥ 30 muestras por celda):

* **Modelos (4, de 3 proveedores):** `openai:gpt-4.1-mini` (estructurado),
  `anthropic:claude-haiku-4-5` (estructurado), `groq:llama-3.3-70b-versatile`
  (sin estructurado: C omitido), `groq:openai/gpt-oss-120b` (estructurado; confirmar).
* **Tareas (14 dominios):** extracción `log, cls, tc, ner, cat, map, sum, us, a, s`;
  generativas `card, q, r, code`.
* **Brazos:** A, B, C, D, D+R. **Repeticiones:** 30 en V2 (celda = tarea × brazo × modelo);
  10 en V3b con `max_tokens` al 50 %. V3a: 20 cortes por muestra de V2 (sin costo).
* `temperatura: 0.7`, `max_tokens: 8192`, 1 ronda de reparación sin texto de origen.

### Estimación del dry-run

`python experiments/generativo/run.py --config configs/estudio.yaml --adapter real --dry-run`
(15-sep-2026, precios **provisionales** de `precios.json`):

| Proveedor | Modelo | Llamadas de generación | Reparación esperada / máxima | Tokens entrada | Tokens salida esperados | Costo esperado USD | Costo máximo USD |
|---|---|---|---|---|---|---|---|
| Anthropic | claude-haiku-4-5 | 2 240 | 196 / 560 | 2,97 M | 1,70 M | 11,45 | 76,41 |
| Groq | llama-3.3-70b-versatile | 1 680 | 196 / 560 | 2,05 M | 1,20 M | 2,16 | 10,28 |
| Groq | openai/gpt-oss-120b | 2 240 | 196 / 560 | 2,61 M | 1,70 M | 1,66 | 11,40 |
| OpenAI | gpt-4.1-mini | 2 240 | 196 / 560 | 2,38 M | 1,70 M | 3,67 | 24,46 |
| **Total** | | **8 400** | **784 / 2 240** | **10,0 M** | **6,3 M** | **≈ 19** | **≈ 123** |

Por proveedor: Anthropic ≈ 11,5 USD esperados (76 máx.), Groq ≈ 3,8 (22 máx.),
OpenAI ≈ 3,7 (24 máx.). Supuestos de la estimación:

* tokens de entrada contados con `o200k_base` sobre los prompts reales y
  multiplicados por un factor por proveedor (Anthropic 1,25; Groq 1,1) que es
  un supuesto conservador, no una medición;
* salida esperada = tokens de la salida de referencia del brazo × 1,15; el
  **costo máximo** asume que cada llamada agota `max_tokens` (cota superior);
* reparación esperada = 35 % de las muestras D+R con el 20 % de las líneas;
* los modelos de razonamiento (`gpt-oss-120b`, y `gpt-5-mini` o `claude-opus-5` si se eligieran)
  facturan tokens de razonamiento como salida: su costo real puede superar el esperado;
* el runner es secuencial: con ≈ 10 s por llamada, el estudio completo llevaría
  del orden de 25 h de reloj (estimación gruesa; paralelizar por proveedor es
  una mejora pendiente).

El piloto real (`configs/piloto.yaml`, 396 llamadas + ≈ 38 reparaciones) se
estima en ≈ 1,1 USD esperados y ≈ 3,7 USD como máximo.

## Qué necesita el equipo para ejecutarlo

1. **Elegir los modelos definitivos** y confirmar para cada uno: disponibilidad,
   soporte de modo estructurado estricto (sobre todo en Groq), si acepta
   `temperature` (algunos modelos recientes de Anthropic la rechazan:
   `enviar_temperatura: false`) y si razona por defecto.
2. **Verificar precios** en las páginas oficiales, actualizar `precios.json`
   (`verificado: true`, `fecha_consulta`) y repetir el dry-run.
3. **Claves de API** de OpenAI, Anthropic y Groq en variables de entorno de la
   máquina que ejecuta (nunca en el repositorio).
4. **Presupuesto:** fijar `--max-costo-usd` (sugerencia: piloto real 5 USD;
   estudio con los modelos de la matriz ≈ 40 USD, holgura sobre los ≈ 19
   esperados; el máximo teórico es ≈ 123 USD).
5. Ejecutar primero `--limite 20` y revisar a mano algunas respuestas de cada
   brazo, luego el piloto real, y solo después el estudio.
6. Decidir si la reparación incluye el texto de origen (`incluir_entrada`): sin
   él no puede recuperar líneas truncadas; con él cuesta más entrada.

## Equivalencia con los experimentos previos (E1–E5)

Los experimentos de `generative/` usaron modelos de **un solo proveedor**
(tres modelos Claude vía sub-agentes, temperatura por defecto), n = 6–10 por
celda y lectura estricta.

| Previo | Qué medía | Equivalente en V2/V3 | Diferencias |
|---|---|---|---|
| **E1** fidelidad de serialización | mismo contenido, 6 formatos, `parseable` y `round_trip` | **V2 extracción**, brazos B (JSON) y D (`.mini`); A sustituye al CSV/pipe hecho a mano | varios proveedores; brazo C nuevo; lectura tolerante; clasificación de corrupción **sin aviso**; texto con caracteres conflictivos reales; tokens y costo reportados por la API |
| **Ablación** (borrador v1 con solo escapes) | efecto de la regla de protección del separador | no incluida; se reproduce añadiendo un brazo con otro bloque de especificación | — |
| **E2** transferencia a forks no vistos | `.mini` en `tc`, `log`, `cls` solo con el bloque de especificación | **V2 brazo D** sobre 14 forks (incluye `ext-tc`, `ext-log`, `ext-cls`) | contenido estresado; comparación con A/B/C; reparación selectiva |
| **E3** síntesis de parser | el modelo escribe un parser desde la especificación | fuera de alcance (no mide salidas estructuradas) | se mantiene como E3 |
| **E4** punto de equilibrio | costo del bloque de especificación frente al ahorro por registro (conteo determinista) | tokens de entrada y salida **facturados** por brazo en V2, incluida la reparación; el dry-run usa el mismo tokenizador que E4 | punto de equilibrio empírico por modelo en lugar de teórico |
| **E5** truncamiento | cortes aleatorios de documentos serializados y lectores tolerantes | **V3a** (mismo método sobre salidas reales de modelos, con los lectores de cada brazo) y **V3b** (truncamiento real por `max_tokens`) | lectores del brazo (B/C con `json.loads`, sin recuperación parcial); métrica de eficiencia idéntica |

## Riesgos y amenazas a la validez

* **Simulación:** las tasas de falla del simulador son inventadas; los
  resultados simulados no deben mezclarse ni citarse junto a los reales (se
  guardan en `resultados/simulado/` y llevan la marca en muestras, manifiesto,
  tablas y figuras).
* **Lector del brazo A:** representa a un equipo "sin biblioteca"; otro equipo
  podría escribir un lector más defensivo. El lector está documentado y fijo.
* **Brazo B:** `json.loads` sin recuperación parcial es deliberado (práctica
  común), pero penaliza el truncamiento; un lector JSON tolerante sería un
  brazo adicional.
* **Estrés artificial:** los fragmentos insertados son realistas pero no
  provienen de datos de producción; en `cls` alteran el conjunto de etiquetas.
* **IC por registro optimistas** (correlación dentro de la muestra).
* **Tokenizador y precios** del dry-run aproximados; costo máximo muy por encima
  del esperado porque supone agotar `max_tokens`.
* **Modelos cambiantes:** identificadores y precios pueden variar entre la
  estimación y la ejecución; el manifiesto guarda la configuración y el commit,
  y cada muestra guarda el `model` que devuelve la API.
* **Latencia:** se mide en el cliente e incluye red y colas del proveedor.
* **Reparación en truncamiento:** sin texto de origen gasta llamadas sin
  recuperar la línea cortada; conviene decidir la política antes del estudio.
