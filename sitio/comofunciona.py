"""Short entry point to the integration workflow."""

def construir(ctx):
    """The full walkthrough is available at /flujo/."""


def inyectar_portada(html, ctx):
    a = ctx.ambos
    cuerpo = f'''<section class="landing-section landing-workflow" id="como-funciona" aria-labelledby="workflow-title">
  <div class="wrap">
    <h2 id="workflow-title">{a("De la IA a tu aplicación", "From AI to your application")}</h2>
    <ol class="workflow-steps">
      <li><h3>{a("Define los campos", "Define the fields")}</h3>
        <p>{a("Una muestra JSON fija los nombres, el orden y los tipos de tus datos.", "A JSON sample sets your field names, order, and types.")}</p></li>
      <li><h3>{a("Pide la respuesta en .mini", "Request a .mini response")}</h3>
        <p>{a("La IA escribe los valores sin repetir el nombre de cada campo.", "AI writes the values without repeating every field name.")}</p></li>
      <li><h3>{a("Recibe JSON validado", "Receive validated JSON")}</h3>
        <p>{a(".mini verifica la respuesta, puede reparar errores y la convierte en JSON.", ".mini checks the response, can repair errors, and converts it to JSON.")}</p></li>
    </ol>
  </div>
</section>'''
    return ctx.region(html, "COMO FUNCIONA", cuerpo)
