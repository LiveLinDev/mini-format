# Experimentos V1 (eficiencia en tokens) y V4 (modelo de costos)

Ambos experimentos son deterministas y **no llaman a ningún modelo de lenguaje**:
serializan datos sintéticos, cuentan tokens con tokenizadores locales y combinan
esos recuentos con precios publicados.

```bash
python experiments/v1_tokens/run.py    # ≈ 2 min: tokens, ahorros, instrucción, equilibrio en tokens, figuras
python experiments/v4_costos/run.py    # < 10 s: costos, ahorro anual, equilibrio monetario (ejecuta V1 si falta)
```

Requisitos: los del benchmark (`tiktoken` o los vocabularios de `benchmark/vocab`,
PyYAML, `regex`, Node ≥ 22 para el codificador oficial de TOON) más `numpy` y
`matplotlib`. No modifican `benchmark/` ni `src/`; solo los importan.

| Ruta | Contenido |
|---|---|
| `comun.py` | generador de datos con semilla, tokenizadores, bootstrap, interpolación del punto de equilibrio |
| `v1_tokens/run.py`, `v1_tokens/instruccion.py` | experimento V1 y bloques de instrucción (.mini y JSON Schema) |
| `v1_tokens/results/*.csv` | datos crudos y resúmenes de V1 |
| `v1_tokens/results/instrucciones_muestra/` | textos exactos de instrucción medidos (familias `a` y `cls`) |
| `v4_costos/precios.json` | precios por millón de tokens con URL y fecha de consulta |
| `v4_costos/run.py`, `v4_costos/results/*.csv` | experimento V4 y sus resultados |
| `*/figures/*.png` | figuras (texto en español) |

## 1. Reproducción de la línea base

`v1_tokens/run.py` vuelve a serializar los 14 dominios con n = 12 y el protocolo
original (`domains.expand`), cuenta con `o200k_base` y compara celda a celda con
`benchmark/results/summary_12.csv`. Además se ejecutó `python benchmark/run_benchmark.py`
sobre este árbol y `git status` quedó limpio (los CSV publicados se regeneran idénticos).

| Cambio en tokens de .mini (media de 14 dominios) | Publicada | Reproducida | Rango por dominio (reproducido) |
|---|---|---|---|
| .mini vs JSON compacto | −33,8 % | −33,8 % | −39,5 a −27,3 % |
| .mini vs TOON (oficial, tal cual) | −37,4 % | −37,4 % | −48,3 a −2,3 % |
| .mini vs TOON aplanado | −7,0 % | −7,0 % | −18,6 a 0,0 % |
| .mini vs CSV aplanado | +5,0 % | +5,1 % | −8,4 a +14,5 % |

Las 168 celdas (tokens por formato y porcentajes por dominio) coinciden exactamente
(`linea_base_n12.csv`). La única diferencia es de redondeo en el agregado de CSV: el
5,0 % publicado es la media de los porcentajes ya redondeados a un decimal (5,04 %); la
media sin redondear es 5,06 %.

## 2. Protocolo V1

* **Dominios:** las 14 familias de `forks/`.
* **Tamaños:** n ∈ {1, 5, 10, 25, 50, 100, 250} registros por documento.
* **Datos:** los generadores existentes solo tienen 12 registros base por dominio. Se
  usan dos variantes:
  * `muestreo` (principal): identificadores y cabecera de `domains.expand(prefix, n)`;
    el contenido de cada registro sale de bloques de 12 registros base barajados con
    `random.Random("20260914:<prefijo>")`. Evita que n = 1 sea siempre el primer
    registro y que el orden sea periódico.
  * `ciclo` (sensibilidad): exactamente `domains.expand`, el protocolo publicado.
* **Formatos:** JSON indentado, JSON compacto, YAML, XML, CSV aplanado, TOON oficial
  (tal cual y aplanado, codificador de referencia v4.1.1 en `benchmark/toon_ref`) y .mini.
* **Tokenizadores:** `o200k_base` y `cl100k_base` (tiktoken). Tercer tokenizador:
  `r50k_base` (GPT-2), cargado desde `whisper/assets/gpt2.tiktoken`, que ya estaba
  instalado y cuyo sha256 (`306cd27f…`) coincide con el hash oficial de `r50k_base`
  en `tiktoken_ext`. No se descargó nada. En `~/.cache/huggingface` solo está
  `sentence-transformers/clip-ViT-B-32`: su tokenizador CLIP pasa todo a minúsculas y
  normaliza los espacios en blanco, así que no sirve para medir formatos de texto.
* **Métricas:** tokens por documento y por registro; ahorro = 1 − T(.mini)/T(formato)
  por dominio; media, mediana, rango e IC 95 % bootstrap percentil (10 000 re-muestreos
  de los 14 dominios, semilla 20260914). Ida y vuelta: `minifmt.roundtrip_ok`
  (objeto → .mini → objeto, más estabilidad del texto) para .mini y el decodificador
  oficial para TOON.

**Ida y vuelta:** 196 documentos .mini y 392 TOON (2 variantes × 14 dominios × 7 tamaños);
cero fallos.

### 2.1 Ahorro de .mini por tokenizador (n = 100, variante `muestreo`)

Media sobre 14 dominios [IC 95 %]. Un valor positivo significa que .mini usa menos tokens.

| .mini frente a | o200k_base | cl100k_base | r50k_base (GPT-2) |
|---|---|---|---|
| JSON indentado | 59,3 [56,8; 61,8] | 58,2 [55,4; 61,0] | 73,6 [71,0; 76,1] |
| JSON compacto | **34,8 [32,7; 36,9]** | 32,7 [30,4; 35,1] | 30,4 [27,9; 33,0] |
| YAML | 45,6 [42,6; 48,8] | 44,6 [41,4; 47,9] | 42,2 [39,2; 45,1] |
| XML | 63,1 [60,1; 66,0] | 61,8 [58,3; 65,2] | 67,4 [63,6; 70,8] |
| CSV aplanado | −2,6 [−4,7; −0,4] | −3,3 [−5,2; −1,2] | −1,0 [−2,3; 0,4] |
| TOON (oficial, tal cual) | 37,4 [28,7; 44,1] | 36,1 [27,3; 43,0] | 42,9 [34,1; 50,0] |
| TOON aplanado (tabular) | 2,0 [−0,1; 4,4] | 1,3 [−0,8; 3,6] | 3,3 [1,6; 5,0] |

Medianas, rangos y los demás tamaños están en `v1_tokens/results/ahorro_resumen.csv`.
Frente a JSON compacto, el ahorro por dominio va de 27,9 % a 41,7 % (o200k, n = 100).

### 2.2 Cómo cambia el ahorro con n (o200k_base, `muestreo`)

| .mini frente a | n=1 | n=5 | n=10 | n=25 | n=50 | n=100 | n=250 |
|---|---|---|---|---|---|---|---|
| JSON indentado | 55,3 | 57,9 | 58,5 | 59,1 | 59,2 | 59,3 | 59,3 |
| JSON compacto | 27,0 | 32,5 | 33,5 | 34,4 | 34,6 | 34,8 | 34,9 |
| YAML | 36,9 | 43,1 | 44,3 | 45,3 | 45,5 | 45,6 | 45,7 |
| XML | 50,3 | 59,8 | 61,6 | 62,6 | 62,9 | 63,1 | 63,2 |
| CSV aplanado | −26,2 | −8,6 | −5,5 | −3,6 | −3,0 | −2,6 | −2,4 |
| TOON oficial | 34,8 | 37,0 | 37,3 | 37,5 | 37,4 | 37,4 | 37,4 |
| TOON aplanado | 30,5 | 13,1 | 8,1 | 4,3 | 2,8 | 2,0 | 1,6 |

* Frente a formatos que repiten estructura en cada registro (JSON, YAML, XML), el ahorro
  **crece con n** y se estabiliza desde n ≈ 25: la cabecera .mini se amortiza y el
  ahorro por registro es constante (ajuste lineal T(n) = a + b·n con R² ≥ 0,9999).
* Frente a formatos tabulares (CSV, TOON aplanado), la ventaja de .mini **se reduce con
  n**: con documentos pequeños pesa el encabezado de columnas de CSV/TOON; con documentos
  grandes ambos convergen a ≈ 40 tokens por registro (.mini 40,1; TOON aplanado 41,0;
  CSV 39,3 a n = 100). CSV no transmite metadatos de documento ni tipos, así que su
  cabecera no es comparable (con n = 1, CSV omite toda la cabecera .mini).
* **Sensibilidad `ciclo` vs `muestreo`:** con n = 100 las medias coinciden a ±0,1 puntos;
  con n = 1 difieren como máximo 1,3 puntos (el registro que se usa cambia).
* **Sensibilidad al tokenizador:** frente a JSON compacto, cl100k da 2,1 puntos menos que
  o200k y r50k 4,4 puntos menos; frente a JSON indentado r50k da mucho más (73,6 %)
  porque GPT-2 codifica cada espacio de la indentación por separado (8 espacios = 8 tokens en
  r50k frente a 1 en o200k).

Figuras: `v1_tokens/figures/fig1_ahorro_vs_n.png`, `fig2_tokens_por_registro.png`,
`fig3_ahorro_por_dominio_n100.png`.

## 3. Sobrecarga de instrucción y punto de equilibrio

Bloques medidos por familia e idioma (`v1_tokens/instruccion.py`):

* `mini_spec`: `spec_block(contract, lang)` sin cambios; `mini_spec_ejemplo`: con un ejemplo de 1 registro.
* `json_schema`: frase de instrucción + JSON Schema derivado del contrato (compacto; con los
  mismos tipos, enumerados, rangos, aridades y descripciones que el bloque .mini;
  sin `additionalProperties:false`, lo que favorece a JSON).
* `json_schema_ejemplo`: esquema + el mismo ejemplo de 1 registro en JSON compacto.
* `json_ejemplo`: frase + solo el ejemplo JSON (instrucción mínima, el caso más adverso para .mini).

Tokens medios de instrucción (14 dominios):

| Tokenizador / idioma | mini_spec | mini_spec_ejemplo | json_schema | json_schema_ejemplo | json_ejemplo |
|---|---|---|---|---|---|
| o200k / es | 416 | 495 | 289 | 394 | 137 |
| o200k / en | 372 | 450 | 287 | 391 | 134 |
| cl100k / es | 441 | 523 | 280 | 385 | 138 |
| cl100k / en | 370 | 450 | 277 | 380 | 132 |

La especificación .mini es más larga que el esquema en 12 de 14 familias. Las excepciones
son `a` y `q`, con cabecera de tupla y listas: en `a` el esquema es más largo en ambos
idiomas; en `q` lo es en inglés, y en español .mini lo supera por solo 17 tokens (o200k).

**Punto de equilibrio en tokens** (`equilibrio_tokens*.csv`): menor n por llamada con
ΔO(n) = T_JSON(n) − T_.mini(n) ≥ ΔI = I_.mini − I_JSON, interpolado sobre la rejilla medida.
Salida en JSON compacto; o200k; mediana [mín; máx] de 14 dominios:

| Instrucción .mini vs JSON | es | en |
|---|---|---|
| mini_spec vs json_schema | 7,8 [1; 13,7] | 5,6 [1; 10,0] |
| mini_spec_ejemplo vs json_schema_ejemplo | 6,7 [1; 12,5] | 4,5 [1; 8,8] |
| mini_spec vs json_ejemplo | 14,8 [5,8; 25,4] | 12,7 [4,7; 21,8] |
| mini_spec_ejemplo vs json_ejemplo | 19,0 [9,3; 29,8] | 16,8 [8,2; 26,1] |

Con cl100k las medianas suben (10,2 y 17,4 en español para las filas 1 y 3); con r50k,
a 14,0 y 21,3.

**Punto de equilibrio monetario** (`v4_costos/results/equilibrio_dinero.csv`,
`equilibrio_curva_razon.csv`): la condición pasa a ser p_out·ΔO(n) ≥ p_in_ef·ΔI; solo
importa la razón ρ = p_in_ef/p_out. Sin caché, ρ = 0,12–0,25 en los modelos consultados y
la mediana de n* baja a **1,0–1,9 registros** (mini_spec vs json_schema) o 1,7–3,6
(vs json_ejemplo); el peor dominio necesita como máximo 3,2 y 6,1 registros. **Con caché
de prompt** (ρ = 0,005–0,02) la instrucción queda compensada desde el primer registro
en todas las familias. Supuesto de caché: estado estacionario, todas las llamadas leen la
instrucción de la caché; no se cuentan la escritura inicial (1,25× la entrada en Anthropic),
el almacenamiento por hora (Google), el tiempo de vida de la caché ni el mínimo de tokens
cacheables, que puede exigir que el prompt de sistema completo supere un umbral. En Groq no
hay precio de caché publicado, así que el escenario con caché usa el precio normal.

## 4. V4 — modelo de costos

`costo_llamada = I_f·p_in_ef + O_f(k)·p_out`, `costo_1000 = (1000/k)·costo_llamada`, promedio
de 14 dominios, tokens o200k, instrucción en español (`mini_spec` para .mini y `json_schema`
para JSON). Solo cuenta la parte del costo que **depende del formato**: el contenido de
entrada de la tarea es el mismo para todos los formatos y queda fuera.

Precios (USD por millón de tokens) leídos en las páginas oficiales el **2026-09-15**. La
sesión empezó el 14-sep, pero la lectura ocurrió después de medianoche; el detalle está en
`precios.json`.

| Proveedor | Modelo | Entrada | Entrada en caché | Salida | Fuente |
|---|---|---|---|---|---|
| OpenAI | GPT-5.4 (contexto corto) | 2,50 | 0,25 | 15,00 | developers.openai.com/api/docs/pricing |
| OpenAI | GPT-5.4 mini | 0,75 | 0,075 | 4,50 | ídem |
| OpenAI | GPT-5 mini | 0,25 | 0,025 | 2,00 | ídem |
| Anthropic | Claude Opus 5 | 5,00 | 0,50 | 25,00 | platform.claude.com/docs/en/about-claude/pricing |
| Anthropic | Claude Sonnet 5 | 2,00 | 0,20 | 10,00 | ídem |
| Anthropic | Claude Haiku 4.5 | 1,00 | 0,10 | 5,00 | ídem |
| Google | Gemini 3.5 Flash | 1,50 | 0,15 | 9,00 | ai.google.dev/gemini-api/docs/pricing |
| Google | Gemini 3.1 Pro Preview (≤200k) | 2,00 | 0,20 | 12,00 | ídem |
| Google | Gemini 2.5 Flash | 0,30 | 0,03 | 2,50 | ídem |
| Groq | GPT OSS 120B | 0,15 | no publicado | 0,60 | console.groq.com/docs/models |
| Groq | GPT OSS 20B | 0,075 | no publicado | 0,30 | ídem |
| DeepSeek | DeepSeek V4.1 Flash (hora pico) | 0,30 | 0,006 | 1,20 | api-docs.deepseek.com/quick_start/pricing |

**Costo por 1 000 registros y ahorro anual de .mini frente a JSON compacto** (25 registros por llamada):

| Modelo | JSON USD/1000 | .mini USD/1000 | Ahorro | Ahorro anual 10 mil reg. | 1 millón | 100 millones | Ahorro con caché |
|---|---|---|---|---|---|---|---|
| GPT-5.4 | 0,9601 | 0,6559 | 31,7 % | 3,04 | 304 | 30 415 | 33,8 % |
| GPT-5.4 mini | 0,2880 | 0,1968 | 31,7 % | 0,91 | 91 | 9 124 | 33,8 % |
| GPT-5 mini | 0,1270 | 0,0861 | 32,3 % | 0,41 | 41 | 4 098 | 33,9 % |
| Claude Opus 5 | 1,6097 | 1,1071 | 31,2 % | 5,03 | 503 | 50 267 | 33,7 % |
| Claude Sonnet 5 | 0,6439 | 0,4428 | 31,2 % | 2,01 | 201 | 20 107 | 33,7 % |
| Claude Haiku 4.5 | 0,3219 | 0,2214 | 31,2 % | 1,01 | 101 | 10 053 | 33,7 % |
| Gemini 3.5 Flash | 0,5760 | 0,3935 | 31,7 % | 1,82 | 182 | 18 249 | 33,8 % |
| Gemini 3.1 Pro Preview | 0,7680 | 0,5247 | 31,7 % | 2,43 | 243 | 24 332 | 33,8 % |
| Gemini 2.5 Flash | 0,1587 | 0,1074 | 32,3 % | 0,51 | 51 | 5 129 | 33,9 % |
| GPT OSS 120B (Groq) | 0,0390 | 0,0271 | 30,6 % | 0,12 | 12 | 1 191 | 30,6 %* |
| GPT OSS 20B (Groq) | 0,0195 | 0,0135 | 30,6 % | 0,06 | 6 | 596 | 30,6 %* |
| DeepSeek V4.1 Flash | 0,0780 | 0,0541 | 30,6 % | 0,24 | 24 | 2 382 | 34,0 % |

\* sin precio de caché publicado. Montos anuales en USD, sin caché.

* El **porcentaje** de ahorro depende casi solo de la razón entrada/salida y del tamaño de
  llamada; el **monto** escala con el precio de salida.
* Con k registros por llamada, el ahorro frente a JSON compacto sin caché va de −2,6 % a
  9,2 % con k = 1 (con un solo registro y sin caché, .mini sale 2,6 % más caro en los modelos
  con razón entrada/salida 0,25: GPT OSS y DeepSeek; con caché, 24–27 % de ahorro), 25,5–29,3 % con k = 10, 30,6–32,3 % con k = 25 y 33,4–33,9 % con k = 100.
* Frente a los otros formatos (k = 25, sin caché): JSON indentado + JSON Schema 55,5–57,0 %;
  contando solo la salida porque no se midió su instrucción, YAML 44,9 %, XML 61,2 %,
  TOON oficial 41,4 %, TOON aplanado 4,6 % y CSV −2,6 %
  (`ahorro_anual.csv`).

Figuras: `v4_costos/figures/fig1_costo_1000_registros.png`, `fig2_ahorro_anual_1M.png`,
`fig3_equilibrio_vs_razon_precios.png`.

## 5. Supuestos y amenazas a la validez

**Validez de constructo**
* Se miden tokens de documentos **ideales** generados por serializadores, no salidas reales
  de modelos. Un modelo puede añadir texto, errores o reintentos; eso lo evalúan V2/V3 con
  generación real y no está incluido aquí.
* La salida se compara con la instrucción equivalente, pero la calidad o validez que logra
  cada instrucción no se mide. Un JSON Schema usado con *structured outputs* puede cobrarse o
  procesarse de otra forma según el proveedor.
* CSV y TOON aplanado pierden metadatos (CSV) o necesitan aplanar el esquema; no son
  equivalentes semánticos completos.

**Validez interna**
* Los recuentos son exactos para `o200k_base`, `cl100k_base` y `r50k_base`. Para los modelos,
  `o200k_base` es exacto en GPT-5 mini (tiktoken lo asigna a ese vocabulario) y en gpt-oss
  (`o200k_harmony`, codificación de texto idéntica, verificado). En GPT-5.4 y GPT-5.4 mini se
  **supone** o200k, porque tiktoken 0.13 no publica el mapeo. Para **Anthropic, Google y DeepSeek
  los tokens son una aproximación**: cada proveedor usa su propio tokenizador, y la página de
  Anthropic advierte que Claude 4.7 y posteriores generan alrededor de 30 % más tokens para el
  mismo texto. Se espera que el porcentaje de ahorro sea más estable que el monto absoluto
  (los tres tokenizadores medidos varían 4,4 puntos frente a JSON compacto), pero no se ha verificado.
* Punto de equilibrio: interpolación lineal sobre n ∈ {1, 5, 10, 25, 50, 100, 250}; un valor
  n* ≤ 1 se reporta como 1.

**Validez externa**
* Cada dominio tiene solo 12 registros base; con n > 12 el contenido se repite y solo cambian
  los identificadores. Las curvas miden longitud de serialización, no diversidad semántica.
  Dominios con textos más largos por registro tendrán menos ahorro relativo, y dominios con
  campos cortos, más.
* Hay 14 dominios y siete están en español: el IC bootstrap describe la variación entre
  estos dominios, no una población de dominios.
* Los precios cambian con frecuencia (por ejemplo, Google anuncia aumentos para 2027-01-01 en
  algunos modelos). Los resultados valen para la fecha de consulta; basta editar
  `precios.json` y volver a ejecutar V4.
* El escenario con caché es una cota optimista: ignora escritura, almacenamiento, tiempo de
  vida y tamaño mínimo cacheable.

**Pendientes**
* Tercer tokenizador de un modelo de lenguaje abierto **actual** (Llama 3, Qwen, Mistral):
  no hay ninguno en caché local y no se descargó. `r50k_base` (GPT-2, modelo abierto) sirve
  como tercer tokenizador, pero es de 2019 y no representa los vocabularios de 128 mil a
  200 mil tokens de los modelos actuales.
* Precio de caché de Groq (no publicado) y precios de Mistral (no consultados).
