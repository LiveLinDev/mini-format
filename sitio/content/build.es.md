# Crear tu toolkit

`mini build` convierte muestras JSON en un contrato de dominio y herramientas Python ejecutables. El contrato viaja con la aplicación y el prompt explica al modelo cómo escribir las respuestas compactas.

```bash
mini build phones.json catalog.json --prefix phone --out .mini
```

## Qué genera

| Archivo | Uso |
|---|---|
| `contract.json` | Orden de los campos, tipos, codificación y estructura del dominio. |
| `schema.json` | Esquema JSON de referencia inferido de las muestras. |
| `prompt.es.md`, `prompt.en.md` | Instrucción de formato para el modelo. |
| `parser.py` | Codifica JSON y reconstruye el JSON original desde `.mini`. |
| `validator.py` | Comprueba estructura, tipos y registros. |
| `repair.py` | Aplica correcciones seguras y entrega diagnósticos. |
| `example.json`, `example.mini` | Ejemplo verificable de ida y vuelta. |
| `manifest.json`, `README.md` | Perfil, inventario y guía de uso. |

## Muestras representativas

La inferencia descubre lo observado; no puede adivinar las reglas de tu negocio. Incluye campos ausentes y presentes, nulos, listas vacías y completas, objetos anidados y los distintos tipos que aceptas. Revisa el contrato generado antes de integrarlo. Conserva una versión del toolkit por dominio para reproducir cada respuesta.

Un campo que aparece una sola vez puede ser opcional. Que todos los ejemplos tengan el mismo valor no convierte ese valor automáticamente en una regla de negocio. Los valores frecuentes pueden codificarse de forma reversible sin prohibir valores nuevos.

## Dos perfiles explícitos

El **perfil base SPEC 1.1** mantiene las 14 familias y sus parsers Python, JavaScript y TypeScript. El **perfil generado `mini-domain/1`** añade el mapa necesario para conservar estructuras JSON y adaptar la codificación al dominio. Se usa con su `parser.py`, no con un parser del perfil base que desconozca el contrato generado.

## Ciclo de trabajo

```bash
python .mini/parser.py encode input.json
python .mini/parser.py decode response.mini
python .mini/validator.py response.mini
python .mini/parser.py diagnose response.mini
python .mini/repair.py response.mini --out corrected.mini
```

La salida de `decode` es JSON listo para la aplicación. `diagnose` explica los fallos; `repair` conserva el contenido y aplica solamente cambios deterministas. Para aceptar explícitamente el número de registros recibidos: `python .mini/repair.py response.mini --out corrected.mini --fix-count`.

Un valor semánticamente incorrecto no tiene una reparación universal: utiliza el informe y el prompt de reintento para solicitar al modelo una corrección. No descartes silenciosamente datos ni completes información desconocida.

Para aplicar correcciones por línea, guarda un objeto como `{"2": "línea .mini corregida"}` en `corrections.json` y ejecuta:

```bash
python .mini/parser.py apply response.mini corrections.json --out corrected.mini
```

Solo acepta reemplazos de líneas diagnosticadas como inválidas y vuelve a validar el documento completo antes de escribirlo.

## Medir el ahorro completo

Compara el mismo JSON y el mismo tokenizador. Cuenta tanto el prompt de contrato como las salidas y los reintentos. El contrato se amortiza al reutilizarlo; los lotes pequeños o datos sin repetición pueden no compensarlo. Consulta la [metodología](/docs/metodologia/) y repite la medida con tus muestras.
