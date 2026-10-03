"""Módulos opcionales del sitio: «Cómo funciona» (portada), /validacion/ y /economia/.

Cada módulo es un archivo `sitio/<nombre>.py` que construye su parte del sitio sin tocar
`construir.py`. `construir.py` los descubre y los ejecuta ANTES de `publicar.prepare_public_site`,
de modo que sus páginas entran en el sitemap, el sellado `?v=` y `check_site.py`.

Los módulos conocidos (`MODULOS`) y su contrato
-----------------------------------------------
* `comofunciona` — `construir(ctx)` y `inyectar_portada(html, ctx) -> html`.
  `inyectar_portada` recibe el HTML de `sitio/index.html` y devuelve el HTML con su sección
  puesta dentro de las anclas idempotentes (ver «Anclas» abajo). Es el único módulo que toca la portada.
* `validacion` — `construir(ctx)`: escribe `/validacion/` con `ctx.escribir_pagina("validacion", html)`.
* `economia` — `construir(ctx)`: escribe `/economia/` con `ctx.escribir_pagina("economia", html)`.

Reglas de ejecución
-------------------
* Si `sitio/<nombre>.py` NO existe, el módulo se omite con un aviso claro (los módulos son opcionales).
* Si existe y falla (excepción, falta `construir`, `inyectar_portada` no devuelve texto...), el
  build FALLA ruidosamente con `ModuloError`: nunca se publica un sitio a medias en silencio.
* Un módulo es un archivo suelto: se carga por ruta (no hace falta `sys.path`), y puede importar
  `cifras` (está en el `sys.path` del build) para no escribir cifras a mano.

El contexto `ctx` (SimpleNamespace)
-----------------------------------
    ctx.root                 Path de la raíz del repositorio.
    ctx.sitio                Path de `sitio/`.
    ctx.cabecera(activo)     HTML del enlace de salto + cabecera compartida. `activo` es la ruta del menú
                             (p. ej. "validacion"); marca `aria-current`.
    ctx.pie()                HTML del pie compartido.
    ctx.ambos(es, en)        Gemelos de idioma `<span data-lang="es">…</span><span data-lang="en" hidden>…`.
                             TODO texto visible de un módulo debe salir de aquí (o de `data-lang-body`):
                             la copia /en/ de la portada se genera por mapa de cadenas y lo que no
                             esté en `ambos()` ni en `sitio/i18n/*.en.json` quedaría en español.
    ctx.prefijar_ids(h, pref)  Evita ids duplicados entre los cuerpos ES y EN de una misma página.
    ctx.cabeza()             Bloque para el <head>: marca de JS + Google Fonts + base.css + docs.css.
    ctx.cabeza_docs          Lo mismo, como cadena (alias de `cabeza()`).
    ctx.version / ctx.spec   Versión del paquete y de la especificación (`__version__`, `SPEC_VERSION`).
    ctx.leer_json(ruta)      Lee un JSON (UTF-8) relativo a la raíz del repo; error claro si falta o es inválido.
    ctx.cifras               dict de `sitio/cifras.py` (casos de conformidad, códigos de error, familias, versiones).
    ctx.escribir_pagina(ruta, html)
                             Escribe `sitio/<ruta>/index.html` y registra la ruta como página bilingüe en línea
                             (entra en el sitemap y en el sellado `?v=`; queda fuera de /en/).
    ctx.region(html, nombre, contenido)
                             Sustituye (idempotente) lo que hay entre las anclas `nombre` de la portada.
    ctx.recursos(html, css=(), js=())
                             Añade, una sola vez, `<link rel="stylesheet">` antes de `</head>` y
                             `<script defer>` antes de `</body>`. El `?v=` lo sella publicar.py.
    ctx.pagina(ruta, titulo_es, titulo_en, cuerpo, css=(), js=(), activo=None, descripcion=None)
                             Esqueleto completo de una página bilingüe en línea (cabeza, cabecera, `<main
                             id="contenido">`, pie y docs.js). Devuelve el HTML; se escribe con `escribir_pagina`.

Anclas de la portada
--------------------
`sitio/index.html` lleva, entre la tira «Para tu aplicación» y «Cuatro piezas», un par de comentarios:

    <!-- ═══════════ COMO FUNCIONA ═══════════ -->
    <!-- ═══════════ /COMO FUNCIONA ═══════════ -->

`ctx.region(html, "COMO FUNCIONA", contenido)` reemplaza lo que hay entre ambos y conserva las anclas, por lo que
puede ejecutarse N veces con el mismo resultado. No coloques la sección dentro de las anclas de `benchmarks.py`
(`<div class="bench">` del héroe ni «BENCHMARK COMPLETO»).
"""
from __future__ import annotations

import html as _html
import importlib.util
import json
import re
from pathlib import Path
from types import SimpleNamespace

MODULOS = ("comofunciona", "validacion", "economia", "flujo")
ANCLA = "═══════════"
# Carpetas que el build ya posee: un módulo no puede escribir ahí.
RESERVADAS = {"en", "source", "downloads", "docs", "playground", "mesa-de-ayuda", "servidor"}


class ModuloError(RuntimeError):
    """Un módulo existente falló: el build debe detenerse."""


# --------------------------------------------------------------------------- utilidades del contexto
def region(html: str, nombre: str, contenido: str) -> str:
    """Reemplaza el contenido entre `<!-- ═══ NOMBRE ═══ -->` y `<!-- ═══ /NOMBRE ═══ -->` (idempotente)."""
    abre = f"<!-- {ANCLA} {nombre} {ANCLA} -->"
    cierra = f"<!-- {ANCLA} /{nombre} {ANCLA} -->"
    patron = re.compile(re.escape(abre) + r".*?" + re.escape(cierra), re.S)
    if len(patron.findall(html)) != 1:
        raise ModuloError(f"la portada debe tener exactamente un par de anclas «{abre}» … «{cierra}»")
    return patron.sub(lambda _: f"{abre}\n{contenido.strip()}\n{cierra}", html, count=1)


def recursos(html: str, css=(), js=()) -> str:
    """Añade hojas y scripts locales una sola vez (el `?v=` se sella después, en publicar.py)."""
    for ruta in css:
        etiqueta = f'<link rel="stylesheet" href="{ruta}">'
        if not re.search(r'<link[^>]+href="' + re.escape(ruta) + r'(?:\?[^"]*)?"', html):
            if "</head>" not in html:
                raise ModuloError("no hay </head> donde añadir " + ruta)
            html = html.replace("</head>", etiqueta + "\n</head>", 1)
    for ruta in js:
        etiqueta = f'<script defer src="{ruta}"></script>'
        if not re.search(r'<script[^>]+src="' + re.escape(ruta) + r'(?:\?[^"]*)?"', html):
            if "</body>" not in html:
                raise ModuloError("no hay </body> donde añadir " + ruta)
            html = html.replace("</body>", etiqueta + "\n</body>", 1)
    return html


def _leer_json(raiz: Path):
    def leer(ruta):
        archivo = raiz / ruta
        if not archivo.is_file():
            raise ModuloError(f"leer_json: no existe {ruta}")
        try:
            return json.loads(archivo.read_text(encoding="utf-8"))
        except json.JSONDecodeError as error:
            raise ModuloError(f"leer_json: {ruta} no es JSON válido ({error})") from error
    return leer


def crear_contexto(construir, publicar=None) -> SimpleNamespace:
    """Arma `ctx` a partir del módulo `construir` (cabecera, pie, versiones...)."""
    raiz, sitio = construir.RAIZ, construir.SITIO
    registrar = getattr(publicar, "registrar_en_linea", None) if publicar else None

    def escribir_pagina(ruta: str, contenido: str) -> Path:
        limpia = ruta.strip("/")
        partes = limpia.split("/")
        if not limpia or ".." in partes or Path(limpia).is_absolute() or partes[0] in RESERVADAS:
            raise ModuloError(f"escribir_pagina: ruta no permitida «{ruta}»")
        destino = sitio / limpia / "index.html"
        destino.parent.mkdir(parents=True, exist_ok=True)
        destino.write_text(contenido, encoding="utf-8")
        if registrar:
            registrar(limpia)
        return destino

    def pagina(ruta, titulo_es, titulo_en, cuerpo, css=(), js=(), activo=None, descripcion=None):
        cabeza = construir.cabeza() + "".join(f'<link rel="stylesheet" href="{c}">' for c in css)
        scripts = "".join(f'<script defer src="{s}"></script>' for s in js)
        meta = f'<meta name="description" content="{_html.escape(descripcion, quote=True)}">' if descripcion else ""
        return (f'<!doctype html><html lang="es" data-title-es="{_html.escape(titulo_es)} — mini-format" '
                f'data-title-en="{_html.escape(titulo_en)} — mini-format"><head><meta charset="utf-8">'
                f'<meta name="viewport" content="width=device-width, initial-scale=1">'
                f'<title>{_html.escape(titulo_es)} — mini-format</title>{meta}{cabeza}</head>\n'
                f'<body>{construir.cabecera(activo if activo is not None else ruta)}\n'
                f'<main id="contenido">{cuerpo}</main>\n{construir.pie()}<script src="/docs.js"></script>{scripts}</body></html>')

    return SimpleNamespace(
        root=raiz, sitio=sitio,
        cabecera=construir.cabecera, pie=construir.pie, ambos=construir.ambos,
        prefijar_ids=construir.prefijar_ids, cabeza=construir.cabeza, cabeza_docs=construir.cabeza(),
        version=construir.__version__, spec=construir.SPEC_VERSION,
        leer_json=_leer_json(raiz), cifras=construir.CIFRAS,
        escribir_pagina=escribir_pagina, region=region, recursos=recursos, pagina=pagina,
    )


# --------------------------------------------------------------------------- descubrimiento y ejecución
def cargar(nombre: str, sitio: Path):
    """Carga `sitio/<nombre>.py`; None si no existe. Una excepción al importarlo es un fallo del módulo."""
    archivo = sitio / f"{nombre}.py"
    if not archivo.is_file():
        return None
    spec = importlib.util.spec_from_file_location(f"sitio_modulo_{nombre}", archivo)
    modulo = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(modulo)
    except Exception as error:  # noqa: BLE001 — se re-lanza con el nombre del módulo
        raise ModuloError(f"el módulo «{nombre}» ({archivo.name}) no se pudo importar: {error!r}") from error
    if not callable(getattr(modulo, "construir", None)):
        raise ModuloError(f"el módulo «{nombre}» debe definir construir(ctx)")
    if nombre == "comofunciona" and not callable(getattr(modulo, "inyectar_portada", None)):
        raise ModuloError("el módulo «comofunciona» debe definir inyectar_portada(html, ctx)")
    return modulo


def ejecutar(ctx, nombres=MODULOS, salida=print) -> dict:
    """Ejecuta los módulos presentes. Devuelve {nombre: "ok" | "omitido"}; un módulo que falla lanza ModuloError."""
    estado: dict = {}
    for nombre in nombres:
        modulo = cargar(nombre, ctx.sitio)
        if modulo is None:
            salida(f"  aviso: módulo opcional «{nombre}» no encontrado (sitio/{nombre}.py); se omite")
            estado[nombre] = "omitido"
            continue
        try:
            modulo.construir(ctx)
            if nombre == "comofunciona":
                portada = ctx.sitio / "index.html"
                antes = portada.read_text(encoding="utf-8")
                despues = modulo.inyectar_portada(antes, ctx)
                if not isinstance(despues, str) or not despues.strip():
                    raise ModuloError("inyectar_portada debe devolver el HTML de la portada")
                if despues != antes:
                    portada.write_text(despues, encoding="utf-8")
        except ModuloError:
            raise
        except Exception as error:  # noqa: BLE001
            raise ModuloError(f"el módulo «{nombre}» falló: {error!r}") from error
        salida(f"  módulo {nombre}: ok")
        estado[nombre] = "ok"
    return estado
