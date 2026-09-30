# Herramienta de sesión de V6b (`sesion.html`)

Un solo archivo HTML con JavaScript propio, **sin dependencias y sin conexión**: se abre con doble clic
(`file://`). Nada sale del navegador: no hay servidor ni peticiones de red (la página lo impide con una política
de contenido `connect-src 'none'`). **No contiene datos de participantes**; lo que se registra vive solo en este
navegador hasta que se exporta.

## Qué hace

1. **Participante**: código seudónimo (`EST-nn` o `PIL-nn`; rechaza nombres), perfil, lenguaje, entorno, y
   asignación por contrabalanceo. La asignación usa el mismo algoritmo que
   `python tools/analizar_v6.py contrabalanceo`; una prueba comprueba que dan el mismo plan para muchas
   semillas y tamaños. Hay que marcar que el consentimiento existe (solo se marca, no se guarda ninguna
   firma) o declarar una sesión de ensayo.
2. **Tareas**: un cronómetro por tarea con su tope (30, 30, 15, 10 y 15 minutos). Cuenta solo el tiempo
   activo (pausar detiene el reloj), se cierra solo al llegar al tope como **tiempo agotado** (que no es éxito) y
   no permite marcar éxito pasado el tope. Registra ayudas del observador, código de error y notas, y permite
   cerrar como lograda, entrega que no cumple o abandono. Las tareas siguen el orden del plan y solo una corre
   a la vez.
3. **SUS**: diez ítems en el original de Brooke (1996) o en la traducción **provisional** del equipo.
4. **Incidentes** y marca de sesión no válida con motivo.
5. **Exportar**: JSON (con el registro de eventos) y CSV, en la forma que lee `tools/analizar_v6.py`; importar
   una sesión guardada; **borrar** la sesión del navegador (pide confirmación).

## Uso

Sigue `../protocolo.md` (secciones 4 a 7). Resumen: abrir, escribir el código, generar el plan con la semilla
fijada, «Aplicar al código indicado», marcar el consentimiento, **Comenzar sesión**, conducir las tareas,
SUS, exportar, borrar. Guarda los archivos en `evidencia/restringida/v6/sesiones/`.

## Garantías y límites

* Guarda un latido cada segundo en `localStorage` de este navegador. Si se recarga la página con una tarea en
  curso, queda **en pausa** con lo contado hasta el último latido (se puede perder como mucho 1 segundo).
  Si el navegador bloquea el almacenamiento, la herramienta funciona pero avisa de que hay que exportar.
* No verifica entregas: eso lo hace `../tareas/verificar_entrega.py`. El observador decide con su resultado.
* Accesible: estructura con encabezados, controles con etiquetas, foco visible, cronómetros con `role="timer"`
  y avisos de tiempo agotado en una región viva. Iconos en SVG con `currentColor`; ningún emoji. Usa los
  tokens de color del sitio y respeta el tema claro u oscuro del sistema.
* Se probó con Chromium (Playwright) y con el núcleo en Node, en `tests/test_v6_herramienta.py`. No se probó en
  Firefox ni en Safari.
