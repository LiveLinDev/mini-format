"""Figura de V3a (matplotlib, texto en español, mismo estilo que las figuras de V1)."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Sequence

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

TINTA, TINTA2, REJILLA = "#0b0b0b", "#52514e", "#e4e3df"
COLOR = {"json_estricto": "#8a8985", "json_parcial_jiter": "#eb6834", "jsonl": "#1baf7a",
         "json_objetos_completos": "#2a78d6", "mini_tolerante": "#e34948", "mini_tolerante_sin_cola": "#e34948"}
ETIQUETA = {"json_estricto": "JSON estricto (json.loads)", "json_parcial_jiter": "JSON parcial (jiter)",
            "jsonl": "JSON Lines", "json_objetos_completos": "JSON, objetos completos (propio)",
            "mini_tolerante": ".mini tolerante", "mini_tolerante_sin_cola": ".mini tolerante, sin última línea (variante)"}
ESTILO = {"mini_tolerante_sin_cola": (0, (4, 2)), "json_objetos_completos": (0, (1, 1.6))}
MARCA = {"json_estricto": "s", "json_parcial_jiter": "^", "jsonl": "D", "json_objetos_completos": "v",
         "mini_tolerante": "o", "mini_tolerante_sin_cola": "o"}


def _ejes(ax) -> None:
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    for s in ("left", "bottom"):
        ax.spines[s].set_color(TINTA2)
    ax.tick_params(colors=TINTA2, labelsize=9)
    ax.grid(True, color=REJILLA, linewidth=0.8)
    ax.set_axisbelow(True)


CORTA = {"json_estricto": "JSON estricto", "json_parcial_jiter": "JSON parcial (jiter)", "jsonl": "JSON Lines",
         "json_objetos_completos": "JSON objetos completos", "mini_tolerante": ".mini tolerante",
         "mini_tolerante_sin_cola": ".mini sin última línea"}
ANCHO = {"json_estricto": 2, "json_parcial_jiter": 5, "jsonl": 3.6, "json_objetos_completos": 2.2,
         "mini_tolerante": 2.4, "mini_tolerante_sin_cola": 1.6}


def dibujar(curvas: Sequence[Dict[str, Any]], resumen: Sequence[Dict[str, Any]], ruta: Path,
            n_documentos: int, dpi: int = 160) -> None:
    orden = [c for c in ETIQUETA if any(f["condicion"] == c for f in curvas)]
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(13.6, 5.4), gridspec_kw={"width_ratios": [1.5, 1]})
    # A: registros recuperados sobre solicitados según el límite de tokens
    for c in orden:
        rs = sorted((f for f in curvas if f["condicion"] == c), key=lambda f: f["k"])
        x = [f["fraccion_limite"] * 100 for f in rs]
        y = [f["recuperados_sobre_solicitados"] * 100 for f in rs]
        lo = [f["rs_ic95_inf"] * 100 if f["rs_ic95_inf"] is not None else v for f, v in zip(rs, y)]
        hi = [f["rs_ic95_sup"] * 100 if f["rs_ic95_sup"] is not None else v for f, v in zip(rs, y)]
        ax1.fill_between(x, lo, hi, color=COLOR[c], alpha=0.10, linewidth=0)
        ax1.plot(x, y, color=COLOR[c], linewidth=ANCHO[c], linestyle=ESTILO.get(c, "-"), alpha=0.85 if c == "json_parcial_jiter" else 1,
                 marker=MARCA[c], markersize=4, label=ETIQUETA[c], zorder=3 if c.startswith("mini") else 2)
    ax1.set_xlim(0, 101)
    ax1.set_ylim(-2, 102)
    ax1.set_xlabel("Límite de tokens de salida (% de los tokens o200k del JSON compacto)", color=TINTA)
    ax1.set_ylabel("Registros recuperados / solicitados (%)", color=TINTA)
    ax1.set_title("Registros completos recuperados según el límite de salida", fontsize=11, color=TINTA, loc="left")
    ax1.legend(fontsize=8, frameon=False, loc="center right", bbox_to_anchor=(1.0, 0.36))
    _ejes(ax1)
    # B: precisión del último registro y cortes con registros espurios
    filas = {r["condicion"]: r for r in resumen if r["estrato"] == "todos"}
    cs = [c for c in orden if c in filas and filas[c]["precision"]["punto"] is not None]
    ys, err_lo, err_hi, etq = [], [], [], []
    for c in cs:
        p = filas[c]["precision"]
        lo = p["ic95_inf"] if p["ic95_inf"] is not None else p["punto"]
        hi = p["ic95_sup"] if p["ic95_sup"] is not None else p["punto"]
        ys.append(p["punto"] * 100)
        err_lo.append(max(0.0, (p["punto"] - lo) * 100))
        err_hi.append(max(0.0, (hi - p["punto"]) * 100))
        pct = f"{filas[c]['fraccion_cortes_con_espurios'] * 100:.1f}".replace(".", ",")
        etq.append(CORTA[c] + "\ncortes con espurio: " + pct + " %")
    pos = list(range(len(cs)))[::-1]
    ax2.barh(pos, ys, height=0.6, color=[COLOR[c] for c in cs], edgecolor="white", linewidth=0.8,
             xerr=[err_lo, err_hi], error_kw={"ecolor": TINTA2, "elinewidth": 1, "capsize": 2})
    ax2.set_yticks(pos)
    ax2.set_yticklabels(etq, fontsize=8, color=TINTA2)
    minimo = min(y - e for y, e in zip(ys, err_lo)) if ys else 90
    ax2.set_xlim(max(0, min(minimo - 1.5, 98)), 100.3)
    ax2.set_xlabel("Precisión = recuperados / emitidos (%), IC 95 % por documento", color=TINTA)
    ax2.set_title("Precisión de lo que emite cada lector", fontsize=11, color=TINTA, loc="left")
    _ejes(ax2)
    ax2.grid(False, axis="y")
    fig.text(0.01, 0.005, f"Datos: {n_documentos} documentos de n = 50 registros (sintéticos, de prueba públicos y un snapshot real). Cortes en tokens o200k "
             "(aproximación para otros proveedores). Procedencia: reproducido_local. Sin modelos. IC 95 % por bootstrap de documentos.",
             fontsize=7.5, color=TINTA2, ha="left", va="bottom")
    fig.tight_layout(rect=(0, 0.03, 1, 1))
    Path(ruta).parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(ruta, dpi=dpi, facecolor="white")
    plt.close(fig)
