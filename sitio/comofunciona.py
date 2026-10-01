"""Entrada al recorrido de ejemplos desde la portada."""


def construir(ctx):
    """La explicación completa se construye en /ejemplo/ con sus demos."""


def inyectar_portada(html, ctx):
    a = ctx.ambos
    titulo = a('Tus datos.<br><span class="dim">Tu propio .mini.</span>',
               'Your data.<br><span class="dim">Your own .mini.</span>')
    cuerpo = f'''<section class="section cf-preview" id="como-funciona">
  <div class="frame">
    <p class="eyebrow">{a("Cómo funciona", "How it works")}</p>
    <div class="split-head">
      <h2>{titulo}</h2>
      <p class="aside">{a("Decides qué información necesita tu aplicación. mini-format crea las reglas y las instrucciones para que la IA responda en .mini; después comprueba la respuesta y te devuelve los datos para usarlos.", "Decide what information your application needs. mini-format creates the rules and instructions for the AI to reply in .mini, then checks the answer and returns data you can use.")}</p>
    </div>
    <ol class="cf-flow">
      <li><span class="cf-number">01</span><h3>{a("Describe tus datos", "Describe your data")}</h3><p>{a("Partes de muestras JSON o del esquema de tu aplicación.", "Start with JSON samples or your application's schema.")}</p></li>
      <li><span class="cf-number">02</span><h3>{a("Crea tu formato", "Create your format")}</h3><p>{a("El contrato fija los campos y tipos. El prompt explica a la IA cómo responder.", "The contract defines fields and types. The prompt tells the AI how to respond.")}</p></li>
      <li><span class="cf-number">03</span><h3>{a("Valida y usa la respuesta", "Validate and use the answer")}</h3><p>{a("Recuperas los registros válidos y detectas lo que debes corregir o volver a pedir.", "Recover valid records and identify what to correct or request again.")}</p></li>
    </ol>
    <div class="cf-preview-action"><a class="btn btn-solid btn-lg" href="/ejemplo/#como-funciona">{a("Cómo funciona · ver los ejemplos →", "How it works · explore the examples →")}</a><p>{a("Sigue el proceso, prueba la Mesa de ayuda y compara un lote de tickets en la misma página.", "Follow the process, try the help desk and compare a ticket batch on the same page.")}</p></div>
  </div>
</section>'''
    return ctx.recursos(ctx.region(html, "COMO FUNCIONA", cuerpo), css=("/comofunciona.css",))
