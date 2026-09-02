"""Generate every figure used by the paper and the thesis from the CSV results.

    python benchmark/make_figures.py
Writes PNG (300 dpi) + SVG + PDF to benchmark/figures/.
Palette: validated categorical order (blue, orange, aqua, yellow, magenta,
green, violet, red) assigned by entity, never by rank; direct labels on bars.
"""
from __future__ import annotations

import csv
import json
import sys
from collections import defaultdict
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import os
LANG = os.environ.get("MINI_FIG_LANG", "en")
TR_ES = {'content only ({payload} tokens)': 'solo contenido ({payload} tokens)', 'output tokens (o200k_base), 12 assessment items': 'tokens de salida (o200k_base), 12 ítems', 'tokens, % of JSON compact (lower is better)': 'tokens, % de JSON compacto (menor es mejor)', 'Token cost across 14 domains (n = 12 records, o200k_base)': 'Costo en tokens en 14 dominios (n = 12 registros, o200k_base)', 'records (assessment items)': 'registros (ítems de evaluación)', 'output tokens (o200k_base)': 'tokens de salida (o200k_base)', 'structural overhead = (tokens − content) / tokens, % (14 domains)': 'sobrecarga estructural = (tokens − contenido) / tokens, % (14 dominios)', '.mini token saving, %\n(mean of 14 domains)': 'ahorro de tokens de .mini, %\n(media de 14 dominios)', 'USD per month for 360 000 records\n(1 000 banks × 12 items × 30 days; $10 per 1M output tokens)': 'USD al mes para 360 000 registros\n(1 000 bancos × 12 ítems × 30 días; 10 USD por millón de tokens de salida)', 'round-trip success, %': 'éxito de ida y vuelta, %', 'v0 · quotes only\nDeepSeek-V3\nn = 30': 'v0 · solo comillas\nDeepSeek-V3\nn = 30', 'v0 · quotes only\nDeepSeek-R1\nn = 20': 'v0 · solo comillas\nDeepSeek-R1\nn = 20', 'v1 draft\nbackslash only\nHaiku 4.5, n = 6': 'v1 borrador\nsolo escapes\nHaiku 4.5, n = 6', 'v1.0 · quotes or\nescapes + count key\nHaiku 4.5, n = 10': 'v1.0 · comillas o\nescapes + clave k\nHaiku 4.5, n = 10', '.mini round-trip success, %': 'éxito de ida y vuelta de .mini, %', 'round-trip success, % (n = 6)': 'éxito de ida y vuelta, % (n = 6)', 'E2 · generation from the contract alone': 'E2 · generación desde el contrato', 'parsers passing all fixtures, % (n = 2)': 'analizadores correctos, % (n = 2)', 'E3 · parser written from the spec block': 'E3 · analizador desde el bloque', '.mini (spec 640 tok)': '.mini (spec 640 tok)', 'records generated in one call': 'registros generados en una llamada', 'total tokens = specification + output': 'tokens totales = especificación + salida', 'Break-even including the cost of teaching the format': 'Punto de equilibrio incluyendo el costo de enseñar el formato', 'complete records recovered\nafter random truncation, %': 'registros completos recuperados\ntras truncamiento aleatorio, %', 'CONTRACT\ncontract.json\nprefix · header keys\ncore fields · extensions\ntypes · arity · markers': 'CONTRATO\ncontract.json\nprefijo · claves cabecera\nnúcleo · extensiones\ntipos · aridad · marcas', 'spec block\n(mini prompt)': 'bloque de spec\n(mini prompt)', 'parser\n(interpreted)': 'analizador\n(interpretado)', 'serializer\n(interpreted)': 'serializador\n(interpretado)', 'fork checker\nI1–I5': 'verificador de\nbifurcaciones I1–I5', 'generative model\n(any provider)': 'modelo generativo\n(todo proveedor)', '.mini document\n(one line per record)': 'documento .mini\n(1 línea/registro)', 'canonical JSON\n(application object)': 'JSON canónico\n(objeto de la app)', 'fixtures\nvalid · escaping · bad': 'fixtures\nválido·escapes·malos', 'child fork\nparent core +\nappended tail': 'bifurcación hija\nnúcleo padre +\ncola nueva', 'fork: new prefix · inherited fields unchanged · new fields appended': 'bifurcación: prefijo nuevo · campos heredados intactos · campos nuevos al final', 'registry\nunique prefixes\nlineage · CI\n(mini check-forks)': 'registro\nprefijos únicos\nlinaje · CI\n(mini check-forks)', 'A .mini family: the contract is data; every tool is derived from it': 'Una familia .mini: el contrato es un dato; toda herramienta se deriva de él', 'Lecture audio /\ntranscript': 'audio de clase /\ntranscripción', 'Whisper ASR\n(local)': 'Whisper ASR\n(local)', 'LLM generation\nin .mini-a': 'generación LLM\nen .mini-a', 'parse + validate\n(E01–E13), repair': 'parse + validar\n(E01–E13)\ny reparar', 'canonical JSON\n→ Django ORM': 'JSON canónico\n→ ORM Django', 'IRT 3PL / CAT\nquiz · cards · map': 'IRT 3PL / CAT\nquiz · tarjetas\n· mapa', 'SIMA case study: where .mini sits in the microlearning pipeline': 'Caso SIMA: dónde se sitúa .mini en el pipeline de microaprendizaje', '−38 % tokens vs\nJSON compact per bank': '−38 % tokens vs\nJSON por banco', '22/53 incoherent items\ncaught before persistence': '22/53 ítems incoherentes\ndetectados antes', 'θ estimate, SE stop rule,\nexposure control': 'estimación de θ, parada por EE,\ncontrol de exposición', 'education': 'educación', 'software / ops': 'software / operaciones', 'NLP / commerce': 'PLN / comercio', 'Each box is a contract shipped with fixtures and a README; the number is core fields + extension fields. ': 'Cada caja es un contrato publicado con fixtures y README; el número es campos del núcleo + extensiones. ', 'q is a fork of a (same core, +3 trailing fields). All 14 pass `mini check-forks` and round-trip in both implementations.': 'q es bifurcación de a (mismo núcleo, +3 campos finales). Las 14 pasan `mini check-forks` e ida y vuelta en ambas implementaciones.', 'marginal tokens per record\n(slope n = 100 → 500)': 'tokens marginales por registro\n(pendiente n = 100 → 500)', '(unseen fork)': '(no vista)', 'data': 'datos', 'format': 'formato', 'TOON (as-is)': 'TOON (tal cual)', 'JSON compact': 'JSON compacto', 'JSON pretty': 'JSON indentado'}
def _(text):
    return TR_ES.get(text, text) if LANG == "es" else text
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib import patches  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
RES = ROOT / "benchmark" / "results"
GEN = ROOT / "generative" / "results"
OUT = ROOT / "benchmark" / ("figures_es" if LANG == "es" else "figures")
OUT.mkdir(parents=True, exist_ok=True)

FMT_ORDER = ["mini", "toon_flat", "toon", "csv", "json_compact", "yaml", "xml", "json_pretty"]
LABEL = {"mini": ".mini", "toon_flat": "TOON (tabular)", "toon": _("TOON (as-is)"), "csv": "CSV", "json_compact": _("JSON compact"),
         "yaml": "YAML", "xml": "XML", "json_pretty": _("JSON pretty"), "json": _("JSON compact")}
COLOR = {"mini": "#2a78d6", "toon_flat": "#eb6834", "toon": "#1baf7a", "csv": "#eda100", "json_compact": "#e87ba4",
         "yaml": "#008300", "xml": "#4a3aa7", "json_pretty": "#e34948", "json": "#e87ba4", "payload": "#52514e"}
INK, INK2, GRID = "#0b0b0b", "#52514e", "#e6e6e3"

plt.rcParams.update({
    "font.family": "DejaVu Sans", "font.size": 8, "axes.edgecolor": INK2, "axes.linewidth": 0.6,
    "axes.spines.top": False, "axes.spines.right": False, "axes.titlesize": 9, "axes.titleweight": "bold",
    "axes.labelsize": 8, "xtick.labelsize": 7.5, "ytick.labelsize": 7.5, "legend.fontsize": 7, "legend.frameon": False,
    "figure.dpi": 120, "savefig.dpi": 300, "axes.grid": True, "grid.color": GRID, "grid.linewidth": 0.5, "axes.axisbelow": True,
})
COL_W, DBL_W = 3.45, 7.1  # IEEE column widths (in)


def save(fig, name):
    for ext in ("png", "svg", "pdf"):
        fig.savefig(OUT / f"{name}.{ext}", bbox_inches="tight", facecolor="white")
    plt.close(fig)
    print("wrote", name)


def read_csv(path):
    with open(path, encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


TOK = read_csv(RES / "tokens.csv")
SUMM = read_csv(RES / "summary_12.csv")
for r in TOK:
    r["n"] = int(r["n"]); r["tokens"] = int(r["tokens"]); r["payload_tokens"] = int(r["payload_tokens"]); r["bytes"] = int(r["bytes"])


def tokens(prefix, fmt, n=12, tokenizer="o200k_base"):
    return next(r for r in TOK if r["prefix"] == prefix and r["format"] == fmt and r["n"] == n and r["tokenizer"] == tokenizer)


# ---------------------------------------------------------------- Fig 1: tokens per format, assessment bank
def fig1():
    fig, ax = plt.subplots(figsize=(COL_W, 2.4))
    vals = [tokens("a", f)["tokens"] for f in FMT_ORDER]
    payload = tokens("a", "mini")["payload_tokens"]
    y = range(len(FMT_ORDER))
    ax.barh(list(y), vals, color=[COLOR[f] for f in FMT_ORDER], height=0.66)
    for i, v in enumerate(vals):
        ax.text(v + 25, i, f"{v:,}", va="center", fontsize=7, color=INK)
    ax.axvline(payload, color=COLOR["payload"], ls=(0, (3, 3)), lw=1)
    ax.text(payload + 15, -0.45, _("content only ({payload} tokens)").format(payload=payload), fontsize=6.5, color=INK2, va="bottom")
    ax.set_yticks(list(y)); ax.set_yticklabels([LABEL[f] for f in FMT_ORDER]); ax.invert_yaxis()
    ax.set_xlabel(_("output tokens (o200k_base), 12 assessment items")); ax.grid(axis="y", visible=False)
    ax.set_xlim(0, max(vals) * 1.18)
    save(fig, "fig01_tokens_assessment")


# ---------------------------------------------------------------- Fig 2: multi-domain heatmap (relative to JSON compact)
def fig2():
    prefixes = ["a", "q", "card", "sum", "map", "r", "s", "code", "tc", "us", "log", "ner", "cat", "cls"]
    fmts = FMT_ORDER
    import numpy as np
    M = np.zeros((len(prefixes), len(fmts)))
    for i, p in enumerate(prefixes):
        base = tokens(p, "json_compact")["tokens"]
        for j, f in enumerate(fmts):
            M[i, j] = 100 * tokens(p, f)["tokens"] / base
    fig, ax = plt.subplots(figsize=(DBL_W, 3.6))
    im = ax.imshow(M, cmap="Blues_r", vmin=40, vmax=200, aspect="auto")
    ax.set_xticks(range(len(fmts))); ax.set_xticklabels([LABEL[f] for f in fmts], rotation=25, ha="right")
    ax.set_yticks(range(len(prefixes))); ax.set_yticklabels([f".mini-{p}" for p in prefixes])
    for i in range(len(prefixes)):
        for j in range(len(fmts)):
            v = M[i, j]
            ax.text(j, i, f"{v:.0f}", ha="center", va="center", fontsize=6.5, color="white" if v < 110 else INK)
    ax.grid(False)
    cb = fig.colorbar(im, ax=ax, fraction=0.025, pad=0.02); cb.set_label(_("tokens, % of JSON compact (lower is better)"), fontsize=7); cb.ax.tick_params(labelsize=6.5)
    ax.set_title(_("Token cost across 14 domains (n = 12 records, o200k_base)"))
    save(fig, "fig02_multidomain_heatmap")


# ---------------------------------------------------------------- Fig 3: scaling
def fig3():
    fig, ax = plt.subplots(figsize=(COL_W, 2.5))
    sizes = sorted({r["n"] for r in TOK})
    for f in FMT_ORDER:
        ys = [tokens("a", f, n)["tokens"] for n in sizes]
        ax.plot(sizes, ys, color=COLOR[f], lw=1.6, marker="o", ms=3, label=LABEL[f])
    ax.set_xscale("log"); ax.set_yscale("log")
    ax.set_xlabel(_("records (assessment items)")); ax.set_ylabel(_("output tokens (o200k_base)"))
    ax.set_xticks(sizes); ax.set_xticklabels([str(s) for s in sizes])
    ax.legend(ncol=2, loc="upper left")
    save(fig, "fig03_scaling")


# ---------------------------------------------------------------- Fig 4: structural overhead
def fig4():
    prefixes = sorted({r["prefix"] for r in TOK})
    fig, ax = plt.subplots(figsize=(COL_W, 2.4))
    data = []
    for f in FMT_ORDER:
        ovh = [100 * (1 - tokens(p, f)["payload_tokens"] / tokens(p, f)["tokens"]) for p in prefixes]
        data.append(ovh)
    bp = ax.boxplot(data, vert=False, widths=0.55, patch_artist=True, showfliers=True,
                    medianprops=dict(color=INK, lw=1), whiskerprops=dict(color=INK2, lw=0.8), capprops=dict(color=INK2, lw=0.8),
                    flierprops=dict(marker="o", ms=2.5, mfc=INK2, mec=INK2))
    for patch, f in zip(bp["boxes"], FMT_ORDER):
        patch.set_facecolor(COLOR[f]); patch.set_alpha(0.85); patch.set_edgecolor("white")
    ax.set_yticks(range(1, len(FMT_ORDER) + 1)); ax.set_yticklabels([LABEL[f] for f in FMT_ORDER]); ax.invert_yaxis()
    ax.set_xlabel(_("structural overhead = (tokens − content) / tokens, % (14 domains)"))
    ax.grid(axis="y", visible=False)
    save(fig, "fig04_overhead")


# ---------------------------------------------------------------- Fig 5: tokenizer robustness
def fig5():
    prefixes = sorted({r["prefix"] for r in TOK})
    fig, ax = plt.subplots(figsize=(COL_W, 2.3))
    import numpy as np
    x = np.arange(len(FMT_ORDER) - 1)
    for k, (tkz, hatch) in enumerate([("o200k_base", None), ("cl100k_base", "////")]):
        vals = []
        for f in FMT_ORDER[1:]:
            sav = [100 * (1 - tokens(p, "mini", 12, tkz)["tokens"] / tokens(p, f, 12, tkz)["tokens"]) for p in prefixes]
            vals.append(sum(sav) / len(sav))
        bars = ax.bar(x + (k - 0.5) * 0.38, vals, width=0.36, color=[COLOR[f] for f in FMT_ORDER[1:]], hatch=hatch, edgecolor="white", lw=0.5,
                      label=tkz)
        for b, v in zip(bars, vals):
            ax.text(b.get_x() + b.get_width() / 2, v + 0.8, f"{v:.0f}", ha="center", fontsize=6, color=INK)
    ax.set_xticks(x); ax.set_xticklabels([LABEL[f] for f in FMT_ORDER[1:]], rotation=25, ha="right")
    ax.set_ylabel(_(".mini token saving, %\n(mean of 14 domains)"))
    ax.set_ylim(-12, 78)
    ax.legend(handles=[patches.Patch(facecolor="#bbbbbb", label="o200k_base (GPT-4o family)"),
                       patches.Patch(facecolor="#bbbbbb", hatch="////", label="cl100k_base (GPT-4 family)")], loc="upper left", fontsize=6)
    ax.grid(axis="x", visible=False)
    save(fig, "fig05_tokenizers")


# ---------------------------------------------------------------- Fig 6: cost projection
def fig6():
    fig, ax = plt.subplots(figsize=(COL_W, 2.2))
    per_rec = {}
    for f in FMT_ORDER:
        per_rec[f] = (tokens("a", f, 500)["tokens"] - tokens("a", f, 100)["tokens"]) / 400
    records_per_month = 1000 * 12 * 30  # 1,000 banks of 12 items per day
    price = 10.0  # USD per 1M output tokens (normalised assumption)
    costs = {f: per_rec[f] * records_per_month / 1e6 * price for f in FMT_ORDER}
    vals = [costs[f] for f in FMT_ORDER]
    ax.barh(range(len(FMT_ORDER)), vals, color=[COLOR[f] for f in FMT_ORDER], height=0.66)
    for i, v in enumerate(vals):
        ax.text(v + 4, i, f"${v:,.0f}", va="center", fontsize=7)
    ax.set_yticks(range(len(FMT_ORDER))); ax.set_yticklabels([LABEL[f] for f in FMT_ORDER]); ax.invert_yaxis()
    ax.set_xlabel(_("USD per month for 360 000 records\n(1 000 banks × 12 items × 30 days; $10 per 1M output tokens)"))
    ax.set_xlim(0, max(vals) * 1.15); ax.grid(axis="y", visible=False)
    save(fig, "fig06_cost")
    return costs


# ---------------------------------------------------------------- Fig 7: generative validation E1
def fig7():
    rows = read_csv(GEN / "e1_summary.csv")
    models = ["haiku", "sonnet", "opus"]
    mlabel = {"haiku": "Claude Haiku 4.5", "sonnet": "Claude Sonnet 5", "opus": "Claude Opus 5"}
    fmts = ["mini", "toon", "csv", "json", "yaml", "xml"]
    fig, axes = plt.subplots(1, 3, figsize=(DBL_W, 2.2), sharey=True)
    for ax, m in zip(axes, models):
        vals = []
        for f in fmts:
            r = next((x for x in rows if x["model"] == m and x["format"] == f), None)
            vals.append(float(r["round_trip_pct"]) if r else 0)
        bars = ax.bar(range(len(fmts)), vals, color=[COLOR[f if f != "toon" else "toon_flat"] for f in fmts], width=0.7, edgecolor="white")
        n = next((x["n"] for x in rows if x["model"] == m), "?")
        for b, v in zip(bars, vals):
            ax.text(b.get_x() + b.get_width() / 2, v + 2, f"{v:.0f}", ha="center", fontsize=6.5)
        ax.set_xticks(range(len(fmts))); ax.set_xticklabels([LABEL.get(f, f) if f != "toon" else "TOON" for f in fmts], rotation=30, ha="right")
        ax.set_title(f"{mlabel[m].replace('Claude ', '')}  (n = {n}/" + _("format") + ")", fontsize=7.5); ax.set_ylim(0, 112); ax.grid(axis="x", visible=False)
    axes[0].set_ylabel(_("round-trip success, %"))
    save(fig, "fig07_generative_e1")


# ---------------------------------------------------------------- Fig 8: ablation
def fig8():
    rows = read_csv(GEN / "ablation.csv")
    groups = defaultdict(list)
    for r in rows:
        groups[r["spec"]].append(r["round_trip"] == "True")
    labels = [_("v0 · quotes only\nDeepSeek-V3\nn = 30"), _("v0 · quotes only\nDeepSeek-R1\nn = 20"),
              _("v1 draft\nbackslash only\nHaiku 4.5, n = 6"), _("v1.0 · quotes or\nescapes + count key\nHaiku 4.5, n = 10")]
    vals = [80.0, 100.0]
    for spec in ["v1-draft (backslash only)", "v1.0 (quotes or escapes + count key)"]:
        g = groups[spec]; vals.append(100 * sum(g) / len(g))
    fig, ax = plt.subplots(figsize=(COL_W, 2.4))
    cols = ["#9a9a97", "#9a9a97", "#eb6834", "#2a78d6"]
    bars = ax.bar(range(4), vals, color=cols, width=0.62, edgecolor="white")
    for b, v in zip(bars, vals):
        ax.text(b.get_x() + b.get_width() / 2, v + 2, f"{v:.0f}%", ha="center", fontsize=7)
    ax.set_xticks(range(4)); ax.set_xticklabels(labels, fontsize=5.8)
    ax.set_ylabel(_(".mini round-trip success, %")); ax.set_ylim(0, 115); ax.grid(axis="x", visible=False)
    save(fig, "fig08_ablation")


# ---------------------------------------------------------------- Fig 9: E2 + E3
def fig9():
    e2 = read_csv(GEN / "e2_summary.csv")
    e3 = read_csv(GEN / "e3_samples.csv")
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(DBL_W, 2.2))
    prefixes = ["tc", "log", "cls"]
    import numpy as np
    x = np.arange(len(prefixes))
    for k, m in enumerate(["haiku", "sonnet"]):
        vals = [float(next(r["round_trip_pct"] for r in e2 if r["model"] == m and r["prefix"] == p)) for p in prefixes]
        bars = ax1.bar(x + (k - 0.5) * 0.36, vals, width=0.34, color=["#2a78d6", "#1baf7a"][k], edgecolor="white", label={"haiku": "Haiku 4.5", "sonnet": "Sonnet 5"}[m])
        for b, v in zip(bars, vals):
            ax1.text(b.get_x() + b.get_width() / 2, v + 2, f"{v:.0f}", ha="center", fontsize=6.5)
    ax1.set_xticks(x); ax1.set_xticklabels([f".mini-{p}\n" + _("(unseen fork)") for p in prefixes]); ax1.set_ylim(0, 115)
    ax1.set_ylim(0, 135); ax1.set_ylabel(_("round-trip success, % (n = 6)")); ax1.set_title(_("E2 · generation from the contract alone")); ax1.legend(loc="upper right", ncol=2); ax1.grid(axis="x", visible=False)
    prefixes3 = ["a", "tc", "log", "cls"]
    for k, m in enumerate(["sonnet", "opus"]):
        vals = []
        for p in prefixes3:
            g = [r for r in e3 if r["model"] == m and r["prefix"] == p]
            vals.append(100 * sum(r["all_ok"] == "True" for r in g) / max(1, len(g)))
        bars = ax2.bar(np.arange(4) + (k - 0.5) * 0.36, vals, width=0.34, color=["#1baf7a", "#4a3aa7"][k], edgecolor="white", label={"sonnet": "Sonnet 5", "opus": "Opus 5"}[m])
        for b, v in zip(bars, vals):
            ax2.text(b.get_x() + b.get_width() / 2, v + 2, f"{v:.0f}", ha="center", fontsize=6.5)
    ax2.set_xticks(range(4)); ax2.set_xticklabels([f".mini-{p}" for p in prefixes3]); ax2.set_ylim(0, 115)
    ax2.set_ylim(0, 135); ax2.set_ylabel(_("parsers passing all fixtures, % (n = 2)")); ax2.set_title(_("E3 · parser written from the spec block")); ax2.legend(loc="upper right", ncol=2); ax2.grid(axis="x", visible=False)
    save(fig, "fig09_transfer_parsers")


# ---------------------------------------------------------------- Fig 10: break-even
def fig10():
    rows = read_csv(GEN / "e4_breakeven.csv")
    fig, ax = plt.subplots(figsize=(COL_W, 2.4))
    import numpy as np
    n = np.arange(0, 61)
    mini_spec = int(rows[0]["spec_tokens_mini"]); mini_rec = float(rows[0]["tokens_per_record_mini"])
    ax.plot(n, mini_spec + mini_rec * n, color=COLOR["mini"], lw=2, label=_(".mini (spec 640 tok)"))
    for r in rows:
        f = r["alternative"]
        key = {"json": "json_compact", "toon": "toon_flat"}.get(f, f)
        ax.plot(n, int(r["spec_tokens_alt"]) + float(r["tokens_per_record_alt"]) * n, color=COLOR[key], lw=1.4, label=f"{LABEL[key]} (spec {r['spec_tokens_alt']} tok)")
        be = r["breakeven_records"]
        if be != "never" and float(be) <= 60:
            ax.axvline(float(be), color=COLOR[key], lw=0.7, ls=":")
    ax.set_xlabel(_("records generated in one call")); ax.set_ylabel(_("total tokens = specification + output"))
    ax.set_ylim(0, 12500); ax.legend(loc="upper left", fontsize=6.2)
    ax.set_title(_("Break-even including the cost of teaching the format"))
    save(fig, "fig10_breakeven")


# ---------------------------------------------------------------- Fig 11: truncation recovery
def fig11():
    rows = read_csv(GEN / "e5_truncation.csv")
    fmts = ["mini", "toon_flat", "csv", "yaml", "json", "xml"]
    prefixes = ["a", "tc", "log"]
    import numpy as np
    fig, ax = plt.subplots(figsize=(COL_W, 2.3))
    x = np.arange(len(fmts))
    for k, p in enumerate(prefixes):
        vals = [float(next(r["recovery_efficiency"] for r in rows if r["prefix"] == p and r["format"] == f)) for f in fmts]
        bars = ax.bar(x + (k - 1) * 0.27, vals, width=0.25, color=["#2a78d6", "#1baf7a", "#eda100"][k], edgecolor="white", label=f".mini-{p} " + _("data"))
        for b, v in zip(bars, vals):
            ax.text(b.get_x() + b.get_width() / 2, v + 1.5, f"{v:.0f}", ha="center", fontsize=5.8)
    ax.set_xticks(x); ax.set_xticklabels([LABEL[f] for f in fmts], rotation=25, ha="right")
    ax.set_ylabel(_("complete records recovered\nafter random truncation, %")); ax.set_ylim(0, 112); ax.legend(loc="upper right", fontsize=6); ax.grid(axis="x", visible=False)
    save(fig, "fig11_truncation")


# ---------------------------------------------------------------- Fig 12: architecture of a family (diagram)
def box(ax, x, y, w, h, text, fc, fs=7, ec="none", tc="white", weight="bold"):
    ax.add_patch(patches.FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.02,rounding_size=0.08", fc=fc, ec=ec, lw=0.8))
    ax.text(x + w / 2, y + h / 2, text, ha="center", va="center", fontsize=fs, color=tc, weight=weight, linespacing=1.25)


def arrow(ax, x1, y1, x2, y2, color=INK2, lw=1):
    ax.annotate("", xy=(x2, y2), xytext=(x1, y1), arrowprops=dict(arrowstyle="-|>", color=color, lw=lw, shrinkA=2, shrinkB=2))


def fig12():
    fig, ax = plt.subplots(figsize=(DBL_W, 2.9))
    ax.set_xlim(0, 10); ax.set_ylim(-0.45, 4.25); ax.axis("off"); ax.grid(False)
    box(ax, 0.1, 2.3, 2.3, 1.5, _("CONTRACT\ncontract.json\nprefix · header keys\ncore fields · extensions\ntypes · arity · markers"), "#2a78d6", fs=6.6)
    box(ax, 3.0, 3.1, 1.9, 0.75, _("spec block\n(mini prompt)"), "#1baf7a", fs=6.8)
    box(ax, 3.0, 2.1, 1.9, 0.75, _("parser\n(interpreted)"), "#eb6834", fs=6.8)
    box(ax, 3.0, 1.1, 1.9, 0.75, _("serializer\n(interpreted)"), "#eda100", fs=6.8, tc=INK)
    box(ax, 3.0, 0.1, 1.9, 0.75, _("fork checker\nI1–I5"), "#4a3aa7", fs=6.8)
    for y in (3.475, 2.475, 1.475, 0.475):
        arrow(ax, 2.4, 3.05, 3.0, y)
    box(ax, 5.7, 3.1, 1.9, 0.75, _("generative model\n(any provider)"), "#52514e", fs=6.8)
    box(ax, 5.7, 2.1, 1.9, 0.75, _(".mini document\n(one line per record)"), "#0b0b0b", fs=6.8)
    box(ax, 5.7, 1.1, 1.9, 0.75, _("canonical JSON\n(application object)"), "#0b0b0b", fs=6.8)
    box(ax, 5.7, 0.1, 1.9, 0.75, _("fixtures\nvalid · escaping · bad"), "#52514e", fs=6.4)
    arrow(ax, 4.9, 3.475, 5.7, 3.475); arrow(ax, 6.65, 3.1, 6.65, 2.85)
    arrow(ax, 6.65, 2.1, 6.65, 1.85); ax.text(6.75, 1.98, "parse", fontsize=6.3, color=INK2)
    arrow(ax, 6.25, 1.85, 6.25, 2.1); ax.text(5.75, 1.98, "dumps", fontsize=6.3, color=INK2, ha="left")
    arrow(ax, 4.9, 0.475, 5.7, 0.475)
    box(ax, 8.2, 0.3, 1.6, 1.0, _("child fork\nparent core +\nappended tail"), "#2a78d6", fs=6.6)
    ax.plot([1.25, 1.25, 9.0], [2.3, -0.2, -0.2], color="#2a78d6", lw=1.2, solid_capstyle="round")
    arrow(ax, 9.0, -0.2, 9.0, 0.3, color="#2a78d6", lw=1.2)
    ax.text(5.0, -0.12, _("fork: new prefix · inherited fields unchanged · new fields appended"), fontsize=6.3, color="#2a78d6", ha="center", va="bottom")
    box(ax, 8.2, 2.0, 1.6, 1.2, _("registry\nunique prefixes\nlineage · CI\n(mini check-forks)"), "#52514e", fs=6.6)
    arrow(ax, 9.0, 1.3, 9.0, 2.0)
    ax.text(0.2, 4.05, _("A .mini family: the contract is data; every tool is derived from it"), fontsize=8.5, weight="bold", color=INK, va="center")
    save(fig, "fig12_architecture")


# ---------------------------------------------------------------- Fig 13: SIMA pipeline (case study)
def fig13():
    fig, ax = plt.subplots(figsize=(DBL_W, 2.0))
    ax.set_xlim(0, 10); ax.set_ylim(0, 2.6); ax.axis("off"); ax.grid(False)
    steps = [(_("Lecture audio /\ntranscript"), "#52514e"), (_("Whisper ASR\n(local)"), "#52514e"), (_("LLM generation\nin .mini-a"), "#2a78d6"),
             (_("parse + validate\n(E01–E13), repair"), "#eb6834"), (_("canonical JSON\n→ Django ORM"), "#0b0b0b"), (_("IRT 3PL / CAT\nquiz · cards · map"), "#1baf7a")]
    w, gap = 1.45, 0.22
    for i, (t, c) in enumerate(steps):
        x = 0.1 + i * (w + gap)
        box(ax, x, 1.0, w, 0.95, t, c, fs=5.9 if LANG == "es" else 6.2)
        if i < len(steps) - 1:
            arrow(ax, x + w, 1.475, x + w + gap, 1.475)
    ax.text(0.1, 2.35, _("SIMA case study: where .mini sits in the microlearning pipeline"), fontsize=8.5, weight="bold")
    ax.text(0.1 + 2 * (w + gap) + w / 2, 0.75, _("−38 % tokens vs\nJSON compact per bank"), fontsize=6.2, color="#2a78d6", ha="center", va="top")
    ax.text(0.1 + 3 * (w + gap) + w / 2, 0.75, _("22/53 incoherent items\ncaught before persistence"), fontsize=6.2, color="#eb6834", ha="center", va="top")
    ax.text(0.1 + 5 * (w + gap) + w / 2, 0.75, _("θ estimate, SE stop rule,\nexposure control"), fontsize=6.2, color="#1baf7a", ha="center", va="top")
    save(fig, "fig13_sima_pipeline")


# ---------------------------------------------------------------- Fig 14: fork lineage / gallery
def fig14():
    reg = json.loads((ROOT / "forks" / "registry.json").read_text(encoding="utf-8"))
    order = ["a", "q", "card", "sum", "map", "r", "s", "code", "tc", "us", "log", "ner", "cat", "cls"]
    dom = {r["prefix"]: r["domain"] for r in reg}
    arity = {r["prefix"]: (r["arity"], r["extensions"]) for r in reg}
    fig, ax = plt.subplots(figsize=(DBL_W, 2.6))
    ax.set_xlim(0, 10); ax.set_ylim(0, 3.2); ax.axis("off"); ax.grid(False)
    groups = [(_("education"), ["a", "q", "card", "sum", "map", "r", "s", "code"], "#2a78d6"),
              (_("software / ops"), ["tc", "us", "log"], "#eb6834"), (_("NLP / commerce"), ["ner", "cat", "cls"], "#1baf7a")]
    x = 0.15
    for name, ps, col in groups:
        ax.text(x, 2.95, name, fontsize=7.5, weight="bold", color=col)
        for i, p in enumerate(ps):
            cx = x + (i % 4) * 0.75; cy = 2.05 - (i // 4) * 0.95
            box(ax, cx, cy, 0.68, 0.72, f"{p}\n{arity[p][0]}+{arity[p][1]}", col, fs=6.6)
        x += 0.75 * min(4, len(ps)) + 0.35
    arrow(ax, 0.83, 2.41, 0.90, 2.41, color="#2a78d6", lw=1.2)
    ax.text(0.15, 0.55, _("Each box is a contract shipped with fixtures and a README; the number is core fields + extension fields. ")
            + _("q is a fork of a (same core, +3 trailing fields). All 14 pass `mini check-forks` and round-trip in both implementations."),
            fontsize=6.4, color=INK2, wrap=True)
    save(fig, "fig14_fork_gallery")


# ---------------------------------------------------------------- Fig 15: per-record marginal cost
def fig15():
    prefixes = ["a", "q", "card", "sum", "map", "r", "s", "code", "tc", "us", "log", "ner", "cat", "cls"]
    import numpy as np
    fig, ax = plt.subplots(figsize=(DBL_W, 2.4))
    x = np.arange(len(prefixes))
    fm = ["mini", "toon_flat", "csv", "json_compact"]
    for k, f in enumerate(fm):
        vals = [(tokens(p, f, 500)["tokens"] - tokens(p, f, 100)["tokens"]) / 400 for p in prefixes]
        ax.bar(x + (k - 1.5) * 0.2, vals, width=0.19, color=COLOR[f], edgecolor="white", label=LABEL[f])
    ax.set_xticks(x); ax.set_xticklabels([f".mini-{p}" for p in prefixes], rotation=25, ha="right")
    ax.set_ylabel(_("marginal tokens per record\n(slope n = 100 → 500)")); ax.legend(ncol=4, loc="upper right"); ax.grid(axis="x", visible=False)
    save(fig, "fig15_marginal_cost")


if __name__ == "__main__":
    fig1(); fig2(); fig3(); fig4(); fig5(); costs = fig6(); fig7(); fig8(); fig9(); fig10(); fig11(); fig12(); fig13(); fig14(); fig15()
    print(json.dumps({k: round(v, 1) for k, v in costs.items()}))
