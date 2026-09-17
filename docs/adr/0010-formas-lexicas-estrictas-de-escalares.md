# ADR 0010. Formas léxicas estrictas de booleanos y números

* Estado: aceptada
* Fecha: 2026-09-17 (SPEC 1.1)
* Especificación: [SPEC.md](../../SPEC.md) §4 (formas léxicas) y §6 (tabla de tipos)

## Contexto y problema

La tabla de tipos de SPEC 1.0 definía `bool` como `true`/`false` con `1`/`0` aceptados a
la entrada, `int` como `-?[0-9]+` y `float` como «número JSON». Las implementaciones de
referencia eran más permisivas: aceptaban `yes`/`no`/`y`/`n`/`t`/`f` sin distinguir
mayúsculas, enteros con `+`, flotantes como `.5` o `1.` y, en Python, dígitos Unicode no
ASCII. Otra implementación que siguiera la tabla rechazaba esos documentos: el
resultado dependía de la implementación.

## Alternativas consideradas

1. **Normalizar la permisividad de la referencia** en la especificación.
2. **Aplicar la tabla 1.0 de forma estricta**, con dígitos ASCII, y precisar lo que la
   tabla dejaba implícito.
3. **Permisividad configurable por contrato.**

## Decisión

Se adopta la alternativa 2. `bool` acepta exactamente `true`, `false`, `1` y `0`; `int`
es `-?[0-9]+`; `float` es `-?[0-9]+(\.[0-9]+)?([eE][+-]?[0-9]+)?`. Solo se admiten
dígitos ASCII, sin signo `+`, y un flotante lleva dígitos a ambos lados del punto.
Cualquier otra forma es E06. Se mantienen los ceros a la izquierda, que la suite 1.0 ya
aceptaba (`05`, `0.50`), y la salida canónica los elimina.

## Consecuencias

* Todo documento válido según la tabla 1.0 sigue siendo válido con el mismo objeto
  canónico; solo se rechazan formas que 1.0 no definía.
* Vocabularios como sí/no deben declararse como `enum`, cuyo conjunto de valores es
  explícito y no depende del idioma (por ejemplo, «n» también es la clave de recuento y
  la inicial de «no»).
* La validación es idéntica en Python, TypeScript y el navegador, sin depender de las
  clases de caracteres Unicode de cada lenguaje.
* La alternativa 1 se descarta porque convierte particularidades de una implementación en
  norma; la 3, porque rompe la regla de que el contrato solo describe datos.

## Evidencia

* SPEC 1.0, §6, tabla de tipos (revisión `d4a1d44` de [SPEC.md](../../SPEC.md)).
* Comportamiento previo de la referencia: `_TRUE = {"true", "1", "yes", "y", "t"}` y
  `_INT_RE = re.compile(r"^[+-]?\d+$")` en [src/minifmt/values.py](../../src/minifmt/values.py)
  (revisión `d4a1d44`); la lista de puntos pendientes de
  [conformance/README.md](../../conformance/README.md) en esa revisión.
* Casos de conformidad: `sc-bool-yes`, `sc-bool-t`, `sc-bool-no`, `sc-bool-uppercase`,
  `sc-int-plus`, `sc-int-unicode-digits`, `sc-float-plus`, `sc-float-leading-dot`,
  `sc-float-trailing-dot`, `sc-float-nan` y `sc-leading-zeros` en
  [conformance/cases/types.json](../../conformance/cases/types.json); casos 1.0
  `sc-bool-01` y `rt-over-escaped-normalised` sin cambios.
