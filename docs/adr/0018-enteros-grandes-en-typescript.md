# ADR 0018. Enteros fuera de ±2^53 en TypeScript y en el navegador

* Estado: **Propuesta (no vigente)**. No cambia SPEC 1.1 ni el comportamiento de ninguna implementación.
* Fecha: 2026-09-30 (auditoría V5)
* Especificación: [SPEC.md](../../SPEC.md) §4, §6

## Contexto y problema

SPEC §4 define `int` como `-?[0-9]+` y §6 como «integer» en el JSON canónico, sin fijar una
precisión máxima. La referencia Python usa enteros de precisión arbitraria y es exacta.
TypeScript y `js/mini.js` (el mismo código) usan números de JavaScript y, **sin error ni aviso**:

| Entrada | Python | TypeScript / navegador |
|---|---|---|
| `9007199254740993` (2^53 + 1) | `9007199254740993` | `9007199254740992` |
| `123456789012345678901234567890` | exacto | `1.2345678901234568e+29` |
| `dumps` de `2**60` | `1152921504606846976` | `1152921504606847000` |

Un identificador de 64 bits en un campo `int` se corrompe sin que nadie lo note. El límite está
documentado en `ts/README.md`, pero no hay caso de conformidad ni aviso en ejecución.
El tipo `decimal` (cadena exacta) es hoy la vía para valores grandes.

## Alternativas consideradas

1. **Estado actual documentado.** Sin cambios; el riesgo queda a cargo de quien lee el README.
2. **Acotar `int` en la norma a ±(2^53 − 1)** (como I-JSON, RFC 7493) y exigir E13/E06 fuera de
   ese rango en todas las implementaciones. Interoperable, pero quita a Python una capacidad que
   hoy tiene y cambia la norma: documentos 1.1 válidos dejarían de serlo.
3. **Norma abierta con obligación de señalar**: `int` no tiene límite, pero una implementación
   que no pueda representar un valor exactamente DEBE informar (E13) en lugar de alterarlo. No
   cambia a Python; TypeScript pasaría a rechazar lo que hoy corrompe.
4. **TypeScript entrega `bigint` fuera del rango seguro.** Conserva el valor, pero cambia el tipo
   público (`number | bigint`) y `JSON.stringify` falla con `bigint`.
5. **Opción `intMode: 'number' | 'bigint' | 'error'`** en `parse` y `dumps` (por defecto
   `'number'`, sin cambio de comportamiento) combinada con la alternativa 3 como valor por
   defecto en una versión mayor.

## Decisión propuesta

Alternativa 3 en la norma (nunca alterar en silencio), realizada en TypeScript con la opción de
la alternativa 5 (`'error'` como valor por defecto en 1.2; `'bigint'` para quien lo necesite).
Esta decisión es de la especificación y de la API pública, por lo que no se ha implementado.

## Compatibilidad

* Python no cambia. Un documento con un entero mayor que 2^53 sigue siendo válido en Python.
* TypeScript pasaría a rechazar (E13) lo que hoy devuelve un valor aproximado; es un cambio de
  comportamiento visible solo para quien ya recibe datos corruptos.
* `js/mini.js` se regenera desde `ts/src`.

## Prueba de aceptación

1. Caso de conformidad `sc-int-beyond-2-53` con la expectativa escrita desde la regla elegida.
2. `ts/test/bigint.test.ts` (que hoy fija el comportamiento actual) se sustituye por pruebas del
   comportamiento nuevo; hasta entonces cualquier cambio del redondeo la hace fallar.
3. [tests/test_nucleo_divergencias.py](../../tests/test_nucleo_divergencias.py) sigue fijando que
   Python es exacto.

## Evidencia

* [ts/test/bigint.test.ts](../../ts/test/bigint.test.ts): el comportamiento actual de TypeScript.
* [tests/test_nucleo_divergencias.py](../../tests/test_nucleo_divergencias.py): Python exacto.
* [ts/README.md](../../ts/README.md), tabla «Diferencias que quedan» y sección «Limitaciones».
