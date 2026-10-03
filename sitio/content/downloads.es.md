# Descargar mini-format 1.3.1

El toolkit incluye todo lo necesario para crear un formato propio desde un archivo de datos o definiendo campos en el asistente. Licencia MIT; sin cuenta ni conexión a un repositorio privado.

Descarga recomendada: [paquete completo .zip](/downloads/mini-format-1.3.1.zip). Incluye el instalador, un ejemplo de 20 tickets con historial y un formulario local. Después ejecuta `mini setup`.

<details><summary>Otros paquetes y referencia técnica</summary>

| Descarga | Contenido |
|---|---|
| [Toolkit completo .zip](/downloads/mini-format-1.3.1.zip) | Paquete Python, paquete Node, ejemplos de integración, especificaciones y guías. |
| [Python .whl](/downloads/mini_format-1.3.1-py3-none-any.whl) | CLI `mini`, perfil base y constructor de toolkits. Python 3.9+. |
| [Node / TypeScript .tgz](/downloads/mini-format-core-1.3.1.tgz) | Parser, validador, serializador y streaming del perfil base. Node 22.6+. |
| [14 familias de muestra .zip](/downloads/mini-format-1.3.1-example-families.zip) | Opcionales: contratos y fixtures para estudiar o adaptar. No van en los paquetes Python y Node. |
| [Código fuente .zip](/downloads/mini-format-1.3.1-source.zip) | Implementaciones, pruebas, contratos y benchmark público reproducible. |

</details>

## Instalar Python

```bash
python -m pip install https://mini-format.pmoluna.com/downloads/mini_format-1.3.1-py3-none-any.whl
mini setup
```

`mini setup` abre el asistente: acepta JSON, CSV, TSV y XML, o te deja definir campos sin archivo. Genera una carpeta con `GUIA.md`, ejemplos, prompt, conversor y validador. Para instalar sin conexión, desde la carpeta extraída:

```bash
python -m pip install --no-index mini_format-1.3.1-py3-none-any.whl
```

## Instalar Node

Descarga el `.tgz` o extráelo del toolkit y ejecuta:

```bash
npm install ./mini-format-core-1.3.1.tgz
```

Importa la biblioteca con `import { Registry, parse } from '@mini-format/core'`. El toolkit generado de dominio utiliza Python; esta biblioteca implementa el perfil base SPEC 1.1.

## Verificar la descarga

[SHA256SUMS.txt](/downloads/SHA256SUMS.txt) contiene las huellas de los cinco paquetes. El [manifiesto JSON](/downloads/manifest.json) incluye versión, tamaño y SHA-256.

En PowerShell: `Get-FileHash .\mini-format-1.3.1.zip -Algorithm SHA256`. En Linux: `sha256sum mini-format-1.3.1.zip`. En macOS: `shasum -a 256 mini-format-1.3.1.zip`. Compara el resultado con el archivo de huellas.

Continúa con [Inicio rápido](/docs/quickstart/) o consulta [Crear tu toolkit](/docs/build/). Si quieres probar las familias opcionales, lee [cómo cargarlas](/docs/forks/).
