# Descargar mini-format 1.1.0

El toolkit incluye todo lo necesario para crear un formato de dominio desde tus muestras JSON y ejecutarlo localmente. Licencia MIT; sin cuenta ni conexión a un repositorio privado.

| Descarga | Contenido |
|---|---|
| [Toolkit completo .zip](/downloads/mini-format-1.1.0.zip) | Paquete Python, paquete Node, ejemplos, especificaciones y guías. |
| [Python .whl](/downloads/mini_format-1.1.0-py3-none-any.whl) | CLI `mini`, perfil base, 14 familias y constructor de toolkits. Python 3.9+. |
| [Node / TypeScript .tgz](/downloads/mini-format-core-1.1.0.tgz) | Parser, validador, serializador y streaming del perfil base. Node 22.6+. |
| [Código fuente .zip](/downloads/mini-format-1.1.0-source.zip) | Implementaciones, pruebas, contratos y benchmark público reproducible. |

## Instalar Python

```bash
python -m pip install https://mini-format.pmoluna.com/downloads/mini_format-1.1.0-py3-none-any.whl
mini build examples/phones.json examples/phones-extra.json --prefix phone --out .mini
```

El segundo comando usa los ejemplos incluidos en el ZIP. Para instalar sin conexión, desde la carpeta extraída:

```bash
python -m pip install --no-index mini_format-1.1.0-py3-none-any.whl
```

## Instalar Node

Descarga el `.tgz` o extráelo del toolkit y ejecuta:

```bash
npm install ./mini-format-core-1.1.0.tgz
```

Importa la biblioteca con `import { Registry, parse } from '@mini-format/core'`. El toolkit generado de dominio utiliza Python; esta biblioteca implementa el perfil base SPEC 1.0.

## Verificar la descarga

[SHA256SUMS.txt](/downloads/SHA256SUMS.txt) contiene las huellas de los cuatro paquetes. El [manifiesto JSON](/downloads/manifest.json) incluye versión, tamaño y SHA-256.

En PowerShell: `Get-FileHash .\mini-format-1.1.0.zip -Algorithm SHA256`. En Linux: `sha256sum mini-format-1.1.0.zip`. En macOS: `shasum -a 256 mini-format-1.1.0.zip`. Compara el resultado con el archivo de huellas.

Continúa con [Inicio rápido](/docs/quickstart/) o consulta [Crear tu toolkit](/docs/build/).
