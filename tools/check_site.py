"""Check generated public pages and downloadable artifacts without a network.

    python tools/check_site.py

Reglas (todas sin red, sobre `sitio/` ya construido):
  1. ids únicos por página;
  2. enlaces internos (`href`, `src`, `poster`) y anclas que existen;
  3. checksums de los artefactos de `downloads/manifest.json`;
  4. `404.html` existe, está marcado noindex y es bilingüe (el servidor debe devolver 404 REAL: ver
     sitio/servidor/NGINX_404.md; un fallback a `index.html` es un soft-404);
  5. el texto NO depende de JavaScript: cada página tiene texto visible en el HTML estático, las páginas con
     contenido `.rv` llevan la marca `js` y `base.css` la regla `html:not(.js) .rv`, y el cuerpo del idioma
     por omisión no nace oculto;
  6. cabecera unificada: todas las páginas con cabecera tienen el mismo menú que la portada (incluida
     «Validación»), y el botón de menú móvil apunta a una lista que existe;
  7. el sitemap solo enumera páginas que existen y no le falta ninguna página bilingüe en línea;
  8. `version.json` tiene sus cuatro claves;
  9. toda hoja de estilo y script local lleva el sellado `?v=` (sin él, un cambio de estilos deja la caché vieja).
"""
from __future__ import annotations

from collections import Counter
import hashlib
from html.parser import HTMLParser
import json
from pathlib import Path
import re
import sys
from urllib.parse import unquote, urljoin, urlsplit
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
SITE = ROOT / "sitio"
ORIGIN = "https://mini-format.pmoluna.com"
VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param", "source", "track", "wbr"}
MIN_TEXTO_VISIBLE = 120  # caracteres de texto visible sin JavaScript que debe tener toda página
RUTAS_EN_LINEA = ("taller", "sima", "ejemplo", "validacion", "economia", "flujo")


class Page(HTMLParser):
    """Recoge ids, enlaces, texto visible sin JS, menú y metadatos de una página."""

    def __init__(self, text):
        super().__init__(convert_charrefs=True)
        self.ids, self.links = [], []
        self.text_chars = 0
        self.classes: set[str] = set()
        self.nav_links: list[str] | None = None
        self.toggle: dict | None = None
        self.metas: dict[str, str] = {}
        self.has_js_flag = 'classList.add("js")' in text or "classList.add('js')" in text
        self.has_lang_spans = 'data-lang="es"' in text and 'data-lang="en"' in text
        self.html_attrs: dict = {}
        self.es_body_hidden = False
        self._stack: list[tuple[str, bool, str]] = []  # (etiqueta, oculto, marca: nav | cta | "")
        self._opaco = 0  # dentro de script/style/noscript/template
        self._in_body = False
        self._in_nav = 0
        self._in_cta = 0
        self.feed(text)

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        clases = (attrs.get("class") or "").split()
        if tag == "html":
            self.html_attrs = attrs
        if tag == "body":
            self._in_body = True
        if tag == "meta" and attrs.get("name"):
            self.metas[attrs["name"]] = attrs.get("content", "")
        if "id" in attrs:
            self.ids.append(attrs["id"])
        for key in ("href", "src", "poster"):
            if attrs.get(key):
                self.links.append(attrs[key])
        self.classes.update(clases)
        if tag == "button" and "nav-toggle" in clases:
            self.toggle = attrs
        marca = ""
        if tag == "ul" and "nav-links" in clases:
            self.nav_links, marca = [], "nav"
        elif tag == "li" and "nav-cta" in clases:
            marca = "cta"
        if tag == "a" and self._in_nav and not self._in_cta and attrs.get("href") and self.nav_links is not None:
            self.nav_links.append(attrs["href"])
        if attrs.get("data-lang-body") == "es" and "hidden" in attrs:
            self.es_body_hidden = True
        if tag in VOID:
            return
        if tag in {"script", "style", "noscript", "template"}:
            self._opaco += 1
        self._in_nav += marca == "nav"
        self._in_cta += marca == "cta"
        # El HTML estático ya trae `hidden` en el idioma que no se ve: es lo que cuenta sin JavaScript.
        self._stack.append((tag, "hidden" in attrs, marca))

    def handle_endtag(self, tag):
        if tag in VOID:
            return
        for i in range(len(self._stack) - 1, -1, -1):
            if self._stack[i][0] == tag:
                for t, _, marca in self._stack[i:]:
                    self._opaco -= t in {"script", "style", "noscript", "template"}
                    self._in_nav -= marca == "nav"
                    self._in_cta -= marca == "cta"
                del self._stack[i:]
                break

    def handle_data(self, data):
        if self._in_body and not self._opaco and not any(h for _, h, _ in self._stack):
            self.text_chars += len(data.strip())


def _paginas(site: Path) -> dict[Path, "Page"]:
    paginas = {}
    for path in site.rglob("*.html"):
        partes = path.relative_to(site).parts[:-1]
        if any(p in {"downloads", "servidor"} for p in partes):
            continue
        paginas[path] = Page(path.read_text(encoding="utf-8"))
    # Download indexes are public; exclude only potential HTML inside artifacts.
    for path in (site / "downloads/index.html", site / "en/downloads/index.html"):
        if path.exists():
            paginas[path] = Page(path.read_text(encoding="utf-8"))
    return paginas


def _nav_sin_idioma(links: list[str]) -> list[str]:
    return [re.sub(r"^/en(?=/)", "", h) or "/" for h in links]


def comprobar(site: Path = SITE) -> list[str]:
    """Devuelve la lista (vacía si todo está bien) de problemas del sitio construido en `site`."""
    problems: list[str] = []
    pages = _paginas(site)
    por_ruta = {p.resolve(): pg for p, pg in pages.items()}
    # ---- 1-2: ids únicos, enlaces y anclas
    for path, page in pages.items():
        relative = path.relative_to(site).as_posix()
        for name, count in Counter(page.ids).items():
            if count > 1:
                problems.append(f"{relative}: duplicate id {name}")
        for link in page.links:
            url = urlsplit(urljoin(ORIGIN + "/" + relative, link))
            if url.scheme not in {"http", "https"} or url.netloc != urlsplit(ORIGIN).netloc:
                continue
            target = (site / unquote(url.path).lstrip("/")).resolve()
            if not target.is_relative_to(site.resolve()):
                problems.append(f"{relative}: outside site {link}")
                continue
            if target.is_dir():
                target /= "index.html"
            if not target.is_file():
                problems.append(f"{relative}: missing {link}")
            elif url.fragment and target in por_ruta and unquote(url.fragment) not in por_ruta[target].ids:
                problems.append(f"{relative}: missing anchor {link}")
    # ---- 3: checksums
    manifest_path = site / "downloads/manifest.json"
    manifest = {"files": []}
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        for entry in manifest["files"]:
            data = (site / "downloads" / entry["name"]).read_bytes()
            if len(data) != entry["bytes"] or hashlib.sha256(data).hexdigest() != entry["sha256"]:
                problems.append(f"invalid release checksum: {entry['name']}")
    else:
        problems.append("downloads/manifest.json: missing")
    # ---- 4: 404.html real
    e404 = pages.get(site / "404.html")
    if e404 is None:
        problems.append("404.html: missing (el servidor necesita una página de error real; ver sitio/servidor/NGINX_404.md)")
    else:
        if "noindex" not in e404.metas.get("robots", ""):
            problems.append("404.html: falta <meta name=\"robots\" content=\"noindex\">")
        if not e404.has_lang_spans:
            problems.append("404.html: no es bilingüe (faltan los gemelos data-lang es/en)")
    # ---- 5: el texto no depende de JavaScript
    base_css = site / "base.css"
    css_ok = base_css.exists() and "html:not(.js) .rv" in base_css.read_text(encoding="utf-8")
    for path, page in pages.items():
        relative = path.relative_to(site).as_posix()
        if page.text_chars < MIN_TEXTO_VISIBLE and not relative.startswith("source/"):
            problems.append(f"{relative}: menos de {MIN_TEXTO_VISIBLE} caracteres de texto visible sin JavaScript ({page.text_chars})")
        if page.es_body_hidden and "data-localized-routes" not in page.html_attrs and not relative.startswith("en/"):
            problems.append(f"{relative}: el cuerpo en español nace oculto (sin JavaScript no se vería)")
        if ("rv" in page.classes or page.toggle is not None) and not page.has_js_flag:
            problems.append(f"{relative}: usa contenido que depende de la marca «js» pero no la pone en <head>")
        if "rv" in page.classes and not css_ok:
            problems.append(f"{relative}: base.css no tiene la regla html:not(.js) .rv (el texto quedaría con opacity:0 sin JS)")
    # ---- 6: cabecera unificada
    home = pages.get(site / "index.html")
    if home is None or not home.nav_links:
        problems.append("index.html: sin menú de navegación")
    else:
        esperado = _nav_sin_idioma(home.nav_links)
        if "/flujo/" not in esperado:
            problems.append("index.html: el menú no enlaza /flujo/")
        for path, page in pages.items():
            relative = path.relative_to(site).as_posix()
            if page.nav_links is None:
                continue
            if _nav_sin_idioma(page.nav_links) != esperado:
                problems.append(f"{relative}: el menú difiere del de la portada")
            if page.toggle is None:
                problems.append(f"{relative}: la cabecera no tiene botón de menú móvil")
            else:
                destino = page.toggle.get("aria-controls", "")
                if "aria-expanded" not in page.toggle or destino not in page.ids:
                    problems.append(f"{relative}: el botón de menú debe llevar aria-expanded y aria-controls con un id existente")
    # ---- 7: sitemap
    sitemap = site / "sitemap.xml"
    if not sitemap.exists():
        problems.append("sitemap.xml: missing")
    else:
        urls = [e.text for e in ET.parse(sitemap).getroot().iter() if e.tag.endswith("loc")]
        for url in urls:
            ruta = unquote(urlsplit(url).path).lstrip("/")
            destino = site / ruta
            if destino.is_dir():
                destino /= "index.html"
            if not destino.is_file():
                problems.append(f"sitemap.xml: {url} no existe")
        for ruta in RUTAS_EN_LINEA:
            if (site / ruta / "index.html").is_file() and f"{ORIGIN}/{ruta}/" not in urls:
                problems.append(f"sitemap.xml: falta /{ruta}/")
    # ---- 9: sellado de recursos locales
    for path, page in pages.items():
        relative = path.relative_to(site).as_posix()
        for link in page.links:
            url = urlsplit(urljoin(ORIGIN + "/" + relative, link))
            if url.netloc != urlsplit(ORIGIN).netloc or not url.path.endswith((".css", ".js")):
                continue
            if (site / unquote(url.path).lstrip("/")).is_file() and "v=" not in url.query:
                problems.append(f"{relative}: {link} no lleva el sellado ?v= (la caché no se invalidaría al cambiar el archivo)")
    # ---- 8: version.json
    version = site / "version.json"
    if not version.exists():
        problems.append("version.json: missing")
    else:
        faltan = {"commit", "construido", "mini_format", "spec"} - set(json.loads(version.read_text(encoding="utf-8")))
        if faltan:
            problems.append(f"version.json: faltan claves {sorted(faltan)}")
    return problems


def main():
    problems = comprobar(SITE)
    if problems:
        raise SystemExit("\n".join(sorted(set(problems))))
    pages = _paginas(SITE)
    manifest = json.loads((SITE / "downloads/manifest.json").read_text(encoding="utf-8"))
    print(f"PASS: {len(pages)} HTML pages, internal links/anchors, unique IDs, 404.html, no-JS text, unified header/menu, "
          f"sitemap and {len(manifest['files'])} artifact checksums")


if __name__ == "__main__":
    main()
