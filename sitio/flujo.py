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
<p class="eyebrow">{a("Automatización de soporte", "Support automation")}</p>
<h1>{a("De mensajes de soporte<br>a tickets listos para usar.", "From support messages<br>to usable tickets.")}</h1>
<p class="lead">{a("Una empresa recibe quejas y consultas de sus clientes. Su equipo pierde tiempo leyendo cada mensaje y creando un ticket a mano: una ficha con asunto, categoría y prioridad para asignar el problema.", "A company receives customer complaints and questions. Its team spends time reading each message and manually creating a ticket: a record with a title, category and priority to assign the issue.")}</p>
<p>{a("La empresa automatiza esa tarea. Su aplicación envía los mensajes a una IA, que los interpreta y genera un ticket por mensaje. Pide el resultado en JSON, un formato de datos que el código puede guardar y filtrar.", "The company automates this task. Its app sends messages to AI, which interprets them and generates one ticket per message. It requests JSON, a data format the code can store and filter.")}</p>
<div class="story-before"><div><h3>{a("Lo que escribe el cliente", "What the customer writes")}</h3><p>«No puedo entrar: mi contraseña dejó de funcionar.»</p></div><div><h3>{a("Lo que necesita la aplicación", "What the app needs")}</h3><pre>{{"id": 1, "titulo": "Error al iniciar sesión",
 "categoria": "acceso", "prioridad": "alta"}}</pre></div></div>
<p>{a("Aquí procesaremos 20 mensajes y obtendremos 20 objetos JSON: cada objeto es un ticket. .mini cambia cómo escribe la IA esa respuesta; el resultado para la aplicación conserva los mismos datos.", "Here we process 20 messages and get 20 JSON objects: each object is one ticket. .mini changes how AI writes that response; the application result keeps the same data.")}</p>
<section id="ahorro"><h2>{a("1. ¿Por qué cambiar la respuesta JSON?", "1. Why change the JSON response?")}</h2>
<p>{a('En cada ticket, JSON repite los nombres "titulo", "categoria" y "prioridad", además de comillas y signos. Esa repetición también se genera y se factura. Los tokens son fragmentos de texto: la API cuenta los que recibe (entrada) y los que genera (salida) para calcular el coste.', 'In every ticket, JSON repeats the field names "titulo", "categoria" and "prioridad", plus quotes and punctuation. This repetition is also generated and billed. Tokens are pieces of text: the API counts what it receives (input) and generates (output) to calculate cost.')}</p>
<p>{a("TOON reduce esa repetición declarando campos una vez en tablas. .mini también los declara una vez, en un contrato adaptado al dominio de la aplicación. El contrato fija el orden y los tipos; la IA escribe principalmente los valores. Por eso no hay que volver a escribir cada nombre en cada ticket.", "TOON reduces repetition by declaring fields once in tables. .mini also declares them once, in a contract tailored to the application's domain. The contract fixes their order and types; AI mostly writes values. Each ticket no longer repeats every field name.")}</p>
<p>{a("El mismo resultado de 20 tickets, contado con o200k_base:", "The same 20-ticket result, counted with o200k_base:")}</p>
<table><thead><tr><th>{a("Respuesta", "Response")}</th><th>{a("Tokens de salida", "Output tokens")}</th></tr></thead><tbody>{table}</tbody></table>
<p>{a(".mini usa un 37,2 % menos que JSON y un 8,6 % menos que TOON en esta salida. Menos tokens de salida pueden reducir esa parte de la factura.", ".mini uses 37.2% fewer output tokens than JSON and 8.6% fewer than TOON in this example. Fewer output tokens can reduce that part of the bill.")}</p>
<p class="aside">{a("No es el coste total: el prompt .mini de este caso tiene 571 tokens y la corrección también cuesta tokens. En lotes pequeños ese gasto puede superar el ahorro. Mide el flujo completo con tu modelo.", "This is not total cost: this case's .mini prompt has 571 tokens and correction also costs tokens. On small batches, this overhead can exceed the output saving. Measure the full workflow with your model.")}</p>
<a href="/economia/">{a("Explorar el coste completo →", "Explore total cost →")}</a>
</section>
<section id="integrar"><h2>{a("2. Prepara el formato y conecta tu aplicación", "2. Prepare the format and connect your app")}</h2>
<ol class="story-setup"><li><strong>{a("Guarda un JSON real de tu IA.", "Save a real JSON response from your AI.")}</strong> {a("Debe mostrar los campos y tipos que necesita tu aplicación.", "It should show the fields and types your application needs.")}</li>
<li><strong><code>mini setup</code></strong> {a("Elige español o inglés e indica tu muestra JSON. Crea contract.json (reglas de los campos), prompt.es.md o prompt.en.md (instrucciones para la IA) y workflow.py (código que comprueba y convierte la respuesta).", "Choose Spanish or English and your JSON sample. It creates contract.json (field rules), prompt.es.md or prompt.en.md (AI instructions) and workflow.py (code that checks and converts the response).")}</li>
<li><strong>{a("Elige el archivo que llama a tu IA.", "Select the file that calls your AI.")}</strong> {a("Setup prepara la integración en ese archivo. Tu código envía el contenido del prompt generado y pide .mini. El workflow valida, usa Repair, pide una corrección si hace falta, comprueba otra vez y convierte a JSON.", "Setup prepares integration in that file. Your code sends the generated prompt's contents and requests .mini. The workflow validates, uses Repair, requests a correction if needed, checks again and converts to JSON.")}</li>
<li><strong>{a("¿Todavía no tienes un flujo?", "No workflow yet?")}</strong> {a("Elige esa opción en setup. Conserva el kit: el comando para conectarlo más adelante queda en README.md y GUIA.md.", "Select that option in setup. Keep the toolkit: the command to connect it later is saved in README.md and GUIA.md.")}</li>
<li><strong>{a("Prueba antes de guardar datos reales.", "Test before storing real data.")}</strong> {a("Copia try-prompt.md a tu IA: pide 20 objetos ficticios con tu contrato. Un registro es un objeto; aquí, un ticket. El workflow comprueba toda la respuesta antes de entregarla.", "Paste try-prompt.md into your AI: it asks for 20 fictional objects using your contract. A record is one object; here, one ticket. The workflow checks the entire response before delivery.")}</li></ol>
<p>{a("La edición automática cubre un patrón Python de chat completions + json.loads. Para otros SDK y lenguajes se genera una guía con las rutas reales para tu IA de código. El callback permite conservar tu proveedor.", "Automatic editing covers a Python chat completions + json.loads pattern. Other SDKs and languages receive a coding-AI guide with actual paths. The callback keeps your provider.")}</p>
<a class="btn btn-solid" href="/docs/quickstart/">{a("Instalar y seguir la guía →", "Install and follow the guide →")}</a>
<details><summary>{a("Probar con una IA real y mi API key", "Try a real AI with my API key")}</summary>
<p>{a("Descarga el paquete, instálalo y abre el formulario local:", "Download and install the package, then open the local form:")}</p><pre><code>python examples/flujo-soporte/run.py --serve</code></pre>
<p>{a("El formulario tiene un campo para tu API key y el modelo. La clave se usa en memoria; no se guarda. Puedes seguir usando la grabación sin clave. Las llamadas reales y las correcciones se facturan por tu proveedor.", "The form has fields for your API key and model. The key stays in memory and is not saved. Replay remains available without a key. Your provider bills real calls and corrections.")}</p></details>
</section>
<section id="demo" aria-labelledby="demo-title"><h2 id="demo-title">{a("3. Sigue una ejecución, desde la IA hasta el JSON", "3. Follow a run, from AI to JSON")}</h2>
<p>{a("Repite una ejecución guardada de 20 tickets, sin API key. Muse escribió las respuestas de ejemplo; añadimos dos fallos para enseñar la reparación. El contrato, el validador, el reparador y el parser Python sí se ejecutaron.", "Replay a saved 20-ticket run without an API key. Muse authored the example responses; two errors were inserted to demonstrate repair. The contract, validator, repairer and Python parser were actually executed.")}</p>
<div class="story-actions"><button class="btn btn-solid" id="story-run" type="button">{a("Reproducir flujo guardado", "Replay saved workflow")}</button><button class="btn btn-ghost" id="story-next" type="button">{a("Ver paso a paso", "Step through")}</button></div>
<p id="story-status" role="status" aria-live="polite">{a("Listo. No se llamará a una API.", "Ready. No API call will be made.")}</p>
<ol id="story-steps" class="story-steps"></ol>
<noscript><p>{a("Historial guardado de la ejecución:", "Saved execution history:")}</p><pre>{html.escape(json.dumps(history, ensure_ascii=False, indent=2))}</pre></noscript>
<details><summary>{a("Ver los 20 mensajes de entrada", "See the 20 input messages")}</summary><pre>{html.escape(json.dumps(inputs, ensure_ascii=False, indent=2))}</pre></details>
<details id="story-output" hidden><summary>{a("JSON que recibe la aplicación · 20 tickets", "Application JSON · 20 tickets")}</summary><pre id="story-json"></pre></details>
<details><summary>{a("Historial: respuesta, error y corrección", "History: response, error and correction")}</summary><pre id="story-history"></pre><button class="btn btn-ghost" id="story-save" type="button">{a("Descargar historial JSON", "Download JSON history")}</button><p>{a("Las repeticiones se guardan sólo en este navegador.", "Replays are saved only in this browser.")}</p><ul id="story-runs"></ul></details>
</section>
<p><a href="/playground/">{a("Probar el formato en el playground", "Try the format in the playground")}</a> · <a href="/ejemplo/">{a("Más ejemplos", "More examples")}</a></p>
</div><script id="story-data" type="application/json">{payload}</script>'''
    page = ctx.pagina("flujo", "Un flujo completo", "A complete workflow", cuerpo, css=("/flujo.css",), js=("/flujo.js",), activo="flujo")
    ctx.escribir_pagina("flujo", page)
