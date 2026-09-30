"""Métricas por muestra.

Extracción (salida esperada conocida)
------------------------------------
Cada registro aceptado por el lector se empareja con un registro esperado
(emparejamiento voraz por número de campos iguales, con desempate por
posición; se exige al menos la mitad de los campos iguales).  Resultado por
registro esperado:

* ``correcto``               aceptado e idéntico (tras normalización);
* ``incorrecto_sin_aviso``   aceptado con algún campo distinto;
* ``perdido_detectado``      no aceptado y el lector emitió al menos un aviso;
* ``perdido_sin_aviso``      no aceptado y el lector no emitió ningún aviso.

Los registros aceptados que no se emparejan son ``espurios`` y también cuentan
como incorrectos aceptados sin aviso (el consumidor recibe un registro que no
existe en la entrada).

Generativa (evaluación contra el contrato)
------------------------------------------
Un registro aceptado es ``correcto`` si cumple el contrato (tipos JSON
estrictos, enumeraciones, rangos, aridades, marcadores, clave de conteo y
unicidad) e ``incorrecto_sin_aviso`` si no lo cumple.  Se pierden
``max(0, n_solicitados - aceptados)``, detectados si hubo aviso.

Tres cosas distintas, nunca fusionadas
--------------------------------------
* **sintaxis analizable** (``sintaxis_ok``): el documento se pudo leer;
* **cumplimiento del contrato** (``validos_contrato``): registros aceptados que
  cumplen tipos, enumeraciones, rangos, aridades, marcadores y unicidad de
  identidad, con o sin referencia;
* **exactitud del contenido** (``exactos_contenido``, solo con referencia):
  registros idénticos a los esperados.

La **validez final** es ``validos_finales / solicitados``: el denominador son
TODOS los registros solicitados, de modo que un registro ausente cuenta como no
válido (``validos_finales`` se acota a ``solicitados``; el exceso va a
``excedentes``).

Normalización de comparación: espacios en blanco colapsados (un salto de línea
equivale a un espacio), cadena vacía equivale a nulo, números por valor.
"""
from __future__ import annotations

from typing import Any, Dict, List, Tuple

from minifmt import Contract, canonical_equal, parse
from minifmt.serializer import encode_header, encode_record

from .brazos import Lectura
from .tareas import Tarea


def claves_registro(c: Contract) -> List[str]:
    out = []
    for f in c.fields:
        if f.type == "mlist":
            out += [f.json_items, f.json_selected]
        else:
            out.append(f.name)
    return out


def _norm(v: Any) -> Any:
    if isinstance(v, str):
        s = " ".join(v.split())
        return s if s else None
    if isinstance(v, bool) or v is None:
        return v
    if isinstance(v, (int, float)):
        return float(v)
    if isinstance(v, (list, tuple)):
        return [_norm(x) for x in v]
    if isinstance(v, dict):
        return {k: _norm(x) for k, x in v.items()}
    return v


def _igual(a: Any, b: Any) -> bool:
    if isinstance(a, bool) or isinstance(b, bool):
        return isinstance(a, bool) and isinstance(b, bool) and a == b
    if isinstance(a, list) and isinstance(b, list):
        return len(a) == len(b) and all(_igual(x, y) for x, y in zip(a, b))
    if isinstance(a, dict) and isinstance(b, dict):
        return a.keys() == b.keys() and all(_igual(a[k], b[k]) for k in a)
    return canonical_equal(a, b)


def campo_igual(a: Any, b: Any) -> bool:
    return _igual(_norm(a), _norm(b))


def _iguales(got: Dict[str, Any], exp: Dict[str, Any], claves: List[str]) -> int:
    return sum(1 for k in claves if campo_igual(got.get(k), exp.get(k)))


def emparejar(got: List[Dict[str, Any]], exp: List[Dict[str, Any]], claves: List[str]) -> List[Tuple[int, int, int]]:
    minimo = (len(claves) + 1) // 2
    cand = []
    for gi, g in enumerate(got):
        for ei, e in enumerate(exp):
            s = _iguales(g, e, claves)
            if s >= minimo:
                cand.append((s, -abs(gi - ei), gi, ei))
    cand.sort(reverse=True)
    usados_g, usados_e, pares = set(), set(), []
    for s, _, gi, ei in cand:
        if gi in usados_g or ei in usados_e:
            continue
        usados_g.add(gi)
        usados_e.add(ei)
        pares.append((gi, ei, s))
    return pares


def _base(lectura: Lectura) -> Dict[str, Any]:
    return {"parseable": bool(lectura.parseable), "avisos": len(lectura.avisos), "detectado": bool(lectura.avisos),
            "aceptados": len(lectura.registros), "sintaxis_ok": bool(lectura.parseable)}


def validar_aceptados(lectura: Lectura, t: Tarea) -> Tuple[int, int, int]:
    """(válidos por contrato, inválidos, identidades duplicadas) entre los registros aceptados por el lector."""
    c = t.contrato
    unicos = [f.name for f in c.fields if f.unique]
    vistos: Dict[str, set] = {u: set() for u in unicos}
    validos = invalidos = duplicados = 0
    for rec in lectura.registros:
        ok = cumple_contrato(rec, c, t.cabecera)
        for u in unicos:
            v = rec.get(u)
            try:
                if v in vistos[u]:
                    ok = False
                    duplicados += 1
                vistos[u].add(v)
            except TypeError:
                ok = False
        if ok:
            validos += 1
        else:
            invalidos += 1
    return validos, invalidos, duplicados


def _nuevas(m: Dict[str, Any], lectura: Lectura, t: Tarea, solicitados: int, exactos: Any) -> None:
    validos, _, dup = validar_aceptados(lectura, t)
    m.update({"solicitados": solicitados, "validos_contrato": validos,
              "validos_finales": min(validos, solicitados), "excedentes": max(0, validos - solicitados),
              "identidades_duplicadas": dup, "exactos_contenido": exactos})


def evaluar_extraccion(lectura: Lectura, t: Tarea) -> Dict[str, Any]:
    c = t.contrato
    claves = claves_registro(c)
    exp = t.registros
    pares = emparejar(lectura.registros, exp, claves)
    correctos = sum(1 for _, _, s in pares if s == len(claves))
    incorrectos = len(pares) - correctos
    espurios = len(lectura.registros) - len(pares)
    perdidos = len(exp) - len(pares)
    m = _base(lectura)
    campos_ok = sum(s for _, _, s in pares)
    m.update({
        "esperados": len(exp), "correctos": correctos,
        "incorrectos_emparejados": incorrectos, "espurios": espurios,
        "incorrectos_sin_aviso": incorrectos + espurios,
        "perdidos": perdidos,
        "perdidos_detectados": perdidos if lectura.avisos else 0,
        "perdidos_sin_aviso": 0 if lectura.avisos else perdidos,
        "campos_correctos": campos_ok, "campos_totales": len(exp) * len(claves),
        "exacto": correctos == len(exp) and espurios == 0,
    })
    _nuevas(m, lectura, t, len(exp), correctos)
    return m


_TIPOS_PY = {"str": (str,), "int": (int,), "float": (int, float), "bool": (bool,), "enum": (str,),
             "date": (str,), "decimal": (str,)}


def _tipo_ok(v: Any, tipo: str) -> bool:
    if tipo in ("int", "float") and isinstance(v, bool):
        return False
    return isinstance(v, _TIPOS_PY[tipo])


def tipos_estrictos(rec: Dict[str, Any], c: Contract) -> bool:
    for f in c.fields:
        if f.type == "mlist":
            items, sel = rec.get(f.json_items), rec.get(f.json_selected)
            if items is None:
                if not f.optional:
                    return False
                continue
            if not isinstance(items, list) or not all(_tipo_ok(x, f.item) for x in items):
                return False
            if sel is not None and not (isinstance(sel, int) and not isinstance(sel, bool) or
                                        isinstance(sel, list) and all(isinstance(x, int) and not isinstance(x, bool) for x in sel)):
                return False
            continue
        v = rec.get(f.name)
        if v is None:
            if not f.optional:
                return False
            continue
        if f.type == "list":
            if not isinstance(v, list) or not all(_tipo_ok(x, f.item) for x in v):
                return False
        elif f.type == "tuple":
            if not isinstance(v, dict):
                return False
            for cmp in f.items:
                x = v.get(cmp.name)
                if x is None:
                    if not cmp.optional:
                        return False
                elif not _tipo_ok(x, cmp.type):
                    return False
        elif not _tipo_ok(v, f.type):
            return False
    return True


def cumple_contrato(rec: Dict[str, Any], c: Contract, cabecera: Dict[str, Any]) -> bool:
    if not tipos_estrictos(rec, c):
        return False
    try:
        texto = encode_header(cabecera, c, 1) + "\n" + encode_record(rec, c)
        doc = parse(texto, c, strict=False)
    except Exception:  # noqa: BLE001
        return False
    return not doc.errors and len(doc.records) == 1


def evaluar_generativa(lectura: Lectura, t: Tarea) -> Dict[str, Any]:
    validos, invalidos, _ = validar_aceptados(lectura, t)
    n = t.n_solicitados
    perdidos = max(0, n - len(lectura.registros))
    m = _base(lectura)
    m.update({
        "esperados": n, "correctos": min(validos, n), "excedentes": max(0, validos - n),
        "incorrectos_emparejados": invalidos, "espurios": 0, "incorrectos_sin_aviso": invalidos,
        "perdidos": perdidos,
        "perdidos_detectados": perdidos if lectura.avisos else 0,
        "perdidos_sin_aviso": 0 if lectura.avisos else perdidos,
        "campos_correctos": None, "campos_totales": None,
        "exacto": validos >= n and invalidos == 0,
    })
    _nuevas(m, lectura, t, n, None)
    return m


def evaluar(lectura: Lectura, t: Tarea) -> Dict[str, Any]:
    return evaluar_extraccion(lectura, t) if t.tipo == "extraccion" else evaluar_generativa(lectura, t)
