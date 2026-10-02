# De muestras JSON a un flujo de producción

[English](BUILD_GUIDE.md) · [Perfil de dominio](DOMAIN_PROFILE.es.md)

## 1. Instala localmente

Descomprime el ZIP de la sección Descargas. Con Python 3.9 o posterior:

```sh
python -m pip install --no-index mini_format-1.2.3-py3-none-any.whl
mini build examples/phones.json examples/phones-extra.json --prefix phone --out .mini
```

El constructor lee archivos locales: no envía muestras a modelos ni servicios
externos. No requiere API key, Git ni repositorio remoto. No sobrescribe una
carpeta de salida que ya contenga archivos.

## 2. Entrega muestras representativas

Usa documentos JSON completos, sin quitar metadatos. Incluye campos opcionales,
null, listas vacías, Unicode, distintos valores numéricos y objetos anidados.
El orden de aparición determina las columnas. Un miembro ausente no equivale a
`null`, `false`, `0` ni `""`.

Una lista raíz se considera una colección de registros. Si hay varias listas
dentro de un objeto, se elige la colección de objetos con más registros sumados
entre las muestras, entre las rutas presentes en todas ellas. Puedes indicar
cuál necesitas:

```sh
mini build primero.json segundo.json --prefix product --records /data/products --out .mini-products
```

`--records` usa JSON Pointer por miembros de objetos (`~1` para `/`, `~0` para `~`).
Los metadatos del envoltorio y las listas anidadas se conservan. Un escalar u objeto
sin colección seleccionada también funciona, como documento de un registro.

## 3. Conserva el paquete generado completo

| Archivo | Función |
|---|---|
| `contract.json` | Esquema posicional, colección elegida y huella del contrato |
| `schema.json` | JSON Schema 2020-12 para otros validadores |
| `prompt.en.md`, `prompt.es.md` | Instrucciones para la IA y ejemplo pequeño |
| `parser.py` | Codificador, parser estricto, diagnóstico y reparación selectiva |
| `validator.py`, `repair.py` | Comandos directos de validación y reparación segura |
| `example.json`, `example.mini` | Ejemplos equivalentes de entrada y salida |
| `manifest.json` | Cantidades de muestras, nombres y huellas SHA-256 de archivos |

Revisa los ejemplos y prompts antes de compartirlos: pueden contener tus datos
privados. Conserva el contrato correspondiente junto al parser. Su huella detecta
contratos distintos por accidente; no es un mecanismo de autenticación.

## 4. Integra tu modelo

Añade `prompt.es.md` o `prompt.en.md` a las instrucciones del modelo junto con tu
tarea original. Indica cantidad esperada de registros y reglas del negocio.
Recibe texto `.mini` y conviértelo con el parser generado:

```sh
python .mini/parser.py decode respuesta.mini --out respuesta.json
python .mini/validator.py respuesta.mini
```

El parser sólo usa la biblioteca estándar de Python: la máquina receptora no
necesita instalar mini-format. Para integrarlo como módulo:

```python
import importlib.util
from pathlib import Path

spec = importlib.util.spec_from_file_location("phone_parser", ".mini/parser.py")
parser = importlib.util.module_from_spec(spec)
spec.loader.exec_module(parser)
texto = Path("respuesta.mini").read_text(encoding="utf-8")
datos = parser.loads(texto)  # lanza DomainError si falla; no devuelve JSON inválido
```

Antes de pagar llamadas al modelo, prueba la conversión con tus propios JSON:

```sh
python .mini/parser.py encode entrada.json --out entrada.mini
python .mini/parser.py decode entrada.mini --out restaurado.json
```

## 5. Detecta y repara sin inventar

```sh
python .mini/parser.py diagnose respuesta.mini
python .mini/repair.py respuesta.mini --out reparada.mini
```

La reparación automática elimina BOM UTF-8, normaliza CRLF y retira un bloque
Markdown completo. No inventa campos, no decide valores del negocio y no descarta
registros silenciosamente. Si falla, termina con error y no escribe un archivo de
salida. El diagnóstico identifica líneas físicas, errores y registros recuperables.

Si quedan líneas inválidas, entrega `repair_prompt`, la tarea original, respuesta
y contrato al modelo o a una persona. Guarda el mapa JSON de números de línea y
registros `.mini` corregidos en `correcciones.json`:

```sh
python .mini/parser.py apply respuesta.mini correcciones.json --out corregida.mini
```

Sólo pueden cambiar las líneas diagnosticadas como inválidas. El documento entero
se valida antes de escribirlo. Un fallo de cabecera o contrato exige revisar la
respuesta completa. `--fix-count` acepta explícitamente los registros presentes;
no demuestra que una respuesta truncada esté completa.

Códigos de salida: `0` éxito; `1` diagnóstico inválido o reparación pendiente;
`2` error de entrada, contrato o comando. Usa `--out` para escribir UTF-8 sin
problemas de redirección en Windows.

## 6. Evoluciona y mide

Los campos desconocidos en objetos inferidos o tipos incompatibles producen un error claro. Reconstruye
en otra carpeta con las muestras antiguas y nuevas; actualiza prompt y parser
juntos. Campos sólo null o de tipos mezclados permanecen como JSON abierto porque
las muestras no permiten deducir un tipo más estrecho. Las muestras enseñan
estructura, no reglas como límites de stock, IDs únicos o exactitud semántica.

Un objeto vacío queda cerrado y sin miembros conocidos: incluye muestras con
sus campos previstos antes de usar objetos poblados. Una lista observada sólo
vacía admite elementos JSON abiertos; un nodo de tipos mezclados admite cualquier
JSON, no únicamente los tipos observados. Revisa `schema.json` para comprobar
si esa flexibilidad coincide con la validación que necesita tu aplicación.

Compara con tu mejor formato usando el tokenizador real y la solicitud completa:
coste del prompt/esquema reutilizable más salida generada. Mide exactitud del
modelo, reintentos y latencia en tu integración. El benchmark público demuestra
eficiencia de serialización, no generación perfecta por cualquier modelo.

El perfil generado `mini-domain/1` usa el toolkit Python. El núcleo TypeScript y
el navegador soportan las catorce familias SPEC 1.1; no les pases archivos del
perfil generado. Consulta la [compatibilidad](DOMAIN_PROFILE.es.md).
