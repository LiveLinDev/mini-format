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

## Muestras nuevas

`sample_coverage` prueba dos divisiones intercaladas y reproducibles: primero se
aprende de cada quinto registro y se valida el resto (20% de entrenamiento);
luego se invierten los grupos (80%). Si aparece una variante no observada, debe
rechazarse indicando código y ruta; nunca se descarta ni se cambia el dato.
Se publican tanto los aciertos como los rechazos. Más muestras representativas
pueden cubrir variantes raras, pero no sustituyen las reglas de negocio.
