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
      <li><span class="cf-number">01</span><h3>JSON</h3><p>{a('Cada ticket vuelve a escribir "titulo", "categoria" y "prioridad", con comillas y signos. Si max_tokens corta la respuesta, json.loads pierde todo el lote.', 'Every ticket writes "title", "category" and "priority" again, with quotes and punctuation. If max_tokens cuts the reply, json.loads loses the entire batch.')}</p></li>
      <li><span class="cf-number">02</span><h3>TOON / ISON / CSV</h3><p>{a("Otras notaciones tabulares quitan claves, pero mantienen delimitadores costosos en BPE o carecen de gramáticas GBNF, reparación selectiva y recuperación línea a línea.", "Other tabular formats drop keys, yet retain costly BPE delimiters or lack GBNF grammars, selective repair, and line-level truncation recovery.")}</p></li>
      <li><span class="cf-number">03</span><h3>.mini (domain/2 y filas compactas)</h3><p>{a("Selecciona delimitador BPE óptimo, comprime deltas/prefijos sin pérdida, poda prompts CoT (prompt_style=lean) y recupera el 99,8 % de registros tras cortes.", "Selects the optimal BPE delimiter, losslessly folds deltas/prefixes, prunes CoT prompts (prompt_style=lean), and recovers 99.8% of records after cuts.")}</p></li>
    </ol><p class="fine">{a("En 20 tickets reales, .mini filas compactas usa 182 tokens (-58,9 %) frente a 238 de ISON, 264 de CSV, 304 de TOON y 443 de JSON.", "Across 20 real tickets, .mini compact rows use 182 tokens (-58.9%) vs 238 ISON, 264 CSV, 304 TOON, and 443 JSON.")}</p>
    </div></section><section class="section cf-preview" id="como-funciona">
  <div class="frame">
    <p class="eyebrow">{a("Qué hace mini setup", "What mini setup does")}</p>
    <div class="split-head">
      <h2>{titulo}</h2>
      <p class="aside">{a("Es un asistente en tu terminal. Le das un JSON como el que necesita tu aplicación; prepara las reglas del formato, gramáticas GBNF/Lark y su conexión a tu llamada a IA.", "It is a terminal wizard. Give it JSON like the data your app needs; it prepares format rules, GBNF/Lark grammars, and connects them to your AI call.")}</p>
    </div>
    <ol class="cf-flow">
      <li><span class="cf-number">01</span><h3>{a("Describe tu JSON", "Describe your JSON")}</h3><p>{a("Elige español o inglés y una muestra de datos. El contrato guarda sus campos, su orden y sus tipos: las reglas de tu .mini.", "Choose Spanish or English and a data sample. The contract stores its fields, order and types: the rules of your .mini.")}</p></li>
      <li><span class="cf-number">02</span><h3>{a("Recibe el kit preparado", "Get your toolkit")}</h3><p>{a("Incluye prompts completo y lean anti-CoT para KV-cache, workflow Python/JS y compilación directa a GBNF, Lark o Regex.", "Includes full and lean anti-CoT prompts for KV-cache, Python/JS workflow, and direct GBNF, Lark, or Regex compilation.")}</p></li>
      <li><span class="cf-number">03</span><h3>{a("Elige el archivo de tu flujo", "Choose your workflow file")}</h3><p>{a("Indica dónde llamas a la IA para preparar la integración. Conecta OpenAI, Anthropic, DeepSeek o servidores locales en una línea.", "Select the code that calls AI to prepare integration. Connects OpenAI, Anthropic, DeepSeek, or local endpoints in one line.")}</p></li>
    </ol>
    <div class="cf-preview-action"><a class="btn btn-ghost" href="/docs/quickstart/">{a("Seguir la instalación y el setup →", "Follow installation and setup →")}</a><p>{a("Explora las comparativas de 16 formatos en /validacion/ y costos reales en /economia/.", "Explore the 16-format leaderboard on /validacion/ and live API costs on /economia/.")}</p></div>
  </div>
</section>'''
    return ctx.recursos(ctx.region(html, "COMO FUNCIONA", cuerpo), css=("/comofunciona.css",))
