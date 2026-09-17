# ADR 0015. Códigos de error del serializador

* Estado: aceptada
* Fecha: 2026-09-17 (SPEC 1.1)
* Especificación: [SPEC.md](../../SPEC.md) §2 y §9

## Contexto y problema

SPEC 1.0 exigía la ida y vuelta para objetos válidos, pero no decía qué hace el
serializador con un objeto inválido. Las implementaciones lanzaban errores con códigos
arbitrarios (E06 para un valor fuera de la enumeración, E07 para un componente de tupla
ausente) y línea 0, y no validaban rangos, aridades, claves de conteo ni unicidad: podían
emitir documentos que el propio parser rechazaba. La suite 1.0 solo comprobaba que hubiera
un error («el código no se compara»).

## Alternativas consideradas

1. **Código libre por implementación** (situación 1.0).
2. **Un código específico del serializador** (nuevo, p. ej. E30).
3. **El código que el parser reporta para la misma violación**, con la línea física que
   la entrada ocuparía en la salida, y verificación del texto emitido con un análisis
   estricto.

## Decisión

Se adopta la alternativa 3. El serializador no emite documentos que el parser rechazaría.
Ante un objeto inválido falla con el código de §8 de esa violación y la línea
correspondiente (1 = cabecera; *i* + 2 = registro *i*). Las implementaciones de
referencia codifican el objeto, asignan la línea a los errores de codificación y
verifican el texto con `parse` estricto, devolviendo el primer error.

## Consecuencias

* Un mismo significado por código en ambos sentidos: quien valida con el parser y quien
  serializa ven el mismo diagnóstico.
* No se amplía la tabla de códigos, que es parte del contrato público.
* La serialización tiene el coste adicional de un análisis; a cambio, garantiza que toda
  salida es válida.
* Las pruebas que esperaban E06 para una enumeración o E07 para un componente ausente se
  actualizaron a E10 y E06 ([ts/test/roundtrip.test.ts](../../ts/test/roundtrip.test.ts)).

## Evidencia

* Lista de puntos pendientes de [conformance/README.md](../../conformance/README.md) en la
  revisión `d4a1d44` («Código de error del serializador ante objetos inválidos»).
* Serializador previo: `raise MiniError(E_TYPE, 0, f"'{v}' not in enum", …)` en
  [src/minifmt/serializer.py](../../src/minifmt/serializer.py) (revisión `d4a1d44`).
* Casos 1.1: `dumps-error-*` en [conformance/cases/roundtrip.json](../../conformance/cases/roundtrip.json)
  y los cinco casos 1.0 `dumps-reject-*`, que ahora también fijan el código.
