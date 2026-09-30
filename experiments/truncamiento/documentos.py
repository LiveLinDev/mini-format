"""Documentos de referencia de V3a: 14 dominios sintéticos y 4 snapshots públicos archivados.

Cada documento se serializa en tres textos propios (JSON compacto, JSON Lines y .mini) y de cada texto se
calculan, **construyéndolo pieza a pieza** (no leyéndolo con el lector bajo prueba), los desplazamientos en
bytes donde termina cada registro. Con ellos se sabe exactamente cuántos registros completos hay en
cualquier prefijo («disponibles»). Ver ``PROTOCOLO.md`` §2-§3.
"""
from __future__ import annotations

import hashlib
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

from . import lectores as L

RAIZ = Path(__file__).resolve().parents[2]
for _p in (RAIZ / "experiments", RAIZ / "benchmark", RAIZ / "src"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

N_REGISTROS = 50
DOMINIOS = ["a", "card", "cat", "cls", "code", "log", "map", "ner", "q", "r", "s", "sum", "tc", "us"]
SNAPSHOTS = ["products", "users", "comments", "earthquakes"]
_MARCA = "@@REGISTROS@@"


def _compacto(valor: Any) -> str:
    return json.dumps(valor, ensure_ascii=False, separators=(",", ":"))


def canon(valor: Any) -> str:
    """Forma canónica para comparar registros (independiente del orden de claves)."""
    return json.dumps(valor, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


@dataclass
class TextoFormato:
    texto: str
    fines: List[int]          # bytes UTF-8 donde termina cada registro (contenido completo, sin el LF separador)


@dataclass
class Documento:
    id: str
    tipo: str                 # dominio_sintetico | snapshot_prueba_publica | snapshot_real
    sintetico: bool
    n: int
    clave: Optional[str]      # clave del arreglo de registros en el JSON (None = arreglo en la raíz)
    registros: List[Dict[str, Any]]      # registros de referencia exactos
    envoltura: Optional[Dict[str, Any]]  # campos que no son registros (None si la raíz es un arreglo)
    contrato: Any             # Contract (académico) o dict mini-domain/1
    perfil_mini: str          # 'academico' | 'dominio'
    textos: Dict[str, TextoFormato]      # 'json' | 'jsonl' | 'mini'
    referencia_mini: Optional[List[Any]]  # registros que devuelve el lector sobre el texto .mini COMPLETO
    exclusiones: Dict[str, str] = field(default_factory=dict)  # formato -> causa (falló la precondición de integridad)
    meta: Dict[str, Any] = field(default_factory=dict)

    @property
    def con_envoltura_jsonl(self) -> bool:
        return bool(self.envoltura)


# ------------------------------------------------------------------ construcción de textos
def construir_json_compacto(doc: Any, clave: Optional[str]) -> TextoFormato:
    """JSON compacto con los fines de registro calculados por construcción."""
    registros = doc if clave is None else doc[clave]
    trozos = [_compacto(r) for r in registros]
    if clave is None:
        cabeza, cola = "", ""
    else:
        esqueleto = dict(doc)
        esqueleto[clave] = _MARCA
        s = _compacto(esqueleto)
        marca = _compacto(_MARCA)
        if s.count(marca) != 1:
            raise AssertionError("marca de registros ambigua")
        cabeza, cola = s.split(marca)
    texto = cabeza + "[" + ",".join(trozos) + "]" + cola
    if texto != _compacto(doc):
        raise AssertionError("el JSON compacto construido no coincide con json.dumps")
    pos = len(cabeza.encode("utf-8")) + 1
    fines: List[int] = []
    for i, t in enumerate(trozos):
        pos += len(t.encode("utf-8"))
        fines.append(pos)
        pos += 1                # la coma separadora
    return TextoFormato(texto, fines)


def construir_jsonl(envoltura: Optional[Dict[str, Any]], registros: Sequence[Any]) -> TextoFormato:
    partes: List[str] = []
    pos = 0
    fines: List[int] = []
    if envoltura:
        linea = _compacto(envoltura)
        partes.append(linea + "\n")
        pos += len(linea.encode("utf-8")) + 1
    for r in registros:
        linea = _compacto(r)
        pos += len(linea.encode("utf-8"))
        fines.append(pos)
        pos += 1                # LF
        partes.append(linea + "\n")
    return TextoFormato("".join(partes), fines)


def construir_mini(texto: str, n: int) -> TextoFormato:
    """Desplazamientos de las líneas de registro de un texto .mini (cabecera + n líneas, sin LF final)."""
    lineas = texto.split("\n")
    if len(lineas) != n + 1:
        raise AssertionError(f".mini con {len(lineas)} líneas; se esperaban {n + 1} (cabecera + registros)")
    pos = len(lineas[0].encode("utf-8")) + 1
    fines: List[int] = []
    for linea in lineas[1:]:
        pos += len(linea.encode("utf-8"))
        fines.append(pos)
        pos += 1
    return TextoFormato(texto, fines)


# ------------------------------------------------------------------ integridad
def _sin_nulos(v: Any) -> Any:
    if isinstance(v, dict):
        return {k: _sin_nulos(x) for k, x in v.items() if x is not None}
    if isinstance(v, list):
        return [_sin_nulos(x) for x in v]
    return v


def equivalentes_mini_academico(fuente: Any, leido: Any) -> bool:
    """Igualdad bajo la normalización documentada: clave omitida ≡ null e igualdad numérica entero/flotante."""
    from minifmt import canonical_equal
    return canonical_equal(_sin_nulos(fuente), _sin_nulos(leido))


def _comprobar(doc: Documento) -> None:
    """Precondición de integridad: leer el texto COMPLETO devuelve los registros fuente."""
    # JSON compacto
    try:
        v = json.loads(doc.textos["json"].texto)
        ok = [canon(r) for r in L._extraer(v, doc.clave)] == [canon(r) for r in doc.registros]
        if not ok:
            doc.exclusiones["json"] = "json.loads del texto completo no reproduce los registros fuente"
    except ValueError as e:
        doc.exclusiones["json"] = f"json.loads falla: {e}"
    # JSON Lines
    lec = L.leer_jsonl(doc.textos["jsonl"].texto, doc.con_envoltura_jsonl)
    if [canon(r) for r in lec.registros] != [canon(r) for r in doc.registros]:
        doc.exclusiones["jsonl"] = "el lector JSONL del texto completo no reproduce los registros fuente"
    # .mini
    lec = L.leer_mini_tolerante(doc.textos["mini"].texto, doc.contrato, truncado=False)
    if len(lec.registros) != len(doc.registros):
        doc.exclusiones["mini"] = f"el lector .mini recupera {len(lec.registros)} de {len(doc.registros)} registros del texto completo"
    elif doc.perfil_mini == "academico":
        malos = [i for i, (a, b) in enumerate(zip(doc.registros, lec.registros)) if not equivalentes_mini_academico(a, b)]
        if malos:
            doc.exclusiones["mini"] = f"{len(malos)} registros no equivalentes tras el ida y vuelta (primero: índice {malos[0]})"
    else:
        if [canon(r) for r in lec.registros] != [canon(r) for r in doc.registros]:
            doc.exclusiones["mini"] = "mini-domain/1 no devolvió exactamente los registros fuente"
    if "mini" not in doc.exclusiones:
        doc.referencia_mini = lec.registros


# ------------------------------------------------------------------ fuentes
def construir_dominio(prefijo: str, n: int = N_REGISTROS) -> Documento:
    import comun as C
    import formats
    reg = C.registro()
    contrato = reg.get(prefijo)
    obj = C.generar(prefijo, n, "muestreo", C.SEMILLA)
    clave = contrato.records_key
    registros = obj[clave]
    envoltura = {k: v for k, v in obj.items() if k != clave}
    mini_texto = formats.mini_ser(obj, contrato)
    contrato_ruta = RAIZ / "forks" / prefijo / "contract.json"
    doc = Documento(
        id=prefijo, tipo="dominio_sintetico", sintetico=True, n=len(registros), clave=clave,
        registros=registros, envoltura=envoltura, contrato=contrato, perfil_mini="academico",
        textos={"json": construir_json_compacto(obj, clave),
                "jsonl": construir_jsonl(envoltura, registros),
                "mini": construir_mini(mini_texto, len(registros))},
        referencia_mini=None,
        meta={"semilla": C.SEMILLA, "generador": "experiments/comun.generar(prefijo, 50, 'muestreo')",
              "contrato_ruta": contrato_ruta.relative_to(RAIZ).as_posix(),
              "contrato_sha256": hashlib.sha256(contrato_ruta.read_bytes()).hexdigest(),
              "contrato_version": getattr(contrato, "version", None)})
    _comprobar(doc)
    return doc


def _fuentes_snapshots() -> Dict[str, Dict[str, Any]]:
    ruta = RAIZ / "benchmark" / "public" / "sources.json"
    return {s["id"]: s for s in json.loads(ruta.read_text(encoding="utf-8"))}


def construir_snapshot(id_: str, n: int = N_REGISTROS) -> Documento:
    from minifmt import domain as dom
    fuente = _fuentes_snapshots()[id_]
    ruta = RAIZ / "benchmark" / "public" / fuente["file"]
    crudo = ruta.read_bytes()
    sha = hashlib.sha256(crudo).hexdigest()
    if sha != fuente["sha256"]:
        raise ValueError(f"el snapshot {id_} no coincide con el hash de sources.json")
    original = json.loads(crudo)
    clave = fuente["records_key"]
    if clave is None:
        filas = original[:n]
        doc50: Any = filas
        envoltura: Optional[Dict[str, Any]] = None
    else:
        filas = original[clave][:n]
        doc50 = dict(original)
        doc50[clave] = filas
        envoltura = {k: v for k, v in original.items() if k != clave}
    contrato = dom.infer_contract([doc50], prefix=id_)
    esperado = [] if clave is None else [clave]
    if contrato["record_path"] != esperado:
        raise ValueError(f"{id_}: el contrato inferido eligió record_path={contrato['record_path']}, se esperaba {esperado}")
    mini_texto = dom.encode(doc50, contrato)
    real = fuente["kind"].startswith("real") and "synthetic" not in fuente["kind"]
    doc = Documento(
        id=id_, tipo="snapshot_real" if real else "snapshot_prueba_publica", sintetico=not real, n=len(filas),
        clave=clave, registros=filas, envoltura=envoltura, contrato=contrato, perfil_mini="dominio",
        textos={"json": construir_json_compacto(doc50, clave),
                "jsonl": construir_jsonl(envoltura, filas),
                "mini": construir_mini(mini_texto, len(filas))},
        referencia_mini=None,
        meta={"fuente_url": fuente["url"], "fuente_tipo": fuente["kind"], "archivo": fuente["file"],
              "archivo_sha256": sha, "archivo_registros": fuente["records"], "seleccion": f"primeros {n} registros en el orden archivado",
              "archivado_utc": fuente["fetched_at_utc"]})
    _comprobar(doc)
    return doc


def construir_todos(dominios: Sequence[str] = DOMINIOS, snapshots: Sequence[str] = SNAPSHOTS) -> List[Documento]:
    return [construir_dominio(p) for p in dominios] + [construir_snapshot(s) for s in snapshots]
