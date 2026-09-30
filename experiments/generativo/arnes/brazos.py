"""Brazos (condiciones) del experimento: construcción de prompts y lectores.

Condiciones del Plan de Validación v3 (§5):

A    JSON con instrucción MÍNIMA: solo la forma del documento y los nombres de
     campo, sin tipos, rangos, ejemplo ni reglas; lectura con ``json.loads``
     (quitando cercas de código, práctica habitual).
B    JSON con el contrato descrito en el prompt (tipos, rangos, opcionales,
     ejemplo); misma lectura que A.
C    JSON con restricción nativa del proveedor (``response_format`` /
     ``json_schema``) derivada del contrato; misma lectura que A. Solo donde el
     modelo la admite: si no, la celda es ``no_aplicable`` (no un fallo).
D    .mini con biblioteca: instrucción ``spec_block(contrato, idioma)``, lectura
     con ``extract_document`` + ``minifmt.parse(..., strict=False)``.
X+1  UNA reparación selectiva de la MISMA respuesta del brazo X (no otra muestra
     independiente), para X en A, B, C y D. D+1 usa ``minifmt.ai.repair_request``
     / ``merge_repair``; A+1, B+1 y C+1 usan la reparación equivalente para JSON
     (``json_tolerante``): así la ventaja de un formato no se confunde con que
     solo un brazo tenga reparación.
A0   Control opcional FUERA del diseño del Plan: prompt escrito a mano ("una
     línea por registro, campos separados por |") con lectura ``split('|')``
     ingenua, como la haría un equipo sin biblioteca. Era el «A» del arnés
     anterior; no se incluye en las configuraciones del estudio.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from minifmt import Contract, dumps
from minifmt.ai import extract_document, lenient_parse
from minifmt.ai.adapters.simulated import naive_cell
from minifmt.errors import E_NO_HEADER, E_UNKNOWN_PREFIX
from minifmt.prompt import spec_block
from minifmt.serializer import encode_header

from .tareas import Tarea

BRAZOS_PRIMARIOS = ("A0", "A", "B", "C", "D")
BASE_REPARACION = {"A+1": "A", "B+1": "B", "C+1": "C", "D+1": "D"}   # brazo de reparación -> brazo que repara
BRAZOS = BRAZOS_PRIMARIOS + tuple(BASE_REPARACION)
GENERADORES = set(BRAZOS_PRIMARIOS)        # brazos que hacen una llamada de generación propia
ORDEN_BRAZOS = ["A", "A+1", "B", "B+1", "C", "C+1", "D", "D+1", "A0"]   # orden de presentación


def es_reparacion(brazo: str) -> bool:
    return brazo in BASE_REPARACION


def base_de(brazo: str) -> str:
    """Brazo cuya respuesta se usa (el propio brazo si genera; el que repara si es X+1)."""
    return BASE_REPARACION.get(brazo, brazo)


def formato_de(brazo: str) -> str:
    return {"A0": "pipe", "A": "json", "B": "json", "C": "json", "D": "mini"}[base_de(brazo)]


@dataclass
class Prompt:
    system: str
    user: str
    response_format: Optional[Dict[str, Any]] = None


@dataclass
class Lectura:
    registros: List[Dict[str, Any]]
    avisos: List[str] = field(default_factory=list)
    parseable: bool = True
    n_declarado: Optional[int] = None


# --------------------------------------------------------------------------
# Descripción de campos (común a A, B y C)
# --------------------------------------------------------------------------
def _tipo_humano(f) -> str:
    if f.type == "enum":
        return "uno de: " + ", ".join(f.values or [])
    if f.type == "list":
        return f"lista de {f.item if f.item != 'enum' else 'uno de: ' + ', '.join(f.item_values or [])}" + _rango_lista(f)
    if f.type == "mlist":
        regla = {"exactly_one": "exactamente uno", "at_least_one": "al menos uno", "at_most_one": "como máximo uno",
                 "any": "cero o más"}[f.marker]
        return f"lista de opciones con selección ({regla} seleccionado)" + _rango_lista(f)
    if f.type == "tuple":
        return "grupo fijo (" + ", ".join(f"{c.name}: {c.type}" for c in f.items) + ")"
    rng = ""
    if f.min is not None or f.max is not None:
        rng = f" entre {f.min if f.min is not None else '-∞'} y {f.max if f.max is not None else '∞'}"
    pista = {"date": " (AAAA-MM-DD)", "decimal": " (decimal exacto sin exponente, p. ej. 12.50)"}.get(f.type, "")
    return f.type + rng + pista + (f" — {f.desc}" if f.desc else "")


def _rango_lista(f) -> str:
    if f.min is None and f.max is None:
        return ""
    return f", entre {int(f.min or 0)} y {int(f.max) if f.max else '∞'} elementos"


def _campos_lista(c: Contract) -> str:
    return "\n".join(f"  {i+1}. {f.name}: {_tipo_humano(f)}" + (" (opcional)" if f.optional else "")
                     for i, f in enumerate(c.fields))


def _ejemplo_pipe(t: Tarea) -> str:
    return "|".join(naive_cell(t.ejemplo.get(f.name), f, t.ejemplo) for f in t.contrato.fields)


def _registro_json(rec: Dict[str, Any], c: Contract) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    for f in c.fields:
        if f.type == "mlist":
            out[f.json_items] = rec.get(f.json_items)
            out[f.json_selected] = rec.get(f.json_selected)
        else:
            out[f.name] = rec.get(f.name)
    return out


def _mensaje_usuario(t: Tarea) -> str:
    if t.tipo == "extraccion":
        return t.instruccion + "\n\n" + t.texto_entrada
    return t.instruccion


def cabecera_mini_sin_n(t: Tarea) -> str:
    linea = encode_header(t.cabecera, t.contrato, 0)
    return linea.replace("|n=0", "|n=<número de registros>", 1)


# --------------------------------------------------------------------------
# Esquema JSON (brazo C)
# --------------------------------------------------------------------------
_JSON_T = {"str": "string", "int": "integer", "float": "number", "bool": "boolean", "date": "string", "decimal": "string"}


def _esq_escalar(tipo: str, valores: Optional[List[str]]) -> Dict[str, Any]:
    if tipo == "enum":
        return {"type": "string", "enum": list(valores or [])}
    return {"type": _JSON_T[tipo]}


def _nullable(s: Dict[str, Any], opcional: bool) -> Dict[str, Any]:
    return {"anyOf": [s, {"type": "null"}]} if opcional else s


def esquema_json(c: Contract) -> Dict[str, Any]:
    props: Dict[str, Any] = {}
    for f in c.fields:
        if f.type in ("str", "int", "float", "bool", "enum"):
            props[f.name] = _nullable(_esq_escalar(f.type, f.values), f.optional)
        elif f.type == "list":
            props[f.name] = _nullable({"type": "array", "items": _esq_escalar(f.item, f.item_values)}, f.optional)
        elif f.type == "mlist":
            props[f.json_items] = _nullable({"type": "array", "items": _esq_escalar(f.item, f.item_values)}, f.optional)
            sel = ({"type": "integer"} if f.marker in ("exactly_one",) else
                   {"anyOf": [{"type": "integer"}, {"type": "null"}]} if f.marker == "at_most_one" else
                   {"type": "array", "items": {"type": "integer"}})
            props[f.json_selected] = _nullable(sel, f.optional)
        elif f.type == "tuple":
            comps = {cmp.name: _nullable(_esq_escalar(cmp.type, cmp.values), cmp.optional) for cmp in f.items}
            props[f.name] = _nullable({"type": "object", "properties": comps, "required": list(comps),
                                       "additionalProperties": False}, f.optional)
    registro = {"type": "object", "properties": props, "required": list(props), "additionalProperties": False}
    return {"type": "object", "properties": {c.records_key: {"type": "array", "items": registro}},
            "required": [c.records_key], "additionalProperties": False}


# --------------------------------------------------------------------------
# Prompts
# --------------------------------------------------------------------------
def nombres_json(c: Contract) -> List[str]:
    """Claves de un registro JSON, en el orden del contrato (una lista con selección son dos claves)."""
    out: List[str] = []
    for f in c.fields:
        out += [f.json_items, f.json_selected] if f.type == "mlist" else [f.name]
    return out


def _nota_seleccion(c: Contract) -> str:
    mlist = [f for f in c.fields if f.type == "mlist"]
    if not mlist:
        return ""
    f = mlist[0]
    return (f" En '{f.json_items}' van las opciones y en '{f.json_selected}' el índice (base 0) "
            "de la opción seleccionada, o la lista de índices si puede haber varias.")


def construir_prompt(t: Tarea, brazo: str, idioma: str = "es") -> Prompt:
    """Prompt del brazo; un brazo de reparación (X+1) comparte el prompt de generación de X."""
    c = t.contrato
    user = _mensaje_usuario(t)
    brazo = base_de(brazo)
    if brazo == "A0":
        sistema = (
            "Devuelve los datos como texto plano: una línea por registro, campos separados por | en este orden:\n"
            + _campos_lista(c)
            + "\nLas listas y los grupos fijos van con sus elementos separados por comas. En las listas con selección, marca cada "
              "elemento seleccionado con * al final. Deja vacío un campo sin valor. Los booleanos se escriben "
              "true o false. No escribas encabezado ni texto adicional.\nEjemplo de una línea:\n"
            + _ejemplo_pipe(t))
        return Prompt(sistema, user)
    if brazo == "A":
        # instrucción mínima: forma del documento y nombres de campo; nada más (sin tipos, rangos, ejemplo ni reglas)
        sistema = (f"Devuelve solo JSON: un objeto con la clave \"{c.records_key}\" que contiene una lista con un objeto "
                   "por registro, con los campos: " + ", ".join(nombres_json(c)) + ".")
        return Prompt(sistema, user)
    if brazo in ("B", "C"):
        ejemplo = json.dumps({c.records_key: [_registro_json(t.ejemplo, c)]}, ensure_ascii=False)
        descripcion = (c.description + "\n") if c.description else ""
        sistema = (
            f"Devuelve solo un documento JSON válido con la forma {{\"{c.records_key}\": [ ... ]}}, un objeto por "
            "registro, con estos campos:\n" + descripcion + _campos_lista(c) + "\n" + _nota_seleccion(c)
            + " Usa null para campos sin valor. Sin texto adicional.\nEjemplo con un registro:\n" + ejemplo)
        rf = None
        if brazo == "C":
            rf = {"type": "json_schema", "name": f"salida_{c.prefix}", "schema": esquema_json(c)}
        return Prompt(sistema, user, rf)
    if brazo == "D":
        ej = dumps({"header": t.cabecera, c.records_key: [t.ejemplo]}, c)
        sistema = spec_block(c, idioma, ej)
        sistema += f"\nCabecera que debes usar: {cabecera_mini_sin_n(t)}"
        sistema += ("\nDevuelve solo el documento .mini." if idioma == "es" else "\nReturn only the .mini document.")
        return Prompt(sistema, user)
    raise ValueError(f"brazo desconocido: {brazo}")


# --------------------------------------------------------------------------
# Salida de referencia (estimación de tokens de salida y límites de V3b)
# --------------------------------------------------------------------------
def salida_referencia(t: Tarea, brazo: str) -> str:
    c = t.contrato
    brazo = base_de(brazo)
    if brazo == "A0":
        return "\n".join("|".join(naive_cell(r.get(f.name), f, r) for f in c.fields) for r in t.registros)
    if brazo in ("A", "B"):
        return json.dumps({c.records_key: [_registro_json(r, c) for r in t.registros]}, ensure_ascii=False, indent=1)
    if brazo == "C":
        return json.dumps({c.records_key: [_registro_json(r, c) for r in t.registros]}, ensure_ascii=False)
    return dumps({"header": t.cabecera, c.records_key: t.registros}, c)


# --------------------------------------------------------------------------
# Lectores
# --------------------------------------------------------------------------
class _Rechazo(Exception):
    pass


def _conv_ingenua(txt: str, tipo: str) -> Any:
    txt = txt.strip()
    if tipo == "int":
        try:
            return int(txt)
        except ValueError:
            raise _Rechazo(f"int inválido '{txt}'") from None
    if tipo == "float":
        try:
            return float(txt)
        except ValueError:
            raise _Rechazo(f"float inválido '{txt}'") from None
    if tipo == "bool":
        return txt.lower() == "true"
    return txt


def leer_pipe(texto: str, t: Tarea) -> Lectura:
    c = t.contrato
    regs, avisos = [], []
    for k, linea in enumerate((texto or "").split("\n"), 1):
        s = linea.strip()
        if not s or s.startswith("```"):
            continue
        partes = s.split("|")
        if not (c.arity <= len(partes) <= len(c.fields)):
            avisos.append(f"línea {k}: {len(partes)} campos, se esperaban {len(c.fields)}")
            continue
        rec: Dict[str, Any] = {}
        try:
            for i, f in enumerate(c.fields):
                crudo = partes[i].strip() if i < len(partes) else ""
                if f.type == "mlist":
                    elems = [e.strip() for e in crudo.split(",")] if crudo else []
                    marcados = [j for j, e in enumerate(elems) if e.endswith("*")]
                    rec[f.json_items] = [_conv_ingenua(e.rstrip("*"), f.item) for e in elems] if crudo else None
                    if f.marker in ("exactly_one", "at_most_one"):
                        rec[f.json_selected] = marcados[0] if marcados else None
                    else:
                        rec[f.json_selected] = marcados
                elif f.type == "list":
                    rec[f.name] = [_conv_ingenua(e, f.item) for e in crudo.split(",")] if crudo else []
                elif f.type == "tuple":
                    comps = crudo.split(",") if crudo else []
                    if len(comps) != len(f.items):
                        raise _Rechazo(f"{f.name}: {len(comps)} componentes")
                    rec[f.name] = {cmp.name: (_conv_ingenua(v, cmp.type) if v.strip() else None)
                                   for cmp, v in zip(f.items, comps)}
                else:
                    rec[f.name] = _conv_ingenua(crudo, f.type) if crudo else None
        except _Rechazo as e:
            avisos.append(f"línea {k}: {e}")
            continue
        regs.append(rec)
    return Lectura(regs, avisos, parseable=bool((texto or "").strip()))


_CERCA = re.compile(r"^\s*```[a-zA-Z]*\s*\n?|\n?\s*```\s*$")


def leer_json(texto: str, t: Tarea) -> Lectura:
    c = t.contrato
    s = (texto or "").strip()
    if s.startswith("```"):
        s = _CERCA.sub("", s).strip()
    try:
        obj = json.loads(s)
    except ValueError as e:
        return Lectura([], [f"JSON inválido: {str(e)[:120]}"], parseable=False)
    arr = obj.get(c.records_key) if isinstance(obj, dict) else obj if isinstance(obj, list) else None
    if not isinstance(arr, list):
        return Lectura([], [f"JSON sin la lista '{c.records_key}'"], parseable=False)
    regs, avisos = [], []
    for k, r in enumerate(arr):
        if not isinstance(r, dict):
            avisos.append(f"elemento {k} no es un objeto")
            continue
        regs.append(_registro_json(r, c))
    return Lectura(regs, avisos, parseable=True)


def leer_D(texto: str, t: Tarea) -> Lectura:
    c = t.contrato
    doc_txt = extract_document(texto or "", c)
    doc, errores = lenient_parse(doc_txt, c)
    avisos = [str(e) for e in errores]
    if doc is None:
        return Lectura([], avisos or ["documento vacío"], parseable=False)
    parseable = not any(e.code in (E_NO_HEADER, E_UNKNOWN_PREFIX) for e in errores)
    n = doc.header.get("n")
    return Lectura([dict(r) for r in doc.records], avisos, parseable=parseable,
                   n_declarado=n if isinstance(n, int) else None)


def leer(brazo: str, texto: str, t: Tarea) -> Lectura:
    """Lector del brazo. Los brazos X+1 leen con el lector de X (el documento reparado tiene su mismo formato)."""
    f = formato_de(brazo)
    if f == "pipe":
        return leer_pipe(texto, t)
    if f == "json":
        return leer_json(texto, t)
    return leer_D(texto, t)


def tipo_objetivo_simulado(brazo: str) -> str:
    return {"A0": "pipe", "A": "json_minimo", "B": "json", "C": "json_schema", "D": "mini"}[base_de(brazo)]
