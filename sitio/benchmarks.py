"""Render public benchmark figures from their reproducible result file."""
from __future__ import annotations
import html
import json
import re
from pathlib import Path

RESULTS = Path(__file__).resolve().parents[1] / "benchmark" / "public" / "results.json"


def inject_benchmarks(page: str, lang: str) -> str:
    if not RESULTS.exists():
        raise FileNotFoundError("Run benchmark/public/run.py before building the public site")
    result = json.loads(RESULTS.read_text(encoding="utf-8"))
    es = lang == "es"
    def tr(spanish, english): return spanish if es else english
    def number(value, decimals=0):
        formatted = f"{value:,.{decimals}f}"
        return formatted.replace(",", "_").replace(".", ",").replace("_", ".") if es else formatted
    labels = {"products": tr("Productos", "Products"), "users": tr("Usuarios", "Users"), "comments": tr("Comentarios", "Comments"), "quakes": "USGS", "earthquakes": "USGS"}
    formats = {"mini": ("mini-format", "mini-domain/1"), "toon_flat": ("TOON", tr("plano", "flat")), "csv": ("CSV", tr("plano", "flat")), "json_compact": ("JSON", tr("compacto", "compact")), "toon": ("TOON", tr("original", "original")), "yaml": ("YAML", "1.2"), "xml": ("XML", tr("elementos", "elements"))}
    tabs, panels = [], []
    for index, dataset in enumerate(result["datasets"]):
        name = labels.get(dataset["id"], dataset["title"])
        panel_id = "public-" + dataset["id"]
        tabs.append(f'<button role="tab" aria-selected="{str(index == 0).lower()}" data-panel="{panel_id}">{html.escape(name)}</button>')
        baseline = dataset["formats"]["mini"]["tokens"]
        maximum = max(dataset["formats"][fmt]["tokens"] for fmt in formats)
        rows = []
        for fmt, (label, subtitle) in sorted(formats.items(), key=lambda item: dataset["formats"][item[0]]["tokens"]):
            count = dataset["formats"][fmt]["tokens"]
            variant = " is-mini" if fmt == "mini" else (" is-loss" if count < baseline else "")
            rows.append(f'<div class="bar{variant}" style="--w:{100*count/maximum:.2f}%" title="{count} tokens"><span class="name">{label}<small>{subtitle}</small></span><span class="track"><span class="fill"></span></span><span class="val">{number(count/baseline,2)}×</span></div>')
        kind = tr("Observaciones reales", "Real observations") if "real" in dataset["source_kind"] and "synthetic" not in dataset["source_kind"] else tr("Datos públicos de prueba", "Public test data")
        savings = dataset["savings"]["vs_toon_flat_pct"]
        note = tr(f'{number(savings,2)} % menos tokens que TOON plano. Incluye metadatos y diccionarios del documento; prompt reutilizable medido aparte.', f'{number(savings,2)}% fewer tokens than flat TOON. Includes document metadata and dictionaries; reusable prompt measured separately.')
        panels.append(f'<div class="bench-body js-chart" id="{panel_id}" role="tabpanel"{" hidden" if index else ""}><div class="bench-head"><h3>{html.escape(dataset["title"])}</h3><button class="replay" type="button" data-replay>↻ {tr("animar", "replay")}</button></div><p class="unit">{number(dataset["records"])} {tr("registros", "records")} · {kind}</p><p class="howto">{tr("Tokens de salida relativos a .mini · menos es mejor.", "Output tokens relative to .mini · lower is better.")} <b>o200k_base</b></p>{"".join(rows)}<div class="note"><span>{note}</span><a href="/docs/metodologia/">{tr("método →", "method →")}</a></div></div>')
    hero = '<div class="bench"><div class="bench-tabs" role="tablist" aria-label="Datasets">' + "".join(tabs) + '</div>' + "".join(panels) + '</div>'
    page, changed = re.subn(r'    <div class="bench">.*?\n  </div>\n</section>', '    ' + hero + '\n  </div>\n</section>', page, count=1, flags=re.S)
    if changed != 1:
        raise ValueError("Hero benchmark anchor is missing")
    summary = result["summary"]
    weighted = summary["weighted_savings_pct"]
    # Aggregate savings use total tokens, never an unweighted mean of percentages.
    json_savings = weighted.get("json_compact", weighted.get("vs_json_compact_pct"))
    toon_savings = weighted.get("toon_flat", weighted.get("vs_toon_flat_pct"))
    if json_savings is None or toon_savings is None:
        raise ValueError("Missing weighted benchmark savings")
    heading = tr("Mismos datos.<br><span class=\"dim\">Menos tokens medidos.</span>", "Same data.<br><span class=\"dim\">Measured token savings.</span>")
    intro = tr(f'{number(summary["records"])} registros de cuatro conjuntos públicos. {number(json_savings,2)} % menos tokens que JSON compacto y {number(toon_savings,2)} % menos que TOON plano en el total medido.', f'{number(summary["records"])} records from four public datasets. {number(json_savings,2)}% fewer tokens than compact JSON and {number(toon_savings,2)}% fewer than flat TOON across the measured total.')
    table_rows = []
    for dataset in result["datasets"]:
        f, savings = dataset["formats"], dataset["savings"]
        cells = [html.escape(dataset["title"]), number(dataset["records"]), number(f["mini"]["tokens"]), number(f["toon_flat"]["tokens"]), number(savings["vs_toon_flat_pct"],2)+" %", number(savings["vs_csv_pct"],2)+" %", number(f["mini"]["prompt_tokens"])]
        data_cells = ''.join('<td' + (' class="neg"' if i == 5 and savings["vs_csv_pct"] < 0 else '') + '>' + cell + '</td>' for i, cell in enumerate(cells[1:], 1))
        table_rows.append('<tr><th scope="row">' + cells[0] + '</th>' + data_cells + '</tr>')
    heads = [tr("Conjunto", "Dataset"), "N", ".mini", "TOON flat", tr("Ahorro vs TOON", "Saved vs TOON"), tr("Ahorro vs CSV", "Saved vs CSV"), tr("Prompt .mini", ".mini prompt")]
    table = '<div class="tablewrap"><table class="t"><caption class="sr">' + tr("Tokens de salida, ahorro y coste del prompt reutilizable", "Output tokens, savings and reusable prompt cost") + '</caption><thead><tr>' + ''.join('<th scope="col">'+x+'</th>' for x in heads) + '</tr></thead><tbody>' + ''.join(table_rows) + '</tbody></table></div>'
    note = tr('USGS: 1.000 observaciones reales. DummyJSON y JSONPlaceholder: 902 registros de prueba sintéticos, sin duplicación para inflar el lote. Ida y vuelta JSON exacta en los ocho formatos. TOON oficial 4.1.1; se elige el menor de dos aplanados reversibles. Los porcentajes son de salida: el prompt de .mini se muestra aparte. CSV sigue siendo menor en comentarios. Es una medición de serialización, no de precisión de generación de un LLM.', 'USGS: 1,000 real observations. DummyJSON and JSONPlaceholder: 902 synthetic test records, never duplicated to inflate the batch. Exact JSON round-trips for all eight formats. Official TOON 4.1.1; the smaller of two reversible flattening variants is selected. Savings describe output tokens; the .mini prompt is shown separately. CSV remains smaller for comments. This measures serialization, not LLM generation accuracy.')
    block = f'<section class="section"><div class="frame"><div class="split-head"><h2 class="rv">{heading}</h2><p class="aside rv">{intro}</p></div>{table}<p class="fine">{note} <a href="/docs/metodologia/">{tr("Método y reproducción →", "Method and reproduction →")}</a> · <a href="/source/benchmark/public/results.json">JSON</a></p></div></section>'
    page, changed = re.subn(r'(?<=<!-- ═══════════ BENCHMARK COMPLETO ═══════════ -->)\s*<section.*?</section>', '\n' + block, page, count=1, flags=re.S)
    if changed != 1:
        raise ValueError("Detailed benchmark anchor is missing")
    return page
