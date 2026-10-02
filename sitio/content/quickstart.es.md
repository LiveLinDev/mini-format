# Inicio rápido

Construye una vez el toolkit de tu dominio. Después, coloca su prompt en tu flujo de IA y convierte cada respuesta `.mini` de vuelta al JSON que consume tu aplicación.

## 1. Instalar

[Descargar toolkit 1.2.3 (.zip)](/downloads/mini-format-1.2.3.zip) · [Paquete Python (.whl)](/downloads/mini_format-1.2.3-py3-none-any.whl) · [Código fuente (.zip)](/downloads/mini-format-1.2.3-source.zip)

Requiere Python 3.9 o posterior. El núcleo y el toolkit generado usan la biblioteca estándar.

```bash
pip install https://mini-format.pmoluna.com/downloads/mini_format-1.2.3-py3-none-any.whl
mini setup
```

El asistente te pregunta si ya tienes un archivo de datos (JSON, CSV, TSV o XML) o si prefieres definir los campos allí mismo. Crea la carpeta `.mini/` y una `GUIA.md` con los pasos para pedir, validar y convertir respuestas. Para automatizar la creación sin preguntas, usa `mini build` como se explica abajo. `mini init` y `mini` en una terminal siguen abriendo el mismo asistente.

Para instalar sin conexión, descarga el ZIP, extráelo y ejecuta `pip install` sobre el archivo `.whl` incluido. Con Node 22.6 o posterior, instala el paquete del perfil base: `npm install ./mini-format-core-1.2.3.tgz`. Puedes [descargarlo por separado](/downloads/mini-format-core-1.2.3.tgz). El toolkit de dominio generado es Python; las bibliotecas TypeScript y JavaScript implementan el perfil base.

Si ya completaste `mini setup`, tu carpeta está lista: puedes continuar en **4. Integrar**. Los pasos 2 y 3 explican la alternativa por comando.

## 2. Opcional: construir desde muestras por comando

Guarda esto como `phones.json`:

```json
[
  {"id": 1, "brand": "Acme", "model": "One", "price": 299, "available": true},
  {"id": 2, "brand": "Acme", "model": "Pro", "price": 499, "available": false}
]
```

Incluye en archivos adicionales ejemplos de campos opcionales, listas, objetos anidados y valores nulos. La diversidad de casos importa más que repetir la misma muestra.

## 3. Crear tu .mini

```bash
mini build phones.json --prefix phone --out .mini
```

Para combinar muestras: `mini build phones.json more-phones.json --prefix phone --out .mini`.

La carpeta `.mini` contiene el contrato, el esquema JSON, prompts en ambos idiomas, parser, validador, reparación, ejemplos y manifiesto. Lee [Crear tu toolkit](/docs/build/) para conocer el perfil generado y sus reglas.

## 3b. ¿Tu aplicación ya tiene un JSON Schema?

Entonces no necesitas reunir muestras: el contrato se genera desde el esquema en un solo comando, sin carpeta de salida.

```bash
mini from-schema ticket.schema.json -p tk --out contrato_tk.json
mini to-schema contrato_tk.json
mini prompt --contract contrato_tk.json --lang es
mini validate respuesta.mini --contract contrato_tk.json
mini diagnose respuesta.mini --contract contrato_tk.json
```

Con un modelo Pydantic: `mini from-schema --pydantic modelos:Ticket -p tk --out contrato_tk.json`. El contrato resultante sigue el perfil base SPEC 1.1 y se usa con la biblioteca:

```python
from minifmt import Contract, parse, spec_block
from minifmt.ai import merge_repair, repair_request

contrato = Contract.load("contrato_tk.json")

# bloque de formato que se añade al prompt del modelo
instruccion = spec_block(contrato, "es")

# registros válidos y errores con su código y su línea
documento = parse(respuesta, contrato, strict=False)

# reenvía al modelo solo las líneas inválidas y fusiona la corrección
solicitud = repair_request(respuesta, contrato, "es")
fusion = merge_repair(respuesta, correccion, contrato, solicitud)
```

## 4. Integrar

Usa `.mini/prompt.es.md` como instrucción de formato para tu modelo. Guarda su respuesta en `response.mini`.

```bash
python .mini/validator.py response.mini
python .mini/parser.py decode response.mini
```

El segundo comando imprime el JSON reconstruido. También puedes usar `loads(texto)` y `dumps(objeto)` al importar el módulo generado `parser.py` desde tu aplicación.

## 5. Detectar y reparar

```bash
python .mini/parser.py diagnose response.mini
python .mini/repair.py response.mini --out corrected.mini
```

La reparación normaliza envoltorios y saltos de línea seguros. Nunca inventa valores que faltan. Cambiar el recuento declarado exige `--fix-count`; úsalo solo si has comprobado que el lote recibido está completo. Los errores semánticos necesitan una corrección de tu aplicación o un reintento del modelo.

## Familias de muestra opcionales

Puedes descargar [14 contratos de muestra](/docs/forks/) para estudiarlos. No se instalan con Python o Node: tu `.mini` se construye con tus propios datos. Tras extraer el ZIP, usa `mini --forks forks forks` para listarlos.

El [playground](/playground/) incluye un ejemplo de tickets y permite probar el perfil base sin instalar nada. Mira también los [ejemplos explicados](/ejemplo/).
