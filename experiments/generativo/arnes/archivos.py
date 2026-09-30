"""Escritura de archivos con fin de línea LF en todas las plataformas.

Los resultados se referencian por SHA-256 en los manifiestos y el repositorio normaliza a LF: si Windows escribiera CRLF, el
hash guardado no coincidiría con el archivo versionado.  ``Path.write_text(newline=...)`` no existe en Python 3.9.
"""
from __future__ import annotations

from pathlib import Path
from typing import Union


def escribir_texto(ruta: Union[str, Path], texto: str) -> None:
    with open(ruta, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(texto)
