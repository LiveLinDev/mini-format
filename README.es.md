# mini-format

Crea un formato de salida compacto para los JSON de tu dominio. Entrega muestras
representativas una vez y obtén contrato, prompts, parser, validador y herramientas
de reparación. Pide `.mini` a la IA y recupera la estructura JSON original.

[Sitio](https://mini-format.pmoluna.com) · [Documentación](https://mini-format.pmoluna.com/docs/) · [Descargas](https://mini-format.pmoluna.com/downloads/) · [English](README.md)

## Descargar e instalar

Descarga el [kit completo](https://mini-format.pmoluna.com/downloads/mini-format-1.2.2.zip)
y descomprímelo. Necesitas Python 3.9 o posterior; el paquete se instala sin conexión
y no tiene dependencias de ejecución:

```bash
python -m pip install --no-index mini_format-1.2.2-py3-none-any.whl
mini
```

También puedes instalar directamente desde la web:

```bash
python -m pip install https://mini-format.pmoluna.com/downloads/mini_format-1.2.2-py3-none-any.whl
```

`mini` abre un asistente para partir de tus datos (JSON, CSV, TSV o XML) o definir campos sin archivo. Crea tu carpeta `.mini/` y una `GUIA.md` para empezar. Si prefieres automatizarlo, usa `mini build`.

El ZIP contiene el paquete Python, un paquete Node, ejemplos, documentación y
licencia MIT. Las [sumas SHA-256](https://mini-format.pmoluna.com/downloads/SHA256SUMS.txt)
y el [código fuente](https://mini-format.pmoluna.com/downloads/mini-format-1.2.2-source.zip)
están en la misma web. No necesitas una cuenta de GitHub.

## Construye una vez y reutiliza

`mini build` combina las muestras para reconocer orden de campos, tipos, objetos
anidados, listas y valores opcionales. Cuanto más representativas sean, más casos
cubren; las muestras no garantizan conocer todos los valores futuros del dominio.

La carpeta `.mini/` contiene el contrato, prompts en español e inglés, un parser
Python autónomo, validación, diagnóstico, reparación y ejemplos de ida y vuelta.
El sistema receptor puede ejecutar ese parser sin instalar mini-format.

```bash
mini from-json examples/phones.json --contract .mini/contract.json --out phones.mini
mini validate phones.mini --contract .mini/contract.json
mini to-json phones.mini --contract .mini/contract.json --out phones.roundtrip.json
mini diagnose phones.mini --contract .mini/contract.json
```

Incorpora el prompt a las instrucciones del modelo. La reparación corrige formato
inequívoco y prepara una regeneración dirigida para los errores restantes; no
inventa datos del negocio. Consulta la [guía de integración](BUILD_GUIDE.es.md).

## Python y TypeScript

El núcleo sirve para tus propios contratos. Los [14 contratos de muestra](https://mini-format.pmoluna.com/docs/forks/)
se descargan aparte si quieres estudiarlos o adaptarlos.

```python
from minifmt import Registry, parse, dumps
contrato = Registry.load("forks").get("a")  # solo con el ZIP opcional extraído
documento = parse(texto, contrato)
json_canonico = documento.to_canonical()
```

Node 22.6+ puede instalar el paquete ESM compilado, con tipos TypeScript:

```bash
npm install ./mini-format-core-1.2.2.tgz
```

```javascript
import { Registry, parse, createReader } from '@mini-format/core';
const contrato = Registry.load('./forks').get('a'); // ZIP opcional extraído
const documento = parse(texto, contrato);
```

La biblioteca Python ofrece además un lector incremental, la conversión entre
contratos y JSON Schema o modelos Pydantic, y un comando de comparación de tokens:

```python
from minifmt import read_records, from_json_schema, to_json_schema
for item in read_records(fragmentos, contrato):        # fragmentos str o bytes UTF-8
    procesar(item.record, item.line)                   # se emite al cerrarse su línea
contrato = from_json_schema(esquema, "tk")             # un nivel de anidación (SPEC §12)
```

```bash
mini from-schema ticket.schema.json -p tk --out contract.json
mini from-schema --pydantic modelos:Postings -p job  # pydantic es opcional
mini to-schema a --out a.schema.json
mini bench respuesta.mini --enc o200k_base --format table
```

`read_records` produce los mismos registros y errores que `parse` y no retiene los
registros, por lo que su consumo de memoria no crece con el documento. `mini bench`
informa tokens y bytes de .mini, JSON compacto e indentado, YAML, CSV aplanado y
TOON oficial, con el ahorro respecto de JSON compacto; un formato cuya dependencia
(PyYAML, Node.js o el paquete TOON incluido) no está disponible se informa como no
disponible.

`js/mini.js` ofrece la biblioteca TypeScript compilada para navegador, sin
dependencias (generada por `tools/build_js.mjs` y verificada con la suite de
conformidad). El kit de dominio generado incluye su propio runtime autónomo y el
perfil explícito `mini-domain/1`. Las familias del núcleo siguen [SPEC 1.1](SPEC.es.md),
que mantiene válido todo documento 1.0; las decisiones de diseño están en
[docs/adr](docs/adr/README.md). Consulta el [perfil de dominio](DOMAIN_PROFILE.es.md)
y el [protocolo de familias](FORKING.es.md).

## Eficiencia medida

El contrato compartido evita repetir nombres de campo. El ahorro depende de la
estructura, escapes, valores repetidos y tokenizador. El
[benchmark público](benchmark/public/README.md) compara JSON completos y reversibles
con JSON compacto e indentado, TOON oficial anidado y aplanado, YAML, XML y CSV.
Los costos del contrato y del prompt se muestran por separado. El
[benchmark original de 14 dominios](benchmark/results/summary_12.csv) sigue siendo
un experimento independiente del núcleo. Reducir tokens no demuestra por sí solo
exactitud del modelo, menor latencia ni ahorro para cualquier JSON.

## Desarrollo

Descomprime el código fuente y ejecuta:

```bash
python -m pip install -e ".[bench,release]"
python -m unittest discover -s tests
python conformance/run_python.py
node tests/test_js_port.mjs
node --experimental-strip-types --test ts/test/*.test.ts
mini check-forks
python tools/build_release.py --output dist
python sitio/construir.py
```

Construir las descargas requiere Node 22.13+. El núcleo y el parser Python generado
usan la biblioteca estándar. El extra opcional `bench` instala tokenización exacta
(`tiktoken` y respaldo local con `regex`), YAML y gráficos; `release` instala las
herramientas de empaquetado. Consulta [contribución](CONTRIBUTING.es.md) y
[cambios](CHANGELOG.md).

## Investigación y licencia

A. E. J. Palma Obispo y E. J. Palomino Santa Cruz, Universidad Peruana de Ciencias
Aplicadas, 2026. Asesores: Jorge Luis Mayta Guillermo y Ronald Mejía Tarazona.

MIT. Los vocabularios, TOON oficial 4.1.1 y datasets conservan sus licencias y la
procedencia documentada junto a cada recurso.
