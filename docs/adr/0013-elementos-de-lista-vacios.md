# ADR 0013. Elementos de lista vacíos

* Estado: aceptada
* Fecha: 2026-09-17 (SPEC 1.1)
* Especificación: [SPEC.md](../../SPEC.md) §3.4 y §6

## Contexto y problema

La gramática 1.0 permitía elementos vacíos (`bare ::= value`, que puede ser vacío), de
modo que `a,,b` y un separador final (`a,`) eran sintácticamente válidos, y la
referencia los leía como cadenas vacías. Sin embargo, el serializador escribía `[""]`
como un campo vacío, que el parser lee como `[]`: la propiedad de ida y vuelta (§9)
fallaba para listas con un único elemento vacío.

## Alternativas consideradas

1. **Rechazar los elementos vacíos sin comillas** (E06) y exigir `""`.
2. **Aceptarlos como cadena vacía y escribir siempre `""`** en la salida canónica.
3. **Aceptarlos y escribir `""` solo cuando la lista es `[""]`.**

## Decisión

Se adopta la alternativa 2. Un elemento vacío, con o sin comillas, es la cadena vacía
para elementos `str` y un error del tipo de elemento en otro caso (E06; E10 para
`enum`). El serializador canónico escribe todo elemento vacío como `""`, único caso en
que emite comillas.

## Consecuencias

* Ningún documento aceptado por 1.0 se vuelve inválido; la alternativa 1 habría
  invalidado documentos válidos según la gramática 1.0.
* `[""]` hace ida y vuelta: `""` → `[""]` → `""`.
* Una forma uniforme para todo elemento vacío evita que la salida canónica dependa de la
  longitud de la lista (alternativa 3) y no confunde un separador final con un corte.
* Las tuplas no cambian: un componente vacío sigue siendo null si es opcional y E06 si
  es requerido (casos 1.0 `tuple-optional-component` y `tuple-required-component-empty`).

## Evidencia

* Lista de puntos pendientes de [conformance/README.md](../../conformance/README.md) en la
  revisión `d4a1d44` («la referencia los acepta como cadena vacía, lo que rompe la ida y
  vuelta de `[""]`»).
* Caso 1.0 `quote-empty` (`""*,b` → `["", "b"]`) en
  [conformance/cases/quotes.json](../../conformance/cases/quotes.json).
* Casos 1.1: `list-empty-element-middle`, `list-empty-element-trailing`,
  `list-single-empty-string`, `list-empty-element-int`, `list-empty-element-enum`
  ([lists.json](../../conformance/cases/lists.json)), `dumps-empty-string-elements`
  ([roundtrip.json](../../conformance/cases/roundtrip.json)) y `mlist-empty-marked-element`
  ([mlist.json](../../conformance/cases/mlist.json)).
