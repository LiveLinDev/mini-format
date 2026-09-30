"""Análisis de resultados del experimento generativo V2/V3b/V4.

    python experiments/generativo/analyze.py --resultados experiments/generativo/resultados/simulado/piloto

Produce en ``<resultados>/analisis/``:

* ``resumen_brazos.csv`` · ``resumen_brazo_modelo.csv`` · ``resumen_brazo_tarea.csv``
* ``comparaciones_pareadas.csv``   formato (A/B/C frente a D) y estrategia (X frente a X+1), con IC por conglomerados
* ``reparacion.csv``               X frente a X+1: registros ganados, cambios adversos, auditoría de identidades, costo
* ``desenlaces.csv``               ok / formato inválido / vacía / truncada / negativa / error técnico por brazo
* ``latencia_costo.csv``           V4: mediana y p95 del flujo completo, costo por solicitud y por 1 000 registros válidos
* ``solicitudes.jsonl``            la estructura ``solicitud`` (intentos por fase, usage por categorías) de cada muestra
* ``meta_v2.json``                 evaluación de la meta (criterio fijado aquí, antes de mirar los datos)
* ``v3a_truncamiento*.csv``        cortes sobre salidas guardadas (heredado; la V3a canónica vive en experiments/truncamiento)
* ``resumen.md`` y ``fig_*.png``

Reglas de lectura
-----------------
* Se separan SINTAXIS analizable, CUMPLIMIENTO DEL CONTRATO y EXACTITUD DEL CONTENIDO.  La validez final es
  ``registros válidos / registros SOLICITADOS``: un registro ausente cuenta como no válido.
* La incertidumbre es un bootstrap de CONGLOMERADOS: por solicitud (cada muestra con sus registros) y por
  documento (tarea).  Nunca se trata cada registro o cada campo como réplica independiente.
* Un denominador cero da ``None`` (celda vacía), nunca 0.
* Latencia: mediana y p95 (rango más cercano) con ``n``; no incluye las muestras de error técnico.
  En material simulado la latencia de API es sintética y está marcada.
* Costo: se recalcula con ``--tarifas`` a partir del usage por categorías de cada intento; sin tarifa verificada es
  «tarifa no verificada» (vacío).  El material ``asistido_ia`` no tiene usage ni factura: costo vacío.
* Todas las comparaciones entre brazos son EXPLORATORIAS (hay muchas y no se corrigen por comparaciones múltiples).
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import sys
from collections import Counter, defaultdict
from decimal import Decimal
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import arnes  # noqa: E402,F401
from arnes import brazos as B  # noqa: E402
from arnes import tareas as T  # noqa: E402
from arnes.archivos import escribir_texto  # noqa: E402
from arnes.ejecucion import leer_muestras  # noqa: E402
from arnes.estadistica import bootstrap_diferencia, bootstrap_razon, mediana, percentil, wilson  # noqa: E402
from arnes.tarifas import NO_VERIFICADA, Tarifas, costo_usage  # noqa: E402
from arnes.truncamiento import cortes_controlados  # noqa: E402

ORDEN_BRAZOS = list(B.ORDEN_BRAZOS)
NOMBRE_BRAZO = {"A": "A · JSON mínimo", "A+1": "A+1 · JSON mínimo + reparación", "B": "B · JSON con contrato",
                "B+1": "B+1 · JSON con contrato + reparación", "C": "C · JSON nativo", "C+1": "C+1 · JSON nativo + reparación",
                "D": "D · .mini", "D+1": "D+1 · .mini + reparación", "A0": "A0 · pipe a mano (control)"}
ALIAS_BRAZO = {"D+R": "D+1"}           # muestras del arnés anterior
DESENLACES = ("ok", "formato_invalido", "vacia", "truncada", "negativa", "error_tecnico")
COMPARACIONES = [("B", "D", "formato: JSON con contrato frente a .mini"), ("C", "D", "formato: JSON nativo frente a .mini"),
                 ("A", "D", "formato: JSON mínimo frente a .mini"), ("B+1", "D+1", "formato con reparación en ambos: JSON con contrato frente a .mini"),
                 ("C+1", "D+1", "formato con reparación en ambos: JSON nativo frente a .mini"),
                 ("A+1", "D+1", "formato con reparación en ambos: JSON mínimo frente a .mini"),
                 ("A", "B", "contrato en el prompt: A frente a B"), ("B", "C", "restricción nativa: B frente a C"),
                 ("A", "A+1", "estrategia: reparar JSON mínimo"), ("B", "B+1", "estrategia: reparar JSON con contrato"),
                 ("C", "C+1", "estrategia: reparar JSON nativo"), ("D", "D+1", "estrategia: reparar .mini")]
# CRITERIO de la meta V2 (Plan de Validación v3, T4.R3), FIJADO antes de analizar: validez final agregada por
# (brazo, modelo) >= 95 % en al menos 3 modelos de al menos 2 proveedores.  Solo es evaluable con material api_real.
CRITERIO_V2 = {"metrica": "validez final = registros válidos / registros solicitados (ausentes cuentan como no válidos)",
               "umbral": 0.95, "min_modelos": 3, "min_proveedores": 2,
               "interpretacion": "estimación puntual de la validez agregada por (brazo, modelo) >= umbral; se cumple si "
                                 "al menos min_modelos modelos de al menos min_proveedores proveedores la alcanzan; "
                                 "el IC por solicitud se informa pero no decide",
               "evaluable_solo_con": "api_real"}
# paleta categórica de referencia en orden fijo (azul, naranja, aqua, amarillo)
COLORES = {"correctos": "#2a78d6", "incorrectos_sin_aviso": "#eb6834", "perdidos_detectados": "#1baf7a",
           "perdidos_sin_aviso": "#eda100"}
ETIQUETAS = {"correctos": "Correctos", "incorrectos_sin_aviso": "Incorrectos aceptados sin aviso",
             "perdidos_detectados": "Perdidos con aviso", "perdidos_sin_aviso": "Perdidos sin aviso"}
TINTA, TINTA2, REJILLA = "#0b0b0b", "#52514e", "#e4e3df"


NL_ = chr(10)


def _orden_brazo(b: str) -> int:
    return ORDEN_BRAZOS.index(b) if b in ORDEN_BRAZOS else 99


def _f(x: Any, nd: int = 2) -> Optional[float]:
    if x is None:
        return None
    if isinstance(x, float) and math.isnan(x):
        return None
    return round(float(x), nd)


def _pct(x: Optional[float], nd: int = 2) -> Optional[float]:
    return None if x is None else round(100 * x, nd)


def procedencia_de(s: Dict[str, Any]) -> str:
    if s.get("procedencia"):
        return s["procedencia"]
    return "simulado" if s.get("simulado") else "api_real"


def normalizar(muestras: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Adapta muestras del arnés anterior (brazo D+R) sin reescribir el archivo."""
    out = []
    for s in muestras:
        if s.get("brazo") in ALIAS_BRAZO:
            s = dict(s, brazo=ALIAS_BRAZO[s["brazo"]])
        out.append(s)
    return out


def _m(s: Dict[str, Any], k: str, defecto: Any = None) -> Any:
    v = s["metricas"].get(k, defecto)
    return defecto if v is None else v


def costo_de(s: Dict[str, Any], tarifas: Optional[Tarifas]) -> Optional[Decimal]:
    """Costo de la muestra (todas sus fases) en USD o None («tarifa no verificada» / sin usage)."""
    if procedencia_de(s) == "asistido_ia":
        return None
    intentos = (s.get("solicitud") or {}).get("intentos")
    if tarifas is not None and intentos is not None:
        total = Decimal(0)
        for i in intentos:
            if i.get("estado") == "error":
                continue
            c = costo_usage(tarifas.obtener(i["proveedor"], i["modelo"]), i.get("usage"))
            if c is None:
                return None
            total += c
        return total
    v = s.get("costo_usd")
    return None if v is None else Decimal(str(v))


# --------------------------------------------------------------------------
# Agregación
# --------------------------------------------------------------------------
def _ic_razon(grupo: List[Dict[str, Any]], num, den, n_boot: int) -> Dict[str, Optional[float]]:
    por_sol = [(num(s), den(s)) for s in grupo]
    est, lo, hi = bootstrap_razon(por_sol, n_boot=n_boot)
    doc: Dict[str, List[float]] = defaultdict(lambda: [0.0, 0.0])
    for s, (a, b) in zip(grupo, por_sol):
        doc[s["tarea"]][0] += a
        doc[s["tarea"]][1] += b
    _, dlo, dhi = bootstrap_razon([tuple(v) for v in doc.values()], n_boot=n_boot)
    return {"pct": _pct(est), "sol_inf": _pct(lo), "sol_sup": _pct(hi), "doc_inf": _pct(dlo), "doc_sup": _pct(dhi)}


def agregar(grupo: List[Dict[str, Any]], *, tarifas: Optional[Tarifas] = None, n_boot: int = 1000,
            ic: bool = True) -> Dict[str, Any]:
    n = len(grupo)
    m = [s["metricas"] for s in grupo]
    solicitados = sum(_m(s, "solicitados", _m(s, "esperados", 0)) for s in grupo)
    aceptados = sum(x.get("aceptados", 0) for x in m)
    esperados = sum(x["esperados"] for x in m)
    espurios = sum(x.get("espurios", 0) for x in m)
    den_reg = esperados + espurios
    fila: Dict[str, Any] = {"muestras": n, "registros_solicitados": solicitados, "registros_aceptados": aceptados,
                            "espurios": espurios}
    # --- sintaxis / exactos por muestra (Wilson: la unidad es la solicitud)
    for k, v in (("sintaxis_ok", sum(1 for x in m if x.get("sintaxis_ok", x.get("parseable")))),
                 ("exacto", sum(1 for x in m if x.get("exacto"))),
                 ("con_aviso", sum(1 for x in m if x.get("detectado"))),
                 ("truncadas", sum(1 for x in m if x.get("truncado")))):
        p, lo, hi = wilson(v, n) if n else (float("nan"),) * 3
        fila.update({f"{k}_pct": _pct(_f(p, 6)), f"{k}_ic_inf": _pct(_f(lo, 6)), f"{k}_ic_sup": _pct(_f(hi, 6))})
    # --- validez final (sobre TODOS los solicitados), cumplimiento de contrato y exactitud
    vf = sum(_m(s, "validos_finales", _m(s, "correctos", 0)) for s in grupo)
    vc = sum(_m(s, "validos_contrato", 0) for s in grupo)
    fila["validos_finales"] = vf
    if ic:
        r = _ic_razon(grupo, lambda s: _m(s, "validos_finales", _m(s, "correctos", 0)),
                      lambda s: _m(s, "solicitados", _m(s, "esperados", 0)), n_boot)
    else:
        r = {"pct": _pct(vf / solicitados) if solicitados else None, "sol_inf": None, "sol_sup": None, "doc_inf": None, "doc_sup": None}
    fila.update({"validez_final_pct": r["pct"], "validez_final_ic_solicitud_inf": r["sol_inf"],
                 "validez_final_ic_solicitud_sup": r["sol_sup"], "validez_final_ic_documento_inf": r["doc_inf"],
                 "validez_final_ic_documento_sup": r["doc_sup"]})
    fila["cumplimiento_contrato_pct"] = _pct(vc / aceptados) if aceptados else None
    con_ref = [s for s in grupo if s["metricas"].get("exactos_contenido") is not None]
    if con_ref and ic:
        r = _ic_razon(con_ref, lambda s: s["metricas"]["exactos_contenido"], lambda s: _m(s, "solicitados", 0), n_boot)
        fila.update({"exactitud_contenido_pct": r["pct"], "exactitud_contenido_ic_solicitud_inf": r["sol_inf"],
                     "exactitud_contenido_ic_solicitud_sup": r["sol_sup"]})
    else:
        ex = sum(s["metricas"]["exactos_contenido"] for s in con_ref)
        den_ex = sum(_m(s, "solicitados", 0) for s in con_ref)
        fila.update({"exactitud_contenido_pct": _pct(ex / den_ex) if den_ex else None,
                     "exactitud_contenido_ic_solicitud_inf": None, "exactitud_contenido_ic_solicitud_sup": None})
    # --- desenlace por registro (esperados + espurios): puntuales; el IC de los incorrectos es por solicitud
    tot = {k: sum(x.get(k, 0) for x in m) for k in ("correctos", "incorrectos_sin_aviso", "perdidos_sin_aviso", "perdidos_detectados")}
    for k, v in tot.items():
        fila[k] = v
        fila[k + "_pct"] = _pct(min(v, den_reg) / den_reg) if den_reg else None
    if ic and den_reg:
        r = _ic_razon(grupo, lambda s: s["metricas"].get("incorrectos_sin_aviso", 0),
                      lambda s: s["metricas"]["esperados"] + s["metricas"].get("espurios", 0), n_boot)
        fila["incorrectos_sin_aviso_ic_inf"], fila["incorrectos_sin_aviso_ic_sup"] = r["sol_inf"], r["sol_sup"]
    else:
        fila["incorrectos_sin_aviso_ic_inf"] = fila["incorrectos_sin_aviso_ic_sup"] = None
    fila["identidades_duplicadas"] = sum(_m(s, "identidades_duplicadas", 0) for s in grupo)
    # --- desenlaces de la respuesta
    cnt = Counter(s.get("desenlace") or "ok" for s in grupo)
    for d in DESENLACES:
        fila[f"desenlace_{d}"] = cnt.get(d, 0)
    # --- tokens (los del adaptador o usage; vacíos si no hay)
    def media(clave: str) -> Optional[float]:
        v = [x[clave] for x in m if x.get(clave) is not None]
        return _f(sum(v) / len(v), 1) if v else None
    fila.update({"tokens_entrada_media": media("tokens_entrada"), "tokens_salida_media": media("tokens_salida"),
                 "llamadas_reparacion_total": sum(x.get("llamadas_reparacion", 0) for x in m)})
    lim = [s["max_tokens"] for s in grupo if s.get("experimento") == "v3b" and s.get("max_tokens")]
    fila["limite_salida_medio"] = _f(sum(lim) / len(lim), 1) if lim else None
    # --- latencia del flujo completo (sin errores técnicos)
    lat = [s["latencia"]["flujo_s"] for s in grupo if s.get("latencia") and s["latencia"].get("flujo_s") is not None
           and s.get("desenlace") != "error_tecnico"]
    origenes = {s["latencia"].get("origen_api") for s in grupo if s.get("latencia")}
    fila.update({"latencia_flujo_mediana_s": _f(mediana(lat), 3), "latencia_flujo_p95_s": _f(percentil(lat, 0.95), 3),
                 "latencia_n": len(lat),
                 "latencia_excluidas_error_tecnico": sum(1 for s in grupo if s.get("desenlace") == "error_tecnico"),
                 "latencia_origen": "/".join(sorted(x for x in origenes if x)) or None})
    # --- costo
    costos = [costo_de(s, tarifas) for s in grupo]
    intentos_tot = sum(len((s.get("solicitud") or {}).get("intentos") or []) for s in grupo)
    fallidos = sum(1 for s in grupo for i in ((s.get("solicitud") or {}).get("intentos") or []) if i.get("estado") == "error")
    fila.update({"intentos_totales": intentos_tot, "intentos_fallidos": fallidos})
    if n and all(c is not None for c in costos):
        total = sum(costos, Decimal(0))
        fila["costo_usd_total"] = _f(total, 6)
        fila["costo_solicitud_mediana_usd"] = _f(mediana([float(c) for c in costos]), 6)
        if vf > 0:
            fila["costo_por_1000_validos_usd"] = _f(total / Decimal(vf) * 1000, 4)
            fila["costo_nota"] = "nocional: usage simulado" if all(procedencia_de(s) == "simulado" for s in grupo) else ""
        else:
            fila["costo_por_1000_validos_usd"] = None
            fila["costo_nota"] = f"sin registros válidos: fallo; costo incurrido {total:.6f} USD"
    else:
        fila.update({"costo_usd_total": None, "costo_solicitud_mediana_usd": None, "costo_por_1000_validos_usd": None})
        todos_asistidos = bool(grupo) and all(procedencia_de(s) == "asistido_ia" for s in grupo)
        fila["costo_nota"] = "sin usage ni factura de API (asistido_ia)" if todos_asistidos else NO_VERIFICADA
    return fila


def agrupar(muestras: List[Dict[str, Any]], claves: Tuple[str, ...], **kw: Any) -> List[Dict[str, Any]]:
    g: Dict[tuple, List[Dict[str, Any]]] = defaultdict(list)
    for s in muestras:
        g[tuple(s[k] if k != "modelo_completo" else f"{s['proveedor']}:{s['modelo']}" for k in claves)].append(s)
    filas = []
    for k in sorted(g, key=lambda t: tuple(_orden_brazo(x) if c == "brazo" else x for c, x in zip(claves, t))):
        filas.append({**dict(zip(claves, k)), **agregar(g[k], **kw)})
    return filas


def escribir_csv(path: Path, filas: List[Dict[str, Any]]) -> None:
    if not filas:
        return
    campos = list(dict.fromkeys(k for f in filas for k in f))
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=campos, lineterminator="\n")
        w.writeheader()
        w.writerows({k: ("" if v is None else v) for k, v in f.items()} for f in filas)


def tabla_md(filas: List[Dict[str, Any]], columnas: List[Tuple[str, str]]) -> str:
    def cel(v: Any) -> str:
        return "—" if v is None or v == "" else str(v)
    L = ["| " + " | ".join(t for _, t in columnas) + " |", "|" + "---|" * len(columnas)]
    for f in filas:
        L.append("| " + " | ".join(cel(f.get(k)) for k, _ in columnas) + " |")
    return "\n".join(L)


def _ic_txt(f: Dict[str, Any], base: str, sufijo: str = "") -> str:
    p = f.get(base + "_pct")
    if p is None:
        return "—"
    lo, hi = f.get(f"{base}_ic{sufijo}_inf"), f.get(f"{base}_ic{sufijo}_sup")
    return f"{p:.1f}" + ("" if lo is None or hi is None else f" [{lo:.1f}–{hi:.1f}]")


# --------------------------------------------------------------------------
# Comparaciones pareadas
# --------------------------------------------------------------------------
def _clave_celda(s: Dict[str, Any]) -> tuple:
    return (s["experimento"], s["tarea"], s["proveedor"], s["modelo"], s["repeticion"])


def comparaciones_pareadas(muestras: List[Dict[str, Any]], n_boot: int = 1000) -> List[Dict[str, Any]]:
    """Diferencia de validez final (y − x) entre brazos emparejados por (tarea, modelo, repetición).

    Los pares X -> X+1 comparten la MISMA respuesta generada; los demás son generaciones distintas sobre la misma
    tarea (emparejadas por diseño).  IC por bootstrap de pares (solicitud) y por documento.
    """
    idx: Dict[tuple, Dict[str, Dict[str, Any]]] = defaultdict(dict)
    for s in muestras:
        idx[_clave_celda(s)][s["brazo"]] = s
    filas = []
    for exp in sorted({s["experimento"] for s in muestras}):
        for x, y, desc in COMPARACIONES:
            pares = [(c[x], c[y]) for k, c in idx.items() if k[0] == exp and x in c and y in c]
            if not pares:
                continue

            def par_num(a: Dict[str, Any], b: Dict[str, Any]):
                return ((_m(a, "validos_finales", 0), _m(a, "solicitados", 0)), (_m(b, "validos_finales", 0), _m(b, "solicitados", 0)))
            sol = [par_num(a, b) for a, b in pares]
            est, lo, hi = bootstrap_diferencia(sol, n_boot=n_boot)
            doc: Dict[str, List[List[float]]] = defaultdict(lambda: [[0.0, 0.0], [0.0, 0.0]])
            for (a, b), (pa, pb) in zip(pares, sol):
                d = doc[a["tarea"]]
                d[0][0] += pa[0]
                d[0][1] += pa[1]
                d[1][0] += pb[0]
                d[1][1] += pb[1]
            _, dlo, dhi = bootstrap_diferencia([((v[0][0], v[0][1]), (v[1][0], v[1][1])) for v in doc.values()], n_boot=n_boot)
            vx = sum(p[0][0] for p in sol) / sum(p[0][1] for p in sol) if sum(p[0][1] for p in sol) else None
            vy = sum(p[1][0] for p in sol) / sum(p[1][1] for p in sol) if sum(p[1][1] for p in sol) else None
            filas.append({"experimento": exp, "comparacion": f"{y} − {x}", "descripcion": desc, "pares": len(pares),
                          "misma_respuesta": B.base_de(y) == x, "validez_x_pct": _pct(vx), "validez_y_pct": _pct(vy),
                          "diferencia_pp": _pct(est), "ic_solicitud_inf": _pct(lo), "ic_solicitud_sup": _pct(hi),
                          "ic_documento_inf": _pct(dlo), "ic_documento_sup": _pct(dhi), "exploratoria": True})
    return filas


# --------------------------------------------------------------------------
# Reparación
# --------------------------------------------------------------------------
def reparacion(muestras: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    base = {s["id"]: s for s in muestras if not B.es_reparacion(s["brazo"])}
    g: Dict[tuple, List[tuple]] = defaultdict(list)
    for s in muestras:
        if not B.es_reparacion(s["brazo"]) or s.get("generacion_de") not in base:
            continue
        g[(s["experimento"], s["tipo_tarea"], B.base_de(s["brazo"]))].append((base[s["generacion_de"]], s))
    filas = []
    for (exp, tipo, x), pares in sorted(g.items(), key=lambda kv: (kv[0][0], kv[0][1], _orden_brazo(kv[0][2]))):
        ganados = sum(_m(r, "validos_finales", 0) - _m(b, "validos_finales", 0) for b, r in pares)
        peores = [(b, r) for b, r in pares if _m(r, "validos_finales", 0) < _m(b, "validos_finales", 0)]
        con_rep = [r for _, r in pares if r["metricas"].get("llamadas_reparacion")]
        tok = sum((r["metricas"].get("tokens_reparacion_entrada") or 0) + (r["metricas"].get("tokens_reparacion_salida") or 0) for _, r in pares)
        tok_sal = sum(r["metricas"].get("tokens_reparacion_salida") or 0 for _, r in pares)
        tok_gen = sum(b["metricas"].get("tokens_salida") or 0 for b, _ in pares)
        audit = [((r.get("reparacion") or {}).get("auditoria")) for _, r in pares]
        audit = [a for a in audit if a]

        def suma(k: str) -> Optional[int]:
            v = [a[k] for a in audit if a.get(k) is not None]
            return sum(v) if v else None
        no_recup = sum(len(((r.get("reparacion") or {}).get("rondas") or [{}])[-1].get("sin_resolver") or [])
                       for _, r in pares if (r.get("reparacion") or {}).get("rondas"))
        costo_rep = [Decimal(str(r["costo_incremental_usd"])) for _, r in pares if r.get("costo_incremental_usd") is not None]
        costo_rep_usd = sum(costo_rep, Decimal(0)) if len(costo_rep) == len(pares) and pares else None
        filas.append({"experimento": exp, "tipo_tarea": tipo, "brazo_base": x, "brazo_reparado": f"{x}+1", "pares": len(pares),
                      "muestras_reparadas": len(con_rep),
                      "llamadas_reparacion": sum(r["metricas"].get("llamadas_reparacion", 0) for _, r in pares),
                      "registros_validos_ganados": ganados,
                      "registros_correctos_ganados": sum(_m(r, "correctos", 0) - _m(b, "correctos", 0) for b, r in pares),
                      "cambio_incorrectos_sin_aviso": sum(_m(r, "incorrectos_sin_aviso", 0) - _m(b, "incorrectos_sin_aviso", 0) for b, r in pares),
                      "muestras_con_cambio_adverso": len(peores),
                      "registros_adversos": sum(_m(b, "validos_finales", 0) - _m(r, "validos_finales", 0) for b, r in peores),
                      "lineas_no_recuperadas": no_recup,
                      "validos_sobrescritos": suma("validos_sobrescritos"),
                      "identidades_duplicadas_finales": suma("identidades_duplicadas_finales"),
                      "identidades_inventadas": suma("identidades_inventadas"),
                      "correcciones_rechazadas_identidad": suma("correcciones_rechazadas_identidad"),
                      "reparaciones_auditadas": len(audit),
                      "exactas_base": sum(1 for b, _ in pares if b["metricas"].get("exacto")),
                      "exactas_reparadas": sum(1 for _, r in pares if r["metricas"].get("exacto")),
                      "tokens_reparacion_total": tok,
                      "tokens_por_registro_ganado": _f(tok / ganados, 1) if ganados > 0 else None,
                      "salida_reparacion_vs_generacion_pct": _f(100 * tok_sal / tok_gen) if tok_gen else None,
                      "costo_reparacion_usd": _f(costo_rep_usd, 6) if costo_rep_usd is not None else None})
    return filas


# --------------------------------------------------------------------------
# V4: latencia y costo; solicitudes; meta
# --------------------------------------------------------------------------
def latencia_costo(muestras: List[Dict[str, Any]], tarifas: Optional[Tarifas]) -> List[Dict[str, Any]]:
    cols = ("experimento", "brazo", "modelo_completo", "muestras", "latencia_flujo_mediana_s", "latencia_flujo_p95_s",
            "latencia_n", "latencia_excluidas_error_tecnico", "latencia_origen", "costo_usd_total",
            "costo_solicitud_mediana_usd", "costo_por_1000_validos_usd", "costo_nota", "validos_finales",
            "intentos_totales", "intentos_fallidos")
    filas = agrupar(muestras, ("experimento", "brazo", "modelo_completo"), tarifas=tarifas, ic=False)
    return [{k: f[k] for k in cols} for f in filas]


def solicitudes(muestras: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    out = []
    for s in muestras:
        sol = s.get("solicitud")
        if sol:
            out.append({**sol, "procedencia": procedencia_de(s), "experimento": s["experimento"], "tarea": s["tarea"],
                        "desenlace": s.get("desenlace")})
    return out


def evaluar_meta_v2(filas_modelo: List[Dict[str, Any]], procedencias: Iterable[str]) -> Dict[str, Any]:
    """Aplica ``CRITERIO_V2``.  Con material que no sea api_real el resultado es ``no_evaluable``, nunca cumple/no cumple."""
    procs = sorted(set(procedencias))
    evaluable = procs == ["api_real"]
    por_brazo: Dict[str, Any] = {}
    for f in filas_modelo:
        if f.get("experimento") != "v2":
            continue
        prov = f["modelo_completo"].split(":", 1)[0]
        v = f.get("validez_final_pct")
        d = por_brazo.setdefault(f["brazo"], {"modelos": {}, "proveedores_que_cumplen": set()})
        d["modelos"][f["modelo_completo"]] = v
        if v is not None and v / 100 >= CRITERIO_V2["umbral"]:
            d["proveedores_que_cumplen"].add(prov)
    res = {}
    for b, d in sorted(por_brazo.items(), key=lambda kv: _orden_brazo(kv[0])):
        cumplen = [m for m, v in d["modelos"].items() if v is not None and v / 100 >= CRITERIO_V2["umbral"]]
        cumple = (len(cumplen) >= CRITERIO_V2["min_modelos"] and len(d["proveedores_que_cumplen"]) >= CRITERIO_V2["min_proveedores"])
        res[b] = {"modelos_evaluados": len(d["modelos"]), "modelos_que_cumplen": len(cumplen),
                  "proveedores_que_cumplen": len(d["proveedores_que_cumplen"]),
                  "cumple": bool(cumple) if evaluable else None}
    return {"criterio": CRITERIO_V2, "procedencias": procs,
            "resultado": ("evaluado" if evaluable else "no_evaluable"),
            "motivo": ("" if evaluable else "el material no es api_real (simulado, asistido por IA o mezclado): una meta no se "
                                              "evalúa con él"),
            "por_brazo": res}


def resumen_v3a(filas: List[Dict[str, Any]], por_modelo: bool = False) -> List[Dict[str, Any]]:
    """V3a heredada (exploratoria): cortes sobre respuestas guardadas.  Denominador cero = None; IC por muestra (conglomerado)."""
    g: Dict[tuple, List[Dict[str, Any]]] = defaultdict(list)
    for f in filas:
        k = (f["brazo"], f"{f['proveedor']}:{f['modelo']}") if por_modelo else (f["brazo"],)
        g[k].append(f)
    out = []
    for k in sorted(g, key=lambda t: (_orden_brazo(t[0]),) + t[1:]):
        xs = g[k]
        n = len(xs)
        rec, ideal = sum(x["recuperados"] for x in xs), sum(x["ideal"] for x in xs)
        efs = [x["eficiencia"] for x in xs if x["eficiencia"] is not None]
        por_muestra: Dict[str, List[float]] = defaultdict(lambda: [0.0, 0.0])
        for x in xs:
            por_muestra[x["id"]][0] += 1 if x["cero"] else 0
            por_muestra[x["id"]][1] += 1
        est, lo, hi = bootstrap_razon([tuple(v) for v in por_muestra.values()], n_boot=500)
        fila = {"brazo": k[0]}
        if por_modelo:
            fila["modelo"] = k[1]
        fila.update({"cortes": n, "muestras": len(por_muestra), "recuperados_media": _f(rec / n),
                     "ideal_media": _f(ideal / n), "cortes_sin_ideal": n - len(efs),
                     "eficiencia_media_pct": _pct(sum(efs) / len(efs), 1) if efs else None,
                     "recuperados_sobre_ideal_pct": _pct(min(rec, ideal) / ideal, 1) if ideal else None,
                     "cero_recuperados_pct": _pct(est, 1), "cero_ic_inf": _pct(lo, 1), "cero_ic_sup": _pct(hi, 1),
                     "incorrectos_sin_aviso_total": sum(x["incorrectos_sin_aviso"] for x in xs)})
        out.append(fila)
    return out


# --------------------------------------------------------------------------
# Figuras
# --------------------------------------------------------------------------
def _estilo(ax) -> None:
    for lado in ("top", "right"):
        ax.spines[lado].set_visible(False)
    for lado in ("left", "bottom"):
        ax.spines[lado].set_color(REJILLA)
    ax.tick_params(colors=TINTA2, labelsize=9)
    ax.grid(axis="x", color=REJILLA, linewidth=0.8)
    ax.set_axisbelow(True)


def _sufijo(procs: Sequence[str]) -> str:
    if procs == ["simulado"]:
        return "  ·  SIMULADO: valida el arnés, no es un resultado del estudio"
    if procs == ["asistido_ia"]:
        return "  ·  ASISTIDO POR IA: no es una corrida de API"
    if procs != ["api_real"]:
        return "  ·  PROCEDENCIA MIXTA: " + ", ".join(procs)
    return ""


def figuras(salida: Path, res_brazos: List[Dict[str, Any]], v3a: List[Dict[str, Any]], procs: Sequence[str]) -> List[str]:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    sufijo = _sufijo(list(procs))
    sub = sufijo.replace("  ·  ", "")                      # línea propia: los títulos largos se cortaban
    hechas = []
    plt.rcParams.update({"font.size": 10, "axes.titlesize": 11, "axes.titlecolor": TINTA, "text.color": TINTA})

    # 1. desenlaces por registro (v2)
    tipos = [t for t in ("extraccion", "generativa") if any(f["experimento"] == "v2" and f["tipo_tarea"] == t for f in res_brazos)]
    if tipos:
        fig, axes = plt.subplots(len(tipos), 1, figsize=(9.5, 2.2 + 2.3 * len(tipos)), squeeze=False)
        for ax, tipo in zip(axes[:, 0], tipos):
            filas = [f for f in res_brazos if f["experimento"] == "v2" and f["tipo_tarea"] == tipo]
            filas.sort(key=lambda f: -_orden_brazo(f["brazo"]))
            y = list(range(len(filas)))
            izq = [0.0] * len(filas)
            for k in COLORES:
                vals = [f[k + "_pct"] or 0.0 for f in filas]
                ax.barh(y, vals, left=izq, color=COLORES[k], height=0.62, edgecolor="white", linewidth=2, label=ETIQUETAS[k])
                for yi, (l, v) in enumerate(zip(izq, vals)):
                    if v >= 7:
                        ax.text(l + v / 2, yi, f"{v:.0f}", ha="center", va="center", fontsize=8, color="white")
                izq = [a + b for a, b in zip(izq, vals)]
            ax.set_yticks(y)
            ax.set_yticklabels([NOMBRE_BRAZO.get(f["brazo"], f["brazo"]) for f in filas], color=TINTA)
            ax.set_xlim(0, 100)
            ax.set_xlabel("% de registros (esperados + espurios)", color=TINTA2)
            ax.set_title("Tareas de extracción" if tipo == "extraccion" else "Tareas generativas (contra contrato)", loc="left")
            _estilo(ax)
        axes[0, 0].legend(ncol=4, fontsize=8, frameon=False, loc="lower left", bbox_to_anchor=(0, 1.12))
        fig.suptitle("V2 · Desenlace de cada registro por brazo" + sufijo, x=0.01, ha="left", fontsize=11, color=TINTA, y=0.995)
        fig.tight_layout()
        p = salida / "fig_v2_desenlaces_registros.png"
        fig.savefig(p, dpi=160)
        plt.close(fig)
        hechas.append(p.name)

    # 2. validez final con IC por solicitud
    filas = [f for f in res_brazos if f["experimento"] == "v2"]
    if filas:
        fig, ax = plt.subplots(figsize=(9.5, 0.9 + 0.42 * len(filas)))
        etiquetas = []
        for i, f in enumerate(filas):
            color = "#2a78d6" if f["tipo_tarea"] == "extraccion" else "#4a3aa7"
            p_ = f["validez_final_pct"]
            if p_ is None:
                etiquetas.append(f"{NOMBRE_BRAZO.get(f['brazo'], f['brazo'])} — sin datos")
                continue
            lo, hi = f["validez_final_ic_solicitud_inf"], f["validez_final_ic_solicitud_sup"]
            if lo is not None and hi is not None:
                ax.errorbar([p_], [i], xerr=[[max(0.0, p_ - lo)], [max(0.0, hi - p_)]], fmt="o", color=color, ecolor=color,
                            markersize=7, capsize=3, linewidth=2)
            else:
                ax.plot([p_], [i], "o", color=color, markersize=7)
            etiquetas.append(f"{NOMBRE_BRAZO.get(f['brazo'], f['brazo'])} — {'extracción' if f['tipo_tarea'] == 'extraccion' else 'generativa'}")
        ax.axvline(95, color=TINTA2, linewidth=1, linestyle=":")
        ax.set_yticks(range(len(filas)))
        ax.set_yticklabels(etiquetas, fontsize=8, color=TINTA)
        ax.invert_yaxis()
        ax.set_xlim(0, 103)
        ax.set_xlabel("validez final % = registros válidos / registros solicitados (IC 95 % bootstrap por solicitud)", color=TINTA2)
        ax.set_title("V2 · Validez final por brazo (línea punteada: 95 %)" + (NL_ + sub if sub else ""), loc="left")
        _estilo(ax)
        fig.tight_layout()
        p = salida / "fig_v2_validez_final.png"
        fig.savefig(p, dpi=160)
        plt.close(fig)
        hechas.append(p.name)

    # 3. tokens medios por muestra
    if filas:
        por_brazo: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
        for f in filas:
            if f["tokens_entrada_media"] is not None and f["tokens_salida_media"] is not None:
                por_brazo[f["brazo"]].append(f)
        br = sorted(por_brazo, key=_orden_brazo)
        if br:
            def pond(b: str, k: str) -> float:
                fs = por_brazo[b]
                return sum(f[k] * f["muestras"] for f in fs) / sum(f["muestras"] for f in fs)
            entrada = [pond(b, "tokens_entrada_media") for b in br]
            salida_t = [pond(b, "tokens_salida_media") for b in br]
            fig, ax = plt.subplots(figsize=(9.5, 1.2 + 0.6 * len(br)))
            y = range(len(br))
            ax.barh([i + 0.2 for i in y], entrada, height=0.38, color="#2a78d6", edgecolor="white", linewidth=2, label="Entrada (incluye reparación)")
            ax.barh([i - 0.2 for i in y], salida_t, height=0.38, color="#eb6834", edgecolor="white", linewidth=2, label="Salida (incluye reparación)")
            for i, (a, b) in enumerate(zip(entrada, salida_t)):
                ax.text(a, i + 0.2, f" {a:,.0f}", va="center", fontsize=8, color=TINTA2)
                ax.text(b, i - 0.2, f" {b:,.0f}", va="center", fontsize=8, color=TINTA2)
            ax.set_yticks(list(y))
            ax.set_yticklabels([NOMBRE_BRAZO.get(b, b) for b in br], color=TINTA)
            ax.invert_yaxis()
            ax.set_xlabel("tokens medios por muestra (los que reporta el adaptador)", color=TINTA2)
            ax.set_title("V2 · Tokens por muestra" + (NL_ + sub if sub else ""), loc="left")
            ax.set_xlim(0, max(entrada + salida_t) * 1.12)
            ax.legend(frameon=False, fontsize=8, loc="upper center", bbox_to_anchor=(0.5, -0.16), ncol=2)
            _estilo(ax)
            fig.tight_layout()
            p = salida / "fig_v2_tokens.png"
            fig.savefig(p, dpi=160, bbox_inches="tight")
            plt.close(fig)
            hechas.append(p.name)

    # 4. latencia del flujo completo (V4)
    lat = [f for f in res_brazos if f["experimento"] == "v2" and f["latencia_flujo_mediana_s"] is not None]
    if lat:
        agg: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
        for f in lat:
            agg[f["brazo"]].append(f)
        br = sorted(agg, key=_orden_brazo)
        med = [sum(f["latencia_flujo_mediana_s"] * f["latencia_n"] for f in agg[b]) / sum(f["latencia_n"] for f in agg[b]) for b in br]
        p95 = [max(f["latencia_flujo_p95_s"] for f in agg[b]) for b in br]
        fig, ax = plt.subplots(figsize=(9.5, 1.2 + 0.5 * len(br)))
        ax.barh(range(len(br)), med, color="#2a78d6", height=0.6, edgecolor="white", linewidth=2, label="mediana (ponderada por n)")
        ax.plot(p95, range(len(br)), "D", color="#eb6834", label="p95 máximo entre grupos")
        ax.set_yticks(range(len(br)))
        ax.set_yticklabels([NOMBRE_BRAZO.get(b, b) for b in br], color=TINTA)
        ax.invert_yaxis()
        ax.set_xlabel("segundos, flujo completo (generación + validación + reparación + entrega)", color=TINTA2)
        ax.set_title("V4 · Latencia del flujo" + (NL_ + sub if sub else ""), loc="left")
        ax.legend(frameon=False, fontsize=8, loc="upper center", bbox_to_anchor=(0.5, -0.16), ncol=2)
        _estilo(ax)
        fig.tight_layout()
        p = salida / "fig_v4_latencia.png"
        fig.savefig(p, dpi=160, bbox_inches="tight")
        plt.close(fig)
        hechas.append(p.name)

    # 5. recuperación ante truncamiento
    v3b = [f for f in res_brazos if f["experimento"] == "v3b"]
    if v3a or v3b:
        fig, axes = plt.subplots(1, 2, figsize=(10.5, 3.8))
        if v3a:
            ax = axes[0]
            br = [f["brazo"] for f in v3a]
            vals = [f["recuperados_sobre_ideal_pct"] or 0 for f in v3a]
            ax.barh(range(len(br)), vals, color="#2a78d6", height=0.6, edgecolor="white", linewidth=2)
            for i, v in enumerate(vals):
                ax.text(v, i, f" {v:.0f} %", va="center", fontsize=8, color=TINTA2)
            ax.set_yticks(range(len(br)))
            ax.set_yticklabels([NOMBRE_BRAZO.get(b, b) for b in br], color=TINTA)
            ax.invert_yaxis()
            ax.set_xlim(0, 110)
            ax.set_xlabel("registros recuperados / recuperables (%)", color=TINTA2)
            ax.set_title("V3a heredada · cortes sobre respuestas", loc="left")
            _estilo(ax)
        else:
            axes[0].axis("off")
        if v3b:
            ax = axes[1]
            agg2: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
            for f in v3b:
                agg2[f["brazo"]].append(f)
            br = sorted(agg2, key=_orden_brazo)
            for i, b in enumerate(br):
                v = sum(f["validos_finales"] for f in agg2[b])
                den = sum(f["registros_solicitados"] for f in agg2[b])
                if not den:
                    continue
                ax.plot([100 * v / den], [i], "o", color="#2a78d6", markersize=8)
                ax.text(100 * v / den, i, f"  {100 * v / den:.0f} %", va="center", fontsize=8, color=TINTA2)
            ax.set_yticks(range(len(br)))
            ax.set_yticklabels([NOMBRE_BRAZO.get(b, b) for b in br], color=TINTA)
            ax.invert_yaxis()
            ax.set_xlim(-3, 103)
            ax.set_xlabel("validez final % sobre los solicitados", color=TINTA2)
            ax.set_title("V3b · Generación con límite de salida", loc="left")
            _estilo(ax)
        else:
            axes[1].axis("off")
        fig.suptitle("Recuperación ante truncamiento" + sufijo, x=0.01, ha="left", fontsize=11, color=TINTA)
        fig.tight_layout()
        p = salida / "fig_v3_recuperacion.png"
        fig.savefig(p, dpi=160)
        plt.close(fig)
        hechas.append(p.name)
    return hechas


# --------------------------------------------------------------------------
def _banner(procs: Sequence[str]) -> List[str]:
    if list(procs) == ["simulado"]:
        return ["> **RESULTADOS SIMULADOS.** Estas cifras provienen del adaptador simulado, cuyas tasas de falla son "
                "supuestos del simulador. Solo validan que el arnés funciona de extremo a extremo; **no son resultados "
                "del estudio** y no deben citarse como evidencia sobre ningún formato ni modelo.", ""]
    if list(procs) == ["asistido_ia"]:
        return ["> **MATERIAL ASISTIDO POR IA.** Las respuestas las produjo una IA en sesión (sin usage ni factura de API); "
                "los tokens, si aparecen, son un conteo local aproximado. Sirve para probar el análisis, no es una corrida "
                "de API ni se presenta como tal.", ""]
    if list(procs) != ["api_real"]:
        return [f"> **PROCEDENCIA MIXTA ({', '.join(procs)}).** No se deben sumar ni comparar como un solo estudio.", ""]
    return []


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--resultados", required=True, help="directorio con muestras.jsonl y manifiesto.json")
    ap.add_argument("--sin-figuras", action="store_true")
    ap.add_argument("--tarifas", default=None, help="archivo de tarifas (por defecto evidencia/tarifas/tarifas.json si existe)")
    ap.add_argument("--sin-v3a", action="store_true", help="omite la V3a heredada (tarda en estudios grandes)")
    ap.add_argument("--bootstrap", type=int, default=1000, help="réplicas del bootstrap por conglomerados (0 = sin IC)")
    args = ap.parse_args(argv)
    res_dir = Path(args.resultados)
    muestras = normalizar(leer_muestras(res_dir / "muestras.jsonl"))
    if not muestras:
        print(f"no hay muestras en {res_dir}", file=sys.stderr)
        return 2
    manifiesto = {}
    if (res_dir / "manifiesto.json").exists():
        manifiesto = json.loads((res_dir / "manifiesto.json").read_text(encoding="utf-8"))
    cfg = manifiesto.get("config", {})
    procs = sorted({procedencia_de(s) for s in muestras})
    tarifas = Tarifas.cargar(Path(args.tarifas)) if args.tarifas else (Tarifas.cargar() if args.tarifas is None else None)
    if tarifas is not None and not tarifas.origen:
        tarifas = None                          # sin archivo: se usan los costos que guardó cada muestra (o ninguno)
    salida = res_dir / "analisis"
    salida.mkdir(parents=True, exist_ok=True)
    nb, ic = max(args.bootstrap, 0), args.bootstrap > 0

    res_brazos = agrupar(muestras, ("experimento", "tipo_tarea", "brazo"), tarifas=tarifas, n_boot=nb, ic=ic)
    res_modelo = agrupar(muestras, ("experimento", "tipo_tarea", "brazo", "modelo_completo"), tarifas=tarifas, n_boot=nb, ic=ic)
    res_tarea = agrupar(muestras, ("experimento", "tarea", "brazo"), tarifas=tarifas, ic=False)
    res_brazo_modelo_total = agrupar(muestras, ("experimento", "brazo", "modelo_completo"), tarifas=tarifas, n_boot=nb, ic=False)
    pareadas = comparaciones_pareadas(muestras, n_boot=max(nb, 1)) if ic else []
    rep = reparacion(muestras)
    desen = [{k: f[k] for k in ("experimento", "tipo_tarea", "brazo", "muestras") + tuple(f"desenlace_{d}" for d in DESENLACES)}
             for f in res_brazos]
    v4 = latencia_costo(muestras, tarifas)
    sols = solicitudes(muestras)
    meta = evaluar_meta_v2(res_brazo_modelo_total, procs)
    v3cfg = (cfg.get("experimentos") or {}).get("v3a") or {}
    tareas = T.cargar(sorted({s["tarea"] for s in muestras}))
    brazos_v3a = tuple(b for b in v3cfg.get("brazos", ["A", "B", "C", "D"]) if b in B.BRAZOS)
    cortes = [] if args.sin_v3a else cortes_controlados(muestras, tareas, cortes=int(v3cfg.get("cortes_por_muestra", 20)),
                                                        semilla=int(v3cfg.get("semilla", 7)), brazos=brazos_v3a)
    v3a = resumen_v3a(cortes)
    v3a_modelo = resumen_v3a(cortes, por_modelo=True)

    escribir_csv(salida / "resumen_brazos.csv", res_brazos)
    escribir_csv(salida / "resumen_brazo_modelo.csv", res_modelo)
    escribir_csv(salida / "resumen_brazo_tarea.csv", res_tarea)
    escribir_csv(salida / "comparaciones_pareadas.csv", pareadas)
    escribir_csv(salida / "reparacion.csv", rep)
    escribir_csv(salida / "desenlaces.csv", desen)
    escribir_csv(salida / "latencia_costo.csv", v4)
    escribir_csv(salida / "v3a_truncamiento.csv", v3a)
    escribir_csv(salida / "v3a_truncamiento_modelo.csv", v3a_modelo)
    with open(salida / "solicitudes.jsonl", "w", encoding="utf-8", newline="\n") as fh:
        for x in sols:
            fh.write(json.dumps(x, ensure_ascii=False, sort_keys=True) + "\n")
    escribir_texto(salida / "meta_v2.json", json.dumps(meta, ensure_ascii=False, indent=2, sort_keys=True, default=list) + "\n")

    for f in res_brazos + res_modelo:
        f["validez_txt"] = _ic_txt(f, "validez_final", "_solicitud")
        f["exactitud_txt"] = _ic_txt(f, "exactitud_contenido", "_solicitud")
        f["sintaxis_txt"] = _ic_txt(f, "sintaxis_ok")
    cols = [("experimento", "exp."), ("tipo_tarea", "tipo"), ("brazo", "brazo"), ("muestras", "muestras"),
            ("sintaxis_txt", "sintaxis analizable % [IC95]"), ("cumplimiento_contrato_pct", "cumple contrato % (de los aceptados)"),
            ("exactitud_txt", "exactitud de contenido % [IC95 solic.]"), ("validez_txt", "validez final % [IC95 solic.]"),
            ("incorrectos_sin_aviso_pct", "incorrectos sin aviso %"), ("perdidos_sin_aviso_pct", "perdidos sin aviso %"),
            ("perdidos_detectados_pct", "perdidos con aviso %"), ("tokens_entrada_media", "tok. entrada"),
            ("tokens_salida_media", "tok. salida"), ("latencia_flujo_mediana_s", "latencia mediana s"),
            ("latencia_flujo_p95_s", "p95 s"), ("latencia_n", "n"), ("costo_por_1000_validos_usd", "USD / 1000 válidos")]
    L = [f"# Resumen del experimento generativo — {manifiesto.get('nombre', res_dir.name)}", ""] + _banner(procs)
    L += [f"Muestras: {len(muestras)} · commit: `{(manifiesto.get('commit') or '')[:10]}` · adaptador: {manifiesto.get('adaptador', '')} · "
          f"procedencia: {', '.join(procs)}", ""]
    est_path = res_dir / "estado_estudio.json"
    if est_path.exists():
        est = json.loads(est_path.read_text(encoding="utf-8"))
        L += [f"Estado del estudio: **{est.get('estado')}** · celdas {est.get('celdas')} · gasto {est.get('gasto')}", ""]
    L += ["Validez final = registros válidos / registros SOLICITADOS (los ausentes cuentan como no válidos). IC 95 %: bootstrap de "
          "conglomerados por solicitud (nunca por registro o campo). Sintaxis: IC de Wilson por muestra. Los costos dependen de "
          "tarifas verificadas; sin ellas son «tarifa no verificada».", "",
          "## Por brazo", "", tabla_md(res_brazos, cols), "",
          "## Por brazo y modelo", "", tabla_md(res_modelo, cols[:3] + [("modelo_completo", "modelo")] + cols[3:]), "",
          "## Desenlaces de la respuesta (recuento de muestras)", "",
          tabla_md(desen, [(k, k.replace("desenlace_", "").replace("_", " ")) for k in (desen[0].keys() if desen else [])]), "",
          "## Comparaciones pareadas (EXPLORATORIAS: sin corrección por comparaciones múltiples)", "",
          (tabla_md(pareadas, [("experimento", "exp."), ("comparacion", "y − x"), ("descripcion", "qué compara"), ("pares", "pares"),
                               ("misma_respuesta", "misma respuesta"), ("validez_x_pct", "validez x %"), ("validez_y_pct", "validez y %"),
                               ("diferencia_pp", "dif. pp"), ("ic_solicitud_inf", "IC solic. inf"), ("ic_solicitud_sup", "IC solic. sup"),
                               ("ic_documento_inf", "IC doc. inf"), ("ic_documento_sup", "IC doc. sup")]) if pareadas else "(sin pares)"), "",
          "## Reparación selectiva (X frente a X+1, sobre la misma respuesta)", "",
          tabla_md(rep, [(k, k.replace("_", " ")) for k in (rep[0].keys() if rep else [])]) if rep else "(sin pares X / X+1)", "",
          "## V4 · latencia del flujo completo y costo", "",
          tabla_md(v4, [(k, k.replace("_", " ")) for k in (v4[0].keys() if v4 else [])]), "",
          "## Meta V2 (criterio fijado antes de analizar)", "",
          f"Resultado: **{meta['resultado']}**. " + meta["motivo"], "",
          "## V3a heredada (exploratoria) · cortes sobre salidas guardadas", "",
          "La V3a del Plan (documento canónico, fracciones predefinidas, JSON parcial y JSON Lines) está en `experiments/truncamiento`; "
          "esta tabla corta las respuestas guardadas de cada brazo y deja el denominador cero como vacío.", "",
          tabla_md(v3a, [(k, k.replace("_", " ")) for k in (v3a[0].keys() if v3a else [])]) if v3a else "(sin muestras v2)", ""]
    if not args.sin_figuras:
        hechas = figuras(salida, res_brazos, v3a, procs)
        L += ["## Figuras", ""] + [f"![{h}]({h})" for h in hechas]
    escribir_texto(salida / "resumen.md", "\n".join(L) + "\n")
    print(f"análisis escrito en {salida}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
