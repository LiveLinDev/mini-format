"""Entrada al recorrido de ejemplos desde la portada."""


def construir(ctx):
    """La explicación completa se construye en /ejemplo/ con sus demos."""


def inyectar_portada(html, ctx):
    a = ctx.ambos
    titulo = a('Un asistente.<br><span class="dim">Un flujo completo.</span>',
               'One wizard.<br><span class="dim">One complete workflow.</span>')
    cuerpo = f'''<section class="section cf-preview" id="como-funciona">
  <div class="frame">
    <p class="eyebrow">{a("Cómo funciona", "How it works")}</p>
    <div class="split-head">
      <h2>{titulo}</h2>
      <p class="aside">{a("Ya tienes una llamada a IA que pide JSON. mini setup usa una muestra de esa respuesta para preparar el formato y ayudarte a conectarlo.", "You already have an AI call requesting JSON. mini setup uses a sample response to prepare the format and help connect it.")}</p>
    </div>
    <ol class="cf-flow">
      <li><span class="cf-number">01</span><h3>{a("Crea tu contrato", "Create your contract")}</h3><p>{a("Elige el idioma y tu JSON. El asistente prepara las reglas y el prompt para la IA.", "Choose your language and JSON sample. The wizard prepares rules and an AI prompt.")}</p></li>
      <li><span class="cf-number">02</span><h3>{a("Prueba 20 registros", "Try 20 records")}</h3><p>{a("Pide una muestra .mini a tu IA. Valida y prueba Repair si hay errores.", "Ask your AI for a .mini sample. Validate it and try Repair if there are errors.")}</p></li>
      <li><span class="cf-number">03</span><h3>{a("Conecta tu aplicación", "Connect your application")}</h3><p>{a("La IA genera .mini. El puente valida, repara, vuelve a validar y devuelve JSON.", "AI generates .mini. The bridge validates, repairs, revalidates and returns JSON.")}</p></li>
    </ol>
    <div class="cf-preview-action"><a class="btn btn-solid btn-lg" href="/flujo/">{a("Ver el caso de los 20 tickets →", "See the 20-ticket use case →")}</a><p>{a("Respuestas guardadas, corrección de una línea y JSON final. Sin clave.", "Saved replies, a one-line correction and final JSON. No key required.")}</p></div>
  </div>
</section>'''
    return ctx.recursos(ctx.region(html, "COMO FUNCIONA", cuerpo), css=("/comofunciona.css",))
