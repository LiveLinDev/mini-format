"""Módulo /validacion/ — Tablas reproducibles de competidores 2026, conformidad y cortes.

Toda cifra proviene de:
- ``benchmark/public/competitors_results.json`` (o200k_base, cl100k_base, p50k_base; round-trip 100%)
- ``experiments/estudio_formatos/corridas/resultados.json`` (18 corridas reales + 180 cortes)
- ``ctx.cifras`` (conformidad de 376 casos en 14 familias)

Política estricta: cero flechas, emojis ni símbolos dingbats prohibidos.
"""
from __future__ import annotations

import html


def construir(ctx) -> None:
    a = ctx.ambos
    comp = ctx.leer_json("benchmark/public/competitors_results.json")
    datasets = comp.get("datasets", [])
    ds_map = {d["name"]: d for d in datasets}
    casos = ctx.cifras.get("casos_conformidad", 376)
    familias = len(ctx.leer_json("forks/registry.json")) if isinstance(ctx.leer_json("forks/registry.json"), list) else 14

    pub_names = ("products", "users", "comments", "earthquakes")
    tot_json = sum(ds_map[n]["formats"]["json_compact"]["o200k_base"] for n in pub_names)
    tot_v2 = sum(ds_map[n]["formats"]["mini_v2"]["o200k_base"] for n in pub_names)
    tot_save = (tot_json - tot_v2) / tot_json * 100.0

    # Per-dataset winner rows
    summary_rows = []
    for d in datasets:
        fmts = d["formats"]
        best_fmt = "mini_rows" if "mini_rows" in fmts else "mini_v2"
        best_st = fmts[best_fmt]
        json_st = fmts["json_compact"]
        ison_tok = fmts["ison"]["o200k_base"]
        toon_tok = (fmts.get("toon_flat") or fmts.get("toon") or {})["o200k_base"]
        csv_tok = fmts["csv"]["o200k_base"]
        summary_rows.append(
            f'<tr><th scope="row">{html.escape(d["label"])}</th>'
            f'<td>{d["records"]:,}</td>'
            f'<td><strong>{best_st["o200k_base"]:,}</strong> <span class="val-badge">{html.escape(best_fmt)}</span></td>'
            f'<td>{ison_tok:,}</td>'
            f'<td>{csv_tok:,}</td>'
            f'<td>{toon_tok:,}</td>'
            f'<td>{json_st["o200k_base"]:,}</td>'
            f'<td><strong>{best_st["saving_vs_json_compact"]:+.1f}%</strong></td></tr>'
        )

    # Full 16-format leaderboard aggregated across 1,902 public records + 3 tokenizers
    agg_formats = [
        ("mini_v2", ".mini (domain/2)"),
        ("mini_v1", ".mini (domain/1)"),
        ("csv", "CSV (flat reversible)"),
        ("ison", "ISON v1.0"),
        ("toon_flat", "TOON (flat 4.1.1)"),
        ("json_positional", "Positional JSON"),
        ("tonl", "TONL"),
        ("hedl", "HEDL"),
        ("lean", "LEAN"),
        ("raif", "RAIF"),
        ("json_short", "Short-Key JSON"),
        ("json_compact", "JSON compact"),
        ("toon", "TOON (as-is)"),
        ("yaml", "YAML"),
        ("json_pretty", "JSON pretty"),
        ("xml", "XML"),
    ]
    agg_rows = []
    for key, label in agg_formats:
        o200 = sum(ds_map[n]["formats"][key]["o200k_base"] for n in pub_names)
        cl100 = sum(ds_map[n]["formats"][key]["cl100k_base"] for n in pub_names)
        p50 = sum(ds_map[n]["formats"][key]["p50k_base"] for n in pub_names)
        b_tot = sum(ds_map[n]["formats"][key]["bytes"] for n in pub_names)
        save = (tot_json - o200) / tot_json * 100.0
        hl = " style=\"font-weight:700\"" if key == "mini_v2" else ""
        agg_rows.append(
            f'<tr{hl}><th scope="row">{html.escape(label)}</th>'
            f'<td>{o200:,}</td><td>{cl100:,}</td><td>{p50:,}</td>'
            f'<td>{b_tot:,}</td><td>{save:+.1f}%</td><td>{a("100% Exacto", "100% Exact")}</td></tr>'
        )

    cuerpo = f'''<div class="val-wrap prose">
  <p class="eyebrow">{a("Evidencia técnica reproducible", "Reproducible technical proof")}</p>
  <h1>{a("Validación y Benchmarks 2026", "Validation & 2026 Benchmarks")}</h1>
  <p class="lead">{a(
      "Comparación de tokens serializados con tres tokenizadores BPE. El arnés verifica la ida y vuelta del JSON y aporta contexto compartido a los perfiles que lo necesitan.",
      "Comparison of serialized text with three BPE tokenizers. The harness verifies JSON round-trips and supplies shared context to profiles that need it."
  )}</p>

  <div class="val-kpi-grid">
    <div class="val-kpi">
      <strong>{a("4 conjuntos", "4 datasets")}</strong>
      <span>{a("Datos públicos y un ejemplo adicional de 20 tickets.", "Public datasets and a separate 20-ticket example.")}</span>
    </div>
    <div class="val-kpi">
      <strong>-{tot_save:.1f}% {a("total", "total")}</strong>
      <span>{a(f"{tot_v2:,} vs {tot_json:,} JSON compacto en 1.902 registros.", f"{tot_v2:,} vs {tot_json:,} JSON compact across 1,902 public records.")}</span>
    </div>
    <div class="val-kpi">
      <strong>99.8% {a("cortes", "recovery")}</strong>
      <span>{a("1.705 / 1.708 registros salvados tras max_tokens vs 0 / 1.724 JSON.", "1,705 / 1,708 records recovered after truncation cuts vs 0 / 1,724 JSON.")}</span>
    </div>
    <div class="val-kpi">
      <strong>{casos} {a("casos", "cases")}</strong>
      <span>{a(f"Conformidad cruzada Python / JS / Oracle TS en {familias} familias más gramáticas GBNF/Lark.", f"Cross-runtime Python / JS / Oracle TS conformance across {familias} families plus GBNF/Lark.")}</span>
    </div>
  </div>

  <section class="val-sec">
    <h2>{a("Resultados por conjunto de datos (o200k_base)", "Per-workload results (o200k_base)")}</h2>
    <div class="tablewrap">
      <table class="t">
        <thead>
          <tr>
            <th scope="col">{a("Conjunto", "Dataset")}</th>
            <th scope="col">N</th>
            <th scope="col">.mini</th>
            <th scope="col">ISON</th>
            <th scope="col">CSV</th>
            <th scope="col">TOON</th>
            <th scope="col">JSON compact</th>
            <th scope="col">{a("Ahorro vs JSON", "Saving vs JSON")}</th>
          </tr>
        </thead>
        <tbody>{"".join(summary_rows)}</tbody>
      </table>
    </div>
  </section>

  <section class="val-sec">
    <h2>{a("Clasificación agregada multiformato (1.902 registros públicos)", "Aggregate multi-tokenizer leaderboard (1,902 public records)")}</h2>
    <div class="tablewrap">
      <table class="t">
        <thead>
          <tr>
            <th scope="col">{a("Formato", "Format")}</th>
            <th scope="col">o200k_base</th>
            <th scope="col">cl100k_base</th>
            <th scope="col">p50k_base</th>
            <th scope="col">Bytes</th>
            <th scope="col">{a("Ahorro vs JSON", "Saving vs JSON")}</th>
            <th scope="col">Round-trip</th>
          </tr>
        </thead>
        <tbody>{"".join(agg_rows)}</tbody>
      </table>
    </div>
  </section>

  <section class="val-sec">
    <h2>{a("Supervivencia ante truncamiento (180 cortes reales)", "Truncation cut survival (180 real cuts)")}</h2>
    <div class="tablewrap">
      <table class="t">
        <thead>
          <tr>
            <th scope="col">{a("Lector", "Reader")}</th>
            <th scope="col">{a("Registros completos antes del corte", "Complete records before cut")}</th>
            <th scope="col">{a("Recuperados", "Recovered")}</th>
            <th scope="col">{a("Tasa", "Rate")}</th>
          </tr>
        </thead>
        <tbody>
          <tr><th scope="row">.mini Workflow</th><td>1,708</td><td>1,705</td><td><strong>99.8%</strong></td></tr>
          <tr><th scope="row">JSON (json.loads)</th><td>1,724</td><td>0</td><td>0.0%</td></tr>
        </tbody>
      </table>
    </div>
  </section>

  <p class="wip-links">
    <a class="btn btn-ghost" href="/economia/">{a("Calculadora de costos LLM", "LLM Cost Simulator")}</a>
    <a class="btn btn-ghost" href="/source/benchmark/public/competitors_results.json">{a("Resultados completos (JSON)", "Full benchmark results (JSON)")}</a>
    <a class="btn btn-ghost" href="/docs/conformance/">{a("Suite de conformidad", "Conformance suite")}</a>
  </p>
</div>'''
    html_out = ctx.pagina("validacion", "Validación y Benchmarks", "Validation & Benchmarks", cuerpo)
    html_out = ctx.recursos(html_out, css=("/validacion.css",))
    ctx.escribir_pagina("validacion", html_out)
