"""Reparación selectiva de UNA respuesta, común a .mini y JSON (lo usan el ejecutor y la importación).

``solicitar`` construye la solicitud con solo lo rechazado; ``fusionar`` incorpora la respuesta de reparación sin
sobrescribir lo válido; ``auditar`` comprueba, sobre el texto, que no se sobrescribió un registro válido ni se
duplicó o inventó una identidad (ver ``auditoria.py``).  Ninguna función llama a un proveedor.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from minifmt.ai import merge_repair, repair_request

from . import auditoria as AU
from . import brazos as B
from . import json_tolerante as J
from .tareas import Tarea


@dataclass
class Solicitud:
    formato: str                      # mini | json
    needed: bool
    system: str
    user: str
    max_tokens_hint: int
    lineas: List[int]
    textos: List[str]
    raw: Any                          # RepairRequest o SolicitudJSON
    response_format: Optional[Dict[str, Any]] = None
    document: str = ""                # .mini: documento extraído al que se refieren los números de línea
    indices: List[int] = field(default_factory=list)   # JSON: posiciones 0-based de los objetos rechazados


def solicitar(formato: str, texto: str, t: Tarea, prompt_base: B.Prompt, idioma: str, contexto: Optional[str],
              brazo_base: str, items_json: Optional[List[J.ItemJSON]] = None) -> Solicitud:
    c = t.contrato
    if formato == "mini":
        req = repair_request(texto, c, idioma, context=contexto)
        return Solicitud("mini", req.needed, req.system, req.user, req.max_tokens_hint, list(req.lines),
                         [it.text for it in req.items], req, document=req.document)
    rf = prompt_base.response_format if brazo_base == "C" else None
    req = J.solicitud_reparacion_json(texto, t, prompt_base.system, contexto=contexto, response_format=rf, items=items_json)
    return Solicitud("json", req.needed, req.system, req.user, req.max_tokens_hint, req.lines,
                     [r.item.texto for r in req.rechazados], req, response_format=req.response_format,
                     indices=[r.item.indice for r in req.rechazados])


@dataclass
class Resultado:
    texto: str
    progreso: bool
    ok: bool
    ronda: Dict[str, Any]
    items_json: Optional[List[J.ItemJSON]] = None
    sin_resolver_json: List[int] = field(default_factory=list)
    rechazos_identidad: int = 0


def fusionar(sol: Solicitud, texto: str, respuesta: Dict[str, Any], t: Tarea, resp_serializable: Dict[str, Any],
             max_tokens: int) -> Resultado:
    c = t.contrato
    base = {"prompt": {"system": sol.system, "user": sol.user}, "max_tokens": max_tokens,
            "respuesta": resp_serializable, "lineas_solicitadas": sol.lineas}
    if sol.formato == "mini":
        merged = merge_repair(texto, respuesta["text"], c, sol.raw)
        ronda = dict(base, reemplazadas=merged.replaced, eliminadas=merged.dropped, sin_resolver=merged.unresolved,
                     notas=merged.notes)
        return Resultado(merged.text, bool(merged.replaced or merged.dropped), merged.ok, ronda)
    fus = J.fusionar_json(texto, respuesta["text"], sol.raw, t)
    ronda = dict(base, reemplazadas=fus.reemplazados, eliminadas=fus.descartados, sin_resolver=fus.sin_resolver,
                 notas=fus.notas, rechazos_identidad_duplicada=fus.rechazos_identidad_duplicada,
                 rechazos_identidad_inventada=fus.rechazos_identidad_inventada)
    return Resultado(fus.texto, bool(fus.reemplazados or fus.descartados), fus.ok, ronda, items_json=fus.items,
                     sin_resolver_json=list(fus.sin_resolver),
                     rechazos_identidad=fus.rechazos_identidad_duplicada + fus.rechazos_identidad_inventada)


def auditar(sol_inicial: Solicitud, texto_original: str, texto_final: str, t: Tarea,
            rechazos_identidad: int = 0, registros_finales: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
    c = t.contrato
    if sol_inicial.formato == "mini":
        return AU.auditar_mini(sol_inicial.document, texto_final, sol_inicial.lineas, sol_inicial.textos, c)
    items0 = J.dividir_registros(texto_original, c.records_key)[0] or []
    return AU.auditar_json(items0, sol_inicial.indices, registros_finales or [], c, rechazos_identidad)


def estado_reparacion(rondas: List[Dict[str, Any]], error: bool) -> str:
    if error:
        return "error_tecnico"
    if not rondas:
        return "no_necesaria"
    ult = rondas[-1]
    if not ult["sin_resolver"]:
        return "completa"
    return "parcial" if (ult["reemplazadas"] or ult["eliminadas"]) else "sin_cambios"
