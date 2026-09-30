"""Decodificador de referencia INDEPENDIENTE de .mini, escrito desde SPEC.md §3-§8.

No importa ``minifmt`` (ni su parser, ni su codec, ni sus valores): lee el contrato como JSON puro y
reimplementa la gramática de la especificación con otra estructura (un escáner de caracteres en vez de
los pares (carácter, escapado) del código de la biblioteca). Sirve de oráculo para comparar el parser
Python y ``js/mini.js`` sobre todo el corpus de conformidad y sobre documentos generados, de modo que
parser y serializador de la biblioteca no validen su propio defecto.

    decodificar(texto, contrato_json, estricto=True) -> Resultado(canonico, errores)

``errores`` es un conjunto de pares ``(código, línea)`` (línea física 1-based; 0 para errores de documento).
``canonico`` es el objeto canónico del §7 (en modo estricto, ``None`` si hay errores; en modo tolerante,
con los registros válidos).

Zonas en las que la SPEC calla y este oráculo adopta una lectura que se declara aquí (ADR 0017 y las
auditorías V5 las tratan como decisiones de norma pendientes; no son defectos del oráculo):

* Conjunto «whitespace» del §3.5: ``ESPACIOS`` (la lista de ``str.isspace()`` de Python, escrita punto por punto).
* Una entrada de cabecera vacía (``hd|n=1|``) se omite; el §4 no la admite pero tampoco le asigna un código.
* Tras un error E09 en una cabecera, el modo tolerante recupera el resto de la cabecera leyendo ``\\x``
  inválido como los dos caracteres literales; los demás motores hacen lo mismo. Solo se compara el contenido
  de la cabecera en modo estricto.
* Se informa a lo sumo UN error por campo (el primero según el orden: aridad, elementos, regla del marcador),
  aunque el §8 dice «cada error»; las suites de conformidad comparan conjuntos de pares.
"""
from __future__ import annotations

import datetime
import decimal
import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Set, Tuple

# Caracteres que el §3.5 recorta (punto de código a punto de código).
ESPACIOS = frozenset(
    [0x09, 0x0A, 0x0B, 0x0C, 0x0D, 0x1C, 0x1D, 0x1E, 0x1F, 0x20, 0x85, 0xA0, 0x1680]
    + list(range(0x2000, 0x200B)) + [0x2028, 0x2029, 0x202F, 0x205F, 0x3000]
)
ESCAPES_FIJOS = {"|": "|", ",": ",", "*": "*", '"': '"', "\\": "\\", "n": "\n"}

ENTERO = re.compile(r"-?[0-9]+")
FLOTANTE = re.compile(r"-?[0-9]+(\.[0-9]+)?([eE][+-]?[0-9]+)?")
DECIMAL = re.compile(r"(-?)([0-9]+)(\.[0-9]+)?")
FECHA = re.compile(r"([0-9]{4})-([0-9]{2})-([0-9]{2})")


class ErrorOraculo(Exception):
    def __init__(self, codigo: str, linea: int):
        super().__init__(f"{codigo}@{linea}")
        self.codigo, self.linea = codigo, linea


@dataclass
class Resultado:
    canonico: Optional[Dict[str, Any]]
    errores: Set[Tuple[str, int]]


def es_espacio(ch: str) -> bool:
    return ord(ch) in ESPACIOS


# ---------------------------------------------------------------------------------------------
# §3.3 Escapes: la línea pasa a una lista de caracteres con la marca «escapado»
# ---------------------------------------------------------------------------------------------
Car = Tuple[str, bool]


def escanear(linea: str, sep: str, linea_no: int, tolerante: bool = False) -> List[Car]:
    salida: List[Car] = []
    i = 0
    while i < len(linea):
        c = linea[i]
        if c != "\\":
            salida.append((c, False))
            i += 1
            continue
        if i + 1 >= len(linea):
            raise ErrorOraculo("E09", linea_no)  # barra invertida final
        s = linea[i + 1]
        if s in ESCAPES_FIJOS:
            salida.append((ESCAPES_FIJOS[s], True))
        elif s == sep:
            salida.append((sep, True))
        elif tolerante:
            salida.append(("\\", True))
            salida.append((s, True))
        else:
            raise ErrorOraculo("E09", linea_no)
        i += 2
    return salida


def recortar(cs: List[Car]) -> List[Car]:
    """§3.5: se recorta el espacio exterior que está escrito en el texto (no el que produce un escape)."""
    a, b = 0, len(cs)
    while a < b and not cs[a][1] and es_espacio(cs[a][0]):
        a += 1
    while b > a and not cs[b - 1][1] and es_espacio(cs[b - 1][0]):
        b -= 1
    return cs[a:b]


def dividir(cs: List[Car], delim: str) -> List[List[Car]]:
    partes: List[List[Car]] = [[]]
    for c in cs:
        if c[0] == delim and not c[1]:
            partes.append([])
        else:
            partes[-1].append(c)
    return partes


def texto(cs: List[Car]) -> str:
    return "".join(c for c, _ in cs)


# ---------------------------------------------------------------------------------------------
# §3.4 Elementos de lista
# ---------------------------------------------------------------------------------------------
def elementos(campo: List[Car], sep: str, linea_no: int) -> List[Tuple[str, bool]]:
    """Divide un campo de tipo lista en (texto, marcado). Campo vacío: lista vacía."""
    if not campo:
        return []
    res: List[Tuple[str, bool]] = []
    i, n = 0, len(campo)

    def libre(k: int) -> bool:
        return not campo[k][1]

    while True:
        while i < n and libre(i) and es_espacio(campo[i][0]):
            i += 1
        if i < n and libre(i) and campo[i][0] == '"':
            i += 1
            buf: List[str] = []
            cerrado = False
            while i < n:
                ch, esc = campo[i]
                if ch == '"' and not esc:
                    if i + 1 < n and campo[i + 1][0] == '"' and not campo[i + 1][1]:
                        buf.append('"')
                        i += 2
                        continue
                    cerrado = True
                    i += 1
                    break
                buf.append(ch)
                i += 1
            if not cerrado:
                raise ErrorOraculo("E09", linea_no)
            marcado = False
            if buf and buf[-1] == "*" and not campo[i - 2][1]:  # «…*» justo antes de la comilla de cierre
                marcado = True
                buf.pop()
            while i < n and libre(i) and es_espacio(campo[i][0]):
                i += 1
            if i < n and libre(i) and campo[i][0] == "*":
                marcado = True
                i += 1
            while i < n and libre(i) and es_espacio(campo[i][0]):
                i += 1
            if i < n and not (libre(i) and campo[i][0] == sep):
                raise ErrorOraculo("E09", linea_no)
            res.append(("".join(buf), marcado))
        else:
            j = i
            while j < n and not (libre(j) and campo[j][0] == sep):
                j += 1
            trozo = recortar(campo[i:j])
            marcado = False
            if trozo and not trozo[-1][1] and trozo[-1][0] == "*":
                marcado = True
                trozo = recortar(trozo[:-1])
            res.append((texto(trozo), marcado))
            i = j
        if i >= n:
            break
        i += 1  # separador
        if i >= n:  # separador final: último elemento vacío
            res.append(("", False))
            break
    return res


# ---------------------------------------------------------------------------------------------
# §4/§6 Escalares
# ---------------------------------------------------------------------------------------------
def fecha_valida(t: str) -> bool:
    m = FECHA.fullmatch(t)
    if not m:
        return False
    try:
        datetime.date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    except ValueError:
        return False
    return True


def decimal_canonico(t: str) -> Optional[str]:
    m = DECIMAL.fullmatch(t)
    if not m:
        return None
    signo, entera, frac = m.group(1), m.group(2).lstrip("0") or "0", m.group(3) or ""
    if entera == "0" and set(frac[1:]) <= {"0"}:
        signo = ""
    return signo + entera + frac


def _limite_decimal(v: Any) -> decimal.Decimal:
    if isinstance(v, str):
        return decimal.Decimal(decimal_canonico(v) or "0")
    return decimal.Decimal(int(v))


def escalar(t: str, tipo: str, campo: Dict[str, Any], linea_no: int, valores: Optional[List[str]],
            con_rango: bool) -> Any:
    if tipo == "str":
        return t
    if tipo == "int":
        if not ENTERO.fullmatch(t):
            raise ErrorOraculo("E06", linea_no)
        v: Any = int(t)
    elif tipo == "float":
        if not FLOTANTE.fullmatch(t):
            raise ErrorOraculo("E06", linea_no)
        v = float(t)
        if v != v or v in (float("inf"), float("-inf")):
            raise ErrorOraculo("E06", linea_no)
    elif tipo == "bool":
        if t in ("true", "1"):
            return True
        if t in ("false", "0"):
            return False
        raise ErrorOraculo("E06", linea_no)
    elif tipo == "enum":
        if valores is None or t not in valores:
            raise ErrorOraculo("E10", linea_no)
        return t
    elif tipo == "date":
        if not fecha_valida(t):
            raise ErrorOraculo("E06", linea_no)
        v = t
    elif tipo == "decimal":
        v = decimal_canonico(t)
        if v is None:
            raise ErrorOraculo("E06", linea_no)
    else:
        raise ErrorOraculo("E06", linea_no)
    if con_rango:
        lo, hi = campo.get("min"), campo.get("max")
        if tipo == "decimal":
            d = decimal.Decimal(v)
            if (lo is not None and d < _limite_decimal(lo)) or (hi is not None and d > _limite_decimal(hi)):
                raise ErrorOraculo("E13", linea_no)
        elif (lo is not None and v < lo) or (hi is not None and v > hi):
            raise ErrorOraculo("E13", linea_no)
    return v


class Marcada(tuple):
    """Resultado de una lista marcada: (elementos, selección)."""


def campo_compuesto(cs: List[Car], c: Dict[str, Any], sep: str, linea_no: int, cabecera: Dict[str, Any]) -> Any:
    tipo = c["type"]
    opcional = bool(c.get("optional"))
    if tipo in ("list", "mlist"):
        if not cs and opcional:
            return Marcada((None, None)) if tipo == "mlist" else None
        elems = elementos(cs, sep, linea_no)
        lo, hi = c.get("min"), c.get("max")
        if not elems and not opcional and lo is not None and lo > 0:
            raise ErrorOraculo("E07", linea_no)
        if lo is not None and len(elems) < lo:
            raise ErrorOraculo("E07", linea_no)
        if hi is not None and len(elems) > hi:
            raise ErrorOraculo("E07", linea_no)
        clave = c.get("count_key")
        if clave and isinstance(cabecera.get(clave), int) and not isinstance(cabecera.get(clave), bool) \
                and len(elems) != cabecera[clave]:
            raise ErrorOraculo("E07", linea_no)
        tipo_item = c.get("item", "str")
        items = [escalar(t, tipo_item, c, linea_no, c.get("item_values"), False) for t, _ in elems]
        marcados = [i for i, (_, m) in enumerate(elems) if m]
        if tipo == "list":
            if marcados:
                raise ErrorOraculo("E08", linea_no)
            return items
        regla = c.get("marker", "exactly_one")
        if regla == "exactly_one" and len(marcados) != 1:
            raise ErrorOraculo("E08", linea_no)
        if regla == "at_least_one" and len(marcados) < 1:
            raise ErrorOraculo("E08", linea_no)
        if regla == "at_most_one" and len(marcados) > 1:
            raise ErrorOraculo("E08", linea_no)
        if regla in ("exactly_one", "at_most_one"):
            return Marcada((items, marcados[0] if marcados else None))
        return Marcada((items, marcados))
    # tupla
    partes = elementos(cs, sep, linea_no)
    if not partes and opcional:
        return None
    comps = c["items"]
    if len(partes) != len(comps):
        raise ErrorOraculo("E07", linea_no)
    salida: Dict[str, Any] = {}
    for comp, (t, m) in zip(comps, partes):
        if m:
            raise ErrorOraculo("E08", linea_no)
        if t == "":
            if comp.get("optional"):
                salida[comp["name"]] = comp.get("default")
                continue
            raise ErrorOraculo("E06", linea_no)
        salida[comp["name"]] = escalar(t, comp["type"], comp, linea_no, comp.get("values"), True)
    return salida


def campo_de_registro(cs: List[Car], c: Dict[str, Any], sep: str, linea_no: int, cabecera: Dict[str, Any]) -> Any:
    tipo = c["type"]
    if tipo in ("list", "mlist", "tuple"):
        return campo_compuesto(cs, c, sep, linea_no, cabecera)
    t = texto(cs)
    if t == "":
        if c.get("optional"):
            return c.get("default")
        raise ErrorOraculo("E06", linea_no)
    return escalar(t, tipo, c, linea_no, c.get("values"), True)


# ---------------------------------------------------------------------------------------------
# §5 Cabecera
# ---------------------------------------------------------------------------------------------
def normalizar_contrato(d: Dict[str, Any]) -> Dict[str, Any]:
    """Lectura mínima del contrato JSON: extensiones opcionales y claves de cabecera n y v implícitas."""
    claves = dict(d.get("header", {}).get("keys", {}))
    claves.setdefault("n", {"type": "int"})
    claves.setdefault("v", {"type": "int", "default": 1})
    requeridas = set(d.get("header", {}).get("required", ["n"])) | {"n"}
    ext = [dict(f, optional=True) for f in d.get("extensions", [])]
    return {
        "prefix": d["prefix"], "version": int(d.get("version", 1)), "sep": d.get("list_separator", ","),
        "claves": claves, "requeridas": requeridas, "nucleo": d.get("core", []), "ext": ext,
        "records_key": d.get("records_key", "records"),
    }


def cabecera(linea: str, linea_no: int, c: Dict[str, Any]) -> Tuple[str, Dict[str, Any], Set[Tuple[str, int]], Set[str]]:
    errores: Set[Tuple[str, int]] = set()
    try:
        campos = [recortar(p) for p in dividir(escanear(linea, c["sep"], linea_no), "|")]
    except ErrorOraculo as e:
        errores.add((e.codigo, e.linea))
        seguro = linea[:-1] if (len(linea) - len(linea.rstrip("\\"))) % 2 else linea
        campos = [recortar(p) for p in dividir(escanear(seguro, c["sep"], linea_no, tolerante=True), "|")]
    prefijo = texto(campos[0]) if campos else ""
    cab: Dict[str, Any] = {}
    vistas: Set[str] = set()
    for cs in campos[1:]:
        if not texto(cs):
            continue
        eq = next((k for k, (ch, esc) in enumerate(cs) if ch == "=" and not esc), -1)
        if eq < 0:
            errores.add(("E12", linea_no))
            continue
        clave = texto(recortar(cs[:eq]))
        valor = recortar(cs[eq + 1:])
        if clave in vistas:
            errores.add(("E12", linea_no))
            continue
        vistas.add(clave)
        decl = c["claves"].get(clave)
        try:
            if decl is None:
                cab[clave] = texto(valor)
            elif decl.get("type") == "list":
                cab[clave] = [escalar(t, decl.get("item", "str"), decl, linea_no, decl.get("values"), False)
                              for t, _ in elementos(valor, c["sep"], linea_no)]
            elif decl.get("type") == "tuple":
                partes = elementos(valor, c["sep"], linea_no)
                if len(partes) != len(decl["items"]):
                    raise ErrorOraculo("E07", linea_no)
                cab[clave] = {comp["name"]: (escalar(t, comp["type"], comp, linea_no, comp.get("values"), True)
                                             if t != "" else None)
                              for comp, (t, _) in zip(decl["items"], partes)}
            else:
                cab[clave] = escalar(texto(valor), decl.get("type", "str"), decl, linea_no, decl.get("values"), True)
        except ErrorOraculo as e:
            errores.add((e.codigo, e.linea))
    for clave, decl in c["claves"].items():
        if clave not in vistas:
            if clave in c["requeridas"] and clave != "n":
                errores.add(("E12", linea_no))
            elif decl.get("default") is not None:
                cab[clave] = decl["default"]
    if "n" not in vistas:
        errores.add(("E03", linea_no))
    return prefijo, cab, errores, vistas


# ---------------------------------------------------------------------------------------------
# §3.1 Líneas y §6-§8 Documento
# ---------------------------------------------------------------------------------------------
def lineas_fisicas(doc: str) -> List[Tuple[int, str]]:
    if doc[:1] == "\ufeff":
        doc = doc[1:]
    salida = []
    for i, cruda in enumerate(doc.split("\n"), start=1):
        if cruda.endswith("\r"):
            cruda = cruda[:-1]
        if all(es_espacio(ch) for ch in cruda):
            continue
        salida.append((i, cruda))
    return salida


def _clave_unica(v: Any) -> Any:
    if isinstance(v, list):
        return ("L",) + tuple(_clave_unica(x) for x in v)
    if isinstance(v, dict):
        return ("D",) + tuple(sorted((k, _clave_unica(x)) for k, x in v.items()))
    return (type(v).__name__ if isinstance(v, bool) else "v", v)


def decodificar(doc: str, contrato: Dict[str, Any], estricto: bool = True) -> Resultado:
    c = normalizar_contrato(contrato)
    lineas = lineas_fisicas(doc)
    if not lineas:
        return Resultado(None, {("E01", 0)})
    errores: Set[Tuple[str, int]] = set()
    ln_cab, txt_cab = lineas[0]
    prefijo, cab, err_cab, vistas = cabecera(txt_cab, ln_cab, c)
    errores |= err_cab
    if prefijo != c["prefix"]:
        errores.add(("E02", ln_cab))
    version = cab.get("v", 1)
    version = version if isinstance(version, int) and not isinstance(version, bool) and version else 1
    campos = c["nucleo"] + c["ext"]
    registros: List[Dict[str, Any]] = []
    unicos: Dict[str, Set[Any]] = {f["name"]: set() for f in campos if f.get("unique")}
    for ln, linea in lineas[1:]:
        try:
            cs = [recortar(p) for p in dividir(escanear(linea, c["sep"], ln), "|")]
        except ErrorOraculo as e:
            errores.add((e.codigo, e.linea))
            continue
        nf = len(cs)
        if nf < len(c["nucleo"]):
            errores.add(("E05", ln))
            continue
        if nf > len(campos):
            if version > c["version"]:
                cs = cs[:len(campos)]
                nf = len(cs)
            else:
                errores.add(("E05", ln))
                continue
        reg: Dict[str, Any] = {}
        errores_reg: Set[Tuple[str, int]] = set()
        for i, f in enumerate(campos):
            if i >= nf:
                if f["type"] == "mlist":
                    reg[_json_items(f)], reg[_json_sel(f)] = None, None
                else:
                    reg[f["name"]] = f.get("default")
                continue
            try:
                val = campo_de_registro(cs[i], f, c["sep"], ln, cab)
            except ErrorOraculo as e:
                errores_reg.add((e.codigo, e.linea))
                continue
            if isinstance(val, Marcada):
                reg[_json_items(f)], reg[_json_sel(f)] = val
            else:
                reg[f["name"]] = val
        for nombre, vistos in unicos.items():
            v = reg.get(nombre)
            if v is not None and _clave_unica(v) in vistos:
                errores_reg.add(("E11", ln))
        if errores_reg:
            errores |= errores_reg
            continue
        for nombre, vistos in unicos.items():
            if reg.get(nombre) is not None:
                vistos.add(_clave_unica(reg[nombre]))
        registros.append(reg)
    n = cab.get("n")
    if isinstance(n, int) and not isinstance(n, bool) and n != len(lineas) - 1:
        errores.add(("E04", 0))
    canonico = {"prefix": prefijo, "header": cab, c["records_key"]: registros}
    if estricto and errores:
        return Resultado(None, errores)
    return Resultado(canonico, errores)


def _json_items(f: Dict[str, Any]) -> str:
    return f.get("json", {}).get("items", "items")


def _json_sel(f: Dict[str, Any]) -> str:
    return f.get("json", {}).get("selected", "correct" if f.get("marker", "exactly_one") == "exactly_one" else "selected")


def iguales(a: Any, b: Any) -> bool:
    """Igualdad del §7: los números se comparan numéricamente (-1 ≡ -1.0); claves como conjunto."""
    if isinstance(a, bool) or isinstance(b, bool):
        return isinstance(a, bool) and isinstance(b, bool) and a == b
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        return abs(float(a) - float(b)) <= 1e-12 * max(1.0, abs(float(a)), abs(float(b))) if (
            isinstance(a, float) or isinstance(b, float)) else a == b
    if isinstance(a, list) and isinstance(b, list):
        return len(a) == len(b) and all(iguales(x, y) for x, y in zip(a, b))
    if isinstance(a, dict) and isinstance(b, dict):
        return set(a) == set(b) and all(iguales(a[k], b[k]) for k in a)
    return a == b
