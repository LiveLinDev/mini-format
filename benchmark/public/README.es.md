# Benchmark con APIs públicas

La comparación conserva cada respuesta JSON completa, sus campos, tipos y
metadatos. Mide tokens de serialización; no mide calidad de generación de una IA
ni velocidad del parser. Evalúa el toolkit de dominios generado; el benchmark
académico de contratos manuales sigue en `benchmark/results/`.

| Conjunto | Objetos | Procedencia |
| --- | ---: | --- |
| DummyJSON productos | 194 | Datos sintéticos públicos para pruebas |
| DummyJSON usuarios | 208 | Datos sintéticos públicos para pruebas |
| JSONPlaceholder comentarios | 500 | Colección sintética pública completa |
| USGS terremotos | 1.000 | Observaciones reales, primeros eventos de enero de 2025 |

Son 1.902 IDs únicos dentro de sus respectivos conjuntos. No se duplicaron filas
para aumentar el tamaño ni se seleccionaron solamente campos favorables. Los
endpoints se eligieron antes de medir. Los JSON sintéticos no son tráfico real
de clientes. `sources.json` registra URL, selección, fecha, tamaño y SHA-256;
`THIRD_PARTY.md` contiene las atribuciones.

## Reproducir

Desde la raíz del repositorio, con Python 3.9+ y Node.js 22.14+:

```sh
python -m pip install -e ".[bench]"
python benchmark/public/run.py
```

La ejecución no necesita descargar datos: comprueba los hashes de las copias
incluidas y produce `results.json` y `results.csv`. Cada formato debe reconstruir
el JSON original o la prueba falla. No importa el orden de claves ni escribir
un mismo número como `1` o `1.0`; sí se distinguen booleanos, números, textos,
valores ausentes, `null`, cadenas vacías y listas vacías.

Para actualizar deliberadamente los datos: `python benchmark/public/fetch.py`
y después repetir el benchmark. Las fuentes pueden cambiar. La opción
`--baselines-only` ejecuta las comparaciones sin el toolkit .mini.

## Qué se cuenta

`.mini` aprende el contrato del conjunto completo. Es una medición del formato
ajustado a esas muestras, no una prueba de generalización a esquemas nuevos.
Los valores compartidos del documento se transmiten explícitamente.
Los diccionarios de textos repetidos también se incluyen en la cabecera medida.
`mini_without_document_factoring_tokens` muestra la salida con ambas
optimizaciones desactivadas.

TOON usa su encoder y decoder oficiales, versión vendorizada 4.1.1. TOON plano
prueba dos estrategias reversibles: objetos como columnas JSON Pointer con
listas en celdas JSON, y expansión de las listas por índice en más columnas.
Se elige el menor número de tokens de salida y se publican ambos resultados en
`flattening`. Un mapa compartido reconstruye tipos y estructura. CSV prueba las
mismas dos estrategias y también elige la menor; usa quoting RFC 4180, tipos
compartidos y una línea `#meta` con los metadatos originales. No se omite
información para reducir tokens.

También se comparan JSON compacto, JSON indentado, YAML de PyYAML y XML compacto
con tipos explícitos. Son implementaciones documentadas, no una afirmación de
haber optimizado todas las variantes posibles de TOON, CSV o XML.

Todos usan `o200k_base`. `tokens` mide la salida transmitida;
`shared_schema_tokens`, el contrato/mapa reutilizable;
`payload_plus_schema_tokens`, ambos juntos. `prompt_tokens` y
`payload_plus_prompt_tokens` muestran por separado el prompt inglés generado de
.mini. No se suma dos veces contrato y prompt. Que los otros formatos tengan
cero en `prompt_tokens` significa que no se midió un prompt específico para
ellos, no que una IA carezca de instrucciones. El ahorro monetario depende de
los precios de entrada/salida, el caché y la frecuencia de uso.

El ahorro ponderado es `1 - suma(tokens mini) / suma(tokens otro formato)`.
Se publican también los resultados individuales y cualquier ahorro negativo.
Un corpus finito no demuestra que .mini siempre gane; menos tokens tampoco
demuestran por sí solos que una IA genere correctamente.

## Generación y lectura en la nube

`native_schema_results.json` incluye cada tarea y los tokens reportados, hasta
dos intentos por formato. Codex usó GPT-6 Luna con razonamiento desactivado.
JSON nativo y `.mini` por columnas o filas usaron `--output-schema`. Las
variantes proyectadas restauraron los IDs a partir del contexto de la aplicación.

```sh
python benchmark/public/run_native_schema.py --out output/nativo --start 60 --cases 12 --arms mini_columnar mini json_schema json_schema_projected --compact-single --literal-codes
python benchmark/public/run_native_schema.py --out output/filas-nativas --start 84 --cases 12 --workers 4 --arms mini_native_rows mini_columnar json_schema_projected --compact-single --literal-codes
python benchmark/public/run_native_schema.py --out output/reuso-esquema --start 192 --cases 18 --workers 3 --arms mini_reused_rows mini_native_rows json_schema_projected --compact-single --literal-codes
npm install --prefix output/toon-44 @toon-format/toon@4.4.0
python benchmark/public/run_cloud_reading.py --out output/lectura --toon-module output/toon-44/node_modules/@toon-format/toon/dist/index.mjs --model-table --start 48 --cases 12
```

El costo por acierto divide el gasto de todos los intentos entre los aciertos
exactos. Se publica la estimación con la tarifa normal de entrada y con el
caché observado. Ambas cuentan todo el contexto reportado por Codex. Los
tokens del prompt inicial de lectura cuentan la tarea, la explicación y el
documento. Los tres formatos usan el mismo esquema de respuesta.

En `mini_reused_rows`, el esquema es idéntico para todos los recuentos del
ensayo. El SDK sigue validando la cantidad exacta antes de entregar el JSON.
La medición con caché refleja los aciertos que reportó Codex en cada formato.

### Consultas sobre varias tablas

`run_multitable_reading.py` usa las mismas tablas de tickets y agentes y el
mismo esquema de respuesta en cada formato. Primero comprueba que todos los
códecs recuperen los datos originales. En cada documento hace cuatro preguntas,
con el texto del documento al inicio de la entrada, y mide hasta dos intentos
por pregunta. El resultado distingue costos con y sin la caché observada.

```sh
python -m pip install "gcf-python @ git+https://github.com/blackwell-systems/gcf-python@3a55a7546b2184ea0d2468e667b31536457e2e63"
cargo build --manifest-path benchmark/public/hedl_reference/Cargo.toml --target-dir output/hedl-reference
git show 805e7cf5e931a42b7d9cdefb94bbb2cf7c429453:src/minifmt/transport.py > output/transport-anterior.py
python benchmark/public/run_multitable_reading.py --out output/lectura-tablas --previous-transport output/transport-anterior.py --hedl-parser output/hedl-reference/debug/mini-hedl-reference --toon-module output/toon-44/node_modules/@toon-format/toon/dist/index.mjs
```

En Windows, el ejecutable `mini-hedl-reference` termina en `.exe`. La prueba
usa los encoders y decoders oficiales de HEDL 2.0.0, GCF y TOON 4.4.0.
Para repetir la comparación adicional con GCF, elige una carpeta `--out`
distinta y añade `--arms mini_tables gcf --start 350 --sizes 25 40 58`.

Para probar textos repetidos, estos comandos comparan `.mini` con referencias,
la versión de tablas sin referencias y BPP 0.4.0 en sus dos modos. Se hacen tres
preguntas por documento y se indican los pasos de búsqueda por ID.

```sh
python -m pip install bpp-format==0.4.0
python benchmark/public/run_multitable_reading.py --out output/referencias --arms mini_text_refs mini_tables bpp_refs bpp_plain --start 416 --sizes 32 48 56 68 --questions 3 --lookup-steps
python benchmark/public/run_multitable_reading.py --out output/referencias-bpp --arms mini_text_refs bpp_plain --start 430 --sizes 34 47 58 76 --questions 3 --lookup-steps
```

El piloto usó `--start 400 --sizes 32 48 64 80` sin `--lookup-steps`. El JSON
público conserva el piloto y las dos corridas posteriores, incluidos los
fallos y el total de consultas emparejadas frente a BPP sin referencias.

La comparación con LDF 0.6.0 y TRON 0.1.3 usa el decodificador oficial de cada
formato para comprobar que se conservaron los datos. En la nube, LDF usa su
modo de tablas hijas y todos los formatos responden al mismo esquema JSON.

```sh
cargo build --locked --manifest-path benchmark/public/ldf_reference/Cargo.toml --target-dir output/ldf-reference
npm install --prefix output/tron --ignore-scripts @tron-format/tron@0.1.3
python benchmark/public/run_multitable_reading.py --out output/lectura-ldf-tron --arms mini_text_refs ldf tron json_compact --ldf-parser output/ldf-reference/debug/mini-ldf-reference --tron-module output/tron/node_modules/@tron-format/tron/dist/index.js --start 450 --sizes 22 39 56 73 --questions 3 --lookup-steps
python benchmark/public/run_multitable_reading.py --out output/lectura-ldf-confirmacion --arms mini_text_refs mini_tables ldf --ldf-parser output/ldf-reference/debug/mini-ldf-reference --cases 451 470 471 472 --sizes 39 35 53 71 --questions 3 --lookup-steps
python benchmark/public/run_multitable_reading.py --out output/lectura-ldf-tablas --arms mini_tables ldf --ldf-parser output/ldf-reference/debug/mini-ldf-reference --start 450 --sizes 22 39 56 73 --questions 3 --lookup-steps
```

En Windows, añade `.exe` al ejecutable `mini-ldf-reference`. Los conteos de
documento completo con `o200k_base` comparan también la variante `hoist` de LDF.
Se contabilizan los metadatos de origen y las declaraciones de cada formato.
[Especificación de LDF](https://ldflabs.org/docs/spec/), [SDK de TRON](https://github.com/tron-format/tron-javascript).

## Muestras nuevas

`sample_coverage` prueba dos divisiones intercaladas y reproducibles: primero se
aprende de cada quinto registro y se valida el resto (20% de entrenamiento);
luego se invierten los grupos (80%). Si aparece una variante no observada, debe
rechazarse indicando código y ruta; nunca se descarta ni se cambia el dato.
Se publican tanto los aciertos como los rechazos. Más muestras representativas
pueden cubrir variantes raras, pero no sustituyen las reglas de negocio.
