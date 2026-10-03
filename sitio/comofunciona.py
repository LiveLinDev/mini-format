"""Entrada al recorrido de ejemplos desde la portada."""


def construir(ctx):
    """La explicación completa se construye en /ejemplo/ con sus demos."""


def inyectar_portada(html, ctx):
    a = ctx.ambos
    titulo = a('Tu formato nace<br><span class="dim">de los datos que necesitas.</span>',
               'Your format starts<br><span class="dim">with the data you need.</span>')
    cuerpo = f'''<section class="section" id="por-que"><div class="frame">
    <p class="eyebrow">{a("Dónde se reduce el texto", "Where text gets shorter")}</p>
    <h2>{a('JSON repite los nombres.<br><span class="dim">.mini acuerda las reglas una vez.</span>', 'JSON repeats field names.<br><span class="dim">.mini agrees on the rules once.</span>')}</h2>
    <ol class="cf-flow">
      <li><span class="cf-number">01</span><h3>JSON</h3><p>{a('Cada ticket vuelve a escribir "titulo", "categoria" y "prioridad", con comillas y signos. La IA también genera y cobra ese texto.', 'Every ticket writes "title", "category" and "priority" again, with quotes and punctuation. AI also generates and bills that text.')}</p></li>
      <li><span class="cf-number">02</span><h3>TOON</h3><p>{a("También reduce repetición: en una tabla, declara los campos una vez. Es otra alternativa para responder con datos estructurados.", "It also reduces repetition: a table declares fields once. It is another alternative for structured data responses.")}</p></li>
      <li><span class="cf-number">03</span><h3>.mini</h3><p>{a("Adapta un contrato a tu dominio: soporte, pedidos o inventario. Cada línea usa el orden de campos acordado y el código conoce sus tipos. Tu aplicación recupera el JSON.", "Tailors a contract to your domain: support, orders or inventory. Each line uses the agreed field order and the code knows its types. Your app gets JSON back.")}</p></li>
    </ol><p class="fine">{a("En los 20 tickets medidos, .mini usa 278 tokens frente a 304 de TOON y 443 de JSON. La ventaja depende de tus datos; compara también las instrucciones y las correcciones antes de calcular el ahorro total.", "For the 20 measured tickets, .mini uses 278 tokens versus TOON's 304 and JSON's 443. The benefit depends on your data; include instructions and corrections before calculating total savings.")}</p>
    </div></section><section class="section cf-preview" id="como-funciona">
  <div class="frame">
    <p class="eyebrow">{a("Qué hace mini setup", "What mini setup does")}</p>
    <div class="split-head">
      <h2>{titulo}</h2>
      <p class="aside">{a("Es un asistente en tu terminal. Le das un JSON como el que necesita tu aplicación; prepara las reglas del formato y su conexión a tu llamada a IA.", "It is a terminal wizard. Give it JSON like the data your app needs; it prepares format rules and connects them to your AI call.")}</p>
    </div>
    <ol class="cf-flow">
      <li><span class="cf-number">01</span><h3>{a("Describe tu JSON", "Describe your JSON")}</h3><p>{a("Elige español o inglés y una muestra de datos. El contrato guarda sus campos, su orden y sus tipos: las reglas de tu .mini.", "Choose Spanish or English and a data sample. The contract stores its fields, order and types: the rules of your .mini.")}</p></li>
      <li><span class="cf-number">02</span><h3>{a("Recibe el kit preparado", "Get your toolkit")}</h3><p>{a("El prompt son las instrucciones para la IA. El workflow es el código que comprueba su respuesta, la repara cuando puede y devuelve JSON.", "The prompt contains AI instructions. The workflow is code that checks the response, repairs it when possible and returns JSON.")}</p></li>
      <li><span class="cf-number">03</span><h3>{a("Elige el archivo de tu flujo", "Choose your workflow file")}</h3><p>{a("Indica dónde llamas a la IA para preparar la integración. Si todavía no tienes ese código, la guía guarda el comando para hacerlo después.", "Select the code that calls AI to prepare integration. If you do not have it yet, the guide saves the command for later.")}</p></li>
    </ol>
    <div class="cf-preview-action"><a class="btn btn-ghost" href="/docs/quickstart/">{a("Seguir la instalación y el setup →", "Follow installation and setup →")}</a><p>{a("Incluye un prompt para probar 20 objetos antes de conectar tu aplicación.", "Includes a prompt to test 20 objects before connecting your application.")}</p></div>
  </div>
</section>'''
    return ctx.recursos(ctx.region(html, "COMO FUNCIONA", cuerpo), css=("/comofunciona.css",))
