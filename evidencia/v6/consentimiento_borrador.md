# Consentimiento informado para participar en V6b: BORRADOR

> **PENDIENTE DE REVISIÓN. Sin firmas y sin aprobación.** Este texto es un borrador del equipo para
> discutirlo con el asesor y con el órgano institucional que corresponda. **No es el formulario
> institucional**, no se usa para reclutar ni para sesiones reales y no contiene ninguna firma ni
> consentimiento supuesto. El consentimiento y el manejo de datos requieren revisión institucional antes de
> reclutar (Plan de Validación v3, P101 y A.3). Los corchetes `[...]` son datos que aún no existen y que
> **no deben inventarse**.

## Qué debe revisar y aprobar el comité o el asesor

| # | Punto | Estado |
|---|---|---|
| 1 | Si el estudio requiere aprobación ética formal o basta la del asesor, y cuál es el órgano que decide | Pendiente |
| 2 | El texto final del consentimiento, en el formato del formulario institucional (este borrador solo aporta el contenido) | Pendiente |
| 3 | Qué datos se guardan y por cuánto tiempo; **fecha de eliminación** de los datos y de cualquier grabación | Pendiente: `[fecha por fijar]` |
| 4 | Quién tiene acceso a los datos (equipo y asesor) y dónde se guardan | Propuesta abajo; pendiente |
| 5 | Si se graba la pantalla: texto del consentimiento **específico y separado**, y si finalmente se permite (la propuesta es que no) | Pendiente |
| 6 | Medidas ante la relación de poder si los participantes son estudiantes de la misma institución (la participación no afecta notas ni evaluación; quien evalúa no es quien recluta) | Pendiente |
| 7 | Normativa de protección de datos personales que aplica y su cumplimiento (el equipo no ha verificado cuál: por ejemplo, la ley peruana de protección de datos personales, por confirmar) | Pendiente |
| 8 | Compensación o reconocimiento, si lo hubiera (este borrador asume que no hay) | Pendiente |
| 9 | Canal de contacto del equipo para dudas y para retirarse | Pendiente: `[correo institucional del equipo]` |
| 10 | Procedimiento si el participante se retira (qué se elimina y en qué plazo) | Propuesta abajo; pendiente |
| 11 | Que la versión lingüística del SUS usada esté fijada antes de la primera sesión | Pendiente (`sus/sus.md`) |

## Dónde se guardan los datos

* **Datos de sesión** (códigos seudónimos, tiempos, resultados, SUS, notas): `evidencia/restringida/v6/`.
  Esa carpeta **no se publica**: git la ignora (`.gitignore`). Solo se versiona `evidencia/restringida/README.md`.
* **Consentimientos firmados** y **lista de contacto**: fuera del repositorio, en el almacenamiento
  institucional que indique el comité, **separados** de los datos de sesión. El código seudónimo es lo único
  que liga ambos y solo lo conoce el equipo.
* **Lo que sí se publica**: el resumen agregado (por ejemplo, medias e intervalos), sin datos individuales ni
  identificadores, y solo cuando lo permita la aprobación.
* No se guardan claves de API, credenciales ni datos de terceros.

---

## Texto propuesto para el participante

**Título del estudio.** Evaluación de la facilidad de integrar mini-format (código del proyecto TP202610039).

**Propósito.** Queremos saber qué tan fácil es integrar mini-format, una notación para que los modelos de
lenguaje devuelvan datos estructurados, en un programa pequeño, en comparación con hacerlo con JSON. **Se
evalúa el componente, no tus conocimientos ni tu capacidad.**

**Qué harás.** Resolverás cinco tareas de programación cortas con ejemplos preparados (dos versiones de una
misma tarea, una con JSON y otra con mini-format, y otras tres que prueban funciones de mini-format) y
contestarás un cuestionario de diez preguntas sobre tu experiencia. Un observador del equipo medirá el
tiempo, anotará lo que ocurra y registrará si necesitas ayuda. El observador no te dará instrucciones de
solución.

**Duración.** Hasta 120 minutos en total: unos 10 de introducción, hasta 100 de tareas y unos 10 de
cuestionario y cierre. Puede dividirse en dos encuentros. Puedes pedir una pausa cuando quieras.

**Participación voluntaria.** Participar es voluntario y puedes retirarte en cualquier momento, sin dar
explicaciones y **sin ninguna consecuencia académica o laboral**. Si te retiras, eliminaremos tus datos si lo
pides.

**Qué datos se guardan.** Un código seudónimo (por ejemplo `EST-07`), tu perfil general (por ejemplo, estudiante
o desarrollador), el lenguaje que usas, tu sistema operativo, los tiempos y resultados de cada tarea, las
ayudas que hayas necesitado, tus respuestas al cuestionario y notas del observador que describen hechos.
**No** guardamos tu nombre junto a estos datos, ni credenciales, ni datos de terceros. Te pedimos que no uses
cuentas personales ni información de otras personas durante las tareas.

**Quién puede ver los datos.** Solo el equipo del proyecto y su asesor. Los datos de sesión se guardan en
`[almacenamiento por indicar]`, separados de este formulario y de tu información de contacto. En publicaciones
solo se mostrarán resultados agregados, sin forma de identificarte.

**Cuánto tiempo se guardan.** Hasta `[fecha por fijar]`; después se eliminan los datos de sesión y cualquier
grabación.

**Riesgos y beneficios.** No esperamos riesgos superiores a los de una actividad de programación cotidiana;
puede haber cansancio o frustración si una tarea se complica. Tu participación ayuda a mejorar el
componente. `[Compensación: ninguna / por indicar]`.

**Contacto.** Para preguntas, para retirarte o para pedir que eliminemos tus datos: `[correo institucional del equipo]`.

### Grabación de pantalla (consentimiento separado)

Por defecto **no se graba**. Si el órgano aprobador lo permitiera, la grabación se autorizaría aquí, por
separado, no capturaría credenciales y se eliminaría en `[fecha por fijar]`.

- [ ] Autorizo la grabación de pantalla.
- [ ] No autorizo la grabación de pantalla.

### Confirmaciones del participante (se completan en la sesión, en el formulario institucional aprobado)

- [ ] Soy mayor de edad.
- [ ] He leído y entendido esta información y pude hacer preguntas.
- [ ] Acepto participar de forma voluntaria.
- [ ] Sé que puedo retirarme en cualquier momento sin consecuencias.

| | |
|---|---|
| Participante (código seudónimo asignado por el equipo) | `[se asigna en la sesión]` |
| Firma del participante | *(sin firma: se firma únicamente en el formulario institucional aprobado)* |
| Fecha | *(sin fecha)* |
| Nombre y firma de quien recoge el consentimiento | *(sin firma)* |

*Este borrador no incluye ninguna firma, ninguna fecha de aceptación ni ningún nombre de participante.*
