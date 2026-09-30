"""Reversibilidad objeto -> texto -> objeto de cada comparador, ANTES de contar sus tokens.

Un conteo de tokens solo es comparable si el texto contado conserva los mismos
datos. Este módulo decodifica cada texto con un decodificador independiente del
codificador (JSON ``json.loads``, YAML ``safe_load``, XML con ``xml.etree``, CSV con
esquema, TOON con el decodificador oficial en modo estricto, .mini con ``minifmt.parse``)
y compara el resultado con el objeto original.

Estados (``Resultado.estado``):

* ``reversible``            el objeto reconstruido es semánticamente idéntico (claves sin
                            orden, ``bool`` distinto de número, ``1 == 1.0``).
* ``reversible_normalizado`` idéntico salvo normalizaciones DECLARADAS en ``normalizaciones``
                            (``None`` equivale a clave ausente; el serializador .mini añade
                            ``header.n`` y ``header.v``).
* ``no_reversible``         el texto no permite reconstruir el objeto; ``causa`` dice por qué
                            (primera diferencia con su ruta) y la comparación que lo use debe
                            excluirlo explícitamente.

Decodificar con ayuda del contrato (XML, CSV, TOON aplanado) es legítimo: el contrato es
un artefacto compartido que se declara y se cuenta aparte. Lo que no se admite es que una
diferencia se oculte: cualquier discrepancia queda registrada.
"""
from __future__ import annotations

import json
import subprocess
import sys
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

ROOT = Path(__file__).resolve().parents[2]
for _p in (ROOT / "src", ROOT / "benchmark", ROOT / "benchmark" / "public"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import yaml  # noqa: E402

import baselines as B  # noqa: E402  (benchmark/public/baselines.py)
import formats  # noqa: E402
from minifmt import dumps, parse  # noqa: E402

ACEPTADOS = ("reversible", "reversible_normalizado")
NODE_DECODE = ["node", "--experimental-strip-types", "--experimental-transform-types",
               str(ROOT / "benchmark" / "toon_ref" / "toon_decode.mjs")]
TOON_BRIDGE = ROOT / "benchmark" / "public" / "toon.mjs"


@dataclass
class Resultado:
    estado: str
    causa: str = ""
    normalizaciones: List[str] = field(default_factory=list)
    detalle: Dict[str, Any] = field(default_factory=dict)

    @property
    def aceptado(self) -> bool:
        return self.estado in ACEPTADOS


# ---------------------------------------------------------------- comparación
def _tipo(v: Any) -> str:
    return type(v).__name__


def primera_diferencia(a: Any, b: Any, ruta: str = "$") -> Optional[str]:
    """Ruta y descripción de la primera diferencia semántica entre ``a`` (original) y ``b``."""
    if B.equivalent(a, b):
        return None
    if isinstance(a, dict) and isinstance(b, dict):
        for k in a:
            if k not in b:
                return f"{ruta}/{k}: falta en el texto decodificado"
            d = primera_diferencia(a[k], b[k], f"{ruta}/{k}")
            if d:
                return d
        for k in b:
            if k not in a:
                return f"{ruta}/{k}: clave nueva tras decodificar"
        return f"{ruta}: diferencia de claves"
    if isinstance(a, list) and isinstance(b, list):
        if len(a) != len(b):
            return f"{ruta}: longitud {len(a)} frente a {len(b)}"
        for i, (x, y) in enumerate(zip(a, b)):
            d = primera_diferencia(x, y, f"{ruta}/{i}")
            if d:
                return d
    return f"{ruta}: {_tipo(a)} {json.dumps(a, ensure_ascii=False)[:60]} frente a {_tipo(b)} {json.dumps(b, ensure_ascii=False, default=str)[:60]}"


def sin_nulos(v: Any) -> Any:
    """Normalización declarada: una clave con valor ``None`` equivale a una clave ausente."""
    if isinstance(v, dict):
        return {k: sin_nulos(x) for k, x in v.items() if x is not None}
    if isinstance(v, list):
        return [sin_nulos(x) for x in v]
    return v


def comparar(original: Any, recuperado: Any, extra: Sequence[str] = ()) -> Resultado:
    d = primera_diferencia(original, recuperado)
    if d is None:
        return Resultado("reversible_normalizado" if extra else "reversible", normalizaciones=list(extra))
    if primera_diferencia(sin_nulos(original), sin_nulos(recuperado)) is None:
        return Resultado("reversible_normalizado", normalizaciones=["None equivale a clave ausente", *extra])
    return Resultado("no_reversible", causa=d)


# ------------------------------------------------------------------ JSON, YAML
def verificar_json(obj: Any, texto: str) -> Resultado:
    try:
        return comparar(obj, json.loads(texto))
    except Exception as e:
        return Resultado("no_reversible", causa=f"json.loads falla: {e}")


def verificar_yaml(obj: Any, texto: str) -> Resultado:
    try:
        return comparar(obj, yaml.safe_load(texto))
    except Exception as e:
        return Resultado("no_reversible", causa=f"yaml.safe_load falla: {e}")


# ------------------------------------------------------------ conversión de celdas
def _a_tipo(v: Any, tipo: str) -> Any:
    """Convierte el texto de una celda al tipo del contrato; ya tipado se devuelve igual."""
    if v is None or not isinstance(v, str):
        return v
    if tipo == "int":
        return int(v)
    if tipo == "float":
        return float(v)
    if tipo == "bool":
        if v not in ("true", "false"):
            raise ValueError(f"booleano no válido {v!r}")
        return v == "true"
    return v


def _celda(v: Any, f) -> Any:
    """Celda -> valor del campo escalar. Vacío: ``None`` salvo cadena obligatoria."""
    if v is None:
        return None
    if isinstance(v, str) and v == "" and (f.type != "str" or f.optional):
        return None
    return _a_tipo(v, f.type)


def _lista(v: Any, tipo_item: str, sep: str = ";") -> Optional[List[Any]]:
    if v is None or v == "":
        return [] if v == "" else None
    if isinstance(v, list):
        return v
    return [_a_tipo(x, tipo_item) for x in str(v).split(sep)]


# ------------------------------------------------------------------ XML (formats.xml_ser)
def _cabecera_de_xml(raiz: ET.Element, c) -> Dict[str, Any]:
    hdr: Dict[str, Any] = {}
    for k, v in raiz.attrib.items():
        hk = c.header_keys.get(k)
        hdr[k] = _a_tipo(v, hk.type if hk else "str")
    for ch in raiz:
        if ch.tag == "rec":
            continue
        hk = c.header_keys.get(ch.tag)
        if hk is not None and hk.type == "tuple":
            tipos = {comp.name: comp.type for comp in hk.items}
            hdr[ch.tag] = {kk: _a_tipo(vv, tipos.get(kk, "str")) for kk, vv in ch.attrib.items()}
        else:
            item = hk.item if hk is not None else "str"
            hdr[ch.tag] = [_a_tipo(i.text or "", item) for i in ch]
    return hdr


def _registro_de_xml(rec: ET.Element, c) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    for f in c.fields:
        if f.type in ("str", "int", "float", "bool", "enum"):
            e = rec.find(f.name)
            out[f.name] = None if e is None else _a_tipo(e.text or "", f.type)
        elif f.type == "list":
            e = rec.find(f.name)
            out[f.name] = None if e is None else [_a_tipo(i.text or "", f.item) for i in e]
        elif f.type == "mlist":
            e = rec.find(f.json_items)
            if e is None:
                out[f.json_items] = out[f.json_selected] = None
                continue
            out[f.json_items] = [_a_tipo(i.text or "", f.item) for i in e]
            idx = [i for i, el in enumerate(e) if el.attrib.get("sel") == "1"]
            out[f.json_selected] = (idx[0] if idx else None) if f.marker in ("exactly_one", "at_most_one") else idx
        elif f.type == "tuple":
            e = rec.find(f.name)
            if e is None:
                out[f.name] = None
            else:
                tipos = {comp.name: comp.type for comp in f.items}
                out[f.name] = {k: _a_tipo(v, tipos.get(k, "str")) for k, v in e.attrib.items()}
    return out


def verificar_xml_contrato(obj: Dict[str, Any], texto: str, c) -> Resultado:
    """XML de ``formats.xml_ser``: sin tipos en el texto; se decodifica con ayuda del contrato."""
    try:
        raiz = ET.fromstring(texto)
        rec = {"header": _cabecera_de_xml(raiz, c), c.records_key: [_registro_de_xml(r, c) for r in raiz.findall("rec")]}
    except Exception as e:
        return Resultado("no_reversible", causa=f"decodificación XML con contrato falla: {e}")
    r = comparar(obj, rec)
    r.detalle["decodificacion"] = "xml.etree + tipos del contrato (el texto no lleva tipos)"
    return r


def verificar_xml_tipado(obj: Any, texto: str) -> Resultado:
    try:
        return comparar(obj, B.xml_decode(texto))
    except Exception as e:
        return Resultado("no_reversible", causa=f"xml_decode falla: {e}")


# -------------------------------------------------- aplanado por contrato (CSV, TOON plano)
def desaplanar_contrato(filas: List[Dict[str, Any]], c, header: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Inversa contractual de ``formats.flatten_record`` (la usan CSV y TOON aplanado)."""
    out: List[Dict[str, Any]] = []
    for row in filas:
        rec: Dict[str, Any] = {}
        for f in c.fields:
            if f.type in ("str", "int", "float", "bool", "enum"):
                rec[f.name] = _celda(row.get(f.name), f)
            elif f.type in ("list", "mlist"):
                nombre = f.name if f.type == "list" else f.json_items
                k = formats.list_arity(f, header)
                if k:
                    vals = [row.get(f"{nombre}_{i + 1}") for i in range(k)]
                    while vals and vals[-1] in (None, ""):
                        vals.pop()
                    lista: Optional[List[Any]] = [_a_tipo(v, f.item) for v in vals]
                else:
                    lista = _lista(row.get(nombre), f.item)
                rec[nombre] = lista
                if f.type == "mlist":
                    sel = row.get(f.json_selected)
                    if f.marker in ("exactly_one", "at_most_one"):
                        rec[f.json_selected] = None if sel in (None, "") else int(sel) - 1
                    else:
                        rec[f.json_selected] = None if sel in (None, "") else [int(x) - 1 for x in str(sel).split(";")]
            elif f.type == "tuple":
                comps = {comp.name: _celda(row.get(f"{f.name}_{comp.name}"), comp) for comp in f.items}
                comps = {k: v for k, v in comps.items() if v is not None}
                rec[f.name] = comps if comps else None
        out.append(rec)
    return out


def verificar_csv_contrato(obj: Dict[str, Any], texto: str, c) -> Resultado:
    """CSV de ``formats.csv_ser``: no lleva el ``header`` del documento."""
    import csv
    import io
    try:
        filas = list(csv.DictReader(io.StringIO(texto, newline="")))
        recs = desaplanar_contrato(filas, c, obj.get("header", {}))
    except Exception as e:
        return Resultado("no_reversible", causa=f"decodificación CSV falla: {e}")
    reg_ok = comparar(obj[c.records_key], recs)
    det = {"registros": reg_ok.estado, "causa_registros": reg_ok.causa}
    if obj.get("header"):
        return Resultado("no_reversible", detalle=det,
                         causa=f"el CSV descarta los metadatos del documento (header con {len(obj['header'])} claves: {', '.join(obj['header'])}); "
                               f"solo los registros se reconstruyen: {reg_ok.estado}")
    return Resultado(reg_ok.estado, reg_ok.causa, reg_ok.normalizaciones, det)


# ------------------------------------------------------------------ TOON
def _node(cmd: Sequence[str], entrada: Any) -> Any:
    r = subprocess.run(list(cmd), input=json.dumps(entrada, ensure_ascii=False, separators=(",", ":")).encode("utf-8"),
                       capture_output=True, check=True, cwd=str(ROOT))
    return json.loads(r.stdout.decode("utf-8"))


def decodificar_toon_lote(textos: Sequence[str]) -> List[Tuple[bool, Any]]:
    """Decodificador oficial de TOON en modo estricto (un solo proceso node para todo el lote)."""
    if not textos:
        return []
    res = _node(NODE_DECODE, list(textos))
    return [(bool(r["ok"]), r.get("value", r.get("error"))) for r in res]


def verificar_toon(obj: Any, decodificado: Tuple[bool, Any]) -> Resultado:
    ok, valor = decodificado
    if not ok:
        return Resultado("no_reversible", causa=f"TOON estricto no decodifica: {valor}")
    return comparar(obj, valor)


def verificar_toon_plano_contrato(obj: Dict[str, Any], decodificado: Tuple[bool, Any], c) -> Resultado:
    ok, valor = decodificado
    if not ok:
        return Resultado("no_reversible", causa=f"TOON estricto no decodifica: {valor}")
    try:
        rec = {"header": valor["header"], c.records_key: desaplanar_contrato(valor[c.records_key], c, obj.get("header", {}))}
    except Exception as e:
        return Resultado("no_reversible", causa=f"desaplanado por contrato falla: {e}")
    r = comparar(obj, rec)
    r.detalle["decodificacion"] = "decodificador TOON oficial + inversa del aplanado por contrato"
    return r


# ------------------------------------------------------------------ .mini
def verificar_mini(obj: Dict[str, Any], texto: str, c) -> Resultado:
    try:
        canon = parse(texto, c).to_canonical()
    except Exception as e:
        return Resultado("no_reversible", causa=f"minifmt.parse falla: {e}")
    rec = {"header": {k: v for k, v in canon["header"].items()}, c.records_key: canon[c.records_key]}
    extra = []
    for k in ("n", "v"):
        if k not in obj.get("header", {}) and k in rec["header"]:
            del rec["header"][k]
            extra.append(f"header.{k} lo añade el serializador .mini")
    r = comparar(obj, rec, extra)
    if r.aceptado:
        if dumps(canon, c) != texto:
            return Resultado("no_reversible", causa="el texto .mini no es estable: dumps(parse(texto)) != texto")
    return r


# ------------------------------------------------------ variantes reversibles de baselines.py
def variantes_aplanadas(obj: Dict[str, Any], c) -> Dict[str, Tuple[Any, dict]]:
    """Las dos variantes de aplanado genérico de ``baselines.flatten`` (o su error)."""
    out: Dict[str, Any] = {}
    for nombre, expandir in (("celdas", False), ("columnas", True)):
        try:
            out[nombre] = B.flatten(obj, c.records_key, expand_arrays=expandir)
        except Exception as e:  # p. ej. claves numéricas ambiguas
            out[nombre] = e
    return out


def _sin_tokens(t: Any) -> bool:
    return isinstance(t, Exception)


def comparadores_reversibles(docs: Sequence[Dict[str, Any]], c) -> List[Dict[str, Dict[str, Any]]]:
    """Comparadores con esquema/mapa de ``benchmark/public`` para cada documento.

    Devuelve, por documento, ``{formato: {texto, mapa, resultado}}`` con los formatos
    ``xml_tipado``, ``csv_rev:celdas``, ``csv_rev:columnas``, ``toon_rev:celdas`` y
    ``toon_rev:columnas``. Cada uno se verifica de ida y vuelta al generarse.
    """
    planos = [variantes_aplanadas(d, c) for d in docs]
    a_node: List[Any] = []
    indice: List[Tuple[int, str]] = []
    for i, p in enumerate(planos):
        for nombre, v in p.items():
            if not _sin_tokens(v):
                a_node.append(v[0])
                indice.append((i, nombre))
    toon = B.toon_batch(a_node, TOON_BRIDGE) if a_node else []
    toon_por = {k: toon[j] for j, k in enumerate(indice)}
    out: List[Dict[str, Dict[str, Any]]] = []
    for i, d in enumerate(docs):
        entrada: Dict[str, Dict[str, Any]] = {}
        try:
            xt = B.xml_encode(d)
            entrada["xml_tipado"] = {"texto": xt, "mapa": "", "resultado": verificar_xml_tipado(d, xt)}
        except Exception as e:
            entrada["xml_tipado"] = {"texto": "", "mapa": "", "resultado": Resultado("no_reversible", causa=f"xml_encode falla: {e}")}
        for nombre in ("celdas", "columnas"):
            v = planos[i][nombre]
            if _sin_tokens(v):
                causa = f"aplanado genérico imposible: {v}"
                for pref in ("csv_rev", "toon_rev"):
                    entrada[f"{pref}:{nombre}"] = {"texto": "", "mapa": "", "resultado": Resultado("no_reversible", causa=causa)}
                continue
            flat, esquema = v
            try:
                texto_csv = B.csv_encode(flat, esquema)
                r = comparar(d, B.csv_decode(texto_csv, esquema))
            except Exception as e:
                texto_csv, r = "", Resultado("no_reversible", causa=f"csv con esquema falla: {e}")
            entrada[f"csv_rev:{nombre}"] = {"texto": texto_csv, "mapa": B.compact(esquema), "resultado": r}
            t = toon_por[(i, nombre)]
            try:
                r = comparar(d, B.unflatten(t["decoded"], esquema))
            except Exception as e:
                r = Resultado("no_reversible", causa=f"toon aplanado con esquema falla: {e}")
            esquema_toon = {**esquema, "columns": [{k: v2 for k, v2 in col.items() if k != "csv_type"} for col in esquema["columns"]]}
            entrada[f"toon_rev:{nombre}"] = {"texto": t["text"], "mapa": B.compact(esquema_toon), "resultado": r}
        out.append(entrada)
    return out


# ------------------------------------------------------------------ lote completo
FORMATOS_ARCHIVADOS = ["json_pretty", "json_compact", "yaml", "xml", "csv", "toon", "toon_flat", "mini"]


def verificar_lote(docs: Sequence[Dict[str, Any]], textos: Sequence[Dict[str, str]], c) -> List[Dict[str, Resultado]]:
    """Verifica los 8 formatos archivados de cada documento (un solo node para el TOON del lote)."""
    a_dec: List[str] = []
    for t in textos:
        a_dec.extend([t["toon"], t["toon_flat"]])
    dec = decodificar_toon_lote(a_dec)
    out: List[Dict[str, Resultado]] = []
    for i, (d, t) in enumerate(zip(docs, textos)):
        out.append({
            "json_pretty": verificar_json(d, t["json_pretty"]),
            "json_compact": verificar_json(d, t["json_compact"]),
            "yaml": verificar_yaml(d, t["yaml"]),
            "xml": verificar_xml_contrato(d, t["xml"], c),
            "csv": verificar_csv_contrato(d, t["csv"], c),
            "toon": verificar_toon(d, dec[2 * i]),
            "toon_flat": verificar_toon_plano_contrato(d, dec[2 * i + 1], c),
            "mini": verificar_mini(d, t["mini"], c),
        })
    return out
