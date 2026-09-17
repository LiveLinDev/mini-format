# ADR 0016. Tipos `date` y `decimal`

* Estado: aceptada
* Fecha: 2026-09-17 (SPEC 1.1)
* Especificación: [SPEC.md](../../SPEC.md) §4, §6 y §7

## Contexto y problema

Los dominios de integración declaran con frecuencia fechas y montos. En SPEC 1.0 solo
podían representarse como `str` (sin validación) o `float` (con pérdida de precisión
binaria y sin conservar la escala, p. ej. `12.50`). Las familias oficiales ya describían
fechas como texto libre: la clave de cabecera `d` es `str` con la descripción «generation
date YYYYMMDD». El ingeniero integrador necesita declarar el tipo y que el analizador
reporte E06 con número de línea cuando un valor no lo cumple, o conocer la justificación
de su exclusión.

## Alternativas consideradas

1. **Excluir los tipos** y documentar el uso de `str` con validación en la aplicación.
2. **`date` y `decimal` como tipos escalares** con forma textual estricta y valor canónico
   string.
3. **Fecha y hora con zona horaria (ISO 8601 completo)** y decimales como `number` JSON.

## Decisión

Se adopta la alternativa 2:

* `date`: `AAAA-MM-DD`, día existente del calendario gregoriano proléptico entre
  0001-01-01 y 9999-12-31; JSON canónico, el mismo texto. `min`/`max` opcionales como
  cadenas `AAAA-MM-DD` (E13).
* `decimal`: `-?[0-9]+(\.[0-9]+)?`, sin exponente; JSON canónico string, sin ceros a la
  izquierda en la parte entera ni signo en el cero, conservando todos los dígitos
  fraccionarios. `min`/`max` opcionales como cadenas decimales o enteros menores que
  2^53 en valor absoluto, comparados exactamente (E13).
* Formas inválidas: E06 con la línea del registro o de la cabecera. Límites inválidos en
  el contrato: E20. Ambos tipos se admiten en campos, elementos de lista, componentes de
  tupla y claves de cabecera.

## Consecuencias

* Un documento 1.0 no cambia; un contrato que usa `date` o `decimal` requiere una
  implementación 1.1. El caso de contrato 1.0 que usaba `date` como tipo desconocido pasa
  a usar `datetime`.
* El valor canónico string evita que JavaScript o Python redondeen el decimal por coma
  flotante binaria y conserva la escala; el consumidor decide la conversión a su tipo
  exacto (p. ej. `decimal.Decimal`).
* Se excluye la hora y la zona horaria (alternativa 3): sus variantes (desplazamientos,
  segundos intercalares, fracciones) exceden una forma léxica simple y verificable por
  línea; un instante puede declararse como `str` o como dos campos.
* El serializador Python acepta además `datetime.date` y `decimal.Decimal`; un `float`
  para un `decimal` es E06, porque su valor exacto no es el decimal escrito.
* El bloque de especificación del prompt indica la forma textual de ambos tipos.

## Evidencia

* [forks/a/README.md](../../forks/a/README.md): la clave de cabecera `d` se documenta como
  `str`, «generation date YYYYMMDD», sin validación de tipo.
* [generative/results/e1_samples.csv](../../generative/results/e1_samples.csv): los fallos de CSV
  con Haiku («invalid literal for int() with base 10: '0.2'») muestran que la ausencia de
  tipos explícitos traslada la validación numérica a cada consumidor.
* Casos 1.1 en [conformance/cases/types.json](../../conformance/cases/types.json)
  (`date-decimal-basic`, `decimal-normalised`, `decimal-exact-digits`,
  `date-decimal-composites`, `date-bad-format`, `date-not-in-calendar`, `date-error-line`
  con E06 en la línea 3, `date-range`, `decimal-range-max`, `date-lenient`, entre otros),
  [header.json](../../conformance/cases/header.json) (`hdr-date-bad`),
  [roundtrip.json](../../conformance/cases/roundtrip.json) (`dumps-date-decimal`,
  `dumps-error-date`, `dumps-error-decimal-float`) y
  [contract.json](../../conformance/cases/contract.json) (`contract-date-decimal-valid`,
  `contract-date-bad-bound`, `contract-decimal-float-bound`).
* El caso `decimal-exact-digits` usa `0.1000000000000000055511151231257827`, que un
  `float` binario no conserva.
