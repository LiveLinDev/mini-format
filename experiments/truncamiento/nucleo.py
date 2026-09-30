"""Núcleo de V3a: cortes por tokens, lectura con cada lector y métricas por (documento, lector, corte).

Definiciones exactas en ``PROTOCOLO.md`` §6. Un denominador cero es ``None`` (nunca 0 ni 1).
"""
from __future__ import annotations

from bisect import bisect_right
from collections import Counter
from typing import Any, Callable, Dict, List, NamedTuple, Optional, Sequence, Tuple

from . import corte as K
from . import lectores as R
from .documentos import Documento, canon

KS = tuple(range(1, 21))


class Condicion(NamedTuple):
    nombre: str
    formato: str            # texto propio que lee: 'json' | 'jsonl' | 'mini'
    etiqueta: str
    propia: bool            # implementación propia de este estudio
    primaria: bool          # condición de la meta documental
    variante: bool          # análisis de sensibilidad declarado, no una de las cinco condiciones del diseño


CONDICIONES: Tuple[Condicion, ...] = (
    Condicion("json_estricto", "json", "JSON compacto estricto (json.loads)", False, False, False),
    Condicion("json_parcial_jiter", "json", "JSON parcial (jiter, modo on)", False, False, False),
    Condicion("jsonl", "jsonl", "JSON Lines", False, False, False),
    Condicion("mini_tolerante", "mini", ".mini tolerante (minifmt)", False, True, False),
    Condicion("json_objetos_completos", "json", "JSON, objetos completos (implementación propia)", True, False, False),
    Condicion("mini_tolerante_sin_cola", "mini", ".mini tolerante, sin última línea sin LF", False, False, True),
)


def leer(cond: Condicion, prefijo: str, doc: Documento, truncado: bool) -> R.Lectura:
    n = cond.nombre
    if n == "json_estricto":
        return R.leer_json_estricto(prefijo, doc.clave)
    if n == "json_parcial_jiter":
        return R.leer_json_parcial_jiter(prefijo, doc.clave, "on")
    if n == "jsonl":
        return R.leer_jsonl(prefijo, doc.con_envoltura_jsonl)
    if n == "mini_tolerante":
        return R.leer_mini_tolerante(prefijo, doc.contrato, truncado, sin_cola=False)
    if n == "mini_tolerante_sin_cola":
        return R.leer_mini_tolerante(prefijo, doc.contrato, truncado, sin_cola=True)
    if n == "json_objetos_completos":
        return R.leer_json_objetos_completos(prefijo, doc.clave)
    raise KeyError(n)


def referencia(cond: Condicion, doc: Documento) -> List[Any]:
    return doc.referencia_mini if cond.formato == "mini" else doc.registros


# ------------------------------------------------------------------ métricas
def disponibles(fines: Sequence[int], n_bytes: int) -> int:
    """Registros cuyo contenido termina dentro del prefijo (``fines`` ordenado)."""
    return bisect_right(fines, n_bytes)


def clasificar(emitidos: Sequence[Any], ref: Sequence[Any], disp: int, solicitados: int) -> Dict[str, Any]:
    """Cuenta por multiconjunto lo que emitió un lector frente a la referencia (PROTOCOLO §6)."""
    cr = Counter(canon(r) for r in ref)
    ce = Counter(canon(e) for e in emitidos)
    identicos = sum(min(v, cr[c]) for c, v in ce.items())
    duplicados = sum(max(0, v - cr[c]) for c, v in ce.items() if c in cr)
    espurios = sum(v for c, v in ce.items() if c not in cr)
    n_emit = len(emitidos)
    if n_emit != identicos + duplicados + espurios:
        raise AssertionError("la clasificación no suma los registros emitidos")
    recuperados = min(identicos, disp)
    return {
        "disponibles": disp,
        "emitidos": n_emit,
        "identicos": identicos,
        "recuperados": recuperados,
        "completados_heuristicamente": identicos - recuperados,
        "duplicados": duplicados,
        "espurios": espurios,
        "recall_disponibles": (recuperados / disp) if disp > 0 else None,
        "recall_solicitados": recuperados / solicitados,
        "precision": (recuperados / n_emit) if n_emit > 0 else None,
    }


# ------------------------------------------------------------------ evaluación de un documento
def evaluar_documento(doc: Documento, enc: Any, ks: Sequence[int] = KS,
                      condiciones: Sequence[Condicion] = CONDICIONES) -> Tuple[List[Dict[str, Any]], Dict[str, Any], List[Dict[str, str]]]:
    """Devuelve ``(filas, info, exclusiones)``: una fila por (lector, k)."""
    segs = {f: K.segmentar(enc, t.texto) for f, t in doc.textos.items()}
    t_ref = segs["json"].n_tokens
    info = {"documento": doc.id, "tokens_ref_json": t_ref,
            "tokens_por_formato": {f: s.n_tokens for f, s in segs.items()},
            "bytes_por_formato": {f: len(s.datos) for f, s in segs.items()}}
    filas: List[Dict[str, Any]] = []
    exclusiones: List[Dict[str, str]] = []
    for cond in condiciones:
        causa = doc.exclusiones.get(cond.formato)
        if causa:
            exclusiones.append({"documento": doc.id, "condicion": cond.nombre, "causa": causa})
            continue
        ref = referencia(cond, doc)
        seg, fines = segs[cond.formato], doc.textos[cond.formato].fines
        for k in ks:
            lim = K.limite_k(k, t_ref)
            pre = K.prefijo_por_tokens(seg, lim)
            lec = leer(cond, pre.texto, doc, pre.truncado)
            disp = disponibles(fines, pre.n_bytes)
            m = clasificar(lec.registros, ref, disp, doc.n)
            filas.append({
                "documento": doc.id, "tipo": doc.tipo, "sintetico": doc.sintetico,
                "condicion": cond.nombre, "formato_texto": cond.formato, "k": k,
                "limite_tokens": lim, "tokens_ref_json": t_ref, "tokens_texto": seg.n_tokens,
                "truncado": pre.truncado, "bytes_prefijo": pre.n_bytes, "bytes_descartados": pre.bytes_descartados,
                "solicitados": doc.n, **m,
                "nota_lector": lec.nota, "fallo_lector": lec.fallo,
            })
    return filas, info, exclusiones
