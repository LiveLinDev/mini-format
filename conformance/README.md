# Suite de conformidad de .mini (especificación 1.0)

Casos independientes del lenguaje para comprobar que una implementación de
`.mini` (Python, TypeScript u otra) se comporta como exige `SPEC.md`. Todas las
implementaciones deben ejecutar **la misma lógica de runner** descrita abajo.

```bash
python conformance/run_python.py          # resumen por categoría (sale con 1 si algo falla)
python conformance/run_python.py -v       # muestra el motivo de cada fallo
python conformance/run_python.py -k quotes
python conformance/generate.py            # regenera cases/*.json
```

La suite también corre dentro de `pytest` (`tests/test_conformance.py`).

## Archivos

| Ruta | Contenido |
|---|---|
| `cases/<categoría>.json` | `{"suite", "spec", "category", "cases": [caso, ...]}` |
| `generate.py` | Fuente de los casos. Las expectativas salen de los fixtures publicados en `forks/*/fixtures` o están escritas a mano desde `SPEC.md`; **nunca** se calculan ejecutando la implementación. |
| `run_python.py` | Runner de referencia contra `minifmt`. |

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
| `dumps` | `dumps(input, contract)` | Si `expected.rejected`: el serializador lanza un error (el código no se compara). Si no: el texto es idéntico a `expected.mini` byte a byte y ese texto se acepta en modo estricto. |
| `contract` | cargar `input` como contrato | Los errores (E20, línea 0) coinciden; `[]` significa contrato válido. |
| `fork` | comprobar `contract`/`family` contra `parent` (nombre de familia o contrato embebido) | Los errores de invariantes (E21, línea 0) coinciden como conjunto; `[]` significa bifurcación válida. |

Un fallo inesperado de la implementación (excepción no prevista) cuenta como
caso fallido.

## Categorías

| Categoría | Cubre |
|---|---|
| `fixtures` | `valid.mini` ↔ `canonical.json` y cada `bad_*.mini` de las 14 familias |
| `lenient` | cada `bad_*.mini` en modo tolerante: registros válidos conservados |
| `escapes` | `\|` `\,` `\;` `\*` `\"` `\\` `\n`, escapes inválidos y colgantes (E09), CRLF, `escaping.mini` de cada familia |
| `quotes` | elementos entre comillas estilo CSV, `""`, marcador dentro o fuera, E09 |
| `lists` | aridad `min`/`max`/`count_key` (E07), tipos de elementos, separador propio |
| `mlist` | las cuatro reglas de marcador (E08) y la forma canónica de la selección |
| `tuples` | aridad (E07), componentes opcionales, marcador prohibido |
| `optionals` | campos vacíos, cola de extensiones, requeridos vacíos (E06) |
| `arity` | menos o más campos que el contrato (E05) |
| `types` | int, float, bool, enum (E06, E10, E13) |
| `unique` | E11 y su interacción con el modo tolerante |
| `header` | E01, E02, E03, E04, E12, BOM, líneas en blanco, claves tipadas y desconocidas |
| `truncation` | último registro incompleto, líneas faltantes, diagnóstico de regeneración |
| `roundtrip` | serialización canónica y su rechazo de objetos inválidos |
| `contract` | contratos inválidos (E20) |
| `fork` | invariantes I3/I4 del protocolo de bifurcación (E21) |

## Puntos no fijados por la suite

La suite evita, a propósito, comportamientos que `SPEC.md` 1.0 no define con
precisión; quedan pendientes de decisión:

* `\,` cuando el separador del contrato no es `,` (la gramática lo excluye;
  la implementación de referencia lo acepta).
* Booleanos distintos de `true`/`false`/`1`/`0` (la referencia acepta también
  `yes`/`no`/`y`/`n`/`t`/`f`), enteros con `+` y floats como `.5` o `1.`.
* Código de un valor de cabecera con tipo incorrecto (`n=abc` produce E06 y
  E03 en la referencia; la tabla de §8 sugiere E12).
* Claves de cabecera duplicadas (la referencia conserva la última).
* Elementos vacíos en listas (`a,,b` o separador final): la referencia los
  acepta como cadena vacía, lo que rompe la ida y vuelta de `[""]`.
* Lista opcional vacía: la referencia devuelve `[]` y no `null`.
* Código de error del serializador ante objetos inválidos.
