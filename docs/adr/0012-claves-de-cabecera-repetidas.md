# ADR 0012. Claves de cabecera repetidas

* Estado: aceptada
* Fecha: 2026-09-17 (SPEC 1.1)
* Especificación: [SPEC.md](../../SPEC.md) §5 y §8 (E12)

## Contexto y problema

SPEC 1.0 no decía qué ocurre si una clave aparece dos veces en la cabecera
(`a|n=3|…|n=4`). La referencia conservaba la última aparición sin informar. El objeto
canónico dependía de la implementación y, en el caso de `n`, también el resultado de la
validación del recuento (E04).

## Alternativas consideradas

1. **Conservar la última aparición** (comportamiento de la referencia 1.0).
2. **Conservar la primera aparición** sin informar.
3. **Error E12 por cada aparición repetida**, conservando la primera para la lectura
   tolerante.
4. **Acumular los valores en una lista.**

## Decisión

Se adopta la alternativa 3. Una clave no debe aparecer más de una vez; cada repetición es
E12 en la línea de cabecera. Cuenta la primera aparición, que es la que usa un parser
tolerante.

## Consecuencias

* Un documento con claves repetidas no tenía objeto canónico determinado en 1.0, por lo
  que la regla no altera el resultado de ningún documento que 1.0 definiera.
* Una cabecera ambigua suele indicar una generación defectuosa (por ejemplo, dos valores
  de `n`); el error la hace visible en lugar de elegir un valor en silencio.
* Se conserva la primera aparición porque es la que un lector en streaming conoce antes
  de procesar el resto de la línea.
* La alternativa 4 se descarta porque cambiaría el tipo de la clave según el documento.
* El perfil de dominio generado ya trataba las claves de cabecera repetidas como error
  ([DOMAIN_PROFILE.md](../../DOMAIN_PROFILE.md): «Unknown or duplicate header names are
  errors»).

## Evidencia

* Lista de puntos pendientes de [conformance/README.md](../../conformance/README.md) en la
  revisión `d4a1d44` («la referencia conserva la última»).
* Casos 1.1: `hdr-duplicate-key`, `hdr-duplicate-n` y `hdr-duplicate-key-lenient` en
  [conformance/cases/header.json](../../conformance/cases/header.json).
