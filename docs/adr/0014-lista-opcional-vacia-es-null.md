# ADR 0014. La lista opcional vacía es null

* Estado: aceptada
* Fecha: 2026-09-17 (SPEC 1.1)
* Especificación: [SPEC.md](../../SPEC.md) §6

## Contexto y problema

SPEC 1.0 establecía que «un campo vacío denota null y solo es válido para campos
opcionales». La referencia, en cambio, devolvía `[]` para una lista opcional vacía y
aplicaba `min` y la regla del marcador (E07, E08) aunque el campo fuera opcional. Esto
producía dos problemas: una extensión de tipo lista omitida valía null, pero la misma
extensión escrita vacía valía `[]`; y la ida y vuelta fallaba, porque `[]` se serializa
como campo vacío y una extensión vacía final se omite.

## Alternativas consideradas

1. **`[]` para toda lista vacía** (comportamiento de la referencia 1.0).
2. **null para toda lista opcional vacía** y `[]` para una lista requerida vacía.
3. **null para toda lista vacía**, requerida u opcional.

## Decisión

Se adopta la alternativa 2. Un campo vacío es null en todo campo opcional, cualquiera
sea su tipo (en una lista marcada, ambas claves hermanas son null). Una lista o lista
marcada requerida vacía es `[]`, sujeta a `min` y a la regla del marcador. El valor
canónico de una lista opcional vacía es null; el serializador puede aceptar `[]` y
escribirlo como campo vacío.

## Consecuencias

* Se cumple el texto de SPEC 1.0 («an empty field denotes null»), que la referencia no
  respetaba para listas.
* Se conserva el caso 1.0 `list-empty` (lista requerida sin mínimo vacía = `[]`); la
  alternativa 3 lo habría contradicho.
* Una extensión omitida y una extensión vacía producen el mismo objeto canónico.
* Una lista marcada opcional `exactly_one` vacía deja de producir E08.

## Evidencia

* SPEC 1.0, §6 (revisión `d4a1d44` de [SPEC.md](../../SPEC.md)); lista de puntos
  pendientes de [conformance/README.md](../../conformance/README.md) en esa revisión («la
  referencia devuelve `[]` y no `null`»).
* Prueba unitaria actualizada: `test_parser_misc_branches` en
  [tests/test_cli_tools.py](../../tests/test_cli_tools.py).
* Casos: `list-empty` (1.0) en [lists.json](../../conformance/cases/lists.json);
  `opt-list-empty-null`, `opt-mlist-empty-null` y `opt-list-min-applies-when-present`
  en [optionals.json](../../conformance/cases/optionals.json);
  `dumps-optional-list-empty-array` en [roundtrip.json](../../conformance/cases/roundtrip.json).
