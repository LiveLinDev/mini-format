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
from minifmt import Registry, __version__, SPEC_VERSION  # noqa: E402

REPO = "https://github.com/LiveLinDev/mini-format"
SITE_URL = "https://mini-format.pmoluna.com"
DOWNLOAD = "/downloads/mini-format-1.2.0.zip"
SOURCE = "/downloads/mini-format-1.2.0-source.zip"
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
    ("Norma", [("docs/spec", "Especificación 1.1"), ("docs/profile", "Perfil mini-domain/1"), ("docs/spec/cambios", "Versiones y compatibilidad"), ("docs/adr", "Registro de decisiones"), ("docs/forking", "Extender: familias"), ("docs/forks", "Familias oficiales"), ("docs/errors", "Códigos de error")]),
    ("Bibliotecas", [("docs/python", "Python"), ("docs/typescript", "TypeScript"), ("docs/cli", "Herramienta de línea de comandos"), ("docs/conformance", "Suite de conformidad")]),
    ("Evidencia", [("docs/metodologia", "Metodología y experimentos")]),
    ("Proyecto", [("docs/contribuir", "Contribuir"), ("docs/licencia", "Licencia")]),
]
GRUPOS_EN = [
    ("Start", [("docs", "Introduction"), ("downloads", "Downloads"), ("docs/quickstart", "Quickstart"), ("docs/build", "Build your toolkit")]),
    ("Reference", [("docs/spec", "Specification 1.1"), ("docs/profile", "mini-domain/1 profile"), ("docs/spec/cambios", "Versions and compatibility"), ("docs/adr", "Decision records"), ("docs/forking", "Extending: forks"), ("docs/forks", "Official families"), ("docs/errors", "Error codes")]),
    ("Libraries", [("docs/python", "Python"), ("docs/typescript", "TypeScript"), ("docs/cli", "Command-line tool"), ("docs/conformance", "Conformance suite")]),
    ("Evidence", [("docs/metodologia", "Methodology and experiments")]),
    ("Project", [("docs/contribuir", "Contributing"), ("docs/licencia", "License")]),
]
ORDEN = [ruta for _, items in GRUPOS_ES for ruta, _ in items]
NOMBRES_ES = {r: t for _, it in GRUPOS_ES for r, t in it}
NOMBRES_EN = {r: t for _, it in GRUPOS_EN for r, t in it}


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
def cabecera(activo: str = "") -> str:
    def a(ruta, es, en):
        cur = ' aria-current="page"' if activo.startswith(ruta) else ""
        return f'<li><a href="/{ruta}/"{cur}>{ambos(es, en)}</a></li>'
    nav = "".join([a("docs", "Documentación", "Documentation"),
                   a("docs/spec", "Especificación", "Specification"),
                   a("docs/errors", "Errores", "Errors"),
                   a("docs/forks", "Familias", "Families"),
                   a("playground", "Playground", "Playground"),
                   a("mesa-de-ayuda", "Demo", "Demo")])
    return f'''<a class="skip" href="#contenido">{ambos("Saltar al contenido", "Skip to content")}</a>
<header class="site-header"><div class="wrap nav">
  <a class="brand" href="/"><svg class="glyph" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.1" stroke-linecap="round" aria-hidden="true"><path d="M3 6h18M3 12h12M3 18h7"/><circle cx="20" cy="15" r="2.6"/></svg>mini-format</a>
  <ul class="nav-links">{nav}</ul>
  <span class="spacer"></span>
  <a class="icon-link" href="{SOURCE}" aria-label="Download source code"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="m9 18-6-6 6-6M15 6l6 6-6 6"/></svg></a>
  <div class="seg lang-toggle" role="group" aria-label="Idioma / Language"><button type="button" data-lang-btn="es" aria-pressed="true">ES</button><button type="button" data-lang-btn="en" aria-pressed="false">EN</button></div>
  <a class="btn btn-solid" href="/docs/quickstart/">{ambos("Instalar", "Install")}</a>
</div></header>'''


def pie() -> str:
    def col(es, en, enlaces):
        items = "".join(f'<li><a href="{h}">{ambos(t_es, t_en)}</a></li>' for h, t_es, t_en in enlaces)
        return f"<div><h3>{ambos(es, en)}</h3><ul>{items}</ul></div>"
    c1 = col("Aprender", "Learn", [("/docs/", "Introducción", "Introduction"),
                                   ("/docs/quickstart/", "Inicio rápido", "Quickstart"),
                                   ("/docs/spec/", "Especificación 1.1", "Specification 1.1"),
                                   ("/docs/errors/", "Índice de errores", "Error index")])
    c2 = col("Componente", "Component", [("/docs/python/", "Biblioteca Python", "Python library"),
                                         ("/docs/typescript/", "Biblioteca TypeScript", "TypeScript library"),
                                         ("/docs/cli/", "Herramienta", "Command-line tool"),
                                         ("/docs/conformance/", "Conformidad", "Conformance")])
    c3 = col("Evidencia", "Evidence", [("/mesa-de-ayuda/", "Mesa de ayuda (demo)", "Help desk (demo)"),
                                       (f"{REPO}/tree/main/experiments/v5_ancho", "Eje de ancho (V5)", "Width axis (V5)"),
                                       (f"{REPO}/tree/main/experiments/v1_tokens", "Tokens (V1)", "Tokens (V1)"),
                                       (f"{REPO}/tree/main/experiments/v4_costos", "Costos (V4)", "Costs (V4)"),
                                       ("/docs/metodologia/", "Metodología", "Methodology")])
    c4 = col("Proyecto", "Project", [(SOURCE, "Código fuente", "Source code"),
                                     ("/playground/", "Playground", "Playground"),
                                     ("/docs/licencia/", "Licencia MIT", "MIT License"),
                                     ("/docs/contribuir/", "Contribuir", "Contributing")])
    return f'''<footer class="site-footer"><div class="wrap"><div class="fgrid">{c1}{c2}{c3}{c4}</div><div class="colophon">{ambos(f"mini-format {__version__} · SPEC {SPEC_VERSION} · Adrián Palma Obispo y Erick Palomino Santa Cruz · UPC, 2026.", f"mini-format {__version__} · SPEC {SPEC_VERSION} · Adrián Palma Obispo and Erick Palomino Santa Cruz · UPC, 2026.")}</div></div></footer>'''


def lateral(activo: str) -> str:
    out = []
    for (titulo_es, items_es), (titulo_en, items_en) in zip(GRUPOS_ES, GRUPOS_EN):
        out.append(f"<h4>{ambos(titulo_es, titulo_en)}</h4><ul>")
        for (ruta_es, txt_es), (ruta_en, txt_en) in zip(items_es, items_en):
            assert ruta_es == ruta_en
            cur = ' aria-current="page"' if ruta_es == activo else ""
            out.append(f'<li><a href="/{ruta_es}/"{cur}>{ambos(txt_es, txt_en)}</a></li>')
        out.append("</ul>")
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
<title>{html.escape(titulo_es)} — mini-format</title>{FONTS}<link rel="stylesheet" href="/base.css"><link rel="stylesheet" href="/docs.css"></head>
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
    pagina_docs("docs/forks", "Familias oficiales", "Official families", f"""
<h1>Familias oficiales</h1>
<p>Catorce contratos publicados en <code>forks/</code>. Cada familia es un archivo de datos (<code>contract.json</code>) que
la misma implementación interpreta: parser, serializador, validador y bloque de prompt se derivan de él.
Para crear la tuya, lee <a href="/docs/forking/">Extender: familias</a>.</p>
<table><thead><tr><th>Prefijo</th><th>Nombre</th><th>Dominio</th><th>Núcleo</th><th>Ext.</th><th>Padre</th></tr></thead><tbody>{filas_es}</tbody></table>
""", f"""
<h1>Official families</h1>
<p>Fourteen contracts published in <code>forks/</code>. Each family is a data file (<code>contract.json</code>)
that the same implementation interprets: parser, serializer, validator and prompt block are all derived from it.
To create yours, read <a href="/docs/forking/">Extending: forks</a>.</p>
<table><thead><tr><th>Prefix</th><th>Name</th><th>Domain</th><th>Core</th><th>Ext.</th><th>Parent</th></tr></thead><tbody>{filas_es}</tbody></table>
"""); n += 1

    ET = {
        "es": {"dominio": "Dominio", "version": "Versión", "padre": "Padre", "clave": "Clave de registros",
               "sep": "Separador de lista", "archivo": "Archivo", "campos": "Campos por posición",
               "tipo": "Tipo", "desc": "Descripción", "parte": "Parte", "nucleo": "núcleo",
               "ext": "extensión", "raiz": "— (raíz)", "ejemplo": "Ejemplo válido",
               "cargalo": 'Cárgalo en el <a href="/playground/">playground</a> o valida con',
               "notas": "Notas de la familia", "valores": "valores", "migas": "familias"},
        "en": {"dominio": "Domain", "version": "Version", "padre": "Parent", "clave": "Records key",
               "sep": "List separator", "archivo": "File", "campos": "Fields by position",
               "tipo": "Type", "desc": "Description", "parte": "Part", "nucleo": "core",
               "ext": "extension", "raiz": "— (root)", "ejemplo": "Valid example",
               "cargalo": 'Load it in the <a href="/playground/">playground</a> or validate with',
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
<p>{t['cargalo']} <code>mini validate forks/{c.prefix}/fixtures/valid.mini</code>.</p>
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
<p>Quince códigos estables, definidos en <code>src/minifmt/errors.py</code> y reproducidos por la biblioteca TypeScript.
Son parte del contrato público del formato: un validador escrito en otro lenguaje debe producir los mismos códigos
para los mismos documentos, y la <a href="/docs/conformance/">suite de conformidad</a> lo comprueba.</p>
<p>Cada error lleva <strong>código</strong>, <strong>línea</strong> (1-based; 0 para errores de documento), <strong>campo</strong> cuando aplica y un mensaje legible.
El informe identifica la línea y el campo que debe corregirse.</p>
<table><thead><tr><th>Código</th><th>Condición</th><th>Constante</th><th>SPEC</th></tr></thead><tbody>{filas}</tbody></table>
""", f"""
<h1>Error codes</h1>
<p>Fifteen stable codes, defined in <code>src/minifmt/errors.py</code> and reproduced by the TypeScript library.
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

Se instala con el [paquete Python](/docs/quickstart/). La opción global `--forks DIR` se escribe antes del comando para usar
otro directorio de familias: `mini --forks mis-familias validate respuesta.mini`.

| Comando | Qué hace |
|---|---|
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
mini validate forks/a/fixtures/valid.mini
mini diagnose respuesta.mini | jq '.errors'
mini prompt log --lang es > prompt_sistema.txt
mini new-fork quiz2 --from a --add "feedback:str" "level:enum{easy|hard}"
mini check-forks
mini bench forks/a/fixtures/valid.mini -p a --format table
```
""")
    cli_en = md("""
# `mini` tool

Installed with the [Python package](/docs/quickstart/). Put the global `--forks DIR` option before the command to use
another family directory: `mini --forks my-families validate response.mini`.

| Command | What it does |
|---|---|
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
mini validate forks/a/fixtures/valid.mini
mini diagnose respuesta.mini | jq '.errors'
mini prompt log --lang es > prompt_sistema.txt
mini new-fork quiz2 --from a --add "feedback:str" "level:enum{easy|hard}"
mini check-forks
```
""")
    pagina_docs("docs/cli", "Herramienta de línea de comandos", "Command-line tool",
                prefijar_ids(cli_es, "es"), prefijar_ids(cli_en, "en")); n += 1

    es, en = md_par("conformance/README.md", "conformance/README.en.md")
    pagina_docs("docs/conformance", "Suite de conformidad", "Conformance suite", es, en); n += 1

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
    ("<b>.mini</b> is a family of contracts. Each card is a fork: a contract (data, not code) that the same parser interprets. Click a card to load its example in the editor. Lineage arrows show <code>parent → child</code> forks that keep the core stable and only append fields.",
     "<b>.mini</b> es una familia de contratos. Cada tarjeta es una familia: un contrato (datos, no código) que interpreta el mismo parser. Pulsa una tarjeta para cargar su ejemplo en el editor. Las flechas de linaje muestran <code>padre → hija</code>: familias que conservan el núcleo y solo añaden campos."),
    ("<label>Fork <select", "<label>Familia <select"),
    (">Load example<", ">Cargar ejemplo<"), (">Load escaping example<", ">Cargar ejemplo con escapes<"), (">Inject 3 errors<", ">Inyectar 3 errores<"),
    ("<h2>.mini document</h2>", "<h2>Documento .mini</h2>"),
    ("<h2>Canonical JSON <span class=\"muted\">(edit and press “JSON → .mini”)</span></h2>", "<h2>JSON canónico <span class=\"muted\">(edita y pulsa «JSON → .mini»)</span></h2>"),
    ("<h2>Contract signature</h2>", "<h2>Firma del contrato</h2>"),
    ("<summary>Prompt block for a generative model (EN)</summary>", "<summary>Bloque de prompt para un modelo generativo (EN)</summary>"),
    ("The current editor document (canonical object) serialized into every format from the <em>same</em> data. TOON is encoded with the <b>official TOON reference implementation</b> (v4.1.1, bundled). Token counts use",
     "El documento actual del editor (objeto canónico) serializado en todos los formatos a partir de los <em>mismos</em> datos. TOON se codifica con la <b>implementación oficial de referencia de TOON</b> (v4.1.1, incluida). El recuento de tokens usa"),
    ("<h2>Tokens per format</h2>", "<h2>Tokens por formato</h2>"), ("<h2>Serialized output</h2>", "<h2>Salida serializada</h2>"),
    ("<label>Show <select", "<label>Mostrar <select"),
    ('<option value="toon">TOON (official, as-is)</option><option value="toon_flat">TOON (flattened, tabular)</option><option value="csv">CSV (flattened)</option><option value="json">JSON compact</option><option value="json_pretty">JSON pretty</option>',
     '<option value="toon">TOON (oficial, tal cual)</option><option value="toon_flat">TOON (aplanado, tabular)</option><option value="csv">CSV (aplanado)</option><option value="json">JSON compacto</option><option value="json_pretty">JSON indentado</option>'),
    ("Design a fork in four steps: (1) choose a parent or start blank, (2) add fields — inherited fields stay fixed, new ones are appended, (3) read the contract + prompt block, (4) download <code>contract.json</code> and run <code>mini check-forks</code>. The invariants of §10 are checked live.",
     "Diseña una familia en cuatro pasos: (1) elige un padre o empieza en blanco, (2) añade campos — los heredados quedan fijos, los nuevos se añaden al final, (3) lee el contrato y el bloque de prompt, (4) descarga <code>contract.json</code> y ejecuta <code>mini check-forks</code>. Los invariantes de §10 se comprueban en vivo."),
    ("<h2>1 · Identity</h2>", "<h2>1 · Identidad</h2>"), ("<h2 style=\"margin-top:14px\">2 · Fields</h2>", "<h2 style=\"margin-top:14px\">2 · Campos</h2>"),
    ("<label>Prefix <input", "<label>Prefijo <input"), ("<label>Name <input", "<label>Nombre <input"), ("<label>Parent <select", "<label>Padre <select"),
    ('<option value="">(none — blank contract)</option>', '<option value="">(ninguno — contrato en blanco)</option>'),
    ("<label>List separator <input", "<label>Separador de lista <input"), ("<label>Records key <input", "<label>Clave de registros <input"),
    (">+ add field<", ">+ añadir campo<"), ('<span class="note">types:', '<span class="note">tipos:'),
    ("<h2 style=\"margin-top:14px\">Invariant check</h2>", "<h2 style=\"margin-top:14px\">Comprobación de invariantes</h2>"),
    ("<h2>3 · Generated contract</h2>", "<h2>3 · Contrato generado</h2>"), (">Download contract.json<", ">Descargar contract.json<"), (">Open example in editor<", ">Abrir ejemplo en el editor<"),
    ("<h2 style=\"margin-top:14px\">Prompt block</h2>", "<h2 style=\"margin-top:14px\">Bloque de prompt</h2>"), ("<h2 style=\"margin-top:14px\">Example document</h2>", "<h2 style=\"margin-top:14px\">Documento de ejemplo</h2>"),
    ("Pre-computed results of <code>benchmark/run_benchmark.py</code> (o200k_base, n = 12 records per fork). Bars are tokens; the dotted line is the content-only lower bound (payload).",
     "Resultados precalculados de <code>benchmark/run_benchmark.py</code> (o200k_base, n = 12 registros por familia). Las barras son tokens; la línea punteada es la cota inferior de solo contenido (carga útil)."),
    ("<h2>Tokens by format and fork (n = 12)</h2>", "<h2>Tokens por formato y familia (n = 12)</h2>"), ("<h2>Summary</h2>", "<h2>Resumen</h2>"),
    ("<h2>Structure</h2>", "<h2>Estructura</h2>"), ("<h2 style=\"margin-top:14px\">Escapes</h2>", "<h2 style=\"margin-top:14px\">Escapes</h2>"),
    ("<h2 style=\"margin-top:14px\">Fork invariants</h2>", "<h2 style=\"margin-top:14px\">Invariantes de familia</h2>"), ("<h2>Error codes</h2>", "<h2>Códigos de error</h2>"),
    ("<tr><th>Code</th><th>Condition</th></tr>", "<tr><th>Código</th><th>Condición</th></tr>"),
    ("Full specification: <code>SPEC.md</code> in the repository. Reference implementation: Python (<code>src/minifmt</code>) and TypeScript (<code>ts/src</code>); the engine of this page, <code>js/mini.js</code>, is generated from the TypeScript library and passes the conformance suite.",
     'Especificación completa: <a href="/docs/spec/">/docs/spec/</a>. Índice de errores con una página por código: <a href="/docs/errors/">/docs/errors/</a>. Motor de esta página: <code>js/mini.js</code>, generado desde la biblioteca TypeScript y verificado con la suite de conformidad.'),
]


def construir_playground() -> None:
    tpl = (RAIZ / "playground" / "template.html").read_text(encoding="utf-8")
    # 1) estilos del sitio en lugar de los propios
    tpl = re.sub(r"<style>.*?</style>", FONTS + '<link rel="stylesheet" href="/base.css"><link rel="stylesheet" href="/playground.css">', tpl, count=1, flags=re.S)
    # 2) cabecera del sitio + barra de pestañas (mismo <nav> y #themeBtn que espera el motor)
    cab = cabecera("playground") + '''
<div class="pg-nav"><div class="wrap">
  <nav>
    <button data-tab="forks" class="active">Familias</button>
    <button data-tab="editor">Editor y validador</button>
    <button data-tab="compare">Comparar formatos</button>
    <button data-tab="wizard">Asistente de familias</button>
    <button data-tab="bench">Benchmark</button>
    <button data-tab="spec">Chuleta de la norma</button>
  </nav>
  <button class="toggle" id="themeBtn" title="Cambiar tema" aria-label="Cambiar tema">◐</button>
</div></div>
<main id="contenido">
<div class="pg-intro"><div><h1>Playground</h1><p>Valida documentos, convierte JSON ↔ .mini, compara tokens contra JSON, YAML, XML, CSV y el codificador oficial de TOON, y diseña tu propia familia. Todo corre en tu navegador.</p></div>
<p class="meta">mini-format ''' + __version__ + ''' · SPEC ''' + SPEC_VERSION + '''<br>motor: js/mini.js · 14 familias</p></div>'''
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
    # 5) datos embebidos, igual que playground/build.py
    mini_js = (RAIZ / "js" / "mini.js").read_text(encoding="utf-8")
    toon_js = (RAIZ / "benchmark" / "toon_ref" / "toon.bundle.js").read_text(encoding="utf-8")
    reg = Registry.load(RAIZ / "forks")
    orden = ["a", "q", "card", "sum", "map", "r", "s", "code", "tc", "us", "log", "ner", "cat", "cls"]
    forks = []
    for c in sorted(reg, key=lambda c: (orden.index(c.prefix) if c.prefix in orden else 99, c.prefix)):
        p = reg.paths[c.prefix]
        e = {"prefix": c.prefix, "contract": json.loads((p / "contract.json").read_text(encoding="utf-8")),
             "example": (p / "fixtures" / "valid.mini").read_text(encoding="utf-8")}
        if (p / "fixtures" / "escaping.mini").exists():
            e["escaping"] = (p / "fixtures" / "escaping.mini").read_text(encoding="utf-8")
        forks.append(e)
    import csv
    bench = []
    summ = RAIZ / "benchmark" / "results" / "summary_12.csv"
    if summ.exists():
        for r in csv.DictReader(open(summ, encoding="utf-8")):
            bench.append({k: (float(v) if k != "prefix" and "." in v else (int(v) if k != "prefix" else v)) for k, v in r.items()})
    safe = lambda js: js.replace("</script", "<\\/script")
    out = (tpl.replace("__MINI_JS__", safe(mini_js)).replace("__TOON_JS__", safe(toon_js))
              .replace("__FORKS_JSON__", safe(json.dumps(forks, ensure_ascii=False))).replace("__BENCH_JSON__", safe(json.dumps(bench))))
    destino = SITIO / "playground" / "index.html"
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text(out, encoding="utf-8")
    print(f"  playground: {len(out.encode('utf-8'))//1024} KB, {len(forks)} familias, {len(bench)} filas de benchmark")


# --------------------------------------------------------------------------- caso de integración
def construir_mesa() -> None:
    """Página /mesa-de-ayuda/: el caso de integración corriendo en el navegador con js/mini.js.

    Los datos (esquema, mensajes y respuestas grabadas) están en examples/mesa-de-ayuda/; el contrato
    no se escribe a mano: se genera aquí con la misma conversión que `mini from-schema`.
    """
    from minifmt import from_json_schema, spec_block
    base = RAIZ / "examples" / "mesa-de-ayuda"
    esquema = (base / "ticket.schema.json").read_text(encoding="utf-8")
    contrato = from_json_schema(json.loads(esquema), "tk")
    grabacion = lambda formato, escenario: (base / "grabaciones" / formato / f"{escenario}.{formato}").read_text(encoding="utf-8")
    datos = {
        "contrato": contrato.to_dict(),
        "esquema": esquema.strip(),
        "mensajes": json.loads((base / "mensajes.json").read_text(encoding="utf-8")),
        "grabaciones": {formato: {esc: grabacion(formato, esc) for esc in ("ok", "error", "cortada")}
                        for formato in ("mini", "json")},
        "mediciones": json.loads((base / "mediciones.json").read_text(encoding="utf-8")),
        "prompt": {"es": spec_block(contrato, "es"), "en": spec_block(contrato, "en")},
        "errores": {codigo: titulo.lower() for codigo, _, titulo, _, _ in ERRORES},
        "erroresEn": {codigo: titulo.lower() for codigo, _, titulo, _, _ in ERRORES_EN},
    }
    safe = lambda js: js.replace("</script", "<\\/script")
    pagina = (base / "plantilla.html").read_text(encoding="utf-8")
    for marca, valor in [("__CABEZA__", FONTS + '<link rel="stylesheet" href="/base.css"><link rel="stylesheet" href="/docs.css">'),
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
    print(f"  mesa de ayuda: {len(pagina.encode('utf-8'))//1024} KB, contrato tk con {len(contrato.core)} campos")


def sellar() -> None:
    """version.json: qué commit construyó lo publicado (GITHUB_SHA en CI, 'local' fuera)."""
    import os
    from datetime import datetime, timezone
    datos = {"commit": os.environ.get("GITHUB_SHA", "local"), "construido": datetime.now(timezone.utc).isoformat(timespec="seconds"),
             "mini_format": __version__, "spec": SPEC_VERSION}
    (SITIO / "version.json").write_text(json.dumps(datos, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    sellar()
    n = construir_docs()
    print(f"  docs: {n} páginas")
    construir_playground()
    construir_mesa()
    from publicar import prepare_public_site
    prepare_public_site(TRADUCCIONES)
    import subprocess
    subprocess.run([sys.executable, str(RAIZ / "tools" / "build_release.py"), "--output", str(SITIO / "downloads")], check=True)
    print("listo")
