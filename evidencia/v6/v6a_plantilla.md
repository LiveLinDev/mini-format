# V6a: plantilla y lista de verificación (integración en sistemas reales)

**Estado: plantilla vacía. No hay resultados.** Este documento dice qué evidencia hay que reunir y cómo
se comprueba que está completa. No acredita ninguna integración.

V6a es **naturalista**: estudia la adopción de mini-format en el contexto real de un sistema anfitrión
(Plan de Validación v3, sección 8, y Charter v5, sección 1.4). V6b es **controlado con tareas**; no
se acreditan uno con el otro ni con el mismo número de demostradores (Plan v3, P77).

## Qué exige el plan

* Dos sistemas de **dominios distintos** (P72).
* La integración **sustituye o complementa el lector de la respuesta del modelo sin rehacer el sistema
  anfitrión** (P72).
* El registro muestra contexto, responsable, contrato, cambio de código, instalación, versión, datos
  usados, ejecución, incidentes y limitaciones (P72, tabla T9).
* Segundo sistema: acordar un responsable externo y documentar su operación real; «el demostrador solo
  no demuestra adopción independiente» (tabla T8).

## Lo que NO cuenta por sí solo

| Caso | Por qué no basta |
|---|---|
| CIMA (en código y rutas, `SIMA` y `/sima/`) | Es una integración **reportada por el equipo**. Es un caso de uso legítimo, pero no se da por hecho que sea una adopción ajena al equipo: la auditoría previa (hallazgo C9) observó que el README de V8 enlaza un repositorio de la misma organización que el remoto de mini-format, y el plan no dice si CIMA es ajeno. Hay que **acreditarlo**, no suponerlo. Además sus cifras (350 registros tras reparar frente a 343 válidos iniciales y 5 reparados) están **por conciliar** (P76). |
| El demostrador interno de tickets (mesa de ayuda, `examples/mesa-de-ayuda`, `/mesa-de-ayuda/`) | Lo preparó el equipo para mostrar el caso; los datos son del equipo. No es una adopción independiente (T8). |
| Una sesión V6b | Mide integrabilidad con tareas controladas; es otro estudio. |

## Cómo usar la plantilla

1. Copia `v6a_plantilla.json` a `evidencia/restringida/v6/v6a/ficha_<n>.json` mientras tenga datos
   personales o del sistema anfitrión. Lo publicable (sin datos personales, con autorización) puede
   pasar después a una corrida en `evidencia/corridas/`.
2. Una ficha **por sistema**. No mezcles dos sistemas en una.
3. Lo que no se conozca se deja en `null` y se explica en `limitaciones`. **Nunca** se escribe 0 ni un
   valor supuesto para «rellenar».
4. La ficha solo dice `conformidad_del_mantenedor.confirma_el_alcance_ejecutado: true` cuando existe
   una confirmación real guardada (correo, acta o comentario en el repositorio) y su referencia está en
   `referencia_de_archivo`. No se inventa una firma ni una aprobación.
5. Las respuestas de modelo que se usen llevan su procedencia (`api_real`, `asistido_ia`, etc.) y,
   si hubo llamadas pagadas, su usage real; en este proyecto no hay llamadas de pago autorizadas.
6. Al registrar la ejecución como corrida (`tools/evidencia_lib.py`), un resultado `cumple` o
   `no_cumple` exige estado `ejecutado`, criterio fijado antes y procedencia real; lo histórico o
   asistido por IA es `no_evaluable`.

## Campos de evidencia contextual (equivalen a la tabla T9 del plan)

| Campo de la ficha | Contenido esperado | Pregunta de control |
|---|---|---|
| `identificacion`, `independencia_del_equipo` | Nombre, dominio, versión, ubicación, y por qué el sistema es ajeno al equipo | ¿Quién lo mantiene y qué relación tiene con el equipo? |
| `mantenedor`, `autorizacion` | Rol, organización, código seudónimo; autorización de uso de la evidencia y de envío de datos a un proveedor | ¿Hay autorización guardada y con qué alcance? |
| `cambio`, `contrato`, `version_del_componente` | Componente reemplazado, commits antes y después, líneas, contrato con hash, versión de mini-format con hash del paquete | ¿Se puede reproducir el cambio desde los commits? |
| `ejecucion`, `incidencias` | Escenario, entradas permitidas, datos usados, modelo y procedencia, fechas UTC, fallos observados | ¿Es operación real o un montaje? |
| `impacto_tecnico` | Esfuerzo (con quién lo midió y cómo), dependencias, cambios de interfaz o persistencia, riesgos de retorno | ¿Se midió o se estima? |
| `conformidad_del_mantenedor` | Confirmación del alcance ejecutado | ¿Existe el archivo al que se refiere? |
| `limitaciones` | Lo que no se pudo hacer o verificar | ¿Dice la causa exacta? |

## Lista de verificación de cierre (marcar solo con evidencia en mano)

**Sistema 1: CIMA (SIMA)**

- [ ] Commit de la rama y de la integración, conservados y enlazados (los hashes citados en el backlog que
  faltan en este repositorio viven en otros repositorios: confirmar dónde).
- [ ] Respuestas y condiciones de comparación conservadas (modelo, parámetros, datos usados).
- [ ] Conciliados 350 frente a 343 + 5 (P76), con la regla escrita antes de recalcular.
- [ ] Acreditada (o descartada) la independencia del equipo; si no es ajeno, se reporta como
  caso contextual y **no** como segunda adopción externa.
- [ ] Autorización de uso de evidencia y de envío de datos a un proveedor.
- [ ] Ficha completa y confirmación del mantenedor guardada.

**Sistema 2: dominio distinto, responsable externo**

- [ ] Sistema elegido, de un dominio distinto al de CIMA, con mantenedor externo que acepta participar.
- [ ] Autorización por escrito de uso de la evidencia; acuerdo sobre qué datos pueden usarse.
- [ ] Cambio de código real (commits antes y después) que sustituye o complementa el lector de la
  respuesta del modelo sin rehacer el sistema.
- [ ] Contrato generado o escrito y su hash; versión de mini-format y hash del paquete.
- [ ] Ejecución documentada en el contexto real, con incidencias.
- [ ] Esfuerzo de integración medido y no estimado (quién, cómo, cuánto).
- [ ] Confirmación del mantenedor sobre lo ejecutado.
- [ ] Ficha completa.

**Global**

- [ ] Los dos sistemas son de dominios distintos entre sí, y la diferencia está justificada en la ficha.
- [ ] Ninguna ficha contiene datos personales ni secretos.
- [ ] `evidencia/v6/estado.json` actualizado con lo que realmente se cumple.

Mientras alguna casilla de sistema 2 esté sin marcar, **V6a sigue pendiente** y el indicador I4.4 del
Charter no puede declararse cumplido.
