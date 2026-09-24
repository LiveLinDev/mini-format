"""V8 · Integración en SIMA: resumen y figura desde datos.json (ejecuciones reales con DeepSeek).

Uso: python experiments/v8_sima/analizar.py
Escribe resumen.json y fig_json_vs_mini.png en esta carpeta.
"""
import json
from pathlib import Path
from statistics import mean

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

AQUI = Path(__file__).resolve().parent
D = json.loads((AQUI / "datos.json").read_text(encoding="utf-8"))
LIMITE = D["limite_salida_tokens"]


def resumen():
    cmp = {}
    for c in D["comparaciones"]:
        g = cmp.setdefault(c["items_pedidos"], [])
        g.append(c)
    comparaciones = {}
    for n, filas in sorted(cmp.items()):
        comparaciones[n] = {
            "corridas": len(filas),
            "salida_mini": [f["mini"]["tokens_salida"] for f in filas],
            "salida_json": [f["json"]["tokens_salida"] for f in filas],
            "entrada_mini": [f["mini"]["tokens_entrada"] for f in filas],
            "entrada_json": [f["json"]["tokens_entrada"] for f in filas],
            "validas_mini": [f["mini"]["validas"] for f in filas],
            "validas_json": [f["json"]["validas"] for f in filas],
            "corte_json": [f["json"]["corte"] for f in filas],
            "ahorro_salida_pct": [round(100 * (1 - f["mini"]["tokens_salida"] / f["json"]["tokens_salida"]), 1) for f in filas],
            "segundos_mini": [f["mini"]["segundos"] for f in filas],
            "segundos_json": [f["json"]["segundos"] for f in filas],
        }
    clases = [c["resumen"] for c in D["clases"]]
    total = lambda k: sum((r.get(k) or 0) for r in clases)  # noqa: E731
    bancos = [(r["tokens"]["mini"], r["tokens"]["json_compacto"]) for r in clases]
    return {
        "comparaciones": comparaciones,
        "clases": {
            "corridas": len(clases),
            "items_pedidos": total("pedidos"),
            "validos_al_llegar": total("recibidos"),
            "lineas_invalidas": total("invalidos"),
            "lineas_reparadas": total("reparados"),
            "validos_finales": total("finales"),
            "llamadas": total("llamadas"),
            "invalidos_aceptados_por_lector_anterior": total("legado_invalidos"),
            "tokens_banco_mini": [b[0] for b in bancos],
            "tokens_banco_json_compacto": [b[1] for b in bancos],
            "ahorro_banco_pct": [round(100 * (1 - m / j), 1) for m, j in bancos],
        },
    }


def figura(r):
    c12, c40 = r["comparaciones"][12], r["comparaciones"][40]
    plt.rcParams.update({"font.family": "serif", "font.size": 7.5})
    fig, (a, b) = plt.subplots(1, 2, figsize=(3.45, 1.85), dpi=300, gridspec_kw={"width_ratios": [1.35, 1]})
    x = [0, 1]
    ancho = 0.36
    mini = [mean(c12["salida_mini"]), mean(c40["salida_mini"])]
    js = [mean(c12["salida_json"]), mean(c40["salida_json"])]
    a.bar([i - ancho / 2 for i in x], mini, ancho, color="#3b3bd6", label=".mini")
    a.bar([i + ancho / 2 for i in x], js, ancho, color="#9a9a9a", hatch="///", edgecolor="white", linewidth=0, label="JSON")
    a.axhline(LIMITE, color="#b91c1c", linestyle="--", linewidth=0.8)
    a.text(-0.55, LIMITE + 90, "output limit (4,000)", color="#b91c1c", ha="left", fontsize=6.3)
    a.text(1 + ancho / 2, js[1] - 380, "cut", ha="center", fontsize=6.5, color="white", fontweight="bold")
    a.set_xticks(x, ["12 items", "40 items"])
    a.set_ylabel("Output tokens")
    a.set_ylim(0, LIMITE * 1.42)
    a.set_title("(a) Output tokens per call", fontsize=7.5)
    a.legend(frameon=False, fontsize=6.5, loc="upper right", ncol=2, handlelength=1.2, columnspacing=0.8)
    for s in ("top", "right"):
        a.spines[s].set_visible(False)
    uso_mini = [mean(c12["validas_mini"]) / 12 * 100, mean(c40["validas_mini"]) / 40 * 100]
    uso_json = [mean(c12["validas_json"]) / 12 * 100, mean(c40["validas_json"]) / 40 * 100]
    b.bar([i - ancho / 2 for i in x], uso_mini, ancho, color="#3b3bd6")
    b.bar([i + ancho / 2 for i in x], uso_json, ancho, color="#9a9a9a", hatch="///", edgecolor="white", linewidth=0)
    b.text(1 + ancho / 2, 3, "0", ha="center", fontsize=6.5)
    b.set_xticks(x, ["12 items", "40 items"])
    b.set_ylabel("Usable items (%)")
    b.set_ylim(0, 112)
    b.set_title("(b) Usable items", fontsize=7.5)
    for s in ("top", "right"):
        b.spines[s].set_visible(False)
    fig.tight_layout(pad=0.3, w_pad=0.8)
    fig.savefig(AQUI / "fig_json_vs_mini.png")


if __name__ == "__main__":
    r = resumen()
    (AQUI / "resumen.json").write_text(json.dumps(r, ensure_ascii=False, indent=1), encoding="utf-8")
    figura(r)
    print(json.dumps(r, ensure_ascii=False, indent=1))
