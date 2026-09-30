# Suite de conformidad de .mini (especificación 1.1)

Casos independientes del lenguaje para comprobar que una implementación de
`.mini` (Python, TypeScript u otra) se comporta como exige `SPEC.md`. Todas las
implementaciones deben ejecutar **la misma lógica de runner** descrita abajo.

```bash
python conformance/run_python.py          # resumen por categoría (sale con 1 si algo falla)
python conformance/run_python.py -v       # muestra el motivo de cada fallo
python conformance/run_python.py -k quotes
python conformance/generate.py            # regenera cases/*.json
node conformance/run_js.mjs               # misma suite contra js/mini.js (motor del playground)
```

La suite también corre dentro de `pytest` (`tests/test_conformance.py`), de
`cd ts && npm test` (`ts/test/conformance.test.ts`) y de `node tests/test_js_port.mjs`
(motor del playground).

## Archivos

| Ruta | Contenido |
|---|---|
| `cases/<categoría>.json` | `{"suite", "spec", "category", "cases": [caso, ...]}` |
| `generate.py` | Fuente de los casos. Las expectativas salen de los fixtures publicados en `forks/*/fixtures` o están escritas a mano desde `SPEC.md`; **nunca** se calculan ejecutando la implementación. |
| `run_python.py` | Runner de referencia contra `minifmt`. |
| `run_js.mjs` | Runner contra `js/mini.js`, el motor del playground generado desde `ts/src`. |
| `oraculo/` | Decodificador de referencia independiente, escrito desde la gramática de la SPEC sin importar `minifmt` (`decodificador.py`), y su runner sobre este corpus (`ejecutar.py`). |

Los casos que usan `family` leen `forks/<family>/contract.json` desde la raíz
del repositorio.

## Formato de un caso

```json
{
  "id": "quote-doubled",
  "category": "quotes",
  "description": "\"\" dentro de comillas es una comilla",
  "mode": "strict",
  "family": "a",
  "contract": { "...": "contrato embebido, alternativa a family" },
  "parent": "a",
  "input": "mk|n=1\n\"dijo \"\"sí\"\"\"*,no|a*|a|1",
  "expected": {
    "canonical": { "prefix": "mk", "header": {"n": 1, "v": 1}, "rows": [ ... ] },
    "errors": [ {"code": "E08", "line": 2} ],
    "mini": "texto .mini esperado al serializar",
    "rejected": true,
    "diagnostics": { "invalid_lines": [3], "missing_records": 0 }
  }
}
```

* Cada caso tiene **exactamente uno** de `family` (nombre de familia oficial)
  o `contract` (contrato embebido con el mismo esquema que `contract.json`),
  salvo el modo `contract`, que no usa ninguno.
* `input` es texto `.mini` (modos `strict` y `lenient`), un objeto canónico
  (modo `dumps`), un contrato (modo `contract`) o `null` (modo `fork`).
* En `expected` solo aparecen las claves que aplican al modo.

## Semántica de los modos (lógica del runner)

Comparaciones comunes:

* **Errores**: se comparan como **conjunto de pares distintos `(code, line)`**;
  el orden y las repeticiones no importan. `line` es la línea física
  (1-based, contando las líneas en blanco omitidas); los errores de documento
  (E01, E04) y los de contrato/fork (E20, E21) usan línea `0`.
* **Canónico**: igualdad estructural; las claves de los objetos se comparan
  como conjunto y los números numéricamente (`-1` ≡ `-1.0`, tolerancia 1e-12).
  Los campos ausentes de un registro valen `null`; una lista marcada aparece
  como dos claves hermanas (elementos y selección).

| Modo | Acción | Pasa si |
|---|---|---|
| `strict` | `parse(input, contract, strict)` | Si `expected.errors` existe: el documento se rechaza y los pares coinciden. Si no: se acepta, el canónico coincide con `expected.canonical` y, cuando hay `expected.mini`, `dumps(canónico) == mini` y `parse(mini)` vuelve a dar el mismo canónico (ida y vuelta). |
| `lenient` | `parse(input, contract, lenient)` | Si hay `expected.canonical`: se devuelve un documento con esos registros válidos (y la cabecera leída), y sus errores coinciden con `expected.errors` (lista vacía = sin errores). Si no hay `canonical`: el documento no se puede construir (p. ej. E01) y los errores coinciden. Si hay `expected.diagnostics`: las líneas rechazadas (ascendentes, sin la cabecera) y los registros faltantes (`n` − líneas de registro, mínimo 0) coinciden. |
| `dumps` | `dumps(input, contract)` | Si `expected.rejected`: el serializador lanza un error y, si hay `expected.errors`, su par `(code, line)` es uno de los esperados (SPEC §9: código del parser y línea que ocuparía la entrada). Si no: el texto es idéntico a `expected.mini` byte a byte y ese texto se acepta en modo estricto. |
| `contract` | cargar `input` como contrato | Los errores (E20, línea 0) coinciden; `[]` significa contrato válido. |
| `fork` | comprobar `contract`/`family` contra `parent` (nombre de familia o contrato embebido) | Los errores de invariantes (E21, línea 0) coinciden como conjunto; `[]` significa bifurcación válida. |

Un fallo inesperado de la implementación (excepción no prevista) cuenta como
caso fallido.

## Categorías

| Categoría | Cubre |
|---|---|
| `fixtures` | `valid.mini` ↔ `canonical.json` y cada `bad_*.mini` de las 14 familias |
| `lenient` | cada `bad_*.mini` en modo tolerante: registros válidos conservados |
| `escapes` | `\|` `\,` (con cualquier separador) `\;` `\*` `\"` `\\` `\n`, escapes inválidos y colgantes (E09), CRLF, `escaping.mini` de cada familia |
| `quotes` | elementos entre comillas estilo CSV, `""`, marcador dentro o fuera, E09 |
| `lists` | aridad `min`/`max`/`count_key` (E07), tipos de elementos, separador propio, elementos vacíos |
| `mlist` | las cuatro reglas de marcador (E08) y la forma canónica de la selección |
| `tuples` | aridad (E07), componentes opcionales, marcador prohibido |
| `optionals` | campos vacíos, cola de extensiones, requeridos vacíos (E06), listas opcionales vacías (null) |
| `arity` | menos campos que el núcleo, o campos excedentes sin `v` posterior (E05) |
| `types` | int, float, bool, enum, date, decimal y sus formas léxicas (E06, E10, E13) |
| `unique` | E11 y su interacción con el modo tolerante |
| `header` | E01, E02, E03, E04, E12, BOM, líneas en blanco, claves tipadas, mal tipadas, repetidas y desconocidas |
| `truncation` | último registro incompleto, líneas faltantes, diagnóstico de regeneración |
| `roundtrip` | serialización canónica y su rechazo de objetos inválidos con el código del parser |
| `contract` | contratos inválidos (E20) |
| `fork` | invariantes I3/I4 del protocolo de bifurcación (E21) |

## Reglas añadidas en la especificación 1.1

La versión 1.0 de esta suite evitaba siete comportamientos que `SPEC.md` 1.0 no
definía con precisión. SPEC 1.1 fija una regla para cada uno (§13 de la
especificación) y la suite la comprueba; `SPEC_1_1_RULES` en `generate.py` enumera
los casos de cada regla y `tests/test_conformance.py` verifica que existen.

| Punto | Regla 1.1 | ADR | Casos (ejemplos) |
|---|---|---|---|
| `\,` con separador distinto de `,` | coma literal; `\<sep>` solo para el separador propio | [0009](../docs/adr/0009-escape-de-coma-con-cualquier-separador.md) | `esc-comma-custom-separator`, `esc-other-separator-invalid` |
| Booleanos `yes`/`t`…, enteros con `+`, floats `.5` o `1.` | E06; solo `true`/`false`/`1`/`0` y dígitos ASCII | [0010](../docs/adr/0010-formas-lexicas-estrictas-de-escalares.md) | `sc-bool-yes`, `sc-int-plus`, `sc-float-leading-dot` |
| Valor de cabecera mal tipado (`n=abc`) | código de la violación de tipo (E06), sin E03 | [0011](../docs/adr/0011-codigo-de-valor-de-cabecera-mal-tipado.md) | `hdr-n-not-int`, `hdr-n-not-int-lenient` |
| Claves de cabecera repetidas | E12; cuenta la primera | [0012](../docs/adr/0012-claves-de-cabecera-repetidas.md) | `hdr-duplicate-key`, `hdr-duplicate-n` |
| Elementos de lista vacíos e ida y vuelta de `[""]` | cadena vacía; el serializador escribe `""` | [0013](../docs/adr/0013-elementos-de-lista-vacios.md) | `list-empty-element-middle`, `list-single-empty-string` |
| Lista opcional vacía | null | [0014](../docs/adr/0014-lista-opcional-vacia-es-null.md) | `opt-list-empty-null`, `opt-mlist-empty-null` |
| Código de error del serializador | código del parser y línea que ocuparía la entrada | [0015](../docs/adr/0015-errores-del-serializador.md) | `dumps-error-range`, `dumps-error-second-record` |

Además, la suite 1.1 cubre los tipos `date` y `decimal`
([ADR 0016](../docs/adr/0016-tipos-date-y-decimal.md); casos `date-*`, `decimal-*`,
`dumps-date-decimal`, `contract-date-*`).

Los 303 casos de la suite 1.0 se conservan con las mismas expectativas; cinco casos
`dumps-reject-*` ahora también fijan el código de error y `contract-unknown-type`
usa `datetime` como tipo desconocido.

## Casos añadidos después de 1.1 (376 en total)

| Caso | Regla (SPEC) |
|---|---|
| `hdr-escaped-eq-key`, `hdr-escaped-eq-key-lenient` | `key\=value` en la cabecera: `\=` es un escape inválido (E09, §3.3) y su `=` está escapado, así que la entrada no tiene separador (E12, §3.2 y §5) |
| `hdr-escaped-eq-n` | `n\=1` no declara `n`: E09, E12 y E03 |
| `hdr-escaped-eq-in-value` | `\=` dentro de un valor: solo E09 |

Las expectativas se escribieron desde la norma, no ejecutando ninguna implementación. Los tres ejecutores
(`run_python.py`, `run_js.mjs` y `ts/test/conformance.test.ts`) las cumplen; antes de corregir el parser Python, tres de ellas fallaban.

## Origen de las expectativas y oráculo independiente

De los 376 casos, 128 (`fx-*`: fixtures, `dumps`, `escaping` y `lenient` de las 14 familias) salen de `forks/*/fixtures`, que
`benchmark/make_forks.py` genera con `dumps`/`parse` de la implementación Python: respecto de Python son circulares. El resto está
escrito a mano desde `SPEC.md`. Para no depender solo de eso, `oraculo/decodificador.py` reimplementa la lectura desde la gramática
de la especificación con otra estructura y sin importar `minifmt`; `python conformance/oraculo/ejecutar.py` comprueba que cumple los
307 de ellos, los de modo `strict` y `lenient` (los modos `dumps`, `contract` y `fork` no los decodifica). `tests/test_nucleo_propiedades.py`,
`tests/test_nucleo_oraculo.py` y `tools/fuzz_diferencial.py` lo usan para comparar Python y `js/mini.js` sobre documentos generados.
Las zonas en las que la SPEC calla y el oráculo adopta una lectura están declaradas al principio de su código y en el ADR 0017.
