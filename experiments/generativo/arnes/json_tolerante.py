"""Reparación selectiva para JSON: el equivalente de ``minifmt.ai.repair`` para los brazos A+1, B+1 y C+1.

El Plan de Validación exige comparaciones equivalentes: si solo el brazo .mini
pudiera reparar, la ventaja del formato se confundiría con la de la estrategia
de reparación.  Este módulo da a JSON la MISMA oportunidad:

1. ``dividir_registros`` localiza la lista de registros dentro de la respuesta
   con un escáner tolerante (respeta cadenas y llaves, acepta una comilla
   suelta dentro de un texto y un salto de línea crudo) y entrega cada objeto
   por separado, de modo que un registro roto no invalida a los demás (un
   ``json.loads`` del documento entero sí lo haría: ese es el lector estricto
   de los brazos A/B/C sin reparación).
2. ``solicitud_reparacion_json`` arma una solicitud con SOLO los objetos
   rechazados (sintaxis, contrato o identidad repetida) y el motivo de cada uno;
   no reenvía los válidos.
3. ``fusionar_json`` incorpora las correcciones sin sobrescribir ningún objeto
   válido y rechaza una corrección que duplique o invente una identidad (campo
   ``unique``): una identidad duplicada nunca llega al documento final.

La respuesta esperada es ``{"<clave>": [objeto, ...]}`` con exactamente tantos
objetos como se pidieron, en el mismo orden (``null`` para descartar un
elemento que no era un registro).
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from minifmt import Contract
from minifmt.serializer import encode_header, encode_record
from minifmt.parser import parse

from .tareas import Tarea

_ESPACIO = " \t\r\n"


# --------------------------------------------------------------------------
# Escáner tolerante
# --------------------------------------------------------------------------
@dataclass
class ItemJSON:
    indice: int                       # posición (0-based) dentro de la lista
    texto: str                        # texto del elemento tal como vino
    objeto: Optional[Dict[str, Any]]  # objeto analizado (None si no se pudo)
    error: Optional[str] = None       # error de sintaxis o de forma
    incompleto: bool = False          # el texto terminó antes de cerrar el objeto (truncamiento)
    nulo: bool = False                # el elemento era el literal null


def _localizar_lista(s: str, clave: str) -> Optional[int]:
    m = re.search(r'"%s"\s*:\s*\[' % re.escape(clave), s)
    if m:
        return m.end()
    t = s.lstrip()
    if t.startswith("["):
        return len(s) - len(t) + 1
    return None


def _cerrar_cadena(s: str, i: int) -> int:
    """Índice de la comilla que cierra la cadena abierta en ``s[i]`` (-1 si no cierra).

    Una comilla solo cierra si la sigue ``,``, ``:``, ``}`` o ``]`` (con espacios
    opcionales); si no, se toma como carácter literal del texto.
    """
    j = i + 1
    n = len(s)
    while j < n:
        c = s[j]
        if c == "\\":
            j += 2
            continue
        if c == '"':
            k = j + 1
            while k < n and s[k] in _ESPACIO:
                k += 1
            if k >= n or s[k] in ",:}]":
                return j
        j += 1
    return -1


def dividir_registros(texto: str, clave: str) -> Tuple[Optional[List[ItemJSON]], List[str]]:
    """Separa los elementos de la lista ``clave`` de una respuesta JSON.

    Devuelve ``(items, notas)``; ``items`` es ``None`` si no se localiza la lista.
    """
    s = (texto or "").replace("﻿", "")
    notas: List[str] = []
    ini = _localizar_lista(s, clave)
    if ini is None:
        return None, ["no se localizó la lista de registros"]
    n = len(s)
    i = ini
    items: List[ItemJSON] = []
    while i < n:
        while i < n and (s[i] in _ESPACIO or s[i] == ","):
            i += 1
        if i >= n or s[i] == "]":
            break
        if s[i] == "{":
            depth, j, cerrado = 0, i, False
            while j < n:
                ch = s[j]
                if ch == '"':
                    e = _cerrar_cadena(s, j)
                    if e < 0:
                        j = n
                        break
                    j = e + 1
                    continue
                if ch == "{":
                    depth += 1
                elif ch == "}":
                    depth -= 1
                    if depth == 0:
                        j += 1
                        cerrado = True
                        break
                j += 1
            frag = s[i:j]
            obj, err = None, None
            try:
                v = json.loads(frag)
                if isinstance(v, dict):
                    obj = v
                else:  # pragma: no cover - un fragmento que empieza en { siempre es objeto
                    err = "el elemento no es un objeto"
            except ValueError as e:
                err = f"JSON inválido: {str(e)[:100]}"
            items.append(ItemJSON(len(items), frag, obj, err, incompleto=not cerrado))
            i = j
        elif s.startswith("null", i):
            items.append(ItemJSON(len(items), "null", None, None, nulo=True))
            i += 4
        else:
            j = i
            while j < n and s[j] not in ",]":
                j += 1
            items.append(ItemJSON(len(items), s[i:j].strip(), None, "el elemento no es un objeto"))
            i = j
    return items, notas


# --------------------------------------------------------------------------
# Diagnóstico de contrato
# --------------------------------------------------------------------------
def _nombre_tipo(v: Any) -> str:
    return type(v).__name__


def motivos_incumplimiento(rec: Dict[str, Any], c: Contract, cabecera: Dict[str, Any]) -> List[str]:
    """Motivos por los que un registro JSON no cumple el contrato (vacío si cumple)."""
    from .metricas import _tipo_ok  # import local: metricas importa brazos
    out: List[str] = []
    for f in c.fields:
        claves = [f.json_items, f.json_selected] if f.type == "mlist" else [f.name]
        for k in claves:
            if k not in rec and not f.optional:
                out.append(f"falta el campo '{k}'")
        if f.type == "mlist":
            items = rec.get(f.json_items)
            if items is None:
                if not f.optional:
                    out.append(f"'{f.json_items}' no puede ser null")
            elif not isinstance(items, list) or not all(_tipo_ok(x, f.item) for x in items):
                out.append(f"'{f.json_items}' debe ser una lista de {f.item}")
            continue
        v = rec.get(f.name)
        if v is None:
            if not f.optional and f.name in rec:
                out.append(f"'{f.name}' no puede ser null")
            continue
        if f.type == "list":
            if not isinstance(v, list) or not all(_tipo_ok(x, f.item) for x in v):
                out.append(f"'{f.name}' debe ser una lista de {f.item}")
        elif f.type == "tuple":
            if not isinstance(v, dict):
                out.append(f"'{f.name}' debe ser un objeto")
            else:
                for cmp in f.items:
                    x = v.get(cmp.name)
                    if x is None:
                        if not cmp.optional:
                            out.append(f"'{f.name}.{cmp.name}' es obligatorio")
                    elif not _tipo_ok(x, cmp.type):
                        out.append(f"'{f.name}.{cmp.name}' debe ser {cmp.type}")
        elif not _tipo_ok(v, f.type):
            out.append(f"'{f.name}' debe ser {f.type} (recibido {_nombre_tipo(v)})")
    if out:
        return out
    try:
        texto = encode_header(cabecera, c, 1) + "\n" + encode_record(rec, c)
        doc = parse(texto, c, strict=False)
    except Exception as e:  # noqa: BLE001
        return [f"no cumple el contrato: {str(e)[:120]}"]
    for e in doc.errors:
        fld = f" [{e.field}]" if getattr(e, "field", None) else ""
        out.append(f"{e.code}{fld}: {e.message}")
    if not out and len(doc.records) != 1:
        out.append("el registro no se acepta")
    return out


def campos_identidad(c: Contract) -> List[str]:
    return [f.name for f in c.fields if f.unique]


def identidad(rec: Dict[str, Any], campos: List[str]) -> Optional[Tuple[str, ...]]:
    if not campos:
        return None
    return tuple(str(rec.get(k)) for k in campos)


def identidad_de_texto(texto: str, campos: List[str]) -> Optional[Tuple[str, ...]]:
    """Identidad que declara un objeto roto, leída con una expresión regular (None si no se recupera)."""
    if not campos:
        return None
    vals: List[str] = []
    for k in campos:
        m = re.search(r'"%s"\s*:\s*("(?:[^"\\]|\\.)*"|-?\d+(?:\.\d+)?)' % re.escape(k), texto)
        if not m:
            return None
        try:
            vals.append(str(json.loads(m.group(1))))
        except ValueError:
            return None
    return tuple(vals)


# --------------------------------------------------------------------------
# Solicitud de reparación
# --------------------------------------------------------------------------
@dataclass
class ItemRechazado:
    item: ItemJSON
    motivos: List[str]
    identidad_repetida: bool = False


@dataclass
class SolicitudJSON:
    system: str
    user: str
    rechazados: List[ItemRechazado]
    items: List[ItemJSON]                  # todos los elementos localizados, en orden
    clave: str
    response_format: Optional[Dict[str, Any]] = None
    max_tokens_hint: int = 256
    notas: List[str] = field(default_factory=list)

    @property
    def needed(self) -> bool:
        return bool(self.rechazados)

    @property
    def lines(self) -> List[int]:          # posiciones 1-based, como en la reparación .mini
        return [r.item.indice + 1 for r in self.rechazados]


def clasificar_items(items: List[ItemJSON], t: Tarea) -> List[ItemRechazado]:
    c = t.contrato
    campos = campos_identidad(c)
    vistos: Dict[Tuple[str, ...], int] = {}
    rech: List[ItemRechazado] = []
    for it in items:
        if it.nulo:
            rech.append(ItemRechazado(it, ["el elemento es null"]))
            continue
        if it.objeto is None:
            rech.append(ItemRechazado(it, [it.error or "no es un objeto"] + (["el objeto quedó incompleto (truncado)"] if it.incompleto else [])))
            continue
        mot = motivos_incumplimiento(it.objeto, c, t.cabecera)
        ident = identidad(it.objeto, campos)
        repetida = False
        if not mot and ident is not None:
            if ident in vistos:
                mot.append(f"identidad repetida: ya existe el objeto {vistos[ident] + 1} con {'/'.join(campos)} = {'/'.join(ident)}")
                repetida = True
            else:
                vistos[ident] = it.indice
        if mot:
            rech.append(ItemRechazado(it, mot, repetida))
    return rech


def solicitud_reparacion_json(respuesta: str, t: Tarea, sistema_base: str, *, contexto: Optional[str] = None,
                              response_format: Optional[Dict[str, Any]] = None,
                              items: Optional[List[ItemJSON]] = None) -> SolicitudJSON:
    """Solicitud con solo los objetos rechazados de ``respuesta`` y el diagnóstico de cada uno.

    ``items`` permite encadenar rondas: son los elementos resultantes de la fusión anterior.
    """
    c = t.contrato
    notas: List[str] = []
    if items is None:
        items, notas = dividir_registros(respuesta, c.records_key)
    if items is None:
        return SolicitudJSON(system="", user="", rechazados=[], items=[], clave=c.records_key, notas=notas)
    rech = clasificar_items(items, t)
    k = len(rech)
    sistema = ("Eres un corrector de documentos JSON. Corriges únicamente los objetos que se te indican, "
               "conservando su contenido y respetando el formato.\n\n" + sistema_base)
    L = [f"Un documento JSON con la clave \"{c.records_key}\" tiene {k} objeto(s) inválido(s). Corrige SOLO esos objetos.",
         "Objetos inválidos (posición en la lista, contenido y problemas):"]
    for r in rech:
        L.append(f"[O{r.item.indice + 1}] {r.item.texto}")
        for m in r.motivos:
            L.append(f"    - {m}")
    if contexto:
        L += ["", "Texto de origen (para recuperar valores):", contexto]
    L += ["", f"Responde solo con un documento JSON {{\"{c.records_key}\": [...]}} con exactamente {k} objeto(s), uno por cada "
              "objeto inválido y en el mismo orden. Si un elemento no era un registro, escribe null en su lugar. "
              "No repitas los objetos válidos ni añadas explicaciones ni bloques de código."]
    chars = sum(len(r.item.texto) for r in rech)
    hint = max(64, int(chars / 2.5) + 16 * (k + 1))
    return SolicitudJSON(system=sistema, user="\n".join(L), rechazados=rech, items=items, clave=c.records_key,
                         response_format=response_format, max_tokens_hint=hint, notas=notas)


# --------------------------------------------------------------------------
# Fusión
# --------------------------------------------------------------------------
@dataclass
class FusionJSON:
    texto: str                                   # documento JSON final (solo registros válidos)
    registros: List[Dict[str, Any]]
    items: List[ItemJSON] = field(default_factory=list)   # elementos resultantes (para encadenar otra ronda)
    reemplazados: List[int] = field(default_factory=list)      # posiciones 1-based corregidas con éxito
    descartados: List[int] = field(default_factory=list)
    sin_resolver: List[int] = field(default_factory=list)
    notas: List[str] = field(default_factory=list)
    rechazos_identidad_duplicada: int = 0
    rechazos_identidad_inventada: int = 0

    @property
    def ok(self) -> bool:
        return not self.sin_resolver


def fusionar_json(respuesta_original: str, respuesta_reparacion: str, solicitud: SolicitudJSON, t: Tarea) -> FusionJSON:
    """Incorpora las correcciones a la respuesta original.

    * Los objetos válidos pasan intactos y en su posición (nunca se sobrescriben).
    * Una corrección solo se acepta si cumple el contrato por sí sola y no
      repite la identidad de otro registro del documento final.
    * Si el objeto roto declaraba una identidad recuperable (y no era una
      identidad repetida), la corrección debe conservarla: cambiarla sería
      inventar un registro.
    """
    c = t.contrato
    campos = campos_identidad(c)
    notas: List[str] = []
    resp_items, nt = dividir_registros(respuesta_reparacion, c.records_key)
    notas += nt
    if resp_items is None:
        resp_items = []
    if len(resp_items) != len(solicitud.rechazados):
        notas.append(f"se esperaban {len(solicitud.rechazados)} objetos corregidos y llegaron {len(resp_items)}")
    rech_por_indice = {r.item.indice: r for r in solicitud.rechazados}
    corr: Dict[int, Optional[ItemJSON]] = {}
    for r, ri in zip(solicitud.rechazados, resp_items):
        corr[r.item.indice] = ri
    # identidades ya ocupadas por objetos válidos (se reservan antes de aceptar correcciones)
    ocupadas: Dict[Tuple[str, ...], int] = {}
    for it in solicitud.items:
        if it.indice in rech_por_indice or it.objeto is None:
            continue
        ident = identidad(it.objeto, campos)
        if ident is not None:
            ocupadas[ident] = it.indice
    finales: List[Dict[str, Any]] = []
    items_out: List[ItemJSON] = []
    reemplazados: List[int] = []
    descartados: List[int] = []
    sin_resolver: List[int] = []
    dup = inv = 0
    for it in solicitud.items:
        r = rech_por_indice.get(it.indice)
        if r is None:
            finales.append(it.objeto)  # válido: intacto
            items_out.append(it)
            continue
        pos = it.indice + 1
        ri = corr.get(it.indice)
        if ri is None:
            sin_resolver.append(pos)
            items_out.append(it)
            continue
        if ri.nulo:
            descartados.append(pos)
            continue
        if ri.objeto is None:
            notas.append(f"objeto {pos}: la corrección no es JSON válido ({ri.error})")
            sin_resolver.append(pos)
            items_out.append(it)
            continue
        mot = motivos_incumplimiento(ri.objeto, c, t.cabecera)
        if mot:
            notas.append(f"objeto {pos}: la corrección sigue inválida ({mot[0]})")
            sin_resolver.append(pos)
            items_out.append(it)
            continue
        ident = identidad(ri.objeto, campos)
        if ident is not None:
            if ident in ocupadas and ocupadas[ident] != it.indice:
                notas.append(f"objeto {pos}: la corrección repite la identidad {'/'.join(ident)} del objeto {ocupadas[ident] + 1}")
                dup += 1
                sin_resolver.append(pos)
                items_out.append(it)
                continue
            original = None if r.identidad_repetida else identidad_de_texto(it.texto, campos)
            if original is not None and original != ident:
                notas.append(f"objeto {pos}: la corrección cambia la identidad {'/'.join(original)} por {'/'.join(ident)}")
                inv += 1
                sin_resolver.append(pos)
                items_out.append(it)
                continue
            ocupadas[ident] = it.indice
        finales.append(ri.objeto)
        items_out.append(ItemJSON(it.indice, json.dumps(ri.objeto, ensure_ascii=False), ri.objeto))
        reemplazados.append(pos)
    texto = json.dumps({c.records_key: finales}, ensure_ascii=False)
    return FusionJSON(texto=texto, registros=finales, items=items_out, reemplazados=reemplazados, descartados=descartados,
                      sin_resolver=sorted(sin_resolver), notas=notas, rechazos_identidad_duplicada=dup,
                      rechazos_identidad_inventada=inv)
