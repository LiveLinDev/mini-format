# ADR 0009. `\,` es un escape válido con cualquier separador

* Estado: aceptada
* Fecha: 2026-09-17 (SPEC 1.1)
* Especificación: [SPEC.md](../../SPEC.md) §3.3 y §4 (producción `escape`)

## Contexto y problema

SPEC 1.0 era ambigua: la tabla de §3.3 listaba «`\,` (o `\<sep>` para el separador del
contrato)», mientras que la gramática de §4 solo admitía `"\" SEP`. Con un separador
distinto de la coma (por ejemplo `;`), la gramática rechazaba `\,` y las
implementaciones de referencia lo aceptaban como coma literal. La suite 1.0 evitó el
caso ([conformance/README.md](../../conformance/README.md) en la revisión `d4a1d44`, «Puntos no
fijados por la suite»).

## Alternativas consideradas

1. **Solo `\<sep>`**: `\,` sería E09 cuando el separador no es la coma (lectura estricta de
   la gramática 1.0).
2. **`\,` siempre válido como coma literal**, además de `\<sep>` para el separador propio.
3. **Cualquier signo de puntuación escapable.**

## Decisión

Se adopta la alternativa 2. `\,` denota una coma literal en todo contrato; `\<sep>` es
válido solo para el separador del contrato, de modo que `\;` con separador `,` es E09.

## Consecuencias

* Ningún documento aceptado por las implementaciones 1.0 pasa a ser inválido.
* El sobre-escape de comas, habitual en modelos entrenados con el separador por defecto,
  nunca invalida un documento; la regla ya declarada en §3.3 («over-escaping is
  idempotent-safe») se extiende a contratos con otro separador.
* La tokenización puede resolver escapes sin conocer el separador cuando este es `,`, lo
  que usa `detect_prefix` antes de elegir el contrato.
* La alternativa 3 se descarta porque ampliaría las secuencias válidas y ocultaría errores
  de escape reales (E09).

## Evidencia

* Implementación 1.0 que ya aceptaba `\,` con cualquier separador: `tokenize` en
  [src/minifmt/codec.py](../../src/minifmt/codec.py) y [ts/src/codec.ts](../../ts/src/codec.ts)
  (condición `nxt in (FIELD_SEP, MARKER, ESCAPE, sep, ",", '"')`).
* Casos de conformidad: `esc-comma-custom-separator` y `esc-other-separator-invalid` en
  [conformance/cases/escapes.json](../../conformance/cases/escapes.json).
