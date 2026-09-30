"""Cifras del proyecto calculadas desde el repositorio, nunca escritas a mano.

    python sitio/cifras.py          # imprime las cifras como JSON

Las cifras que la portada y la documentación repiten a mano (casos de la suite de
conformidad, códigos de error, familias oficiales y versiones) salen de aquí.
`tests/test_sitio_cifras.py` falla si el texto publicado difiere de este cálculo,
de modo que una cifra obsoleta (por ejemplo «303 casos» cuando la suite 1.1 tiene
372) no vuelve a llegar al sitio sin que una prueba lo note.

Procedencia: todo lo de este módulo se deriva de archivos del repositorio
(`conformance/cases/*.json`, `src/minifmt/errors.py`, `forks/*/contract.json`,
`src/minifmt/__init__.py`). La única excepción es `CASOS_SUITE_1_0`, una cifra
histórica de la suite 1.0 que se cita como tal (fuente: CHANGELOG.md, entrada de la
suite 1.1) y que no se recalcula porque los casos no llevan marca de versión.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]

# Cifra histórica citada por CHANGELOG.md («372 cases (303 from 1.0 kept ...)»):
# la suite 1.0 tenía 303 casos y la 1.1 los conserva todos.
CASOS_SUITE_1_0 = 303

_NOMBRES_ES = {12: "Doce", 13: "Trece", 14: "Catorce", 15: "Quince", 16: "Dieciséis", 17: "Diecisiete",
               18: "Dieciocho", 19: "Diecinueve", 20: "Veinte"}
_NOMBRES_EN = {12: "Twelve", 13: "Thirteen", 14: "Fourteen", 15: "Fifteen", 16: "Sixteen", 17: "Seventeen",
               18: "Eighteen", 19: "Nineteen", 20: "Twenty"}


def casos_conformidad(raiz: Path = RAIZ) -> tuple[int, int]:
    """(total de casos, archivos de categoría) de conformance/cases/*.json."""
    total, archivos = 0, 0
    for archivo in sorted((raiz / "conformance" / "cases").glob("*.json")):
        total += len(json.loads(archivo.read_text(encoding="utf-8"))["cases"])
        archivos += 1
    return total, archivos


def codigos_error(raiz: Path = RAIZ) -> list[str]:
    """Códigos estables definidos en src/minifmt/errors.py (constantes E_* = "Exx")."""
    texto = (raiz / "src" / "minifmt" / "errors.py").read_text(encoding="utf-8")
    return re.findall(r'^E_[A-Z_]+\s*=\s*"(E\d+)"', texto, re.M)


def familias(raiz: Path = RAIZ) -> list[str]:
    """Prefijos de las familias oficiales: una carpeta forks/<prefijo>/ con contract.json."""
    return sorted(p.parent.name for p in (raiz / "forks").glob("*/contract.json"))


def _version_paquete(raiz: Path) -> str:
    return re.search(r'^version = "([^"]+)"', (raiz / "pyproject.toml").read_text(encoding="utf-8"), re.M).group(1)


def _version_spec(raiz: Path) -> str:
    return re.search(r'^SPEC_VERSION = "([^"]+)"', (raiz / "src" / "minifmt" / "__init__.py").read_text(encoding="utf-8"), re.M).group(1)


def calcular(raiz: Path = RAIZ) -> dict:
    """Todas las cifras públicas con sus palabras en ES y EN (para textos como «Catorce familias»)."""
    casos, archivos = casos_conformidad(raiz)
    codigos = codigos_error(raiz)
    prefijos = familias(raiz)
    return {
        "casos_conformidad": casos,
        "archivos_conformidad": archivos,
        "casos_suite_1_0": CASOS_SUITE_1_0,
        "casos_nuevos_1_1": casos - CASOS_SUITE_1_0,
        "codigos_error": len(codigos),
        "codigos": codigos,
        "familias": len(prefijos),
        "prefijos_familias": prefijos,
        "version_paquete": _version_paquete(raiz),
        "version_spec": _version_spec(raiz),
        "palabra_familias_es": _NOMBRES_ES.get(len(prefijos)),
        "palabra_familias_en": _NOMBRES_EN.get(len(prefijos)),
        "palabra_codigos_es": _NOMBRES_ES.get(len(codigos)),
        "palabra_codigos_en": _NOMBRES_EN.get(len(codigos)),
    }


if __name__ == "__main__":
    print(json.dumps(calcular(), ensure_ascii=False, indent=2))
