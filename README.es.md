# .mini: tu IA responde más corto; tu aplicación recibe JSON

Si tu aplicación pide listas de datos a una IA, `.mini` puede reducir los tokens de esa respuesta. El contrato define los campos una vez; la IA devuelve los valores en un formato compacto. El flujo valida, repara y convierte el resultado al JSON que tu aplicación usa.

**Un caso:** convertir 20 mensajes de soporte en 20 tickets con asunto, categoría y prioridad. Hace falta JSON para guardar, filtrar y asignar los tickets. [Mira el flujo completo](https://mini-format.pmoluna.com/flujo/): entrada, respuesta, corrección e historial.

En ese ejemplo, el mismo resultado consume 443 tokens en JSON, 304 en TOON y 278 en .mini (`o200k_base`). Es una comparación de salida. El prompt .mini tiene 571 tokens y las correcciones también consumen tokens; mide el coste completo antes de atribuir un ahorro de dinero.

## Empieza aquí

[Descarga y extrae el paquete](https://mini-format.pmoluna.com/downloads/mini-format-1.3.0.zip). Desde la carpeta extraída:

```sh
python -m pip install --no-index mini_format-1.3.0-py3-none-any.whl
mini setup
```

El asistente te guía:

1. Español o inglés.
2. Un JSON de ejemplo de tu IA, tus propios campos o el caso de soporte incluido.
3. Nombre y carpeta: genera contrato, prompt, validador, Repair y `workflow.py`.
4. Prueba: pide 20 registros ficticios a tu IA con el prompt generado y valida la respuesta.
5. Integración: localiza la llamada a IA de tu proyecto y prepara la conexión al flujo.

La edición automática cubre un patrón Python síncrono de chat completions + `json.loads`. Otros SDK o lenguajes reciben una guía para tu IA de código, con las rutas reales. `Workflow.run` acepta cualquier callback síncrono que reciba un prompt y devuelva texto; también hay una entrada por CLI para otros lenguajes.

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
