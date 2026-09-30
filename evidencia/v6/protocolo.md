# Protocolo operativo de V6b (estudio controlado con personas)

**Estado: sin participantes; estudio pendiente, materiales listos.** Este protocolo no contiene
resultados. Sigue el Plan de Validación v3 (secciones 9 a 11 y anexo A) y el Charter v5 (indicador I4.4);
donde el plan deja una decisión abierta, aquí se propone un valor por defecto y se marca como
**decisión del equipo** para fijarla antes del piloto.

V6b es **controlado con tareas**: tareas estandarizadas y respuestas congeladas. Tener personas reales
no lo vuelve naturalista (Plan v3, tabla T2). Lo naturalista es V6a (`v6a_plantilla.md`).

| Elemento | Dónde está |
|---|---|
| Tareas T1 a T4, respuestas congeladas y criterios objetivos | `tareas/` (`tareas/LEEME.md`) |
| Verificador objetivo de entregas (solo observador) | `tareas/verificar_entrega.py` |
| Hoja de observación impresa | `tareas/hoja_observacion.md` |
| Herramienta de sesión (cronómetro, registro, exportación) | `herramienta/sesion.html` |
| Generador de contrabalanceo y análisis | `tools/analizar_v6.py` |
| Consentimiento (borrador) | `consentimiento_borrador.md` |
| SUS | `sus/sus.md`, `sus/sus_items.json` |
| Dónde se guardan los datos reales | `evidencia/restringida/v6/` (git lo ignora) |

## 1. Antes de reclutar

La sesión 1 no empieza hasta cumplir todo este apartado.

1. **Aprobación institucional.** El consentimiento y el manejo de datos requieren revisión
   institucional antes de reclutar (Plan v3, P101). Lo que debe aprobar el comité o el asesor está en
   `consentimiento_borrador.md`. Sin esa aprobación no se recluta a nadie.
2. **Versión lingüística del SUS.** Fijar y adjuntar la versión autorizada en español (Plan v3, P89).
   Hoy la traducción es provisional (`sus/sus.md`).
3. **Congelar lo que se evalúa.** Registrar, en `evidencia/restringida/v6/preparacion.json`, el commit
   de mini-format, el hash del paquete que se instala (`.whl` o `.tgz`), el hash de la guía entregada y
   el resultado de `python evidencia/v6/tareas/construir_tareas.py --verificar`. Si cambia algo de
   esto después de empezar, se documenta como desviación (sección 8).
4. **Verificar los materiales.**
   ```bash
   PYTHONPATH=src python evidencia/v6/tareas/construir_tareas.py --verificar
   PYTHONPATH=src python -m pytest -q -p no:cacheprovider tests/test_v6_tareas.py tests/test_v6_analisis.py tests/test_v6_herramienta.py
   ```
5. **Decisiones que fija el equipo antes del piloto** (valor propuesto entre paréntesis):

   | Decisión | Propuesta |
   |---|---|
   | Validación de JSON disponible en la condición JSON | `jsonschema` (Python) y `ajv` (TypeScript), preinstalados: es lo que un desarrollador usaría de forma natural; sin ellos la condición JSON no sería una comparación razonable |
   | Componentes de la condición .mini | `minifmt` (Python) o el paquete TypeScript del perfil base, preinstalados, más la guía |
   | Guía entregada en la condición .mini | `sitio/content/quickstart.es.md` tal como está en el commit congelado (copia en `tareas/participante/guia_mini.md`) |
   | Asistentes de IA generativa durante las tareas | No permitidos (confundirían el tiempo); sí documentación oficial y búsqueda de documentación |
   | Acceso a internet | Solo para documentación; sin credenciales personales ni datos de terceros (Plan v3, A.1) |
   | Grabación de pantalla | No, salvo consentimiento específico aparte (Plan v3, P101) |
   | Semilla del contrabalanceo | Un entero fijado y registrado **antes** de reclutar; no se cambia después |
   | Tamaño objetivo | 10 válidos, mínimo 8, máximo 12 (la decisión de parar no depende de resultados; ver sección 8) |

6. **Generar y guardar el plan de contrabalanceo** (una sola vez, con N = 12 para que cualquier
   prefijo sirva; el algoritmo asigna por bloques y el plan de N = 8 es prefijo del de N = 12):
   ```bash
   PYTHONPATH=src python tools/analizar_v6.py contrabalanceo --participantes 12 --semilla <SEMILLA> \
       --formato json --salida evidencia/restringida/v6/plan.json
   ```
   Cada participante recibe una de cuatro secuencias (orden JSON-luego-.mini o .mini-luego-JSON, y qué
   variante A o B se resuelve con cada formato). Los pilotos `PIL-01` y `PIL-02` llevan un orden distinto
   cada uno. Los códigos no llevan datos personales.
7. **Preparar la carpeta de la sesión.** Copiar `tareas/participante/` a un directorio limpio por
   participante, con una carpeta `entrega/` vacía. El participante **no** recibe `tareas/observador/`
   (contiene las respuestas de referencia y las soluciones) ni `verificar_entrega.py`.
8. **Preparar el equipo del participante.** Python 3.9 o posterior con `minifmt` y `jsonschema`, o
   Node 22.6 o posterior con el paquete TypeScript y `ajv`; editor a su elección. Probar un `hola mundo`
   y la carga de ambos paquetes **antes** de la sesión (el tiempo de instalación no cuenta como tarea).

## 2. Población

* 8 a 12 participantes **válidos**, mayores de edad, con experiencia en Python o TypeScript, JSON y
  consumo de APIs; estudiantes de los últimos ciclos de Ingeniería de Software o Sistemas y, en lo
  posible, al menos tres desarrolladores en ejercicio (P81).
* **Se excluyen**: autores del proyecto, asesores y cualquier persona con experiencia previa directa
  con mini-format (P81). Pregunta esto en la selección y vuélvelo a confirmar en la sesión.
* **2 pilotos adicionales** hacen el piloto y no entran en el análisis (P81).
* Cada participante es una **persona real**. Ningún agente, modelo o script simula participantes.
* La lista de contacto se guarda aparte, fuera del repositorio y separada de los datos (P101).

## 3. Pilotos

1. Los dos pilotos siguen el mismo protocolo y se registran con `tipo = piloto` (`PIL-01`, `PIL-02`).
2. Sirven para detectar enunciados ambiguos, topes irreales, fallos de la herramienta o del entorno.
3. Tras el piloto, el equipo revisa y **versiona** cualquier cambio (motivo, fecha, qué cambia) en
   `evidencia/restringida/v6/cambios_tras_piloto.md`. Se puede corregir un enunciado ambiguo; no se
   cambian los topes ni los criterios de éxito por lo que hicieron los pilotos **sin dejar constancia**.
4. Si el cambio es material (otro criterio de éxito, otra tarea), hay que repetir el piloto con
   personas distintas. Los pilotos **nunca** se reutilizan como participantes del estudio ni se mezclan
   con sus cifras; `tools/analizar_v6.py` los excluye por `tipo = piloto`.
5. Los criterios de la sección 9 quedan **congelados antes de la primera sesión del estudio**.

## 4. La sesión, paso a paso (120 minutos como máximo)

La duración es 10 + 100 + 10 = 120 minutos: 10 de introducción y consentimiento, 100 de tareas (topes
30 + 30 + 15 + 10 + 15) y 10 de cuestionario y cierre (Plan v3, P85). La versión previa decía 80 minutos
y estaba mal. Se puede dividir en dos encuentros con el mismo protocolo (por ejemplo: T1 en las dos
condiciones en el primero; T2 a T4, SUS y cierre en el segundo). La pausa no cuenta como desempeño.

| Momento | Qué hace el observador |
|---|---|
| Antes de llegar | Abrir `herramienta/sesion.html` en el navegador del observador; preparar la carpeta limpia y el equipo del participante; tener a mano `hoja_observacion.md` y el consentimiento aprobado. |
| 0 a 10 min | Leer la apertura (abajo). Entregar y explicar el consentimiento; que lo firme en el formulario institucional (fuera de esta herramienta). Confirmar que no es autor ni asesor ni ha usado mini-format. Anotar perfil, lenguaje y entorno **sin datos personales**. En la herramienta: código, semilla, «Aplicar al código indicado», marcar el consentimiento y **Comenzar sesión**. |
| Hasta 100 min de tareas | Las cinco tareas en el orden que marca el plan. Cada una: sección 5. |
| Últimos 10 min | Sección 6: primero el SUS, luego (si hay tiempo) comentarios abiertos. Cerrar y agradecer. |
| Después (observador, sin el participante) | Sección 7. |

**Apertura del observador** (Plan v3, A.1):
«Gracias por participar. Evaluaremos la facilidad de integrar mini-format, no tus conocimientos. Puedes
pedir una pausa o retirarte sin consecuencias. No uses credenciales personales ni datos de terceros.
Trabajarás con ejemplos preparados. Registraré tiempos, resultados y dificultades. Durante cada tarea no
daré instrucciones de solución; si necesitas ayuda, la registraré para comprender dónde mejorar el
componente».

## 5. Conducir cada tarea

1. Entrega la carpeta de la tarea (la herramienta indica cuál: por ejemplo `participante/T1A_json/`) y
   la referencia de salida descrita en el enunciado, **sin revelar la solución** (Plan v3, A.2).
2. Pulsa **Iniciar** cuando le muestres el enunciado: el cronómetro arranca al mostrar la tarea.
3. No des instrucciones de solución. Puedes repetir el enunciado **textualmente**. Cualquier otra
   orientación (qué comando usar, cómo interpretar un error, qué formato tiene algo) es **ayuda** y se
   registra con **Registrar ayuda** (y una nota sin datos personales).
4. Cuando el participante diga «listo»:
   1. Pulsa **Pausar** (el reloj se detiene en ese instante).
   2. Ejecuta el verificador: `PYTHONPATH=src python evidencia/v6/tareas/verificar_entrega.py <T1A|T1B|T2|T3|T4> <carpeta entrega>`.
   3. Si **cumple**: pulsa **Criterio cumplido**. El resultado queda «lograda sin ayuda» o «con
      ayuda» según haya ayudas registradas.
   4. Si **no cumple**: di solo «todavía no cumple el criterio», sin leer qué criterio falla (eso sería
      ayuda), pulsa **Reanudar** y anota en la nota cuántas veces declaró «listo». Puede seguir hasta el tope.
5. **Tope**: al alcanzar el tiempo máximo la herramienta cierra la tarea como **tiempo agotado**. Eso
   **no es éxito**, no se marca a mano y no se convierte en 30 (ni en ningún otro) minutos.
6. Otros cierres: **Abandono** (el participante decide no continuar sin entregar) y **Entrega no
   cumple** (entregó algo que no cumple y no quiere o no puede seguir). Ninguno es éxito.
7. **Deshacer cierre** sirve solo para corregir un clic equivocado; queda en el registro de eventos.
   No puede deshacerse un tiempo agotado ni una tarea posterior ya iniciada.
8. **Fallo técnico del entorno** (se cae el equipo, un paquete no carga): pausa, anótalo como
   incidente, resuelve y reanuda. No es ayuda, pero sí incidente y se informa.
9. Las herramientas de uso general y la documentación están permitidas según las decisiones de la sección 1, punto 5. Toda
   consulta a una persona o a una IA no prevista se anota.

| Tarea | Tope | Éxito (objetivo, lo dice el verificador) |
|---|---|---|
| T1 JSON | 30 min | Los 9 registros válidos idénticos y en orden, sin cambiar valores ni tipos; el inválido rechazado con su posición, sin tumbar a los demás |
| T1 .mini | 30 min | Lo mismo con la variante equivalente y el componente |
| T2 | 15 min | Diagnóstico correcto (código de error y línea) y documento corregido que valida, con el defectuoso reparado sin inventar valores y los otros 11 registros intactos |
| T3 | 10 min | Recupera exactamente los registros completos, sin contar el cortado, e indica cuántos no pudo recuperar y cuál es el primero |
| T4 | 15 min | Su contrato acepta el caso positivo con los nombres y valores esperados y rechaza el negativo con el error esperado |

Los detalles y los enunciados están en `tareas/LEEME.md`.

## 6. Cuestionario SUS

* Se aplica **al terminar las tareas y antes de discutir opiniones** con el observador (Plan v3, tabla
  T11; Brooke, 1996). Que lo responda el participante en la sección 3 de la herramienta, solo.
* «El sistema» de los ítems es mini-format (la guía y el componente). Lee esa aclaración y nada más.
* No expliques ítems, no sugieras respuestas ni comentes la puntuación (A.2). Todos los ítems se
  marcan; si alguien no puede responder uno, marca el punto central (indicación de Brooke).
* Un formulario incompleto **no se puntúa** (P92), pero no invalida por sí solo la sesión.
* La herramienta muestra la puntuación **solo al observador** al final; no se comenta hasta cerrar.

## 7. Después de la sesión

1. Exportar **JSON** y **CSV** desde la sección 5 de la herramienta. Guardarlos en
   `evidencia/restringida/v6/sesiones/` con el nombre que propone la herramienta (`sesion_<código>_<fecha>`).
2. Comprobar que el archivo abre: `python tools/analizar_v6.py puntuar-sus <archivo>` no da error.
3. **Borrar la sesión del navegador** con el botón correspondiente (después de exportar).
4. Completar la hoja de observación en papel si se usó y guardarla con el código, no con el nombre.
5. Guardar la decisión de validez: si la persona no cumple un criterio de elegibilidad descubierto
   después, marcar la sesión como no válida en la herramienta (con el motivo) antes de exportar.
6. La lista de contacto **no** se guarda junto a estos archivos.

## 8. Incidentes, desviaciones y reemplazos

* **Incidente** (problema, severidad, paso, efecto, evidencia): se registra en la herramienta. El
  hallazgo puede originar una nueva historia de usuario sin reescribir resultados previos (T11).
* **Sesión válida** (definición fijada de antemano): persona elegible, con consentimiento, que cerró las
  cinco tareas con cualquier resultado. Un SUS incompleto no invalida la sesión pero ese SUS no se puntúa.
* **No válida**: se retira, no cumple un criterio de elegibilidad, o fallo del observador o del entorno que
  impide medir. Se marca `valido = false` con motivo, **no se borra**, y se cuenta aparte en el resumen.
* **Retirada de un participante**: se respeta y se eliminan sus datos si lo pide (consentimiento).
* **Reemplazos**: si al terminar el calendario hay menos de 8 válidos se reclutan más, hasta 12,
  siguiendo el plan en orden. La decisión de parar o continuar **no puede depender de SUS ni de tiempos**.
* **Cambio de protocolo a mitad de estudio**: se versiona (motivo, fecha, efecto) y se reporta. Un cambio
  de criterios después de ver datos de participantes invalida la interpretación y se informa como tal.

## 9. Criterios y reglas de análisis (fijados antes de analizar)

Son la interpretación del Plan v3 (P92, P93, P95) y se congelan antes de la primera sesión del estudio.

1. **Éxito de una tarea**: resultado «lograda sin ayuda» o «lograda con ayuda» según el verificador.
   `tiempo agotado`, `no completa` y `abandono` **no son éxito**.
2. **Tiempo y censura**: el tiempo activo de T1 se mide con el cronómetro (sin pausas). Una tarea no lograda
   es **censurada**: su tiempo es «mayor que el tope». Para medianas y cuantiles se ordena por encima de
   todos los tiempos observados; **no** se trunca a 30 minutos ni se descarta.
3. **Mediana de T1 .mini** = promedio de los dos valores centrales si n es par. Si alguno de los valores
   que intervienen está censurado, la mediana **no está determinada** y la meta queda **no demostrada**; se
   informa la cota inferior. Cuantiles: interpolación lineal (tipo 7) solo entre valores observados.
4. **Metas**: SUS (media) ≥ 70; mediana de T1 .mini ≤ 30 minutos; al menos 80 % de los intentos de tarea
   logrados **sin ayuda** (criterio operativo adicional propuesto en el plan, P93, no un resultado), con al
   menos 8 participantes válidos de estudio y sin pilotos.
5. **Resultado del estudio**: `cumple` solo si las tres metas se observan con n ≥ 8; `no_cumple` si hay
   n ≥ 8 y alguna meta no se observa o no queda demostrada; `no_evaluable` con menos de 8 válidos. El
   criterio exige demostrarse: una mediana indeterminada no cuenta como cumplida.
6. **SUS**: puntuación de Brooke (impares respuesta − 1, pares 5 − respuesta, suma × 2,5); formularios
   incompletos sin puntuar; media con IC del 95 % (t de Student) y valores individuales seudonimizados.
7. **Tasas**: proporciones con IC del 95 % de Wilson; denominadores explícitos (intentos registrados;
   una tarea sin registrar no cuenta como éxito ni como fallo y se informa).
8. **Comparación pareada de T1** (.mini − JSON): descriptiva (mediana y rango) solo con los participantes
   que lograron ambas condiciones; los pares con censura se cuentan aparte, no se imputan. Con esta muestra
   el análisis es principalmente descriptivo; un contraste no paramétrico (Wilcoxon) y el tamaño del efecto
   son opcionales y se añaden **fuera** de `analizar_v6.py` solo si el patrón de datos lo permite (P95).
9. **Sensibilidad** declarada de antemano: repetir T1 contando la ayuda como fallo.
10. **Amenazas que se reportan**: muestra por conveniencia y predominio de estudiantes; el contrabalanceo
    reduce pero no elimina el aprendizaje; dos variantes de T1 equivalentes por construcción pero no
    calibradas más allá del piloto; T1 en JSON depende de las bibliotecas preinstaladas.

## 10. Análisis

```bash
PYTHONPATH=src python tools/analizar_v6.py resumen evidencia/restringida/v6/sesiones/
PYTHONPATH=src python tools/analizar_v6.py puntuar-sus evidencia/restringida/v6/sesiones/ --formato csv
PYTHONPATH=src python tools/analizar_v6.py t1 evidencia/restringida/v6/sesiones/
PYTHONPATH=src python tools/analizar_v6.py exito evidencia/restringida/v6/sesiones/
```

`resumen` excluye pilotos y sesiones no válidas, lista cuántos son y calcula las tres metas. Se niega a
mezclar datos de ensayo con datos reales y avisa cuando los datos son un fixture de prueba.

## 11. Registro de la corrida

1. Comprobar con `manifiesto` (sin `--escribir`) que el manifiesto es válido:
   `python tools/analizar_v6.py manifiesto evidencia/restringida/v6/sesiones/`.
2. Guardarlo con `--escribir` en `evidencia/corridas/<run_id>/` (contrato `mini-format/corrida/1`,
   procedencia `participantes`). El manifiesto lleva el resumen agregado; **no** los datos
   individuales, que se quedan en `evidencia/restringida/`.
3. Actualizar `evidencia/v6/estado.json` con lo que realmente ocurrió.
4. Toda cifra que aparezca luego en un documento o en la interfaz debe salir de ese archivo validado.

## 12. Lo que no se hace

* No se usan agentes ni modelos como participantes, ni «datos de ejemplo» como si fueran resultados.
* No se rellenan con supuestos los datos faltantes; se dejan `null` y se explica.
* No se mezclan pilotos con el estudio ni fixtures con datos reales.
* No se convierte un tiempo agotado en un éxito de 30 minutos, ni se descarta.
* No se modifican los criterios después de ver datos.
* No se presenta la traducción provisional del SUS como escala validada.
* No se publican consentimientos firmados, contactos ni datos individuales.

## 13. Calendario de referencia (Plan v3, tabla T13)

| Semana | Actividad |
|---|---|
| S8 (5 a 11 de octubre) | Piloto técnico y con dos personas; reclutar; seleccionar segundo sistema de V6a |
| S9 y S10 (12 a 25 de octubre) | Sesiones V6b y evidencia de la segunda integración de V6a |
| S11 a S13 | Análisis, conclusiones y actualización de memoria y artículo |

Las fechas dependen de la aprobación de la sección 1, punto 1: sin ella, el calendario se corre; no se salta la aprobación.
