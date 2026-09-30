# OPT — optimización especializada, reversible y medible

Pregunta: ¿cuánto se ahorra, contando **todo lo que se transmite al modelo**, si en lugar del flujo estándar se diseña a mano
un contrato `.mini` dentro de SPEC 1.1 y se compara con JSON compacto? Y, igual de importante, ¿cuándo **no** se ahorra?

Todo es local: sin red, sin claves, sin llamadas a APIs de modelos. Los tokens son conteos locales del texto completo con tres
vocabularios BPE archivados en `benchmark/vocab` (`o200k_base`, `cl100k_base`, `r50k_base`); aproximan, no son `usage` ni conteo
de solicitud de ningún proveedor, y son solo una aproximación para Anthropic, Google o DeepSeek.

## Qué se comparó

| Perfil | Qué es |
|---|---|
| `json_compacto` | Línea base: JSON sin espacios del objeto de la aplicación envuelto en `{clave:[…]}`. Su instrucción cuenta 0 tokens en la lectura primaria (favorable a JSON); la lectura secundaria suma instrucción + JSON Schema compacto. |
| `json_legible` | El mismo JSON con sangría (aparte). |
| `general_fromschema` | Flujo estándar: `mini from-schema` + `spec_block` en español, lo que imprime `mini prompt --contract … --lang es`. |
| `general_dominio` | Flujo estándar alternativo: `mini build` (perfil `mini-domain/1`) inferido de 100 registros de desarrollo; su `make_prompt`. |
| `especializado` | Contrato diseñado a mano (orden, tipos acotados, constantes en la cabecera, códigos cortos, enteros escalados) con **mapa explícito** y dos instrucciones: `spec_block` sobre ese contrato y una plantilla compacta propia (`instruccion_compacta`). |
| `json_abreviado` | Control: JSON con las mismas abreviaturas que el especializado. Separa lo que ahorra el formato de lo que ahorran las abreviaturas. |

Cada instrucción se mide **sin ejemplo** y **con ejemplo** de 2 registros. El total de una respuesta es el conteo del texto
`instrucción + salto doble + salida` tokenizado como **un solo texto**, nunca una suma de fragmentos.

Dominios (etiquetados con claridad):

* `tickets` — **representativo**: el hilo de «Cómo funciona» (mesa de ayuda). Sintético determinista.
* `eventos` — **FAVORABLE**: muchos campos cortos y enumerados, fecha constante por lote. Sintético y diseñado con esa forma; su ahorro **no es una promesa general**.
* `comentarios` — texto libre largo, los comentarios públicos de JSONPlaceholder (`benchmark/public/data/comments.json`, MIT). El caso de menor ahorro; se publica igual.

Lotes n ∈ {1, 5, 10, 25, 50, 100, 250} (hasta 5 lotes disjuntos por tamaño) y, para el punto de equilibrio, n = 1…250 anidados.

## Criterio fijado antes de medir

[`criterio.json`](criterio.json) se versionó en dos commits (`c196ec9`, `42b3c91`) **anteriores** a cualquier medición sobre los datos
de prueba; el segundo solo precisa qué variante de instrucción es la primaria. Criterios: C1 (caso representativo, n = 100, los tres
tokenizadores: ahorro de salida del especializado ≥ 30 %), C2 (mismo caso: total del especializado < total de JSON compacto con instrucción 0)
y C3 (equivalencia exacta sin fallos). El resto es descriptivo. C3 se aplicó con la lectura estricta: cualquier fallo en los perfiles
evaluados (todos menos `mini build`) lo incumple; los fallos de `mini build`, si hubiera, se publicarían aparte.

La configuración se **diseñó** con una semilla de desarrollo (20260930; comentarios 0–149) y se **midió** con otra (20261001; comentarios 150–499).
La búsqueda, sus candidatos y lo descartado están en [`diseno/`](diseno/).

## Cifras

<!-- cifras:inicio (generado por tools/ejecutar_opt.py; no editar a mano) -->

Corrida `opt-20260930t191636z` (procedencia `reproducido_local`, commit `12f37c0`, árbol limpio: true). Resultado del criterio fijado de antemano: **cumple** (C1 salida ≥ 30 % en los tres tokenizadores: true; C2 total menor que JSON: true; C3 equivalencia exacta sin fallos: true).

### n = 100, tokenizador o200k_base (lectura primaria)

Media de los lotes medidos. «Salida» es el texto que devuelve el modelo; «Total» es instrucción + salida tokenizados como un solo texto. Positivo = .mini usa menos tokens que JSON compacto.

| Dominio | Perfil | Instrucción (tokens) | Salida | Total | Ahorro de salida | Ahorro del total vs JSON sin instrucción | Ahorro del total vs JSON con esquema |
|---|---|--:|--:|--:|--:|--:|--:|
| tickets (representativo) | JSON compacto (base) | 0 | 4068.8 | 4068.8 | — | — | — |
| | general: mini from-schema | 410 | 2703.2 | 3114.2 | +33.6 % | +23.5 % | +27.9 % |
| | general: mini build | 693 | 2725.2 | 3418.2 | +33.0 % | +16.0 % | +20.9 % |
| | especializado (instrucción compacta) | 220 | 2433.0 | 2654.0 | +40.2 % | +34.8 % | +38.6 % |
| eventos de planta (FAVORABLE) | JSON compacto (base) | 0 | 6598.6 | 6598.6 | — | — | — |
| | general: mini from-schema | 582 | 3977.2 | 4560.2 | +39.7 % | +30.9 % | +35.4 % |
| | general: mini build | 804 | 2465.0 | 3269.0 | +62.6 % | +50.5 % | +53.7 % |
| | especializado (instrucción compacta) | 363 | 1624.0 | 1988.0 | +75.4 % | +69.9 % | +71.9 % |
| comentarios (texto libre; ahorro pequeño) | JSON compacto (base) | 0 | 7187.0 | 7187.0 | — | — | — |
| | general: mini from-schema | 461 | 6084.3 | 6546.3 | +15.3 % | +8.9 % | +12.5 % |
| | general: mini build | 746 | 6102.3 | 6848.3 | +15.1 % | +4.7 % | +8.4 % |
| | especializado (instrucción compacta) | 270 | 6085.3 | 6356.3 | +15.3 % | +11.6 % | +15.0 % |

### n = 100, por tokenizador

| Dominio | Tokenizador | Ahorro de salida general | Ahorro de salida especializado | Ahorro del total general | Ahorro del total especializado | Instrucción general → especializada (tokens) |
|---|---|--:|--:|--:|--:|--:|
| tickets (representativo) | o200k_base | +33.6 % | +40.2 % | +23.5 % | +34.8 % | 410 → 220 |
|  | cl100k_base | +30.5 % | +37.8 % | +20.0 % | +32.1 % | 446 → 240 |
|  | r50k_base | +31.2 % | +38.1 % | +20.4 % | +32.4 % | 572 → 302 |
| eventos de planta (FAVORABLE) | o200k_base | +39.7 % | +75.4 % | +30.9 % | +69.9 % | 582 → 363 |
|  | cl100k_base | +39.1 % | +77.5 % | +29.9 % | +71.8 % | 621 → 377 |
|  | r50k_base | +42.7 % | +80.2 % | +33.1 % | +74.4 % | 791 → 477 |
| comentarios (texto libre; ahorro pequeño) | o200k_base | +15.3 % | +15.3 % | +8.9 % | +11.6 % | 461 → 270 |
|  | cl100k_base | +12.2 % | +12.2 % | +6.0 % | +8.5 % | 508 → 301 |
|  | r50k_base | +11.3 % | +11.3 % | +4.6 % | +7.3 % | 650 → 388 |

### Ahorro del total (instrucción con ejemplo + salida) según el tamaño de lote, o200k_base

Negativo = el .mini gasta MÁS que JSON compacto sin instrucción. Frente a un JSON que también lleva su esquema como instrucción el equilibrio llega antes (columna correspondiente de la tabla de n = 100).

| Dominio · perfil | n=1 | n=5 | n=10 | n=25 | n=50 | n=100 | n=250 |
|---|--:|--:|--:|--:|--:|--:|--:|
| tickets · general | -871.5 % | -162.5 % | -66.5 % | -6.6 % | +13.3 % | +23.5 % | +29.6 % |
| tickets · especializado | -450.9 % | -66.5 % | -14.0 % | +18.3 % | +29.2 % | +34.8 % | +38.1 % |
| eventos · general | -765.8 % | -135.0 % | -48.2 % | +4.5 % | +22.2 % | +30.9 % | +36.2 % |
| eventos · especializado | -442.7 % | -37.1 % | +18.9 % | +52.6 % | +64.1 % | +69.9 % | +72.9 % |
| comentarios · general | -590.3 % | -115.1 % | -50.0 % | -10.4 % | +2.5 % | +8.9 % | +12.8 % |
| comentarios · especializado | -341.6 % | -61.3 % | -23.0 % | +0.2 % | +7.8 % | +11.6 % | +13.9 % |

### Punto de equilibrio n* (menor n desde el cual el .mini gasta menos hasta n = 250)

«Salida»: payload frente a JSON compacto. «Total»: instrucción + salida frente a JSON compacto con instrucción 0 (lectura más dura para .mini).

| Dominio | Tokenizador | Salida (n*) | Total general con ejemplo | Total especializado con ejemplo | Total especializado sin ejemplo |
|---|---|--:|--:|--:|--:|
| tickets (representativo) | o200k_base | 1 | 31 | 14 | 10 |
|  | cl100k_base | 1 | 35 | 15 | 11 |
|  | r50k_base | 1 | 35 | 15 | 11 |
| eventos de planta (FAVORABLE) | o200k_base | 1 | 23 | 8 | 7 |
|  | cl100k_base | 1 | 24 | 8 | 7 |
|  | r50k_base | 1 | 23 | 8 | 7 |
| comentarios (texto libre; ahorro pequeño) | o200k_base | 1 | 42 | 25 | 14 |
|  | cl100k_base | 1 | 51 | 30 | 16 |
|  | r50k_base | 1 | 60 | 36 | 19 |

### Control: cuánto es del formato y cuánto de las abreviaturas (n = 100, o200k_base)

JSON con las mismas abreviaturas (códigos, enteros escalados y constantes una sola vez) usa menos tokens que JSON compacto sin ellas: parte del ahorro del perfil especializado NO es del formato.

| Dominio | JSON compacto | JSON con las mismas abreviaturas | .mini especializado | Ahorro frente a JSON compacto | Ahorro frente a JSON abreviado (efecto del formato) |
|---|--:|--:|--:|--:|--:|
| tickets (representativo) | 4068.8 | 3797.6 | 2433.0 | +40.2 % | +35.9 % |
| eventos de planta (FAVORABLE) | 6598.6 | 4025.0 | 1624.0 | +75.4 % | +59.7 % |
| comentarios (texto libre; ahorro pequeño) | 7187.0 | 7187.0 | 6085.3 | +15.3 % | +15.3 % |

### Simulación de una ampliación NO implementada: diccionario por documento (n = 100, o200k_base)

| Dominio | Salida general (tokens) | General con diccionario simulado | Ahorro potencial | Especializado a mano | Columnas del diccionario |
|---|--:|--:|--:|--:|---|
| tickets (representativo) | 2652 | 2608 | +1.7 % | 2382 | prioridad, categoria |
| eventos de planta (FAVORABLE) | 3950 | 3108 | +21.3 % | 1621 | planta, tipo_evento, severidad, estado |
| comentarios (texto libre; ahorro pequeño) | 5954 | — | — | 5955 | ninguna: ninguna columna cumple la regla (se repite poco o ahorra menos de lo que cuesta declararla) |

<!-- cifras:fin -->

## Qué se eligió y por qué

Búsqueda local sobre desarrollo: se acepta un cambio solo si reduce ≥ 1 % los tokens (instrucción compacta + salida, n = 50, suma de los tres
tokenizadores) **y** reconstruye todos los registros. Lo aceptado en cada dominio está en `diseno/<dominio>.json`:

* `tickets`: identificador numérico con prefijo `T-` constante (el mayor aporte) y códigos abreviados para prioridad y categoría.
* `eventos`: fecha como clave de cabecera, códigos para las cuatro enumeraciones, identificador de equipo numérico, hora en minutos y valor escalado ×10.
* `comentarios`: ningún tratamiento superó el umbral; el «especializado» solo gana por una instrucción más corta.

Toda abreviatura es **reversible con un mapa explícito**: vive en la aplicación (`mapa.json`), se imprime en la instrucción (se cuenta) y se verifica con
`reconstruir(parse(mini)) == original` para **todo** registro (valores, tipos, orden de claves y metadatos). Si falla, la configuración se descarta.
Un segundo decodificador independiente, [`examples/optimizacion/reconstruir.py`](../../examples/optimizacion/reconstruir.py), usa solo `minifmt` y el mapa.

## Qué NO funcionó o no aportó

* **El orden contractual no aportó**: en los tres dominios ningún movimiento de un campo alcanzó el 1 % (`diseno/*.json`, rondas de tipo `orden`).
* **Comentarios**: sin enumeraciones ni constantes no hay nada que abreviar; el ahorro de salida que hay es el de quitar los nombres de clave y las comillas.
* **`mini build` (perfil `mini-domain/1`) compensa tarde**: su instrucción es la más larga y con lotes pequeños la salida puede ser incluso mayor que JSON (ver las tablas).
  Donde hay mucho texto repetido (eventos) su diccionario automático da buena parte del ahorro sin diseñar nada, pero vive solo en Python.
* **`spec_block` del contrato especializado** es bastante más largo que la plantilla compacta (incluye reglas de listas, marcadores y nulos que este contrato no usa).
* **Diccionarios por documento** (simulación de una ampliación del formato, NO implementada): aplican solo donde el texto se repite mucho; en tickets y
  comentarios casi no aplican. Ver [ADR 0030](../../docs/adr/0030-propuesta-alias-de-enumeracion-y-diccionarios-por-documento.md) (propuesta, no vigente).
* **Esquemas de código**: no hay uno mejor para todas las enumeraciones. La abreviatura mnemotécnica (prefijo único más corto) ganó cuando las etiquetas tienen
  iniciales distintas; con etiquetas compuestas y prefijo común (las plantas de `eventos`) ganó la letra secuencial. La elección la hizo la búsqueda por tokens, no un criterio de
  comprensión del modelo, que no se midió.
* No probado: `list_separator`, `count_key`, familias heredadas, `default` de campos (rompe `dumps(parse(t)) = t`, según la auditoría del núcleo) y listas,
  porque ninguno de los tres dominios los necesita.

## Límites y advertencias

* **Sin modelo real.** No se midió si un modelo sigue la instrucción compacta, ni la tasa de validez con códigos cortos; nada de esto es evidencia V2/V3.
  La instrucción compacta es una plantilla propia del estudio y debe validarse antes de adoptarla.
* El total suma tokens de entrada y de salida **sin ponderar por tarifa**; el costo en dinero no se calcula aquí.
* JSON con instrucción 0 es la lectura primaria (la más dura para `.mini`); si el JSON también lleva su esquema, `.mini` empata o gana antes.
* Dos dominios son sintéticos y del mismo generador para desarrollo y prueba; `eventos` es favorable por diseño. El máximo observado no es una promesa universal.
* Los diez tickets de «Cómo funciona» vienen de `examples/mesa-de-ayuda/grabaciones/mini/ok.mini` (commit `c5e6605`, sesión asistida por IA): no hay registro de modelo,
  fecha de llamada ni `usage`, así que se etiquetan `asistido_ia` con procedencia no verificable y se usan solo como contenido de ejemplo.
* El serializador no admite cadenas con espacio en los extremos ni `""` en campos opcionales (defecto D-1 de la auditoría del núcleo); los datos medidos no las contienen y la
  comprobación de ida y vuelta las detectaría.

## Reproducir

```bash
python tools/ejecutar_opt.py                        # corrida completa: escribe evidencia/corridas/opt-<fecha>/ y examples/optimizacion/
python tools/ejecutar_opt.py --rapido --salida /tmp/opt   # prueba de humo (no es evidencia oficial)
cd experiments && python -m optimizacion.diseno     # rehace la búsqueda de diseño sobre desarrollo
python -m pytest -q -p no:cacheprovider tests/test_opt_*.py
python examples/optimizacion/reconstruir.py tickets # decodificador independiente
```

## Archivos

| Ruta | Qué es |
|---|---|
| `criterio.json` | criterio fijado antes de medir |
| `datos.py`, `dominios.py` | generadores, esquemas de aplicación y espacio de diseño |
| `especializacion.py` | tratamientos, mapa explícito, `codificar`/`reconstruir`, comprobación de equivalencia e instrucciones |
| `perfiles.py`, `medir.py`, `tokenizadores.py` | perfiles, medición, equilibrio, tokenizadores locales |
| `diseno.py`, `diseno/` | búsqueda de diseño y su registro completo |
| `ejemplo.py` | el ejemplo de «Cómo funciona» (`evidencia/corridas/opt-*/ejemplo_tickets.json`) |
| `propuesta.py` | simulación del diccionario por documento (ampliación NO implementada) |
| `documentos.py`, `carpeta_ejemplos.py` | generan este bloque de cifras, el ADR 0030 y `examples/optimizacion/` desde los resultados |
| `../../tools/ejecutar_opt.py` | orquesta la corrida y escribe el manifiesto (`tools/evidencia_lib.py`) |
| `../../examples/optimizacion/` | contratos, instrucciones reales, respuestas, mapas y `reconstruir.py` por dominio |
