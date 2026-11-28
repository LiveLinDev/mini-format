"""Interactive preview of the compact rows accepted by the published SDK."""

from html import escape
import json

from minifmt.domain import decode_rows, encode_rows, infer_contract


def construir(ctx):
    """The full walkthrough is available at /flujo/."""


def muestra(campos, filas):
    tickets = [dict(zip(campos, fila)) for fila in filas]
    contrato = infer_contract([tickets], "ticket")
    opciones = {"last_text_field": campos[-1]}
    compacto = encode_rows(tickets, contrato, **opciones)
    restaurado = decode_rows(compacto, contrato, expected_records=len(tickets), **opciones)
    if restaurado != tickets:
        raise ValueError("La muestra de la portada no conserva los tickets")

    def par(campo, valor):
        return (f'<span class="key">{escape(json.dumps(campo, ensure_ascii=False))}</span>:'
                f'<span class="string">{escape(json.dumps(valor, ensure_ascii=False))}</span>')

    registros = []
    for ticket in restaurado:
        pares = [par(campo, valor) for campo, valor in ticket.items()]
        registros.append("  {" + ", ".join(pares[:2]) + ",\n   " + pares[2] + "}")
    visibles = []
    for fila in compacto.splitlines():
        categoria, prioridad, titulo = fila.split(" ", 2)
        visibles.append(f'<span class="key">{escape(categoria)}</span> '
                        f'<span class="priority">{escape(prioridad)}</span> {escape(titulo)}')
    return "\n".join(visibles), "[\n" + ",\n".join(registros) + "\n]"


def inyectar_portada(html, ctx):
    a = ctx.ambos
    campos_es = ("categoria", "prioridad", "titulo")
    campos_en = ("category", "priority", "title")
    mini_es, json_es = muestra(campos_es, (("cuenta", "alta", "Error al iniciar sesión"),
                                         ("pago", "media", "Cobro duplicado")))
    mini_en, json_en = muestra(campos_en, (("account", "high", "Sign-in error"),
                                         ("payment", "medium", "Duplicate charge")))
    campos = "".join(f'<li><code>{a(es, en)}</code><span>{a("Texto", "Text")}</span></li>'
                     for es, en in zip(campos_es, campos_en))

    cuerpo = f'''<section class="wrap workbench-wrap" id="como-funciona">
  <figure class="workbench" id="por-que" aria-labelledby="example-caption">
    <figcaption class="workbench-header" id="example-caption">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linejoin="round" aria-hidden="true"><rect x="3" y="5" width="18" height="14" rx="2"/><path d="m7 9 3 3-3 3m6 0h4"/></svg>
      {a("Dos tickets de soporte", "Two support tickets")}
    </figcaption>
    <fieldset class="example-format">
      <legend class="sr">{a("Etapa del recorrido", "Workflow step")}</legend>
      <input type="radio" name="example-format" id="view-mini" aria-controls="example-mini" checked>
      <input type="radio" name="example-format" id="view-schema" aria-controls="example-schema">
      <input type="radio" name="example-format" id="view-json" aria-controls="example-json">
      <div class="flow-canvas">
        <div class="flow-nodes">
          <label class="flow-node" for="view-mini">
            <span class="flow-icon"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" aria-hidden="true"><path d="M4 6h16M4 12h11M4 18h6"/><circle cx="19" cy="17" r="2.5"/></svg></span>
            <span class="flow-node-name">{a("Modelo", "Model")}</span>
            <span class="flow-node-type">.mini</span>
          </label>
          <span class="flow-edge flow-edge-schema" aria-hidden="true"></span>
          <label class="flow-node" for="view-schema">
            <span class="flow-icon"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M12 22s7-3 7-9.5V5l-7-3-7 3v7.5C5 19 12 22 12 22Z"/><path d="m9 12 2 2 4-4"/></svg></span>
            <span class="flow-node-name">{a("Validación", "Validation")}</span>
            <span class="flow-node-type">{a("Esquema", "Schema")}</span>
          </label>
          <span class="flow-edge flow-edge-json" aria-hidden="true"></span>
          <label class="flow-node" for="view-json">
            <span class="flow-icon"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M10 4H8a2 2 0 0 0-2 2v3a3 3 0 0 1-3 3 3 3 0 0 1 3 3v3a2 2 0 0 0 2 2h2m4-16h2a2 2 0 0 1 2 2v3a3 3 0 0 0 3 3 3 3 0 0 0-3 3v3a2 2 0 0 1-2 2h-2"/></svg></span>
            <span class="flow-node-name">{a("Tu app", "Your app")}</span>
            <span class="flow-node-type">JSON</span>
          </label>
        </div>
      </div>
      <div class="example-editor">
        <div class="example-panel example-mini" id="example-mini">
          <div class="editor-tab"><code>{a("respuesta.mini", "response.mini")}</code></div>
          <pre><code>{a(mini_es, mini_en)}</code></pre>
          <p>{a("Una fila por ticket. Los nombres de los campos ya están en el esquema.", "One row per ticket. The field names are already in the schema.")}</p>
        </div>
        <div class="example-panel example-schema" id="example-schema">
          <div class="editor-tab"><code>{a("Esquema del ticket", "Ticket schema")}</code></div>
          <ol class="editor-fields">{campos}</ol>
          <p>{a(".mini verifica los campos, el tipo de dato y la cantidad de filas.", ".mini checks the fields, their types, and the number of rows.")}</p>
        </div>
        <div class="example-panel example-json" id="example-json">
          <div class="editor-tab"><code>tickets.json</code></div>
          <pre><code>{a(json_es, json_en)}</code></pre>
          <p class="example-output"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="m5 12 4 4L19 6"/></svg>
            {a("2 tickets validados y convertidos a JSON.", "2 tickets validated and converted to JSON.")}</p>
        </div>
        <button class="example-next" type="button" data-example-next hidden>
          <span class="next-schema">{a("Ver validación", "See validation")}</span>
          <span class="next-json">{a("Ver JSON", "See JSON")}</span>
          <span class="next-mini">{a("Volver a .mini", "Back to .mini")}</span>
          <span aria-hidden="true">→</span>
        </button>
      </div>
    </fieldset>
  </figure>
</section>'''
    return ctx.region(html, "COMO FUNCIONA", cuerpo)
