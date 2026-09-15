"""V4 — modelo de costos de .mini frente a otros formatos.

Uso (desde la raíz del repositorio):
    python experiments/v4_costos/run.py [--tokenizador o200k_base] [--idioma es]

Si faltan los resultados de V1 se ejecuta primero experiments/v1_tokens/run.py.
No llama a ningún modelo: combina los tokens medidos en V1 con los precios de
experiments/v4_costos/precios.json.

Modelo de costo (por dominio d, formato f, modelo m, tamaño de llamada k registros):
    costo_llamada = I_f · p_in_ef + O_f(k) · p_out            (USD / 1e6 tokens)
    costo_1000    = (1000 / k) · costo_llamada
    p_in_ef       = p_in (sin caché) | p_cache (con caché; si no hay precio publicado, p_in)
  * I_f: tokens del bloque de instrucción (solo .mini y JSON; los demás formatos
    se reportan únicamente con costo de salida).
  * El contenido de entrada de la tarea (transcripción, texto a clasificar...) es
    idéntico para todos los formatos y se excluye: los costos son la parte que
    DEPENDE del formato.
  * Escenario con caché = estado estacionario: todas las llamadas leen la
    instrucción de la caché; se ignoran la escritura inicial (1,25× en Anthropic),
    el almacenamiento por hora (Google) y el mínimo de tokens cacheables.
Los costos se promedian sobre los 14 dominios.
"""
from __future__ import annotations

import argparse
import json
import math
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

import numpy as np  # noqa: E402

import comun as C  # noqa: E402

RES = HERE / "results"
FIG = HERE / "figures"
V1 = C.EXP / "v1_tokens" / "results"
TAM_LLAMADA = [1, 10, 25, 100]
VOLUMENES = [10_000, 1_000_000, 100_000_000]
INSTR = {"mini": "mini_spec", "json_compact": "json_schema", "json_pretty": "json_schema"}
PARES = [("mini_spec", "json_schema"), ("mini_spec", "json_ejemplo"), ("mini_spec_ejemplo", "json_schema_ejemplo")]


def cargar_v1():
    if not (V1 / "tokens.csv").exists() or not (V1 / "instruccion_tokens.csv").exists():
        print("Resultados de V1 ausentes: ejecutando experiments/v1_tokens/run.py", flush=True)
        subprocess.run([sys.executable, str(C.EXP / "v1_tokens" / "run.py")], check=True)
    T = {}
    for r in C.leer_csv(V1 / "tokens.csv"):
        if r["variante"] == "muestreo":
            T[(r["tokenizador"], r["dominio"], int(r["n"]), r["formato"])] = int(r["tokens"])
    I = {(r["tokenizador"], r["dominio"], r["idioma"], r["instruccion"]): int(r["tokens"])
         for r in C.leer_csv(V1 / "instruccion_tokens.csv")}
    return T, I


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tokenizador", default="o200k_base")
    ap.add_argument("--idioma", default="es")
    args = ap.parse_args()
    tk, lang = args.tokenizador, args.idioma
    precios = json.loads((HERE / "precios.json").read_text(encoding="utf-8"))
    modelos = [m for m in precios["modelos"] if m.get("verificado")]
    T, I = cargar_v1()
    doms = sorted({d for (_, d, _, _) in T})
    RES.mkdir(parents=True, exist_ok=True)

    costos = []
    for m in modelos:
        for cache in (False, True):
            p_in = m["entrada"]
            p_ef = (m["entrada_cache"] if (cache and m["entrada_cache"] is not None) else p_in)
            for k in TAM_LLAMADA:
                for f in C.FORMATOS:
                    sal, ins = [], []
                    for d in doms:
                        o = T[(tk, d, k, f)]
                        i = I[(tk, d, lang, INSTR[f])] if f in INSTR else 0
                        sal.append(1000 / k * o * m["salida"] / 1e6)
                        ins.append(1000 / k * i * p_ef / 1e6)
                    c_sal, c_ins = float(np.mean(sal)), float(np.mean(ins))
                    costos.append({"proveedor": m["proveedor"], "modelo": m["modelo"], "cache": cache,
                                   "cache_sin_precio_publicado": cache and m["entrada_cache"] is None,
                                   "registros_por_llamada": k, "formato": f, "instruccion": INSTR.get(f, ""),
                                   "costo_salida_1000_usd": c_sal, "costo_instruccion_1000_usd": c_ins,
                                   "costo_total_1000_usd": c_sal + c_ins,
                                   "tokens_exactos": m["tokens_exactos"]})
    C.escribir_csv(RES / "costo_por_1000_registros.csv", costos)
    idx = {(r["modelo"], r["cache"], r["registros_por_llamada"], r["formato"]): r for r in costos}

    anual = []
    for m in modelos:
        for cache in (False, True):
            for k in TAM_LLAMADA:
                mini = idx[(m["modelo"], cache, k, "mini")]
                for ref in C.FORMATOS:
                    if ref == "mini":
                        continue
                    r = idx[(m["modelo"], cache, k, ref)]
                    base = "costo_total_1000_usd" if ref in INSTR else "costo_salida_1000_usd"
                    ahorro_1000 = r[base] - mini[base]
                    fila = {"proveedor": m["proveedor"], "modelo": m["modelo"], "cache": cache, "registros_por_llamada": k,
                            "referencia": ref, "incluye_instruccion": ref in INSTR,
                            "costo_ref_1000_usd": r[base], "costo_mini_1000_usd": mini[base],
                            "ahorro_1000_usd": ahorro_1000, "ahorro_pct": 100 * ahorro_1000 / r[base]}
                    for v in VOLUMENES:
                        fila[f"ahorro_anual_{v}_usd"] = ahorro_1000 * v / 1000
                    anual.append(fila)
    C.escribir_csv(RES / "ahorro_anual.csv", anual)

    # Punto de equilibrio monetario por llamada (registros de salida que compensan ΔI)
    eq = []
    for m in modelos:
        for cache in (False, True):
            p_ef = (m["entrada_cache"] if (cache and m["entrada_cache"] is not None) else m["entrada"])
            for im, ij in PARES:
                ns = []
                for d in doms:
                    dI = I[(tk, d, lang, im)] - I[(tk, d, lang, ij)]
                    dO = [T[(tk, d, n, "json_compact")] - T[(tk, d, n, "mini")] for n in C.TAMANOS]
                    umbral = dI * p_ef / m["salida"]
                    ns.append(C.cruce(C.TAMANOS, dO, umbral))
                eq.append({"proveedor": m["proveedor"], "modelo": m["modelo"], "cache": cache, "instr_mini": im, "instr_json": ij,
                           "precio_entrada_efectivo": p_ef, "precio_salida": m["salida"], "razon_entrada_salida": p_ef / m["salida"],
                           "n_eq_mediana": float(np.median(ns)), "n_eq_min": float(min(ns)), "n_eq_max": float(max(ns)),
                           "n_eq_media": float(np.mean(ns))})
    C.escribir_csv(RES / "equilibrio_dinero.csv", eq)

    # Curva genérica: n* (mediana de dominios) en función de la razón precio_entrada_efectivo / precio_salida
    rhos = np.logspace(np.log10(0.002), 0, 60)
    curva = []
    for im, ij in PARES:
        for rho in rhos:
            ns = []
            for d in doms:
                dI = I[(tk, d, lang, im)] - I[(tk, d, lang, ij)]
                dO = [T[(tk, d, n, "json_compact")] - T[(tk, d, n, "mini")] for n in C.TAMANOS]
                ns.append(C.cruce(C.TAMANOS, dO, dI * rho))
            curva.append({"instr_mini": im, "instr_json": ij, "razon": float(rho), "n_eq_mediana": float(np.median(ns)),
                          "n_eq_max": float(max(ns))})
    C.escribir_csv(RES / "equilibrio_curva_razon.csv", curva)

    figuras(modelos, idx, eq, curva)
    # Resumen en consola: k = 25, sin caché y con caché, vs JSON compacto
    print(f"\nTokenizador {tk}, instrucción en '{lang}', 25 registros por llamada; referencia JSON compacto (+JSON Schema)")
    for r in anual:
        if r["registros_por_llamada"] == 25 and r["referencia"] == "json_compact":
            print(f"  {r['modelo']:24s} cache={str(r['cache']):5s} JSON={r['costo_ref_1000_usd']:.4f} mini={r['costo_mini_1000_usd']:.4f} "
                  f"ahorro={r['ahorro_pct']:.1f}%  anual: 1e4={r['ahorro_anual_10000_usd']:.2f} 1e6={r['ahorro_anual_1000000_usd']:.2f} "
                  f"1e8={r['ahorro_anual_100000000_usd']:.0f}")
    for r in eq:
        if r["instr_json"] == "json_schema" or r["instr_json"] == "json_ejemplo":
            print(f"  eq {r['modelo']:24s} cache={str(r['cache']):5s} {r['instr_mini']} vs {r['instr_json']}: "
                  f"mediana n*={r['n_eq_mediana']:.2f} [{r['n_eq_min']:.2f}, {r['n_eq_max']:.2f}]")


def figuras(modelos, idx, eq, curva):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    FIG.mkdir(parents=True, exist_ok=True)
    TINTA, TINTA2, REJ = "#0b0b0b", "#52514e", "#e4e3df"
    COL = {"json_compact": "#eb6834", "mini": "#e34948", "json_schema": "#2a78d6", "json_ejemplo": "#1baf7a",
           "json_schema_ejemplo": "#4a3aa7"}

    def estilo(ax):
        for s in ("top", "right"):
            ax.spines[s].set_visible(False)
        for s in ("left", "bottom"):
            ax.spines[s].set_color(TINTA2)
        ax.tick_params(colors=TINTA2, labelsize=9)
        ax.grid(True, color=REJ, linewidth=0.8)
        ax.set_axisbelow(True)

    k = 25
    orden = sorted(modelos, key=lambda m: -idx[(m["modelo"], False, k, "json_compact")]["costo_total_1000_usd"])
    nombres = [f"{m['modelo']} ({m['proveedor']})" for m in orden]
    y = np.arange(len(orden))
    from matplotlib.ticker import FixedLocator, FuncFormatter, NullLocator
    fig, ax = plt.subplots(figsize=(8.6, 5.8), dpi=150)
    series = [("mini", ".mini + spec_block", -0.19), ("json_compact", "JSON compacto + JSON Schema", 0.19)]
    for key, etq, off in series:  # .mini arriba en cada par, igual que en la leyenda
        vals = [idx[(m["modelo"], False, k, key)]["costo_total_1000_usd"] for m in orden]
        ax.barh(y + off, vals, height=0.36, color=COL[key], label=etq, edgecolor="white", linewidth=0.8)
    ax.invert_yaxis()
    ax.set_xscale("log")
    ax.xaxis.set_major_locator(FixedLocator([0.01, 0.03, 0.1, 0.3, 1, 3]))
    ax.xaxis.set_minor_locator(NullLocator())
    ax.xaxis.set_major_formatter(FuncFormatter(lambda v, _: f"{v:g}".replace(".", ",")))
    ax.set_yticks(y)
    ax.set_yticklabels(nombres, fontsize=8)
    ax.set_xlabel("USD por cada 1 000 registros generados (escala logarítmica)", color=TINTA)
    ax.set_title("Costo dependiente del formato por 1 000 registros\n(25 registros/llamada, sin caché, instrucción en español, o200k_base)",
                 fontsize=11, color=TINTA, loc="left")
    estilo(ax)
    ax.grid(axis="y", visible=False)
    ax.legend(fontsize=8, frameon=False, loc="lower right")
    fig.tight_layout()
    fig.savefig(FIG / "fig1_costo_1000_registros.png")
    plt.close(fig)

    # Fig. 2: ahorro anual a 1 millón de registros/año
    fig, ax = plt.subplots(figsize=(8.6, 5.8), dpi=150)
    for j, cache in enumerate((False, True)):
        vals = [(idx[(m["modelo"], cache, k, "json_compact")]["costo_total_1000_usd"] - idx[(m["modelo"], cache, k, "mini")]["costo_total_1000_usd"]) * 1000
                for m in orden]
        ax.barh(y + (j - 0.5) * 0.38, vals, height=0.36, color=("#2a78d6" if not cache else "#1baf7a"),
                label=("sin caché de prompt" if not cache else "con caché de prompt (estado estacionario)"), edgecolor="white", linewidth=0.8)
        for yy, v in zip(y + (j - 0.5) * 0.38, vals):
            ax.annotate(f"{v:,.0f}", (v, yy), xytext=(3, 0), textcoords="offset points", va="center", fontsize=7, color=TINTA2)
    ax.set_yticks(y)
    ax.set_yticklabels(nombres, fontsize=8)
    ax.set_xlabel("Ahorro anual de .mini frente a JSON compacto (USD, 1 millón de registros/año)", color=TINTA)
    ax.set_title("Ahorro anual estimado con 1 millón de registros al año\n(25 registros/llamada; tokens o200k_base, aproximados fuera de OpenAI/gpt-oss)",
                 fontsize=11, color=TINTA, loc="left")
    ax.invert_yaxis()
    estilo(ax)
    ax.grid(axis="y", visible=False)
    ax.legend(fontsize=8, frameon=False, loc="lower right")
    fig.tight_layout()
    fig.savefig(FIG / "fig2_ahorro_anual_1M.png")
    plt.close(fig)

    # Fig. 3: punto de equilibrio en función de la razón de precios
    fig, ax = plt.subplots(figsize=(8.4, 5.0), dpi=150)
    for im, ij in PARES:
        cs = [c for c in curva if c["instr_mini"] == im and c["instr_json"] == ij]
        ax.plot([c["razon"] for c in cs], [c["n_eq_mediana"] for c in cs], color=COL[ij], linewidth=2, label=f"{im} vs {ij}")
    pts = [e for e in eq if e["instr_mini"] == "mini_spec" and e["instr_json"] == "json_schema"]
    ax.scatter([e["razon_entrada_salida"] for e in pts], [e["n_eq_mediana"] for e in pts], s=36, color="#0b0b0b",
               edgecolor="white", linewidth=1.5, zorder=3, label="modelos (mini_spec vs json_schema)")
    ax.set_xscale("log")
    ax.set_xlabel("Razón precio de entrada efectivo / precio de salida (escala log.)", color=TINTA)
    ax.set_ylabel("Registros por llamada para compensar (mediana de 14 dominios)", color=TINTA)
    ax.set_title("Punto de equilibrio monetario de la instrucción .mini\n(razón 1 = equilibrio en tokens; puntos = modelos con y sin caché; n* ≤ 1 se muestra como 1)",
                 fontsize=11, color=TINTA, loc="left")
    estilo(ax)
    ax.legend(fontsize=8, frameon=False, loc="upper left")
    fig.tight_layout()
    fig.savefig(FIG / "fig3_equilibrio_vs_razon_precios.png")
    plt.close(fig)
    print(f"[fig] figuras en {FIG}")


if __name__ == "__main__":
    main()
