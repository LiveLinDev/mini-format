# Optimización: perfil general frente a perfil especializado

Un dominio por carpeta. Todo lo de aquí lo **regenera** `python tools/ejecutar_opt.py` con las herramientas reales
(`mini from-schema`, `spec_block`, `mini build`/`make_prompt`, `dumps`); una prueba comprueba que lo versionado coincide.
Las «respuestas» son la serialización determinista de los datos de referencia, **no salida de un modelo**.

| Carpeta | Caso | Datos de referencia |
|---|---|---|
| `tickets/` | **representativo** | los 10 tickets del hilo de «Cómo funciona» (`examples/mesa-de-ayuda`, procedencia `asistido_ia` no verificable) |
| `eventos/` | **FAVORABLE** (diseñado con esa forma; no es promesa general) | 10 eventos sintéticos deterministas |
| `comentarios/` | **ahorro pequeño** (texto libre largo) | 5 comentarios públicos de JSONPlaceholder (MIT) |

Cada carpeta trae: `esquema.json` (el de la aplicación), `contrato_general.json`, `contrato_dominio.json` (`mini build`),
`contrato_especializado.json`, `mapa.json` (el mapa explícito: vive en la aplicación), las instrucciones
(`instruccion_*.txt`, sin y con ejemplo), las respuestas (`respuesta_*.json|mini`) y `datos_originales.json`.

Decodificar con el mapa, sin importar nada de `experiments/`:

```bash
python examples/optimizacion/reconstruir.py tickets
```

Las cifras, el criterio y el diseño están en [`experiments/optimizacion/README.md`](../../experiments/optimizacion/README.md).
