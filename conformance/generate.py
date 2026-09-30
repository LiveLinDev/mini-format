"""Genera la suite de conformidad de .mini (``conformance/cases/*.json``).

    python conformance/generate.py

Los resultados esperados NO se calculan con la implementación de referencia:
salen de los fixtures publicados de cada familia (``canonical.json``,
``escaping.json``, nombre del fixture negativo y línea alterada) o están
escritos a mano en este archivo a partir de SPEC.md.  ``run_python.py``
comprueba después que ``minifmt`` los cumple; cualquier discrepancia se
investiga en lugar de regenerar las expectativas desde el código.
"""
from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any, Dict, List, Optional

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
FORKS = ROOT / "forks"
CASES_DIR = HERE / "cases"

CASES: Dict[str, List[Dict[str, Any]]] = {}
SPEC_VERSION = "1.1"


def add(category: str, cid: str, description: str, *, mode: str = "strict", input: Any,
        family: Optional[str] = None, contract: Optional[dict] = None, parent: Any = None,
        canonical: Optional[dict] = None, errors: Optional[List[dict]] = None,
        mini: Optional[str] = None, rejected: Optional[bool] = None,
        diagnostics: Optional[dict] = None) -> None:
    assert (family is None) != (contract is None) or mode in ("contract",), cid
    case: Dict[str, Any] = {"id": cid, "category": category, "description": description, "mode": mode}
    if family is not None:
        case["family"] = family
    if contract is not None:
        case["contract"] = contract
    if parent is not None:
        case["parent"] = parent
    case["input"] = input
    exp: Dict[str, Any] = {}
    if canonical is not None:
        exp["canonical"] = canonical
    if errors is not None:
        exp["errors"] = errors
    if mini is not None:
        exp["mini"] = mini
    if rejected is not None:
        exp["rejected"] = rejected
    if diagnostics is not None:
        exp["diagnostics"] = diagnostics
    case["expected"] = exp
    ids = {c["id"] for cs in CASES.values() for c in cs}
    assert cid not in ids, f"duplicate case id {cid}"
    CASES.setdefault(category, []).append(case)


def err(code: str, line: int) -> Dict[str, Any]:
    return {"code": code, "line": line}


# =====================================================================
# 1. Fixtures of the official families
# =====================================================================
BAD_CODE = {"bad_arity": "E05", "bad_type": "E06", "bad_marker": "E08"}
# Every bad_type fixture replaces a numeric value by 'many' (E06); checked by hand.
BAD_CODE_OVERRIDE: Dict[tuple, str] = {}


def read(p: Path) -> str:
    return p.read_text(encoding="utf-8")


def fixture_cases() -> None:
    for cdir in sorted(p for p in FORKS.iterdir() if (p / "contract.json").is_file()):
        prefix = cdir.name
        contract = json.loads(read(cdir / "contract.json"))
        rk = contract.get("records_key", "records")
        fx = cdir / "fixtures"
        valid = read(fx / "valid.mini")
        canon = json.loads(read(fx / "canonical.json"))
        add("fixtures", f"fx-{prefix}-valid", f"valid.mini de '{prefix}' produce canonical.json y se re-serializa byte a byte",
            family=prefix, input=valid, canonical=canon, mini=valid.rstrip("\n"))
        if (fx / "escaping.mini").is_file():
            esc_json = json.loads(read(fx / "escaping.json"))
            add("escapes", f"fx-{prefix}-escaping", f"escaping.mini de '{prefix}' con todos los caracteres reservados",
                family=prefix, input=read(fx / "escaping.mini"), canonical=esc_json)
        add("roundtrip", f"fx-{prefix}-dumps", f"canonical.json de '{prefix}' se serializa exactamente como valid.mini",
            mode="dumps", family=prefix, input=canon, mini=valid.rstrip("\n"))
        vlines = valid.rstrip("\n").split("\n")
        for bad in sorted(fx.glob("bad_*.mini")):
            text = read(bad)
            blines = text.rstrip("\n").split("\n")
            diff = [i for i, (x, y) in enumerate(zip(vlines, blines)) if x != y]
            assert len(diff) == 1 and len(vlines) == len(blines), (prefix, bad.name)
            line = diff[0] + 1
            kind = bad.stem
            if kind == "bad_count":
                errors = [err("E04", 0)]
                header = dict(canon["header"])
                header["n"] = int(blines[0].split("|n=")[1].split("|")[0])
                lenient_canon = {"prefix": canon["prefix"], "header": header, rk: canon[rk]}
            else:
                code = BAD_CODE_OVERRIDE.get((prefix, kind), BAD_CODE[kind])
                errors = [err(code, line)]
                recs = [r for i, r in enumerate(canon[rk]) if i != line - 2]
                lenient_canon = {"prefix": canon["prefix"], "header": canon["header"], rk: recs}
            add("fixtures", f"fx-{prefix}-{kind}", f"{bad.name} de '{prefix}' se rechaza (línea {line if kind != 'bad_count' else 0})",
                family=prefix, input=text, errors=errors)
            add("lenient", f"fx-{prefix}-{kind}-lenient", f"{bad.name} de '{prefix}' en modo tolerante conserva los registros válidos",
                mode="lenient", family=prefix, input=text, canonical=lenient_canon, errors=errors)


# =====================================================================
# 2. Small embedded contracts written from SPEC.md
# =====================================================================
SC = {  # scalars + extensions
    "prefix": "sc", "records_key": "rows",
    "core": [
        {"name": "id", "type": "str", "unique": True},
        {"name": "qty", "type": "int", "min": 0, "max": 100},
        {"name": "ratio", "type": "float", "min": -1, "max": 1},
        {"name": "flag", "type": "bool"},
        {"name": "color", "type": "enum", "values": ["red", "green", "blue"]},
    ],
    "extensions": [
        {"name": "memo", "type": "str"},
        {"name": "extra", "type": "int"},
    ],
}
LS = {  # lists
    "prefix": "ls", "records_key": "rows",
    "header": {"required": ["n"], "keys": {"k": {"type": "int"}}},
    "core": [
        {"name": "id", "type": "str"},
        {"name": "xs", "type": "list", "item": "str", "min": 1, "max": 3},
        {"name": "ns", "type": "list", "item": "int"},
        {"name": "es", "type": "list", "item": "enum", "item_values": ["a", "b"]},
        {"name": "ks", "type": "list", "item": "str", "count_key": "k"},
    ],
}
MK = {  # marked lists, one per marker rule
    "prefix": "mk", "records_key": "rows",
    "core": [
        {"name": "one", "type": "mlist", "item": "str", "marker": "exactly_one", "json": {"items": "one", "selected": "one_sel"}},
        {"name": "some", "type": "mlist", "item": "str", "marker": "at_least_one", "json": {"items": "some", "selected": "some_sel"}},
        {"name": "maybe", "type": "mlist", "item": "str", "marker": "at_most_one", "json": {"items": "maybe", "selected": "maybe_sel"}},
        {"name": "anyk", "type": "mlist", "item": "int", "marker": "any", "json": {"items": "anyk", "selected": "anyk_sel"}},
    ],
}
TP = {  # tuples
    "prefix": "tp", "records_key": "rows",
    "core": [
        {"name": "id", "type": "str"},
        {"name": "pt", "type": "tuple", "items": [
            {"name": "x", "type": "int"}, {"name": "y", "type": "float"}, {"name": "tag", "type": "str", "optional": True}]},
    ],
    "extensions": [
        {"name": "span", "type": "tuple", "items": [{"name": "lo", "type": "int"}, {"name": "hi", "type": "int"}]},
    ],
}
SM = {  # custom list separator
    "prefix": "sm", "records_key": "rows", "list_separator": ";",
    "core": [
        {"name": "id", "type": "str"},
        {"name": "xs", "type": "list", "item": "str"},
        {"name": "opts", "type": "mlist", "item": "str", "marker": "exactly_one", "json": {"items": "opts", "selected": "ans"}},
    ],
}
HD = {  # typed header
    "prefix": "hd", "records_key": "rows",
    "header": {"required": ["n", "src"], "keys": {
        "src": {"type": "str"},
        "ls": {"type": "list", "item": "int"},
        "tp": {"type": "tuple", "items": [{"name": "a", "type": "int"}, {"name": "b", "type": "str"}]},
        "k": {"type": "int"},
        "lang": {"type": "str", "default": "es"},
    }},
    "core": [{"name": "id", "type": "str"}],
}


def C(prefix: str, header: dict, key: str, records: list) -> dict:
    h = {"v": 1}
    h.update(header)
    return {"prefix": prefix, "header": h, key: records}


def sc_rec(id="r1", qty=5, ratio=0.5, flag=True, color="red", memo=None, extra=None):
    return {"id": id, "qty": qty, "ratio": ratio, "flag": flag, "color": color, "memo": memo, "extra": extra}


def scalar_cases() -> None:
    c = SC
    add("types", "sc-basic", "tipos escalares básicos",
        contract=c, input="sc|n=1\nr1|5|0.5|true|red", canonical=C("sc", {"n": 1}, "rows", [sc_rec()]), mini="sc|n=1\nr1|5|0.5|true|red")
    add("types", "sc-negative-float-exp", "números negativos y exponente",
        contract=c, input="sc|n=1\nr1|0|-2.5e-1|false|blue", canonical=C("sc", {"n": 1}, "rows", [sc_rec(qty=0, ratio=-0.25, flag=False, color="blue")]))
    add("types", "sc-bool-01", "booleanos 1/0 aceptados en la entrada",
        contract=c, input="sc|n=2\nr1|1|1|1|green\nr2|1|-1|0|green",
        canonical=C("sc", {"n": 2}, "rows", [sc_rec(qty=1, ratio=1, flag=True, color="green"), sc_rec(id="r2", qty=1, ratio=-1, flag=False, color="green")]))
    add("types", "sc-float-integral", "un float integral se escribe sin .0 y compara numéricamente",
        contract=c, input="sc|n=1\nr1|5|1.0|true|red", canonical=C("sc", {"n": 1}, "rows", [sc_rec(ratio=1)]))
    add("types", "sc-int-bad", "entero no numérico (E06)", contract=c, input="sc|n=1\nr1|cinco|0.5|true|red", errors=[err("E06", 2)])
    add("types", "sc-int-decimal", "entero con decimales (E06)", contract=c, input="sc|n=1\nr1|5.5|0.5|true|red", errors=[err("E06", 2)])
    add("types", "sc-float-bad", "número inválido (E06)", contract=c, input="sc|n=1\nr1|5|0,5x|true|red", errors=[err("E06", 2)])
    add("types", "sc-bool-bad", "booleano inválido (E06)", contract=c, input="sc|n=1\nr1|5|0.5|maybe|red", errors=[err("E06", 2)])
    add("types", "sc-enum-bad", "valor fuera de la enumeración (E10)", contract=c, input="sc|n=1\nr1|5|0.5|true|purple", errors=[err("E10", 2)])
    add("types", "sc-enum-case", "la enumeración distingue mayúsculas (E10)", contract=c, input="sc|n=1\nr1|5|0.5|true|Red", errors=[err("E10", 2)])
    add("types", "sc-int-range-max", "entero sobre max (E13)", contract=c, input="sc|n=1\nr1|101|0.5|true|red", errors=[err("E13", 2)])
    add("types", "sc-int-range-min", "entero bajo min (E13)", contract=c, input="sc|n=1\nr1|-1|0.5|true|red", errors=[err("E13", 2)])
    add("types", "sc-float-range", "float fuera de rango (E13)", contract=c, input="sc|n=1\nr1|5|1.5|true|red", errors=[err("E13", 2)])
    add("types", "sc-several-errors-one-line", "varios errores en la misma línea se reportan todos",
        contract=c, input="sc|n=1\nr1|x|9|true|pink", errors=[err("E06", 2), err("E13", 2), err("E10", 2)])
    add("types", "sc-errors-several-lines", "errores en líneas distintas con su número de línea",
        contract=c, input="sc|n=3\nr1|5|0.5|true|red\nr2|500|0.5|true|red\nr3|5|0.5|true|rojo",
        errors=[err("E13", 3), err("E10", 4)])
    add("types", "sc-whitespace-trim", "espacios alrededor de campos no son significativos",
        contract=c, input="sc|n=1\n  r1 |  5 | 0.5 | true |red  ", canonical=C("sc", {"n": 1}, "rows", [sc_rec()]))
    add("types", "sc-internal-whitespace", "espacios internos se preservan; ':' '[' '{' son literales",
        contract=c, input="sc|n=1\nr1|5|0.5|true|red|a: [b] {c}  d",
        canonical=C("sc", {"n": 1}, "rows", [sc_rec(memo="a: [b] {c}  d")]))

    # optionals / arity
    add("optionals", "opt-ext-omitted", "extensiones omitidas valen null", contract=c,
        input="sc|n=1\nr1|5|0.5|true|red", canonical=C("sc", {"n": 1}, "rows", [sc_rec()]))
    add("optionals", "opt-ext-partial", "cola de extensión parcial", contract=c,
        input="sc|n=1\nr1|5|0.5|true|red|nota", canonical=C("sc", {"n": 1}, "rows", [sc_rec(memo="nota")]), mini="sc|n=1\nr1|5|0.5|true|red|nota")
    add("optionals", "opt-ext-empty-middle", "extensión vacía intermedia es null", contract=c,
        input="sc|n=1\nr1|5|0.5|true|red||7", canonical=C("sc", {"n": 1}, "rows", [sc_rec(extra=7)]), mini="sc|n=1\nr1|5|0.5|true|red||7")
    add("optionals", "opt-ext-empty-trailing", "extensiones vacías al final son null y el serializador las omite", contract=c,
        input="sc|n=1\nr1|5|0.5|true|red||", canonical=C("sc", {"n": 1}, "rows", [sc_rec()]))
    add("optionals", "opt-required-empty", "campo requerido vacío (E06)", contract=c,
        input="sc|n=1\nr1||0.5|true|red", errors=[err("E06", 2)])
    add("optionals", "opt-required-empty-str", "texto requerido vacío (E06)", contract=c,
        input="sc|n=1\n |5|0.5|true|red", errors=[err("E06", 2)])
    add("optionals", "opt-ext-type-error", "extensión presente con tipo inválido (E06)", contract=c,
        input="sc|n=1\nr1|5|0.5|true|red|nota|siete", errors=[err("E06", 2)])
    add("arity", "arity-fewer", "menos campos que el núcleo (E05)", contract=c,
        input="sc|n=1\nr1|5|0.5|true", errors=[err("E05", 2)])
    add("arity", "arity-more", "más campos que núcleo + extensiones (E05)", contract=c,
        input="sc|n=1\nr1|5|0.5|true|red|m|1|sobra", errors=[err("E05", 2)])
    add("arity", "arity-escaped-pipe-not-separator", "una barra escapada no cuenta como separador (E05)", contract=c,
        input="sc|n=1\nr1|5|0.5|true\\|red", errors=[err("E05", 2)])

    # uniqueness
    add("unique", "unique-dup", "valor repetido en campo unique (E11)", contract=c,
        input="sc|n=2\nr1|5|0.5|true|red\nr1|6|0.5|true|red", errors=[err("E11", 3)])
    add("unique", "unique-dup-lenient", "modo tolerante conserva la primera aparición", mode="lenient", contract=c,
        input="sc|n=3\nr1|5|0.5|true|red\nr1|6|0.5|true|red\nr2|7|0.5|true|red",
        canonical=C("sc", {"n": 3}, "rows", [sc_rec(), sc_rec(id="r2", qty=7)]), errors=[err("E11", 3)],
        diagnostics={"invalid_lines": [3], "missing_records": 0})
    add("unique", "unique-distinct", "valores distintos son válidos", contract=c,
        input="sc|n=2\nr1|5|0.5|true|red\nR1|5|0.5|true|red",
        canonical=C("sc", {"n": 2}, "rows", [sc_rec(), sc_rec(id="R1")]))
    add("unique", "unique-after-escape", "la unicidad compara el valor ya decodificado (E11)", contract=c,
        input="sc|n=2\na\\|b|5|0.5|true|red\na\\|b|6|0.5|true|red", errors=[err("E11", 3)])
    add("unique", "unique-rejected-line-does-not-claim", "una línea rechazada no reserva el valor único", mode="lenient", contract=c,
        input="sc|n=2\nr1|500|0.5|true|red\nr1|5|0.5|true|red",
        canonical=C("sc", {"n": 2}, "rows", [sc_rec()]), errors=[err("E13", 2)],
        diagnostics={"invalid_lines": [2], "missing_records": 0})


def list_cases() -> None:
    c = LS
    H = "ls|n=1|k=2"

    def rec(id="r1", xs=None, ns=None, es=None, ks=None):
        return {"id": id, "xs": xs if xs is not None else ["x"], "ns": ns if ns is not None else [1, 2],
                "es": es if es is not None else ["a"], "ks": ks if ks is not None else ["p", "q"]}

    hdr = {"n": 1, "k": 2}
    add("lists", "list-basic", "listas de str, int y enum", contract=c,
        input=f"{H}\nr1|x|1,2|a|p,q", canonical=C("ls", hdr, "rows", [rec()]), mini=f"{H}\nr1|x|1,2|a|p,q")
    add("lists", "list-empty", "lista vacía sin mínimo es []", contract=c,
        input=f"{H}\nr1|x||a|p,q", canonical=C("ls", hdr, "rows", [rec(ns=[])]))
    add("lists", "list-trim-elements", "espacios alrededor de los elementos se recortan", contract=c,
        input=f"{H}\nr1| x , y |1 , 2| a , b |p , q", canonical=C("ls", hdr, "rows", [rec(xs=["x", "y"], es=["a", "b"])]))
    add("lists", "list-min", "lista bajo el mínimo (E07)", contract=c, input=f"{H}\nr1||1|a|p,q", errors=[err("E07", 2)])
    add("lists", "list-max", "lista sobre el máximo (E07)", contract=c, input=f"{H}\nr1|a,b,c,d|1|a|p,q", errors=[err("E07", 2)])
    add("lists", "list-count-key-less", "lista con menos elementos que la clave de conteo (E07)", contract=c,
        input=f"{H}\nr1|x|1|a|p", errors=[err("E07", 2)])
    add("lists", "list-count-key-collision", "coma sin proteger rompe la aridad fijada por k (E07)", contract=c,
        input=f"{H}\nr1|x|1|a|p, y más,q", errors=[err("E07", 2)])
    add("lists", "list-count-key-escaped", "coma escapada respeta la aridad de k", contract=c,
        input=f"{H}\nr1|x|1|a|p\\, y más,q", canonical=C("ls", hdr, "rows", [rec(ns=[1], ks=["p, y más", "q"])]))
    add("lists", "list-int-item-bad", "elemento entero inválido (E06)", contract=c, input=f"{H}\nr1|x|1,dos|a|p,q", errors=[err("E06", 2)])
    add("lists", "list-enum-item-bad", "elemento fuera de la enumeración (E10)", contract=c, input=f"{H}\nr1|x|1|a,c|p,q", errors=[err("E10", 2)])
    add("lists", "list-marker-not-allowed", "marcador * en lista simple (E08)", contract=c, input=f"{H}\nr1|x*|1|a|p,q", errors=[err("E08", 2)])
    add("lists", "list-escaped-star", "\\* en lista simple es un asterisco literal", contract=c,
        input=f"{H}\nr1|x\\*|1|a|p,q", canonical=C("ls", hdr, "rows", [rec(xs=["x*"], ns=[1])]))
    add("lists", "list-star-inside", "un * que no es el último carácter es literal", contract=c,
        input=f"{H}\nr1|a*b|1|a|p,q", canonical=C("ls", hdr, "rows", [rec(xs=["a*b"], ns=[1])]))
    add("lists", "list-custom-separator", "separador ';' definido por el contrato; ',' es literal", contract=SM,
        input="sm|n=1\nr1|a, b;c|uno, dos*;tres",
        canonical=C("sm", {"n": 1}, "rows", [{"id": "r1", "xs": ["a, b", "c"], "opts": ["uno, dos", "tres"], "ans": 0}]),
        mini="sm|n=1\nr1|a, b;c|uno, dos*;tres")
    add("lists", "list-custom-separator-escape", "\\; protege el separador personalizado", contract=SM,
        input="sm|n=1\nr1|a\\;b|x;y*",
        canonical=C("sm", {"n": 1}, "rows", [{"id": "r1", "xs": ["a;b"], "opts": ["x", "y"], "ans": 1}]))
    add("lists", "list-custom-separator-quoted", "comillas protegen el separador personalizado", contract=SM,
        input='sm|n=1\nr1|"a;b"|"x;y"*;z',
        canonical=C("sm", {"n": 1}, "rows", [{"id": "r1", "xs": ["a;b"], "opts": ["x;y", "z"], "ans": 0}]))


def mlist_cases() -> None:
    c = MK

    def rec(one=("a", "b"), one_sel=0, some=("a",), some_sel=(0,), maybe=("a",), maybe_sel=None, anyk=(1,), anyk_sel=()):
        return {"one": list(one), "one_sel": one_sel, "some": list(some), "some_sel": list(some_sel),
                "maybe": list(maybe), "maybe_sel": maybe_sel, "anyk": list(anyk), "anyk_sel": list(anyk_sel)}

    add("mlist", "mlist-basic", "exactly_one da índice; at_least_one lista; at_most_one null; any lista vacía", contract=c,
        input="mk|n=1\na*,b|a*|a|1", canonical=C("mk", {"n": 1}, "rows", [rec()]), mini="mk|n=1\na*,b|a*|a|1")
    add("mlist", "mlist-selected-index", "el índice seleccionado es base 0", contract=c,
        input="mk|n=1\na,b,c*|a*,b,c*|a,b*|1*,2,3*",
        canonical=C("mk", {"n": 1}, "rows", [rec(one=("a", "b", "c"), one_sel=2, some=("a", "b", "c"), some_sel=(0, 2),
                                                 maybe=("a", "b"), maybe_sel=1, anyk=(1, 2, 3), anyk_sel=(0, 2))]))
    add("mlist", "mlist-exactly-one-none", "exactly_one sin marcador (E08)", contract=c, input="mk|n=1\na,b|a*|a|1", errors=[err("E08", 2)])
    add("mlist", "mlist-exactly-one-two", "exactly_one con dos marcadores (E08)", contract=c, input="mk|n=1\na*,b*|a*|a|1", errors=[err("E08", 2)])
    add("mlist", "mlist-at-least-one-none", "at_least_one sin marcador (E08)", contract=c, input="mk|n=1\na*,b|a|a|1", errors=[err("E08", 2)])
    add("mlist", "mlist-at-most-one-two", "at_most_one con dos marcadores (E08)", contract=c, input="mk|n=1\na*,b|a*|a*,b*|1", errors=[err("E08", 2)])
    add("mlist", "mlist-any-all", "any admite todos marcados", contract=c,
        input="mk|n=1\na*,b|a*|a|1*,2*", canonical=C("mk", {"n": 1}, "rows", [rec(anyk=(1, 2), anyk_sel=(0, 1))]))
    add("mlist", "mlist-marker-space", "espacios entre el elemento y * se recortan", contract=c,
        input="mk|n=1\na *, b|a*|a|1", canonical=C("mk", {"n": 1}, "rows", [rec()]))
    add("mlist", "mlist-escaped-star-not-marker", "\\* al final es literal y no marca (E08 si falta el marcador)", contract=c,
        input="mk|n=1\na\\*,b|a*|a|1", errors=[err("E08", 2)])
    add("mlist", "mlist-escaped-star-then-marker", "\\** = asterisco literal seguido del marcador", contract=c,
        input="mk|n=1\na\\**,b|a*|a|1", canonical=C("mk", {"n": 1}, "rows", [rec(one=("a*", "b"))]), mini="mk|n=1\na\\**,b|a*|a|1")
    add("mlist", "mlist-int-item-bad", "elemento entero inválido en lista marcada (E06)", contract=c,
        input="mk|n=1\na*,b|a*|a|1,x*", errors=[err("E06", 2)])


def tuple_cases() -> None:
    c = TP
    add("tuples", "tuple-basic", "tupla a objeto anidado", contract=c,
        input="tp|n=1\nr1|3,-1.5,izq", canonical=C("tp", {"n": 1}, "rows", [{"id": "r1", "pt": {"x": 3, "y": -1.5, "tag": "izq"}, "span": None}]),
        mini="tp|n=1\nr1|3,-1.5,izq")
    add("tuples", "tuple-optional-component", "componente opcional vacío es null", contract=c,
        input="tp|n=1\nr1|3,2,", canonical=C("tp", {"n": 1}, "rows", [{"id": "r1", "pt": {"x": 3, "y": 2, "tag": None}, "span": None}]))
    add("tuples", "tuple-optional-extension", "extensión de tipo tupla presente", contract=c,
        input="tp|n=1\nr1|3,2,t|0,9", canonical=C("tp", {"n": 1}, "rows", [{"id": "r1", "pt": {"x": 3, "y": 2, "tag": "t"}, "span": {"lo": 0, "hi": 9}}]))
    add("tuples", "tuple-optional-empty", "tupla opcional vacía es null", contract=c,
        input="tp|n=1\nr1|3,2,t|", canonical=C("tp", {"n": 1}, "rows", [{"id": "r1", "pt": {"x": 3, "y": 2, "tag": "t"}, "span": None}]))
    add("tuples", "tuple-arity-less", "tupla con menos componentes (E07)", contract=c, input="tp|n=1\nr1|3,2", errors=[err("E07", 2)])
    add("tuples", "tuple-arity-more", "tupla con más componentes (E07)", contract=c, input="tp|n=1\nr1|3,2,t,u", errors=[err("E07", 2)])
    add("tuples", "tuple-required-empty", "tupla requerida vacía (E07)", contract=c, input="tp|n=1\nr1|", errors=[err("E07", 2)])
    add("tuples", "tuple-component-type", "componente con tipo inválido (E06)", contract=c, input="tp|n=1\nr1|tres,2,t", errors=[err("E06", 2)])
    add("tuples", "tuple-required-component-empty", "componente requerido vacío (E06)", contract=c, input="tp|n=1\nr1|,2,t", errors=[err("E06", 2)])
    add("tuples", "tuple-marker", "marcador * dentro de una tupla (E08)", contract=c, input="tp|n=1\nr1|3,2,t*", errors=[err("E08", 2)])
    add("tuples", "tuple-escaped-comma", "coma escapada dentro de un componente de texto", contract=c,
        input="tp|n=1\nr1|3,2,a\\, b", canonical=C("tp", {"n": 1}, "rows", [{"id": "r1", "pt": {"x": 3, "y": 2, "tag": "a, b"}, "span": None}]),
        mini="tp|n=1\nr1|3,2,a\\, b")


def escape_cases() -> None:
    c = SC

    def one(memo):
        return C("sc", {"n": 1}, "rows", [sc_rec(memo=memo)])

    base = "sc|n=1\nr1|5|0.5|true|red|"
    add("escapes", "esc-pipe", "\\| es una barra literal", contract=c, input=base + "a\\|b", canonical=one("a|b"), mini=base + "a\\|b")
    add("escapes", "esc-backslash", "\\\\ es una barra invertida literal", contract=c, input=base + "C:\\\\tmp", canonical=one("C:\\tmp"), mini=base + "C:\\\\tmp")
    add("escapes", "esc-newline", "\\n es un salto de línea dentro del valor", contract=c, input=base + "l1\\nl2", canonical=one("l1\nl2"), mini=base + "l1\\nl2")
    add("escapes", "esc-comma-scalar", "\\, en un escalar es inocuo (sobre-escape)", contract=c, input=base + "a\\, b", canonical=one("a, b"), mini=base + "a, b")
    add("escapes", "esc-star-scalar", "\\* en un escalar es un asterisco", contract=c, input=base + "nota\\*", canonical=one("nota*"), mini=base + "nota*")
    add("escapes", "esc-quote-scalar", "\\\" en un escalar es una comilla", contract=c, input=base + "\\\"hola\\\"", canonical=one('"hola"'), mini=base + '"hola"')
    add("escapes", "esc-quote-literal-scalar", "comillas en un escalar son literales (los escalares no se entrecomillan)", contract=c,
        input=base + '"a, b"', canonical=one('"a, b"'))
    add("escapes", "esc-backslash-then-n", "\\\\n es barra invertida seguida de n", contract=c, input=base + "a\\\\nb", canonical=one("a\\nb"), mini=base + "a\\\\nb")
    add("escapes", "esc-escaped-space-kept", "un espacio tras \\n no se recorta", contract=c, input=base + "\\n x", canonical=one("\n x"))
    add("escapes", "esc-all-reserved", "todos los reservados en un mismo escalar", contract=c,
        input=base + "p\\|b\\\\c,\\*\\\"\\nfin", canonical=one('p|b\\c,*"\nfin'), mini=base + 'p\\|b\\\\c,*"\\nfin')
    add("escapes", "esc-invalid", "secuencia de escape inválida (E09)", contract=c, input=base + "a\\tb", errors=[err("E09", 2)])
    add("escapes", "esc-dangling", "barra invertida final (E09)", contract=c, input=base + "abc\\", errors=[err("E09", 2)])
    add("escapes", "esc-invalid-in-core", "escape inválido en un campo del núcleo (E09)", contract=c,
        input="sc|n=1\nr\\1|5|0.5|true|red", errors=[err("E09", 2)])
    add("escapes", "esc-invalid-lenient", "en modo tolerante el escape inválido se reporta y el registro se descarta", mode="lenient", contract=c,
        input="sc|n=2\nr1|5|0.5|true|red|a\\qb\nr2|5|0.5|true|red", canonical=C("sc", {"n": 2}, "rows", [sc_rec(id="r2")]),
        errors=[err("E09", 2)], diagnostics={"invalid_lines": [2], "missing_records": 0})
    L = LS
    H = "ls|n=1|k=2"
    add("escapes", "esc-list-comma", "\\, dentro de un elemento de lista", contract=L,
        input=f"{H}\nr1|a\\,b|1|a|p,q", canonical=C("ls", {"n": 1, "k": 2}, "rows", [{"id": "r1", "xs": ["a,b"], "ns": [1], "es": ["a"], "ks": ["p", "q"]}]),
        mini=f"{H}\nr1|a\\,b|1|a|p,q")
    add("escapes", "esc-list-leading-quote", "\\\" al inicio de un elemento evita abrir comillas", contract=L,
        input=f"{H}\nr1|\\\"a|1|a|p,q", canonical=C("ls", {"n": 1, "k": 2}, "rows", [{"id": "r1", "xs": ['"a'], "ns": [1], "es": ["a"], "ks": ["p", "q"]}]),
        mini=f"{H}\nr1|\\\"a|1|a|p,q")
    add("escapes", "esc-list-pipe-newline", "\\| y \\n dentro de elementos de lista", contract=L,
        input=f"{H}\nr1|a\\|b,c\\nd|1|a|p,q", canonical=C("ls", {"n": 1, "k": 2}, "rows", [{"id": "r1", "xs": ["a|b", "c\nd"], "ns": [1], "es": ["a"], "ks": ["p", "q"]}]))
    add("escapes", "esc-crlf-ignored", "CR antes de LF se ignora", contract=c,
        input="sc|n=1\r\nr1|5|0.5|true|red\r\n", canonical=C("sc", {"n": 1}, "rows", [sc_rec()]))


def quote_cases() -> None:
    c = MK

    def rec(one, one_sel):
        return {"one": one, "one_sel": one_sel, "some": ["a"], "some_sel": [0], "maybe": ["a"], "maybe_sel": None, "anyk": [1], "anyk_sel": []}

    tail = "|a*|a|1"
    add("quotes", "quote-basic", "elemento entre comillas con separador literal", contract=c,
        input='mk|n=1\n"impacto, justicia y evidencia"*,otra' + tail,
        canonical=C("mk", {"n": 1}, "rows", [rec(["impacto, justicia y evidencia", "otra"], 0)]),
        )
    add("quotes", "quote-canonical-is-escaped", "el serializador emite la forma escapada del elemento entrecomillado", mode="dumps", contract=c,
        input=C("mk", {"n": 1}, "rows", [rec(["impacto, justicia y evidencia", "otra"], 0)]),
        mini="mk|n=1\nimpacto\\, justicia y evidencia*,otra" + tail)
    add("quotes", "quote-marker-inside", "el marcador puede ir justo antes de la comilla de cierre", contract=c,
        input='mk|n=1\n"a, b*",c' + tail, canonical=C("mk", {"n": 1}, "rows", [rec(["a, b", "c"], 0)]))
    add("quotes", "quote-escaped-star-inside", "\\* antes de la comilla de cierre es literal", contract=c,
        input='mk|n=1\n"a\\*",c*' + tail, canonical=C("mk", {"n": 1}, "rows", [rec(["a*", "c"], 1)]))
    add("quotes", "quote-star-literal-inside", "* en medio de un elemento entrecomillado es literal", contract=c,
        input='mk|n=1\n"a*b, c",d*' + tail, canonical=C("mk", {"n": 1}, "rows", [rec(["a*b, c", "d"], 1)]))
    add("quotes", "quote-doubled", "\"\" dentro de comillas es una comilla", contract=c,
        input='mk|n=1\n"dijo ""sí"""*,no' + tail, canonical=C("mk", {"n": 1}, "rows", [rec(['dijo "sí"', "no"], 0)]))
    add("quotes", "quote-backslash-inside", "los escapes siguen activos dentro de comillas", contract=c,
        input='mk|n=1\n"a\\|b, c\\\\d"*,e' + tail, canonical=C("mk", {"n": 1}, "rows", [rec(["a|b, c\\d", "e"], 0)]))
    add("quotes", "quote-whitespace-around", "espacios alrededor de un elemento entrecomillado se ignoran", contract=c,
        input='mk|n=1\n  "a, b"  * , c' + tail, canonical=C("mk", {"n": 1}, "rows", [rec(["a, b", "c"], 0)]))
    add("quotes", "quote-inner-spaces-kept", "espacios dentro de las comillas se preservan", contract=c,
        input='mk|n=1\n" a "*,b' + tail, canonical=C("mk", {"n": 1}, "rows", [rec([" a ", "b"], 0)]))
    add("quotes", "quote-not-first-literal", "una comilla que no es el primer carácter es literal", contract=c,
        input='mk|n=1\nel "mejor"*,b' + tail, canonical=C("mk", {"n": 1}, "rows", [rec(['el "mejor"', "b"], 0)]))
    add("quotes", "quote-empty", "elemento entrecomillado vacío", contract=c,
        input='mk|n=1\n""*,b' + tail, canonical=C("mk", {"n": 1}, "rows", [rec(["", "b"], 0)]))
    add("quotes", "quote-unbalanced", "comilla sin cerrar (E09)", contract=c, input='mk|n=1\n"a, b*,c' + tail, errors=[err("E09", 2)])
    add("quotes", "quote-text-after-close", "texto entre la comilla de cierre y el separador (E09)", contract=c,
        input='mk|n=1\n"a" b*,c' + tail, errors=[err("E09", 2)])
    add("quotes", "quote-equivalent-to-escape", "comillas y escapes denotan el mismo valor", contract=c,
        input='mk|n=2\n"x, y"*,z' + tail + "\nx\\, y*,z" + tail,
        canonical=C("mk", {"n": 2}, "rows", [rec(["x, y", "z"], 0), rec(["x, y", "z"], 0)]))
    add("quotes", "quote-in-plain-list", "comillas en una lista simple de la familia a", contract=LS,
        input='ls|n=1|k=2\nr1|"a, b",c|1|a|"p, q",r',
        canonical=C("ls", {"n": 1, "k": 2}, "rows", [{"id": "r1", "xs": ["a, b", "c"], "ns": [1], "es": ["a"], "ks": ["p, q", "r"]}]))


def header_cases() -> None:
    c = HD
    rec = [{"id": "x"}]
    add("header", "hdr-typed", "claves de cabecera tipadas (lista, tupla, entero) y valor por defecto", contract=c,
        input="hd|n=1|src=clase 3|ls=1,2,3|tp=7,siete|k=2\nx",
        canonical=C("hd", {"n": 1, "src": "clase 3", "ls": [1, 2, 3], "tp": {"a": 7, "b": "siete"}, "k": 2, "lang": "es"}, "rows", rec))
    add("header", "hdr-unknown-keys", "claves desconocidas se conservan como texto", contract=c,
        input="hd|n=1|src=s|model=m-1|temp=0.2\nx",
        canonical=C("hd", {"n": 1, "src": "s", "lang": "es", "model": "m-1", "temp": "0.2"}, "rows", rec))
    add("header", "hdr-v-explicit", "v explícito", contract=c,
        input="hd|n=1|v=2|src=s\nx", canonical={"prefix": "hd", "header": {"n": 1, "v": 2, "src": "s", "lang": "es"}, "rows": rec})
    add("header", "hdr-eq-in-value", "solo el primer '=' separa clave y valor", contract=c,
        input="hd|n=1|src=a=b=c\nx", canonical=C("hd", {"n": 1, "src": "a=b=c", "lang": "es"}, "rows", rec))
    add("header", "hdr-whitespace", "espacios alrededor de claves y valores se recortan", contract=c,
        input="hd | n = 1 | src =  s \nx", canonical=C("hd", {"n": 1, "src": "s", "lang": "es"}, "rows", rec))
    add("header", "hdr-escaped-pipe", "\\| en un valor de cabecera", contract=c,
        input="hd|n=1|src=a\\|b\nx", canonical=C("hd", {"n": 1, "src": "a|b", "lang": "es"}, "rows", rec))
    add("header", "hdr-bom", "BOM inicial se ignora", contract=c,
        input="\ufeffhd|n=1|src=s\nx", canonical=C("hd", {"n": 1, "src": "s", "lang": "es"}, "rows", rec))
    add("header", "hdr-blank-lines", "líneas vacías se omiten y los números de línea siguen siendo físicos", contract=c,
        input="\n\nhd|n=2|src=s\n\n   \nx\n\ny|sobra\n", errors=[err("E05", 8)])
    add("header", "hdr-zero-records", "n=0 sin registros es válido", contract=c,
        input="hd|n=0|src=s", canonical=C("hd", {"n": 0, "src": "s", "lang": "es"}, "rows", []))
    add("header", "hdr-e01-empty", "documento vacío (E01)", contract=c, input="", errors=[err("E01", 0)])
    add("header", "hdr-e01-blank", "documento con solo líneas en blanco (E01)", contract=c, input="\n  \n\t\n", errors=[err("E01", 0)])
    add("header", "hdr-e02-prefix", "prefijo distinto del contrato (E02)", contract=c, input="hx|n=1|src=s\nx", errors=[err("E02", 1)])
    add("header", "hdr-e02-case", "el prefijo distingue mayúsculas (E02)", contract=c, input="HD|n=1|src=s\nx", errors=[err("E02", 1)])
    add("header", "hdr-e03-no-n", "cabecera sin n (E03)", contract=c, input="hd|src=s\nx", errors=[err("E03", 1)])
    add("header", "hdr-e04-more", "más registros que n (E04)", contract=c, input="hd|n=1|src=s\nx\ny", errors=[err("E04", 0)])
    add("header", "hdr-e04-fewer", "menos registros que n (E04)", contract=c, input="hd|n=3|src=s\nx\ny", errors=[err("E04", 0)])
    add("header", "hdr-e12-no-eq", "entrada de cabecera sin '=' (E12)", contract=c, input="hd|n=1|src=s|basura\nx", errors=[err("E12", 1)])
    add("header", "hdr-e12-required-missing", "falta una clave requerida (E12)", contract=c, input="hd|n=1\nx", errors=[err("E12", 1)])
    add("header", "hdr-list-bad-item", "elemento inválido en lista de cabecera (E06)", contract=c, input="hd|n=1|src=s|ls=1,x\nx", errors=[err("E06", 1)])
    add("header", "hdr-tuple-arity", "tupla de cabecera con aridad incorrecta (E07)", contract=c, input="hd|n=1|src=s|tp=1\nx", errors=[err("E07", 1)])
    add("header", "hdr-escape-invalid", "escape inválido en la cabecera (E09)", contract=c, input="hd|n=1|src=a\\qb\nx", errors=[err("E09", 1)])
    # SPEC §3.2: '=' separa clave y valor solo en su primera aparición SIN escapar. '\=' no es una
    # secuencia de escape válida (§3.3: E09) y su '=' queda escapado, así que la entrada no tiene
    # separador (§5: entrada sin '=' es E12). Hallado por el fuzz diferencial de la auditoría V5
    # (Python conservaba una clave rota y no informaba E12).
    add("header", "hdr-escaped-eq-key", "'\\=' en una clave de cabecera: E09 por el escape y E12 por la entrada sin '=' sin escapar", contract=c,
        input="hd|n=1|src=s|foo\\=bar\nx", errors=[err("E09", 1), err("E12", 1)])
    add("header", "hdr-escaped-eq-key-lenient", "modo tolerante: la entrada con '\\=' se descarta y el registro se conserva", mode="lenient", contract=c,
        input="hd|n=1|src=s|foo\\=bar\nx", canonical=C("hd", {"n": 1, "src": "s", "lang": "es"}, "rows", rec),
        errors=[err("E09", 1), err("E12", 1)])
    add("header", "hdr-escaped-eq-n", "'n\\=1' no declara n: E09, E12 por la entrada y E03 porque falta n", contract=c,
        input="hd|n\\=1|src=s\nx", errors=[err("E09", 1), err("E12", 1), err("E03", 1)])
    add("header", "hdr-escaped-eq-in-value", "'\\=' dentro de un valor es un escape inválido (E09), sin otros errores", contract=c,
        input="hd|n=1|src=a\\=b\nx", errors=[err("E09", 1)])
    add("header", "hdr-count-errors-combined","errores de cabecera y de conteo se acumulan", contract=c,
        input="hd|n=2|src=s|basura\nx", errors=[err("E12", 1), err("E04", 0)])
    add("header", "hdr-lenient-keeps-records", "con errores de cabecera el modo tolerante conserva los registros", mode="lenient", contract=c,
        input="hd|n=1|basura\nx", canonical=C("hd", {"n": 1, "lang": "es"}, "rows", rec), errors=[err("E12", 1)])


def truncation_cases() -> None:
    c = SC
    full = "sc|n=3\nr1|5|0.5|true|red\nr2|6|0.5|true|green\nr3|7|0.5|false|blue"
    r12 = [sc_rec(), sc_rec(id="r2", qty=6, color="green")]
    add("truncation", "trunc-last-record-cut", "último registro incompleto: se reporta su línea y se conservan los anteriores", mode="lenient", contract=c,
        input=full[: full.rindex("|false")], canonical=C("sc", {"n": 3}, "rows", r12), errors=[err("E05", 4)],
        diagnostics={"invalid_lines": [4], "missing_records": 0})
    add("truncation", "trunc-last-record-cut-strict", "el mismo documento truncado se rechaza en modo estricto", contract=c,
        input=full[: full.rindex("|false")], errors=[err("E05", 4)])
    add("truncation", "trunc-inside-value", "corte en mitad de un valor enum (E10)", mode="lenient", contract=c,
        input=full[:-2], canonical=C("sc", {"n": 3}, "rows", r12), errors=[err("E10", 4)],
        diagnostics={"invalid_lines": [4], "missing_records": 0})
    add("truncation", "trunc-missing-lines", "faltan líneas completas: E04 y registros faltantes", mode="lenient", contract=c,
        input=full[: full.index("\nr3")], canonical=C("sc", {"n": 3}, "rows", r12), errors=[err("E04", 0)],
        diagnostics={"invalid_lines": [], "missing_records": 1})
    add("truncation", "trunc-cut-and-missing", "registro cortado y líneas faltantes", mode="lenient", contract=c,
        input="sc|n=5\nr1|5|0.5|true|red\nr2|6|0", canonical=C("sc", {"n": 5}, "rows", [sc_rec()]),
        errors=[err("E05", 3), err("E04", 0)], diagnostics={"invalid_lines": [3], "missing_records": 3})
    add("truncation", "trunc-dangling-escape", "corte justo después de una barra invertida (E09)", mode="lenient", contract=c,
        input="sc|n=2\nr1|5|0.5|true|red\nr2|5|0.5|true|red|a\\", canonical=C("sc", {"n": 2}, "rows", [sc_rec()]),
        errors=[err("E09", 3)], diagnostics={"invalid_lines": [3], "missing_records": 0})
    add("truncation", "trunc-list-count-key", "corte dentro de una lista con clave de conteo (E07)", mode="lenient", contract=LS,
        input="ls|n=2|k=2\nr1|x|1|a|p,q\nr2|x|1|a|p",
        canonical=C("ls", {"n": 2, "k": 2}, "rows", [{"id": "r1", "xs": ["x"], "ns": [1], "es": ["a"], "ks": ["p", "q"]}]),
        errors=[err("E07", 3)], diagnostics={"invalid_lines": [3], "missing_records": 0})
    add("truncation", "trunc-open-quote", "corte dentro de un elemento entrecomillado (E09)", mode="lenient", contract=MK,
        input='mk|n=2\na*,b|a*|a|1\n"a, b',
        canonical=C("mk", {"n": 2}, "rows", [{"one": ["a", "b"], "one_sel": 0, "some": ["a"], "some_sel": [0], "maybe": ["a"], "maybe_sel": None, "anyk": [1], "anyk_sel": []}]),
        errors=[err("E05", 3)], diagnostics={"invalid_lines": [3], "missing_records": 0})
    add("truncation", "trunc-header-only", "solo la cabecera: todos los registros faltan", mode="lenient", contract=c,
        input="sc|n=3", canonical=C("sc", {"n": 3}, "rows", []), errors=[err("E04", 0)],
        diagnostics={"invalid_lines": [], "missing_records": 3})
    add("truncation", "trunc-empty-lenient", "documento vacío en modo tolerante (E01, sin documento)", mode="lenient", contract=c,
        input="", errors=[err("E01", 0)])
    add("truncation", "trunc-a-family", "familia a: último ítem cortado tras el tema", mode="lenient", family="a",
        input=read(FORKS / "a/fixtures/valid.mini").rstrip("\n").rsplit("|", 5)[0],
        canonical=_a_first_11(), errors=[err("E05", 13)], diagnostics={"invalid_lines": [13], "missing_records": 0})


def _a_first_11() -> dict:
    canon = json.loads(read(FORKS / "a/fixtures/canonical.json"))
    canon["items"] = canon["items"][:11]
    return canon


def dumps_cases() -> None:
    c = SC
    add("roundtrip", "dumps-escapes-scalar", "el serializador escapa | \\ y saltos de línea", mode="dumps", contract=c,
        input=C("sc", {"n": 1}, "rows", [sc_rec(memo="a|b\\c\nd, e*")]), mini="sc|n=1\nr1|5|0.5|true|red|a\\|b\\\\c\\nd, e*")
    add("roundtrip", "dumps-crlf-normalised", "CRLF en un valor se serializa como \\n", mode="dumps", contract=c,
        input=C("sc", {"n": 1}, "rows", [sc_rec(memo="a\r\nb")]), mini="sc|n=1\nr1|5|0.5|true|red|a\\nb")
    add("roundtrip", "dumps-tail-omitted", "extensiones nulas finales se omiten", mode="dumps", contract=c,
        input=C("sc", {"n": 1}, "rows", [sc_rec()]), mini="sc|n=1\nr1|5|0.5|true|red")
    add("roundtrip", "dumps-null-middle-extension", "extensión nula intermedia queda vacía", mode="dumps", contract=c,
        input=C("sc", {"n": 1}, "rows", [sc_rec(extra=3)]), mini="sc|n=1\nr1|5|0.5|true|red||3")
    add("roundtrip", "dumps-float-format", "floats integrales sin .0; booleanos true/false", mode="dumps", contract=c,
        input=C("sc", {"n": 2}, "rows", [sc_rec(ratio=1.0, flag=False), sc_rec(id="r2", ratio=-0.125)]),
        mini="sc|n=2\nr1|5|1|false|red\nr2|5|-0.125|true|red")
    add("roundtrip", "dumps-n-recomputed", "n se recalcula a partir de los registros", mode="dumps", contract=c,
        input={"prefix": "sc", "header": {"n": 99, "v": 1}, "rows": [sc_rec()]}, mini="sc|n=1\nr1|5|0.5|true|red")
    add("roundtrip", "dumps-list-element-escapes", "elementos de lista: separador, * final y comilla inicial", mode="dumps", contract=LS,
        input=C("ls", {"n": 1, "k": 2}, "rows", [{"id": "r1", "xs": ['"a', "b*", "c,d"], "ns": [], "es": ["b"], "ks": ["p|q", "r\\s"]}]),
        mini='ls|n=1|k=2\nr1|\\"a,b\\*,c\\,d||b|p\\|q,r\\\\s')
    add("roundtrip", "dumps-header-typed", "cabecera tipada: n primero, luego claves del contrato y extras", mode="dumps", contract=HD,
        input={"prefix": "hd", "header": {"zz": "extra", "tp": {"a": 1, "b": "x,y"}, "src": "s", "ls": [3, 4], "n": 1, "v": 1, "lang": "es"}, "rows": [{"id": "x"}]},
        mini="hd|n=1|src=s|ls=3,4|tp=1,x\\,y|lang=es|zz=extra\nx")
    add("roundtrip", "dumps-mlist-rules", "serialización de las cuatro reglas de marcador", mode="dumps", contract=MK,
        input=C("mk", {"n": 1}, "rows", [{"one": ["a", "b"], "one_sel": 1, "some": ["a", "b"], "some_sel": [0, 1], "maybe": ["a"], "maybe_sel": None, "anyk": [1, 2], "anyk_sel": []}]),
        mini="mk|n=1\na,b*|a*,b*|a|1,2")
    add("roundtrip", "dumps-tuple-optional", "tupla con componente nulo y extensión tupla", mode="dumps", contract=TP,
        input=C("tp", {"n": 1}, "rows", [{"id": "r1", "pt": {"x": 1, "y": 2.5, "tag": None}, "span": {"lo": -1, "hi": 1}}]),
        mini="tp|n=1\nr1|1,2.5,|-1,1")
    add("roundtrip", "dumps-reject-marker", "exactly_one sin selección no se puede serializar", mode="dumps", contract=MK,
        input=C("mk", {"n": 1}, "rows", [{"one": ["a", "b"], "one_sel": None, "some": ["a"], "some_sel": [0], "maybe": ["a"], "maybe_sel": None, "anyk": [1], "anyk_sel": []}]),
        rejected=True, errors=[err("E08", 2)])
    add("roundtrip", "dumps-reject-index", "índice seleccionado fuera de rango no se puede serializar", mode="dumps", contract=MK,
        input=C("mk", {"n": 1}, "rows", [{"one": ["a", "b"], "one_sel": 5, "some": ["a"], "some_sel": [0], "maybe": ["a"], "maybe_sel": None, "anyk": [1], "anyk_sel": []}]),
        rejected=True, errors=[err("E08", 2)])
    add("roundtrip", "dumps-reject-required-null", "campo requerido nulo no se puede serializar", mode="dumps", contract=c,
        input=C("sc", {"n": 1}, "rows", [sc_rec(qty=None)]), rejected=True, errors=[err("E06", 2)])
    add("roundtrip", "dumps-reject-enum", "valor fuera de la enumeración no se puede serializar", mode="dumps", contract=c,
        input=C("sc", {"n": 1}, "rows", [sc_rec(color="pink")]), rejected=True, errors=[err("E10", 2)])
    add("roundtrip", "dumps-reject-tuple-component", "componente requerido de tupla ausente", mode="dumps", contract=TP,
        input=C("tp", {"n": 1}, "rows", [{"id": "r1", "pt": {"x": 1}, "span": None}]), rejected=True, errors=[err("E06", 2)])
    # parse -> dumps stability on non-canonical inputs
    add("roundtrip", "rt-quoted-to-escaped", "entrada con comillas: el canónico y su serialización escapada", contract=MK,
        input='mk|n=1\n"a, b"*,c|"x"*|a|1',
        canonical=C("mk", {"n": 1}, "rows", [{"one": ["a, b", "c"], "one_sel": 0, "some": ["x"], "some_sel": [0], "maybe": ["a"], "maybe_sel": None, "anyk": [1], "anyk_sel": []}]),
        mini="mk|n=1\na\\, b*,c|x*|a|1")
    add("roundtrip", "rt-over-escaped-normalised", "sobre-escapes y espacios se normalizan al serializar", contract=c,
        input="sc|n=1\n r1 |05|0.50|1|red|a\\, b\\*",
        canonical=C("sc", {"n": 1}, "rows", [sc_rec(memo="a, b*")]), mini="sc|n=1\nr1|5|0.5|true|red|a, b*")


def contract_cases() -> None:
    ok = {"prefix": "ok", "core": [{"name": "id", "type": "str"}]}
    add("contract", "contract-minimal-valid", "contrato mínimo válido", mode="contract", input=ok, errors=[])
    bad = [
        ("contract-no-prefix", "falta prefix", {"core": [{"name": "id", "type": "str"}]}),
        ("contract-bad-prefix", "prefix con caracteres inválidos", {"prefix": "1x", "core": [{"name": "id", "type": "str"}]}),
        ("contract-no-core", "sin campos núcleo", {"prefix": "x", "core": []}),
        ("contract-unknown-type", "tipo desconocido", {"prefix": "x", "core": [{"name": "id", "type": "datetime"}]}),
        ("contract-enum-no-values", "enum sin values", {"prefix": "x", "core": [{"name": "e", "type": "enum"}]}),
        ("contract-bad-marker", "regla de marcador desconocida", {"prefix": "x", "core": [{"name": "m", "type": "mlist", "marker": "two"}]}),
        ("contract-tuple-no-items", "tupla sin componentes", {"prefix": "x", "core": [{"name": "t", "type": "tuple"}]}),
        ("contract-tuple-nested", "tupla con componente compuesto", {"prefix": "x", "core": [{"name": "t", "type": "tuple", "items": [{"name": "l", "type": "list"}]}]}),
        ("contract-duplicate-field", "nombres de campo duplicados", {"prefix": "x", "core": [{"name": "id", "type": "str"}], "extensions": [{"name": "id", "type": "int"}]}),
        ("contract-bad-separator", "separador de lista reservado", {"prefix": "x", "list_separator": "|", "core": [{"name": "id", "type": "str"}]}),
        ("contract-list-composite-item", "lista cuyo elemento no es escalar", {"prefix": "x", "core": [{"name": "l", "type": "list", "item": "tuple"}]}),
        ("contract-field-no-type", "campo sin type", {"prefix": "x", "core": [{"name": "id"}]}),
    ]
    for cid, desc, d in bad:
        add("contract", cid, f"contrato inválido: {desc} (E20)", mode="contract", input=d, errors=[err("E20", 0)])

    parent = json.loads(read(FORKS / "a/contract.json"))
    add("fork", "fork-q-of-a", "q es una bifurcación válida de a", mode="fork", family="q", parent="a", input=None, errors=[])

    def child(mutate, prefix="ch"):
        d = copy.deepcopy(parent)
        d["prefix"], d["parent"] = prefix, "a"
        mutate(d)
        return d

    def swap(d):
        d["core"][1], d["core"][2] = d["core"][2], d["core"][1]

    def drop(d):
        d["core"] = d["core"][:-1]

    def retype(d):
        d["core"][6] = {"name": "difficulty", "type": "float"}

    def sep(d):
        d["list_separator"] = ";"

    def append_ok(d):
        d["extensions"] = [{"name": "nota", "type": "str"}]

    def rename(d):
        d["core"][0] = dict(d["core"][0], name="ident")

    def req_header(d):
        d["header"]["required"] = []

    add("fork", "fork-append-extension", "añadir extensiones al final es compatible", mode="fork", contract=child(append_ok), parent="a", input=None, errors=[])
    add("fork", "fork-reorder", "reordenar campos heredados (E21)", mode="fork", contract=child(swap), parent="a", input=None, errors=[err("E21", 0)])
    add("fork", "fork-drop", "eliminar un campo heredado (E21)", mode="fork", contract=child(drop), parent="a", input=None, errors=[err("E21", 0)])
    add("fork", "fork-retype", "cambiar el tipo de un campo heredado (E21)", mode="fork", contract=child(retype), parent="a", input=None, errors=[err("E21", 0)])
    add("fork", "fork-rename", "renombrar un campo heredado (E21)", mode="fork", contract=child(rename), parent="a", input=None, errors=[err("E21", 0)])
    add("fork", "fork-separator", "cambiar el separador de lista (E21)", mode="fork", contract=child(sep), parent="a", input=None, errors=[err("E21", 0)])
    add("fork", "fork-required-header", "fork que conserva los requeridos del padre (n implícito)", mode="fork", contract=child(req_header), parent="a", input=None, errors=[])


# =====================================================================
# 3. SPEC 1.1: rules for the points SPEC 1.0 left open (docs/adr/0009-0015)
# =====================================================================
OL = {  # optional lists and marked lists
    "prefix": "ol", "records_key": "rows",
    "core": [
        {"name": "id", "type": "str"},
        {"name": "req", "type": "list", "item": "str"},
        {"name": "opt", "type": "list", "item": "int", "optional": True, "min": 1},
    ],
    "extensions": [
        {"name": "sel", "type": "mlist", "item": "str", "marker": "exactly_one", "json": {"items": "sel", "selected": "sel_i"}},
        {"name": "tags", "type": "list", "item": "str"},
    ],
}


def spec11_cases() -> None:
    c = SC
    base = "sc|n=1\nr1|5|0.5|true|red|"

    # (1) \, is a valid escape whatever the list separator; \<sep> only for the contract's separator
    add("escapes", "esc-comma-custom-separator", "\\, es un escape válido aunque el separador sea ';' (SPEC 1.1 §3.3)", contract=SM,
        input="sm|n=1\nr\\,1|a\\,b;c|x*;y",
        canonical=C("sm", {"n": 1}, "rows", [{"id": "r,1", "xs": ["a,b", "c"], "opts": ["x", "y"], "ans": 0}]),
        mini="sm|n=1\nr,1|a,b;c|x*;y")
    add("escapes", "esc-other-separator-invalid", "\\; con el separador por defecto ',' no es un escape (E09)", contract=c,
        input=base + "a\\;b", errors=[err("E09", 2)])

    # (2) scalar lexical forms: bool true/false/1/0 only; no '+'; floats need digits on both sides
    for cid, desc, rec, code in [
        ("sc-bool-yes", "booleano 'yes' (E06)", "r1|5|0.5|yes|red", "E06"),
        ("sc-bool-t", "booleano 't' (E06)", "r1|5|0.5|t|red", "E06"),
        ("sc-bool-no", "booleano 'n' (E06)", "r1|5|0.5|n|red", "E06"),
        ("sc-bool-uppercase", "booleano 'True' distingue mayúsculas (E06)", "r1|5|0.5|True|red", "E06"),
        ("sc-int-plus", "entero con '+' (E06)", "r1|+5|0.5|true|red", "E06"),
        ("sc-int-unicode-digits", "dígitos no ASCII en un entero (E06)", "r1|５|0.5|true|red", "E06"),
        ("sc-float-plus", "float con '+' (E06)", "r1|5|+0.5|true|red", "E06"),
        ("sc-float-leading-dot", "float '.5' sin parte entera (E06)", "r1|5|.5|true|red", "E06"),
        ("sc-float-trailing-dot", "float '1.' sin decimales (E06)", "r1|5|1.|true|red", "E06"),
        ("sc-float-nan", "NaN no es un número (E06)", "r1|5|NaN|true|red", "E06"),
    ]:
        add("types", cid, desc, contract=c, input="sc|n=1\n" + rec, errors=[err(code, 2)])
    add("types", "sc-leading-zeros", "ceros a la izquierda en int y float se aceptan y se normalizan", contract=c,
        input="sc|n=1\nr1|007|00.5|0|red", canonical=C("sc", {"n": 1}, "rows", [sc_rec(qty=7, flag=False)]))

    # (3) ill-typed header values: code of the type violation, no E03
    h = HD
    add("header", "hdr-n-not-int", "n=abc: E06 en la cabecera, sin E03 ni E04 (SPEC 1.1 §5)", contract=h,
        input="hd|n=abc|src=s\nx", errors=[err("E06", 1)])
    add("header", "hdr-n-empty", "n vacío: E06 en la cabecera, sin E03", contract=h,
        input="hd|n=|src=s\nx", errors=[err("E06", 1)])
    add("header", "hdr-typed-scalar-bad", "clave tipada int con valor inválido (E06)", contract=h,
        input="hd|n=1|src=s|k=dos\nx", errors=[err("E06", 1)])
    add("header", "hdr-n-not-int-lenient", "n inválido en modo tolerante: registros conservados y sin registros faltantes", mode="lenient", contract=h,
        input="hd|n=abc|src=s\nx", canonical={"prefix": "hd", "header": {"v": 1, "src": "s", "lang": "es"}, "rows": [{"id": "x"}]},
        errors=[err("E06", 1)], diagnostics={"invalid_lines": [], "missing_records": 0})

    # (4) duplicate header keys: E12, first occurrence kept
    add("header", "hdr-duplicate-key", "clave de cabecera repetida (E12)", contract=h,
        input="hd|n=1|src=a|src=b\nx", errors=[err("E12", 1)])
    add("header", "hdr-duplicate-n", "n repetido (E12); se conserva el primero, sin E04", contract=h,
        input="hd|n=1|src=s|n=2\nx", errors=[err("E12", 1)])
    add("header", "hdr-duplicate-key-lenient", "modo tolerante: se conserva la primera aparición de la clave", mode="lenient", contract=h,
        input="hd|n=1|src=s|model=a|model=b\nx",
        canonical=C("hd", {"n": 1, "src": "s", "lang": "es", "model": "a"}, "rows", [{"id": "x"}]), errors=[err("E12", 1)])

    # (5) empty list elements: a bare empty element is ""; the serializer writes ""
    L, H = LS, "ls|n=1|k=2"

    def lrec(xs=("x",), ns=(1,), es=("a",), ks=("p", "q")):
        return {"id": "r1", "xs": list(xs), "ns": list(ns), "es": list(es), "ks": list(ks)}

    add("lists", "list-empty-element-middle", "elemento vacío intermedio es la cadena vacía y se serializa como \"\"", contract=L,
        input=f"{H}\nr1|a,,b|1|a|p,q", canonical=C("ls", {"n": 1, "k": 2}, "rows", [lrec(xs=("a", "", "b"))]),
        mini=f'{H}\nr1|a,"",b|1|a|p,q')
    add("lists", "list-empty-element-trailing", "separador final: último elemento vacío", contract=L,
        input=f"{H}\nr1|a,|1|a|p,", canonical=C("ls", {"n": 1, "k": 2}, "rows", [lrec(xs=("a", ""), ks=("p", ""))]),
        mini=f'{H}\nr1|a,""|1|a|p,""')
    add("lists", "list-single-empty-string", "[\"\"] se escribe \"\" y vuelve a ser [\"\"] (ida y vuelta)", contract=L,
        input=f'{H}\nr1|""|1|a|p,q', canonical=C("ls", {"n": 1, "k": 2}, "rows", [lrec(xs=("",))]), mini=f'{H}\nr1|""|1|a|p,q')
    add("lists", "list-empty-element-int", "elemento vacío en lista de enteros (E06)", contract=L,
        input=f"{H}\nr1|x|1,,2|a|p,q", errors=[err("E06", 2)])
    add("lists", "list-empty-element-enum", "elemento vacío en lista de enum (E10)", contract=L,
        input=f"{H}\nr1|x|1|a,|p,q", errors=[err("E10", 2)])
    add("roundtrip", "dumps-empty-string-elements", "el serializador escribe \"\" para elementos vacíos", mode="dumps", contract=L,
        input=C("ls", {"n": 1, "k": 2}, "rows", [lrec(xs=("",), ns=(), ks=("", "q"))]), mini=f'{H}\nr1|""||a|"",q')
    add("mlist", "mlist-empty-marked-element", "'*' solo es un elemento vacío marcado", contract=MK,
        input="mk|n=1\n*,b|a*|a|1",
        canonical=C("mk", {"n": 1}, "rows", [{"one": ["", "b"], "one_sel": 0, "some": ["a"], "some_sel": [0], "maybe": ["a"], "maybe_sel": None, "anyk": [1], "anyk_sel": []}]),
        mini='mk|n=1\n""*,b|a*|a|1')

    # (6) an empty field is null for every optional field, lists and marked lists included
    def orec(req=(), opt=None, sel=None, sel_i=None, tags=None):
        return {"id": "r1", "req": list(req), "opt": opt, "sel": sel, "sel_i": sel_i, "tags": tags}

    add("optionals", "opt-list-empty-null", "lista opcional vacía es null; lista requerida vacía es []", contract=OL,
        input="ol|n=1\nr1|||a*,b", canonical=C("ol", {"n": 1}, "rows", [orec(sel=["a", "b"], sel_i=0)]), mini="ol|n=1\nr1|||a*,b")
    add("optionals", "opt-mlist-empty-null", "lista marcada opcional vacía es null (no E08)", contract=OL,
        input="ol|n=1\nr1|x|1||t", canonical=C("ol", {"n": 1}, "rows", [orec(req=("x",), opt=[1], tags=["t"])]), mini="ol|n=1\nr1|x|1||t")
    add("optionals", "opt-list-min-applies-when-present", "el mínimo de una lista opcional se aplica si no está vacía", contract={
        "prefix": "om", "records_key": "rows", "core": [{"name": "id", "type": "str"}, {"name": "l", "type": "list", "item": "str", "optional": True, "min": 2}]},
        input="om|n=2\nr1|\nr2|a", errors=[err("E07", 3)])
    add("roundtrip", "dumps-optional-list-empty-array", "[] en una lista opcional se escribe vacío (su forma canónica es null)", mode="dumps", contract=OL,
        input=C("ol", {"n": 1}, "rows", [orec(opt=[], tags=[])]), mini="ol|n=1\nr1||")

    # (7) serializer errors: parser code and the line the entry would occupy
    MKR = {"one": ["a", "b"], "one_sel": 0, "some": ["a"], "some_sel": [0], "maybe": ["a"], "maybe_sel": None, "anyk": [1], "anyk_sel": []}
    for cid, desc, contract, obj, code, line in [
        ("dumps-error-range", "valor fuera de rango (E13)", c, C("sc", {"n": 1}, "rows", [sc_rec(qty=500)]), "E13", 2),
        ("dumps-error-type", "texto en un campo int (E06)", c, C("sc", {"n": 1}, "rows", [sc_rec(qty="cinco")]), "E06", 2),
        ("dumps-error-non-integral", "float no entero en un campo int (E06)", c, C("sc", {"n": 1}, "rows", [sc_rec(qty=2.5)]), "E06", 2),
        ("dumps-error-required-empty-string", "texto requerido vacío (E06)", c, C("sc", {"n": 1}, "rows", [sc_rec(id="")]), "E06", 2),
        ("dumps-error-second-record", "el error se ubica en la línea del registro (E10 en la línea 3)", c,
         C("sc", {"n": 2}, "rows", [sc_rec(), sc_rec(id="r2", color="pink")]), "E10", 3),
        ("dumps-error-unique", "valor único repetido (E11)", c, C("sc", {"n": 2}, "rows", [sc_rec(), sc_rec()]), "E11", 3),
        ("dumps-error-list-arity", "lista bajo el mínimo (E07)", L, C("ls", {"n": 1, "k": 2}, "rows", [lrec(xs=())]), "E07", 2),
        ("dumps-error-count-key", "lista distinta de la clave de conteo (E07)", L, C("ls", {"n": 1, "k": 2}, "rows", [lrec(ks=("p",))]), "E07", 2),
        ("dumps-error-header-required", "falta una clave requerida de cabecera (E12 en la línea 1)", HD,
         {"prefix": "hd", "header": {"n": 1}, "rows": [{"id": "x"}]}, "E12", 1),
        ("dumps-error-selection-type", "selección que no es índice (E08)", MK, C("mk", {"n": 1}, "rows", [dict(MKR, one_sel="a")]), "E08", 2),
    ]:
        add("roundtrip", cid, f"el serializador rechaza con el código del parser: {desc}", mode="dumps", contract=contract,
            input=obj, rejected=True, errors=[err(code, line)])


# Points that SPEC 1.0 left open, the ADR that decides each one and the cases that
# fix the 1.1 rule (tests/test_conformance.py checks that every id exists).
SPEC_1_1_RULES: Dict[str, Dict[str, Any]] = {
    "escape-comma-any-separator": {"adr": "0009", "cases": ["esc-comma-custom-separator", "esc-other-separator-invalid"]},
    "scalar-lexical-forms": {"adr": "0010", "cases": ["sc-bool-yes", "sc-bool-t", "sc-bool-no", "sc-bool-uppercase", "sc-int-plus",
                                                      "sc-int-unicode-digits", "sc-float-plus", "sc-float-leading-dot",
                                                      "sc-float-trailing-dot", "sc-float-nan", "sc-leading-zeros"]},
    "header-value-type-code": {"adr": "0011", "cases": ["hdr-n-not-int", "hdr-n-empty", "hdr-typed-scalar-bad", "hdr-n-not-int-lenient"]},
    "header-duplicate-keys": {"adr": "0012", "cases": ["hdr-duplicate-key", "hdr-duplicate-n", "hdr-duplicate-key-lenient"]},
    "empty-list-elements": {"adr": "0013", "cases": ["list-empty-element-middle", "list-empty-element-trailing", "list-single-empty-string",
                                                     "list-empty-element-int", "list-empty-element-enum", "dumps-empty-string-elements",
                                                     "mlist-empty-marked-element"]},
    "empty-optional-list": {"adr": "0014", "cases": ["opt-list-empty-null", "opt-mlist-empty-null", "opt-list-min-applies-when-present",
                                                     "dumps-optional-list-empty-array"]},
    "serializer-error-codes": {"adr": "0015", "cases": ["dumps-error-range", "dumps-error-type", "dumps-error-non-integral",
                                                        "dumps-error-required-empty-string", "dumps-error-second-record", "dumps-error-unique",
                                                        "dumps-error-list-arity", "dumps-error-count-key", "dumps-error-header-required",
                                                        "dumps-error-selection-type", "dumps-reject-marker", "dumps-reject-enum"]},
    "date-decimal-types": {"adr": "0016", "cases": ["date-decimal-basic", "decimal-normalised", "decimal-exact-digits", "date-decimal-composites",
                                                    "date-bad-format", "date-not-in-calendar", "date-error-line", "date-range", "decimal-range-max",
                                                    "hdr-date-bad", "date-lenient", "dumps-date-decimal", "dumps-error-date",
                                                    "dumps-error-decimal-float", "contract-date-decimal-valid", "contract-date-bad-bound"]},
}


DT = {  # date and decimal (SPEC 1.1 §6)
    "prefix": "dt", "records_key": "rows",
    "header": {"keys": {"d": {"type": "date"}}},
    "core": [
        {"name": "id", "type": "str", "unique": True},
        {"name": "day", "type": "date", "min": "2000-01-01", "max": "2099-12-31"},
        {"name": "amount", "type": "decimal", "min": 0, "max": "1000.00"},
    ],
    "extensions": [
        {"name": "rate", "type": "decimal"},
        {"name": "days", "type": "list", "item": "date"},
        {"name": "span", "type": "tuple", "items": [{"name": "start", "type": "date"}, {"name": "total", "type": "decimal", "optional": True}]},
    ],
}


def dt_rec(id="r1", day="2024-02-29", amount="12.50", rate=None, days=None, span=None):
    return {"id": id, "day": day, "amount": amount, "rate": rate, "days": days, "span": span}


def date_decimal_cases() -> None:
    c = DT

    def one(**kw):
        return C("dt", {"n": 1}, "rows", [dt_rec(**kw)])

    add("types", "date-decimal-basic", "date AAAA-MM-DD y decimal exacto: JSON canónico string", contract=c,
        input="dt|n=1\nr1|2024-02-29|12.50", canonical=one(), mini="dt|n=1\nr1|2024-02-29|12.50")
    add("types", "decimal-normalised", "decimal: sin ceros a la izquierda ni signo en cero; conserva la escala", contract=c,
        input="dt|n=2\nr1|2024-01-01|007.50\nr2|2024-01-01|-0.00|-000.10",
        canonical=C("dt", {"n": 2}, "rows", [dt_rec(day="2024-01-01", amount="7.50"), dt_rec(id="r2", day="2024-01-01", amount="0.00", rate="-0.10")]),
        mini="dt|n=2\nr1|2024-01-01|7.50\nr2|2024-01-01|0.00|-0.10")
    add("types", "decimal-exact-digits", "decimal conserva todos los dígitos (sin redondeo binario)", contract=c,
        input="dt|n=1\nr1|2024-02-29|999.99999999999999999999|0.1000000000000000055511151231257827",
        canonical=one(amount="999.99999999999999999999", rate="0.1000000000000000055511151231257827"),
        mini="dt|n=1\nr1|2024-02-29|999.99999999999999999999|0.1000000000000000055511151231257827")
    add("types", "date-decimal-composites", "listas y tuplas de date/decimal y clave de cabecera date", contract=c,
        input="dt|n=1|d=2026-09-17\nr1|2024-02-29|12.50||2024-01-01,2024-12-31|2024-03-01,99.9",
        canonical=C("dt", {"n": 1, "d": "2026-09-17"}, "rows", [dt_rec(days=["2024-01-01", "2024-12-31"], span={"start": "2024-03-01", "total": "99.9"})]),
        mini="dt|n=1|d=2026-09-17\nr1|2024-02-29|12.50||2024-01-01,2024-12-31|2024-03-01,99.9")
    for cid, desc, rec, code in [
        ("date-bad-format", "fecha que no es AAAA-MM-DD (E06)", "r1|24-02-29|1", "E06"),
        ("date-slashes", "fecha con barras (E06)", "r1|2024/02/29|1", "E06"),
        ("date-with-time", "fecha con hora (E06)", "r1|2024-02-29T10:00|1", "E06"),
        ("date-not-in-calendar", "29 de febrero de un año no bisiesto (E06)", "r1|2023-02-29|1", "E06"),
        ("date-month-13", "mes 13 (E06)", "r1|2024-13-01|1", "E06"),
        ("date-year-zero", "año 0000 (E06)", "r1|0000-01-01|1", "E06"),
        ("date-range", "fecha bajo el mínimo del contrato (E13)", "r1|1999-12-31|1", "E13"),
        ("decimal-comma", "decimal con coma (E06)", "r1|2024-02-29|1,5", "E06"),
        ("decimal-exponent", "decimal con exponente (E06)", "r1|2024-02-29|1e3", "E06"),
        ("decimal-leading-dot", "decimal '.5' (E06)", "r1|2024-02-29|.5", "E06"),
        ("decimal-plus", "decimal con '+' (E06)", "r1|2024-02-29|+1", "E06"),
        ("decimal-range-max", "decimal sobre el máximo, comparación exacta (E13)", "r1|2024-02-29|1000.0000000000000000001", "E13"),
        ("decimal-range-min", "decimal bajo el mínimo (E13)", "r1|2024-02-29|-0.01", "E13"),
        ("date-list-item-bad", "elemento de lista date inválido (E06)", "r1|2024-02-29|1||2024-01-01,2024-02-30", "E06"),
        ("decimal-tuple-component-bad", "componente decimal inválido en tupla (E06)", "r1|2024-02-29|1|||2024-01-01,1.2.3", "E06"),
    ]:
        add("types", cid, desc, contract=c, input="dt|n=1\n" + rec, errors=[err(code, 2)])
    add("types", "date-error-line", "fecha inválida: E06 con el número de línea del registro", contract=c,
        input="dt|n=3\nr1|2024-01-01|1\nr2|2024-31-01|1\nr3|2024-01-03|1", errors=[err("E06", 3)])
    add("header", "hdr-date-bad", "clave de cabecera date inválida (E06)", contract=c,
        input="dt|n=1|d=17/09/2026\nr1|2024-02-29|1", errors=[err("E06", 1)])
    add("types", "date-lenient", "modo tolerante descarta solo el registro con la fecha inválida", mode="lenient", contract=c,
        input="dt|n=2\nr1|2024-02-30|1\nr2|2024-02-29|12.50",
        canonical=C("dt", {"n": 2}, "rows", [dt_rec(id="r2")]), errors=[err("E06", 2)],
        diagnostics={"invalid_lines": [2], "missing_records": 0})
    add("roundtrip", "dumps-date-decimal", "serialización de date y decimal", mode="dumps", contract=c,
        input=C("dt", {"n": 1}, "rows", [dt_rec(amount="1000.00", rate="-3", days=[], span={"start": "2000-01-01", "total": None})]),
        mini="dt|n=1\nr1|2024-02-29|1000.00|-3||2000-01-01,")
    add("roundtrip", "dumps-error-date", "fecha inexistente no se puede serializar (E06)", mode="dumps", contract=c,
        input=one(day="2024-02-30"), rejected=True, errors=[err("E06", 2)])
    add("roundtrip", "dumps-error-decimal-float", "un decimal se entrega como string, no como float binario (E06)", mode="dumps", contract=c,
        input=one(amount=12.5), rejected=True, errors=[err("E06", 2)])
    add("contract", "contract-date-decimal-valid", "contrato con date y decimal y sus límites", mode="contract", input=DT, errors=[])
    add("contract", "contract-date-bad-bound", "límite date que no es una fecha válida (E20)", mode="contract",
        input={"prefix": "x", "core": [{"name": "d", "type": "date", "min": "2024-02-30"}]}, errors=[err("E20", 0)])
    add("contract", "contract-decimal-float-bound", "límite decimal float no entero (E20: se escribe como string)", mode="contract",
        input={"prefix": "x", "core": [{"name": "m", "type": "decimal", "max": 1.5}]}, errors=[err("E20", 0)])


def build() -> Dict[str, List[Dict[str, Any]]]:
    CASES.clear()
    fixture_cases()
    scalar_cases()
    list_cases()
    mlist_cases()
    tuple_cases()
    escape_cases()
    quote_cases()
    header_cases()
    truncation_cases()
    dumps_cases()
    contract_cases()
    spec11_cases()
    date_decimal_cases()
    return CASES


def main() -> None:
    cases = build()
    CASES_DIR.mkdir(exist_ok=True)
    for old in CASES_DIR.glob("*.json"):
        old.unlink()
    total = 0
    for cat in sorted(cases):
        doc = {"suite": ".mini conformance", "spec": SPEC_VERSION, "category": cat, "cases": cases[cat]}
        with open(CASES_DIR / f"{cat}.json", "w", encoding="utf-8", newline="\n") as fh:
            fh.write(json.dumps(doc, ensure_ascii=False, indent=2) + "\n")
        total += len(cases[cat])
        print(f"{cat:12s} {len(cases[cat]):4d}")
    print(f"{'total':12s} {total:4d}")


if __name__ == "__main__":
    main()
