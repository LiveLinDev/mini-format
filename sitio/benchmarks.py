"""Render public benchmark figures from their reproducible result files."""
from __future__ import annotations
import html
import json
import re
from pathlib import Path

RESULTS = Path(__file__).resolve().parents[1] / "benchmark" / "public" / "results.json"
COMP_RESULTS = Path(__file__).resolve().parents[1] / "benchmark" / "public" / "competitors_results.json"


def inject_benchmarks(page: str, lang: str) -> str:
    if not RESULTS.exists():
        raise FileNotFoundError("Run benchmark/public/run.py before building the public site")
    result = json.loads(RESULTS.read_text(encoding="utf-8"))
    comp = json.loads(COMP_RESULTS.read_text(encoding="utf-8")) if COMP_RESULTS.is_file() else {"datasets": []}
    comp_map = {d["name"]: d["formats"] for d in comp.get("datasets", [])}

    es = lang == "es"
    def tr(spanish, english): return spanish if es else english
    def number(value, decimals=0):
        formatted = f"{value:,.{decimals}f}"
        return formatted.replace(",", "_").replace(".", ",").replace("_", ".") if es else formatted
    labels = {"products": tr("Productos", "Products"), "users": tr("Usuarios", "Users"), "comments": tr("Comentarios", "Comments"), "quakes": "USGS", "earthquakes": "USGS"}
    base_formats = {"mini": ("mini-format", "mini-domain/1"), "toon_flat": ("TOON", tr("plano", "flat")), "csv": ("CSV", tr("plano", "flat")), "json_compact": ("JSON", tr("compacto", "compact")), "toon": ("TOON", tr("original", "original")), "yaml": ("YAML", "1.2"), "xml": ("XML", tr("elementos", "elements"))}

    tabs, panels = [], []
    total_v2_tok = 0
    total_json_tok = 0
    total_toon_flat_tok = 0
    for index, dataset in enumerate(result["datasets"]):
        did = dataset["id"]
        c_fmts = comp_map.get(did, {})
        has_v2 = "mini_v2" in c_fmts
        name = labels.get(did, dataset["title"])
        panel_id = "public-" + did
        tabs.append(f'<button role="tab" aria-selected="{str(index == 0).lower()}" data-panel="{panel_id}">{html.escape(name)}</button>')

        entries = {}
        if has_v2:
            entries["mini_v2"] = ("mini-format", "mini-domain/2", c_fmts["mini_v2"]["o200k_base"])
        for k, (lbl, sub) in base_formats.items():
            entries[k] = (lbl, sub, dataset["formats"][k]["tokens"])
        for extra_key, extra_lbl, extra_sub in (("ison", "ISON", "v1.0"), ("tonl", "TONL", "compact"), ("lean", "LEAN", "tab")):
            if extra_key in c_fmts:
                entries[extra_key] = (extra_lbl, extra_sub, c_fmts[extra_key]["o200k_base"])

        baseline_key = "mini_v2" if has_v2 else "mini"
        baseline = entries[baseline_key][2]
        maximum = max(v[2] for v in entries.values())
        total_v2_tok += baseline
        total_json_tok += dataset["formats"]["json_compact"]["tokens"]
        total_toon_flat_tok += dataset["formats"]["toon_flat"]["tokens"]

        rows = []
        for fmt, (label, subtitle, count) in sorted(entries.items(), key=lambda item: item[1][2]):
            variant = " is-mini" if fmt == baseline_key else (" is-loss" if count < baseline else "")
            rows.append(f'<div class="bar{variant}" style="--w:{100*count/maximum:.2f}%" title="{count} tokens"><span class="name">{label}<small>{subtitle}</small></span><span class="track"><span class="fill"></span></span><span class="val">{number(count/baseline,2)}×</span></div>')
        kind = tr("Observaciones reales", "Real observations") if "real" in dataset["source_kind"] and "synthetic" not in dataset["source_kind"] else tr("Datos públicos de prueba", "Public test data")
        vs_toon_v2 = (dataset["formats"]["toon_flat"]["tokens"] - baseline) / dataset["formats"]["toon_flat"]["tokens"] * 100.0
        note = tr(f'{number(vs_toon_v2,2)} % menos tokens que TOON plano (domain/2). Prompt reutilizable medido aparte.', f'{number(vs_toon_v2,2)}% fewer tokens than flat TOON (domain/2). Reusable prompt measured separately.')
        panels.append(f'<div class="bench-body js-chart" id="{panel_id}" role="tabpanel"{" hidden" if index else ""}><div class="bench-head"><h3>{html.escape(dataset["title"])}</h3><button class="replay" type="button" data-replay>↻ {tr("animar", "replay")}</button></div><p class="unit">{number(dataset["records"])} {tr("registros", "records")} · {kind}</p><p class="howto">{tr("Tokens de salida relativos a .mini domain/2 · menos es mejor.", "Output tokens relative to .mini domain/2 · lower is better.")} <b>o200k_base</b></p>{"".join(rows)}<div class="note"><span>{note}</span><a href="/validacion/">{tr("comparativa completa →", "full comparison →")}</a></div></div>')

    hero = '<div class="bench"><div class="bench-tabs" role="tablist" aria-label="Datasets">' + "".join(tabs) + '</div>' + "".join(panels) + '</div>'
    page, changed = re.subn(r'    <div class="bench">.*?\n  </div>\n</section>', '    ' + hero + '\n  </div>\n</section>', page, count=1, flags=re.S)
    if changed != 1:
        raise ValueError("Hero benchmark anchor is missing")

    summary = result["summary"]
    json_savings = (total_json_tok - total_v2_tok) / total_json_tok * 100.0 if total_json_tok else 0.0
    toon_savings = (total_toon_flat_tok - total_v2_tok) / total_toon_flat_tok * 100.0 if total_toon_flat_tok else 0.0
    heading = tr("Mismos datos.<br><span class=\"dim\">Menos tokens medidos.</span>", "Same data.<br><span class=\"dim\">Measured token savings.</span>")
    intro = tr(f'{number(summary["records"])} registros de cuatro conjuntos públicos. {number(json_savings,1)} % menos tokens que JSON compacto y {number(toon_savings,1)} % menos que TOON plano con mini-domain/2.', f'{number(summary["records"])} records from four public datasets. {number(json_savings,1)}% fewer tokens than compact JSON and {number(toon_savings,1)}% fewer than flat TOON with mini-domain/2.')

    table_rows = []
    for dataset in result["datasets"]:
        did = dataset["id"]
        c_fmts = comp_map.get(did, {})
        f = dataset["formats"]
        v2_tok = c_fmts["mini_v2"]["o200k_base"] if "mini_v2" in c_fmts else f["mini"]["tokens"]
        csv_tok = f["csv"]["tokens"]
        tf_tok = f["toon_flat"]["tokens"]
        ison_tok = c_fmts["ison"]["o200k_base"] if "ison" in c_fmts else tf_tok
        vs_toon = (tf_tok - v2_tok) / tf_tok * 100.0
        vs_csv = (csv_tok - v2_tok) / csv_tok * 100.0
        cells = [html.escape(dataset["title"]), number(dataset["records"]), number(v2_tok), number(ison_tok), number(tf_tok), number(vs_toon, 1) + " %", number(vs_csv, 1) + " %"]
        data_cells = ''.join('<td' + (' class="neg"' if i == 6 and vs_csv < 0 else '') + '>' + cell + '</td>' for i, cell in enumerate(cells[1:], 1))
        table_rows.append('<tr><th scope="row">' + cells[0] + '</th>' + data_cells + '</tr>')
    heads = [tr("Conjunto", "Dataset"), "N", ".mini v2", "ISON", "TOON flat", tr("vs TOON", "vs TOON"), tr("vs CSV", "vs CSV")]
    table = '<div class="tablewrap"><table class="t"><caption class="sr">' + tr("Tokens de salida, comparativa contra ISON, TOON y CSV", "Output tokens, comparison vs ISON, TOON and CSV") + '</caption><thead><tr>' + ''.join('<th scope="col">' + x + '</th>' for x in heads) + '</tr></thead><tbody>' + ''.join(table_rows) + '</tbody></table></div>'
    note = tr(
        'USGS aporta 1.000 observaciones reales. DummyJSON y JSONPlaceholder aportan 902 registros públicos de prueba. '
        'La tabla cuenta tokens del texto serializado con los perfiles del arnés. '
        'Para calcular el costo de generación también cuentan la instrucción, el contrato y los reintentos.',
        'USGS contributes 1,000 real observations. DummyJSON and JSONPlaceholder contribute 902 public test records. '
        'The table counts serialized text tokens for the profiles implemented by the harness. '
        'Generation cost also depends on the instructions, contract, and retries.',
    )
    block = f'<section class="section"><div class="frame"><div class="split-head"><h2 class="rv">{heading}</h2><p class="aside rv">{intro}</p></div>{table}<p class="fine">{note} <a href="/validacion/#generacion-nube">{tr("Costo por respuesta correcta", "Cost per correct response")}</a> · <a href="/validacion/#serializacion-publica">{tr("Tabla de 16 formatos", "16-format leaderboard")}</a> · <a href="/source/benchmark/public/competitors_results.json">JSON</a></p></div></section>'
    page, changed = re.subn(r'(?<=<!-- ═══════════ BENCHMARK COMPLETO ═══════════ -->)\s*<section.*?</section>', '\n' + block, page, count=1, flags=re.S)
    if changed != 1:
        raise ValueError("Detailed benchmark anchor is missing")
    return page
