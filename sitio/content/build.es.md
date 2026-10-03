# Conecta .mini a tu llamada a IA

Empieza con [mini setup](https://mini-format.pmoluna.com/docs/quickstart/): idioma, JSON de muestra, nombre y carpeta. El toolkit contiene contrato, prompts y un flujo Python portátil, sin dependencias externas.

## Desde el asistente o por comando

En `mini setup`, elige **Elegir mi archivo** para señalar el código que llama a la IA, o **Buscar en mi proyecto** para localizarlo. Puedes revisar el cambio propuesto o conectar Python compatible con una copia del original. Si eliges **Todavía no tengo un flujo**, el kit conserva el comando para retomarlo en `README.md` y `GUIA.md`.

Cuando tengas el archivo, también puedes conectarlo con:

```sh
mini integrate app.py --bundle .mini --lang es
```

Localiza llamadas de IA y lecturas JSON. Escribe `integration/INTEGRATE.md` con las rutas reales y, para código compatible, `change.diff`. Para aplicarlo, repite el comando con `--apply`.

La edición automática reconoce una llamada Python síncrona `client.chat.completions.create(...)`, asignada a una variable, seguida de `json.loads(response.choices[0].message.content)`. La respuesta no debe tener otros usos. Conserva cliente, modelo, mensajes y parámetros; elimina `response_format`, lee el prompt generado y conecta el flujo. Guarda el original en `integration/app.py.before` y crea un puente junto al archivo.

Otros SDK, lenguajes, streaming, herramientas o funciones asíncronas reciben una guía para tu IA de código: requieren adaptar el callback o el puente al flujo real.

## Con tu proveedor: un callback

Una función recibe un prompt y devuelve texto. Usa la llamada a IA de tu aplicación, sin forzar salida JSON:

```python
import importlib.util
from pathlib import Path

bundle = Path('.mini').resolve()
spec = importlib.util.spec_from_file_location('my_mini_flow', bundle / 'workflow.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
flow = module.Workflow(bundle, lang='es')

def generate(prompt):
    response = client.chat.completions.create(
        model=model,
        messages=[{'role': 'user', 'content': prompt}],
    )
    return response.choices[0].message.content

data = flow.run(generate, task, expected_records=20)
# data: los datos JSON-compatible de tu aplicación.
# flow.last_run: respuesta, diagnósticos, corrección y resultado.
```

`task` contiene los datos de entrada y la tarea. La clave y la configuración siguen en tu aplicación. El callback se usa para generar y corregir; incluye las instrucciones de negocio necesarias en ambas llamadas.

## Qué hace el flujo

1. Lee `prompt.es.md` y lo añade a la tarea.
2. Obtiene .mini de la IA y lo valida.
3. Repair elimina envoltorios, BOM y CRLF seguros.
4. Pide al mismo callback las líneas incorrectas; conserva las correctas. Los errores de cabecera o recuento requieren regenerar el documento completo.
5. Vuelve a validar y comprueba `expected_records` si lo indicas.
6. El parser devuelve JSON sólo si todo es válido.

Por defecto hay como máximo una corrección. `max_repairs=0` la desactiva. Si aún falla, lanza `WorkflowError`; el informe está en `error.report` y `flow.last_run`. No inventa datos ni reduce el recuento esperado. La validación comprueba estructura y tipos, no la veracidad de la interpretación de la IA.

## Código asíncrono y Node

En Python, usa `await flow.run_async(generate, task, expected_records=20)` con tu callback asíncrono.

En Node, importa `Workflow` de `./.mini/workflow.mjs` y llama `await new Workflow().run(generate, task, {expectedRecords: 20})`. El callback puede usar cualquier SDK. El puente ejecuta el mismo runtime Python generado; necesita Python disponible. Valida, repara, pide una corrección y entrega JSON. `lastRun` contiene el historial.

## Desde otro lenguaje

Pasa texto por stdin a `python .mini/workflow.py -`. Código 0: JSON por stdout. Código 1: historial y diagnósticos por stderr. El llamador conecta los reintentos semánticos a su proveedor; este comando sólo repara envoltorios y convierte, sin llamadas a IA.

```sh
python .mini/workflow.py response.mini --out result.json --expected-records 20
```

`--history archivo.json` guarda el recorrido si lo deseas. Puede contener datos de tu aplicación; no incluye la API key porque el runtime nunca la recibe.

## Prueba reproducible

`python examples/flujo-soporte/run.py` repite los 20 tickets ilustrativos y su corrección con las herramientas reales. `--serve` abre el formulario local, con opción de IA real y API key en memoria. [Ver el historial](https://mini-format.pmoluna.com/flujo/).

Si cambian los datos, reconstruye en una carpeta nueva con muestras representativas: `mini build muestra.json otra.json --prefix ticket --out .mini-v2 --lang es`. No edites el contrato a mano. Una muestra no demuestra reglas que nunca observó.

El perfil generado es `mini-domain/1` y usa su propio parser Python. Las bibliotecas base Python/TypeScript siguen SPEC 1.1. Las familias son opcionales. [Referencia de dominio](/docs/profile/).
