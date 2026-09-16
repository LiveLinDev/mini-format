# .mini — notación bifurcable y eficiente en tokens para salidas estructuradas de LLM

[![spec](https://img.shields.io/badge/spec-1.0-2a78d6)](SPEC.md) [![forks](https://img.shields.io/badge/forks-14-1baf7a)](forks/) [![license](https://img.shields.io/badge/license-MIT-lightgrey)](LICENSE)

`.mini` es una notación posicional orientada a líneas para las **salidas estructuradas
de modelos generativos de lenguaje en dominios cerrados**: una línea de cabecera que
nombra un *contrato* y declara el número de registros, y después exactamente un
registro por línea con los campos separados por `|`.

```
a|n=2|m=IRT3PL|d=20260603|l=es|t=demo|k=4
i1|L1|Biología|¿Dónde ocurre la fotosíntesis?|cloroplastos*,núcleo,mitocondria,ribosoma|0.9,-1,0.25|1|biología,0.2,low
i2|L3|Matemática|Si 3x+6=18, ¿cuál es x?|4*,6,8,12|1.4,0.2,0.2|3|matemática,0.25,medium
```

Como emisor y receptor comparten el contrato, nada estructural se repite:
ni claves, ni llaves, ni corchetes, ni comillas ni indentación. Con los mismos datos
de 14 dominios cuesta **un 34 % menos de tokens de salida que JSON compacto**
(27–40 %), un 37 % menos que TOON aplicado al objeto anidado y un 7 % menos que el
mejor caso tabular de TOON — a pocos puntos de CSV puro, pero conservando listas
tipadas, tuplas, un marcador de selección, un recuento de registros y un parser
que valida
([benchmark](benchmark/results/summary_12.csv)).

`.mini` no es un formato sino una **familia**: cada dominio nuevo obtiene su propio
contrato (`forks/<prefix>/contract.json`) y la implementación de referencia lo
interpreta — parser, serializador, validador, bloque de prompt y comprobador de
familias se derivan todos del contrato. Este repositorio incluye catorce familias
(ítems de evaluación, quizzes, tarjetas, segmentos de lección, mapas conceptuales,
rúbricas, encuestas, ejercicios de programación, casos de prueba, historias de
usuario, registros de eventos, anotaciones NER, filas de catálogo, salidas de
clasificación).

## Pruébalo

* **Playground** (sin instalar): abre [`playground/index.html`](playground/index.html) — valida documentos, convierte JSON ↔ .mini, compara tokens contra JSON/YAML/XML/CSV y el codificador *oficial* de TOON, y diseña una familia con el asistente.
* **Python**

```bash
git clone https://github.com/<you>/mini-format && cd mini-format
pip install -e .                 # o bien: PYTHONPATH=src
mini forks                       # lista los contratos
mini validate forks/a/fixtures/valid.mini
mini to-json forks/tc/fixtures/valid.mini | head
mini prompt log --lang es        # bloque de especificación para un modelo generativo
mini check-forks                 # chequeo de CI: invariantes + ida y vuelta de fixtures
```

```python
from minifmt import Registry, parse, dumps
reg = Registry.load()
doc = parse(text, reg.get("a"))          # -> Document; doc.to_canonical() es JSON plano
text = dumps(obj, reg.get("a"))          # JSON canónico -> .mini
```

* **JavaScript**: `js/mini.js` es un port sin dependencias (navegador + node) que pasa los mismos fixtures que la implementación Python (`node tests/test_js_port.mjs`).

## Crea una familia

```bash
mini new-fork quiz2 --from a --add "feedback:str" "level:enum{easy|hard}"
# edita forks/quiz2/contract.json, añade fixtures/valid.mini + fixtures/canonical.json
mini check-forks
```

Cinco invariantes mantienen toda familia analizable por construcción — una línea =
un registro; cabecera con prefijo y `n`; los campos heredados nunca cambian; campos
nuevos solo al final; los fixtures hacen ida y vuelta. Ver [FORKING.md](FORKING.md) y
[CONTRIBUTING.md](CONTRIBUTING.md). Una familia es **datos, no código**: para
contribuir una, abre un pull request con una carpeta bajo `forks/`.

## Estructura del repositorio

| Ruta | Contenido |
|---|---|
| `SPEC.md` | Especificación 1.0 (gramática, escapes, tipos, códigos de error, protocolo de bifurcación) |
| `src/minifmt/` | Implementación de referencia (Python ≥ 3.9, sin dependencias) + CLI `mini` |
| `js/mini.js` | Port a JavaScript |
| `forks/` | 14 contratos con fixtures y READMEs; `registry.json` |
| `benchmark/` | Benchmark de tokens (8 formatos × 14 dominios × 6 tamaños × 2 tokenizadores), puente al codificador oficial de TOON, figuras |
| `generative/` | Protocolo de validación generativa, salidas crudas de modelos, resultados |
| `playground/` | Playground interactivo de un solo archivo (listo para GitHub Pages) |
| `tests/` | Pruebas de conformidad en Python y JS |

## Reproduce los experimentos

```bash
python benchmark/make_forks.py        # regenera contratos + fixtures (idempotente)
python benchmark/run_benchmark.py     # tokens.csv, summary_12.csv, roundtrip.csv (≈30 s)
python generative/run_eval.py         # reevalúa las salidas de modelos archivadas
python generative/extra_experiments.py# ablación, punto de equilibrio, recuperación ante truncamiento
python benchmark/make_figures.py      # figuras para el artículo
python -m unittest discover -s tests  # 25 pruebas incl. 4 000 idas y vueltas con fuzzing
node tests/test_js_port.mjs           # conformidad entre implementaciones
```

El recuento de tokens usa `tiktoken` cuando está instalado y si no un BPE exacto
en Python puro sobre los archivos de rangos oficiales `o200k_base` / `cl100k_base`
vendidos (`benchmark/vocab/`, sha256 verificado); ambos reproducen los recuentos
publicados al token. TOON se codifica con la implementación oficial de referencia
(v4.1.1, spec 4.1) vendida bajo `benchmark/toon_ref/vendor` y ejecutada con Node ≥ 22
type stripping — sin npm install.

## Cita

> A. E. J. Palma Obispo and E. J. Palomino Santa Cruz, ".mini: a forkable, token-efficient notation for structured outputs of generative models," Universidad Peruana de Ciencias Aplicadas, 2026.

Asesores: Fidel Eugenio García Rojas (especializado), Ronald Mejía Tarazona (metodológico).

## Licencia

MIT. El material vendido de terceros conserva su propia licencia: implementación de referencia de TOON (MIT, Johann Schopplich), archivos de rangos de tokenizadores (MIT, OpenAI / gpt-tokenizer).
