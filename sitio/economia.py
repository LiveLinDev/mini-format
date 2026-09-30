"""Módulo /economia/ — PLACEHOLDER mínimo y válido.

Genera una página con cabecera y pie reales y un aviso «en construcción», para que los enlaces de
navegación y `tools/check_site.py` pasen mientras el flujo de economía llega con su contenido.
Quien lo reemplace conserva el contrato: `construir(ctx)` escribe la página con
`ctx.escribir_pagina("economia", html)` (API completa en sitio/modulos.py y sitio/LEEME_MODULOS.md);
los precios y costos deben salir de archivos con fecha de consulta y procedencia, nunca escritos a mano.
"""
from __future__ import annotations

OBRAS = ('<svg class="wip-ico" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" '
         'stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">'
         '<path d="M14.7 6.3a4 4 0 0 0-5.4 5.1L3 17.7V21h3.3l6.3-6.3a4 4 0 0 0 5.1-5.4l-2.6 2.6-2.4-.6-.6-2.4z"/></svg>')


def construir(ctx) -> None:
    a = ctx.ambos
    cuerpo = f'''<div class="wrap wip">
  {OBRAS}
  <p class="eyebrow">{a("Evidencia", "Evidence")}</p>
  <h1>{a("Economía", "Economics")}</h1>
  <p class="lead">{a("Esta página está en construcción. Aquí se publicará el análisis económico de usar mini-format: costo por registro, sensibilidad a los precios de cada modelo y los supuestos de cada estimación.",
                      "This page is under construction. The economic analysis of using mini-format will be published here: cost per record, sensitivity to each model's prices and the assumptions behind every estimate.")}</p>
  <p class="wip-links"><a class="btn btn-ghost" href="/docs/metodologia/">{a("Metodología y experimentos", "Methodology and experiments")}</a>
  <a class="btn btn-ghost" href="/ejemplo/">{a("Ejemplo a escala", "Example at scale")}</a></p>
</div>'''
    ctx.escribir_pagina("economia", ctx.pagina("economia", "Economía", "Economics", cuerpo))
