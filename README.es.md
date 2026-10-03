# .mini: reduce el texto que genera tu IA y recupera el mismo JSON

Una empresa recibe quejas y consultas. Para evitar crear tickets a mano, su aplicación pide a una IA que interprete cada mensaje y genere una ficha con asunto, categoría y prioridad. Esa ficha es un ticket; el código necesita recibirlo en **JSON** para guardarlo y asignarlo.

JSON repite los nombres de los campos en cada ticket. La API cuenta ese texto en **tokens**, fragmentos que utiliza para calcular la factura. Menos tokens en la respuesta cuestan menos con el mismo modelo y tarifa. TOON también reduce repetición; `.mini` adapta las reglas a tu dominio mediante un **contrato**: campos, orden y tipos declarados una vez. El código valida la respuesta compacta, la repara cuando puede y recupera los mismos objetos JSON.

[Sigue la automatización de soporte](https://mini-format.pmoluna.com/flujo/): 20 mensajes de clientes se convierten a 20 objetos JSON, con una ejecución guardada que puedes inspeccionar sin clave.

En ese ejemplo, el mismo resultado consume 443 tokens en JSON, 304 en TOON y 278 en .mini (`o200k_base`). Es una comparación de salida. El prompt .mini tiene 571 tokens y las correcciones también consumen tokens; mide el coste completo antes de atribuir un ahorro de dinero.

## Empieza aquí

[Descarga y extrae el paquete](https://mini-format.pmoluna.com/downloads/mini-format-1.3.1.zip). Desde la carpeta extraída:

```sh
python -m pip install --no-index mini_format-1.3.1-py3-none-any.whl
mini setup
```

El asistente te guía:

1. Español o inglés.
2. Un JSON de ejemplo de tu IA, tus propios campos o el caso de soporte incluido.
3. Nombre y carpeta: crea `contract.json` (reglas), `prompt.es.md` / `prompt.en.md` (instrucciones para la IA) y `workflow.py` (validación, Repair y conversión a JSON).
4. Integración: elige el archivo que llama a la IA, busca en tu proyecto o selecciona **Todavía no tengo un flujo**. El comando para retomarlo queda en `GUIA.md` y `README.md`.
5. Prueba: copia `try-prompt.md` a tu IA; pide 20 objetos ficticios. Comprueba la respuesta antes de guardar datos reales.

La edición automática cubre un patrón Python síncrono de chat completions + `json.loads`. Otros SDK o lenguajes reciben una guía para tu IA de código, con las rutas reales. `Workflow.run` acepta cualquier callback síncrono que reciba un prompt y devuelva texto; también hay una entrada por CLI para otros lenguajes.

Si todavía no tienes un flujo, conserva el kit. Cuando crees tu llamada a IA, ejecuta:

```sh
mini integrate ruta/a/tu/app.py --bundle .mini --lang es
```

## Prueba el flujo sin clave

```sh
python examples/flujo-soporte/run.py
```

Reproduce 20 tickets escritos por Muse con fallos introducidos para la demostración. Ejecuta las herramientas reales y guarda `output/soporte/result.json` e `history.json`. No llama a una API. Para ver el formulario local y, opcionalmente, usar una API key de OpenAI: `python examples/flujo-soporte/run.py --serve`.

## Continúa cuando lo necesites

- [Inicio rápido](https://mini-format.pmoluna.com/docs/quickstart/): desde tu JSON hasta la aplicación.
- [Integración y toolkit](BUILD_GUIDE.es.md): callback, reparación y conexión por comando.
- [Descargas](https://mini-format.pmoluna.com/downloads/): Python, Node y ejemplos.
- [Especificación](SPEC.es.md) y [perfil del toolkit](DOMAIN_PROFILE.es.md): referencia técnica.

`.mini` se adapta a tus datos. Las 14 familias son ejemplos opcionales, no una lista de casos obligatorios. El toolkit generado utiliza Python 3.9+ y su perfil `mini-domain/1`; la biblioteca Node/TypeScript implementa el perfil base SPEC 1.1. [MIT](LICENSE).
