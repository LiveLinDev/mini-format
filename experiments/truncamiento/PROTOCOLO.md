# V3a — truncamiento y recuperación sobre textos conocidos: PROTOCOLO

Estado: **fijado antes de ejecutar** la corrida completa. Este archivo no se edita después de ver
resultados; cualquier cambio posterior va únicamente en la sección «Enmiendas» al final, con fecha,
motivo y una nota de si se hizo antes o después de ver cifras.

Procedencia de la corrida: `reproducido_local` (todo local, sin modelos, sin claves, gasto 0 USD).
Identificador de estudio: `V3a`. V3b (generación real con `max_tokens`) es otro flujo y no se mezcla aquí.

## 1. Pregunta y alcance

Cuando la salida de un modelo se corta por el límite de tokens de salida, ¿qué parte de los registros
que **sí llegaron completos** puede recuperar cada formato con un lector razonable?

Este estudio **no** genera nada con modelos: toma documentos cuyo contenido exacto se conoce, los
serializa en cada formato, los corta como lo haría un `max_tokens` y mide qué recupera cada lector.
No es una afirmación universal sobre JSON ni sobre `.mini`: el caso histórico 38/40 de CIMA
(`reportado_historico`) no se sustituye ni se reproduce aquí.

Lo que el diseño **no** puede medir (se declara de antemano): cómo cortan de verdad los modelos, el
efecto del cierre espontáneo del modelo antes del límite, ni la calidad semántica de lo generado.

## 2. Documentos de referencia

Cada documento tiene **n = 50 registros solicitados** y una lista exacta de registros de referencia
(se publica en `documentos.json` de la corrida).

**A. Catorce dominios sintéticos** (prefijos `a, card, cat, cls, code, log, map, ner, q, r, s, sum, tc, us`):
`experiments/comun.generar(prefijo, 50, "muestreo", semilla=20260914)`. Son **datos sintéticos
etiquetados**: 12 registros base por dominio, barajados en bloques con la semilla registrada e
identificadores frescos. Contrato: `forks/<prefijo>/contract.json`. Formato `.mini` académico 1.0/1.1,
leído con `minifmt.Reader`.

**B. Cuatro snapshots públicos archivados** (`benchmark/public/data/*.json`, verificados contra
`benchmark/public/sources.json`): `products`, `users`, `comments`, `earthquakes`. Se toman los
**primeros 50 registros en el orden archivado**; la envoltura (campos que no son registros) se deja
tal cual, por lo que sus contadores (`total`, `limit`…) describen el archivo original y no los 50
registros: es parte del dato y no se corrige. Contrato `.mini`: perfil de dominio `mini-domain/1`,
`minifmt.domain.infer_contract([documento_50], prefix=id)` (el contrato se aprende del propio documento:
este estudio mide recuperación bajo corte, no generalización del contrato).

Naturaleza de los datos (tal como declara `sources.json`, no como suele resumirse): `products`, `users`
y `comments` son **datos de prueba públicos y ficticios** (DummyJSON y JSONPlaceholder);
solo `earthquakes` (USGS, enero 2025) son **observaciones reales**. El informe lo distingue.

Precondición de integridad (se comprueba y se registra, no se ajusta): leer el texto **completo** de
cada formato debe devolver exactamente los registros fuente (JSON, JSON Lines) o registros equivalentes
bajo la normalización «clave omitida ≡ `null` y igualdad numérica entera/flotante» (`.mini` académico;
`mini-domain/1` es sin pérdida y se compara exacto). Un documento que falle para un formato se excluye
**solo de esa condición**, con su causa, en `exclusiones` de los resultados.

## 3. Texto propio de cada formato

Todos parten del mismo documento. Desplazamientos en **bytes UTF-8** del texto propio.

| Formato | Texto propio |
|---|---|
| JSON compacto | `json.dumps(doc, ensure_ascii=False, separators=(",", ":"))` (claves en el orden del documento). |
| JSON Lines | Línea 1: la envoltura (objeto con los campos que no son registros; omitida si no hay, p. ej. `comments`). Luego un objeto compacto por registro, cada línea terminada en LF. |
| `.mini` | `minifmt.dumps` (dominios) o `minifmt.domain.encode` (snapshots). Sin LF final. |

Un registro está **disponible** en un prefijo si **todo su contenido** está dentro del prefijo:
JSON y JSON Lines, hasta su `}` de cierre inclusive; `.mini`, hasta el último carácter de su línea
(el LF es separador, no contenido). Los desplazamientos de fin de registro se calculan
**construyendo** el texto pieza a pieza (no leyéndolo con el lector bajo prueba) y se verifica que la
concatenación coincide byte a byte con la serialización de la biblioteca.

## 4. Unidad de corte

* Tokenizador: `o200k_base`, vocabulario local `benchmark/vocab/o200k_base.tiktoken` (hash verificado),
  paquete `tiktoken`. Es el **conteo local exacto de o200k** y se usa aquí como **unidad de referencia**
  de un `max_tokens`; **no** es el tokenizador de Anthropic, Google ni DeepSeek (para ellos es una
  aproximación) y no hay conteo de solicitud ni `usage`.
* `T_ref` = tokens o200k del **JSON compacto** del documento.
* Límite `L_k = round(k/20 × T_ref)` para `k = 1..20`, con redondeo aritmético (mitad hacia arriba)
  hecho con enteros: `L_k = (2·k·T_ref + 20) // 40`.
* **Mismo `L_k` para todos los formatos**, aplicado a los tokens de **su propio texto**, como lo haría un
  `max_tokens` real: el prefijo son los primeros `L_k` tokens; si el texto tiene menos de `L_k` tokens el
  prefijo es el texto completo y el corte se registra `truncado = false`.
* Corte en frontera de token; el prefijo se reconstruye con los **bytes** de los tokens y se decodifica
  como UTF-8 incremental: una secuencia UTF-8 final incompleta se descarta. Nunca se inserta `U+FFFD`.
* En `k = 20` el JSON compacto cabe exactamente (texto completo). Esos cortes no se descartan: son parte
  del diseño pedido y se informan aparte en el análisis secundario (§8).
* Por cada prefijo se registra el número de registros completos **disponibles** (referencia).

## 5. Lectores (qué hace cada uno y por qué es razonable)

1. **`json_estricto`** — `json.loads` del prefijo. Si falla, recupera 0 registros. Razón: es lo que hace
   un consumidor ingenuo de un JSON; es el comparador de «sin tolerancia».
2. **`json_parcial_jiter`** — `jiter.from_json(prefijo, partial_mode="on")` (biblioteca **jiter**, versión
   registrada en el manifiesto; dependencia solo de bench/desarrollo). Devuelve el análisis parcial del
   JSON; los registros son los elementos del arreglo de registros **tal como jiter los entrega**, incluido
   un último elemento incompleto si lo hay (un consumidor real de JSON parcial lo vería). Modo `"on"`:
   descarta cadenas y claves incompletas al final (no `"trailing-strings"`). Un elemento parcial no cuenta
   como recuperado; cuenta como registro emitido espurio y baja la precisión. Si `jiter` lanza error, el
   corte recupera 0 y se anota `error_lector`.
3. **`jsonl`** — se separa el prefijo en LF; se analiza cada línea con `json.loads`; se descarta cualquier
   línea que no sea un objeto JSON completo (la final incompleta incluida). La línea de envoltura (si el
   documento la tiene) ocupa la posición 1 y no es registro. Razón: es el algoritmo estándar de JSON Lines.
4. **`mini_tolerante`** — el lector tolerante de la biblioteca: `minifmt.Reader(contrato, strict=False)`
   para los dominios y, para `mini-domain/1` (que no tiene lector incremental), el aislamiento línea a línea
   que usa `minifmt.domain.diagnose` (cabecera completa + cada línea decodificada sola con `n=1`).
   **Tal cual**: acepta una última línea sin LF si valida (así lo define `Reader.end`); no hay ninguna
   heurística para descartarla. Razón: es «el lector tolerante de `.mini`» que pide el diseño y no se le
   añade ni quita nada.
5. **`json_objetos_completos`** — comparador fuerte **de implementación propia de este estudio**
   (`experiments/truncamiento/lectores.py`): escáner incremental de llaves y cadenas (conoce escapes y
   anidación) que emite cada elemento completo del arreglo de registros y nunca uno parcial. Sirve para
   que `.mini` no gane por comparación contra lectores deliberadamente débiles: es el mejor lector de JSON
   que se puede construir sin heurística de completado.

**Variante declarada (análisis de sensibilidad, no primaria):** `mini_tolerante_sin_cola` — el mismo lector
que 4, pero el consumidor **sabe que el límite cortó la salida** (`truncado = true`, como un
`finish_reason = length`) y descarta la última línea si el prefijo no termina en LF. Razón: el lector tal
cual (4) puede emitir una última línea válida pero con un campo final cortado; esta variante cuantifica el
costo de esa política. Si el texto no se cortó (`truncado = false`), no se descarta nada.

## 6. Métricas por (documento, lector, corte)

Sea `E` la lista de registros que emite el lector, `R` la referencia (registros exactos del documento
en su representación canónica, `json.dumps(sort_keys=True)`) y `D` los disponibles.
La coincidencia es de **multiconjunto** (un registro de la referencia solo se usa las veces que aparece).

* `identicos` = Σ mín(apariciones en `E`, apariciones en `R`).
* `recuperados` = mín(`identicos`, `D`).
* `completados_heuristicamente` = `identicos − recuperados`: registros emitidos idénticos a la referencia
  cuyo texto **no** estaba completo en el prefijo (el lector «adivinó» lo que faltaba). No cuentan como recuperados.
* `duplicados` = apariciones de un registro de la referencia en `E` por encima de las que tiene `R`.
* `espurios` = registros emitidos que no son ningún registro de la referencia (parciales con valores
  cortados, inventados). `|E| = identicos + duplicados + espurios`.
* `recall_disponibles` = `recuperados / D` — **null si `D = 0`**.
* `recall_solicitados` = `recuperados / 50` (el denominador nunca es cero).
* `precision` = `recuperados / |E|` — **null si `|E| = 0`**.

Un denominador cero es **null**, nunca 0 ni 1; esos cortes se excluyen del agregado que lo necesita y su
número se informa.

## 7. Agregación e intervalos

Los 20 cortes de un documento son observaciones **relacionadas**: el documento es el conglomerado.

* Razón agregada `Σ num / Σ den` sobre cortes con denominador > 0 (estimador de razón).
* **IC 95 % por bootstrap de conglomerados**: se remuestrean documentos (no cortes) con reemplazo,
  `B = 10 000`, `numpy.random.default_rng(20260930)`, percentiles 2,5 y 97,5. Si una réplica tiene
  denominador total 0, se descarta y se cuenta.
* Las curvas por corte (`recuperados/solicitados` media por `k`) remuestrean documentos igual.
* Estratos informados: los 18 documentos juntos; 14 sintéticos; 4 snapshots (3 de prueba públicos + 1 real).
  Cada documento pesa por sus registros disponibles (razón), no por igual; además se informa el mínimo por documento.

## 8. Criterio (fijado aquí, antes del análisis)

Meta documental: **recuperar ≥ 90 % de los registros completos disponibles**.

* **Primaria.** Condición `mini_tolerante`. Estadístico: `Σ recuperados / Σ disponibles` sobre **todos los
  cortes con `disponibles > 0`** (k = 1..20) de los 18 documentos. `cumple` si el punto es ≥ 0,90;
  `no_cumple` si no. Se informa el IC 95 % por conglomerado y si su extremo inferior también es ≥ 0,90,
  pero la decisión usa el punto.
* **Secundarios (informan, no deciden):** (a) lo mismo solo sobre cortes **efectivamente truncados**
  (`truncado = true`), porque en los cortes altos `.mini` ya cabe completo y eso infla la razón; (b)
  mínimo por documento y por dominio; (c) los demás lectores, incluida la variante sin cola;
  (d) `recuperados/solicitados` por `k`; (e) precisión y cortes con registro espurio.
* **Expectativas declaradas (no son criterios):** `json_estricto` ≈ 0 hasta `k = 20`; los lectores
  capaces (`jsonl`, `json_objetos_completos`, `json_parcial_jiter`, `mini_tolerante`) recuperan casi todo
  lo disponible, de modo que la meta no separa formatos por recall sobre lo disponible; la diferencia
  esperada está en cuántos registros **caben** (`disponibles/solicitados`) y en la **precisión** del
  último registro. Si `.mini` no mejora sobre `jsonl` o `json_objetos_completos` en recall sobre
  disponibles, se dice.
* La interpretación de este criterio queda **sujeta a aprobación del asesor** (`aprobacion_asesor:
  pendiente` en el manifiesto). El veredicto `cumple`/`no_cumple` del manifiesto aplica la regla fijada
  aquí; no sustituye esa aprobación.

## 9. Reproducción

```
python tools/ejecutar_v3a.py            # corrida completa (18 documentos × 20 cortes × lectores)
python tools/ejecutar_v3a.py --rapido   # humo: 3 documentos, 5 cortes, sin escribir evidencia
```

Dependencias: `tiktoken`, `jiter` (nueva, bench/dev), `numpy`, `matplotlib`, `pyyaml`. Sin red.
Salidas en `evidencia/corridas/v3a-<sello>/`: `manifiesto.json`, `cortes.csv`, `resumen_lectores.csv`,
`curvas.csv`, `por_documento.csv`, `resultados.json`, `documentos.json`, `figura_v3a.png`.

## 10. Limitaciones declaradas de antemano

1. Datos sintéticos (14) o de prueba (3); solo un conjunto real.
2. Los cortes son deterministas y los hace un tokenizador de referencia, no un proveedor.
3. Los lectores son implementaciones concretas; el resultado vale para esas implementaciones
   (jiter, `json.loads`, el lector propio, `minifmt`), no para «JSON» o «.mini» en abstracto.
4. `.mini` mide `minifmt` (Python); el puerto TypeScript no se ejecuta aquí.
5. Un registro emitido pero con un campo final cortado que aun así valida es el riesgo específico de
   los formatos sin delimitador de cierre; el estudio lo mide (`espurios`), no lo corrige.
6. El corte de los modelos reales no cae en posiciones uniformes: los 20 cortes son una malla, no una muestra.

## Enmiendas

(ninguna)
