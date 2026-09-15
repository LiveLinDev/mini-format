"""Paso de construcción que empaqueta las familias oficiales dentro de ``minifmt``.

Los metadatos del proyecto viven en ``pyproject.toml``.  Este archivo solo
extiende ``build_py`` para copiar ``forks/`` (fuente única en la raíz del
repositorio, usada también por el benchmark, la validación generativa, el
port JS y el playground) a ``minifmt/forks/`` dentro del paquete construido.
Así ``Registry.load()`` funciona tras ``pip install`` sin duplicar las
familias en el árbol de fuentes.
"""
from __future__ import annotations

import shutil
from pathlib import Path

from setuptools import setup
from setuptools.command.build_py import build_py as _build_py

ROOT = Path(__file__).resolve().parent
FORKS_SRC = ROOT / "forks"
FORK_PATTERNS = ("registry.json", "*/contract.json", "*/README.md", "*/fixtures/*")


def fork_files(base: Path = FORKS_SRC):
    seen = set()
    for pattern in FORK_PATTERNS:
        for p in sorted(base.glob(pattern)):
            if p.is_file() and p not in seen:
                seen.add(p)
                yield p


class build_py(_build_py):
    """``build_py`` que además copia las familias como datos del paquete."""

    def run(self):
        super().run()
        if getattr(self, "editable_mode", False) or not FORKS_SRC.is_dir():
            return  # en modo editable se usan directamente las del repositorio
        target = Path(self.build_lib) / "minifmt" / "forks"
        for src in fork_files():
            dst = target / src.relative_to(FORKS_SRC)
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(src, dst)

    def get_outputs(self, include_bytecode=True):
        outs = list(super().get_outputs(include_bytecode))
        if getattr(self, "editable_mode", False) or not FORKS_SRC.is_dir():
            return outs
        target = Path(self.build_lib) / "minifmt" / "forks"
        outs.extend(str(target / p.relative_to(FORKS_SRC)) for p in fork_files())
        return outs


setup(cmdclass={"build_py": build_py})
