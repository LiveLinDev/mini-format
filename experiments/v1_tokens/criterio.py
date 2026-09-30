"""Evaluación del criterio documental de V1 con la interpretación fijada en ``criterio_v1.json``.

El umbral, el mínimo de dominios, los tokenizadores, la serie primaria y la regla de
decisión salen de ``criterio_v1.json`` (fijado y confirmado en git ANTES del análisis);
aquí no hay otro umbral. Además del veredicto primario se calculan, sin elegir, las lecturas
alternativas: media por dominio frente a agregado por suma, n = 12, variante ``ciclo``,
intersección de dominios y el efecto del tamaño n.

Entrada: filas de ``serie.medir_serie`` (``tokens_largo``). Solo entran en un ahorro los
formatos con ``comparacion_valida`` (reversibilidad verificada); un dominio cuyo par
.mini/JSON compacto no es válido se excluye de forma explícita y visible.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np

HERE = Path(__file__).resolve().parent
RUTA_CRITERIO = HERE / "criterio_v1.json"


def cargar_criterio(ruta: Path = RUTA_CRITERIO) -> Dict[str, Any]:
    return json.loads(Path(ruta).read_text(encoding="utf-8"))


# ------------------------------------------------------------------ agregación
def suma_por_dominio(filas: Sequence[Dict[str, Any]], tokenizador: str, variante: str, n: Optional[int],
                     formato: str) -> Dict[str, Optional[int]]:
    """Σ tokens de TODOS los documentos de cada dominio (``n`` None = todos los n de la variante).

    Un dominio cuyo documento no es válido para la comparación devuelve ``None``.
    """
    out: Dict[str, Optional[int]] = {}
    for f in filas:
        if f["tokenizador"] != tokenizador or f["variante"] != variante or f["formato"] != formato:
            continue
        if n is not None and int(f["n"]) != int(n):
            continue
        d = f["dominio"]
        valido = bool(f["comparacion_valida"]) and f["tokens"] is not None
        if not valido:
            out[d] = None
        elif d in out and out[d] is None:
            continue
        else:
            out[d] = out.get(d, 0) + int(f["tokens"])
    return out


def ahorros_dominio(filas: Sequence[Dict[str, Any]], tokenizador: str, variante: str, n: Optional[int],
                    ref: str = "json_compact") -> Dict[str, Any]:
    """Ahorro de .mini frente a ``ref`` por dominio (Σ sobre documentos) y dominios excluidos."""
    m = suma_por_dominio(filas, tokenizador, variante, n, "mini")
    r = suma_por_dominio(filas, tokenizador, variante, n, ref)
    dominios = sorted(set(m) | set(r))
    validos, excluidos = [], []
    for d in dominios:
        if m.get(d) is None or r.get(d) is None or r[d] == 0:
            excluidos.append(d)
        else:
            validos.append(d)
    return {
        "dominios": validos, "excluidos": excluidos,
        "tokens_mini": {d: m[d] for d in validos}, "tokens_ref": {d: r[d] for d in validos},
        "ahorro_pct": {d: 100.0 * (1.0 - m[d] / r[d]) for d in validos},
    }


def bootstrap_dominios(tok_mini: Sequence[float], tok_ref: Sequence[float], B: int = 10000, semilla: int = 20260914,
                       alfa: float = 0.05) -> Dict[str, Tuple[float, float]]:
    """IC percentil por conglomerados (dominios con reemplazo) de la media por dominio y del agregado por suma."""
    m = np.asarray(tok_mini, dtype=float)
    r = np.asarray(tok_ref, dtype=float)
    a = 100.0 * (1.0 - m / r)
    rng = np.random.default_rng(semilla)
    idx = rng.integers(0, len(a), size=(B, len(a)))
    medias = a[idx].mean(axis=1)
    agreg = 100.0 * (1.0 - m[idx].sum(axis=1) / r[idx].sum(axis=1))
    q = (alfa / 2, 1 - alfa / 2)
    return {"media": (float(np.quantile(medias, q[0])), float(np.quantile(medias, q[1]))),
            "agregado": (float(np.quantile(agreg, q[0])), float(np.quantile(agreg, q[1])))}


def resumen_serie(filas: Sequence[Dict[str, Any]], tokenizador: str, variante: str, n: Optional[int], umbral: float,
                  B: int = 10000, semilla: int = 20260914, ref: str = "json_compact") -> Dict[str, Any]:
    a = ahorros_dominio(filas, tokenizador, variante, n, ref)
    dom = a["dominios"]
    if not dom:
        return {"tokenizador": tokenizador, "variante": variante, "n": n, "dominios_validos": 0, "excluidos": a["excluidos"]}
    m = [a["tokens_mini"][d] for d in dom]
    r = [a["tokens_ref"][d] for d in dom]
    ahorro = [a["ahorro_pct"][d] for d in dom]
    ic = bootstrap_dominios(m, r, B, semilla)
    ge = [d for d in dom if a["ahorro_pct"][d] >= umbral]
    return {
        "tokenizador": tokenizador, "variante": variante, "n": n,
        "dominios_validos": len(dom), "dominios_excluidos": a["excluidos"],
        "tokens_mini_total": int(sum(m)), "tokens_json_compacto_total": int(sum(r)),
        "media_por_dominio_pct": float(np.mean(ahorro)), "ic95_media": list(ic["media"]),
        "agregado_suma_pct": 100.0 * (1.0 - sum(m) / sum(r)), "ic95_agregado": list(ic["agregado"]),
        "mediana_pct": float(np.median(ahorro)), "min_pct": float(min(ahorro)), "max_pct": float(max(ahorro)),
        "dominios_ge_umbral": len(ge), "lista_dominios_ge_umbral": ge,
        "lista_dominios_lt_umbral": [d for d in dom if d not in ge],
        "ahorro_por_dominio_pct": {d: a["ahorro_pct"][d] for d in dom},
    }


def tabla_referencias(filas: Sequence[Dict[str, Any]], filas_rev: Sequence[Dict[str, Any]], umbral: float,
                      B: int = 2000, semilla: int = 20260914) -> List[Dict[str, Any]]:
    """Ahorro de .mini frente a CADA comparador, con la exclusión explícita de los no reversibles.

    Un comparador cuyo documento no se reconstruye (``no_reversible``) no entra en ninguna media:
    su fila sale con ``estado = excluido_no_reversible``, la causa y sin cifra de ahorro.
    """
    causas: Dict[str, str] = {}
    for r in filas_rev:
        if r["estado"] == "no_reversible" and r["formato"] not in causas:
            causas[r["formato"]] = r["causa"]
    out: List[Dict[str, Any]] = []
    toks = sorted({f["tokenizador"] for f in filas})
    formatos = [f for f in dict.fromkeys(f["formato"] for f in filas) if f != "mini"]
    combos = sorted({(f["variante"], int(f["n"])) for f in filas})
    decod = {f["formato"]: f["decodificacion"] for f in filas}
    for t in toks:
        for variante, n in combos:
            for ref in formatos:
                r = resumen_serie(filas, t, variante, n, umbral, B, semilla, ref)
                base = {"tokenizador": t, "variante": variante, "n": n, "referencia": ref, "decodificacion": decod[ref],
                        "replicacion_de_base": n > 12}
                if not r.get("dominios_validos"):
                    out.append({**base, "estado": "excluido_no_reversible", "dominios_validos": 0,
                                "dominios_excluidos": ";".join(r.get("excluidos", r.get("dominios_excluidos", []))),
                                "causa": causas.get(ref, "ningún dominio con ida y vuelta verificada"),
                                "media_por_dominio_pct": None, "ic95_media_inf": None, "ic95_media_sup": None,
                                "agregado_suma_pct": None, "ic95_agregado_inf": None, "ic95_agregado_sup": None, "dominios_ge_umbral": None})
                    continue
                excl = r["dominios_excluidos"]
                out.append({**base, "estado": "incluido" if not excl else "parcial_dominios_excluidos", "dominios_validos": r["dominios_validos"],
                            "dominios_excluidos": ";".join(excl), "causa": causas.get(ref, "") if excl else "",
                            "media_por_dominio_pct": r["media_por_dominio_pct"], "ic95_media_inf": r["ic95_media"][0], "ic95_media_sup": r["ic95_media"][1],
                            "agregado_suma_pct": r["agregado_suma_pct"], "ic95_agregado_inf": r["ic95_agregado"][0], "ic95_agregado_sup": r["ic95_agregado"][1],
                            "dominios_ge_umbral": r["dominios_ge_umbral"]})
    return out


# ------------------------------------------------------------------ veredicto
def evaluar(filas: Sequence[Dict[str, Any]], criterio: Optional[Dict[str, Any]] = None, B: int = 10000) -> Dict[str, Any]:
    """Veredicto primario + lecturas alternativas + efecto de n, todo desde ``filas``."""
    crit = criterio or cargar_criterio()
    ip = crit["interpretacion_primaria"]
    umbral = float(ip["umbral_pct"])
    minimo = int(ip["min_dominios"])
    toks = list(ip["tokenizadores"])
    semilla = 20260914

    primario = {t: resumen_serie(filas, t, ip["variante"], ip["n"], umbral, B, semilla) for t in toks}
    por_tok = {t: {"dominios_ge_umbral": r.get("dominios_ge_umbral", 0), "cumple": r.get("dominios_ge_umbral", 0) >= minimo}
               for t, r in primario.items()}
    dominios_en_datos = sorted({f["dominio"] for f in filas})
    alcance_completo = len(dominios_en_datos) == int(ip["dominios_totales"])
    if not alcance_completo:  # subconjunto de dominios (p. ej. --rapido): el cálculo se publica, el veredicto no
        veredicto = "no_evaluable"
    else:
        veredicto = "cumple" if all(v["cumple"] for v in por_tok.values()) else "no_cumple"

    def lecturas(variante: str, n: Optional[int]) -> Dict[str, Any]:
        res = {t: resumen_serie(filas, t, variante, n, umbral, B, semilla) for t in toks}
        out: Dict[str, Any] = {"serie": {"variante": variante, "n": n}, "por_tokenizador": res}
        ok_dom = {t: res[t].get("dominios_ge_umbral", 0) >= minimo for t in toks}
        ok_media = {t: res[t].get("media_por_dominio_pct", -1) >= umbral for t in toks}
        ok_agreg = {t: res[t].get("agregado_suma_pct", -1) >= umbral for t in toks}
        inter = set.intersection(*[set(res[t].get("lista_dominios_ge_umbral", [])) for t in toks]) if toks else set()
        out["lecturas"] = {
            "dominios_ge_umbral_en_cada_tokenizador": {"por_tokenizador": ok_dom, "cumple": all(ok_dom.values())},
            "media_por_dominio_ge_umbral_en_cada_tokenizador": {"por_tokenizador": ok_media, "cumple": all(ok_media.values())},
            "agregado_suma_ge_umbral_en_cada_tokenizador": {"por_tokenizador": ok_agreg, "cumple": all(ok_agreg.values())},
            "interseccion_de_dominios_ge_umbral_con_los_tres": {"dominios": sorted(inter), "n": len(inter), "cumple": len(inter) >= minimo},
        }
        return out

    alternativas = {
        "n100_muestreo": lecturas("muestreo", 100),
        "n100_ciclo": lecturas("ciclo", 100),
        "n12_ciclo": lecturas("ciclo", 12),
        "n12_muestreo": lecturas("muestreo", 12),
    }
    ns = sorted({int(f["n"]) for f in filas})
    efecto_n = []
    for variante in ("muestreo", "ciclo"):
        for n in ns:
            for t in toks:
                r = resumen_serie(filas, t, variante, n, umbral, B, semilla)
                if not r.get("dominios_validos"):
                    continue
                efecto_n.append({"variante": variante, "n": n, "tokenizador": t, "media_por_dominio_pct": r["media_por_dominio_pct"],
                                 "ic95_media": r["ic95_media"], "agregado_suma_pct": r["agregado_suma_pct"],
                                 "ic95_agregado": r["ic95_agregado"], "dominios_ge_umbral": r["dominios_ge_umbral"],
                                 "replicacion_de_base": n > 12})
    return {
        "criterio_id": crit["id"], "umbral_pct": umbral, "min_dominios": minimo, "tokenizadores": toks,
        "interpretacion_primaria": ip, "fijado_el": crit["fijado_el"], "sujeto_a_aprobacion_del_asesor": crit["sujeto_a_aprobacion_del_asesor"],
        "primario": {"resumen_por_tokenizador": primario, "decision_por_tokenizador": por_tok, "veredicto": veredicto,
                     "dominios_en_los_datos": dominios_en_datos, "alcance_completo": alcance_completo},
        "lecturas_alternativas": alternativas,
        "efecto_n": efecto_n,
    }


def _fmt(x: Any, nd: int = 2) -> str:
    return "—" if x is None else f"{x:.{nd}f}".replace(".", ",")


def informe_md(ev: Dict[str, Any]) -> str:
    """Informe legible del criterio: veredicto primario y TODAS las lecturas."""
    p = ev["primario"]
    L = ["# Criterio documental V1: evaluación", "",
         f"Criterio `{ev['criterio_id']}`, fijado el {ev['fijado_el']} antes del análisis; "
         "**sujeto a aprobación del asesor**.", "",
         "## Veredicto con la interpretación primaria", "",
         f"Serie n=100, variante `muestreo`; ahorro del dominio = 1 − ΣT(.mini)/ΣT(JSON compacto) sobre todos los documentos del dominio; "
         f"umbral {_fmt(ev['umbral_pct'], 0)} %; mínimo {ev['min_dominios']} dominios por tokenizador.", "",
         "| Tokenizador | Dominios ≥ 30 % | ¿≥ 10? | Media por dominio (IC95) | Agregado por suma (IC95) | Mín–máx |",
         "|---|---:|:---:|---|---|---|"]
    for t, r in p["resumen_por_tokenizador"].items():
        d = p["decision_por_tokenizador"][t]
        L.append(f"| {t} | {r['dominios_ge_umbral']} / {r['dominios_validos']} | {'sí' if d['cumple'] else 'no'} | "
                 f"{_fmt(r['media_por_dominio_pct'])} % [{_fmt(r['ic95_media'][0])}; {_fmt(r['ic95_media'][1])}] | "
                 f"{_fmt(r['agregado_suma_pct'])} % [{_fmt(r['ic95_agregado'][0])}; {_fmt(r['ic95_agregado'][1])}] | "
                 f"{_fmt(r['min_pct'], 1)}–{_fmt(r['max_pct'], 1)} |")
    L += ["", f"**Veredicto primario: `{p['veredicto']}`.**" + ("" if p["alcance_completo"] else
          f" (solo hay {len(p['dominios_en_los_datos'])} dominios en los datos: el criterio exige {ev['interpretacion_primaria']['dominios_totales']}; las cifras no son las publicadas)"), "",
          "Dominios por debajo del umbral (n=100 muestreo):", ""]
    for t, r in p["resumen_por_tokenizador"].items():
        bajos = ", ".join(f"{d} {_fmt(r['ahorro_por_dominio_pct'][d], 1)}" for d in r["lista_dominios_lt_umbral"]) or "ninguno"
        L.append(f"* {t}: {bajos}")
    L += ["", "## Lecturas alternativas (publicadas sin elegir la más alta)", "",
          "| Serie | Lectura | " + " | ".join(ev["tokenizadores"]) + " | ¿cumple los tres? |", "|---|---|" + "---:|" * len(ev["tokenizadores"]) + ":---:|"]
    nombres = {"dominios_ge_umbral_en_cada_tokenizador": "≥ 10 dominios con ahorro ≥ 30 %",
               "media_por_dominio_ge_umbral_en_cada_tokenizador": "media por dominio ≥ 30 %",
               "agregado_suma_ge_umbral_en_cada_tokenizador": "agregado por suma ≥ 30 %"}
    for clave, alt in ev["lecturas_alternativas"].items():
        s = alt["serie"]
        for lect, etiqueta in nombres.items():
            celdas = []
            for t in ev["tokenizadores"]:
                r = alt["por_tokenizador"][t]
                if lect.startswith("dominios"):
                    celdas.append(f"{r.get('dominios_ge_umbral', 0)}/{r.get('dominios_validos', 0)}")
                elif lect.startswith("media"):
                    celdas.append(_fmt(r.get("media_por_dominio_pct")) + " %")
                else:
                    celdas.append(_fmt(r.get("agregado_suma_pct")) + " %")
            ok = alt["lecturas"][lect]["cumple"]
            L.append(f"| {clave} | {etiqueta} | " + " | ".join(celdas) + f" | {'sí' if ok else 'no'} |")
        it = alt["lecturas"]["interseccion_de_dominios_ge_umbral_con_los_tres"]
        L.append(f"| {clave} | intersección de dominios ≥ 30 % con los tres | " + " | ".join(["—"] * len(ev["tokenizadores"]))
                 + f" | {it['n']} dominios ({'sí' if it['cumple'] else 'no'}): {', '.join(it['dominios']) or 'ninguno'} |")
    L += ["", "## Efecto del tamaño n (variante `muestreo`; n > 12 repite los 12 registros base)", "",
          "| n | " + " | ".join(f"{t} media / suma / dominios ≥ 30" for t in ev["tokenizadores"]) + " |", "|---:|" + "---|" * len(ev["tokenizadores"])]
    ns = sorted({e["n"] for e in ev["efecto_n"]})
    for n in ns:
        celdas = []
        for t in ev["tokenizadores"]:
            e = next((x for x in ev["efecto_n"] if x["variante"] == "muestreo" and x["n"] == n and x["tokenizador"] == t), None)
            celdas.append("—" if e is None else f"{_fmt(e['media_por_dominio_pct'], 1)} / {_fmt(e['agregado_suma_pct'], 1)} / {e['dominios_ge_umbral']}")
        L.append(f"| {n} | " + " | ".join(celdas) + " |")
    L += ["", "Las cifras para n > 12 provienen de la replicación de los 12 registros base de cada dominio "
          "(`replicacion_de_base`): miden longitud de serialización, no diversidad semántica ni muestras independientes.", ""]
    return "\n".join(L)
