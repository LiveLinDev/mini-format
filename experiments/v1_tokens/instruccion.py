"""Bloques de instrucción equivalentes para .mini y JSON (tokens de entrada).

* ``mini_spec``           : ``spec_block(contract, lang)`` tal cual lo genera la biblioteca.
* ``mini_spec_ejemplo``   : el mismo bloque con un ejemplo válido de 1 registro.
* ``json_schema``         : frase de instrucción + JSON Schema (draft 2020-12) derivado
                            del contrato, serializado compacto (sin espacios).
* ``json_schema_ejemplo`` : lo anterior + el mismo ejemplo de 1 registro en JSON compacto.
* ``json_ejemplo``        : frase de instrucción + solo el ejemplo JSON (instrucción mínima).

El JSON Schema lleva la misma información que el bloque .mini: nombre y
descripción del contrato, claves de cabecera tipadas, campos con tipo, enumerados,
rangos, aridad de listas y descripciones de campos escalares. No se agrega
``additionalProperties: false`` (lo exigiría el modo estricto de algunas APIs y
alargaría el esquema), de modo que es una cota favorable a JSON.
"""
from __future__ import annotations

import json
from typing import Any, Dict

from minifmt import spec_block
from minifmt.contract import Contract, Field

import comun as C
import formats

_TIPOS = {"str": "string", "int": "integer", "float": "number", "bool": "boolean", "enum": "string"}


def _escalar(tipo: str, values=None) -> Dict[str, Any]:
    d: Dict[str, Any] = {"type": _TIPOS[tipo]}
    if tipo == "enum" and values:
        d["enum"] = list(values)
    return d


def _campo(f: Field) -> Dict[str, Dict[str, Any]]:
    """Propiedades JSON que produce un campo del contrato (mlist produce dos)."""
    if f.type in ("str", "int", "float", "bool", "enum"):
        d = _escalar(f.type, f.values)
        if f.type in ("int", "float"):
            if f.min is not None:
                d["minimum"] = f.min
            if f.max is not None:
                d["maximum"] = f.max
        if f.desc:
            d["description"] = f.desc
        return {f.name: d}
    if f.type in ("list", "mlist"):
        arr: Dict[str, Any] = {"type": "array", "items": _escalar(f.item, f.item_values)}
        if f.min is not None:
            arr["minItems"] = int(f.min)
        if f.max is not None:
            arr["maxItems"] = int(f.max)
        if f.type == "list":
            return {f.name: arr}
        if f.marker in ("exactly_one", "at_most_one"):
            sel = {"type": "integer", "minimum": 0, "description": f"0-based index of the selected element of {f.json_items}"}
        else:
            sel = {"type": "array", "items": {"type": "integer", "minimum": 0},
                   "description": f"ascending 0-based indices of the selected elements of {f.json_items}"}
        return {f.json_items: arr, f.json_selected: sel}
    if f.type == "tuple":
        props = {}
        for comp in f.items:
            props.update(_campo(comp))
        return {f.name: {"type": "object", "properties": props, "required": [c.name for c in f.items]}}
    raise ValueError(f.type)


def json_schema(c: Contract) -> Dict[str, Any]:
    hdr_props: Dict[str, Any] = {}
    hdr_req = []
    for k, hk in c.header_keys.items():
        if k in ("n", "v"):  # el objeto JSON canónico no lleva n ni v
            continue
        hdr_props.update(_campo(hk.as_field()))
        if hk.required:
            hdr_req.append(k)
    rec_props: Dict[str, Any] = {}
    rec_req = []
    for f in list(c.core) + list(c.extensions):
        p = _campo(f)
        rec_props.update(p)
        if not f.optional and f not in c.extensions:
            rec_req.extend(p.keys())
    header = {"type": "object", "properties": hdr_props}
    if hdr_req:
        header["required"] = hdr_req
    schema: Dict[str, Any] = {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "title": c.name or c.prefix,
    }
    if c.description:
        schema["description"] = c.description
    schema.update({
        "type": "object",
        "properties": {
            "header": header,
            c.records_key: {"type": "array", "items": {"type": "object", "properties": rec_props, "required": rec_req}},
        },
        "required": ["header", c.records_key],
    })
    return schema


def ejemplo_doc(prefix: str) -> Dict[str, Any]:
    """Documento de 1 registro (el primer registro base) usado como ejemplo."""
    return C.generar(prefix, 1, "ciclo")


def bloques(c: Contract, lang: str) -> Dict[str, str]:
    es = lang == "es"
    ej = ejemplo_doc(c.prefix)
    ej_mini = formats.mini_ser(ej, c)
    ej_json = formats.json_compact(ej, c)
    sch = json.dumps(json_schema(c), ensure_ascii=False, separators=(",", ":"))
    if es:
        cab = f"FORMATO JSON — familia '{c.prefix}'\nDevuelve solo un objeto JSON válido (sin bloques de código ni comentarios) que cumpla este JSON Schema:\n"
        cab_ej = f"FORMATO JSON — familia '{c.prefix}'\nDevuelve solo un objeto JSON válido (sin bloques de código ni comentarios) con exactamente esta estructura. Ejemplo con 1 registro:\n"
        ej_lbl = "\nEjemplo válido:\n"
    else:
        cab = f"JSON FORMAT — family '{c.prefix}'\nReturn only a valid JSON object (no code fences, no comments) that validates against this JSON Schema:\n"
        cab_ej = f"JSON FORMAT — family '{c.prefix}'\nReturn only a valid JSON object (no code fences, no comments) with exactly this structure. Example with 1 record:\n"
        ej_lbl = "\nValid example:\n"
    return {
        "mini_spec": spec_block(c, lang),
        "mini_spec_ejemplo": spec_block(c, lang, example=ej_mini),
        "json_schema": cab + sch,
        "json_schema_ejemplo": cab + sch + ej_lbl + ej_json,
        "json_ejemplo": cab_ej + ej_json,
    }


# Pares (instrucción .mini, instrucción JSON) para el punto de equilibrio
PARES = [
    ("mini_spec", "json_schema"),                  # especificación vs especificación (principal)
    ("mini_spec_ejemplo", "json_schema_ejemplo"),  # ambas con ejemplo
    ("mini_spec", "json_ejemplo"),                 # caso adverso: JSON solo con ejemplo
    ("mini_spec_ejemplo", "json_ejemplo"),         # caso más adverso
]
