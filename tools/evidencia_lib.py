"""Biblioteca común de evidencia reproducible: manifiestos de corrida.

Todo estudio (V1-V6, V7, V8 y los de apoyo) registra cada ejecución como una
carpeta ``evidencia/corridas/<run_id>/`` con un ``manifiesto.json`` que sigue el
contrato ``mini-format/corrida/1`` (``evidencia/esquemas/corrida.schema.json``)
y los archivos de resultados que el manifiesto referencia con su SHA-256.

Solo biblioteca estándar. No hace llamadas de red ni inventa valores: lo que no
se puede determinar (commit sin git, versión de un paquete ausente) se registra
como ``null``, nunca como un valor supuesto.
"""
from __future__ import annotations

import hashlib
import json
import os
import platform
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence

ESQUEMA_CORRIDA = "mini-format/corrida/1"
ESTADOS_EJECUCION = ("pendiente", "bloqueado", "parcial", "ejecutado")
RESULTADOS = ("no_evaluable", "cumple", "no_cumple")
# Procedencia del dato: de dónde viene la evidencia, no cuánto vale.
PROCEDENCIAS = (
    "reportado_historico",   # cifra de un documento o corrida anterior, no reejecutada aquí
    "reproducido_local",    # recalculada ahora, sin API ni personas, desde datos congelados
    "simulado",             # proveedor simulado: valida el arnés, nunca un modelo
    "asistido_ia",          # texto producido por una IA en sesión (sin usage ni factura de API)
    "api_real",             # llamada real autorizada a un proveedor, con usage original
    "participantes",        # sesión con personas
)
ESTUDIOS_CONOCIDOS = ("V1", "V2", "V3", "V3a", "V3b", "V4", "V5", "V6a", "V6b", "V7", "V8", "OPT", "CF")

_RUN_ID = re.compile(r"^[a-z0-9][a-z0-9._-]{2,80}$")
_FECHA = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")
_SHA = re.compile(r"^[0-9a-f]{64}$")

PAQUETES_POR_DEFECTO = ("tiktoken", "regex", "numpy", "scipy", "PyYAML", "pytest", "coverage", "hypothesis", "jiter")


# ------------------------------------------------------------------ utilidades
def raiz_repo() -> Path:
    return Path(__file__).resolve().parent.parent


def ahora_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def sha256_bytes(datos: bytes) -> str:
    return hashlib.sha256(datos).hexdigest()


def sha256_texto(texto: str) -> str:
    return sha256_bytes(texto.encode("utf-8"))


def sha256_archivo(ruta: os.PathLike) -> str:
    h = hashlib.sha256()
    with open(ruta, "rb") as fh:
        for bloque in iter(lambda: fh.read(1 << 20), b""):
            h.update(bloque)
    return h.hexdigest()


def json_canonico(obj: Any) -> str:
    """JSON determinista: claves ordenadas, UTF-8 sin escapes, sangría 2, LF final."""
    return json.dumps(obj, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def escribir_json(ruta: os.PathLike, obj: Any) -> None:
    p = Path(ruta)
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(json_canonico(obj))


def leer_json(ruta: os.PathLike) -> Any:
    with open(ruta, encoding="utf-8") as fh:
        return json.load(fh)


def _git(*args: str, cwd: Optional[Path] = None, crudo: bool = False) -> Optional[str]:
    """Ejecuta git; ``crudo`` conserva los espacios iniciales (p. ej. ``status --porcelain``)."""
    try:
        r = subprocess.run(["git", *args], cwd=str(cwd or raiz_repo()), capture_output=True,
                           text=True, encoding="utf-8", timeout=60)
    except (OSError, subprocess.SubprocessError):
        return None
    if r.returncode != 0:
        return None
    return r.stdout.rstrip("\r\n") if crudo else r.stdout.strip()


def ruta_relativa(ruta: os.PathLike, base: Optional[Path] = None) -> str:
    base = base or raiz_repo()
    p = Path(ruta).resolve()
    try:
        return p.relative_to(base.resolve()).as_posix()
    except ValueError:
        return p.as_posix()


# --------------------------------------------------------------- procedencia
def info_codigo(repo: Optional[Path] = None) -> Dict[str, Any]:
    """Identifica el código ejecutado.

    ``commit`` es el HEAD real (``null`` si no hay git). ``arbol_limpio`` indica si
    el árbol de trabajo coincidía con ese commit. Si no, ``snapshot_sha256`` es un
    hash del contenido exacto del árbol (archivos rastreados y nuevos no ignorados)
    y ``archivos_modificados`` los lista: la corrida describe ESE código, no el
    commit, y debe reejecutarse contra el commit que se publique. No escribe nada
    en el repositorio.
    """
    repo = repo or raiz_repo()
    commit = _git("rev-parse", "HEAD", cwd=repo)
    rama = _git("rev-parse", "--abbrev-ref", "HEAD", cwd=repo)
    estado = _git("status", "--porcelain", "--untracked-files=all", cwd=repo, crudo=True)
    limpio = (estado == "") if estado is not None else None
    out: Dict[str, Any] = {"commit": commit, "rama": rama, "arbol_limpio": limpio,
                           "snapshot_sha256": None, "archivos_modificados": []}
    if commit is None:
        return out
    if not limpio:
        listado = _git("ls-files", "-c", "-o", "--exclude-standard", "-z", cwd=repo) or ""
        h = hashlib.sha256()
        for rel in sorted(x for x in listado.split("\0") if x):
            p = repo / rel
            if p.is_file():
                h.update(rel.encode("utf-8") + b"\0" + sha256_archivo(p).encode("ascii") + b"\n")
        out["snapshot_sha256"] = h.hexdigest()
        out["archivos_modificados"] = sorted(l[3:] for l in (estado or "").splitlines())
    return out


def _version_paquete(nombre: str) -> Optional[str]:
    try:
        from importlib import metadata
        return metadata.version(nombre)
    except Exception:
        return None


def info_entorno(paquetes: Sequence[str] = PAQUETES_POR_DEFECTO) -> Dict[str, Any]:
    node = None
    try:
        r = subprocess.run(["node", "--version"], capture_output=True, text=True, timeout=20)
        if r.returncode == 0:
            node = r.stdout.strip()
    except (OSError, subprocess.SubprocessError):
        pass
    return {
        "so": f"{platform.system()} {platform.release()}",
        "arquitectura": platform.machine(),
        "python": platform.python_version(),
        "node": node,
        "dependencias": {p: _version_paquete(p) for p in paquetes},
    }


def referencia_archivo(ruta: os.PathLike, base: Optional[Path] = None, **extra: Any) -> Dict[str, Any]:
    p = Path(ruta)
    ref: Dict[str, Any] = {"ruta": ruta_relativa(p, base), "sha256": sha256_archivo(p), "bytes": p.stat().st_size}
    ref.update(extra)
    return ref


def nuevo_run_id(estudio: str, sello: Optional[str] = None) -> str:
    sello = sello or datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"{estudio.lower()}-{sello.lower()}"


# ------------------------------------------------------------------ manifiesto
def nueva_corrida(estudio: str, procedencia: str, comando: str, *, run_id: Optional[str] = None,
                  **campos: Any) -> Dict[str, Any]:
    """Crea un manifiesto con los campos de procedencia rellenados desde el entorno real.

    Campos opcionales habituales (``campos``): ``pareja``, ``intento``, ``conjuntos``,
    ``contratos``, ``tokenizadores``, ``modelo``, ``parametros``, ``prompts``,
    ``conteos``, ``resumen``, ``criterio``, ``limitaciones``, ``gasto_usd``,
    ``estado_ejecucion``, ``resultado``, ``tarifas``, ``notas``.
    """
    m: Dict[str, Any] = {
        "esquema": ESQUEMA_CORRIDA,
        "run_id": run_id or nuevo_run_id(estudio),
        "estudio": estudio,
        "pareja": None,
        "intento": None,
        "procedencia": procedencia,
        "fecha_utc": ahora_utc(),
        "codigo": info_codigo(),
        "entorno": info_entorno(),
        "comando": comando,
        "conjuntos": [],
        "contratos": [],
        "tokenizadores": [],
        "modelo": None,
        "parametros": {},
        "prompts": [],
        "tarifas": None,
        "resultados": [],
        "conteos": None,
        "resumen": {},
        "criterio": None,
        "estado_ejecucion": "ejecutado",
        "resultado": "no_evaluable",
        "limitaciones": [],
        "gasto_usd": None,
        "notas": "",
    }
    m.update(campos)
    return m


def validar_corrida(m: Dict[str, Any], directorio: Optional[Path] = None) -> List[str]:
    """Devuelve la lista de errores del manifiesto (vacía si es válido).

    Comprueba estructura, enumeraciones y coherencia de honestidad: lo simulado o
    asistido por IA nunca puede declararse ``cumple``; ``api_real`` exige modelo y
    gasto; un resultado ``cumple``/``no_cumple`` exige ``estado_ejecucion`` ejecutado
    y un criterio. Si se pasa ``directorio`` verifica también los SHA-256 de los
    archivos de resultados que viven en él.
    """
    e: List[str] = []
    if not isinstance(m, dict):
        return ["el manifiesto no es un objeto"]
    if m.get("esquema") != ESQUEMA_CORRIDA:
        e.append(f"esquema debe ser {ESQUEMA_CORRIDA!r}")
    rid = m.get("run_id")
    if not isinstance(rid, str) or not _RUN_ID.match(rid):
        e.append("run_id inválido (minúsculas, dígitos, . _ -)")
    if not m.get("estudio"):
        e.append("falta estudio")
    if m.get("procedencia") not in PROCEDENCIAS:
        e.append(f"procedencia debe ser una de {PROCEDENCIAS}")
    if not isinstance(m.get("fecha_utc"), str) or not _FECHA.match(m["fecha_utc"]):
        e.append("fecha_utc debe ser AAAA-MM-DDThh:mm:ssZ")
    if not m.get("comando"):
        e.append("falta comando de reproducción")
    if m.get("estado_ejecucion") not in ESTADOS_EJECUCION:
        e.append(f"estado_ejecucion debe ser uno de {ESTADOS_EJECUCION}")
    if m.get("resultado") not in RESULTADOS:
        e.append(f"resultado debe ser uno de {RESULTADOS}")
    cod = m.get("codigo")
    if not isinstance(cod, dict) or "commit" not in cod or "arbol_limpio" not in cod:
        e.append("codigo debe incluir commit y arbol_limpio")
    elif cod.get("arbol_limpio") is False and not cod.get("snapshot_sha256"):
        e.append("árbol modificado sin snapshot_sha256")
    if not isinstance(m.get("entorno"), dict):
        e.append("falta entorno")
    for clave in ("conjuntos", "contratos", "prompts", "resultados"):
        for i, r in enumerate(m.get(clave) or []):
            sha = r.get("sha256") if isinstance(r, dict) else None
            if sha is not None and not _SHA.match(str(sha)):
                e.append(f"{clave}[{i}].sha256 inválido")
            if isinstance(r, dict) and not r.get("ruta") and clave != "prompts":
                e.append(f"{clave}[{i}] sin ruta")
    proc = m.get("procedencia")
    if m.get("resultado") in ("cumple", "no_cumple"):
        if m.get("estado_ejecucion") != "ejecutado":
            e.append("cumple/no_cumple exige estado_ejecucion = ejecutado")
        if not m.get("criterio"):
            e.append("cumple/no_cumple exige criterio")
        if proc in ("simulado", "asistido_ia", "reportado_historico"):
            e.append(f"una corrida {proc} no puede declararse cumple/no_cumple")
    if proc == "api_real":
        mod = m.get("modelo") or {}
        if not (mod.get("proveedor") and mod.get("modelo_pedido")):
            e.append("api_real exige modelo.proveedor y modelo.modelo_pedido")
        if m.get("gasto_usd") is None:
            e.append("api_real exige gasto_usd")
    if proc in ("simulado", "asistido_ia") and m.get("gasto_usd") not in (None, 0, 0.0):
        e.append(f"una corrida {proc} no tiene gasto de API")
    if m.get("estado_ejecucion") in ("pendiente", "bloqueado") and m.get("resultado") != "no_evaluable":
        e.append("pendiente/bloqueado implica resultado no_evaluable")
    if directorio is not None:
        for r in m.get("resultados") or []:
            if isinstance(r, dict) and r.get("ruta") and r.get("sha256"):
                p = raiz_repo() / r["ruta"]
                if not p.exists():
                    p = Path(directorio) / Path(r["ruta"]).name
                if not p.exists():
                    e.append(f"falta el archivo de resultados {r['ruta']}")
                elif sha256_archivo(p) != r["sha256"]:
                    e.append(f"SHA-256 distinto en {r['ruta']}")
    return e


def directorio_corridas() -> Path:
    return raiz_repo() / "evidencia" / "corridas"


def guardar_corrida(m: Dict[str, Any], archivos: Iterable[os.PathLike] = (),
                    directorio: Optional[Path] = None) -> Path:
    """Escribe ``manifiesto.json`` (y registra en él los ``archivos`` de resultados).

    Los archivos deben existir ya dentro del directorio de la corrida (escríbalos
    allí antes de llamar). Falla si el manifiesto no valida.
    """
    d = Path(directorio) if directorio else directorio_corridas() / m["run_id"]
    d.mkdir(parents=True, exist_ok=True)
    refs = [referencia_archivo(a) for a in archivos]
    if refs:
        m["resultados"] = list(m.get("resultados") or []) + refs
    errores = validar_corrida(m, d)
    if errores:
        raise ValueError("manifiesto inválido: " + "; ".join(errores))
    destino = d / "manifiesto.json"
    escribir_json(destino, m)
    return destino


def cargar_corridas(directorio: Optional[Path] = None) -> List[Dict[str, Any]]:
    base = Path(directorio) if directorio else directorio_corridas()
    out: List[Dict[str, Any]] = []
    if base.exists():
        for p in sorted(base.glob("*/manifiesto.json")):
            out.append(leer_json(p))
    return out


if __name__ == "__main__":  # diagnóstico rápido: python tools/evidencia_lib.py
    json.dump({"codigo": info_codigo(), "entorno": info_entorno()}, sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")
