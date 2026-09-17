# ADR 0011. Código de error de un valor de cabecera mal tipado

* Estado: aceptada
* Fecha: 2026-09-17 (SPEC 1.1)
* Especificación: [SPEC.md](../../SPEC.md) §5 y §8 (E03, E06, E12)

## Contexto y problema

Para `n=abc`, la referencia 1.0 reportaba dos errores: E06 (el valor no es entero) y E03
(«la cabecera no trae `n`»), aunque `n` sí estaba presente. La tabla de §8 describía
E12 como «entrada de cabecera malformada», lo que sugería un tercer código posible. Un
mismo documento podía recibir códigos distintos según la implementación.

## Alternativas consideradas

1. **E12** para toda entrada de cabecera con valor inválido.
2. **E06 + E03** (comportamiento de la referencia 1.0).
3. **El código de la violación de tipo** (E06, E07, E10, E13), igual que en un registro,
   sin E03 cuando la clave está presente.

## Decisión

Se adopta la alternativa 3. Un valor de clave tipada que no coincide con su tipo se
reporta en la línea de cabecera con el código de esa violación; `n=abc` y `n=` son E06.
E03 significa que `n` no aparece. Si `n` es inválido no se comprueba el recuento (sin
E04). E12 queda para entradas sin `=`, claves requeridas ausentes y claves repetidas
(ADR 0012).

## Consecuencias

* La suite 1.0 ya fijaba E06 para un elemento inválido de una lista de cabecera
  (`hdr-list-bad-item`) y E07 para la aridad de una tupla de cabecera
  (`hdr-tuple-arity`); la alternativa 3 es la única coherente con esos casos, mientras
  que la alternativa 1 los habría contradicho.
* Cada código tiene un único significado en registros y cabecera: tipo (E06), aridad
  (E07), enumeración (E10), rango (E13).
* Se elimina el E03 espurio, que inducía a un reparador a añadir un `n` que ya existía.

## Evidencia

* Lista de puntos pendientes de [conformance/README.md](../../conformance/README.md) en la
  revisión `d4a1d44` («`n=abc` produce E06 y E03 en la referencia; la tabla de §8 sugiere
  E12»).
* Casos 1.0 coherentes con la decisión: `hdr-list-bad-item` (E06) y `hdr-tuple-arity`
  (E07) en [conformance/cases/header.json](../../conformance/cases/header.json).
* Casos 1.1: `hdr-n-not-int`, `hdr-n-empty`, `hdr-typed-scalar-bad`,
  `hdr-n-not-int-lenient` y `hdr-date-bad` en el mismo archivo.
