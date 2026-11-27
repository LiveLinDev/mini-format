"""Reempaqueta el wheel 1.3.3 publicado en el sitio para PyPI con el nombre de distribución «minifmt».

En PyPI el nombre «mini-format» choca con el proyecto ajeno «miniformat» (PyPI rechaza nombres que solo difieren en
separadores), por lo que se usa «minifmt», el mismo nombre del paquete importable (import minifmt). Este script toma
mini_format-1.3.3-py3-none-any.whl (mini-format.pmoluna.com/downloads, SHA-256 en SHA256SUMS.txt), cambia solo el
nombre en METADATA, la carpeta .dist-info y la sección de instalación de la descripción, regenera RECORD y deja los
archivos del paquete minifmt/ idénticos byte a byte.
Uso: python tools/empaquetar_pypi_minifmt.py RUTA/mini_format-1.3.3-py3-none-any.whl CARPETA_SALIDA
"""
from __future__ import annotations

import base64
import hashlib
import sys
import zipfile
from pathlib import Path

VIEJO, NUEVO, VERSION = "mini_format", "minifmt", "1.3.3"
INICIO_VIEJO = ("[Download and extract the package](https://mini-format.pmoluna.com/downloads/mini-format-1.3.3.zip). "
                "From the extracted directory:\n\n```sh\npython -m pip install --no-index mini_format-1.3.3-py3-none-any.whl\n"
                "mini setup\n```")
INICIO_NUEVO = ("Install it from PyPI:\n\n```sh\npython -m pip install minifmt\nmini setup\n```\n\n"
                "The same code is distributed at https://mini-format.pmoluna.com/downloads/ as "
                "`mini_format-1.3.3-py3-none-any.whl` (fingerprint in `SHA256SUMS.txt`) for offline installs: "
                "`python -m pip install --no-index mini_format-1.3.3-py3-none-any.whl`.")


def _hash(datos: bytes) -> str:
    return "sha256=" + base64.urlsafe_b64encode(hashlib.sha256(datos).digest()).rstrip(b"=").decode()


def main(wheel: Path, salida: Path) -> None:
    di_viejo, di_nuevo = f"{VIEJO}-{VERSION}.dist-info", f"{NUEVO}-{VERSION}.dist-info"
    archivos = {}
    with zipfile.ZipFile(wheel) as z:
        for info in z.infolist():
            archivos[info.filename] = z.read(info)
    codigo = {n: hashlib.sha256(d).hexdigest() for n, d in archivos.items() if not n.startswith(di_viejo)}
    nuevos = {}
    for nombre, datos in archivos.items():
        if nombre == f"{di_viejo}/RECORD":
            continue
        destino = nombre.replace(di_viejo, di_nuevo, 1) if nombre.startswith(di_viejo) else nombre
        if nombre == f"{di_viejo}/METADATA":
            texto = datos.decode("utf-8")
            assert texto.count("\nName: mini-format\n") == 1 and INICIO_VIEJO in texto
            texto = texto.replace("\nName: mini-format\n", f"\nName: {NUEVO}\n", 1).replace(INICIO_VIEJO, INICIO_NUEVO, 1)
            datos = texto.encode("utf-8")
        nuevos[destino] = datos
    lineas = [f"{n},{_hash(d)},{len(d)}" for n, d in nuevos.items()] + [f"{di_nuevo}/RECORD,,"]
    nuevos[f"{di_nuevo}/RECORD"] = ("\n".join(lineas) + "\n").encode("utf-8")
    assert {n: hashlib.sha256(d).hexdigest() for n, d in nuevos.items() if not n.startswith(di_nuevo)} == codigo
    salida.mkdir(parents=True, exist_ok=True)
    destino = salida / f"{NUEVO}-{VERSION}-py3-none-any.whl"
    with zipfile.ZipFile(destino, "w", zipfile.ZIP_DEFLATED) as z:
        for nombre, datos in nuevos.items():  # el .dist-info va al final, como en el wheel original
            if not nombre.startswith(di_nuevo):
                z.writestr(zipfile.ZipInfo(nombre, (2026, 1, 1, 0, 0, 0)), datos, zipfile.ZIP_DEFLATED)
        for nombre, datos in nuevos.items():
            if nombre.startswith(di_nuevo):
                z.writestr(zipfile.ZipInfo(nombre, (2026, 1, 1, 0, 0, 0)), datos, zipfile.ZIP_DEFLATED)
    print(f"{destino.name}: {hashlib.sha256(destino.read_bytes()).hexdigest()} | {len(codigo)} archivos del paquete "
          "idénticos")


if __name__ == "__main__":
    main(Path(sys.argv[1]), Path(sys.argv[2]))
