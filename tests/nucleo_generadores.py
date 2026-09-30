"""Estrategias de Hypothesis para generar objetos canónicos válidos de un contrato .mini, y contratos al azar.

Módulo de apoyo de tests/test_nucleo_propiedades.py (no es una prueba). Los textos generados son «canónicos»
en el sentido del ADR 0017 (propuesta): sin espacio exterior, sin ``\\r`` y no vacíos cuando el campo lo exige,
porque para el resto de cadenas el serializador no garantiza la ida y vuelta (D-1 de la auditoría V5).
"""
from __future__ import annotations

import datetime
import decimal
import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

from hypothesis import strategies as st

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "conformance" / "oraculo"))

from decodificador import ESPACIOS  # noqa: E402
from minifmt.contract import Contract, Field, HeaderKey  # noqa: E402

ENTERO_SEGURO = 2 ** 53 - 1
ESPECIALES = [chr(c) for c in (0x7C, 0x2C, 0x2A, 0x5C, 0x22, 0x3B, 0x3D, 0x3A, 0x20, 0x09, 0xA0, 0x3000, 0x2028, 0x85, 0x0A)] + [
    chr(0x5C) + "n", chr(0x5C) + chr(0x7C), chr(0x22) * 2, "*,", " ,", chr(0xE9), chr(0xF1), chr(0x20AC), chr(0x1F600),
    "e" + chr(0x301), chr(0x661), "5", "-", ".",
]


def es_canonico(s: str) -> bool:
    """Cadena que el serializador escribe y el parser devuelve idéntica (ver ADR 0017)."""
    return "\r" not in s and (s == "" or (ord(s[0]) not in ESPACIOS and ord(s[-1]) not in ESPACIOS))


_ALFABETO = st.one_of(
    st.sampled_from(ESPECIALES),
    st.characters(blacklist_categories=("Cs",), blacklist_characters=chr(13)),
)
# piezas que pueden ir en un extremo: no empiezan ni acaban en espacio (por eso no se filtra al final, que rechazaría casi todo)
_BORDE = _ALFABETO.filter(lambda s: s != "" and ord(s[0]) not in ESPACIOS and ord(s[-1]) not in ESPACIOS)


def texto(minimo: int = 0, maximo: int = 14) -> st.SearchStrategy[str]:
    """Cadena canónica (ver es_canonico); con ``minimo`` >= 1 nunca es vacía."""
    no_vacio = st.one_of(
        _BORDE,
        st.tuples(_BORDE, st.lists(_ALFABETO, max_size=max(0, maximo - 2)), _BORDE).map(lambda t: t[0] + "".join(t[1]) + t[2]),
    )
    return no_vacio if minimo >= 1 else st.one_of(st.just(""), no_vacio)


# --------------------------------------------------------------------------------------------- escalares
def _num(limite: Any, por_omision: float) -> float:
    return por_omision if limite is None else float(limite)


def escalar(tipo: str, f: Field, valores: Optional[List[str]] = None, con_rango: bool = True) -> st.SearchStrategy[Any]:
    lo = f.min if con_rango else None
    hi = f.max if con_rango else None
    if tipo == "str":
        return texto(1)
    if tipo == "int":
        a = -ENTERO_SEGURO if lo is None else int(lo)
        b = ENTERO_SEGURO if hi is None else int(hi)
        return st.integers(a, b)
    if tipo == "float":
        return st.floats(min_value=None if lo is None else float(lo), max_value=None if hi is None else float(hi),
                         allow_nan=False, allow_infinity=False)
    if tipo == "bool":
        return st.booleans()
    if tipo == "enum":
        return st.sampled_from(valores or [])
    if tipo == "date":
        a = datetime.date.fromisoformat(lo) if isinstance(lo, str) else datetime.date(1, 1, 1)
        b = datetime.date.fromisoformat(hi) if isinstance(hi, str) else datetime.date(9999, 12, 31)
        return st.dates(a, b).map(lambda d: d.isoformat())
    if tipo == "decimal":
        if lo is not None or hi is not None:
            a = decimal.Decimal(str(lo)) if lo is not None else decimal.Decimal(-10 ** 6)
            b = decimal.Decimal(str(hi)) if hi is not None else decimal.Decimal(10 ** 6)
            return st.decimals(min_value=a, max_value=b, places=2, allow_nan=False, allow_infinity=False).map(_dec_texto)
        entera = st.from_regex(r"0|[1-9][0-9]{0,24}", fullmatch=True)
        frac = st.one_of(st.just(""), st.from_regex(r"\.[0-9]{1,30}", fullmatch=True))
        return st.tuples(st.booleans(), entera, frac).map(lambda t: _dec_canonico(("-" if t[0] else "") + t[1] + t[2]))
    raise AssertionError(tipo)


def _dec_texto(d: decimal.Decimal) -> str:
    return _dec_canonico(format(d, "f"))


def _dec_canonico(t: str) -> str:
    signo = "-" if t.startswith("-") else ""
    cuerpo = t.lstrip("-")
    entera, _, frac = cuerpo.partition(".")
    if set(entera) <= {"0"} and set(frac) <= {"0"}:
        signo = ""
    return signo + (entera.lstrip("0") or "0") + ("." + frac if frac else "")


# --------------------------------------------------------------------------------------------- campos
def elemento(f: Field) -> st.SearchStrategy[Any]:
    tipo = f.item
    if tipo == "str":
        return texto(0, 12)  # el elemento vacío es válido (ADR 0013)
    return escalar(tipo, f, f.item_values, con_rango=False)


def valor_campo(f: Field, cuenta: Optional[int] = None) -> st.SearchStrategy[Any]:
    """Valor de un campo de registro; para un mlist devuelve (elementos, selección)."""
    if f.type in ("list", "mlist"):
        lo = 0 if f.min is None else int(f.min)
        hi = 5 if f.max is None else int(f.max)
        minimo = lo if f.optional is False else max(lo, 1)
        if f.type == "mlist" and f.marker in ("exactly_one", "at_least_one"):
            minimo = max(minimo, 1)
        if f.optional and hi < minimo:
            return st.none()  # un maximo de 0 en un campo opcional solo admite null
        if cuenta is not None:
            tamanos = st.just(cuenta)
        else:
            tamanos = st.integers(minimo, max(minimo, min(hi, 6)))
        if f.type == "list":
            base = tamanos.flatmap(lambda k: st.lists(elemento(f), min_size=k, max_size=k))
        else:
            def con_seleccion(k: int):
                items = st.lists(elemento(f), min_size=k, max_size=k)
                if f.marker == "exactly_one":
                    sel = st.integers(0, k - 1)
                elif f.marker == "at_most_one":
                    sel = st.one_of(st.none(), st.integers(0, k - 1)) if k else st.none()
                else:
                    sel = st.lists(st.integers(0, k - 1), unique=True, min_size=1 if f.marker == "at_least_one" else 0,
                                   max_size=k).map(sorted) if k else st.just([])
                return st.tuples(items, sel)
            base = tamanos.flatmap(con_seleccion)
        return st.one_of(st.none(), base) if f.optional else base
    if f.type == "tuple":
        comps = {c.name: (st.one_of(st.none(), _componente(c)) if c.optional else _componente(c)) for c in f.items}
        base = st.fixed_dictionaries(comps)
        return st.one_of(st.none(), base) if f.optional else base
    base = escalar(f.type, f, f.values)
    return st.one_of(st.none(), base) if f.optional else base


def _componente(c: Field) -> st.SearchStrategy[Any]:
    return escalar(c.type, c, c.values)


def _clave_cabecera(hk: HeaderKey) -> st.SearchStrategy[Any]:
    f = hk.as_field()
    if hk.type == "list":
        return st.lists(escalar(hk.item, f, None, con_rango=False), min_size=0, max_size=4)
    if hk.type == "tuple":
        return st.fixed_dictionaries({c.name: escalar(c.type, c, c.values) for c in hk.items})
    return escalar(hk.type, f, hk.values)


@st.composite
def objeto(draw, c: Contract, max_registros: int = 4) -> Dict[str, Any]:
    """Objeto canónico válido bajo ``c`` (con los registros en la forma del §7)."""
    n = draw(st.integers(0, max_registros))
    cabecera: Dict[str, Any] = {}
    for k, hk in c.header_keys.items():
        if k in ("n", "v"):
            continue
        # una clave con valor por omisión se escribe siempre: si se omitiera, parse la añadiría y dumps(parse(t)) != t (D-10, ADR 0017)
        if hk.required or hk.default is not None or draw(st.booleans()):
            cabecera[k] = draw(_clave_cabecera(hk))
    if draw(st.booleans()):
        cabecera["zz_extra"] = draw(texto(1, 10))  # clave no declarada: se conserva como cadena
    cuentas: Dict[str, int] = {}
    for f in c.fields:
        if f.count_key:
            lo = 0 if f.min is None else int(f.min)
            hi = 5 if f.max is None else int(f.max)
            k = draw(st.integers(max(lo, 1) if not f.optional else lo, max(lo, min(hi, 5))))
            cabecera[f.count_key] = k
            cuentas[f.name] = k
    unicos = {f.name: draw(st.lists(valor_campo(Field(name=f.name, type=f.type, values=f.values, min=f.min, max=f.max)),
                                    min_size=n, max_size=n, unique=True)) for f in c.fields if f.unique}
    registros: List[Dict[str, Any]] = []
    for i in range(n):
        rec: Dict[str, Any] = {}
        for f in c.fields:
            if f.name in unicos:
                rec[f.name] = unicos[f.name][i]
                continue
            v = draw(valor_campo(f, cuentas.get(f.name)))
            if f.type == "mlist":
                rec[f.json_items], rec[f.json_selected] = (None, None) if v is None else v
            else:
                rec[f.name] = v
        registros.append(rec)
    return {"prefix": c.prefix, "header": cabecera, c.records_key: registros}


def cabecera_esperada(c: Contract, cabecera: Dict[str, Any], n: int) -> Dict[str, Any]:
    """Cabecera canónica que debe devolver el parser: la dada, ``n``, ``v`` y los valores por omisión."""
    out = dict(cabecera)
    out["n"] = n
    for k, hk in c.header_keys.items():
        if k not in out and hk.default is not None:
            out[k] = hk.default
    return out


# --------------------------------------------------------------------------------------------- contratos
_ESCALARES = ["str", "int", "float", "bool", "enum", "date", "decimal"]


@st.composite
def _campo(draw, nombre: str, opcional: bool, unico_permitido: bool) -> Dict[str, Any]:
    tipo = draw(st.sampled_from(_ESCALARES + ["list", "mlist", "tuple"]))
    d: Dict[str, Any] = {"name": nombre, "type": tipo}
    if opcional:
        d["optional"] = True
    if tipo == "int" and draw(st.booleans()):
        a = draw(st.integers(-50, 50))
        d["min"], d["max"] = a, a + draw(st.integers(0, 100))
    if tipo == "float" and draw(st.booleans()):
        a = draw(st.integers(-50, 50))
        d["min"], d["max"] = float(a), float(a + draw(st.integers(0, 100)))
    if tipo == "date" and draw(st.booleans()):
        d["min"], d["max"] = "1900-01-01", "2100-12-31"
    if tipo == "decimal" and draw(st.booleans()):
        d["min"], d["max"] = "-1000", "1000"
    if tipo == "enum":
        d["values"] = draw(st.lists(st.sampled_from(["a", "b", "x y", "p|q", "é", "1"]), min_size=1, max_size=4, unique=True))
    if tipo in ("list", "mlist"):
        item = draw(st.sampled_from(_ESCALARES))
        d["item"] = item
        if item == "enum":
            d["item_values"] = draw(st.lists(st.sampled_from(["a", "b", "c,d", "e*"]), min_size=1, max_size=3, unique=True))
        if draw(st.booleans()):
            lo = draw(st.integers(0, 2))
            d["min"], d["max"] = lo, lo + draw(st.integers(0, 4))
        if tipo == "mlist":
            d["marker"] = draw(st.sampled_from(["exactly_one", "at_least_one", "at_most_one", "any"]))
            d["json"] = {"items": f"{nombre}_items", "selected": f"{nombre}_sel"}  # dos mlist en un contrato no pueden compartir claves
            if d["marker"] in ("exactly_one", "at_least_one") and d.get("min", 1) < 1:
                d["min"], d["max"] = 1, max(1, d.get("max", 1))
    if tipo == "tuple":
        n = draw(st.integers(1, 3))
        d["items"] = [{"name": "abc"[i], "type": draw(st.sampled_from(_ESCALARES)), **({"optional": True} if draw(st.booleans()) else {})}
                      for i in range(n)]
        for comp in d["items"]:
            if comp["type"] == "enum":
                comp["values"] = ["u", "v"]
        if n == 1:
            # una tupla de un solo componente opcional con valor null se escribe como campo vacío, que el parser lee
            # como tupla vacía (E07) o, si es el único campo, como línea en blanco (D-11, ADR 0017)
            d["items"][0].pop("optional", None)
    if unico_permitido and tipo in ("list", "mlist"):
        # el primer campo del nucleo no puede escribirse vacio: un registro con todos los campos vacios es una linea en
        # blanco y desaparece (D-11, ADR 0017)
        d["min"] = max(d.get("min", 0), 1)
        d["max"] = max(d.get("max", 1), d["min"])
    if unico_permitido and tipo in ("str", "int", "date", "decimal") and not opcional and draw(st.booleans()):
        d["unique"] = True
        d.pop("min", None) if tipo == "int" else None  # un rango pequeño no admite n valores distintos
        d.pop("max", None) if tipo == "int" else None
    return d


@st.composite
def contrato_aleatorio(draw) -> Dict[str, Any]:
    nucleo = [draw(_campo(f"c{i}", False, i == 0)) for i in range(draw(st.integers(1, 4)))]
    ext = [draw(_campo(f"e{i}", True, False)) for i in range(draw(st.integers(0, 3)))]
    claves = {}
    for i in range(draw(st.integers(0, 2))):
        tipo = draw(st.sampled_from(["str", "int", "bool", "date", "list", "tuple"]))
        k: Dict[str, Any] = {"type": tipo}
        if tipo == "list":
            k["item"] = draw(st.sampled_from(["str", "int", "date"]))
        if tipo == "tuple":
            k["items"] = [{"name": "a", "type": "int"}, {"name": "b", "type": "str"}]
        if tipo == "str" and draw(st.booleans()):
            k["default"] = "es"
        claves[f"k{i}"] = k
    return {
        "prefix": draw(st.sampled_from(["p", "q9", "tx-1", "Z_z"])), "version": 1, "records_key": "rows",
        "list_separator": draw(st.sampled_from([",", ",", ";", "/", ":", "#", "~"])),
        "header": {"keys": claves, "required": ["n"] + [k for k in claves if draw(st.booleans())]},
        "core": nucleo, "extensions": ext,
    }


# --------------------------------------------------------------------------------------------- motor JS
class ServidorJS:
    """Proceso de Node persistente que analiza y serializa con js/mini.js (una consulta JSON por línea)."""

    def __init__(self) -> None:
        self.proc = subprocess.Popen(
            [shutil.which("node") or "node", "--no-warnings", str(ROOT / "tests" / "nucleo_servidor_js.mjs")],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding="utf-8", bufsize=1)

    def consultar(self, operacion: str, contrato: Dict[str, Any], dato: Any) -> Dict[str, Any]:
        assert self.proc.stdin is not None and self.proc.stdout is not None
        self.proc.stdin.write(json.dumps({"op": operacion, "contrato": contrato, "dato": dato}, ensure_ascii=False) + "\n")
        self.proc.stdin.flush()
        linea = self.proc.stdout.readline()
        if not linea:
            raise RuntimeError("el servidor de Node terminó: " + (self.proc.stderr.read() if self.proc.stderr else ""))
        return json.loads(linea)

    def cerrar(self) -> None:
        if self.proc.stdin:
            self.proc.stdin.close()
        self.proc.wait(timeout=10)


def hay_node() -> bool:
    return shutil.which("node") is not None
