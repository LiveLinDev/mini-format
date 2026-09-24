# V8 · Integración en SIMA con un modelo comercial

Mediciones reales de la integración de mini-format en [SIMA](https://github.com/LiveLinDev/SIMAApp), la plataforma
que genera bancos de preguntas a partir de clases universitarias. Todas las ejecuciones usaron `deepseek-chat`
(API de DeepSeek) el 21 de septiembre de 2026, con el límite de salida de SIMA de 4 000 tokens por llamada y el
contrato `a` (ítems de evaluación) de mini-format 1.2.1. Es el experimento que cita el short paper (sección VI).

| Archivo | Contenido |
|---|---|
| `datos.json` | datos crudos: comparaciones pareadas y clases completas, con las respuestas del modelo tal como llegaron |
| `analizar.py` | resume `datos.json` y dibuja la figura; `python experiments/v8_sima/analizar.py` |
| `resumen.json` | cifras usadas en el artículo |
| `fig_json_vs_mini.png` | Fig. 2 del artículo |

## Comparación pareada (`comparaciones`)

El primer bloque de una clase (1 154 palabras) se envía dos veces en paralelo con el prompt de generación real de
SIMA: una pidiendo .mini y otra JSON. Solo cambia la sección de formato; el ejemplo JSON es compacto, un ítem por
línea, para no inflar su costo. Los tokens son los que informa el proveedor. Ninguna respuesta se repara.

| Preguntas | Corridas | Salida .mini | Salida JSON | Utilizables .mini | Utilizables JSON |
|---|---|---|---|---|---|
| 12 | 2 | 1 061 · 1 037 | 1 655 · 1 623 | 12 · 12 | 12 · 12 |
| 40 | 1 | 3 489 | 4 000 (cortada) | 38 | 0 |

Con 40 preguntas la respuesta JSON llegó al límite, quedó incompleta y no se pudo leer. En .mini, las dos preguntas
rechazadas (E13, número fuera de rango) quedaron identificadas por línea.

## Clases completas (`clases`)

Cinco ejecuciones completas de dos clases (2 856 y 11 725 palabras) con el lector mini-format: 350 preguntas pedidas
en 38 llamadas, 343 válidas al llegar, 7 líneas rechazadas (5 E07, 2 E05), 5 reparadas reenviando solo esa línea y
las otras pedidas como faltantes; se entregaron las 350. El lector anterior de SIMA habría aceptado las 7 sin aviso.
Los bancos ocupan entre 30,6 % y 32,8 % menos tokens en .mini que los mismos ítems en JSON compacto (`o200k_base`).

Las ejecuciones 3 y 5 son anteriores al registro de la respuesta cruda por bloque, por eso sus `bloques` no traen el
campo `respuesta`. La reproducción en vivo está en https://mini-format.pmoluna.com/sima/ («SIMA en vivo» y
«JSON frente a .mini, en vivo»), que llama a la API de SIMA (`learning/views/demo_api.py`).
