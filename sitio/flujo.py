"""One application story, backed by a replayable Python workflow history."""
from __future__ import annotations

import html
import json


def construir(ctx):
    a = ctx.ambos
    base = ctx.root / "examples" / "flujo-soporte"
    history = json.loads((base / "history.json").read_text(encoding="utf-8"))
    comparison = json.loads((base / "comparison.json").read_text(encoding="utf-8"))
    inputs = json.loads((base / "messages.json").read_text(encoding="utf-8"))
    tokens = comparison["tokens"]
    table = ''.join(f'<tr><td>{name}</td><td>{tokens[key]}</td></tr>' for name, key in (("JSON", "json"), ("TOON", "toon"), (".mini", "mini")))
    payload = json.dumps({"history": history, "inputs": inputs}, ensure_ascii=False).replace("<", "\\u003c")
    cuerpo = f'''<div class="wrap story">
<p class="eyebrow">{a("Un caso completo", "One complete use case")}</p>
<h1>{a("De mensajes de soporte<br>a tickets listos para usar.", "From support messages<br>to usable tickets.")}</h1>
<p class="lead">{a("Tu aplicación recibe 20 mensajes. Le pide a la IA que extraiga el asunto, la categoría y la prioridad. Necesita JSON para guardar, filtrar y asignar los tickets.", "Your app receives 20 messages. It asks AI to extract each title, category and priority. It needs JSON to store, filter and assign tickets.")}</p>
<p>{a("Con .mini cambia la respuesta de la IA. Tu aplicación recibe el mismo JSON al final.", "With .mini, the AI response changes. Your app receives the same JSON at the end.")}</p>
<div class="story-route" aria-label="Workflow">{a("Mensajes → IA → .mini → validar → reparar → JSON", "Messages → AI → .mini → validate → repair → JSON")}</div>
<section id="demo" aria-labelledby="demo-title"><h2 id="demo-title">{a("Mira el flujo en acción", "See the workflow in action")}</h2>
<p>{a("Repite una ejecución guardada de 20 tickets, sin API key. Muse escribió las respuestas de ejemplo; añadimos dos fallos para enseñar la reparación. El contrato, el validador, el reparador y el parser Python sí se ejecutaron.", "Replay a saved 20-ticket run without an API key. Muse authored the example responses; two errors were inserted to demonstrate repair. The contract, validator, repairer and Python parser were actually executed.")}</p>
<div class="story-actions"><button class="btn btn-solid" id="story-run" type="button">{a("Reproducir flujo guardado", "Replay saved workflow")}</button><button class="btn btn-ghost" id="story-next" type="button">{a("Ver paso a paso", "Step through")}</button></div>
<p id="story-status" role="status" aria-live="polite">{a("Listo. No se llamará a una API.", "Ready. No API call will be made.")}</p>
<ol id="story-steps" class="story-steps"></ol>
<noscript><p>{a("Historial guardado de la ejecución:", "Saved execution history:")}</p><pre>{html.escape(json.dumps(history, ensure_ascii=False, indent=2))}</pre></noscript>
<details><summary>{a("Ver los 20 mensajes de entrada", "See the 20 input messages")}</summary><pre>{html.escape(json.dumps(inputs, ensure_ascii=False, indent=2))}</pre></details>
<details id="story-output" hidden><summary>{a("JSON que recibe la aplicación · 20 tickets", "Application JSON · 20 tickets")}</summary><pre id="story-json"></pre></details>
<details><summary>{a("Historial: respuesta, error y corrección", "History: response, error and correction")}</summary><pre id="story-history"></pre><button class="btn btn-ghost" id="story-save" type="button">{a("Descargar historial JSON", "Download JSON history")}</button><p>{a("Las repeticiones se guardan sólo en este navegador.", "Replays are saved only in this browser.")}</p><ul id="story-runs"></ul></details>
</section>
<section id="ahorro"><h2>{a("¿Qué ahorra en este ejemplo?", "What does this example save?")}</h2>
<p>{a("El mismo resultado de 20 tickets, contado con o200k_base:", "The same 20-ticket result, counted with o200k_base:")}</p>
<table><thead><tr><th>{a("Respuesta", "Response")}</th><th>{a("Tokens de salida", "Output tokens")}</th></tr></thead><tbody>{table}</tbody></table>
<p>{a(".mini usa un 37,2 % menos que JSON y un 8,6 % menos que TOON en esta salida. Menos tokens de salida pueden reducir esa parte de la factura.", ".mini uses 37.2% fewer output tokens than JSON and 8.6% fewer than TOON in this example. Fewer output tokens can reduce that part of the bill.")}</p>
<p class="aside">{a("No es el coste total: el prompt .mini de este caso tiene 571 tokens y la corrección también cuesta tokens. En lotes pequeños ese gasto puede superar el ahorro. Mide el flujo completo con tu modelo.", "This is not total cost: this case's .mini prompt has 571 tokens and correction also costs tokens. On small batches, this overhead can exceed the output saving. Measure the full workflow with your model.")}</p>
<a href="/economia/">{a("Explorar el coste completo →", "Explore total cost →")}</a>
</section>
<section id="integrar"><h2>{a("Ahora conéctalo a tu aplicación", "Now connect your application")}</h2>
<ol class="story-setup"><li><strong>{a("Guarda un JSON real de tu IA.", "Save a real JSON response from your AI.")}</strong> {a("Debe mostrar los campos y tipos que necesita tu aplicación.", "It should show the fields and types your application needs.")}</li>
<li><strong><code>mini setup</code></strong> {a("Elige español o inglés, indica la muestra y crea tu contrato y prompt.", "Choose Spanish or English, select the sample and create your contract and prompt.")}</li>
<li><strong>{a("Prueba 20 registros.", "Try 20 records.")}</strong> {a("El asistente prepara un prompt de prueba. Valida la respuesta; usa Repair si hace falta.", "The wizard prepares a test prompt. Validate the response; use Repair if needed.")}</li>
<li><strong>{a("Elige Integración en el asistente.", "Choose Integration in the wizard.")}</strong> {a("Localiza tu llamada a IA. El puente lee el prompt generado, obtiene .mini, valida, repara, vuelve a validar y entrega JSON.", "Locate your AI call. The bridge reads the generated prompt, gets .mini, validates, repairs, revalidates and returns JSON.")}</li></ol>
<p>{a("La edición automática cubre un patrón Python de chat completions + json.loads. Para otros SDK y lenguajes se genera una guía con las rutas reales para tu IA de código. El callback permite conservar tu proveedor.", "Automatic editing covers a Python chat completions + json.loads pattern. Other SDKs and languages receive a coding-AI guide with actual paths. The callback keeps your provider.")}</p>
<a class="btn btn-solid" href="/docs/quickstart/">{a("Instalar y seguir la guía →", "Install and follow the guide →")}</a>
<details><summary>{a("Probar con una IA real y mi API key", "Try a real AI with my API key")}</summary>
<p>{a("Descarga el paquete, instálalo y abre el formulario local:", "Download and install the package, then open the local form:")}</p><pre><code>python examples/flujo-soporte/run.py --serve</code></pre>
<p>{a("El formulario tiene un campo para tu API key y el modelo. La clave se usa en memoria; no se guarda. Puedes seguir usando la grabación sin clave. Las llamadas reales y las correcciones se facturan por tu proveedor.", "The form has fields for your API key and model. The key stays in memory and is not saved. Replay remains available without a key. Your provider bills real calls and corrections.")}</p></details>
</section>
<p><a href="/playground/">{a("Probar el formato en el playground", "Try the format in the playground")}</a> · <a href="/ejemplo/">{a("Más ejemplos", "More examples")}</a></p>
</div><script id="story-data" type="application/json">{payload}</script>'''
    page = ctx.pagina("flujo", "Un flujo completo", "A complete workflow", cuerpo, css=("/flujo.css",), js=("/flujo.js",), activo="flujo")
    ctx.escribir_pagina("flujo", page)
