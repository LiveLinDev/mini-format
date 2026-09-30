# Cuestionario SUS en V6b

**Sin participantes: estudio pendiente, materiales listos.** Esta carpeta fija el instrumento y la forma de
puntuarlo; no contiene ninguna respuesta.

La versión en español es **PROVISIONAL del equipo: versión lingüística por fijar**. No se presenta como una
escala validada (Plan de Validación v3, P89). Antes del piloto, el equipo y el asesor deben fijar y adjuntar
la versión autorizada.

## Atribución correcta

La System Usability Scale (SUS) es de **John Brooke**:

> Brooke, J. (1996). SUS: A quick and dirty usability scale. En *Usability evaluation in industry*
> (pp. 189-194). Taylor & Francis.

La hoja con los diez enunciados lleva la nota «© Digital Equipment Corporation, 1986».

**Qué se verificó.** El 2026-09-30 se cotejaron los diez ítems originales en inglés y la regla de puntuación
con el texto del capítulo de Brooke alojado en `digital.ahrq.gov` (enlace completo en `sus_items.json`). La
referencia bibliográfica es la del Plan v3 (R15); no se comprobó por separado contra el libro.

## Los diez ítems originales (Brooke, 1996)

Escala de 5 puntos: 1 = *Strongly disagree*, 5 = *Strongly agree*. Cinco ítems positivos (impares) y cinco
negativos (pares). Los textos están en `sus_items.json` (clave `original_en`).

| # | Enunciado original en inglés |
|---|---|
| 1 | I think that I would like to use this system frequently |
| 2 | I found the system unnecessarily complex |
| 3 | I thought the system was easy to use |
| 4 | I think that I would need the support of a technical person to be able to use this system |
| 5 | I found the various functions in this system were well integrated |
| 6 | I thought there was too much inconsistency in this system |
| 7 | I would imagine that most people would learn to use this system very quickly |
| 8 | I found the system very cumbersome to use |
| 9 | I felt very confident using the system |
| 10 | I needed to learn a lot of things before I could get going with this system |

## Puntuación estándar

1. Ítems **impares** (1, 3, 5, 7, 9): contribución = respuesta − 1.
2. Ítems **pares** (2, 4, 6, 8, 10): contribución = 5 − respuesta.
3. Se suman las diez contribuciones (cada una va de 0 a 4) y se multiplica por **2,5**.
4. Resultado de 0 a 100. **No es un porcentaje** de tareas completadas ni de ninguna otra cosa.

`SUS = 2,5 × [Σ impares (r − 1) + Σ pares (5 − r)]`

Se aplica después de usar el sistema y **antes de cualquier conversación** con el observador; se pide la
respuesta inmediata a cada ítem y se marcan todos (si alguien no puede responder uno, marca el punto central).
Un formulario incompleto **no se puntúa** y nunca se mezclan pilotos con el estudio (Plan v3, P92).

Implementaciones, que se prueban entre sí: `tools/analizar_v6.py` (`puntuar_sus`), `herramienta/sesion.html`
(`V6.puntuarSUS`) y la hoja `V6 SUS` del libro de Excel del plan. Las pruebas (`tests/test_v6_analisis.py`,
`tests/test_v6_herramienta.py`) usan vectores de respuestas calculados a mano.

## Versión en español

### Provisional del equipo (la que trae la herramienta)

Redactada por el equipo para poder ensayar la herramienta. **No es una adaptación publicada** y no debe
usarse con participantes reales sin fijarla. Los textos están en `sus_items.json` (clave `es_provisional`) y
en `herramienta/sesion.html`. Anclas provisionales: «Totalmente en desacuerdo» y «Totalmente de acuerdo».

### Adaptación publicada candidata (no adoptada)

Se buscó una adaptación al español publicada y verificable. Se encontró y se abrió la ficha de:

> Sevilla-Gonzalez, M. D. R., Moreno Loaeza, L., Lazaro-Carrera, L. S., Bourguet Ramirez, B., Vázquez
> Rodríguez, A., Peralta-Pedrero, M. L., y Almeda-Valdes, P. (2020). Spanish Version of the System Usability
> Scale for the Assessment of Electronic Tools: Development and Validation. *JMIR Human Factors*, 7(4),
> e21161. https://doi.org/10.2196/21161 (acceso abierto, CC BY 4.0 según PubMed Central: PMC7773510).

**Lo verificado**: título, revista, volumen, número, identificador del artículo, año y DOI (ficha de PubMed
Central abierta el 2026-09-30). **Lo no verificado**: los diez ítems finales en español están en el Apéndice
multimedia 2 del artículo; ese apéndice **no se abrió** en esta sesión, por lo que no se reproducen aquí ni se
afirma nada sobre su redacción. La elección de esta u otra versión es una decisión del equipo y del asesor:
deben abrir el apéndice, comparar con la traducción provisional, fijar una y citar la fuente. Mientras tanto,
la traducción provisional sigue marcada como tal.

## Cómo fijar la versión en español (pasos)

1. Abrir el Apéndice multimedia 2 del artículo citado (o elegir otra adaptación publicada y verificable).
2. Decidir con el asesor cuál se adopta y registrar la decisión y su fecha.
3. Sustituir `es_provisional` en `sus_items.json` y los textos de `SUS_ES_PROV` en `herramienta/sesion.html`
   (una prueba comprueba que ambos coinciden) y cambiar la etiqueta «PROVISIONAL» por la cita de la fuente.
4. Reejecutar `tests/test_v6_herramienta.py` y dejar constancia en el protocolo.
