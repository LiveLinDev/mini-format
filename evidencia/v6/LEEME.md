# V6: integración en sistemas reales (V6a) y estudio con personas (V6b)

> **Estado: sin participantes: estudio pendiente, materiales listos.**
> Esta carpeta contiene protocolos, tareas, instrumentos y herramientas. **No contiene ningún resultado**
> ni datos de ninguna persona. Nada de lo que hay aquí acredita el indicador I4.4 del Charter.

V6a y V6b no son intercambiables (Plan de Validación v3, P77):

| | V6a | V6b |
|---|---|---|
| Clasificación (FEDS) | **Naturalista**: integración en el contexto real de un sistema | **Controlado con tareas**: tareas estandarizadas y respuestas congeladas con personas reales |
| Qué se necesita | Dos sistemas de **dominios distintos**, con mantenedor, permiso, cambio de código, contrato, ejecución, incidencias y versión | 2 pilotos excluidos y **al menos 8 participantes válidos** (hasta 12) |
| Qué hay hoy | Plantilla de ficha y lista de verificación, sin datos | Protocolo, tareas, verificador, hoja de observación, consentimiento (borrador), SUS, herramienta de sesión y análisis |
| Qué **no** cuenta | CIMA/SIMA y el demostrador interno de tickets **no** acreditan por sí solos una segunda adopción externa | Agentes o modelos que simulen participantes |

## Mapa de archivos

| Archivo | Para qué sirve |
|---|---|
| `estado.json` | Registro de estado: `pendiente`, sin resultados, y qué falta |
| `protocolo.md` | Protocolo operativo de V6b paso a paso, con los criterios de análisis fijados antes de recoger datos |
| `tareas/` | Repositorio de tareas T1 a T4 con respuestas **congeladas**, verificador objetivo y hoja de observación (`tareas/LEEME.md`) |
| `consentimiento_borrador.md` | Consentimiento informado **BORRADOR pendiente de revisión**; qué debe aprobar el comité o asesor; dónde se guardan los datos |
| `sus/` | Los 10 ítems de Brooke (1996), la puntuación estándar y la versión en español (**provisional**, por fijar) |
| `herramienta/sesion.html` | Herramienta sin conexión: cronómetro por tarea con topes, registro, contrabalanceo, exportación y borrado (`herramienta/LEEME.md`) |
| `v6a_plantilla.json`, `v6a_plantilla.md` | Ficha de evidencia contextual de V6a y lista de verificación |
| `fixtures_de_prueba/` | Datos **de prueba** para las pruebas del análisis. No son datos de participantes |
| `../../tools/analizar_v6.py` | Contrabalanceo y análisis (SUS, T1 con censura, éxito por tarea, pilotos, resumen, manifiesto) |
| `../../tests/test_v6_*.py` | Pruebas de todo lo anterior |

## Reglas de este flujo

1. **Sin datos inventados.** Lo desconocido es `null` y se explica. Ninguna cifra de este directorio es un
   resultado; las cifras que aparecen son parámetros del plan (topes, mínimos, metas) o salen de archivos del
   repositorio.
2. **Procedencia.** Los datos de las tareas son reales del repositorio (variante A de T1) o **sintéticos** (el
   resto), y así están etiquetados. Nada viene de una llamada de pago a un modelo.
3. **Personas reales.** V6b necesita personas reales. Un modelo o agente que simule participantes no vale.
4. **Un tiempo agotado no es éxito.** Se trata como **censurado**: no se trunca a 30 minutos ni se descarta.
5. **Datos reales fuera de git.** Sesiones, consentimientos y contactos viven en `evidencia/restringida/`
   (ignorada por git). Un estudio solo pasa a «ejecutado» cuando hay datos reales registrados como corrida
   con `tools/evidencia_lib.py`.
6. **Metas documentales** (por cumplir, no cumplidas): mediana de T1 con `.mini` ≤ 30 minutos y SUS ≥ 70 con
   al menos 8 participantes válidos; además, al menos 80 % de tareas logradas sin ayuda (criterio operativo
   propuesto, no un resultado).

## Qué falta para empezar (resumen; detalle en `estado.json`)

* Aprobación institucional del consentimiento y el manejo de datos.
* Fijar la versión lingüística del SUS en español y las decisiones del protocolo (sección 1, punto 5).
* Reclutar personas reales: 2 pilotos y al menos 8 participantes válidos.
* V6a: acreditar CIMA/SIMA (incluida su independencia del equipo) y conseguir un segundo sistema de otro
  dominio con mantenedor externo.

## Cómo comprobar que los materiales están sanos

```bash
PYTHONPATH=src python evidencia/v6/tareas/construir_tareas.py --verificar
PYTHONPATH=src python -m pytest -q -p no:cacheprovider tests/test_v6_tareas.py tests/test_v6_analisis.py tests/test_v6_herramienta.py
```

Las pruebas de navegador (Playwright) se omiten si Playwright o Chromium no están instalados; el resto se
ejecuta con solo Python y Node.
