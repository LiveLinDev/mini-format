# Módulos del sitio

Tres partes del sitio viven en módulos propios para que varias personas trabajen a la vez sin pisarse en
`construir.py` ni en `publicar.py`:

| Módulo | Archivo | Qué construye |
|---|---|---|
| `comofunciona` | `sitio/comofunciona.py` | la sección «Cómo funciona» de la portada |
| `validacion` | `sitio/validacion.py` | la página `/validacion/` |
| `economia` | `sitio/economia.py` | la página `/economia/` |

`sitio/validacion.py` y `sitio/economia.py` hoy son **marcadores de posición** (página con cabecera y pie reales y un
aviso «en construcción») que sustituye quien construya el contenido real. `comofunciona.py` todavía no existe: el
build avisa y lo omite.

La API completa está en el docstring de `sitio/modulos.py`; aquí va la guía práctica.

## Cómo funciona el descubrimiento

`python sitio/construir.py` ejecuta, **después** de construir docs, playground, mesa de ayuda, ejemplo, taller y SIMA y
**antes** de `publicar.prepare_public_site` (sitemap, sellado `?v=`, `/en/`):

1. sincroniza la cabecera y el pie de `index.html` y `404.html` con `cabecera()`/`pie()`;
2. para cada módulo de `modulos.MODULOS`: si `sitio/<nombre>.py` no existe, **avisa y lo omite**; si existe y falla
   (excepción al importar, sin `construir`, excepción dentro), **el build falla** con `ModuloError`;
3. `comofunciona` además recibe `inyectar_portada(html, ctx)` con el HTML de `sitio/index.html`.

## Forma de un módulo

```python
# sitio/validacion.py
def construir(ctx):
    datos = ctx.leer_json("evidencia/validacion/resultados.json")     # relativo a la raíz del repo
    a = ctx.ambos
    cuerpo = f'<div class="wrap"><h1>{a("Validación", "Validation")}</h1>…</div>'
    html = ctx.pagina("validacion", "Validación", "Validation", cuerpo, css=["/validacion.css"], js=["/validacion.js"])
    ctx.escribir_pagina("validacion", html)
```

```python
# sitio/comofunciona.py
def construir(ctx):
    ...                                   # p. ej. validar sus datos; no escribe la portada
def inyectar_portada(html, ctx):
    seccion = f'<section class="section" id="como-funciona">…</section>'
    html = ctx.region(html, "COMO FUNCIONA", seccion)              # idempotente
    return ctx.recursos(html, css=["/comofunciona.css"], js=["/comofunciona.js"])
```

### `ctx`

| Miembro | Para qué |
|---|---|
| `ctx.root`, `ctx.sitio` | rutas (`Path`) de la raíz del repo y de `sitio/` |
| `ctx.cabecera(activo)` / `ctx.pie()` | cabecera (con salto al contenido y menú móvil) y pie compartidos |
| `ctx.ambos(es, en)` | `<span data-lang="es">…</span><span data-lang="en" hidden>…</span>` |
| `ctx.prefijar_ids(html, "es")` | evita ids repetidos entre los cuerpos ES y EN |
| `ctx.cabeza()` / `ctx.cabeza_docs` | bloque del `<head>`: marca `js`, Google Fonts, `base.css`, `docs.css` |
| `ctx.version`, `ctx.spec` | versión del paquete y de la especificación |
| `ctx.leer_json(ruta)` | JSON UTF-8 relativo a la raíz; error claro si falta o es inválido |
| `ctx.cifras` | casos de conformidad, códigos de error, familias y versiones (de `sitio/cifras.py`) |
| `ctx.escribir_pagina(ruta, html)` | escribe `sitio/<ruta>/index.html` y registra la ruta (sitemap, `?v=`, canonical) |
| `ctx.pagina(...)` | esqueleto de página bilingüe en línea: cabeza, cabecera, `<main id="contenido">`, pie y `docs.js` |
| `ctx.region(html, nombre, contenido)` | reemplaza lo que hay entre las anclas `nombre` de la portada |
| `ctx.recursos(html, css=(), js=())` | añade una sola vez `<link>` y `<script defer>` |

## La portada: anclas de «Cómo funciona»

`sitio/index.html` tiene, entre la tira «Para tu aplicación» y «Cuatro piezas»:

```html
<!-- ═══════════ COMO FUNCIONA ═══════════ -->
<!-- ═══════════ /COMO FUNCIONA ═══════════ -->
```

Lo que hay entre ambas las reescribe `ctx.region(...)`; puede ejecutarse N veces con el mismo resultado. **No** pongas la
sección dentro de las anclas de `sitio/benchmarks.py` (el `<div class="bench">` del héroe y «BENCHMARK COMPLETO»): esa
inyección usa expresiones regulares sobre la indentación exacta de esas líneas. El contenido que generes queda
escrito en `sitio/index.html` (es a la vez fuente y salida, como ya ocurre con las tablas de benchmark): commitéalo.

La cabecera y el pie de la portada (`CABECERA` y `PIE`) y la cabeza y cabecera y pie de `404.html` también son regiones
generadas: no se editan a mano, se cambian en `construir.py` (`NAV`, `cabecera()`, `pie()`).

## Idiomas (ES/EN)

* **Páginas de los módulos** (`/validacion/`, `/economia/`): bilingües **en línea**. Todo texto visible sale de
  `ctx.ambos()` o de cuerpos `data-lang-body="es|en"`; `docs.js` muestra un idioma y recuerda la elección. No tienen copia
  `/en/…` (igual que `/taller/`, `/sima/` y `/ejemplo/`): en el sitemap entran con una sola URL, con canonical y sin
  `hreflang`.
* **Sección de la portada**: la copia `/en/` se genera por un **mapa de cadenas** (`sitio/landing.en.json`): un texto sin
  clave queda **en español en silencio**. Dos salidas: (a) escribe la sección con `ctx.ambos()` (recomendado; los gemelos
  se alternan solos en `/en/`), o (b) añade las claves a **`sitio/i18n/comofunciona.en.json`** (`{"texto en español": "English
  text"}`): `publicar.py` funde `sitio/i18n/*.en.json` con `landing.en.json` y falla si una clave ya existe con otra
  traducción. Cada nodo de texto entre etiquetas (también los partidos por `<code>` o `<a>`) necesita su clave exacta.
* Un JS nuevo no se traduce: lee `document.documentElement.lang` y lleva sus textos por idioma. Formatea números con
  `Intl.NumberFormat` según ese idioma; no escribas cifras en nodos de texto de la portada (el traductor convierte comas entre
  dígitos).

## Reglas de calidad (las comprueba `tools/check_site.py` o los tests)

* **Cifras**: nada escrito a mano. Las del proyecto salen de `ctx.cifras`; los resultados de estudios, de un archivo de
  resultados validado (`ctx.leer_json`). `tests/test_sitio_cifras.py` falla si la portada, `landing.en.json` o la
  documentación repiten una cifra distinta de la calculada.
* **Sin JavaScript**: el texto se ve con JS desactivado. Lo que aparece con `.rv` ya se ve sin JS (`html:not(.js) .rv`); si tu CSS
  oculta algo hasta que un script lo muestre, añade su regla `html:not(.js) …` para mostrarlo.
* **Iconos**: SVG en línea con `currentColor` (`viewBox` 24), tamaño por CSS. Ni emojis ni dingbats de texto (marcas de verificación, cruces, estrellas, flechas de texto).
* **Colores**: solo los tokens de `base.css` (`rgb(var(--accent))`…), sin hex sueltos.
* **Móvil**: sin desplazamiento horizontal de página a 360 px (envuelve las tablas en un contenedor con `overflow-x:auto`).
* Archivos nuevos de tu módulo en `sitio/` (`comofunciona.css`, `.js`, `.json`…): el navegador los necesita y el despliegue
  los publica; los `*.py`, `landing.en.json`, `content/`, `i18n/` y `servidor/` **no** se publican
  (`sitio/servidor/empaquetar.py`). El zip de fuentes incluye todo lo que haya en la raíz de `sitio/` (`tools/build_release.py`).
* Si tus datos viven fuera de `sitio/`, comprueba que su carpeta está en `paths:` de `.github/workflows/sitio.yml`
  (ya cubre `evidencia/**`, `experiments/**`, `docs/adr/**`, `conformance/cases/**`, `js/**`, `tools/**`, `examples/**`).
* Los enlaces de evidencia a GitHub se reescriben a `/source/…` si el archivo está en las carpetas permitidas de
  `publicar.py` (`ALLOW_ROOTS`; en `experiments/` solo las listadas en `permitted`); si no, caen al zip de fuentes.

## Comprobar

```bash
python sitio/construir.py && python tools/check_site.py
python -m pytest -q -p no:cacheprovider tests/test_sitio_*.py
```
