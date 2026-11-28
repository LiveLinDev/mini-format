"""Render the published transport and cloud comparisons from their measurements."""
from __future__ import annotations

import json
from pathlib import Path

from modulos import region

PUBLIC_RESULTS = Path(__file__).resolve().parents[1] / "benchmark" / "public"


def barras(filas):
    return "".join(f'''<li><div class="cost-label"><span>{etiqueta}</span><strong>{valor}</strong></div>
          <div class="cost-track" aria-hidden="true"><span style="--width:{ancho:.2%}"></span></div></li>'''
                   for etiqueta, valor, ancho in filas)


def resumen_transporte(datos, a):
    conjuntos = datos["datasets"].values()
    formatos = (("mini", ".mini"), ("toon_4_4", "TOON 4.4"), ("json_compact", a("JSON compacto", "Compact JSON")))
    totales = [sum(conjunto["tokenizers"]["o200k_base"][clave] for conjunto in conjuntos) for clave, _ in formatos]
    registros = sum(conjunto["records"] for conjunto in conjuntos)
    mini, toon, control = totales

    def numero(valor):
        texto = f"{valor:,}"
        return a(texto.replace(",", "."), texto)

    ahorro_json = f"{abs(100 * (1 - mini / control)):.1f}"
    comparacion = a(ahorro_json.replace(".", ","), ahorro_json) + "&nbsp;%"
    titulo = (a("Menos tokens que JSON compacto al enviar datos", "Fewer tokens than compact JSON when sending data")
              if mini <= control else a("Más tokens que JSON compacto al enviar datos", "More tokens than compact JSON when sending data"))
    diferencia_toon = f"{abs(100 * (1 - mini / toon)):.1f}"
    direccion_es, direccion_en = ("menos", "less") if mini <= toon else ("más", "more")
    ahorro_toon = a(f"{diferencia_toon.replace('.', ',')}&nbsp;% {direccion_es} que TOON 4.4",
                    f"{diferencia_toon}% {direccion_en} than TOON 4.4")
    registros_en = f"{registros:,}"
    epigrafe = a(f"Tokens para los mismos {registros_en.replace(',', '.')} registros",
                 f"Tokens for the same {registros_en} records")
    techo = max(totales)
    filas = [(etiqueta, numero(total), total / techo) for (_, etiqueta), total in zip(formatos, totales)]
    return f'''<div class="cost-overview transport-overview"><div class="cost-intro">
      <p class="cost-value">{comparacion}</p><h2>{titulo}</h2><p>{ahorro_toon}</p></div>
      <figure class="cost-figure"><figcaption>{epigrafe}</figcaption>
        <ul class="cost-bars">{barras(filas)}</ul>
        <p class="cost-scope">{a("Incluye esquemas y metadatos · o200k_base", "Includes schemas and metadata · o200k_base")}</p></figure></div>'''


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


def costo_telemetria_por_mil(resultado, precios, *, con_cache=False):
    if not resultado["exact"]:
        return None
    entrada = resultado["input_tokens"] * precios["input"]
    if con_cache:
        lectura = resultado["cached_input_tokens"]
        escritura = resultado["cache_write_input_tokens"]
        entrada += lectura * (precios["cached_input"] - precios["input"])
        entrada += escritura * (precios["cache_write_input"] - precios["input"])
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
    for etiqueta, costo in zip((".mini", a("JSON compacto", "Compact JSON")), costos):
        importe = "$" + decimal(costo, 4) if costo is not None else a("Sin aciertos", "No exact results")
        ancho = costo / techo if costo is not None and techo else 0
        filas.append((etiqueta, importe, ancho))

    grupos = cohorte["rows_per_case"]
    muestra = a(f"{len(grupos)} lotes de {min(grupos)} a {max(grupos)} filas · GPT-6 Luna",
                f"{len(grupos)} batches of {min(grupos)} to {max(grupos)} rows · GPT-6 Luna")
    res = a(f"Aciertos: .mini {mini['exact']}/{mini['trials']} · JSON {control['exact']}/{control['trials']}",
            f"Exact results: .mini {mini['exact']}/{mini['trials']} · JSON {control['exact']}/{control['trials']}")
    return f'''<div class="cost-overview"><div class="cost-intro">{comparacion}<h2>{titulo}</h2><p>{muestra}</p></div>
      <figure class="cost-figure"><figcaption>{a("Costo estimado por 1.000 respuestas correctas", "Estimated cost per 1,000 correct responses")}</figcaption>
        <ul class="cost-bars">{barras(filas)}</ul><p class="cost-scope">{res}</p></figure></div>'''


def inject_benchmarks(page: str, lang: str) -> str:
    data = json.loads((PUBLIC_RESULTS / "transport_results.json").read_text(encoding="utf-8"))
    def text(es, en):
        return es if lang == "es" else en
    return region(page, "RESUMEN DE COSTO", resumen_transporte(data, text))
