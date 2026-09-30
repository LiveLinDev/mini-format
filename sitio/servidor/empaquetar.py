"""Empaqueta `sitio/` para el despliegue, dejando fuera los archivos de construcción.

    python sitio/servidor/empaquetar.py | ssh ... desplegar      # tar.gz por la salida estándar
    python sitio/servidor/empaquetar.py --listar                 # qué se publica y qué se excluye

Es la ÚNICA definición de qué se sube al servidor: la usan `.github/workflows/sitio.yml` y
`sitio/desplegar.sh`, y `tests/test_sitio_empaquetado.py` la prueba.

Qué NO se publica (archivos que solo sirven para construir el sitio o documentarlo, nunca al navegador):
  * todo `*.py` de la raíz de `sitio/` (construir.py, publicar.py, benchmarks.py, modulos.py, cifras.py,
    ejemplo_lote.py y los módulos comofunciona/validacion/economia): un generador nuevo no queda público por olvido;
  * `landing.en.json` y `animation.en.json` (mapas de traducción de la portada; `app.en.js` ya los aplica);
  * `content/` (Markdown fuente), `i18n/` (claves EN de los módulos), `servidor/` y `desplegar.sh`;
  * `LEEME_MODULOS.md`, `__pycache__` y `*.pyc` en cualquier nivel.
Lo que sí se publica, aunque sea `.py`, es la evidencia enlazada en `source/` (p. ej. `source/experiments/.../run.py`):
la exclusión de `*.py` es SOLO de la raíz.
"""
from __future__ import annotations

import argparse
import gzip
import sys
import tarfile
from pathlib import Path

SITIO = Path(__file__).resolve().parents[1]
EXCLUIR_DIRS_RAIZ = {"content", "i18n", "servidor"}
EXCLUIR_ARCHIVOS_RAIZ = {"landing.en.json", "animation.en.json", "desplegar.sh", "LEEME_MODULOS.md"}
EXCLUIR_EN_CUALQUIER_NIVEL = {"__pycache__"}
# Sin esto el receptor del servidor rechaza el paquete (recibir-sitio.sh) o el sitio queda roto.
OBLIGATORIOS = ("index.html", "404.html", "base.css", "app.js", "docs.js", "playground/index.html", "docs/index.html",
                "version.json", "sitemap.xml")


def incluir(relativo: Path) -> bool:
    """¿Se publica este archivo (ruta relativa a `sitio/`)?"""
    partes = relativo.parts
    if any(p in EXCLUIR_EN_CUALQUIER_NIVEL for p in partes) or relativo.suffix == ".pyc":
        return False
    if partes[0] in EXCLUIR_DIRS_RAIZ:
        return False
    if len(partes) == 1 and (relativo.name in EXCLUIR_ARCHIVOS_RAIZ or relativo.suffix == ".py"):
        return False
    return True


def clasificar(sitio: Path = SITIO) -> tuple[list[Path], list[Path]]:
    """(publicados, excluidos) como rutas relativas ordenadas. Un enlace simbólico es un error: el receptor lo rechaza."""
    publicados, excluidos = [], []
    for archivo in sorted(sitio.rglob("*")):
        if archivo.is_symlink():
            raise SystemExit(f"enlace simbólico en el sitio: {archivo} (el receptor del servidor lo rechazaría)")
        if not archivo.is_file():
            continue
        relativo = archivo.relative_to(sitio)
        (publicados if incluir(relativo) else excluidos).append(relativo)
    return publicados, excluidos


def faltantes(publicados: list[Path]) -> list[str]:
    presentes = {p.as_posix() for p in publicados}
    return [o for o in OBLIGATORIOS if o not in presentes]


def empaquetar(destino, sitio: Path = SITIO) -> int:
    """Escribe un .tar.gz de los archivos publicados en el objeto binario `destino`. Devuelve cuántos archivos."""
    publicados, _ = clasificar(sitio)
    faltan = faltantes(publicados)
    if faltan:
        raise SystemExit("faltan archivos obligatorios (¿se ejecutó python sitio/construir.py?): " + ", ".join(faltan))
    with gzip.GzipFile(fileobj=destino, mode="wb", mtime=0) as gz:
        with tarfile.open(fileobj=gz, mode="w", format=tarfile.GNU_FORMAT) as tar:
            for relativo in publicados:
                info = tar.gettarinfo(str(sitio / relativo), arcname=relativo.as_posix())
                info.uid = info.gid = 0
                info.uname = info.gname = ""
                info.mode = 0o644
                with (sitio / relativo).open("rb") as datos:
                    tar.addfile(info, datos)
    return len(publicados)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--sitio", type=Path, default=SITIO, help="carpeta a empaquetar (por omisión sitio/)")
    ap.add_argument("--listar", action="store_true", help="solo lista qué se publica y qué se excluye")
    ap.add_argument("--salida", default="-", help="archivo .tar.gz de salida; «-» es la salida estándar")
    args = ap.parse_args(argv)
    if args.listar:
        publicados, excluidos = clasificar(args.sitio)
        print(f"publicados: {len(publicados)} archivos")
        print("excluidos:")
        for e in excluidos:
            print("  " + e.as_posix())
        faltan = faltantes(publicados)
        if faltan:
            print("FALTAN obligatorios: " + ", ".join(faltan))
            return 1
        return 0
    if args.salida == "-":
        n = empaquetar(sys.stdout.buffer, args.sitio)
    else:
        with open(args.salida, "wb") as f:
            n = empaquetar(f, args.sitio)
    print(f"empaquetados {n} archivos", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
