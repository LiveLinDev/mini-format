"""V1 — eficiencia en tokens de .mini (ampliado) + sobrecarga de instrucción.

Uso (desde la raíz del repositorio):
    python experiments/v1_tokens/run.py [--tokenizadores o200k_base,cl100k_base,r50k_base]

No llama a ningún modelo ni descarga nada. Pasos:
 1. Reproduce la línea base publicada (benchmark/results/summary_12.csv: n=12,
    protocolo "ciclo", o200k_base) y la compara celda a celda.
 2. 14 dominios × n ∈ {1,5,10,25,50,100,250} × 8 formatos × tokenizadores,
    con dos variantes de datos: "muestreo" (principal, semilla fija) y "ciclo"
    (protocolo original, sensibilidad). Ida y vuelta verificada para .mini
    (minifmt.roundtrip_ok) y para TOON (decodificador oficial).
 3. Ahorro relativo de .mini frente a cada formato: media, mediana, rango e
    IC 95 % bootstrap (re-muestreo de dominios, semilla fija).
 4. Tokens de los bloques de instrucción (.mini y JSON, es/en) y punto de
    equilibrio en tokens por llamada.

Salidas en experiments/v1_tokens/results/ y experiments/v1_tokens/figures/.
"""
from __future__ import annotations

import argparse
import math
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE))

import numpy as np  # noqa: E402

import comun as C  # noqa: E402
import formats  # noqa: E402
import instruccion as INS  # noqa: E402
from minifmt import roundtrip_ok  # noqa: E402

RES = HERE / "results"
FIG = HERE / "figures"
REFERENCIAS = ["json_pretty", "json_compact", "yaml", "xml", "csv", "toon", "toon_flat"]


# --------------------------------------------------------------- 1. línea base
def linea_base(reg, tk):
    publicado = {r["prefix"]: r for r in C.leer_csv(C.ROOT / "benchmark" / "results" / "summary_12.csv")}
    filas, difs = [], 0
    ahorros = {"json_compact": [], "toon": [], "toon_flat": [], "csv": []}
    for p in reg.contracts:
        c = reg.get(p)
        obj = C.generar(p, 12, "ciclo")
        textos = C.serializar_todos([obj], c)[0]
        tok = {f: tk.count(t) for f, (t, _) in textos.items()}
        for f in C.FORMATOS:
            pub = int(publicado[p][f])
            filas.append({"dominio": p, "metrica": f"tokens_{f}", "publicado": pub, "reproducido": tok[f],
                          "coincide": pub == tok[f]})
            difs += pub != tok[f]
        for ref, col in [("json_compact", "mini_vs_json_compact_pct"), ("toon", "mini_vs_toon_pct"),
                         ("toon_flat", "mini_vs_toon_flat_pct"), ("csv", "mini_vs_csv_pct")]:
            rep = round(100 * (1 - tok["mini"] / tok[ref]), 1)
            ahorros[ref].append(100 * (1 - tok["mini"] / tok[ref]))
            filas.append({"dominio": p, "metrica": col, "publicado": float(publicado[p][col]), "reproducido": rep,
                          "coincide": float(publicado[p][col]) == rep})
            difs += float(publicado[p][col]) != rep
    agregado = []
    for ref, xs in ahorros.items():
        pub = float(np.mean([float(publicado[p][f"mini_vs_{ref}_pct"]) for p in publicado]))
        agregado.append({"referencia": ref, "media_publicada_pct": round(pub, 1), "media_reproducida_pct": round(float(np.mean(xs)), 1),
                         "min_pct": round(min(xs), 1), "max_pct": round(max(xs), 1)})
    C.escribir_csv(RES / "linea_base_n12.csv", filas)
    C.escribir_csv(RES / "linea_base_n12_agregado.csv", agregado)
    print(f"[1] línea base: {len(filas)} celdas comparadas, {difs} diferencias")
    for a in agregado:
        print("    ", a)
    return difs


# --------------------------------------------------------------- 2. medición
def medir(reg, toks):
    filas = []
    t0 = time.time()
    for variante in ("muestreo", "ciclo"):
        for p in reg.contracts:
            c = reg.get(p)
            docs = [C.generar(p, n, variante) for n in C.TAMANOS]
            ser = C.serializar_todos(docs, c)
            for obj, n, textos in zip(docs, C.TAMANOS, ser):
                rt_mini = roundtrip_ok(obj, c)
                for f in C.FORMATOS:
                    texto, rt = textos[f]
                    if f == "mini":
                        rt = rt_mini
                    for tname, tk in toks.items():
                        t = tk.count(texto)
                        filas.append({"tokenizador": tname, "variante": variante, "dominio": p, "n": n, "formato": f,
                                      "tokens": t, "bytes": len(texto.encode("utf-8")), "tokens_por_registro": t / n,
                                      "roundtrip_ok": "" if rt is None else bool(rt)})
            print(f"[2] {variante:8s} {p:5s} ({time.time() - t0:5.1f}s)", flush=True)
    C.escribir_csv(RES / "tokens.csv", filas)
    return filas


def indexar(filas):
    return {(r["tokenizador"], r["variante"], r["dominio"], r["n"], r["formato"]): r["tokens"] for r in filas}


def ahorros(reg, toks, T):
    por_dom, resumen = [], []
    for tname in toks:
        for variante in ("muestreo", "ciclo"):
            for n in C.TAMANOS:
                for ref in REFERENCIAS:
                    xs = []
                    for p in reg.contracts:
                        m, r = T[(tname, variante, p, n, "mini")], T[(tname, variante, p, n, ref)]
                        a = 100 * (1 - m / r)
                        xs.append(a)
                        por_dom.append({"tokenizador": tname, "variante": variante, "dominio": p, "n": n, "referencia": ref,
                                        "tokens_mini": m, "tokens_ref": r, "ahorro_pct": a})
                    s = C.resumen(xs)
                    resumen.append({"tokenizador": tname, "variante": variante, "n": n, "referencia": ref, **s})
    C.escribir_csv(RES / "ahorro_por_dominio.csv", por_dom)
    C.escribir_csv(RES / "ahorro_resumen.csv", resumen)
    return resumen


def ajustes(reg, toks, T):
    """Ajuste lineal T(n) = a + b·n por dominio/formato/tokenizador/variante."""
    filas = []
    x = np.array(C.TAMANOS, dtype=float)
    for tname in toks:
        for variante in ("muestreo", "ciclo"):
            for p in reg.contracts:
                for f in C.FORMATOS:
                    y = np.array([T[(tname, variante, p, n, f)] for n in C.TAMANOS], dtype=float)
                    b, a = np.polyfit(x, y, 1)
                    pred = a + b * x
                    r2 = 1 - ((y - pred) ** 2).sum() / ((y - y.mean()) ** 2).sum()
                    marg = (y[-1] - y[-2]) / (x[-1] - x[-2])
                    filas.append({"tokenizador": tname, "variante": variante, "dominio": p, "formato": f,
                                  "intercepto_a": a, "pendiente_b": b, "r2": r2, "marginal_100_250": marg})
    C.escribir_csv(RES / "ajuste_lineal.csv", filas)
    return {(r["tokenizador"], r["variante"], r["dominio"], r["formato"]): r for r in filas}


# --------------------------------------------------------- 3. instrucción
def instrucciones(reg, toks):
    filas = []
    textos = {}
    for p in reg.contracts:
        c = reg.get(p)
        for lang in ("es", "en"):
            bl = INS.bloques(c, lang)
            for nombre, texto in bl.items():
                textos[(p, lang, nombre)] = texto
                for tname, tk in toks.items():
                    filas.append({"tokenizador": tname, "dominio": p, "idioma": lang, "instruccion": nombre,
                                  "tokens": tk.count(texto), "bytes": len(texto.encode("utf-8"))})
    C.escribir_csv(RES / "instruccion_tokens.csv", filas)
    muestras = RES / "instrucciones_muestra"
    muestras.mkdir(parents=True, exist_ok=True)
    for (p, lang, nombre), texto in textos.items():
        if p in ("a", "cls"):
            (muestras / f"{p}_{lang}_{nombre}.txt").write_text(texto + "\n", encoding="utf-8")
    return {(r["tokenizador"], r["dominio"], r["idioma"], r["instruccion"]): r["tokens"] for r in filas}


def n_equilibrio(delta_i, delta_a, delta_b):
    """n tal que ΔO(n) = Δa + Δb·n iguala a ΔI; ≤1 se reporta como 1."""
    if delta_b <= 0:
        return math.inf
    return max(1.0, (delta_i - delta_a) / delta_b)


def equilibrio(reg, toks, T, FIT, I):
    filas, resumen = [], []
    variante = "muestreo"
    for tname in toks:
        for lang in ("es", "en"):
            for im, ij in INS.PARES:
                ns = []
                for p in reg.contracts:
                    dI = I[(tname, p, lang, im)] - I[(tname, p, lang, ij)]
                    fm, fj = FIT[(tname, variante, p, "mini")], FIT[(tname, variante, p, "json_compact")]
                    da, db = fj["intercepto_a"] - fm["intercepto_a"], fj["pendiente_b"] - fm["pendiente_b"]
                    dO = [T[(tname, variante, p, n, "json_compact")] - T[(tname, variante, p, n, "mini")] for n in C.TAMANOS]
                    ne = C.cruce(C.TAMANOS, dO, dI)
                    ns.append(ne)
                    filas.append({"tokenizador": tname, "idioma": lang, "instr_mini": im, "instr_json": ij, "dominio": p,
                                  "tokens_instr_mini": I[(tname, p, lang, im)], "tokens_instr_json": I[(tname, p, lang, ij)],
                                  "delta_instruccion": dI, "ahorro_salida_n1": dO[0], "ahorro_salida_por_registro_ajuste": db,
                                  "n_equilibrio": ne, "n_equilibrio_ajuste_lineal": n_equilibrio(dI, da, db)})
                s = C.resumen(ns)
                resumen.append({"tokenizador": tname, "idioma": lang, "instr_mini": im, "instr_json": ij,
                                "delta_instruccion_media": float(np.mean([f["delta_instruccion"] for f in filas[-len(ns):]])),
                                "n_eq_media": s["media"], "n_eq_mediana": s["mediana"], "n_eq_min": s["min"], "n_eq_max": s["max"]})
    C.escribir_csv(RES / "equilibrio_tokens.csv", filas)
    C.escribir_csv(RES / "equilibrio_tokens_resumen.csv", resumen)
    return filas, resumen


# ------------------------------------------------------------------ figuras
# Paleta categórica de referencia (orden fijo por formato; ver experiments/README.md)
COLOR = {"json_pretty": "#2a78d6", "json_compact": "#eb6834", "yaml": "#1baf7a", "xml": "#eda100",
         "csv": "#e87ba4", "toon": "#008300", "toon_flat": "#4a3aa7", "mini": "#e34948"}
TK_COLOR = {"o200k_base": "#2a78d6", "cl100k_base": "#eb6834", "r50k_base": "#1baf7a"}
TINTA, TINTA2, REJILLA = "#0b0b0b", "#52514e", "#e4e3df"


def _estilo(ax):
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    for s in ("left", "bottom"):
        ax.spines[s].set_color(TINTA2)
    ax.tick_params(colors=TINTA2, labelsize=9)
    ax.grid(True, color=REJILLA, linewidth=0.8)
    ax.set_axisbelow(True)


def _etiquetas_fin(ax, x, ys, textos, log=False, sep=None):
    """Etiquetas directas al final de las líneas, separadas para que no se solapen."""
    tr = (lambda v: math.log10(v)) if log else (lambda v: v)
    inv = (lambda v: 10 ** v) if log else (lambda v: v)
    orden = sorted(range(len(ys)), key=lambda i: tr(ys[i]))
    pos = [tr(ys[i]) for i in orden]
    lo, hi = ax.get_ylim()
    sep = sep if sep is not None else 0.045 * (tr(hi) - tr(lo))
    for j in range(1, len(pos)):
        if pos[j] - pos[j - 1] < sep:
            pos[j] = pos[j - 1] + sep
    for j, i in enumerate(orden):
        ax.annotate(textos[i], (x, ys[i]), xytext=(x * 1.12, inv(pos[j])), textcoords="data", va="center",
                    fontsize=8, color=TINTA, arrowprops=dict(arrowstyle="-", color=TINTA2, linewidth=0.6, shrinkA=0, shrinkB=2))


def figuras(reg, toks, resumen, T, filas_eq, I):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    FIG.mkdir(parents=True, exist_ok=True)
    tk0 = "o200k_base"

    # Fig. 1: ahorro medio vs n
    fig, ax = plt.subplots(figsize=(8.6, 5.2), dpi=150)
    fin = []
    for ref in REFERENCIAS:
        rs = [r for r in resumen if r["tokenizador"] == tk0 and r["variante"] == "muestreo" and r["referencia"] == ref]
        x = [r["n"] for r in rs]
        ax.fill_between(x, [r["ic95_inf"] for r in rs], [r["ic95_sup"] for r in rs], color=COLOR[ref], alpha=0.12, linewidth=0)
        ax.plot(x, [r["media"] for r in rs], color=COLOR[ref], linewidth=2, marker="o", markersize=4, label=C.ETIQUETAS[ref])
        fin.append((rs[-1]["media"], f"{C.ETIQUETAS[ref]} ({rs[-1]['media']:.1f} %)".replace(f"{rs[-1]['media']:.1f}", f"{rs[-1]['media']:.1f}".replace(".", ","))))
    ax.axhline(0, color=TINTA2, linewidth=1)
    ax.set_xscale("log")
    ax.set_xticks(C.TAMANOS)
    ax.set_xticklabels([str(n) for n in C.TAMANOS])
    ax.set_xlim(0.9, 1800)
    _etiquetas_fin(ax, C.TAMANOS[-1], [v for v, _ in fin], [t for _, t in fin])
    ax.set_xlabel("Registros por documento (n, escala logarítmica)", color=TINTA)
    ax.set_ylabel("Ahorro de .mini frente al formato (%)", color=TINTA)
    ax.set_title("Ahorro de tokens de salida de .mini según el tamaño del documento\n(media de 14 dominios, banda = IC 95 % bootstrap; o200k_base)",
                 fontsize=11, color=TINTA, loc="left")
    _estilo(ax)
    ax.legend(fontsize=8, frameon=False, loc="lower right", ncol=2)
    fig.tight_layout()
    fig.savefig(FIG / "fig1_ahorro_vs_n.png")
    plt.close(fig)

    # Fig. 2: tokens por registro vs n
    from matplotlib.ticker import FixedLocator, NullLocator, FuncFormatter
    fig, ax = plt.subplots(figsize=(8.6, 5.2), dpi=150)
    fin = []
    for f in C.FORMATOS:
        ys = [np.mean([T[(tk0, "muestreo", p, n, f)] / n for p in reg.contracts]) for n in C.TAMANOS]
        ax.plot(C.TAMANOS, ys, color=COLOR[f], linewidth=2, marker="o", markersize=4, label=C.ETIQUETAS[f])
        fin.append((ys[-1], f"{C.ETIQUETAS[f]} ({ys[-1]:.1f})".replace(f"{ys[-1]:.1f}", f"{ys[-1]:.1f}".replace(".", ","))))
    ax.set_xscale("log")
    ax.set_yscale("log")
    ax.yaxis.set_major_locator(FixedLocator([40, 50, 60, 80, 100, 150, 200]))
    ax.yaxis.set_minor_locator(NullLocator())
    ax.yaxis.set_major_formatter(FuncFormatter(lambda v, _: f"{v:.0f}"))
    ax.set_xticks(C.TAMANOS)
    ax.set_xticklabels([str(n) for n in C.TAMANOS])
    ax.set_xlim(0.9, 1800)
    _etiquetas_fin(ax, C.TAMANOS[-1], [v for v, _ in fin], [t for _, t in fin], log=True)
    ax.set_xlabel("Registros por documento (n, escala logarítmica)", color=TINTA)
    ax.set_ylabel("Tokens por registro (media de 14 dominios, escala log.)", color=TINTA)
    ax.set_title("Tokens de salida por registro según formato y tamaño (o200k_base)", fontsize=11, color=TINTA, loc="left")
    _estilo(ax)
    ax.legend(fontsize=8, frameon=False, loc="upper center", ncol=2)
    fig.tight_layout()
    fig.savefig(FIG / "fig2_tokens_por_registro.png")
    plt.close(fig)

    # Fig. 3: ahorro por dominio vs JSON compacto a n=100, por tokenizador
    n0 = 100
    doms = sorted(reg.contracts, key=lambda p: 100 * (1 - T[(tk0, "muestreo", p, n0, "mini")] / T[(tk0, "muestreo", p, n0, "json_compact")]))
    fig, ax = plt.subplots(figsize=(8.2, 5.2), dpi=150)
    k = len(toks)
    for j, tname in enumerate(toks):
        ys = [100 * (1 - T[(tname, "muestreo", p, n0, "mini")] / T[(tname, "muestreo", p, n0, "json_compact")]) for p in doms]
        pos = np.arange(len(doms)) + (j - (k - 1) / 2) * 0.26
        ax.barh(pos, ys, height=0.24, color=TK_COLOR.get(tname, "#4a3aa7"), label=tname, edgecolor="white", linewidth=0.8)
    ax.set_yticks(np.arange(len(doms)))
    ax.set_yticklabels(doms)
    ax.set_xlabel("Ahorro de .mini frente a JSON compacto (%)", color=TINTA)
    ax.set_ylabel("Dominio (familia .mini)", color=TINTA)
    ax.set_title(f"Ahorro por dominio y tokenizador (n = {n0} registros)", fontsize=11, color=TINTA, loc="left")
    _estilo(ax)
    ax.grid(axis="y", visible=False)
    ax.legend(fontsize=8, frameon=False, loc="lower right")
    fig.tight_layout()
    fig.savefig(FIG / "fig3_ahorro_por_dominio_n100.png")
    plt.close(fig)

    # Fig. 4: tokens de instrucción por dominio (es, o200k)
    noms = ["mini_spec", "json_schema", "json_ejemplo"]
    etq = {"mini_spec": "Especificación .mini (spec_block)", "json_schema": "JSON Schema del contrato", "json_ejemplo": "Ejemplo JSON (1 registro)"}
    col = {"mini_spec": COLOR["mini"], "json_schema": COLOR["json_compact"], "json_ejemplo": COLOR["json_pretty"]}
    doms2 = sorted(reg.contracts)
    fig, ax = plt.subplots(figsize=(8.2, 4.8), dpi=150)
    for j, nm in enumerate(noms):
        ys = [I[(tk0, p, "es", nm)] for p in doms2]
        ax.bar(np.arange(len(doms2)) + (j - 1) * 0.27, ys, width=0.25, color=col[nm], label=etq[nm], edgecolor="white", linewidth=0.8)
    ax.set_xticks(np.arange(len(doms2)))
    ax.set_xticklabels(doms2)
    ax.set_xlabel("Dominio (familia .mini)", color=TINTA)
    ax.set_ylabel("Tokens de entrada de la instrucción", color=TINTA)
    ax.set_title("Tamaño del bloque de instrucción por dominio (español, o200k_base)", fontsize=11, color=TINTA, loc="left")
    _estilo(ax)
    ax.grid(axis="x", visible=False)
    ax.legend(fontsize=8, frameon=False, loc="upper left")
    fig.tight_layout()
    fig.savefig(FIG / "fig4_instruccion_tokens.png")
    plt.close(fig)

    # Fig. 5: punto de equilibrio por dominio (tokens, o200k, es)
    fig, ax = plt.subplots(figsize=(8.2, 4.8), dpi=150)
    pares = [("mini_spec", "json_schema"), ("mini_spec", "json_ejemplo"), ("mini_spec_ejemplo", "json_ejemplo")]
    colp = [COLOR["json_compact"], COLOR["json_pretty"], COLOR["toon_flat"]]
    for j, (im, ij) in enumerate(pares):
        ys = [next(f["n_equilibrio"] for f in filas_eq if f["tokenizador"] == tk0 and f["idioma"] == "es"
                   and f["instr_mini"] == im and f["instr_json"] == ij and f["dominio"] == p) for p in doms2]
        ax.bar(np.arange(len(doms2)) + (j - 1) * 0.27, ys, width=0.25, color=colp[j], label=f"{im} vs {ij}", edgecolor="white", linewidth=0.8)
    ax.set_xticks(np.arange(len(doms2)))
    ax.set_xticklabels(doms2)
    ax.set_xlabel("Dominio (familia .mini)", color=TINTA)
    ax.set_ylabel("Registros por llamada para compensar (n*)", color=TINTA)
    ax.set_title("Punto de equilibrio en tokens: registros de salida que compensan\nla instrucción adicional de .mini (sin caché; español; o200k_base; n* ≤ 1 se muestra como 1)",
                 fontsize=11, color=TINTA, loc="left")
    _estilo(ax)
    ax.grid(axis="x", visible=False)
    ax.legend(fontsize=8, frameon=False, loc="upper left")
    fig.tight_layout()
    fig.savefig(FIG / "fig5_equilibrio_tokens.png")
    plt.close(fig)
    print(f"[fig] figuras en {FIG}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tokenizadores", default="o200k_base,cl100k_base,r50k_base")
    args = ap.parse_args()
    toks = C.tokenizadores(args.tokenizadores.split(","))
    for n, t in toks.items():
        print(f"tokenizador {n}: backend={t.backend}")
    reg = C.registro()
    RES.mkdir(parents=True, exist_ok=True)
    difs = linea_base(reg, toks["o200k_base"])
    filas = medir(reg, toks)
    malos = [r for r in filas if r["formato"] in ("mini", "toon", "toon_flat") and r["roundtrip_ok"] is False]
    print(f"[2] ida y vuelta fallida: {len(malos)} filas ({sorted({(r['formato'], r['dominio']) for r in malos})})")
    T = indexar(filas)
    resumen = ahorros(reg, toks, T)
    FIT = ajustes(reg, toks, T)
    I = instrucciones(reg, toks)
    filas_eq, res_eq = equilibrio(reg, toks, T, FIT, I)
    figuras(reg, toks, resumen, T, filas_eq, I)
    for r in resumen:
        if r["variante"] == "muestreo" and r["n"] in (1, 100):
            print(f"  {r['tokenizador']:11s} n={r['n']:<3d} vs {r['referencia']:12s} media={r['media']:6.1f} "
                  f"IC95=[{r['ic95_inf']:.1f}, {r['ic95_sup']:.1f}] mediana={r['mediana']:.1f} rango=[{r['min']:.1f}, {r['max']:.1f}]")
    for r in res_eq:
        print("  eq", r)
    if difs:
        print(f"ATENCIÓN: la línea base difiere en {difs} celdas")


if __name__ == "__main__":
    main()
