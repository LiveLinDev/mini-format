# ADR 0007. Compatibilidad hacia adelante mediante `v`

* Estado: aceptada
* Fecha: 2026-09-01 (SPEC 1.0, precisada en la versión 1.1.0 de las herramientas); registro retrospectivo del 2026-09-16
* Especificación: [SPEC.md](../../SPEC.md) §5, §6 (E05) y §10 («Consequences»)

## Contexto y problema

Una familia crece añadiendo extensiones al final (ADR 0006). Un lector desplegado con
la versión anterior del contrato recibirá documentos con campos que no conoce. Si los
rechaza, cada ampliación obliga a actualizar a todos los lectores a la vez; si acepta
cualquier campo excedente, un error de aridad (por ejemplo, una `|` sin escapar) pasa
inadvertido.

## Alternativas consideradas

1. **Rechazar siempre los campos excedentes** (E05).
2. **Ignorar siempre la cola desconocida.**
3. **Ignorar la cola solo cuando la cabecera del mismo prefijo declara un `v` mayor**
   que la versión del contrato del lector, validando léxicamente la línea completa.

## Decisión

Se adopta la alternativa 3. Con `v` menor o igual que la versión del contrato, un
registro con más campos que los declarados es E05. Con `v` mayor, el parser valida la
línea completa (escapes incluidos), decodifica los campos conocidos e ignora
únicamente los finales desconocidos. Una bifurcación usa otro prefijo y no se lee
directamente con el contrato del padre.

## Consecuencias

* El crecimiento compatible solo incrementa `v`; los lectores anteriores siguen
  funcionando.
* Los campos excedentes sin declaración de versión se siguen detectando como error.
* Un escape inválido en la cola ignorada sigue siendo E09.

## Evidencia

* [CHANGELOG.md](../../CHANGELOG.md), versión 1.1.0: corrección de la compatibilidad hacia
  adelante del núcleo; solo una versión declarada posterior del mismo prefijo permite
  campos finales desconocidos.
* [tests/test_mini.py](../../tests/test_mini.py), `test_older_parser_reads_newer_same_prefix_documents`:
  añade `|v=2` y un campo `future` y espera los 12 registros.
* [tests/test_js_port.mjs](../../tests/test_js_port.mjs): la misma comprobación contra el motor
  del playground.
* Casos de conformidad: `arity-more` (E05 sin `v` posterior) en
  [conformance/cases/arity.json](../../conformance/cases/arity.json).
