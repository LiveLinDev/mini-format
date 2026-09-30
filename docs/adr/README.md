# Registro de decisiones de arquitectura (ADR)

Este directorio documenta las decisiones que dan forma a la especificación `.mini`
([SPEC.md](../../SPEC.md), [SPEC.es.md](../../SPEC.es.md)) y a sus implementaciones.
Cada registro sigue el formato MADR en versión breve: contexto y problema,
alternativas consideradas, decisión, consecuencias y evidencia. La evidencia enlaza
archivos del repositorio; toda cifra citada figura literalmente en el archivo
enlazado o se obtiene contando sus filas, y así se indica.

Convenciones:

* Numeración correlativa de cuatro dígitos; un registro aceptado no se reescribe. Si
  una decisión cambia, se crea un registro nuevo que declara a cuál reemplaza.
* Estados: *propuesta*, *aceptada*, *reemplazada por ADR NNNN*.
* Los registros 0001–0007 documentan de forma retrospectiva decisiones vigentes
  desde SPEC 1.0 (2026-09-01). Los registros 0008–0016 corresponden a SPEC 1.1
  (2026-09-17) y a la versión 1.2.0 de las herramientas. Los registros 0017 y 0018 son
  propuestas de la auditoría V5 (2026-09-30): no están vigentes y no cambian la norma.
* Una regla nueva de la especificación requiere su ADR, su caso de conformidad en
  [`conformance/generate.py`](../../conformance/generate.py) y la implementación
  equivalente en Python y TypeScript ([CONTRIBUTING.md](../../CONTRIBUTING.md)).

## Índice

| ADR | Título | Estado | SPEC |
|---|---|---|---|
| [0001](0001-formato-posicional-con-contrato.md) | Formato posicional con contrato compartido | aceptada | 1.0, §1, §6, §7 |
| [0002](0002-escapes-con-barra-y-comillas.md) | Protección del separador con barra invertida y comillas CSV | aceptada | 1.0, §3.3, §3.4 |
| [0003](0003-lista-marcada-con-asterisco.md) | Lista marcada con sufijo `*` | aceptada | 1.0, §6 |
| [0004](0004-clave-de-conteo.md) | Clave de conteo `n` y `count_key` | aceptada | 1.0, §5 |
| [0005](0005-modo-tolerante.md) | Modo tolerante y recuperación parcial | aceptada | 1.0, §8 |
| [0006](0006-protocolo-de-bifurcacion.md) | Protocolo de bifurcación e invariantes I1–I5 | aceptada | 1.0, §10 |
| [0007](0007-compatibilidad-hacia-adelante-por-version.md) | Compatibilidad hacia adelante mediante `v` | aceptada | 1.0, §6, §10 |
| [0008](0008-motor-del-playground-generado-desde-typescript.md) | Motor del playground generado desde la biblioteca TypeScript | aceptada | 1.1, §2 |
| [0009](0009-escape-de-coma-con-cualquier-separador.md) | `\,` es un escape válido con cualquier separador | aceptada | 1.1, §3.3 |
| [0010](0010-formas-lexicas-estrictas-de-escalares.md) | Formas léxicas estrictas de booleanos y números | aceptada | 1.1, §4, §6 |
| [0011](0011-codigo-de-valor-de-cabecera-mal-tipado.md) | Código de error de un valor de cabecera mal tipado | aceptada | 1.1, §5 |
| [0012](0012-claves-de-cabecera-repetidas.md) | Claves de cabecera repetidas | aceptada | 1.1, §5 |
| [0013](0013-elementos-de-lista-vacios.md) | Elementos de lista vacíos | aceptada | 1.1, §3.4, §6 |
| [0014](0014-lista-opcional-vacia-es-null.md) | La lista opcional vacía es null | aceptada | 1.1, §6 |
| [0015](0015-errores-del-serializador.md) | Códigos de error del serializador | aceptada | 1.1, §9 |
| [0016](0016-tipos-date-y-decimal.md) | Tipos `date` y `decimal` | aceptada | 1.1, §6 |
| [0017](0017-espacio-exterior-decimal-canonico-y-blancos.md) | Espacio exterior, escape de elementos de lista, decimal canónico, valores por omisión, registros vacíos y conjunto de blancos | **propuesta (no vigente)** | §3.4, §3.5, §6, §9 |
| [0018](0018-enteros-grandes-en-typescript.md) | Enteros fuera de ±2^53 en TypeScript y en el navegador | **propuesta (no vigente)** | §4, §6 |
| [0030](0030-propuesta-alias-de-enumeracion-y-diccionarios-por-documento.md) | Alias de enumeración y diccionarios por documento dentro de `.mini` 1.x (simulación de la ganancia) | **propuesta (no vigente)** | §5, §6 |
