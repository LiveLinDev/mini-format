"""Análisis de resultados del experimento generativo V2/V3.

    python experiments/generativo/analyze.py --resultados experiments/generativo/resultados/simulado/piloto

Produce en ``<resultados>/analisis/``:

* ``resumen_brazos.csv``        por experimento × tipo de tarea × brazo
* ``resumen_brazo_modelo.csv``  por experimento × tipo × brazo × modelo
* ``resumen_brazo_tarea.csv``   por experimento × tarea × brazo
* ``reparacion.csv``            D frente a D+R (registros ganados, costo en tokens)
* ``v3a_truncamiento.csv``      cortes controlados sobre salidas guardadas de v2
* ``resumen.md``                tablas legibles con IC 95 % de Wilson
* ``fig_*.png``                 figuras en español

Proporciones de registros: denominador = registros esperados + espurios, de modo
que correctos + incorrectos (emparejados y espurios) + perdidos suman 100 %.
Los IC de Wilson tratan los registros como independientes; los registros de una
misma muestra están correlacionados, así que los intervalos por registro son
optimistas.  Los intervalos por muestra (parseable, exacto) no tienen ese sesgo.
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, Iterable, List, Tuple

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import arnes  # noqa: E402,F401
from arnes import tareas as T  # noqa: E402
from arnes.ejecucion import leer_muestras  # noqa: E402
from arnes.estadistica import wilson  # noqa: E402
from arnes.truncamiento import cortes_controlados  # noqa: E402

ORDEN_BRAZOS = ["A", "B", "C", "D", "D+R"]
NOMBRE_BRAZO = {"A": "A · prompt propio", "B": "B · JSON", "C": "C · JSON estructurado", "D": "D · .mini",
                "D+R": "D+R · .mini + reparación"}
# paleta categórica de referencia en orden fijo (azul, naranja, aqua, amarillo)
COLORES = {"correctos": "#2a78d6", "incorrectos_sin_aviso": "#eb6834", "perdidos_detectados": "#1baf7a",
           "perdidos_sin_aviso": "#eda100"}
ETIQUETAS = {"correctos": "Correctos", "incorrectos_sin_aviso": "Incorrectos aceptados sin aviso",
             "perdidos_detectados": "Perdidos con aviso", "perdidos_sin_aviso": "Perdidos sin aviso"}
TINTA, TINTA2, REJILLA = "#0b0b0b", "#52514e", "#e4e3df"


def _orden_brazo(b: str) -> int:
    return ORDEN_BRAZOS.index(b) if b in ORDEN_BRAZOS else 99


def _media(xs: Iterable[Any]) -> float:
    v = [float(x) for x in xs if x is not None]
    return sum(v) / len(v) if v else float("nan")


def agregar(grupo: List[Dict[str, Any]]) -> Dict[str, Any]:
    m = [s["metricas"] for s in grupo]
    n = len(m)
    esperados = sum(x["esperados"] for x in m)
    espurios = sum(x.get("espurios", 0) for x in m)
    den = esperados + espurios
    tot = {k: sum(x[k] for x in m) for k in ("correctos", "incorrectos_sin_aviso", "perdidos_sin_aviso",
                                            "perdidos_detectados")}
    parse = sum(1 for x in m if x["parseable"])
    exacto = sum(1 for x in m if x["exacto"])
    aviso = sum(1 for x in m if x["detectado"])
    trunc = sum(1 for x in m if x.get("truncado"))
    fila: Dict[str, Any] = {"muestras": n, "registros_esperados": esperados, "espurios": espurios}
    for k, v in (("parseable", parse), ("exacto", exacto), ("con_aviso", aviso), ("truncadas", trunc)):
        p, lo, hi = wilson(v, n)
        fila.update({f"{k}_pct": round(100 * p, 2), f"{k}_ic_inf": round(100 * lo, 2), f"{k}_ic_sup": round(100 * hi, 2)})
    for k, v in tot.items():
        p, lo, hi = wilson(min(v, den), den) if den else (float("nan"),) * 3
        fila.update({k: v, f"{k}_pct": round(100 * p, 2), f"{k}_ic_inf": round(100 * lo, 2), f"{k}_ic_sup": round(100 * hi, 2)})
    fila.update({
        "tokens_entrada_media": round(_media(x["tokens_entrada"] for x in m), 1),
        "tokens_salida_media": round(_media(x["tokens_salida"] for x in m), 1),
        "latencia_media_ms": round(_media(x["latencia_ms"] for x in m), 1),
        "llamadas_media": round(_media(x["llamadas"] for x in m), 3),
        "llamadas_reparacion_total": sum(x["llamadas_reparacion"] for x in m),
        "tokens_reparacion_media": round(_media((x["tokens_reparacion_entrada"] or 0) + (x["tokens_reparacion_salida"] or 0) for x in m), 1),
        "costo_total_usd": round(sum(float(s.get("costo_usd") or 0) for s in grupo), 6),
    })
    return fila


def agrupar(muestras: List[Dict[str, Any]], claves: Tuple[str, ...]) -> List[Dict[str, Any]]:
    g: Dict[tuple, List[Dict[str, Any]]] = defaultdict(list)
    for s in muestras:
        g[tuple(s[k] if k != "modelo_completo" else f"{s['proveedor']}:{s['modelo']}" for k in claves)].append(s)
    filas = []
    for k in sorted(g, key=lambda t: tuple(_orden_brazo(x) if c == "brazo" else x for c, x in zip(claves, t))):
        filas.append({**dict(zip(claves, k)), **agregar(g[k])})
    return filas


def escribir_csv(path: Path, filas: List[Dict[str, Any]]) -> None:
    if not filas:
        return
    campos = list(dict.fromkeys(k for f in filas for k in f))
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=campos)
        w.writeheader()
        w.writerows(filas)


def tabla_md(filas: List[Dict[str, Any]], columnas: List[Tuple[str, str]]) -> str:
    L = ["| " + " | ".join(t for _, t in columnas) + " |", "|" + "---|" * len(columnas)]
    for f in filas:
        L.append("| " + " | ".join(str(f.get(k, "")) for k, _ in columnas) + " |")
    return "\n".join(L)


def _ic_txt(f: Dict[str, Any], k: str) -> str:
    return f"{f[k + '_pct']:.1f} [{f[k + '_ic_inf']:.1f}–{f[k + '_ic_sup']:.1f}]"


def reparacion(muestras: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    d = {s["id"]: s for s in muestras if s["brazo"] == "D"}
    g: Dict[tuple, List[tuple]] = defaultdict(list)
    for s in muestras:
        if s["brazo"] != "D+R" or s.get("generacion_de") not in d:
            continue
        g[(s["experimento"], s["tipo_tarea"])].append((d[s["generacion_de"]], s))
    filas = []
    for (exp, tipo), pares in sorted(g.items()):
        ganados = sum(r["metricas"]["correctos"] - b["metricas"]["correctos"] for b, r in pares)
        nuevos_incorrectos = sum(r["metricas"]["incorrectos_sin_aviso"] - b["metricas"]["incorrectos_sin_aviso"] for b, r in pares)
        con_rep = [r for _, r in pares if r["metricas"]["llamadas_reparacion"]]
        tok = sum(r["metricas"]["tokens_reparacion_entrada"] + r["metricas"]["tokens_reparacion_salida"] for _, r in pares)
        tok_sal = sum(r["metricas"]["tokens_reparacion_salida"] for _, r in pares)
        tok_gen = sum(b["metricas"]["tokens_salida"] or 0 for b, _ in pares)
        filas.append({"experimento": exp, "tipo_tarea": tipo, "pares": len(pares), "muestras_reparadas": len(con_rep),
                      "llamadas_reparacion": sum(r["metricas"]["llamadas_reparacion"] for _, r in pares),
                      "registros_correctos_ganados": ganados, "cambio_incorrectos_sin_aviso": nuevos_incorrectos,
                      "exactas_D": sum(1 for b, _ in pares if b["metricas"]["exacto"]),
                      "exactas_DR": sum(1 for _, r in pares if r["metricas"]["exacto"]),
                      "tokens_reparacion_total": tok,
                      "tokens_por_registro_ganado": round(tok / ganados, 1) if ganados > 0 else "",
                      "salida_reparacion_vs_generacion_pct": round(100 * tok_sal / tok_gen, 2) if tok_gen else ""})
    return filas


def resumen_v3a(filas: List[Dict[str, Any]], por_modelo: bool = False) -> List[Dict[str, Any]]:
    g: Dict[tuple, List[Dict[str, Any]]] = defaultdict(list)
    for f in filas:
        k = (f["brazo"], f"{f['proveedor']}:{f['modelo']}") if por_modelo else (f["brazo"],)
        g[k].append(f)
    out = []
    for k in sorted(g, key=lambda t: (_orden_brazo(t[0]),) + t[1:]):
        xs = g[k]
        n = len(xs)
        cero = sum(1 for x in xs if x["cero"])
        rec, ideal = sum(x["recuperados"] for x in xs), sum(x["ideal"] for x in xs)
        p, lo, hi = wilson(cero, n)
        fila = {"brazo": k[0]}
        if por_modelo:
            fila["modelo"] = k[1]
        fila.update({"cortes": n, "recuperados_media": round(rec / n, 2), "ideal_media": round(ideal / n, 2),
                     "eficiencia_media_pct": round(100 * _media(x["eficiencia"] for x in xs), 1),
                     "recuperados_sobre_ideal_pct": round(100 * min(rec, ideal) / ideal, 1) if ideal else "",
                     "cero_recuperados_pct": round(100 * p, 1), "cero_ic_inf": round(100 * lo, 1), "cero_ic_sup": round(100 * hi, 1),
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


def figuras(salida: Path, res_brazos: List[Dict[str, Any]], v3a: List[Dict[str, Any]], simulado: bool) -> List[str]:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    sufijo = "  ·  SIMULADO: valida el arnés, no es un resultado del estudio" if simulado else ""
    hechas = []
    plt.rcParams.update({"font.size": 10, "axes.titlesize": 11, "axes.titlecolor": TINTA, "text.color": TINTA})

    # 1. desenlaces por registro (v2)
    tipos = [t for t in ("extraccion", "generativa") if any(f["experimento"] == "v2" and f["tipo_tarea"] == t for f in res_brazos)]
    if tipos:
        fig, axes = plt.subplots(len(tipos), 1, figsize=(9, 2.2 + 1.9 * len(tipos)), squeeze=False)
        for ax, tipo in zip(axes[:, 0], tipos):
            filas = [f for f in res_brazos if f["experimento"] == "v2" and f["tipo_tarea"] == tipo]
            filas.sort(key=lambda f: -_orden_brazo(f["brazo"]))
            y = list(range(len(filas)))
            izq = [0.0] * len(filas)
            for k in COLORES:
                vals = [f[k + "_pct"] for f in filas]
                ax.barh(y, vals, left=izq, color=COLORES[k], height=0.62, edgecolor="white", linewidth=2,
                        label=ETIQUETAS[k])
                for yi, (l, v) in enumerate(zip(izq, vals)):
                    if v >= 7:
                        ax.text(l + v / 2, yi, f"{v:.0f}", ha="center", va="center", fontsize=8, color="white")
                izq = [a + b for a, b in zip(izq, vals)]
            ax.set_yticks(y)
            ax.set_yticklabels([NOMBRE_BRAZO.get(f["brazo"], f["brazo"]) for f in filas], color=TINTA)
            ax.set_xlim(0, 100)
            ax.set_xlabel("% de registros (esperados + espurios)", color=TINTA2)
            ax.set_title("Tareas de extracción" if tipo == "extraccion" else "Tareas generativas (contra contrato)",
                         loc="left")
            _estilo(ax)
        axes[0, 0].legend(ncol=4, fontsize=8, frameon=False, loc="lower left", bbox_to_anchor=(0, 1.12))
        fig.suptitle("V2 · Desenlace de cada registro por brazo" + sufijo, x=0.01, ha="left", fontsize=11,
                     color=TINTA, y=0.995)
        fig.tight_layout()
        p = salida / "fig_v2_desenlaces_registros.png"
        fig.savefig(p, dpi=160)
        plt.close(fig)
        hechas.append(p.name)

    # 2. incorrectos sin aviso con IC de Wilson
    filas = [f for f in res_brazos if f["experimento"] == "v2"]
    if filas:
        fig, ax = plt.subplots(figsize=(9, 3.6))
        etiquetas = []
        for i, f in enumerate(filas):
            color = COLORES["incorrectos_sin_aviso"] if f["tipo_tarea"] == "extraccion" else "#4a3aa7"
            p_, lo, hi = f["incorrectos_sin_aviso_pct"], f["incorrectos_sin_aviso_ic_inf"], f["incorrectos_sin_aviso_ic_sup"]
            ax.errorbar([p_], [i], xerr=[[p_ - lo], [hi - p_]], fmt="o", color=color, ecolor=color, markersize=8,
                        capsize=3, linewidth=2)
            etiquetas.append(f"{NOMBRE_BRAZO.get(f['brazo'], f['brazo'])} — {'extracción' if f['tipo_tarea'] == 'extraccion' else 'generativa'}")
        ax.set_yticks(range(len(filas)))
        ax.set_yticklabels(etiquetas, fontsize=8, color=TINTA)
        ax.invert_yaxis()
        ax.set_xlabel("% de registros incorrectos aceptados sin aviso (IC 95 % de Wilson)", color=TINTA2)
        ax.set_title("V2 · Corrupción silenciosa por brazo" + sufijo, loc="left")
        _estilo(ax)
        fig.tight_layout()
        p = salida / "fig_v2_incorrectos_sin_aviso.png"
        fig.savefig(p, dpi=160)
        plt.close(fig)
        hechas.append(p.name)

    # 3. tokens medios por muestra (v2, extracción + generativa agregadas por brazo)
    if filas:
        por_brazo: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
        for f in filas:
            por_brazo[f["brazo"]].append(f)
        br = sorted(por_brazo, key=_orden_brazo)

        def pond(b: str, k: str) -> float:
            fs = por_brazo[b]
            return sum(f[k] * f["muestras"] for f in fs) / sum(f["muestras"] for f in fs)
        entrada = [pond(b, "tokens_entrada_media") for b in br]
        salida_t = [pond(b, "tokens_salida_media") for b in br]
        fig, ax = plt.subplots(figsize=(9, 3.4))
        y = range(len(br))
        ax.barh([i + 0.2 for i in y], entrada, height=0.38, color="#2a78d6", edgecolor="white", linewidth=2,
                label="Entrada (incluye reparación)")
        ax.barh([i - 0.2 for i in y], salida_t, height=0.38, color="#eb6834", edgecolor="white", linewidth=2,
                label="Salida (incluye reparación)")
        for i, (a, b) in enumerate(zip(entrada, salida_t)):
            ax.text(a, i + 0.2, f" {a:,.0f}", va="center", fontsize=8, color=TINTA2)
            ax.text(b, i - 0.2, f" {b:,.0f}", va="center", fontsize=8, color=TINTA2)
        ax.set_yticks(list(y))
        ax.set_yticklabels([NOMBRE_BRAZO.get(b, b) for b in br], color=TINTA)
        ax.invert_yaxis()
        ax.set_xlabel("tokens medios por muestra (reportados por el adaptador)", color=TINTA2)
        ax.set_title("V2 · Tokens por muestra" + sufijo, loc="left")
        ax.legend(frameon=False, fontsize=8, loc="lower right")
        _estilo(ax)
        fig.tight_layout()
        p = salida / "fig_v2_tokens.png"
        fig.savefig(p, dpi=160)
        plt.close(fig)
        hechas.append(p.name)

    # 4. recuperación ante truncamiento
    v3b = [f for f in res_brazos if f["experimento"] == "v3b"]
    if v3a or v3b:
        fig, axes = plt.subplots(1, 2, figsize=(10, 3.6))
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
            ax.set_title("V3a · Cortes controlados", loc="left")
            _estilo(ax)
        else:
            axes[0].axis("off")
        if v3b:
            ax = axes[1]
            agg: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
            for f in v3b:
                agg[f["brazo"]].append(f)
            br = sorted(agg, key=_orden_brazo)
            for i, b in enumerate(br):
                c = sum(f["correctos"] for f in agg[b])
                den = sum(f["registros_esperados"] + f["espurios"] for f in agg[b])
                p_, lo, hi = wilson(c, den)
                ax.errorbar([100 * p_], [i], xerr=[[100 * (p_ - lo)], [100 * (hi - p_)]], fmt="o", color="#2a78d6",
                            markersize=8, capsize=3, linewidth=2)
                ax.text(100 * hi, i, f"  {100 * p_:.0f} %", va="center", fontsize=8, color=TINTA2)
            ax.set_yticks(range(len(br)))
            ax.set_yticklabels([NOMBRE_BRAZO.get(b, b) for b in br], color=TINTA)
            ax.invert_yaxis()
            ax.set_xlim(0, 100)
            ax.set_xlabel("% de registros correctos (IC 95 %)", color=TINTA2)
            ax.set_title("V3b · Llamadas con max_tokens reducido", loc="left")
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
def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--resultados", required=True, help="directorio con muestras.jsonl y manifiesto.json")
    ap.add_argument("--sin-figuras", action="store_true")
    args = ap.parse_args(argv)
    res_dir = Path(args.resultados)
    muestras = leer_muestras(res_dir / "muestras.jsonl")
    if not muestras:
        print(f"no hay muestras en {res_dir}", file=sys.stderr)
        return 2
    manifiesto = {}
    if (res_dir / "manifiesto.json").exists():
        manifiesto = json.loads((res_dir / "manifiesto.json").read_text(encoding="utf-8"))
    cfg = manifiesto.get("config", {})
    simulado = any(s.get("simulado") for s in muestras)
    salida = res_dir / "analisis"
    salida.mkdir(parents=True, exist_ok=True)

    res_brazos = agrupar(muestras, ("experimento", "tipo_tarea", "brazo"))
    res_modelo = agrupar(muestras, ("experimento", "tipo_tarea", "brazo", "modelo_completo"))
    res_tarea = agrupar(muestras, ("experimento", "tarea", "brazo"))
    rep = reparacion(muestras)
    v3cfg = (cfg.get("experimentos") or {}).get("v3a") or {}
    tareas = T.cargar(sorted({s["tarea"] for s in muestras}))
    cortes = cortes_controlados(muestras, tareas, cortes=int(v3cfg.get("cortes_por_muestra", 20)),
                                semilla=int(v3cfg.get("semilla", 7)), brazos=tuple(v3cfg.get("brazos", ["A", "B", "C", "D"])))
    v3a = resumen_v3a(cortes)
    v3a_modelo = resumen_v3a(cortes, por_modelo=True)

    escribir_csv(salida / "resumen_brazos.csv", res_brazos)
    escribir_csv(salida / "resumen_brazo_modelo.csv", res_modelo)
    escribir_csv(salida / "resumen_brazo_tarea.csv", res_tarea)
    escribir_csv(salida / "reparacion.csv", rep)
    escribir_csv(salida / "v3a_truncamiento.csv", v3a)
    escribir_csv(salida / "v3a_truncamiento_modelo.csv", v3a_modelo)

    for f in res_brazos + res_modelo:
        for k in ("parseable", "exacto", "correctos", "incorrectos_sin_aviso", "perdidos_sin_aviso", "perdidos_detectados"):
            f[k + "_txt"] = _ic_txt(f, k)
    cols = [("experimento", "exp."), ("tipo_tarea", "tipo"), ("brazo", "brazo"), ("muestras", "muestras"),
            ("parseable_txt", "parseable % [IC95]"), ("exacto_txt", "exacto % [IC95]"),
            ("correctos_txt", "reg. correctos %"), ("incorrectos_sin_aviso_txt", "incorrectos sin aviso %"),
            ("perdidos_sin_aviso_txt", "perdidos sin aviso %"), ("perdidos_detectados_txt", "perdidos con aviso %"),
            ("tokens_entrada_media", "tok. entrada"), ("tokens_salida_media", "tok. salida"),
            ("latencia_media_ms", "latencia ms"), ("llamadas_reparacion_total", "llamadas rep.")]
    L = [f"# Resumen del experimento generativo — {manifiesto.get('nombre', res_dir.name)}", ""]
    if simulado:
        L += ["> **RESULTADOS SIMULADOS.** Estas cifras provienen del adaptador simulado, cuyas tasas de falla son "
              "supuestos del simulador. Solo validan que el arnés funciona de extremo a extremo; **no son resultados "
              "del estudio** y no deben citarse como evidencia sobre ningún formato ni modelo.", ""]
    L += [f"Muestras: {len(muestras)} · commit: `{manifiesto.get('commit', '')[:10]}` · adaptador: "
          f"{manifiesto.get('adaptador', '')}", "",
          "Proporciones de registros sobre (esperados + espurios); IC 95 % de Wilson (por registro: optimistas, ver "
          "docstring de analyze.py).", "", "## Por brazo", "", tabla_md(res_brazos, cols), "",
          "## Por brazo y modelo", "", tabla_md(res_modelo, cols[:3] + [("modelo_completo", "modelo")] + cols[3:]), "",
          "## Reparación selectiva (D frente a D+R)", "",
          tabla_md(rep, [(k, k.replace("_", " ")) for k in (rep[0].keys() if rep else [])]) if rep else "(sin pares D/D+R)", "",
          "## V3a · cortes controlados sobre salidas guardadas", "",
          tabla_md(v3a, [(k, k.replace("_", " ")) for k in (v3a[0].keys() if v3a else [])]) if v3a else "(sin muestras v2)", ""]
    if not args.sin_figuras:
        hechas = figuras(salida, res_brazos, v3a, simulado)
        L += ["## Figuras", ""] + [f"![{h}]({h})" for h in hechas]
    (salida / "resumen.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    print(f"análisis escrito en {salida}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
