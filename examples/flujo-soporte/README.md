# Un flujo que entrega JSON

Una aplicación recibe mensajes de soporte. La IA debe extraer un ticket por mensaje para que la aplicación pueda guardarlo, filtrarlo y asignarlo: texto libre no sirve para ese paso.

Instala el paquete descargado y ejecuta:

```sh
python examples/flujo-soporte/run.py
```

Se repite una respuesta ilustrativa escrita por Muse con 20 tickets. Contiene un envoltorio Markdown y un tipo incorrecto introducidos para enseñar la reparación; no es una llamada real ni una medida de la frecuencia de errores. El flujo usa el contrato real: valida, quita el envoltorio, pide la corrección guardada de una línea, conserva las demás, vuelve a validar y entrega `result.json`. El historial queda en `output/soporte/history.json`.

Para verlo como formulario local:

```sh
python examples/flujo-soporte/run.py --serve
```

Abre la dirección que imprime. Puedes repetir la grabación sin clave o desplegar el formulario de IA real. La clave se envía al servidor local y de allí a OpenAI por HTTPS, sólo se mantiene en memoria y no se guarda en el historial. No pegues una clave en la web pública. La llamada real y un posible reintento tienen el coste de tu proveedor.

`messages.json` contiene la entrada. `expected.json` contiene los 20 tickets. `raw.mini` y `correction.json` guardan las respuestas ilustrativas. `history.json` registra el recorrido completo y `comparison.json` cuenta los tokens del mismo resultado en JSON, TOON y .mini. La comparación es de salida: el prompt y los reintentos se muestran aparte y también pueden tener coste.

Para tu aplicación, usa `mini setup` o `mini integrate archivo.py --bundle .mini`. El callback de `Workflow.run` conserva tu proveedor. La edición automática admite un patrón Python síncrono de chat completions + `json.loads`; otros flujos reciben una guía concreta para tu IA de código.

En un checkout del código fuente, `python examples/flujo-soporte/measure.py` repite los conteos con el tokenizador y el encoder TOON del repositorio, sin llamadas a IA.
