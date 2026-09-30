"""Módulo /validacion/ — PLACEHOLDER mínimo y válido.

Genera una página con cabecera y pie reales y un aviso «en construcción», para que los enlaces de
navegación y `tools/check_site.py` pasen mientras el flujo de validación llega con su contenido.
Quien lo reemplace conserva el contrato: `construir(ctx)` escribe la página con
`ctx.escribir_pagina("validacion", html)` (API completa en sitio/modulos.py y sitio/LEEME_MODULOS.md)
y toda cifra que muestre debe salir de un archivo de resultados validado, nunca escrita a mano.
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
  <h1>{a("Validación", "Validation")}</h1>
  <p class="lead">{a("Esta página está en construcción. Aquí se publicarán los estudios de validación de mini-format con su procedencia: qué se ejecutó, con qué datos y qué quedó sin evaluar.",
                      "This page is under construction. The validation studies of mini-format will be published here with their provenance: what was run, on which data and what remains unevaluated.")}</p>
  <p class="wip-links"><a class="btn btn-ghost" href="/docs/metodologia/">{a("Metodología y experimentos", "Methodology and experiments")}</a>
  <a class="btn btn-ghost" href="/docs/conformance/">{a("Suite de conformidad", "Conformance suite")}</a></p>
</div>'''
    ctx.escribir_pagina("validacion", ctx.pagina("validacion", "Validación", "Validation", cuerpo))
