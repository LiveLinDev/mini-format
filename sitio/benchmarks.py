"""Render the published cloud comparison using the same cost model as its tables."""
from __future__ import annotations

import json
from pathlib import Path

from modulos import region

CLOUD_RESULTS = Path(__file__).resolve().parents[1] / "benchmark" / "public" / "cloud_results.json"


def costo_por_mil(resultado, precios, *, con_cache=False):
    if not resultado["exact"]:
        return None
    if con_cache:
        cache = resultado["cached_input_tokens"]
        entrada = (resultado["input_tokens"] - cache) * precios["input"] + cache * precios["cached_input"]
    else:
        entrada = resultado["application_input_tokens"] * precios["input"]
    salida = resultado["output_tokens"] * precios["output"]
    return (entrada + salida) / (1000 * resultado["exact"])


def resumen_costo(datos, a):
    cohorte = datos["cohorts"]["projected_text_batches"]
    formatos = cohorte["formats"]
    mini = formatos["mini"]
    control = formatos["json_compact"]
    precios = datos["price_usd_per_million"]
    costos = [costo_por_mil(medicion, precios) for medicion in (mini, control)]
    medida_mini, medida_json = costos

    def decimal(valor, decimales):
        en = f"{valor:.{decimales}f}"
        return a(en.replace(".", ","), en)

    comparacion = ""
    titulo = a("Costo de generación", "Generation cost")
    if medida_mini is not None and medida_json:
        diferencia = 100 * (1 - medida_mini / medida_json)
        if round(diferencia, 1):
            comparacion = f'<p class="cost-value">{decimal(abs(diferencia), 1)}&nbsp;%</p>'
            titulo = (a("Menos costo que JSON compacto", "Lower cost than compact JSON") if diferencia > 0
                      else a("Más costo que JSON compacto", "Higher cost than compact JSON"))

    techo = max((costo for costo in costos if costo is not None), default=0)
    filas = []
    for etiqueta, costo, medicion in zip((".mini", a("JSON compacto", "Compact JSON")), costos, (mini, control)):
        importe = "$" + decimal(costo, 4) if costo is not None else a("Sin aciertos", "No exact results")
        ancho = costo / techo if costo is not None and techo else 0
        filas.append(f'''<li><div class="cost-label"><span>{etiqueta}</span><strong>{importe}</strong></div>
          <div class="cost-track" aria-hidden="true"><span style="--width:{ancho:.2%}"></span></div></li>''')

    grupos = cohorte["rows_per_case"]
    muestra = a(f"{len(grupos)} lotes de {min(grupos)} a {max(grupos)} filas · GPT-6 Luna",
                f"{len(grupos)} batches of {min(grupos)} to {max(grupos)} rows · GPT-6 Luna")
    res = a(f"Aciertos: .mini {mini['exact']}/{mini['trials']} · JSON {control['exact']}/{control['trials']}",
            f"Exact results: .mini {mini['exact']}/{mini['trials']} · JSON {control['exact']}/{control['trials']}")
    return f'''<div class="cost-overview"><div class="cost-intro">{comparacion}<h2>{titulo}</h2><p>{muestra}</p></div>
      <figure class="cost-figure"><figcaption>{a("Costo estimado por 1.000 respuestas correctas", "Estimated cost per 1,000 correct responses")}</figcaption>
        <ul class="cost-bars">{"".join(filas)}</ul><p class="cost-scope">{res}</p></figure></div>'''


def inject_benchmarks(page: str, lang: str) -> str:
    data = json.loads(CLOUD_RESULTS.read_text(encoding="utf-8"))
    def text(es, en):
        return es if lang == "es" else en
    return region(page, "RESUMEN DE COSTO", resumen_costo(data, text))
