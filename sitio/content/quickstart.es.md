# De tu JSON a un flujo con .mini

Una aplicación de soporte recibe mensajes. La IA extrae un ticket por mensaje. La aplicación necesita **JSON** para guardar y asignar los tickets; `.mini` reduce la repetición en la respuesta de la IA y después se convierte a ese mismo JSON.

[Mira primero el caso de 20 tickets](/flujo/). Puedes repetirlo sin API key y ver qué se validó y reparó.

## 1. Instala y abre el asistente

[Descarga el paquete](/downloads/mini-format-1.3.0.zip) y extráelo. Desde esa carpeta:

```sh
python -m pip install --no-index mini_format-1.3.0-py3-none-any.whl
mini setup
```

El asistente pregunta primero **español o inglés**. Después puedes elegir un JSON que tu IA ya haya generado, definir tus campos o usar el ejemplo de tickets. Tu muestra debe incluir los campos y tipos que espera la aplicación; añade muestras si tienes campos opcionales o estructuras diferentes.

Elige un nombre y una carpeta nueva, por ejemplo `.mini`. El contrato define los campos y tipos; el prompt indica a la IA cómo devolverlos. No necesitas escribir ninguno a mano.

## 2. Prueba antes de integrar

Abre `.mini/try-prompt.md` y copia su **contenido** a tu IA. Ya incluye el formato en el idioma elegido y pide 20 registros ficticios del mismo caso. Una ruta sola no enseña las instrucciones a la IA.

Guarda la respuesta como `response.mini`. Compruébala:

```sh
python .mini/validator.py response.mini
```

Puede salir bien a la primera. Si hay errores, Repair elimina envoltorios Markdown, BOM y saltos de línea de Windows. Para un tipo incorrecto o datos ausentes, hay que pedir una corrección a la IA.

```sh
python .mini/repair.py response.mini --out corrected.mini
```

Si Repair informa de errores pendientes, revisa sus diagnósticos: no ha producido una respuesta utilizable. [El ejemplo completo](/flujo/) muestra cómo el flujo pide a la IA sólo la línea incorrecta y comprueba otra vez el resultado.

## 3. Conecta el flujo de tu aplicación

Elige **Integración** dentro de `mini setup`, o ejecuta:

```sh
mini integrate ruta/a/tu/app.py --bundle .mini --lang es
```

Localiza la llamada que pide JSON. Prepara `integration/INTEGRATE.md` con las rutas del contrato y del prompt y, si el código es compatible, un diff. Para aplicar el patrón Python síncrono de chat completions seguido de `json.loads`, añade `--apply`; conserva una copia del archivo original.

Para otros SDK, código asíncrono o lenguajes, entrega la guía a tu IA de código. Debe leer el prompt generado, cambiar el formato de salida de la llamada y conectar el callback a `Workflow.run`. Si tu API fuerza respuestas JSON, desactiva ese modo para recibir .mini.

**El recorrido completo:** tu tarea → IA → .mini → validar → Repair → corrección de IA si hace falta → volver a validar → JSON. La aplicación recibe datos sólo si la respuesta entera es válida. Puedes exigir el número de registros esperado para bloquear lotes incompletos.

[Ver código de integración](/docs/build/).

## 4. Repite una ejecución completa

Desde la carpeta del paquete:

```sh
python examples/flujo-soporte/run.py
```

Hay 20 mensajes, una respuesta .mini guardada y una corrección de una línea. El flujo real entrega `output/soporte/result.json` y guarda `history.json`. Las respuestas son ilustrativas, escritas por Muse; los fallos se introdujeron para enseñar Repair, no para medir la fiabilidad de una IA.

Para el formulario local con modo grabado y modo IA real:

```sh
python examples/flujo-soporte/run.py --serve
```

Abre la dirección que imprime. El formulario pide API key y modelo sólo al elegir una IA real. La clave se usa en memoria y no va al historial. Las llamadas reales y las correcciones tienen coste. Puedes conservar tu proveedor al integrar tu propia función.

## ¿Y el ahorro?

El resultado de estos 20 tickets usa 443 tokens JSON, 304 TOON y 278 .mini con `o200k_base`. El prompt .mini tiene 571 tokens; los reintentos se cuentan aparte. Menos salida no demuestra por sí sola menor coste total, sobre todo con lotes pequeños. [Explorar costes](/economia/).

<details><summary>Ya conozco .mini: alternativas por comando y referencias</summary>

`mini build muestra.json --prefix ticket --out .mini --lang es` crea el mismo toolkit sin asistente. Puedes pasar varias muestras. Si ya tienes un JSON Schema, consulta `mini from-schema --help` y el [perfil base](/docs/spec/).

Las [14 familias de muestra](/docs/forks/) son opcionales. El [playground](/playground/) sirve para practicar el formato base. El toolkit generado usa Python; [Node/TypeScript](/docs/typescript/) implementa el perfil base SPEC 1.1.

</details>
