# Inicio rápido

Construye una vez el toolkit de tu dominio. Después, coloca su prompt en tu flujo de IA y convierte cada respuesta `.mini` de vuelta al JSON que consume tu aplicación.

## 1. Instalar

[Descargar toolkit 1.2.0 (.zip)](/downloads/mini-format-1.2.0.zip) · [Paquete Python (.whl)](/downloads/mini_format-1.2.0-py3-none-any.whl) · [Código fuente (.zip)](/downloads/mini-format-1.2.0-source.zip)

Requiere Python 3.9 o posterior. El núcleo y el toolkit generado usan la biblioteca estándar.

```bash
pip install https://mini-format.pmoluna.com/downloads/mini_format-1.2.0-py3-none-any.whl
mini --help
```

Para instalar sin conexión, descarga el ZIP, extráelo y ejecuta `pip install` sobre el archivo `.whl` incluido. Con Node 22.6 o posterior, instala el paquete del perfil base: `npm install ./mini-format-core-1.2.0.tgz`. Puedes [descargarlo por separado](/downloads/mini-format-core-1.2.0.tgz). El toolkit de dominio generado es Python; las bibliotecas TypeScript y JavaScript implementan el perfil base.

## 2. Reunir ejemplos de tu JSON

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

## Familias incorporadas

Las 14 familias del perfil base siguen disponibles: `mini forks`, `mini prompt log --lang es` y `mini validate documento.mini`. Sus APIs están en [Python](/docs/python/), [TypeScript](/docs/typescript/) y [CLI](/docs/cli/).

El [playground](/playground/) permite explorar el perfil base y comparar formatos sin instalar nada.
