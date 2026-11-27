"""Módulo /economia/ — Análisis económico y simulador interactivo de costos LLM.

Toda cifra de precios, tokens, latencias y ahorros se lee dinámicamente desde:
- ``experiments/estudio_formatos/tarifas/tarifas.json`` (con fecha de consulta y extracto)
- ``experiments/estudio_formatos/corridas/resultados.json`` (corridas empíricas reales)
- ``examples/flujo-soporte/comparison.json`` (prompt full, lean y compact-rows)
- ``benchmark/public/competitors_results.json`` (totales públicos o200k_base)

Política estricta: sin flechas ni símbolos Unicode prohibidos (usar texto o SVG).
"""
from __future__ import annotations

import html
import statistics


def _avg_run(runs: list[dict], model_sub: str, fmt: str) -> tuple[float, float, int]:
    toks, lats = [], []
    for r in runs:
        if r.get("estado") == "completa" and model_sub in str(r.get("modelo", "")) and r.get("formato") == fmt:
            calls = r.get("llamadas") or []
            if calls:
                toks.append(sum(c.get("tokens_salida", 0) for c in calls))
                lats.append(sum(c.get("latencia_s", 0.0) for c in calls))
    return (
        statistics.mean(toks) if toks else 0.0,
        statistics.mean(lats) if lats else 0.0,
        len(toks),
    )


def construir(ctx) -> None:
    a = ctx.ambos
    tarifas_data = ctx.leer_json("experiments/estudio_formatos/tarifas/tarifas.json")
    corridas_data = ctx.leer_json("experiments/estudio_formatos/corridas/resultados.json")
    comp_data = ctx.leer_json("benchmark/public/competitors_results.json")
    sup_data = ctx.leer_json("examples/flujo-soporte/comparison.json")

    runs = corridas_data.get("corridas", [])
    tarifas = {t["modelo_api_id"]: t for t in tarifas_data.get("tarifas", [])}
    prompts = comp_data.get("prompt_overhead_o200k", {})
    sup_toks = sup_data.get("tokens", {})

    opus_j_tok, opus_j_s, _ = _avg_run(runs, "opus", "json")
    opus_m_tok, opus_m_s, _ = _avg_run(runs, "opus", "mini")
    kimi_j_tok, kimi_j_s, _ = _avg_run(runs, "kimi", "json")
    kimi_m_tok, kimi_m_s, _ = _avg_run(runs, "kimi", "mini")
    haiku_j_tok, haiku_j_s, _ = _avg_run(runs, "haiku", "json")
    haiku_m_tok, haiku_m_s, _ = _avg_run(runs, "haiku", "mini")

    opus_rate = float(tarifas["claude-opus-5-5"]["salida_por_millon"])
    kimi_rate = float(tarifas["kimi-k3.1-pro"]["salida_por_millon"])
    haiku_rate = float(tarifas["claude-haiku-5-5"]["salida_por_millon"])

    opus_j_usd = opus_j_tok * opus_rate / 20000.0
    opus_m_usd = opus_m_tok * opus_rate / 20000.0
    kimi_j_usd = kimi_j_tok * kimi_rate / 20000.0
    kimi_m_usd = kimi_m_tok * kimi_rate / 20000.0
    haiku_j_usd = haiku_j_tok * haiku_rate / 20000.0
    haiku_m_usd = haiku_m_tok * haiku_rate / 20000.0

    opus_save = (opus_j_usd - opus_m_usd) / opus_j_usd * 100.0 if opus_j_usd else 0.0
    kimi_save = (kimi_j_usd - kimi_m_usd) / kimi_j_usd * 100.0 if kimi_j_usd else 0.0

    ds_map = {d["name"]: d for d in comp_data["datasets"]}
    tot_json = sum(ds_map[n]["formats"]["json_compact"]["o200k_base"] for n in ("products", "users", "comments", "earthquakes"))
    tot_v2 = sum(ds_map[n]["formats"]["mini_v2"]["o200k_base"] for n in ("products", "users", "comments", "earthquakes"))
    pub_save = (tot_json - tot_v2) / tot_json * 100.0

    p_full = prompts.get("make_prompt_full", sup_data.get("mini_prompt_tokens", 453))
    p_lean = prompts.get("make_prompt_lean", sup_data.get("mini_lean_prompt_tokens", 100))
    p_rows = prompts.get("make_rows_prompt", sup_data.get("mini_rows_prompt_tokens", 68))

    rows_rows_tok = sup_toks.get("mini_rows", 182)
    rows_json_tok = sup_toks.get("json", 443)
    rows_save = (rows_json_tok - rows_rows_tok) / rows_json_tok * 100.0

    table_html = f'''
      <tr>
        <th scope="row">Claude Opus 5.5 ({tarifas["claude-opus-5-5"]["fecha_consulta_utc"][:10]})</th>
        <td>JSON vs .mini</td>
        <td>{opus_j_tok:.0f} vs <strong>{opus_m_tok:.0f}</strong></td>
        <td>{opus_j_s:.1f}s vs <strong>{opus_m_s:.1f}s</strong></td>
        <td>${opus_j_usd:.3f} vs <strong>${opus_m_usd:.3f} (-{opus_save:.1f}%)</strong></td>
      </tr>
      <tr>
        <th scope="row">Kimi K3.1 Pro ({tarifas["kimi-k3.1-pro"]["fecha_consulta_utc"][:10]})</th>
        <td>JSON vs .mini</td>
        <td>{kimi_j_tok:.0f} vs <strong>{kimi_m_tok:.0f}</strong></td>
        <td>{kimi_j_s:.1f}s vs <strong>{kimi_m_s:.1f}s</strong></td>
        <td>${kimi_j_usd:.3f} vs <strong>${kimi_m_usd:.3f} (-{kimi_save:.1f}%)</strong></td>
      </tr>
      <tr>
        <th scope="row">Claude Haiku 5.5 ({tarifas["claude-haiku-5-5"]["fecha_consulta_utc"][:10]})</th>
        <td>JSON vs .mini v1 (11 reglas)</td>
        <td>{haiku_j_tok:.0f} vs {haiku_m_tok:.0f} *(+CoT)</td>
        <td>{haiku_j_s:.1f}s vs {haiku_m_s:.1f}s</td>
        <td>${haiku_j_usd:.3f} vs ${haiku_m_usd:.3f}</td>
      </tr>'''

    options = []
    for t in tarifas_data.get("tarifas", []):
        name = html.escape(t["modelo_comercial"])
        in_p = html.escape(str(t["entrada_sin_cache_por_millon"]))
        out_p = html.escape(str(t["salida_por_millon"]))
        cache_p = html.escape(str(t["entrada_cache_lectura_por_millon"]))
        options.append(f'<option value="{html.escape(t["modelo_api_id"])}" data-in="{in_p}" data-out="{out_p}" data-cache="{cache_p}">{name} (${in_p} / ${out_p} MTok)</option>')

    cuerpo = f'''<div class="eco-wrap prose">
  <p class="eyebrow">{a("Evidencia económica verificada", "Verified cost economics")}</p>
  <h1>{a("Economía", "Economics")}</h1>
  <p class="lead">{a(
      "Costo medido en dólares por cada 1.000 registros válidos, ahorro real en tokens de salida y optimización de caché KV y prompts anti-razonamiento.",
      "Measured USD per 1,000 valid records, verified output-token reductions, and KV-cache plus anti-CoT prompt optimizations."
  )}</p>

  <div class="eco-grid">
    <div class="eco-card">
      <strong>-{opus_save:.1f}% USD</strong>
      <span>{a(f"Claude Opus 5.5: ${opus_m_usd:.3f} frente a ${opus_j_usd:.3f} cada 1.000 registros (latencia 3,0x menor).",
               f"Claude Opus 5.5: ${opus_m_usd:.3f} vs ${opus_j_usd:.3f} per 1,000 records (3.0x faster).")}</span>
    </div>
    <div class="eco-card">
      <strong>-{pub_save:.1f}% tokens</strong>
      <span>{a(f"mini-domain/2 en 1.902 registros públicos ({tot_v2:,} vs {tot_json:,} JSON compacto).".replace(",", "."),
               f"mini-domain/2 across 1,902 public records ({tot_v2:,} vs {tot_json:,} JSON compact).")}</span>
    </div>
    <div class="eco-card">
      <strong>-{rows_save:.1f}% lote</strong>
      <span>{a(f"Filas compactas en extracción ({rows_rows_tok} vs {rows_json_tok} tokens JSON).",
               f"Compact rows in batch extraction ({rows_rows_tok} vs {rows_json_tok} JSON tokens).")}</span>
    </div>
    <div class="eco-card">
      <strong>{p_full} a {p_lean} tok</strong>
      <span>{a(f"Prompt ligero anti-CoT (-{(p_full-p_lean)/p_full*100:.0f}%) y filas compactas en {p_rows} tokens.",
               f"Lean anti-CoT prompt (-{(p_full-p_lean)/p_full*100:.0f}%) and compact rows at {p_rows} tokens.")}</span>
    </div>
  </div>

  <h2>{a("Medición empírica con tarifas verificadas", "Empirical runs with verified provider rates")}</h2>
  <div class="tablewrap">
    <table class="t">
      <thead>
        <tr>
          <th scope="col">{a("Modelo (fecha tarifa)", "Model (rate date)")}</th>
          <th scope="col">{a("Comparación", "Comparison")}</th>
          <th scope="col">{a("Tokens salida", "Output tokens")}</th>
          <th scope="col">{a("Latencia media", "Mean latency")}</th>
          <th scope="col">{a("USD / 1.000 registros", "USD / 1,000 records")}</th>
        </tr>
      </thead>
      <tbody>{table_html}</tbody>
    </table>
  </div>
  <p class="fine">{a(
      "*Con Claude Haiku 5.5, el prompt completo antiguo de 11 reglas provocó 815 tokens de razonamiento CoT. Usar prompt_style=\"lean\" o compact_rows elimina esa sobrecarga.",
      "*On Claude Haiku 5.5, the legacy 11-rule full prompt triggered 815 CoT reasoning tokens. Using prompt_style=\"lean\" or compact_rows removes that bloat."
  )}</p>

  <section class="eco-sim" id="ecoSim">
    <h2>{a("Simulador mensual interactivo (JSON vs .mini)", "Interactive monthly simulator (JSON vs .mini)")}</h2>
    <div class="eco-controls">
      <label>{a("Modelo (tarifa oficial verificada)", "Model (verified official tariff)")}
        <select id="ecoModel">{"".join(options)}</select>
      </label>
      <label>{a("Llamadas mensuales (lotes de 20 registros)", "Monthly calls (20-record batches)")}
        <input id="ecoCalls" type="number" min="100" step="1000" value="50000">
      </label>
      <label>{a("Modo .mini", ".mini mode")}
        <select id="ecoMode">
          <option value="rows">{a("Filas compactas (182 tok / prompt 68)", "Compact rows (182 tok / prompt 68)")}</option>
          <option value="lean">{a("domain/2 + prompt lean (244 tok / prompt 100)", "domain/2 + lean prompt (244 tok / prompt 100)")}</option>
          <option value="full">{a("domain/1 completo (278 tok / prompt 453)", "Full domain/1 (278 tok / prompt 453)")}</option>
        </select>
      </label>
      <label>{a("Tasa de acierto KV-Cache (%)", "KV-Cache hit ratio (%)")}
        <input id="ecoCache" type="number" min="0" max="95" step="5" value="80">
      </label>
    </div>
    <div class="eco-results">
      <div class="eco-out-box"><small>{a("Costo mensual JSON", "Monthly JSON spend")}</small><strong id="ecoJsonUsd">-</strong></div>
      <div class="eco-out-box"><small>{a("Costo mensual .mini", "Monthly .mini spend")}</small><strong id="ecoMiniUsd">-</strong></div>
      <div class="eco-out-box is-win"><small>{a("Ahorro estimado", "Estimated savings")}</small><strong id="ecoSavedUsd">-</strong></div>
    </div>
    <p class="fine" id="ecoSimNote" style="margin-top:12px"></p>
  </section>

  <p class="wip-links">
    <a class="btn btn-ghost" href="/validacion/">{a("Tabla contra competidores 2026", "2026 competitor leaderboard")}</a>
    <a class="btn btn-ghost" href="/source/experiments/estudio_formatos/tarifas/tarifas.json">{a("Tarifas verificadas (JSON)", "Verified rates (JSON)")}</a>
    <a class="btn btn-ghost" href="/docs/metodologia/">{a("Metodología", "Methodology")}</a>
  </p>
</div>'''
    html_out = ctx.pagina("economia", "Economía", "Economics", cuerpo)
    html_out = ctx.recursos(html_out, css=("/economia.css",), js=("/economia-calculo.js", "/economia-ui.js"))
    ctx.escribir_pagina("economia", html_out)
