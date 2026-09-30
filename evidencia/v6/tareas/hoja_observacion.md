# Hoja de observación de V6b (una por participante)

**Formato en blanco: no contiene datos.** Es la versión en papel de lo que registra
`herramienta/sesion.html` (Plan de Validación v3, anexo A.2 y tabla T11). Se identifica a la persona **solo**
por su código seudónimo (`EST-nn` o `PIL-nn`). No escribas nombres, correos ni detalles que la identifiquen.
Las notas describen hechos, no juicios sobre la persona: se evalúa el componente, no su capacidad.

| Campo | Registro |
|---|---|
| Código de participante / tipo | ________________ / Piloto o Estudio |
| Sesión de ensayo (no es un participante) | Sí / No |
| Fecha (UTC) y hora de inicio / fin | ________________ / ________ / ________ |
| Perfil | Estudiante de últimos ciclos / Desarrollador en ejercicio / Otro |
| Experiencia y entorno | Lenguaje: ____________ · Experiencia en APIs: ____________ · SO y versión: ____________ |
| Secuencia asignada (plan) y orden de T1 | S1 S2 S3 S4 · JSON y luego .mini / .mini y luego JSON · JSON con variante A / B |
| Consentimiento confirmado (existe en el formulario institucional, aparte) | Sí / No |
| Elegibilidad confirmada (mayor de edad; no autor ni asesor; sin experiencia previa con mini-format) | Sí / No |
| Versión de mini-format, hash del paquete y guía entregada | ________________________________ |
| Versión lingüística del SUS usada | Original en inglés / Español provisional / Español autorizada: ______ |

## Tareas

Copia este bloque por tarea. Tiempo activo = el del cronómetro (sin pausas).

| Campo | T1 JSON | T1 .mini | T2 | T3 | T4 |
|---|---|---|---|---|---|
| Variante (solo T1) | A / B | A / B | no aplica | no aplica | no aplica |
| Inicio / fin (hora) | ____ / ____ | ____ / ____ | ____ / ____ | ____ / ____ | ____ / ____ |
| Tiempo activo (mm:ss) | ______ | ______ | ______ | ______ | ______ |
| Pausas (n.º y motivo) | ______ | ______ | ______ | ______ | ______ |
| Veces que dijo «listo» sin cumplir | ____ | ____ | ____ | ____ | ____ |
| Resultado | Completa sin ayuda / con ayuda / tiempo agotado / no completa / abandono | igual | igual | igual | igual |
| Ayudas (n.º, minuto y qué se dijo) | ______ | ______ | ______ | ______ | ______ |
| Código de error observado | ______ | ______ | ______ | ______ | ______ |
| Verificador: cumple (Sí / No) | ____ | ____ | ____ | ____ | ____ |
| Observación (hechos) | ______ | ______ | ______ | ______ | ______ |

Reglas de marcado:

* **Completa sin ayuda / con ayuda**: solo si el verificador dijo que cumple. Con ayuda si hubo al menos una ayuda registrada.
* **Tiempo agotado**: se cerró por el tope. No es éxito. No anotes «30 minutos» como si hubiera terminado.
* **No completa**: entregó algo que no cumple y no quiso o no pudo seguir. **Abandono**: no entregó y decidió no continuar.
* **Ayuda**: cualquier información que oriente la solución más allá de repetir el enunciado textualmente.

## Incidentes

| Problema | Severidad | Paso o tarea | Efecto | Evidencia (código de error, archivo) |
|---|---|---|---|---|
| | | | | |
| | | | | |

## Cuestionario SUS y cierre

| Campo | Registro |
|---|---|
| SUS completo (10 ítems respondidos) | Sí / No. Si no, ítems que faltan: ______ |
| SUS aplicado antes de comentar opiniones | Sí / No |
| Sesión válida para el estudio | Sí / No. Si no, motivo: ________________________ |
| Se exportaron JSON y CSV a `evidencia/restringida/v6/sesiones/` | Sí / No |
| Se borró la sesión del navegador | Sí / No |

Guarda esta hoja con el código, no con el nombre, en `evidencia/restringida/v6/` (git la ignora).
