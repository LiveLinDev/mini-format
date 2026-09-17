# Contribuir

Gracias por ayudar a crecer `.mini`. Hay tres tipos de contribución.

## Una familia nueva (la más bienvenida)

1. Lee [FORKING.md](FORKING.md).
2. `mini new-fork <prefix> [--from <parent>] --add ...` y edita el contrato.
3. Añade `fixtures/valid.mini`, `fixtures/canonical.json`, `fixtures/escaping.mini`, `fixtures/escaping.json` y los casos negativos.
4. Escribe `README.md` (propósito, tabla de estructura, ejemplo) — `benchmark/make_forks.py::write_readme` muestra la forma esperada.
5. Ejecuta `mini check-forks`, `python -m unittest discover -s tests`, `node tests/test_js_port.mjs`.
6. Abre un PR titulado `fork: <prefix> — <name>`. Añade tu familia al benchmark dándole 12 registros base en `benchmark/domains.py` (opcional pero apreciado).

Nombres de prefijo: cortos, en minúsculas, únicos. No reutilices un prefijo con una
estructura incompatible — eso es un prefijo nuevo.

## Cambios en la implementación

Ambas implementaciones (Python `src/minifmt`, TypeScript `ts/src`) deben mantenerse
de acuerdo: cualquier cambio en las reglas necesita el cambio espejo en la otra
implementación, una actualización de la spec en `SPEC.md` y `SPEC.es.md`, un caso de
conformidad en `conformance/generate.py` y, si el cambio es una decisión, un ADR en
`docs/adr/`. `js/mini.js` (el motor del playground) se genera desde `ts/src` con
`node --no-warnings tools/build_js.mjs`; no se edita a mano. Los códigos de error son
parte del contrato público; no los renumeres.

## Benchmark y validación

Reporta tokenizador, corpus, serializadores y línea base de cada cifra nueva.
Conserva las salidas crudas de modelos bajo `generative/raw/` para que cada figura
siga siendo trazable. TOON debe producirse con el codificador oficial vendido.

## Código de conducta

Sé amable, preciso y reproducible.
