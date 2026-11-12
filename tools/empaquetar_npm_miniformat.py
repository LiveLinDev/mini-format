"""Reempaqueta el paquete Node 1.3.3 publicado en el sitio para el registro npm con el scope @miniformat.

La organización «mini-format» no estaba disponible en npm; la organización del proyecto es «miniformat». Este script
toma mini-format-core-1.3.3.tgz (el archivo de mini-format.pmoluna.com/downloads, SHA-256 en SHA256SUMS.txt), cambia
solo el nombre del paquete y la sección de instalación de los README, y deja dist/ y src/ idénticos byte a byte.
Uso: python tools/empaquetar_npm_miniformat.py RUTA/mini-format-core-1.3.3.tgz CARPETA_SALIDA
"""
from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import sys
import tarfile
from pathlib import Path

NOMBRE = "@miniformat/core"
SITIO = "https://mini-format.pmoluna.com"

INSTALAR_ES = (
    "## Instalación del paquete\n\n"
    "Necesitas Node.js ≥ 22.6. Instala el paquete desde npm:\n\n"
    "```sh\nnpm install @miniformat/core\n```\n\n"
    "El mismo código se distribuye en " + SITIO + "/downloads/ como `mini-format-core-1.3.3.tgz` (con su huella en "
    "`SHA256SUMS.txt`) para instalar sin conexión:\n\n"
    "```sh\nnpm install --offline --ignore-scripts --no-audit --no-fund ./mini-format-core-1.3.3.tgz\n```\n\n"
    "El archivo descargado conserva el nombre `@mini-format/core`; el código de `dist/` y `src/` es el mismo.\n\n"
)
INSTALAR_EN = (
    "## Install the package\n\n"
    "Requires Node.js ≥ 22.6. Install it from npm:\n\n"
    "```sh\nnpm install @miniformat/core\n```\n\n"
    "The same code is distributed at " + SITIO + "/downloads/ as `mini-format-core-1.3.3.tgz` (fingerprint in "
    "`SHA256SUMS.txt`) for offline installs:\n\n"
    "```sh\nnpm install --offline --ignore-scripts --no-audit --no-fund ./mini-format-core-1.3.3.tgz\n```\n\n"
    "The downloaded archive keeps the name `@mini-format/core`; the code in `dist/` and `src/` is the same.\n\n"
)


def _seccion(texto: str, titulo: str, nuevo: str) -> str:
    ini = texto.index(titulo)
    fin = texto.index("\n## ", ini + len(titulo)) + 1
    return texto[:ini] + nuevo + texto[fin:]


def _huellas(raiz: Path) -> dict:
    return {str(p.relative_to(raiz)).replace("\\", "/"): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(raiz.rglob("*")) if p.is_file() and p.parts[len(raiz.parts)] in ("dist", "src")}


def main(tgz: Path, salida: Path) -> None:
    trabajo = salida / "_trabajo"
    shutil.rmtree(trabajo, ignore_errors=True)
    trabajo.mkdir(parents=True)
    with tarfile.open(tgz) as t:
        t.extractall(trabajo)
    pkg = trabajo / "package"
    original = _huellas(pkg)
    meta = json.loads((pkg / "package.json").read_text(encoding="utf-8"))
    meta["name"] = NOMBRE
    meta["homepage"] = SITIO
    (pkg / "package.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    for nombre, titulo, nuevo in (("README.md", "## Instalación del paquete", INSTALAR_ES),
                                  ("README.en.md", "## Install the package", INSTALAR_EN)):
        r = pkg / nombre
        texto = _seccion(r.read_text(encoding="utf-8"), titulo, nuevo)
        # ejemplos de importación y título con el nombre publicado; la nota sobre el .tgz conserva el nombre original
        texto = texto.replace("from '@mini-format/core'", f"from '{NOMBRE}'").replace(
            "# @mini-format/core", f"# {NOMBRE}")
        r.write_text(texto, encoding="utf-8")
    assert _huellas(pkg) == original, "dist/ o src/ cambiaron"
    salida.mkdir(parents=True, exist_ok=True)
    npm = shutil.which("npm") or "npm"
    r = subprocess.run([npm, "pack", "--pack-destination", str(salida.resolve())], cwd=pkg, capture_output=True,
                       text=True, check=True)
    archivo = salida / r.stdout.strip().splitlines()[-1]
    print(f"{archivo.name}: {hashlib.sha256(archivo.read_bytes()).hexdigest()} | dist/ y src/ idénticos "
          f"({len(original)} archivos)")
    shutil.rmtree(trabajo)


if __name__ == "__main__":
    main(Path(sys.argv[1]), Path(sys.argv[2]))
