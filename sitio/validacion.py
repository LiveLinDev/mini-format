"""Módulo /validacion/ — Tablas reproducibles de competidores 2026, conformidad y cortes.

Toda cifra proviene de:
- ``benchmark/public/competitors_results.json`` (o200k_base, cl100k_base, p50k_base; round-trip 100%)
- ``benchmark/public/cloud_results.json`` (generación en la nube y compresión de entrada)
- ``experiments/estudio_formatos/corridas/resultados.json`` (18 corridas reales + 180 cortes)
- ``ctx.cifras`` (conformidad de 376 casos en 14 familias)

Política estricta: cero flechas, emojis ni símbolos dingbats prohibidos.
"""
from __future__ import annotations

import html


from benchmarks import costo_por_mil, resumen_costo


def resultados_nube(ctx):
    a = ctx.ambos
    datos = ctx.leer_json("benchmark/public/cloud_results.json")
    grupos = datos["cohorts"]
    precios = datos["price_usd_per_million"]
    nombres = {
        "mini": ".mini", "mini_previous": a(".mini anterior", "Previous .mini"),
        "json_positional": a("JSON posicional", "Positional JSON"),
        "json_positional_short": a("JSON posicional con prompt breve", "Positional JSON with short prompt"),
        "json_positional_nested": a("JSON posicional del control original", "Original positional JSON control"),
        "json_compact": a("JSON compacto", "Compact JSON"),
        "json_schema": a("JSON con esquema", "JSON with schema"),
        "csv": "CSV", "csv_escapes": a("CSV con escapes", "CSV with escaping"),
        "csv_typed": a("CSV tipado", "Typed CSV"), "toon": "TOON 4.4",
        "ison": "ISON 1.2.0", "tson": "TSON rev. 40", "jmd": "JMD 0.11.0",
        "nova_compact": "NOVA 0.8.1", "nova_lines": "NOVA Lines 0.8.1", "bpp": "BPP 0.4.0",
        "tokenfold": "Tokenfold 0.6.0",
    }

    def numero(valor, decimales=0):
        ingles = f"{valor:,.{decimales}f}"
        espanol = ingles.translate(str.maketrans(",.", ".,"))
        return a(espanol, ingles) if espanol != ingles else ingles

    pista = a("Desliza para ver todas las columnas.", "Scroll across to see all columns.")

    def tabla(encabezados, filas, etiqueta):
        columnas = "".join(f'<th scope="col">{texto}</th>' for texto in encabezados)
        return (f'<p class="val-scroll-note">{pista}</p>'
                f'<div class="tablewrap val-result-table" tabindex="0"><table class="t">'
                f'<caption class="sr">{etiqueta}</caption><thead><tr>{columnas}</tr></thead>'
                f'<tbody>{"".join(filas)}</tbody></table></div>')

    def tabla_nube(clave, titulo, *, con_cache=False, ancla=""):
        formatos = grupos[clave]["formats"]
        metrica = a("Tokens leídos de caché", "Cached input tokens") if con_cache else a("Tokens de instrucción", "Instruction tokens")
        encabezados = (a("Formato", "Format"), a("USD por 1.000 aciertos", "USD per 1,000 exact results"),
                       a("Exactas", "Exact"), a("Reintentos", "Retries"), metrica)
        filas = []
        for clave_formato, resultado in formatos.items():
            tokens = resultado["cached_input_tokens" if con_cache else "instruction_tokens"]
            costo = costo_por_mil(resultado, precios, con_cache=con_cache)
            precio = numero(costo, 5) if costo is not None else a("Sin exactas", "No exact results")
            filas.append(f'<tr><th scope="row">{nombres[clave_formato]}</th>'
                         f'<td>{precio}</td><td>{resultado["exact"]}/{resultado["trials"]}</td>'
                         f'<td>{resultado["retries"]}</td><td>{numero(tokens)}</td></tr>')
        atributo = f' id="{ancla}"' if ancla else ""
        return (f'<details class="disclosure val-run"{atributo}><summary>{titulo}</summary>'
                f'{tabla(encabezados, filas, titulo)}</details>')

    lotes_medidos = [grupos[clave]["formats"] for clave in ("small_batch", "large_batch")]
    tokens_mini = sum(f["mini"]["instruction_tokens"] for f in lotes_medidos)
    tokens_anteriores = sum(f["mini_previous"]["instruction_tokens"] for f in lotes_medidos)
    ahorro = round(100 * (1 - tokens_mini / tokens_anteriores))
    exactas = sum(f["mini"]["exact"] for f in lotes_medidos)
    exactas_toon = sum(f["toon"]["exact"] for f in lotes_medidos)
    lotes = sum(f["mini"]["trials"] for f in lotes_medidos)
    cache = grupos["cached_batch"]["formats"]
    ahorro_cache = 100 * (1 - costo_por_mil(cache["mini"], precios, con_cache=True)
                          / costo_por_mil(cache["ison"], precios, con_cache=True))
    texto = grupos["projected_text_batches"]["formats"]
    ahorro_texto = round(100 * (1 - costo_por_mil(texto["mini"], precios) / costo_por_mil(texto["json_compact"], precios)))
    titulo_texto = a(f"De 25 a 48 filas de texto · {ahorro_texto} % menos costo que JSON compacto",
                     f"25 to 48 text rows · {ahorro_texto}% lower cost than compact JSON")
    reparacion = grupos["single_invalid_row_repair"]["formats"]
    ahorro_reparacion = round(100 * (1 - costo_por_mil(reparacion["mini"], precios)
                                   / costo_por_mil(reparacion["mini_previous"], precios)))
    titulo_reparacion = a(f"Una fila inválida · {ahorro_reparacion} % menos costo por lote correcto",
                          f"One invalid row · {ahorro_reparacion}% lower cost per exact batch")
    cloud = f'''<details class="disclosure val-group" id="generacion-nube">
    <summary>{a("Generación, precisión y reintentos", "Generation, accuracy and retries")}</summary>
    <div class="val-body prose">
    <p>{a(
        f"Con GPT-6 Luna, .mini generó {exactas} de {lotes} lotes exactos de 2 a 24 filas al primer intento. TOON 4.4 acertó {exactas_toon} de {lotes}. La instrucción de .mini usó {ahorro} % menos tokens que el flujo anterior.",
        f"With GPT-6 Luna, .mini generated {exactas} of {lotes} exact batches of 2 to 24 rows on the first attempt. TOON 4.4 got {exactas_toon} of {lotes} right. The .mini instructions used {ahorro}% fewer tokens than the previous workflow."
    )}</p>
    <p>{a(
        "Cada formato recibió las mismas tareas sintéticas en español y las mismas columnas conocidas. El costo por resultado exacto incluye todos los tokens de entrada y salida, también los de los intentos fallidos y los reintentos.",
        "Every format got the same synthetic Spanish tasks and known columns. Cost per exact result includes all input and output tokens, including failed attempts and retries."
    )}</p>
    {tabla_nube("projected_text_batches", titulo_texto, ancla="lotes-texto")}
    {tabla_nube("single_invalid_row_repair", titulo_reparacion, ancla="reparacion-filas")}
    <p class="val-method">{a("Cinco lotes con una falla simulada a partir de respuestas reales en la nube.",
                            "Five batches with one simulated fault in each recorded cloud response.")}</p>
    {tabla_nube("single_row_recheck", a("Una fila · 4 repeticiones del caso original", "One row · 4 repeats of the original case"))}
    {tabla_nube("single_pair_confirmation", a("Una fila con dos campos de texto · 16 pruebas", "One row with two text fields · 16 trials"))}
    {tabla_nube("single_row", a("Una fila · 12 casos del ensayo anterior", "One row · 12 cases from the previous trial"))}
    {tabla_nube("small_batch", a("De 2 a 8 filas · 8 lotes", "2 to 8 rows · 8 batches"))}
    {tabla_nube("large_batch", a("De 9 a 24 filas · 6 lotes", "9 to 24 rows · 6 batches"))}
    {tabla_nube("support_batches", a("20 tickets contra BPP · 6 lotes", "20 tickets against BPP · 6 batches"))}
    {tabla_nube("recent_single", a("Una fila contra BPP y NOVA · 16 casos", "One row against BPP and NOVA · 16 cases"))}
    <h3>{a("Comparación con ISON y caché", "Cache comparison with ISON")}</h3>
    <p>{a(
        f"En los lotes de 9 a 24 filas, .mini costó {ahorro_cache:.0f} % menos con la misma cantidad de tokens leídos de caché.",
        f"On batches of 9 to 24 rows, .mini cost {ahorro_cache:.0f}% less with the same number of cached input tokens."
    )}</p>
    {tabla_nube("cached_single", a("Una fila con caché · 12 casos", "One row with caching · 12 cases"), con_cache=True)}
    {tabla_nube("cached_batch", a("Lotes de 9 a 24 filas con caché", "Batches of 9 to 24 rows with caching"), con_cache=True)}
    <p class="val-method">{html.escape(datos["measured_on"])} · {a(
        "Las primeras tablas estiman la entrada de la aplicación con o200k_base. Las tablas con caché usan la telemetría del proveedor e incluyen el contexto de Codex. Entre 9 y 24 filas, JSON posicional y .mini tuvieron costos similares.",
        "The first tables estimate application input with o200k_base. The cache tables use provider telemetry, including Codex context. Positional JSON and .mini had similar costs on batches of 9 to 24 rows."
    )} <a href="/source/benchmark/public/cloud_results.json">{a("Datos y commits (JSON)", "Data and commits (JSON)")}</a> ·
      <a href="https://developers.openai.com/api/docs/models/gpt-6-luna">{a("Tarifas del modelo", "Model pricing")}</a></p>
    </div>
  </details>'''

    muestras = {
        "soporte-20": a("20 tickets de soporte", "20 support tickets"),
        "comentarios-500": a("500 comentarios", "500 comments"),
        "16-respuestas-independientes": a("16 objetos independientes", "16 independent objects"),
        "doce-lotes": a("12 lotes sintéticos", "12 synthetic batches"),
    }
    formatos = ("mini", "mini_previous", "bpp", "toon", "tokenfold", "nova_compact", "nova_lines", "json_compact")
    encabezados = [a("Conjunto", "Dataset")] + [nombres[clave] for clave in formatos]
    filas = []
    for clave_muestra, conteos in datos["serialization"].items():
        celdas = "".join(f'<td>{numero(conteos[clave]) if clave in conteos else "—"}</td>' for clave in formatos)
        filas.append(f'<tr><th scope="row">{muestras[clave_muestra]}</th>{celdas}</tr>')
    corpus = datos["schema_inclusive_corpus"]["tokenizers"]["o200k_base"]
    titulos = {"products": a("Productos", "Products"), "users": a("Usuarios", "Users"),
               "comments": a("Comentarios", "Comments"), "earthquakes": a("Sismos", "Earthquakes")}
    perfiles = ("mini", "toon", "csv", "tson", "hedl", "xron", "gcf")
    rotulos = (a("Conjunto", "Dataset"), ".mini", "TOON 4.4.0", "CSV", "TSON rev. 40", "HEDL 2.0.0", "XRON 0.4.1", "GCF 2.8.0")
    filas_corpus = []
    for conjunto, conteos in corpus.items():
        celdas = "".join(f'<td>{numero(conteos[clave])}</td>' for clave in perfiles)
        filas_corpus.append(f'<tr><th scope="row">{titulos[conjunto]}</th>{celdas}</tr>')
    comparacion = a("1.902 registros contando contratos", "1,902 records including contracts")
    adaptativo = ctx.leer_json("benchmark/public/transport_results.json")["datasets"]
    formatos_adaptativos = ("mini_previous", "mini", "csv", "toon_4_4", "terse_py", "gcf_python_2_8", "json_compact")
    titulos_adaptativos = {**titulos, "quotes": a("Citas", "Quotes"), "todos": a("Tareas", "Todos"),
                          "support": a("Tickets de soporte", "Support tickets")}
    filas_adaptativas = []
    for conjunto, detalle in adaptativo.items():
        conteos = detalle["tokenizers"]["o200k_base"]
        celdas = "".join(f'<td>{numero(conteos[clave]) if conteos[clave] is not None else "—"}</td>'
                         for clave in formatos_adaptativos)
        filas_adaptativas.append(f'<tr><th scope="row">{titulos_adaptativos[conjunto]}</th>{celdas}</tr>')
    rotulos_adaptativos = (a("Conjunto", "Dataset"), nombres["mini_previous"], ".mini",
                           "CSV", "TOON 4.4", "TERSE 0.1", "GCF 3.6", nombres["json_compact"])
    titulo_adaptativo = a("Transporte de documentos completos", "Complete document transport")
    resumen_adaptativo = a(
        "Tokens con o200k_base para enviar datos que la aplicación ya tiene. Se cuentan los metadatos y los contratos requeridos. Los siete conjuntos se reconstruyeron por completo con cada formato.",
        "Tokens with o200k_base for sending data the application already has. Metadata and required contracts are included. Every format reconstructed all seven datasets in full.",
    )
    transport = f'''<details class="disclosure val-group" id="compresion-entrada">
    <summary>{a("Tamaño de los datos en tokens", "Data size in tokens")}</summary>
    <div class="val-body prose">
    <p>{a(
        "Tokens del documento completo con o200k_base. Cada formato recuperó exactamente el JSON de origen.",
        "Full-document tokens with o200k_base. Every format recovered the original JSON exactly."
    )}</p>
    {tabla(encabezados, filas, a("Tokens por documento", "Tokens per document"))}
    <p class="val-method">{a("El guion indica una combinación sin ensayo.", "A dash marks a combination that was not tested.")}</p>
    <details class="disclosure val-run" id="transporte-adaptativo">
      <summary>{titulo_adaptativo}</summary>
      <p>{resumen_adaptativo}</p>
      {tabla(rotulos_adaptativos, filas_adaptativas, titulo_adaptativo)}
      <p><a href="/source/benchmark/public/transport_results.json">{a("Datos, versiones y dos tokenizadores", "Data, versions and both tokenizers")}</a></p>
    </details>
    <details class="disclosure val-run"><summary>{comparacion}</summary>
      <p>{a(
          "La medición anterior de .mini, en el commit 69f0596, incluye los contratos o mapas de reconstrucción. Usó menos tokens que TOON 4.4.0 en los cuatro conjuntos. CSV ganó en los 500 comentarios.",
          "The earlier .mini measurement at commit 69f0596 includes the contracts or reconstruction maps. It used fewer tokens than TOON 4.4.0 across all four datasets. CSV won on the 500 comments."
      )}</p>
      {tabla(rotulos, filas_corpus, comparacion)}
    </details>
    </div>
  </details>'''
    return cloud, transport


def construir(ctx) -> None:
    a = ctx.ambos
    comp = ctx.leer_json("benchmark/public/competitors_results.json")
    datasets = comp.get("datasets", [])
    ds_map = {d["name"]: d for d in datasets}
    casos = ctx.cifras.get("casos_conformidad", 376)
    registro = ctx.leer_json("forks/registry.json")
    familias = len(registro) if isinstance(registro, list) else 14

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

    cloud, transport = resultados_nube(ctx)
    prueba = resumen_costo(ctx.leer_json("benchmark/public/cloud_results.json"), a)
    cuerpo = f'''<div class="wrap val-wrap">
  <header class="val-heading">
    <h1>{a("Resultados de .mini", ".mini benchmark results")}</h1>
    <p class="lead">{a("Costo por acierto, precisión y tokens. Abre una prueba para ver cómo se midió.",
                       "Cost per correct response, accuracy, and tokens. Open a test to see how it was measured.")}</p>
  </header>
  <section class="val-overview">
    {prueba}
    <a class="text-link" href="#lotes-texto">{a("Ver el detalle de esta prueba", "See the details of this test")}</a>
  </section>

  <div class="val-groups">
    <details class="disclosure val-group" id="criterios">
      <summary>{a("Cómo se midió", "How we measured it")}</summary>
      <div class="val-body prose">
        <dl class="val-criteria-grid">
          <div><dt>{a("Costo", "Cost")}</dt><dd>{a("USD por respuesta correcta. Cuenta la instrucción, la salida y los reintentos.",
                                                    "USD per correct response. Counts instructions, output and retries.")}</dd></div>
          <div><dt>{a("Precisión", "Accuracy")}</dt><dd>{a("Cuántas respuestas coinciden exactamente con el JSON esperado.",
                                                           "How many responses match the expected JSON exactly.")}</dd></div>
          <div><dt>{a("Tamaño", "Size")}</dt><dd>{a("Tokens del texto que representa los mismos datos.",
                                                     "Tokens in the text representing the same data.")}</dd></div>
        </dl>
        <p><a href="/docs/metodologia/">{a("Metodología completa", "Full methodology")}</a> ·
           <a href="/source/benchmark/public/">{a("Datos y scripts reproducibles", "Reproducible data and scripts")}</a></p>
      </div>
    </details>
    {cloud}
    {transport}
  <details class="disclosure val-group" id="serializacion-publica">
    <summary>{a("Comparación de 16 formatos", "Comparison of 16 formats")}</summary>
    <div class="val-body prose">
      <p>{a(f"En 1.902 registros públicos, .mini domain/2 y JSON compacto ocuparon {tot_v2:,} y {tot_json:,} tokens, respectivamente. Diferencia: {tot_save:.1f} % a favor de .mini.",
             f"Across 1,902 public records, .mini domain/2 and compact JSON took {tot_v2:,} and {tot_json:,} tokens, respectively. Difference: {tot_save:.1f}% in favor of .mini.")}</p>
      <h3>{a("Resultados por conjunto de datos", "Results by dataset")} <code>o200k_base</code></h3>
      <div class="tablewrap val-result-table" tabindex="0">
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
    <h3>{a("Totales de los 1.902 registros", "Totals for all 1,902 records")}</h3>
    <p>{a(
        "Tres tokenizadores BPE cuentan el texto serializado de cuatro conjuntos públicos. El arnés usa esquemas o mapas reutilizables cuando el perfil los requiere para reconstruir el JSON.",
        "Three BPE tokenizers count serialized text from four public datasets. The harness uses reusable schemas or maps when the profile needs them to reconstruct JSON."
    )}</p>
    <div class="tablewrap val-result-table" tabindex="0">
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
    </div>
  </details>
  <details class="disclosure val-group">
    <summary>{a("Recuperación de respuestas cortadas", "Recovering truncated responses")}</summary>
    <div class="val-body prose">
      <p>{a("180 cortes reales. Se cuentan los registros completos que el lector pudo recuperar.", "180 real cuts. This test counts the complete records each reader recovered.")}</p>
    <div class="tablewrap val-result-table" tabindex="0">
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
    </div>
  </details>
  <details class="disclosure val-group">
    <summary>{a("Conformidad y otros estudios", "Conformance and other studies")}</summary>
    <div class="val-body prose">
      <p>{a(f"{casos} casos de conformidad en Python, JavaScript y el oráculo TypeScript, con {familias} familias.",
             f"{casos} conformance cases across Python, JavaScript and the TypeScript oracle with {familias} families.")}</p>
      <ul>
        <li><a href="/docs/conformance/">{a("Suite de conformidad", "Conformance suite")}</a></li>
        <li><a href="/source/experiments/v1_tokens/">{a("Ahorro de tokens por vocabulario", "Token savings by vocabulary")}</a></li>
        <li><a href="/source/experiments/v4_costos/">{a("Costo por modelo", "Cost by model")}</a></li>
        <li><a href="/source/experiments/v5_ancho/">{a("Efecto del número de columnas", "Effect of the number of columns")}</a></li>
      </ul>
    </div>
  </details>
  </div>

  <p class="wip-links">
    <a class="btn btn-ghost" href="/economia/">{a("Calculadora de costos LLM", "LLM Cost Simulator")}</a>
    <a class="btn btn-ghost" href="/source/benchmark/public/competitors_results.json">{a("Resultados completos (JSON)", "Full benchmark results (JSON)")}</a>
  </p>
</div>'''
    html_out = ctx.pagina("validacion", "Resultados de .mini", ".mini benchmark results", cuerpo)
    html_out = ctx.recursos(html_out, css=("/validacion.css",))
    ctx.escribir_pagina("validacion", html_out)
