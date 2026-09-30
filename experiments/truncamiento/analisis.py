"""Agregación de V3a: razones por conglomerados (documento), IC bootstrap y criterio (PROTOCOLO §7-§8).

Los 20 cortes de un documento son observaciones relacionadas: el conglomerado es el documento. El bootstrap
remuestrea documentos con reemplazo. Todo denominador cero es ``None`` y se excluye del agregado que lo
necesita, con su conteo.
"""
from __future__ import annotations

import zlib
from collections import defaultdict
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence, Tuple

import numpy as np

SEMILLA_BOOTSTRAP = 20260930
B_REPLICAS = 10_000
UMBRAL = 0.90

ESTRATOS: Dict[str, Callable[[Dict[str, Any]], bool]] = {
    "todos": lambda f: True,
    "dominios_sinteticos": lambda f: f["tipo"] == "dominio_sintetico",
    "snapshots": lambda f: f["tipo"].startswith("snapshot"),
}


def _rng(etiqueta: str) -> np.random.Generator:
    return np.random.default_rng([SEMILLA_BOOTSTRAP, zlib.crc32(etiqueta.encode("utf-8"))])


def _redondeo(x: Optional[float], d: int = 6) -> Optional[float]:
    return None if x is None else round(float(x), d)


def razon_conglomerados(num: Sequence[float], den: Sequence[float], etiqueta: str, B: int = B_REPLICAS) -> Dict[str, Any]:
    """Σnum/Σden con IC 95 % por bootstrap de conglomerados (un elemento de ``num``/``den`` por documento)."""
    num_a, den_a = np.asarray(num, dtype=float), np.asarray(den, dtype=float)
    nd = len(num_a)
    if nd == 0 or den_a.sum() <= 0:
        return {"punto": None, "ic95_inf": None, "ic95_sup": None, "n_documentos": nd, "replicas_descartadas": 0}
    punto = num_a.sum() / den_a.sum()
    if nd < 2:
        return {"punto": _redondeo(punto), "ic95_inf": None, "ic95_sup": None, "n_documentos": nd, "replicas_descartadas": 0}
    idx = _rng(etiqueta).integers(0, nd, size=(B, nd))
    n_b, d_b = num_a[idx].sum(axis=1), den_a[idx].sum(axis=1)
    ok = d_b > 0
    r = n_b[ok] / d_b[ok]
    return {"punto": _redondeo(punto), "ic95_inf": _redondeo(np.quantile(r, 0.025)),
            "ic95_sup": _redondeo(np.quantile(r, 0.975)), "n_documentos": nd,
            "replicas_descartadas": int((~ok).sum())}


def media_conglomerados(valores: Sequence[float], etiqueta: str, B: int = B_REPLICAS) -> Dict[str, Any]:
    """Media de un valor por documento con IC 95 % por bootstrap de documentos."""
    v = np.asarray(valores, dtype=float)
    nd = len(v)
    if nd == 0:
        return {"media": None, "ic95_inf": None, "ic95_sup": None, "n_documentos": 0}
    if nd < 2:
        return {"media": _redondeo(v.mean()), "ic95_inf": None, "ic95_sup": None, "n_documentos": nd}
    idx = _rng(etiqueta).integers(0, nd, size=(B, nd))
    m = v[idx].mean(axis=1)
    return {"media": _redondeo(v.mean()), "ic95_inf": _redondeo(np.quantile(m, 0.025)),
            "ic95_sup": _redondeo(np.quantile(m, 0.975)), "n_documentos": nd}


def _por_documento(filas: Iterable[Dict[str, Any]], num: str, den: str) -> Tuple[List[str], List[float], List[float]]:
    a: Dict[str, List[float]] = defaultdict(lambda: [0.0, 0.0])
    for f in filas:
        a[f["documento"]][0] += f[num]
        a[f["documento"]][1] += f[den]
    docs = sorted(a)
    return docs, [a[d][0] for d in docs], [a[d][1] for d in docs]


def _min_por_documento(filas: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    docs, num, den = _por_documento(filas, "recuperados", "disponibles")
    vals = [(n / d, doc) for doc, n, d in zip(docs, num, den) if d > 0]
    if not vals:
        return {"minimo": None, "documento": None}
    v, doc = min(vals)
    return {"minimo": _redondeo(v), "documento": doc}


def resumen_condicion(filas: Sequence[Dict[str, Any]], etiqueta: str) -> Dict[str, Any]:
    """Todas las cifras de una condición sobre un conjunto de filas (los cortes de sus documentos)."""
    if not filas:
        return {"n_cortes": 0}
    docs, nr, nd = _por_documento(filas, "recuperados", "disponibles")
    trunc = [f for f in filas if f["truncado"]]
    dt, nrt, ndt = _por_documento(trunc, "recuperados", "disponibles")
    de, ne, nm = _por_documento([f for f in filas if f["emitidos"] > 0], "recuperados", "emitidos")
    emitidos = sum(f["emitidos"] for f in filas)
    cortes_espurios = sum(1 for f in filas if f["espurios"] > 0)
    disp_solic = [sum(f["disponibles"] for f in filas if f["documento"] == d) / sum(f["solicitados"] for f in filas if f["documento"] == d) for d in docs]
    rec_solic = [sum(f["recuperados"] for f in filas if f["documento"] == d) / sum(f["solicitados"] for f in filas if f["documento"] == d) for d in docs]
    return {
        "n_documentos": len(docs),
        "n_cortes": len(filas),
        "n_cortes_disponibles_cero": sum(1 for f in filas if f["disponibles"] == 0),
        "n_cortes_truncados": len(trunc),
        "recall_disponibles": razon_conglomerados(nr, nd, etiqueta + "|recall"),
        "recall_disponibles_solo_truncados": {**razon_conglomerados(nrt, ndt, etiqueta + "|recall_trunc"),
                                              "n_cortes": len(trunc),
                                              "n_cortes_disponibles_cero": sum(1 for f in trunc if f["disponibles"] == 0)},
        "minimo_por_documento": _min_por_documento(filas),
        "recuperados_sobre_solicitados": media_conglomerados(rec_solic, etiqueta + "|rec_solic"),
        "disponibles_sobre_solicitados": media_conglomerados(disp_solic, etiqueta + "|disp_solic"),
        "precision": {**razon_conglomerados(ne, nm, etiqueta + "|precision"),
                      "n_cortes_sin_emitidos_null": sum(1 for f in filas if f["emitidos"] == 0)},
        "registros_emitidos": emitidos,
        "registros_recuperados": sum(f["recuperados"] for f in filas),
        "registros_disponibles": sum(f["disponibles"] for f in filas),
        "espurios": sum(f["espurios"] for f in filas),
        "duplicados": sum(f["duplicados"] for f in filas),
        "completados_heuristicamente": sum(f["completados_heuristicamente"] for f in filas),
        "cortes_con_espurios": cortes_espurios,
        "fraccion_cortes_con_espurios": _redondeo(cortes_espurios / len(filas)),
        "fallos_lector": sum(1 for f in filas if f["fallo_lector"]),
    }


def resumen_lectores(filas: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Una entrada por (condición, estrato)."""
    out: List[Dict[str, Any]] = []
    for cond in sorted({f["condicion"] for f in filas}, key=lambda c: next(i for i, f in enumerate(filas) if f["condicion"] == c)):
        fc = [f for f in filas if f["condicion"] == cond]
        for est, pred in ESTRATOS.items():
            sel = [f for f in fc if pred(f)]
            if sel:
                out.append({"condicion": cond, "estrato": est, **resumen_condicion(sel, f"{cond}|{est}")})
    return out


def curvas(filas: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Por (condición, k) sobre todos los documentos: recuperados/solicitados, disponibles/solicitados y recall."""
    out: List[Dict[str, Any]] = []
    conds = sorted({f["condicion"] for f in filas}, key=lambda c: next(i for i, f in enumerate(filas) if f["condicion"] == c))
    for cond in conds:
        for k in sorted({f["k"] for f in filas}):
            sel = [f for f in filas if f["condicion"] == cond and f["k"] == k]
            if not sel:
                continue
            et = f"curva|{cond}|{k}"
            rs = media_conglomerados([f["recuperados"] / f["solicitados"] for f in sel], et + "|rs")
            ds = media_conglomerados([f["disponibles"] / f["solicitados"] for f in sel], et + "|ds")
            docs, nr, nd = _por_documento(sel, "recuperados", "disponibles")
            rec = razon_conglomerados(nr, nd, et + "|rec")
            de, ne, nm = _por_documento([f for f in sel if f["emitidos"] > 0], "recuperados", "emitidos")
            pre = razon_conglomerados(ne, nm, et + "|pre")
            out.append({
                "condicion": cond, "k": k, "fraccion_limite": k / 20, "n_documentos": len(sel),
                "limite_tokens_mediano": float(np.median([f["limite_tokens"] for f in sel])),
                "truncados": sum(1 for f in sel if f["truncado"]),
                "recuperados_sobre_solicitados": rs["media"], "rs_ic95_inf": rs["ic95_inf"], "rs_ic95_sup": rs["ic95_sup"],
                "disponibles_sobre_solicitados": ds["media"], "ds_ic95_inf": ds["ic95_inf"], "ds_ic95_sup": ds["ic95_sup"],
                "recall_disponibles": rec["punto"], "rec_ic95_inf": rec["ic95_inf"], "rec_ic95_sup": rec["ic95_sup"],
                "documentos_disponibles_cero": sum(1 for f in sel if f["disponibles"] == 0),
                "precision": pre["punto"], "espurios": sum(f["espurios"] for f in sel),
            })
    return out


def por_documento(filas: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    claves = sorted({(f["documento"], f["condicion"]) for f in filas})
    orden = {c: i for i, c in enumerate(dict.fromkeys(f["condicion"] for f in filas))}
    claves.sort(key=lambda x: (x[0], orden[x[1]]))
    for doc, cond in claves:
        sel = [f for f in filas if f["documento"] == doc and f["condicion"] == cond]
        disp, rec, emi = (sum(f[c] for f in sel) for c in ("disponibles", "recuperados", "emitidos"))
        out.append({
            "documento": doc, "tipo": sel[0]["tipo"], "condicion": cond, "n_cortes": len(sel),
            "tokens_ref_json": sel[0]["tokens_ref_json"], "tokens_texto": sel[0]["tokens_texto"],
            "cortes_truncados": sum(1 for f in sel if f["truncado"]),
            "disponibles": disp, "recuperados": rec,
            "recall_disponibles": _redondeo(rec / disp) if disp else None,
            "recuperados_sobre_solicitados_media": _redondeo(sum(f["recuperados"] / f["solicitados"] for f in sel) / len(sel)),
            "emitidos": emi, "precision": _redondeo(rec / emi) if emi else None,
            "espurios": sum(f["espurios"] for f in sel), "duplicados": sum(f["duplicados"] for f in sel),
            "completados_heuristicamente": sum(f["completados_heuristicamente"] for f in sel),
            "cortes_disponibles_cero": sum(1 for f in sel if f["disponibles"] == 0),
        })
    return out


def criterio_primario(filas: Sequence[Dict[str, Any]], condicion: str = "mini_tolerante") -> Dict[str, Any]:
    """Meta documental (PROTOCOLO §8): Σrecuperados/Σdisponibles de la condición primaria, sobre todos los
    cortes con disponibles>0 de los 18 documentos. La decisión usa el punto."""
    fc = [f for f in filas if f["condicion"] == condicion]
    docs, nr, nd = _por_documento(fc, "recuperados", "disponibles")
    r = razon_conglomerados(nr, nd, f"{condicion}|todos|recall")
    trunc = [f for f in fc if f["truncado"]]
    dt, nrt, ndt = _por_documento(trunc, "recuperados", "disponibles")
    rt = razon_conglomerados(nrt, ndt, f"{condicion}|todos|recall_trunc")
    if r["punto"] is None:
        veredicto = "no_evaluable"
    else:
        veredicto = "cumple" if r["punto"] >= UMBRAL else "no_cumple"
    return {
        "condicion": condicion, "umbral": UMBRAL,
        "estadistico": "suma(recuperados)/suma(disponibles) sobre cortes con disponibles>0, k=1..20, todos los documentos",
        "punto": r["punto"], "ic95_inf": r["ic95_inf"], "ic95_sup": r["ic95_sup"],
        "extremo_inferior_supera_umbral": (r["ic95_inf"] >= UMBRAL) if r["ic95_inf"] is not None else None,
        "n_documentos": r["n_documentos"],
        "n_cortes_total": len(fc),
        "n_cortes_excluidos_disponibles_cero": sum(1 for f in fc if f["disponibles"] == 0),
        "solo_truncados": {"punto": rt["punto"], "ic95_inf": rt["ic95_inf"], "ic95_sup": rt["ic95_sup"],
                           "n_cortes": len(trunc),
                           "n_cortes_excluidos_disponibles_cero": sum(1 for f in trunc if f["disponibles"] == 0)},
        "minimo_por_documento": _min_por_documento(fc),
        "veredicto_regla_fijada": veredicto,
        "aprobacion_asesor": "pendiente",
    }
