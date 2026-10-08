"""Construye el sitio de mini-format: documentación bilingüe ES/EN (desde los .md del
repositorio y sus traducciones .es.md/.en.md, los contratos de forks/ y los códigos
de error del núcleo) y el playground re-vestido con el sistema de diseño del sitio.

    python sitio/construir.py            # escribe sitio/docs/** y sitio/playground/index.html

No toca playground/ ni ningún archivo fuera de sitio/. Requiere `markdown` (pip).

Cada página de documentación incluye los dos idiomas en el mismo HTML y un
conmutador ES/EN (`sitio/docs.js`, elección persistida en localStorage). Los
contratos (contract.json) y la licencia MIT se publican tal cual, sin traducir:
las descripciones de contrato alimentan los bloques de prompt y la licencia es
un texto legal.

Orden del build (ver `__main__`): sello de versión, documentación, playground,
mesa de ayuda, ejemplo, taller y SIMA; sincronización de la cabecera y el pie de
`index.html` y `404.html` (`cabecera()`, `pie()`); módulos opcionales
(`sitio/modulos.py`: «Cómo funciona», /validacion/, /economia/); ensamblado
público (`sitio/publicar.py`: /en/, sitemap, `?v=`) y artefactos de descarga.
Las cifras repetidas en el texto salen de `sitio/cifras.py`.
"""
from __future__ import annotations

import html
import json
import posixpath
import re
import sys
from pathlib import Path

import markdown

RAIZ = Path(__file__).resolve().parents[1]
SITIO = RAIZ / "sitio"
sys.path.insert(0, str(RAIZ / "src"))
sys.path.insert(0, str(SITIO))
from minifmt import Registry, __version__, SPEC_VERSION  # noqa: E402
import cifras  # noqa: E402

REPO = "https://github.com/LiveLinDev/mini-format"
SITE_URL = "https://mini-format.pmoluna.com"
DOWNLOAD = f"/downloads/mini-format-{__version__}.zip"
SOURCE = f"/downloads/mini-format-{__version__}-source.zip"
# Marca «hay JavaScript» lo antes posible: el CSS la usa para no esconder contenido sin JS
# (`html:not(.js) .rv{opacity:1}`) y para que el menú móvil tenga una alternativa sin JS.
JS_FLAG = '<script>document.documentElement.classList.add("js")</script>'
FONTS = ('<link rel="preconnect" href="https://fonts.googleapis.com">'
         '<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>'
         '<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Archivo:wght@400;500;600;700;800'
         '&family=Martian+Mono:wght@400;500;600;700&display=swap">')


def ambos(es: str, en: str) -> str:
    """Gemelos de idioma para el chrome compartido: docs.js muestra uno."""
    return f'<span data-lang="es">{es}</span><span data-lang="en" hidden>{en}</span>'


# --------------------------------------------------------------------------- códigos de error
ERRORES = [
    ("E01", "E_NO_HEADER", "Falta la cabecera", "El documento no empieza con la línea de cabecera `prefijo|n=…`. Sin ella no hay contrato que aplicar: es el único error que impide construir el documento incluso en modo tolerante.", "§5, §8"),
    ("E02", "E_UNKNOWN_PREFIX", "Prefijo distinto del contrato", "El prefijo de la cabecera no coincide con el del contrato con el que se está validando (o no existe en el registro de familias).", "§5"),
    ("E03", "E_NO_COUNT", "Falta `n`", "La cabecera no declara `n`, el número de registros. `n` es obligatorio: permite detectar respuestas truncadas y registros perdidos.", "§5"),
    ("E04", "E_COUNT_MISMATCH", "Número de registros distinto de `n`", "Se declararon `n` registros pero se leyó otra cantidad de líneas válidas. En modo tolerante el documento se construye igual y este error queda registrado; el lector en streaming lo expone como `missing`.", "§5, §9"),
    ("E05", "E_ARITY", "Aridad del registro fuera de rango", "La línea tiene menos campos que el núcleo o campos excedentes sin una versión superior. Con el mismo prefijo y una cabecera v mayor que la versión del contrato, el lector valida los campos conocidos e ignora únicamente la cola desconocida.", "§6, §10"),
    ("E06", "E_TYPE", "Tipo incorrecto o requerido vacío", "El valor no se puede interpretar con el tipo declarado (`int`, `float`, `bool`…) o un campo requerido llegó vacío.", "§6"),
    ("E07", "E_LIST_ARITY", "Aridad de lista o tupla", "Una lista tiene menos o más elementos de los permitidos, o una tupla no tiene exactamente los declarados.", "§6"),
    ("E08", "E_MARKER", "Regla del marcador violada", "El marcador `*` de elemento seleccionado aparece donde no corresponde, falta cuando es obligatorio, o se repite en una lista de selección única.", "§3.2, §6"),
    ("E09", "E_ESCAPE", "Escape inválido", "Secuencia de escape no reconocida. Las válidas son `\\|`, `\\\\`, `\\n`, `\\,` (dentro de listas) y `\\*` (dentro de listas). En modo tolerante el registro se descarta.", "§3.3"),
    ("E10", "E_ENUM", "Valor fuera de la enumeración", "El valor no está entre los admitidos por un campo `enum`.", "§6"),
    ("E11", "E_UNIQUE", "Valor único duplicado", "Un campo declarado `unique` repite un valor ya visto en otro registro válido. Una línea rechazada no reserva su valor.", "§6"),
    ("E12", "E_HEADER_KEY", "Entrada de cabecera malformada o ausente", "Una clave requerida de la cabecera falta, o una entrada `clave=valor` está mal formada (por ejemplo, sin `=`).", "§5"),
    ("E13", "E_RANGE", "Fuera de rango numérico", "Un número está fuera del `min`/`max` declarado en el contrato.", "§6"),
    ("E20", "E_CONTRACT", "Contrato inválido", "El `contract.json` no cumple la norma: falta el prefijo, hay nombres duplicados, un tipo desconocido, un separador de lista no permitido… Se detecta al cargar el contrato, no al leer documentos.", "§10"),
    ("E21", "E_FORK", "Invariante de familia violado", "Una familia rompe alguno de los cinco invariantes: cambia el núcleo heredado, inserta campos fuera de la cola, o sus fixtures no hacen ida y vuelta. Lo comprueba `mini check-forks`.", "§10"),
]

ERRORES_EN = [
    ("E01", "E_NO_HEADER", "Missing header", "The document does not start with the header line `prefix|n=…`. Without it there is no contract to apply: it is the only error that prevents building the document even in lenient mode.", "§5, §8"),
    ("E02", "E_UNKNOWN_PREFIX", "Prefix differs from the contract", "The header prefix does not match the contract it is validated against (or does not exist in the family registry).", "§5"),
    ("E03", "E_NO_COUNT", "Missing `n`", "The header does not declare `n`, the record count. `n` is mandatory: it detects truncated responses and lost records.", "§5"),
    ("E04", "E_COUNT_MISMATCH", "Record count differs from `n`", "`n` records were declared but another number of valid lines was read. In lenient mode the document is built anyway and this error is recorded; the streaming reader exposes it as `missing`.", "§5, §9"),
    ("E05", "E_ARITY", "Record arity out of range", "The line has fewer fields than the core or extra fields without a higher version. For the same prefix and a header v higher than the contract version, the reader validates known fields and ignores only the unknown trailing fields.", "§6, §10"),
    ("E06", "E_TYPE", "Wrong type or empty required value", "The value cannot be read with the declared type (`int`, `float`, `bool`…) or a required field arrived empty.", "§6"),
    ("E07", "E_LIST_ARITY", "List or tuple arity", "A list has fewer or more elements than allowed, or a tuple does not have exactly the declared ones.", "§6"),
    ("E08", "E_MARKER", "Marker rule violated", "The `*` selected-element marker appears where it must not, is missing where mandatory, or repeats in a single-selection list.", "§3.2, §6"),
    ("E09", "E_ESCAPE", "Invalid escape", "Unrecognized escape sequence. The valid ones are `\\|`, `\\\\`, `\\n`, `\\,` (inside lists) and `\\*` (inside lists). In lenient mode the record is discarded.", "§3.3"),
    ("E10", "E_ENUM", "Value outside the enumeration", "The value is not among those allowed by an `enum` field.", "§6"),
    ("E11", "E_UNIQUE", "Duplicated unique value", "A `unique` field repeats a value already seen in another valid record. A rejected line does not reserve its value.", "§6"),
    ("E12", "E_HEADER_KEY", "Malformed or missing header entry", "A required header key is missing, or a `key=value` entry is malformed (e.g. without `=`).", "§5"),
    ("E13", "E_RANGE", "Outside the numeric range", "A number is outside the `min`/`max` declared in the contract.", "§6"),
    ("E20", "E_CONTRACT", "Invalid contract", "The `contract.json` violates the norm: missing prefix, duplicate names, unknown type, disallowed list separator… It is detected when loading the contract, not when reading documents.", "§10"),
    ("E21", "E_FORK", "Family invariant violated", "A family breaks one of the five invariants: it changes the inherited core, inserts fields off the tail, or its fixtures do not round-trip. Checked by `mini check-forks`.", "§10"),
]
# --------------------------------------------------------------------------- navegación de docs
GRUPOS_ES = [
    ("Empezar", [("docs", "Introducción"), ("downloads", "Descargas"), ("docs/quickstart", "Inicio rápido"), ("docs/build", "Crear tu toolkit")]),
    ("Norma", [("docs/spec", "Especificación 1.1"), ("docs/profile", "Perfil mini-domain/1"), ("docs/spec/cambios", "Versiones y compatibilidad"), ("docs/adr", "Registro de decisiones"), ("docs/forking", "Extender: familias"), ("docs/forks", "Familias de ejemplo"), ("docs/errors", "Códigos de error")]),
    ("Bibliotecas", [("docs/python", "Python"), ("docs/typescript", "TypeScript"), ("docs/cli", "Herramienta de línea de comandos"), ("docs/conformance", "Suite de conformidad")]),
    ("Evidencia", [("docs/metodologia", "Metodología y experimentos")]),
    ("Proyecto", [("docs/contribuir", "Contribuir"), ("docs/licencia", "Licencia")]),
]
GRUPOS_EN = [
    ("Start", [("docs", "Introduction"), ("downloads", "Downloads"), ("docs/quickstart", "Quickstart"), ("docs/build", "Build your toolkit")]),
    ("Reference", [("docs/spec", "Specification 1.1"), ("docs/profile", "mini-domain/1 profile"), ("docs/spec/cambios", "Versions and compatibility"), ("docs/adr", "Decision records"), ("docs/forking", "Extending: forks"), ("docs/forks", "Sample families"), ("docs/errors", "Error codes")]),
    ("Libraries", [("docs/python", "Python"), ("docs/typescript", "TypeScript"), ("docs/cli", "Command-line tool"), ("docs/conformance", "Conformance suite")]),
    ("Evidence", [("docs/metodologia", "Methodology and experiments")]),
    ("Project", [("docs/contribuir", "Contributing"), ("docs/licencia", "License")]),
]
ORDEN = [ruta for _, items in GRUPOS_ES for ruta, _ in items]
NOMBRES_ES = {r: t for _, it in GRUPOS_ES for r, t in it}
NOMBRES_EN = {r: t for _, it in GRUPOS_EN for r, t in it}


CIFRAS = cifras.calcular()


def cuenta(n: int, palabras: dict, idioma: str) -> str:
    """«Catorce» / «Fourteen» si hay palabra para el número; si no, la cifra."""
    return palabras.get(f"palabra_{idioma}") or str(n)


def aviso_conformidad() -> tuple[str, str]:
    """Total de la suite vigente (calculado de conformance/cases/*.json) para /docs/conformance/."""
    c = CIFRAS
    es = (f'<p class="lang">La suite de la especificación {c["version_spec"]} tiene <strong>{c["casos_conformidad"]} casos</strong> '
          f'({c["casos_suite_1_0"]} heredados de la suite 1.0, que se conservan, y {c["casos_nuevos_1_1"]} nuevos) repartidos en '
          f'{c["archivos_conformidad"]} categorías.</p>')
    en = (f'<p class="lang">The suite for specification {c["version_spec"]} has <strong>{c["casos_conformidad"]} cases</strong> '
          f'({c["casos_suite_1_0"]} inherited from suite 1.0, which are kept, and {c["casos_nuevos_1_1"]} new) across '
          f'{c["archivos_conformidad"]} categories.</p>')
    return es, en


def md(texto: str) -> str:
    return markdown.markdown(texto, extensions=["tables", "fenced_code", "toc", "sane_lists"],
                             extension_configs={"toc": {"permalink": "#", "permalink_class": "anchor", "permalink_title": "Enlace a esta sección"}})


def prefijar_ids(h: str, pref: str) -> str:
    """Evita ids duplicados entre los dos cuerpos de idioma de una página."""
    h = re.sub(r'id="([^"]+)"', lambda m: f'id="{pref}-{m.group(1)}"', h)
    h = re.sub(r'href="#([^"]+)"', lambda m: f'href="#{pref}-{m.group(1)}"', h)
    return h


def reescribir_enlaces(h: str, origin_dir: Path = Path(".")) -> str:
    """Enlaces relativos del repositorio -> rutas del sitio o al repositorio."""
    mapa = {"SPEC.md": "/docs/spec/", "FORKING.md": "/docs/forking/", "CONTRIBUTING.md": "/docs/contribuir/",
            "LICENSE": "/docs/licencia/", "README.md": "/docs/", "playground/index.html": "/playground/",
            "conformance/README.md": "/docs/conformance/", "ts/README.md": "/docs/typescript/",
            "DOMAIN_PROFILE.md": "/docs/profile/", "DOMAIN_PROFILE.es.md": "/docs/profile/",
            "BUILD_GUIDE.md": "/docs/build/", "BUILD_GUIDE.es.md": "/docs/build/"}
    def sub(m):
        href = m.group(1)
        if href.startswith(("http", "#", "/", "mailto:")):
            return m.group(0)
        base = href.split("#")[0]
        norm = posixpath.normpath((origin_dir / base).as_posix()) if base else base
        if base in mapa:
            return f'href="{mapa[base]}"'
        if norm in mapa:
            return f'href="{mapa[norm]}"'
        adr = re.fullmatch(r"docs/adr/(\d{4})-[^/]+\.md", norm or "")
        if adr:
            return f'href="/docs/adr/{adr.group(1)}/"'
        if norm == "docs/adr/README.md":
            return 'href="/docs/adr/"'
        if base.startswith("forks/") and base.count("/") == 1:
            return f'href="/docs/forks/{base.split("/")[1]}/"'
        rel = (origin_dir / href.split("#", 1)[0]).as_posix()
        return f'href="{REPO}/blob/main/{rel}"'
    h = re.sub(r'href="([^"]+)"', sub, h)
    h = re.sub(r'src="(?!http)([^"]+)"', lambda m: f'src="{REPO}/raw/main/{m.group(1)}"', h)
    return h
# --------------------------------------------------------------------------- cabecera y pie compartidos
# Un solo contrato para TODAS las páginas (docs, playground, demo, taller, ejemplo, SIMA, validación,
# economía, 404 y la portada): el menú se define aquí y nadie lo copia a mano.
NAV = [
    ("demo", "Demo en vivo", "Live demo"),
    ("docs", "Documentación", "Documentation"),
    ("flujo", "Cómo funciona", "How it works"),
    ("playground", "Playground", "Playground"),
    ("ejemplo", "Más ejemplos", "More examples"),
]
ICONO_MENU = ('<svg class="ico-abrir" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" aria-hidden="true"><path d="M4 7h16M4 12h16M4 17h16"/></svg>'
              '<svg class="ico-cerrar" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" aria-hidden="true"><path d="M6 6l12 12M18 6 6 18"/></svg>')


def ruta_activa(activo: str) -> str:
    """Ruta del menú que corresponde a la página: la más específica que encaje por segmentos."""
    activo = activo.strip("/")
    mejores = [r for r, _, _ in NAV if activo == r or activo.startswith(r + "/")]
    return max(mejores, key=len) if mejores else ""


def cabeza() -> str:
    """Bloque común del <head> de las páginas generadas: marca de JS, tipografías y hojas compartidas."""
    return JS_FLAG + FONTS + '<link rel="stylesheet" href="/base.css"><link rel="stylesheet" href="/docs.css">'


def cabecera(activo: str = "", portada: bool = False) -> str:
    """Enlace de salto + cabecera. `portada=True` da la variante de la página de inicio (salto a #main,
    buscador y «Descargar» en lugar de «Instalar»); el menú y el botón móvil son los mismos."""
    salto = "#main" if portada else "#contenido"
    enlace = f'<a class="skip" href="{salto}">{ambos("Saltar al contenido", "Skip to content")}</a>'
    return enlace + "\n" + encabezado(activo, portada)


def encabezado(activo: str = "", portada: bool = False) -> str:
    """Solo el <header>: la portada escribe el enlace de salto a mano porque el aviso va entre ambos."""
    marcada = ruta_activa(activo)
    def a(ruta, es, en):
        cur = ' aria-current="page"' if ruta == marcada else ""
        return f'<li><a href="/{ruta}/"{cur}>{ambos(es, en)}</a></li>'
    nav = "".join(a(*item) for item in NAV)
    buscador = ('<a class="search" href="/docs/" aria-label="Ir a la documentación">'
                '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="width:14px;height:14px" aria-hidden="true"><circle cx="11" cy="11" r="7"/><path d="m20 20-3.5-3.5"/></svg>'
                '<span class="search-txt">Buscar en la documentación <kbd>/</kbd></span></a>') if portada else ""
    etiqueta_fuente = "Descargar código fuente" if portada else "Download source code"
    cta = (f'<a class="btn btn-solid" href="#instalar">{ambos("Descargar", "Download")}</a>' if portada
           else f'<a class="btn btn-solid" href="/docs/quickstart/">{ambos("Instalar", "Install")}</a>')
    return f'''<header class="site-header"><div class="wrap nav">
  <a class="brand" href="/"><svg class="glyph" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.1" stroke-linecap="round" aria-hidden="true"><path d="M3 6h18M3 12h12M3 18h7"/><circle cx="20" cy="15" r="2.6"/></svg>mini-format</a>
  <button type="button" class="nav-toggle" aria-expanded="false" aria-controls="nav-links"><span class="sr">{ambos("Menú", "Menu")}</span>{ICONO_MENU}</button>
  <ul class="nav-links" id="nav-links">{nav}<li class="nav-cta">{cta}</li></ul>
  <span class="spacer"></span>
  {buscador}
  <a class="icon-link" href="{SOURCE}" aria-label="{etiqueta_fuente}"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="m9 18-6-6 6-6M15 6l6 6-6 6"/></svg></a>
  <div class="seg lang-toggle" role="group" aria-label="Idioma / Language"><button type="button" data-lang-btn="es" aria-pressed="true">ES</button><button type="button" data-lang-btn="en" aria-pressed="false">EN</button></div>
  {cta}
</div></header>'''


def pie() -> str:
    def col(es, en, enlaces):
        items = "".join(f'<li><a href="{h}">{ambos(t_es, t_en)}</a></li>' for h, t_es, t_en in enlaces)
        return f"<div><h3>{ambos(es, en)}</h3><ul>{items}</ul></div>"
    c1 = col("Aprender", "Learn", [("/flujo/", "Cómo funciona", "How it works"), ("/docs/", "Introducción", "Introduction"),
                                   ("/docs/quickstart/", "Inicio rápido", "Quickstart"),
                                   (f"/docs/spec/", f"Especificación {SPEC_VERSION}", f"Specification {SPEC_VERSION}"),
                                   ("/docs/errors/", "Índice de errores", "Error index")])
    c2 = col("Componente", "Component", [("/docs/python/", "Biblioteca Python", "Python library"),
                                         ("/docs/typescript/", "Biblioteca TypeScript", "TypeScript library"),
                                         ("/docs/cli/", "Herramienta", "Command-line tool"),
                                         ("/docs/conformance/", "Conformidad", "Conformance")])
    c3 = col("Evidencia", "Evidence", [("/validacion/", "Validación", "Validation"),
                                       ("/economia/", "Economía", "Economics"),
                                       ("/ejemplo/", "Ejemplos", "Examples"),
                                       (f"{REPO}/tree/main/experiments/v5_ancho", "Eje de ancho (V5)", "Width axis (V5)"),
                                       (f"{REPO}/tree/main/experiments/v1_tokens", "Tokens (V1)", "Tokens (V1)"),
                                       (f"{REPO}/tree/main/experiments/v4_costos", "Costos (V4)", "Costs (V4)"),
                                       ("/docs/metodologia/", "Metodología", "Methodology")])
    c4 = col("Proyecto", "Project", [(SOURCE, "Código fuente", "Source code"),
                                     ("/playground/", "Playground", "Playground"),
                                     ("/ejemplo/", "Ejemplos", "Examples"),
                                     ("/docs/licencia/", "Licencia MIT", "MIT License"),
                                     ("/docs/contribuir/", "Contribuir", "Contributing")])
    es = (f"mini-format {__version__} · SPEC {SPEC_VERSION} · Adrián Palma Obispo y Erick Palomino Santa Cruz · "
          "Universidad Peruana de Ciencias Aplicadas (UPC), 2026. Cada cifra publicada sale de un script del repositorio y de datos archivados.")
    en = (f"mini-format {__version__} · SPEC {SPEC_VERSION} · Adrián Palma Obispo and Erick Palomino Santa Cruz · "
          "Universidad Peruana de Ciencias Aplicadas (UPC), 2026. Every published figure comes from a repository script and archived data.")
    return f'''<footer class="site-footer"><div class="wrap"><div class="fgrid">{c1}{c2}{c3}{c4}</div><div class="colophon">{ambos(es, en)}</div></div></footer>'''


def lateral(activo: str) -> str:
    out = [f'<a class="docs-flow-link" href="/flujo/">{ambos("Ver un flujo completo", "See a complete workflow")}</a>']
    for (titulo_es, items_es), (titulo_en, items_en) in zip(GRUPOS_ES, GRUPOS_EN):
        expandido = titulo_es == "Empezar" or activo in {ruta for ruta, _ in items_es}
        out.append(f'<details{" open" if expandido else ""}><summary>{ambos(titulo_es, titulo_en)}</summary><ul>')
        for (ruta_es, txt_es), (ruta_en, txt_en) in zip(items_es, items_en):
            assert ruta_es == ruta_en
            cur = ' aria-current="page"' if ruta_es == activo else ""
            out.append(f'<li><a href="/{ruta_es}/"{cur}>{ambos(txt_es, txt_en)}</a></li>')
        out.append("</ul></details>")
    return "".join(out)
def pagina_docs(ruta: str, titulo_es: str, titulo_en: str, cuerpo_es: str, cuerpo_en: str,
                crumbs_es: str = "", crumbs_en: str = "", aviso_es: str = "", aviso_en: str = "") -> None:
    i = ORDEN.index(ruta) if ruta in ORDEN else -1
    prev = (f'<a href="/{ORDEN[i-1]}/">{ambos("← anterior", "← previous")}'
            f"<b>{ambos(NOMBRES_ES[ORDEN[i-1]], NOMBRES_EN[ORDEN[i-1]])}</b></a>" if i > 0 else "<span></span>")
    nxt = (f'<a href="/{ORDEN[i+1]}/">{ambos("siguiente →", "next →")}'
           f"<b>{ambos(NOMBRES_ES[ORDEN[i+1]], NOMBRES_EN[ORDEN[i+1]])}</b></a>" if 0 <= i < len(ORDEN) - 1 else "<span></span>")
    migas = f'<p class="crumbs"><a href="/docs/">docs</a> / {ambos(crumbs_es or html.escape(titulo_es), crumbs_en or html.escape(titulo_en))}</p>'
    conmutador = ('<div class="seg lang-toggle" role="group" aria-label="Idioma / Language">'
                  '<button type="button" data-lang-btn="es" aria-pressed="true">Español</button>'
                  '<button type="button" data-lang-btn="en" aria-pressed="false">English</button></div>')
    doc = f'''<!doctype html><html lang="es" data-title-es="{html.escape(titulo_es)} — mini-format" data-title-en="{html.escape(titulo_en)} — mini-format"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(titulo_es)} — mini-format</title>{cabeza()}</head>
<body>{cabecera(ruta)}
<div class="docs-shell"><aside class="docs-side" aria-label="Docs">{lateral(ruta)}</aside>
<main class="docs-main" id="contenido"><article class="docs-article"><div class="docs-top">{migas}</div><div class="prose" data-lang-body="es">{aviso_es}{cuerpo_es}</div><div class="prose" data-lang-body="en" hidden>{aviso_en}{cuerpo_en}</div>
<nav class="pager">{prev}{nxt}</nav></article></main></div>{pie()}<script src="/docs.js"></script></body></html>'''
    destino = SITIO / ruta / "index.html"
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text(doc, encoding="utf-8")


def md_archivo(rel: str) -> str:
    return reescribir_enlaces(md((RAIZ / rel).read_text(encoding="utf-8")), Path(rel).parent)


def md_par(rel_es: str, rel_en: str) -> tuple[str, str]:
    """Lee el par de fuentes ES/EN y devuelve (html_es, html_en) con ids únicos."""
    es = prefijar_ids(md_archivo(rel_es), "es")
    en = prefijar_ids(md_archivo(rel_en), "en")
    return es, en
# --------------------------------------------------------------------------- páginas
def construir_docs() -> int:
    n = 0
    es, en = md_par("README.es.md", "README.md")
    pagina_docs("docs", "Introducción", "Introduction", es, en); n += 1

    for route, name_es, name_en, stem in [
        ("downloads", "Descargas", "Downloads", "downloads"),
        ("docs/quickstart", "Inicio rápido", "Quickstart", "quickstart"),
        ("docs/build", "Crear tu toolkit", "Build your toolkit", "build"),
        ("docs/spec/cambios", "Versiones y compatibilidad", "Versions and compatibility", "versions"),
    ]:
        es = md((SITIO / "content" / f"{stem}.es.md").read_text(encoding="utf-8"))
        en = md((SITIO / "content" / f"{stem}.en.md").read_text(encoding="utf-8"))
        pagina_docs(route, name_es, name_en, prefijar_ids(es, "es"), prefijar_ids(en, "en"))
        n += 1

    es, en = md_par("SPEC.es.md", "SPEC.md")
    pagina_docs("docs/spec", f"Especificación {SPEC_VERSION}", f"Specification {SPEC_VERSION}", es, en,
                aviso_es='<p class="lang">Traducción informativa al español; el texto normativo es el original en inglés.</p>',
                aviso_en='<p class="lang">Normative text; the Spanish version is an informative translation.</p>'); n += 1

    es, en = md_par("DOMAIN_PROFILE.es.md", "DOMAIN_PROFILE.md")
    pagina_docs("docs/profile", "Perfil mini-domain/1", "mini-domain/1 profile", es, en); n += 1

    es, en = md_par("FORKING.es.md", "FORKING.md")
    pagina_docs("docs/forking", "Extender: familias", "Extending: forks", es, en); n += 1
    # familias
    reg = Registry.load(RAIZ / "forks")
    contratos = sorted(reg.contracts.values() if hasattr(reg, "contracts") and isinstance(reg.contracts, dict) else reg, key=lambda c: c.prefix)
    filas_es = "".join(f'<tr><td><a href="/docs/forks/{c.prefix}/"><code>{c.prefix}</code></a></td><td>{html.escape(c.name)}</td><td>{html.escape(c.domain)}</td><td>{len(c.core)}</td><td>{len(c.extensions)}</td><td>{"<code>" + c.parent + "</code>" if c.parent else "—"}</td></tr>' for c in contratos)
    pagina_docs("docs/forks", "Familias de ejemplo", "Sample families", f"""
<h1>Familias de ejemplo · descarga opcional</h1>
<p><strong>.mini se adapta a tus datos.</strong> Estas {CIFRAS["familias"]} familias son contratos de muestra para estudiar y modificar; no hacen falta para crear tu propio toolkit ni vienen dentro de los paquetes Python o Node.</p>
<p><a class="btn btn-solid" href="/downloads/mini-format-{__version__}-example-families.zip" download>Descargar las {CIFRAS["familias"]} familias (.zip) ↓</a></p>
<p>Extrae el ZIP: obtendrás <code>forks/</code>. Para probarlo usa <code>mini --forks forks forks</code> o <code>mini --forks forks validate forks/a/fixtures/valid.mini</code>. En Python: <code>Registry.load("forks")</code>. En Node: <code>Registry.load("./forks")</code>. El directorio se indica explícitamente; puedes crear contratos nuevos sin descargarlo.</p>
<p>Para crear el tuyo desde JSON, empieza en <a href="/docs/quickstart/">Inicio rápido</a>. Para ampliar una familia, lee <a href="/docs/forking/">Extender: familias</a>.</p>
<table><thead><tr><th>Prefijo</th><th>Nombre</th><th>Dominio</th><th>Núcleo</th><th>Ext.</th><th>Padre</th></tr></thead><tbody>{filas_es}</tbody></table>
""", f"""
<h1>Sample families · optional download</h1>
<p><strong>.mini adapts to your data.</strong> These {CIFRAS["familias"]} sample contracts are for study and modification. You do not need them to build your own toolkit, and they are not bundled with the Python or Node packages.</p>
<p><a class="btn btn-solid" href="/downloads/mini-format-{__version__}-example-families.zip" download>Download {CIFRAS["familias"]} sample families (.zip) ↓</a></p>
<p>Extract the ZIP to get <code>forks/</code>. Try <code>mini --forks forks forks</code> or <code>mini --forks forks validate forks/a/fixtures/valid.mini</code>. In Python: <code>Registry.load("forks")</code>. In Node: <code>Registry.load("./forks")</code>. Pass the directory explicitly; you can create new contracts without downloading it.</p>
<p>To build your own format from JSON, start with the <a href="/docs/quickstart/">quickstart</a>. To extend a sample family, read <a href="/docs/forking/">Extending: forks</a>.</p>
<table><thead><tr><th>Prefix</th><th>Name</th><th>Domain</th><th>Core</th><th>Ext.</th><th>Parent</th></tr></thead><tbody>{filas_es}</tbody></table>
"""); n += 1

    ET = {
        "es": {"dominio": "Dominio", "version": "Versión", "padre": "Padre", "clave": "Clave de registros",
               "sep": "Separador de lista", "archivo": "Archivo", "campos": "Campos por posición",
               "tipo": "Tipo", "desc": "Descripción", "parte": "Parte", "nucleo": "núcleo",
               "ext": "extensión", "raiz": "— (raíz)", "ejemplo": "Ejemplo válido",
               "cargalo": 'Con el ZIP opcional extraído, valida con',
               "notas": "Notas de la familia", "valores": "valores", "migas": "familias"},
        "en": {"dominio": "Domain", "version": "Version", "padre": "Parent", "clave": "Records key",
               "sep": "List separator", "archivo": "File", "campos": "Fields by position",
               "tipo": "Type", "desc": "Description", "parte": "Part", "nucleo": "core",
               "ext": "extension", "raiz": "— (root)", "ejemplo": "Valid example",
               "cargalo": 'With the optional ZIP extracted, validate with',
               "notas": "Family notes", "valores": "values", "migas": "families"},
    }

    for c in sorted(reg, key=lambda c: c.prefix):
        p = reg.paths[c.prefix]
        ejemplo = (p / "fixtures" / "valid.mini").read_text(encoding="utf-8") if (p / "fixtures" / "valid.mini").exists() else ""
        notas = {}
        for lang, rel in (("es", "README.es.md"), ("en", "README.md")):
            f = p / rel
            notas[lang] = prefijar_ids(md_archivo(str(f.relative_to(RAIZ))), lang) if f.exists() else ""
        cuerpos = {}
        for lang in ("es", "en"):
            t = ET[lang]
            campos = []
            for f in list(c.core) + list(c.extensions):
                d = f.to_dict()
                extra = []
                if d.get("values"): extra.append(t["valores"] + ": " + ", ".join(map(str, d["values"])))
                for k in ("min", "max", "unique", "optional", "items", "arity"):
                    if k in d and d[k] not in (None, False, ""):
                        extra.append(f"{k}: {d[k]}")
                ext = " · ".join(extra)
                campos.append(f"<tr><td><code>{html.escape(f.name)}</code></td><td><code>{html.escape(str(d.get('type','')))}</code></td><td>{html.escape(d.get('desc',''))}{(' <small>(' + html.escape(ext) + ')</small>') if ext else ''}</td><td>{t['ext'] if f in c.extensions else t['nucleo']}</td></tr>")
            cuerpos[lang] = f"""
<h1><code>{c.prefix}</code> — {html.escape(c.name)}</h1>
<p>{html.escape(c.description)}</p>
<dl class="errbox"><dt>{t['dominio']}</dt><dd>{html.escape(c.domain)}</dd><dt>{t['version']}</dt><dd>{c.version}</dd><dt>{t['padre']}</dt><dd>{('<a href="/docs/forks/' + c.parent + '/"><code>' + c.parent + '</code></a>') if c.parent else t['raiz']}</dd><dt>{t['clave']}</dt><dd><code>{c.records_key}</code></dd><dt>{t['sep']}</dt><dd><code>{html.escape(c.list_separator)}</code></dd><dt>{t['archivo']}</dt><dd><a href="{REPO}/blob/main/forks/{c.prefix}/contract.json">forks/{c.prefix}/contract.json</a></dd></dl>
<h2>{t['campos']}</h2>
<table><thead><tr><th>#</th><th>{t['tipo']}</th><th>{t['desc']}</th><th>{t['parte']}</th></tr></thead><tbody>{''.join(campos)}</tbody></table>
<h2>{t['ejemplo']}</h2>
<pre><code>{html.escape(ejemplo)}</code></pre>
<p>{t['cargalo']} <code>mini --forks forks validate forks/{c.prefix}/fixtures/valid.mini</code>.</p>
{('<h2>' + t['notas'] + '</h2>' + notas[lang]) if notas[lang] else ''}
"""
        pagina_docs(f"docs/forks/{c.prefix}", f"Familia {c.prefix}", f"Family {c.prefix}",
                    cuerpos["es"], cuerpos["en"],
                    crumbs_es=f'<a href="/docs/forks/">familias</a> / {c.prefix}',
                    crumbs_en=f'<a href="/docs/forks/">families</a> / {c.prefix}'); n += 1

    # errores
    filas = "".join(f'<tr><td><a href="/docs/errors/{cod}/"><span class="errcode">{cod}</span></a></td><td>{html.escape(t)}</td><td><code>{const}</code></td><td>{sec}</td></tr>' for cod, const, t, _, sec in ERRORES)
    filas_en = "".join(f'<tr><td><a href="/docs/errors/{cod}/"><span class="errcode">{cod}</span></a></td><td>{html.escape(t)}</td><td><code>{const}</code></td><td>{sec}</td></tr>' for cod, const, t, _, sec in ERRORES_EN)
    pagina_docs("docs/errors", "Códigos de error", "Error codes", f"""
<h1>Códigos de error</h1>
<p>{cuenta(CIFRAS["codigos_error"], CIFRAS, "codigos_es")} códigos estables, definidos en <code>src/minifmt/errors.py</code> y reproducidos por la biblioteca TypeScript.
Son parte del contrato público del formato: un validador escrito en otro lenguaje debe producir los mismos códigos
para los mismos documentos, y la <a href="/docs/conformance/">suite de conformidad</a> lo comprueba.</p>
<p>Cada error lleva <strong>código</strong>, <strong>línea</strong> (1-based; 0 para errores de documento), <strong>campo</strong> cuando aplica y un mensaje legible.
El informe identifica la línea y el campo que debe corregirse.</p>
<table><thead><tr><th>Código</th><th>Condición</th><th>Constante</th><th>SPEC</th></tr></thead><tbody>{filas}</tbody></table>
""", f"""
<h1>Error codes</h1>
<p>{cuenta(CIFRAS["codigos_error"], CIFRAS, "codigos_en")} stable codes, defined in <code>src/minifmt/errors.py</code> and reproduced by the TypeScript library.
They are part of the format's public contract: a validator written in another language must produce the same codes
for the same documents, and the <a href="/docs/conformance/">conformance suite</a> checks it.</p>
<p>Each error carries a <strong>code</strong>, a <strong>line</strong> (1-based; 0 for document errors), a <strong>field</strong> when applicable and a readable message.
The report identifies the line and field that need correction.</p>
<table><thead><tr><th>Code</th><th>Condition</th><th>Constant</th><th>SPEC</th></tr></thead><tbody>{filas_en}</tbody></table>
"""); n += 1
    for i, ((cod, const, t, desc, sec), (_, _, t_en, desc_en, _)) in enumerate(zip(ERRORES, ERRORES_EN)):
        prev_ = f'<a href="/docs/errors/{ERRORES[i-1][0]}/">← {ERRORES[i-1][0]}</a>' if i else ""
        nxt_ = f'<a href="/docs/errors/{ERRORES[i+1][0]}/">{ERRORES[i+1][0]} →</a>' if i < len(ERRORES) - 1 else ""
        tol_es = 'Impide construir el documento' if cod == 'E01' else ('Se detecta al cargar el contrato' if cod in ('E20', 'E21') else 'Se registra y el documento se construye igual')
        tol_en = 'Prevents building the document' if cod == 'E01' else ('Detected when loading the contract' if cod in ('E20', 'E21') else 'Recorded and the document is built anyway')
        cuerpo_es = f"""
<h1><span class="errcode">{cod}</span> {html.escape(t)}</h1>
<dl class="errbox"><dt>Constante</dt><dd><code>{const}</code></dd><dt>Especificación</dt><dd><a href="/docs/spec/">{sec}</a></dd><dt>Modo tolerante</dt><dd>{tol_es}</dd></dl>
{md(desc)}
<h2>Cómo verlo</h2>
<p>En el <a href="/playground/">playground</a>, pestaña «Editor y validador», el botón «Inyectar 3 errores» provoca E04, E05, E08 y E09 sobre el ejemplo cargado.
Desde la línea de comandos, <code>mini diagnose archivo.mini</code> imprime un informe JSON con todos los errores y las líneas a regenerar.</p>
<p style="display:flex;justify-content:space-between">{prev_}<span></span>{nxt_}</p>
"""
        cuerpo_en = f"""
<h1><span class="errcode">{cod}</span> {html.escape(t_en)}</h1>
<dl class="errbox"><dt>Constant</dt><dd><code>{const}</code></dd><dt>Specification</dt><dd><a href="/docs/spec/">{sec}</a></dd><dt>Lenient mode</dt><dd>{tol_en}</dd></dl>
{md(desc_en)}
<h2>How to see it</h2>
<p>In the <a href="/playground/">playground</a>, “Editor &amp; validator” tab, the “Inject 3 errors” button triggers E04, E05, E08 and E09 on the loaded example.
From the command line, <code>mini diagnose archivo.mini</code> prints a JSON report with every error and the lines to regenerate.</p>
<p style="display:flex;justify-content:space-between">{prev_}<span></span>{nxt_}</p>
"""
        pagina_docs(f"docs/errors/{cod}", f"{cod} — {t}", f"{cod} — {t_en}",
                    prefijar_ids(cuerpo_es, "es"), prefijar_ids(cuerpo_en, "en"),
                    crumbs_es=f'<a href="/docs/errors/">errores</a> / {cod}',
                    crumbs_en=f'<a href="/docs/errors/">errors</a> / {cod}'); n += 1
    # bibliotecas
    py_es = md(f"""
# Biblioteca Python (`minifmt` {__version__})

Implementación de referencia. Sin dependencias en tiempo de ejecución; `tiktoken` es opcional para contar tokens.

## API pública

```python
from minifmt import (Contract, Field, MiniError, MiniValidationError, Document,
                     parse, dumps, detect_prefix, Registry, spec_block, parser_prompt,
                     canonical_equal, roundtrip_ok, __version__, SPEC_VERSION)
```

| Función | Qué hace |
|---|---|
| `Registry.load(dir=…)` | Descubre `forks/*/contract.json`; `reg.get("a")` devuelve el `Contract`. |
| `parse(text, contract, strict=True)` | Analiza y valida. Estricto: lanza `MiniValidationError` con todos los errores. Tolerante (`strict=False`): devuelve `Document` con `records` válidos y `errors`. |
| `Document.to_canonical()` | JSON canónico: `{{"prefix", "header", "<records_key>": [...]}}`. |
| `dumps(obj, contract)` | Canónico → `.mini`. |
| `spec_block(contract, lang="en"|"es")` | Bloque de especificación para el prompt del modelo. |
| `parser_prompt(contract, fixtures, lang)` | Prompt para que un modelo escriba un parser de la familia. |
| `roundtrip_ok(obj, contract)` | `parse(dumps(obj)) == obj` y serialización estable. |
| `detect_prefix(text)` | Prefijo declarado en la cabecera, sin validar. |

## `MiniError`

Campos: `code`, `line` (1-based, 0 = documento), `message`, `field`. `str(e)` produce `E10 line 3 [level]: …`.
Los códigos están en el [índice de errores](/docs/errors/).

## Modo tolerante

```python
doc = parse(texto, c, strict=False)
doc.records          # solo los válidos, con tipos del contrato
doc.errors           # lista de MiniError
doc.record_lines     # línea física de cada registro aceptado
doc.diagnostics()    # informe con las líneas a regenerar (mismo que `mini diagnose`)
```

## Lectura en streaming

```python
from minifmt import read_records, create_reader
for item in read_records(fragmentos, c):   # str o bytes UTF-8, partidos en cualquier punto
    procesar(item.record, item.line)        # se emite al cerrarse la línea del registro
```

`read_records` produce los mismos registros y errores que `parse` y no retiene los registros, por lo que la memoria
no crece con el tamaño del documento. `create_reader(c)` ofrece `push(fragmento)` y `end()` para integrarlo con la
respuesta en streaming de un modelo.

## Contratos desde JSON Schema y Pydantic

```python
from minifmt import from_json_schema, to_json_schema, from_pydantic
c = from_json_schema(esquema, "tk")         # registros de un nivel (SPEC §12)
esquema = to_json_schema(c)                 # ida y vuelta sin pérdida mediante anotaciones x-mini
c = from_pydantic(Modelo, "job")            # pydantic es opcional
```

Las propiedades requeridas pasan al núcleo y las opcionales a las extensiones; `format: date` produce el tipo `date`.
Una estructura con más de un nivel de anidación se rechaza con `E20`, citando SPEC §12.

## Reparación selectiva y proveedores

```python
from minifmt.ai import repair_request, merge_repair
from minifmt.ai.adapters import get_adapter
req = repair_request(respuesta, c, "es")    # solo las líneas inválidas, con sus códigos
if req.needed:
    modelo = get_adapter("openai", "gpt-5-mini")        # también "anthropic", "groq" o "simulado"
    reparada = modelo.generate(req.system, req.user, max_tokens=req.max_tokens_hint * 2, temperature=0)
    fusion = merge_repair(respuesta, reparada["text"], c, req)   # acepta cada corrección solo si es válida
```

Cambiar de proveedor no modifica el contrato ni el resto de la integración. Una demostración sin conexión del flujo
completo se ejecuta con `python demo/sin-conexion/demo.py`.
""")
    py_en = md(f"""
# Python library (`minifmt` {__version__})

Reference implementation. No runtime dependencies; `tiktoken` is optional for token counting.

## Public API

```python
from minifmt import (Contract, Field, MiniError, MiniValidationError, Document,
                     parse, dumps, detect_prefix, Registry, spec_block, parser_prompt,
                     canonical_equal, roundtrip_ok, __version__, SPEC_VERSION)
```

| Function | What it does |
|---|---|
| `Registry.load(dir=…)` | Discovers `forks/*/contract.json`; `reg.get("a")` returns the `Contract`. |
| `parse(text, contract, strict=True)` | Parses and validates. Strict: raises `MiniValidationError` with every error. Lenient (`strict=False`): returns a `Document` with valid `records` and `errors`. |
| `Document.to_canonical()` | Canonical JSON: `{{"prefix", "header", "<records_key>": [...]}}`. |
| `dumps(obj, contract)` | Canonical → `.mini`. |
| `spec_block(contract, lang="en"|"es")` | Specification block for the model's prompt. |
| `parser_prompt(contract, fixtures, lang)` | Prompt for a model to write a parser for the family. |
| `roundtrip_ok(obj, contract)` | `parse(dumps(obj)) == obj` with stable serialization. |
| `detect_prefix(text)` | Prefix declared in the header, without validating. |

## `MiniError`

Fields: `code`, `line` (1-based, 0 = document), `message`, `field`. `str(e)` yields `E10 line 3 [level]: …`.
Codes are in the [error index](/docs/errors/).

## Lenient mode

```python
doc = parse(texto, c, strict=False)
doc.records          # only the valid ones, with contract types
doc.errors           # list of MiniError
doc.record_lines     # physical line of each accepted record
doc.diagnostics()    # report with the lines to regenerate (same as `mini diagnose`)
```

## Streaming read

```python
from minifmt import read_records, create_reader
for item in read_records(chunks, c):       # str or UTF-8 bytes, split anywhere
    handle(item.record, item.line)          # emitted when the record's line closes
```

`read_records` yields the same records and errors as `parse` and does not retain records, so memory does not grow
with the document. `create_reader(c)` offers `push(chunk)` and `end()` for a model's streaming response.

## Contracts from JSON Schema and Pydantic

```python
from minifmt import from_json_schema, to_json_schema, from_pydantic
c = from_json_schema(schema, "tk")          # one-level records (SPEC §12)
schema = to_json_schema(c)                  # lossless round trip through x-mini annotations
c = from_pydantic(Model, "job")             # pydantic is optional
```

Required properties become core fields and optional ones extensions; `format: date` yields the `date` type. Deeper
nesting is rejected with `E20`, citing SPEC §12.

## Selective repair and providers

```python
from minifmt.ai import repair_request, merge_repair
from minifmt.ai.adapters import get_adapter
req = repair_request(answer, c, "en")       # only the invalid lines, with their codes
if req.needed:
    model = get_adapter("openai", "gpt-5-mini")         # also "anthropic", "groq" or "simulated"
    repaired = model.generate(req.system, req.user, max_tokens=req.max_tokens_hint * 2, temperature=0)
    merged = merge_repair(answer, repaired["text"], c, req)     # accepts each correction only if valid
```

Switching providers changes neither the contract nor the rest of the integration. An offline demonstration of the
whole flow runs with `python demo/sin-conexion/demo.py`.
""")
    pagina_docs("docs/python", "Biblioteca Python", "Python library",
                prefijar_ids(py_es, "es"), prefijar_ids(py_en, "en")); n += 1

    es, en = md_par("ts/README.md", "ts/README.en.md")
    pagina_docs("docs/typescript", "Biblioteca TypeScript", "TypeScript library", es, en); n += 1

    cli_es = md("""
# Herramienta `mini`

Se instala con el [paquete Python](/docs/quickstart/). Ejecuta `mini` en una terminal para abrir el asistente: crea un toolkit desde un archivo de datos o definiendo campos, y recibe una `GUIA.md` en la carpeta generada. También puedes crear tu propio contrato con `mini build` o `mini from-schema`. Las [familias de muestra](/docs/forks/) son opcionales; si las descargas, escribe `--forks DIR` antes del comando, por ejemplo `mini --forks forks validate respuesta.mini`.

| Comando | Qué hace |
|---|---|
| `mini setup` / `mini init` | Asistente para construir tu toolkit propio desde datos o campos. |
| `mini integrate PROYECTO --bundle .mini [--apply]` | Localiza la llamada a IA, prepara una guía y conecta código Python compatible con copia. |
| `mini forks` | Lista las familias del registro. |
| `mini validate ARCHIVO` | Validación estricta; sale con 1 si hay errores. |
| `mini diagnose ARCHIVO` | Validación tolerante; imprime un informe JSON con errores y líneas a regenerar. |
| `mini to-json ARCHIVO` | `.mini` → JSON canónico. |
| `mini from-json ARCHIVO -p PREFIJO` | JSON canónico → `.mini`. |
| `mini build MUESTRA.json [OTRAS.json] --prefix PREFIJO --out .mini` | Genera el toolkit de dominio desde muestras JSON. |
| `mini prompt PREFIJO --lang es` | Bloque de especificación para el prompt del modelo. |
| `mini tokens ARCHIVO --enc o200k_base` | Tokens y bytes, declarando el tokenizador. |
| `mini check-forks` | Comprueba los cinco invariantes y la ida y vuelta de los fixtures. |
| `mini new-fork PREFIJO --from PADRE --add "campo:tipo"` | Crea una familia nueva a partir de otra. |
| `mini from-schema ESQUEMA.json -p PREFIJO` | JSON Schema (o `--pydantic modulo:Modelo`) → contrato `.mini`. |
| `mini to-schema PREFIJO` | Contrato → JSON Schema con anotaciones `x-mini`. |
| `mini bench ARCHIVO --enc o200k_base` | Tokens y bytes en .mini, JSON, YAML, CSV y TOON, con el ahorro frente a JSON compacto. |
| `mini repair ARCHIVO --contract contract.json` | Reparación segura de una respuesta de un toolkit de dominio, sin inventar datos. |

```bash
mini from-schema ticket.schema.json -p tk --out contrato.json
mini validate respuesta.mini --contract contrato.json
mini diagnose respuesta.mini --contract contrato.json | jq '.errors'
mini prompt --contract contrato.json --lang es > prompt_sistema.txt
# Con el ZIP opcional extraído: mini --forks forks check-forks
```
""")
    cli_en = md("""
# `mini` tool

Installed with the [Python package](/docs/quickstart/). Run `mini` in a terminal to start the interactive guide: build a toolkit from a data file or define fields, then follow the generated `GUIA.md`. You can also build your own contract with `mini build` or `mini from-schema`. The [sample families](/docs/forks/) are optional; after downloading them, put `--forks DIR` before the command, for example `mini --forks forks validate response.mini`.

| Command | What it does |
|---|---|
| `mini setup` / `mini init` | Interactive guide to build your toolkit from data or fields. |
| `mini integrate PROJECT --bundle .mini [--apply]` | Locate the AI call, prepare a guide and connect supported Python with a backup. |
| `mini forks` | Lists the registry families. |
| `mini validate FILE` | Strict validation; exits 1 on errors. |
| `mini diagnose FILE` | Lenient validation; prints a JSON report with errors and lines to regenerate. |
| `mini to-json FILE` | `.mini` → canonical JSON. |
| `mini from-json FILE -p PREFIX` | Canonical JSON → `.mini`. |
| `mini build SAMPLE.json [OTHERS.json] --prefix PREFIX --out .mini` | Generates the domain toolkit from JSON samples. |
| `mini prompt PREFIX --lang es` | Specification block for the model prompt. |
| `mini tokens FILE --enc o200k_base` | Tokens and bytes, declaring the tokenizer. |
| `mini check-forks` | Checks the five invariants and fixture round-trips. |
| `mini new-fork PREFIX --from PARENT --add "field:type"` | Creates a new family from another. |
| `mini from-schema SCHEMA.json -p PREFIX` | JSON Schema (or `--pydantic module:Model`) → `.mini` contract. |
| `mini to-schema PREFIX` | Contract → JSON Schema with `x-mini` annotations. |
| `mini bench FILE --enc o200k_base` | Tokens and bytes in .mini, JSON, YAML, CSV and TOON, with the saving versus compact JSON. |
| `mini repair FILE --contract contract.json` | Safe repair of a domain-toolkit response, without guessing data. |

```bash
mini from-schema ticket.schema.json -p tk --out contract.json
mini validate response.mini --contract contract.json
mini diagnose response.mini --contract contract.json | jq '.errors'
mini prompt --contract contract.json --lang en > system_prompt.txt
# With the optional ZIP extracted: mini --forks forks check-forks
```
""")
    pagina_docs("docs/cli", "Herramienta de línea de comandos", "Command-line tool",
                prefijar_ids(cli_es, "es"), prefijar_ids(cli_en, "en")); n += 1

    es, en = md_par("conformance/README.md", "conformance/README.en.md")
    aviso_es, aviso_en = aviso_conformidad()
    pagina_docs("docs/conformance", "Suite de conformidad", "Conformance suite", es, en, aviso_es=aviso_es, aviso_en=aviso_en); n += 1

    # registro de decisiones de arquitectura (redactado en español)
    aviso_adr = "<p><em>Decision records are written in Spanish.</em></p>"
    cuerpo_adr = md_archivo("docs/adr/README.md")
    pagina_docs("docs/adr", "Registro de decisiones", "Decision records",
                prefijar_ids(cuerpo_adr, "es"), prefijar_ids(aviso_adr + cuerpo_adr, "en")); n += 1
    for adr in sorted((RAIZ / "docs" / "adr").glob("[0-9][0-9][0-9][0-9]-*.md")):
        num = adr.name[:4]
        cuerpo_adr = md_archivo(f"docs/adr/{adr.name}")
        pagina_docs(f"docs/adr/{num}", f"ADR {num}", f"ADR {num}",
                    prefijar_ids(cuerpo_adr, "es"), prefijar_ids(aviso_adr + cuerpo_adr, "en"),
                    crumbs_es=f'<a href="/docs/adr/">decisiones</a> / {num}',
                    crumbs_en=f'<a href="/docs/adr/">decisions</a> / {num}'); n += 1

    met_es = md_archivo("benchmark/public/README.es.md") + md_archivo("experiments/README.md") + md(f"""
## V5 — ancho del registro

Barre el número de campos por registro (3–50) y el tamaño del lote (1–1000) con datos sintéticos deterministas
(semilla 20260915) y tres tokenizadores. Es la referencia histórica del perfil base; la comparación principal de la portada usa el toolkit generado y los conjuntos públicos descritos arriba.
Script: [`experiments/v5_ancho/correr.py`]({REPO}/tree/main/experiments/v5_ancho).

## Reglas de integridad

* Ninguna cifra publicada sale de un cálculo que no esté en un script del repositorio con sus datos archivados.
* Los pilotos simulados no se citan como resultados.
* Los casos donde mini-format pierde se publican con la misma prominencia que los casos donde gana.
""")
    met_en = md_archivo("benchmark/public/README.md") + md_archivo("experiments/README.en.md") + md(f"""
## V5 — record width

Sweeps the number of fields per record (3–50) and the batch size (1–1000) with deterministic synthetic
data (seed 20260915) and three tokenizers. This is the historical base-profile reference; the main front-page comparison uses the generated toolkit and public datasets described above.
Script: [`experiments/v5_ancho/correr.py`]({REPO}/tree/main/experiments/v5_ancho).

## Integrity rules

* No published figure comes from a computation missing from a repository script with its archived data.
* Simulated pilots are not cited as results.
* Cases where mini-format loses are published with the same prominence as cases where it wins.
""")
    pagina_docs("docs/metodologia", "Metodología y experimentos", "Methodology and experiments",
                prefijar_ids(met_es, "es"), prefijar_ids(met_en, "en")); n += 1

    es, en = md_par("CONTRIBUTING.es.md", "CONTRIBUTING.md")
    pagina_docs("docs/contribuir", "Contribuir", "Contributing", es, en); n += 1
    lic = html.escape((RAIZ / "LICENSE").read_text(encoding="utf-8"))
    pagina_docs("docs/licencia", "Licencia", "License",
                f"<h1>Licencia MIT</h1><p>Texto legal en inglés.</p><pre><code>{lic}</code></pre>",
                f"<h1>MIT License</h1><p>Legal text, in English.</p><pre><code>{lic}</code></pre>"); n += 1
    return n
# --------------------------------------------------------------------------- playground
TRADUCCIONES = [
    ('<html lang="en">', '<html lang="es">'),
    ("<title>.mini Playground</title>", "<title>Playground — mini-format</title>"),
    # (las pestañas se traducen al sustituir la cabecera, más arriba)
    ("Each line on the left is one support ticket. On the right, the parser turns it into a JSON object your application can use. Edit a value to see validation; “Inject errors” shows what gets rejected.",
     "Cada línea de la izquierda es un ticket de soporte. A la derecha, el parser lo convierte a un objeto JSON para tu aplicación. Cambia un valor para comprobarlo; «Inyectar errores» muestra qué se rechaza."),
    ("<label>Contract <select", "<label>Contrato <select"),
    (">Load example<", ">Cargar ejemplo<"), (">Load escaping example<", ">Cargar ejemplo con escapes<"), (">Inject errors<", ">Inyectar errores<"),
    ("<h2>1 · AI response in .mini</h2>", "<h2>1 · Respuesta de la IA en .mini</h2>"),
    ("<h2>2 · JSON for your application</h2>", "<h2>2 · JSON para tu aplicación</h2>"),
    ('aria-label=".mini response"', 'aria-label="Respuesta .mini"'),
    ('aria-label="Application JSON"', 'aria-label="JSON para la aplicación"'),
    ('<summary>Field rules and AI instructions</summary>', '<summary>Reglas de los campos e instrucciones para la IA</summary>'),
    ("<h2>Contract signature</h2>", "<h2>Firma del contrato</h2>"),
    ("<summary>Prompt block for a generative model (EN)</summary>", "<summary>Bloque de prompt para un modelo generativo (EN)</summary>"),
    ("Same tickets, three ways to write them. Tokens are billable pieces of text: a smaller bar means less response cost at the same model and rate. Instructions and retries are extra.", "Mismos tickets, tres formas de escribirlos. Los tokens son fragmentos de texto facturables: una barra menor cuesta menos en la respuesta, con el mismo modelo y tarifa. Instrucciones y reintentos aparte."),
    ("<h2>How much response text does AI write?</h2>", "<h2>¿Cuánto texto escribe la IA en su respuesta?</h2>"),
    ("<h2>See the same data in another format</h2>", "<h2>Ver los mismos datos en otro formato</h2>"),
    ("<summary>All formats and measurement details</summary>", "<summary>Todos los formatos y detalles de medición</summary>"),
    ("TOON reference v4.1.1. Token counting:", "Referencia TOON v4.1.1. Recuento de tokens:"),
    ("Response serialization only; generation quality and total API cost are not measured here.", "Sólo se mide la respuesta serializada; aquí no se mide la calidad de generación ni el coste total de la API."),
    ("<label>Show <select", "<label>Mostrar <select"),
    ('<option value="toon">TOON (official, as-is)</option><option value="toon_flat">TOON (flattened, tabular)</option><option value="csv">CSV (flattened)</option><option value="json">JSON compact</option><option value="json_pretty">JSON pretty</option>',
     '<option value="toon">TOON (oficial, tal cual)</option><option value="toon_flat">TOON (aplanado, tabular)</option><option value="csv">CSV (aplanado)</option><option value="json">JSON compacto</option><option value="json_pretty">JSON indentado</option>'),
    ("Design your own contract: start blank or extend the sample, add fields, inspect the generated document and prompt, then download <code>contract.json</code>. To check a directory of contracts and fixtures later, run <code>mini --forks DIR check-forks</code>.",
     "Diseña tu contrato: empieza en blanco o amplía la muestra, añade campos, examina el documento y el prompt generados, y descarga <code>contract.json</code>. Para comprobar después tus contratos y fixtures, ejecuta <code>mini --forks DIR check-forks</code>."),
    ("<h2>1 · Identity</h2>", "<h2>1 · Identidad</h2>"), ("<h2 style=\"margin-top:14px\">2 · Fields</h2>", "<h2 style=\"margin-top:14px\">2 · Campos</h2>"),
    ("<label>Prefix <input", "<label>Prefijo <input"), ("<label>Name <input", "<label>Nombre <input"), ("<label>Parent <select", "<label>Padre <select"),
    ('<option value="">(none — blank contract)</option>', '<option value="">(ninguno — contrato en blanco)</option>'),
    ("<label>List separator <input", "<label>Separador de lista <input"), ("<label>Records key <input", "<label>Clave de registros <input"),
    (">+ add field<", ">+ añadir campo<"), ('<span class="note">types:', '<span class="note">tipos:'),
    ("<h2 style=\"margin-top:14px\">Invariant check</h2>", "<h2 style=\"margin-top:14px\">Comprobación de invariantes</h2>"),
    ("<h2>3 · Generated contract</h2>", "<h2>3 · Contrato generado</h2>"), (">Download contract.json<", ">Descargar contract.json<"), (">Open example in editor<", ">Abrir ejemplo en el editor<"),
    ("<h2 style=\"margin-top:14px\">Prompt block</h2>", "<h2 style=\"margin-top:14px\">Bloque de prompt</h2>"), ("<h2 style=\"margin-top:14px\">Example document</h2>", "<h2 style=\"margin-top:14px\">Documento de ejemplo</h2>"),
    ("<h2>Structure</h2>", "<h2>Estructura</h2>"), ("<h2 style=\"margin-top:14px\">Escapes</h2>", "<h2 style=\"margin-top:14px\">Escapes</h2>"),
    ("<h2 style=\"margin-top:14px\">Fork invariants</h2>", "<h2 style=\"margin-top:14px\">Invariantes de familia</h2>"), ("<h2>Error codes</h2>", "<h2>Códigos de error</h2>"),
    ("<tr><th>Code</th><th>Condition</th></tr>", "<tr><th>Código</th><th>Condición</th></tr>"),
    ("Full specification: <code>SPEC.md</code> in the repository. Reference implementation: Python (<code>src/minifmt</code>) and TypeScript (<code>ts/src</code>); the engine of this page, <code>js/mini.js</code>, is generated from the TypeScript library and passes the conformance suite.",
     'Especificación completa: <a href="/docs/spec/">/docs/spec/</a>. Índice de errores con una página por código: <a href="/docs/errors/">/docs/errors/</a>. Motor de esta página: <code>js/mini.js</code>, generado desde la biblioteca TypeScript y verificado con la suite de conformidad.'),
]


def construir_playground() -> None:
    tpl = (RAIZ / "playground" / "template.html").read_text(encoding="utf-8")
    # 1) estilos del sitio en lugar de los propios
    tpl = re.sub(r"<style>.*?</style>", lambda _: JS_FLAG + FONTS + '<link rel="stylesheet" href="/base.css"><link rel="stylesheet" href="/playground.css">', tpl, count=1, flags=re.S)
    # 2) cabecera del sitio + barra de pestañas (mismo <nav> y #themeBtn que espera el motor)
    cab = cabecera("playground") + '''
<div class="pg-nav"><div class="wrap">
  <nav>
    <button data-tab="editor" class="active">Editor y validador</button>
    <button data-tab="compare">Comparar formatos</button>
    <button data-tab="wizard">Asistente de familias</button>
    <button data-tab="spec">Chuleta de la norma</button>
  </nav>
  <button class="toggle" id="themeBtn" title="Cambiar tema" aria-label="Cambiar tema">◐</button>
</div></div>
<main id="contenido">
<div class="pg-intro"><div><h1>Playground</h1><p>''' + ambos('Prueba cómo una respuesta .mini se convierte a JSON. Después compara cuánto texto necesita cada formato.', 'Try converting a .mini response to JSON. Then compare how much text each format needs.') + '''</p><p class="note">''' + ambos('Práctica del formato base en tu navegador. Para conectar tu propio contrato generado por setup, sigue la', 'Base-format practice in your browser. To connect your own setup-generated contract, follow the') + ''' <a href="/docs/quickstart/">''' + ambos('guía de integración', 'integration guide') + ''' →</a></p></div>
<p class="meta">mini-format ''' + __version__ + ''' · SPEC ''' + SPEC_VERSION + '''<br>motor: js/mini.js</p></div>'''
    tpl = re.sub(r"<header>.*?</header>\s*<main>", cab, tpl, count=1, flags=re.S)
    # 3) pie del sitio
    tpl = re.sub(r"<footer>.*?</footer>", pie(), tpl, count=1, flags=re.S)
    # 4) traducción de las etiquetas visibles de la plantilla
    faltan = []
    for a, b in TRADUCCIONES:
        if a in tpl: tpl = tpl.replace(a, b)
        else: faltan.append(a[:60])
    if faltan:
        print("  aviso: cadenas no encontradas en template.html:", *faltan, sep="\n    ")
    # 5) un caso de muestra; el catálogo de 14 familias se descarga por separado
    mini_js = (RAIZ / "js" / "mini.js").read_text(encoding="utf-8")
    toon_js = (RAIZ / "benchmark" / "toon_ref" / "toon.bundle.js").read_text(encoding="utf-8")
    sys.path.insert(0, str(RAIZ / "playground"))
    from sample import sample_forks
    forks = sample_forks(RAIZ)
    safe = lambda js: js.replace("</script", "<\\/script")
    out = (tpl.replace("__MINI_JS__", safe(mini_js)).replace("__TOON_JS__", safe(toon_js))
              .replace("__FORKS_JSON__", safe(json.dumps(forks, ensure_ascii=False))))
    destino = SITIO / "playground" / "index.html"
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text(out, encoding="utf-8")
    print(f"  playground: {len(out.encode('utf-8'))//1024} KB, {len(forks)} contrato de muestra")


def precios_proveedores() -> dict:
    """Precios publicados por proveedor para estimar el costo de una corrida en el navegador.

    Se toma el modelo que usa la página si está en la tabla; si no, el más barato del proveedor,
    y se declara como referencia.
    """
    archivo = RAIZ / "experiments" / "v4_costos" / "precios.json"
    if not archivo.exists():
        return {}
    modelos = json.loads(archivo.read_text(encoding="utf-8"))["modelos"]
    quiere = {"deepseek": "deepseek-chat", "groq": "openai/gpt-oss-20b"}
    out = {}
    for proveedor, id_api in quiere.items():
        exactos = [m for m in modelos if m["proveedor"].lower().startswith(proveedor[:4]) and m["id_api"] == id_api]
        candidatos = exactos or [m for m in modelos if m["proveedor"].lower().startswith(proveedor[:4]) and m["salida"]]
        if not candidatos:
            continue
        m = candidatos[0] if exactos else min(candidatos, key=lambda x: x["salida"])
        out[proveedor] = {"entrada": m["entrada"], "salida": m["salida"], "fecha": m["fecha_consulta"],
                          "modelo_precio": m["modelo"] + ("" if exactos else " (referencia)")}
    return out

# --------------------------------------------------------------------------- V7 · escalamiento por lote
def datos_escalamiento() -> dict:
    """Resultados de experiments/v7_escalamiento: barrido, volumen y costo real de la corrida.

    Devuelve {} si el experimento no se ha corrido, y la página omite la sección.
    """
    base = RAIZ / "experiments" / "v7_escalamiento" / "results"
    barrido_dir, volumen_dir = base / "deepseek", base / "deepseek_volumen"
    if not (barrido_dir / "llamadas.jsonl").exists():
        return {}
    import csv as _csv

    meta = json.loads((barrido_dir / "meta.json").read_text(encoding="utf-8"))
    barrido = []
    if (barrido_dir / "por_lote.csv").exists():
        with (barrido_dir / "por_lote.csv").open(encoding="utf-8") as fh:
            for r in _csv.DictReader(fh):
                barrido.append({"formato": r["formato"], "lote": int(r["lote"]),
                                "llamadas": int(r["llamadas"]),
                                "aprovechamiento": float(r["aprovechamiento_pct"]),
                                "tokens_por_registro": float(r["tokens_por_registro"]),
                                "tokens_salida": int(r["tokens_salida_mediana"]),
                                "cortadas": int(r["llamadas_cortadas"]),
                                "ms": int(r["ms_mediana"])})

    def agregar(directorio):
        llamadas = directorio / "llamadas.jsonl"
        if not llamadas.exists():
            return {}
        out = {}
        for linea in llamadas.read_text(encoding="utf-8").splitlines():
            if not linea.strip():
                continue
            f = json.loads(linea)
            if f.get("error"):
                continue
            d = out.setdefault(f["formato"], {"llamadas": 0, "registros": 0, "aprovechados": 0,
                                              "tokens_salida": 0, "tokens_entrada": 0, "lote": f["lote"], "ms": 0})
            d["llamadas"] += 1
            d["registros"] += f["solicitados"]
            d["aprovechados"] += f["aprovechados"]
            d["tokens_salida"] += f["tokens_salida"] or 0
            d["tokens_entrada"] += f["tokens_entrada"] or 0
            d["ms"] += f["ms"]
        return out

    volumen = agregar(volumen_dir)
    precios = meta.get("precios", {})
    for fmt, d in volumen.items():
        d["tokens_por_registro"] = round(d["tokens_salida"] / d["registros"], 2) if d["registros"] else 0
        d["entrada_por_registro"] = round(d["tokens_entrada"] / d["registros"], 2) if d["registros"] else 0
        d["usd_estimado"] = round((d["tokens_salida"] / 1e6) * (precios.get("salida") or 0) +
                                  (d["tokens_entrada"] / 1e6) * (precios.get("entrada") or 0), 4)

    # costo real de la corrida: diferencia de saldo de la cuenta del proveedor (el saldo no se publica)
    real = {}
    archivo_real = volumen_dir / "costo_real.json"
    if archivo_real.exists():
        real = json.loads(archivo_real.read_text(encoding="utf-8"))
    quiebre = {}
    for fmt in sorted({b["formato"] for b in barrido}):
        buenos = [b["lote"] for b in barrido if b["formato"] == fmt and b["aprovechamiento"] == 100]
        malos = [b["lote"] for b in barrido if b["formato"] == fmt and b["aprovechamiento"] < 100]
        quiebre[fmt] = {"maximo_sin_perdida": max(buenos, default=0), "falla_desde": min(malos, default=None)}
    return {"meta": meta, "barrido": barrido, "volumen": volumen, "quiebre": quiebre,
            "precios": precios, "real": real}


# --------------------------------------------------------------------------- caso de integración
def datos_mesa() -> dict:
    """Una sola fuente para la demo integrada y su URL anterior."""
    from minifmt import from_json_schema, spec_block
    base = RAIZ / "examples" / "mesa-de-ayuda"
    esquema = (base / "ticket.schema.json").read_text(encoding="utf-8")
    contrato = from_json_schema(json.loads(esquema), "tk")
    grabacion = lambda formato, escenario: (base / "grabaciones" / formato / f"{escenario}.{formato}").read_text(encoding="utf-8")
    return {
        "contrato": contrato.to_dict(),
        "esquema": esquema.strip(),
        "mensajes": json.loads((base / "mensajes.json").read_text(encoding="utf-8")),
        "grabaciones": {formato: {esc: grabacion(formato, esc) for esc in ("ok", "error", "cortada")}
                        for formato in ("mini", "json")},
        "mediciones": json.loads((base / "mediciones.json").read_text(encoding="utf-8")),
        "prompt": {"es": spec_block(contrato, "es"), "en": spec_block(contrato, "en")},
        "errores": {codigo: titulo.lower() for codigo, _, titulo, _, _ in ERRORES},
        "erroresEn": {codigo: titulo.lower() for codigo, _, titulo, _, _ in ERRORES_EN},
        "escalamiento": datos_escalamiento(),
        "precios": precios_proveedores(),
    }


def construir_mesa() -> None:
    """URL anterior de la demo; comparte datos y componentes con /ejemplo/."""
    base = RAIZ / "examples" / "mesa-de-ayuda"
    datos = datos_mesa()
    safe = lambda js: js.replace("</script", "<\\/script")
    pagina = (base / "plantilla.html").read_text(encoding="utf-8")
    for marca, valor in [("__CABEZA__", cabeza()),
                         ("__CABECERA__", cabecera("mesa-de-ayuda")),
                         ("__PIE__", pie()),
                         ("__MINI_JS__", safe((RAIZ / "js" / "mini.js").read_text(encoding="utf-8"))),
                         ("__DATOS__", safe(json.dumps(datos, ensure_ascii=False)))]:
        if marca not in pagina:
            raise SystemExit(f"plantilla.html: falta la marca {marca}")
        pagina = pagina.replace(marca, valor, 1)
    destino = SITIO / "mesa-de-ayuda" / "index.html"
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text(pagina, encoding="utf-8")
    esc = datos.get("escalamiento") or {}
    print(f"  mesa de ayuda: {len(pagina.encode('utf-8'))//1024} KB, contrato tk con {len(datos['contrato']['core'])} campos"
          + (f", V7 con {len(esc['barrido'])} celdas y volumen de "
             f"{sum(v['registros'] for v in esc['volumen'].values()):,} registros" if esc else ", sin datos de V7"))


def construir_ejemplo() -> None:
    """Recorrido completo: formato propio, demo de soporte y comparación de lotes."""
    sys.path.insert(0, str(SITIO))
    from ejemplo_lote import datos_publicados
    from minifmt import Contract, dumps, parse
    import html
    datos = datos_publicados()
    origen = RAIZ / "examples" / "ejemplo-lote"
    pagina = (origen / "plantilla.html").read_text(encoding="utf-8")
    pagina = pagina.replace("__RECORRIDO__", (origen / "como-funciona.html").read_text(encoding="utf-8"))
    pagina = pagina.replace("__TU_FORMATO__", (origen / "tu-formato.html").read_text(encoding="utf-8"))
    safe = lambda js: js.replace("</script", "<" + "\\" + "/script")

    mesa = datos_mesa()
    plantilla_mesa = (RAIZ / "examples" / "mesa-de-ayuda" / "plantilla.html").read_text(encoding="utf-8")
    estilos = re.search(r"<style>(.*?)</style>", plantilla_mesa, re.S).group(1)
    demo = re.search(r"<!-- MESA DEMO -->(.*?)<!-- /MESA DEMO -->", plantilla_mesa, re.S).group(1)
    # Las mediciones siguen disponibles sin interrumpir el primer recorrido.
    mediciones = demo.index('<section class="mesa-sec">')
    demo = demo[:mediciones] + '<details class="ej-measurements"><summary>' + ambos(
        "Ver las mediciones con un modelo real", "See measurements with a real model") + '</summary>' + demo[mediciones:] + '</details>'
    controlador = re.search(r'<script>const DATOS = __DATOS__;</script>\s*<script>(.*?)</script>', plantilla_mesa, re.S).group(1)
    # DATOS queda en un ámbito propio: ambos ejemplos pueden usar sus controladores originales.
    scripts = '<script>' + safe((RAIZ / "js" / "mini.js").read_text(encoding="utf-8")) + '</script>\n<script>(function () {\nconst DATOS = ' + safe(json.dumps(mesa, ensure_ascii=False)) + ';\n' + controlador + '\n})();</script>'
    muestra = {"tickets": json.loads(mesa["grabaciones"]["json"]["ok"])["tickets"][:2]}
    contrato = Contract.from_dict(mesa["contrato"])
    texto = dumps({"header": {}, contrato.records_key: muestra["tickets"]}, contrato)
    doc = parse(texto, contrato, strict=False)
    if doc.errors or doc.records != muestra["tickets"]:
        raise SystemExit("el ejemplo de Cómo funciona no conserva sus dos tickets")
    encabezados = [("Solicitud", "Request"), ("Urgencia", "Urgency"), ("Tipo", "Type"),
                   ("Qué ocurrió", "What happened"), ("Horas", "Hours")]
    tabla = '<table><thead><tr>' + ''.join('<th scope="col">' + ambos(es, en) + '</th>' for es, en in encabezados)
    tabla += '</tr></thead><tbody>' + ''.join('<tr>' + ''.join('<td>' + html.escape(str(r[c])) + '</td>'
                 for c in ("id", "prioridad", "categoria", "resumen", "horas")) + '</tr>' for r in doc.records) + '</tbody></table>'
    for marca, valor in [("__CABEZA__", cabeza()),
                         ("__CABECERA__", cabecera("ejemplo")),
                         ("__PIE__", pie()),
                         ("__MESA_ESTILOS__", estilos),
                         ("__MESA_DEMO__", demo),
                         ("__MESA_SCRIPTS__", scripts),
                         ("__MUESTRA_JSON__", html.escape(json.dumps(muestra, ensure_ascii=False, indent=2))),
                         ("__MUESTRA_MINI__", html.escape(texto)),
                         ("__MUESTRA_TABLA__", tabla),
                         ("__PROMPT_MUESTRA_ES__", html.escape(mesa["prompt"]["es"])),
                         ("__PROMPT_MUESTRA_EN__", html.escape(mesa["prompt"]["en"])),
                         ("__VERSION__", __version__),
                         ("__DATOS__", safe(json.dumps(datos, ensure_ascii=False)))]:
        if marca not in pagina:
            raise SystemExit(f"plantilla del ejemplo: falta la marca {marca}")
        pagina = pagina.replace(marca, valor, 1)
    destino = SITIO / "ejemplo" / "index.html"
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text(pagina, encoding="utf-8")
    grande = datos["lotes"][-1]
    print(f"  ejemplo a escala: lotes de {', '.join(str(l['n']) for l in datos['lotes'])} registros; "
          f"{grande['n']} registros = {grande['tokens']['mini']} tokens en .mini y {grande['tokens']['json']} en JSON")


EJEMPLOS_TALLER = {
    "productos": {"prefijo": "pr", "tarea": (
        "Registra estos productos del inventario. Inventa un código corto para cada uno y responde solo con el documento .mini.\n"
        "- Lámpara de escritorio LED, hogar, cuesta 59.90, quedan 34 y está a la venta.\n"
        "- Audífonos inalámbricos, tecnología, 149.00, sin stock por ahora.\n"
        "- Polo de algodón talla M, ropa, 35.00, 210 unidades disponibles.\n"
        "- Café tostado de 500 g, alimentos, 28.50, 96 en almacén.\n"
        "- Silla ergonómica, hogar, 499.00, 7 unidades, disponible.\n"
        "- Teclado mecánico, tecnología, 189.90, 18 unidades.\n"
        "- Chaqueta impermeable, ropa, 159.00, retirada de la venta, quedan 3.\n"
        "- Arroz integral de 1 kg, alimentos, 6.40, 1200 unidades."), "esquema": {
        "title": "Productos del catálogo", "type": "object",
        "properties": {
            "id": {"type": "string", "description": "código del producto"},
            "nombre": {"type": "string"},
            "categoria": {"type": "string", "enum": ["hogar", "tecnología", "ropa", "alimentos"]},
            "precio": {"type": "number", "minimum": 0},
            "stock": {"type": "integer", "minimum": 0, "maximum": 5000},
            "disponible": {"type": "boolean"}},
        "required": ["id", "nombre", "categoria", "precio", "stock", "disponible"]}},
    "pedidos": {"prefijo": "pd", "tarea": (
        "Registra estos pedidos recibidos por correo. Usa el número de pedido como id y responde solo con el documento .mini.\n"
        "- PD-5001: Ana Torres pidió 2 unidades el 2026-09-14 por 89.90; ya fue enviado.\n"
        "- PD-5002: Luis Quispe, 1 unidad, 2026-09-15, total 249.00, pendiente de envío.\n"
        "- PD-5003: María Rojas compró 3 unidades el 2026-09-15 por 45.50 y ya lo recibió.\n"
        "- PD-5004: Jorge Huamán canceló su pedido de 1 unidad del 2026-09-16 (total 120.00).\n"
        "- PD-5005: Lucía Flores, 4 unidades, 2026-09-17, 310.75, enviado.\n"
        "- PD-5006: Carlos Díaz, 1 unidad, 2026-09-18, 15.00, pendiente.\n"
        "- PD-5007: Rosa Mendoza, 2 unidades, 2026-09-18, 64.00, entregado.\n"
        "- PD-5008: Pedro Salas, 6 unidades, 2026-09-19, 540.00, pendiente."), "esquema": {
        "title": "Pedidos de clientes", "type": "object",
        "properties": {
            "id": {"type": "string", "description": "número de pedido"},
            "cliente": {"type": "string"},
            "fecha": {"type": "string", "format": "date"},
            "estado": {"type": "string", "enum": ["pendiente", "enviado", "entregado", "cancelado"]},
            "total": {"type": "number", "minimum": 0},
            "unidades": {"type": "integer", "minimum": 1, "maximum": 99}},
        "required": ["id", "cliente", "fecha", "estado", "total", "unidades"]}},
}


def construir_taller() -> None:
    """Página /taller/: del JSON Schema al JSON validado en cinco pasos, con el motor js/mini.js en el navegador."""
    tickets = json.loads((RAIZ / "examples" / "mesa-de-ayuda" / "ticket.schema.json").read_text(encoding="utf-8"))
    mensajes = json.loads((RAIZ / "examples" / "mesa-de-ayuda" / "mensajes.json").read_text(encoding="utf-8"))
    tarea = ("Convierte cada mensaje de cliente en un ticket de soporte. Usa el id del mensaje como id del ticket y "
             "responde solo con el documento .mini.\n" + "\n".join(f"- {m['id']}: {m['mensaje']}" for m in mensajes))
    datos = {"ejemplos": {"tickets": {"prefijo": "tk", "esquema": tickets, "tarea": tarea}, **EJEMPLOS_TALLER}}
    safe = lambda js: js.replace("</script", "<" + "\\" + "/script")
    pagina = (RAIZ / "examples" / "taller" / "plantilla.html").read_text(encoding="utf-8")
    for marca, valor in [("__CABEZA__", cabeza()),
                         ("__CABECERA__", cabecera("taller")),
                         ("__PIE__", pie()),
                         ("__MINI_JS__", safe((RAIZ / "js" / "mini.js").read_text(encoding="utf-8"))),
                         ("__DATOS__", safe(json.dumps(datos, ensure_ascii=False)))]:
        if marca not in pagina:
            raise SystemExit(f"plantilla del taller: falta la marca {marca}")
        pagina = pagina.replace(marca, valor, 1)
    destino = SITIO / "taller" / "index.html"
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text(pagina, encoding="utf-8")
    print(f"  taller de integración: {len(pagina.encode('utf-8')) // 1024} KB, {len(datos['ejemplos'])} esquemas de ejemplo")


def construir_demo() -> None:
    """Página /demo/: el flujo completo en cinco pasos (datos, contrato, respuesta de la IA en .mini y JSON, validación con
    reparación selectiva y resultado), con respuestas grabadas o una llamada en vivo a DeepSeek con la clave del visitante."""
    datos = datos_mesa()
    datos = {k: datos[k] for k in ("contrato", "esquema", "mensajes", "grabaciones", "prompt", "errores", "erroresEn")}
    # salidas reales de la CLI para el panel de terminal (examples/demo/generar_terminal.py)
    datos["terminal"] = json.loads((RAIZ / "examples" / "demo" / "terminal.json").read_text(encoding="utf-8"))
    # precio de los tokens de salida por modelo (consulta fechada a Artificial Analysis)
    precios = json.loads((RAIZ / "examples" / "demo" / "precios_artificialanalysis.json").read_text(encoding="utf-8"))
    por_nombre = {m["modelo"]: m for m in precios["modelos"]}
    datos["precios"] = {k: precios[k] for k in ("fuente", "url", "consultado", "defecto", "equivalencias")}
    datos["precios"]["modelos"] = [por_nombre[n] for n in precios["seleccion"]]
    safe = lambda js: js.replace("</script", "<" + "\\" + "/script")
    pagina = (RAIZ / "examples" / "demo" / "plantilla.html").read_text(encoding="utf-8")
    for marca, valor in [("__CABEZA__", cabeza()),
                         ("__CABECERA__", cabecera("demo")),
                         ("__PIE__", pie()),
                         ("__MINI_JS__", safe((RAIZ / "js" / "mini.js").read_text(encoding="utf-8"))),
                         ("__DATOS__", safe(json.dumps(datos, ensure_ascii=False)))]:
        if marca not in pagina:
            raise SystemExit(f"plantilla de la demo: falta la marca {marca}")
        pagina = pagina.replace(marca, valor, 1)
    destino = SITIO / "demo" / "index.html"
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text(pagina, encoding="utf-8")
    print(f"  demo en vivo: {len(pagina.encode('utf-8')) // 1024} KB, {len(datos['mensajes'])} mensajes, contrato {datos['contrato'].get('prefix')}")


def construir_sima() -> None:
    """Página /sima/: el caso de integración en SIMA con datos archivados de llamadas reales (examples/sima/datos.json)."""
    import shutil
    origen = RAIZ / "examples" / "sima"
    datos = json.loads((origen / "datos.json").read_text(encoding="utf-8"))
    safe = lambda js: js.replace("</script", "<" + "\\" + "/script")
    pagina = (origen / "plantilla.html").read_text(encoding="utf-8")
    for marca, valor in [("__CABEZA__", cabeza()),
                         ("__CABECERA__", cabecera("sima")),
                         ("__PIE__", pie()),
                         ("__MINI_JS__", safe((RAIZ / "js" / "mini.js").read_text(encoding="utf-8"))),
                         ("__DATOS__", safe(json.dumps(datos, ensure_ascii=False)))]:
        if marca not in pagina:
            raise SystemExit(f"plantilla de SIMA: falta la marca {marca}")
        pagina = pagina.replace(marca, valor, 1)
    destino = SITIO / "sima" / "index.html"
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text(pagina, encoding="utf-8")
    shutil.copyfile(origen / "panel.png", destino.parent / "panel.png")
    k = datos["tokens"]
    print(f"  caso SIMA: {len(pagina.encode('utf-8')) // 1024} KB, banco de {datos['clase']['items_pedidos']} ítems = "
          f"{k['mini']} tokens en .mini y {k['json_compacto']} en JSON compacto")


def sellar() -> None:
    """version.json: qué commit construyó lo publicado (GITHUB_SHA en CI, 'local' fuera)."""
    import os
    from datetime import datetime, timezone
    datos = {"commit": os.environ.get("GITHUB_SHA", "local"), "construido": datetime.now(timezone.utc).isoformat(timespec="seconds"),
             "mini_format": __version__, "spec": SPEC_VERSION}
    (SITIO / "version.json").write_text(json.dumps(datos, indent=2) + "\n", encoding="utf-8")


# --------------------------------------------------------------------------- portada y 404 (fuentes escritas a mano)
def sincronizar_estatica(nombre: str, regiones: dict[str, str]) -> bool:
    """Reescribe, entre sus anclas, las regiones generadas de una página fuente (`index.html`, `404.html`).

    Las páginas fuente son HTML escrito a mano; lo único que NO se edita a mano es lo que viene de
    `cabecera()`, `pie()` y `cabeza()`: así la portada y la 404 nunca se desincronizan del menú.
    Devuelve True si el archivo cambió. Idempotente."""
    import modulos
    archivo = SITIO / nombre
    original = archivo.read_text(encoding="utf-8")
    nuevo = original
    for region, contenido in regiones.items():
        nuevo = modulos.region(nuevo, region, contenido)
    if nuevo != original:
        archivo.write_text(nuevo, encoding="utf-8")
    return nuevo != original


def sincronizar_portada() -> bool:
    return sincronizar_estatica("index.html", {"CABECERA": encabezado("", portada=True), "PIE": pie()})


def sincronizar_404() -> bool:
    return sincronizar_estatica("404.html", {"CABEZA": cabeza(), "CABECERA": cabecera(""), "PIE": pie()})


if __name__ == "__main__":
    sellar()
    n = construir_docs()
    print(f"  docs: {n} páginas")
    construir_playground()
    construir_mesa()
    construir_ejemplo()
    construir_taller()
    construir_demo()
    construir_sima()
    sincronizar_portada()
    sincronizar_404()
    import modulos
    import publicar
    modulos.ejecutar(modulos.crear_contexto(sys.modules[__name__], publicar))
    publicar.prepare_public_site(TRADUCCIONES)
    import subprocess
    subprocess.run([sys.executable, str(RAIZ / "tools" / "build_release.py"), "--output", str(SITIO / "downloads")], check=True)
    print("listo")
