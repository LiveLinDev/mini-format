"""Public-site assembly: local evidence links, static locales and SEO metadata."""
from __future__ import annotations

import html
import ast
import hashlib
import json
import re
import shutil
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import parse_qsl, unquote, urlencode, urlsplit

ROOT = Path(__file__).resolve().parents[1]
SITE = ROOT / "sitio"
ORIGIN = "https://mini-format.pmoluna.com"
REPO = "https://github.com/LiveLinDev/mini-format"
SOURCE_ZIP = "/downloads/mini-format-1.2.0-source.zip"
ALLOW_ROOTS = {"benchmark", "experiments", "conformance", "forks", "src", "ts", "js", "docs"}
ALLOW_SUFFIX = {".md", ".json", ".csv", ".py", ".ts", ".js", ".mini", ".txt", ".toml", ".png", ".svg", ".yaml", ".yml"}
EXCLUDE = {"node_modules", "__pycache__", ".venv", ".git", "vocab", "dist"}
COPIED: set[str] = set()


def version_assets(text: str, digest_cache: dict[str, str]) -> str:
    """Version local runtime assets by their bytes, replacing earlier v values."""
    def replace(match: re.Match) -> str:
        attr, value = match.groups()
        url = urlsplit(html.unescape(value))
        if url.scheme or url.netloc or not url.path.startswith("/"):
            return match.group(0)
        relative = unquote(url.path).lstrip("/")
        asset = (SITE / relative).resolve()
        if not asset.is_relative_to(SITE.resolve()) or asset.suffix not in {".css", ".js", ".mp4", ".svg"} or not asset.is_file():
            return match.group(0)
        if relative not in digest_cache:
            digest_cache[relative] = hashlib.sha256(asset.read_bytes()).hexdigest()[:16]
        query = [(key, val) for key, val in parse_qsl(url.query, keep_blank_values=True) if key != "v"]
        query.append(("v", digest_cache[relative]))
        target = url.path + "?" + urlencode(query) + ("#" + url.fragment if url.fragment else "")
        return f'{attr}="{html.escape(target, quote=True)}"'
    return re.sub(r'(href|src)="([^"]+)"', replace, text)


def source_link(rel: str) -> str:
    """Publish only referenced public source material from explicitly allowed trees."""
    rel = unquote(rel).split("#", 1)[0].split("?", 1)[0].strip("/")
    path = (ROOT / rel).resolve()
    if not path.is_relative_to(ROOT) or not path.exists():
        return SOURCE_ZIP
    parts = Path(rel).parts
    if any(p in EXCLUDE or p.startswith(".") for p in parts):
        return SOURCE_ZIP
    if len(parts) > 1 and parts[0] not in ALLOW_ROOTS:
        return SOURCE_ZIP
    if parts and parts[0] == "experiments":
        permitted = {"README.md", "README.en.md", "comun.py", "v1_tokens", "v4_costos", "v5_ancho",
                     "v7_escalamiento"}
        if len(parts) < 2 or parts[1] not in permitted:
            return SOURCE_ZIP
    if path.is_file() and path.suffix not in ALLOW_SUFFIX and path.name != "LICENSE":
        return SOURCE_ZIP
    if rel in COPIED:
        return "/source/" + rel + ("/" if path.is_dir() else "")
    COPIED.add(rel)
    dst = SITE / "source" / rel
    if path.is_file():
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, dst)
        return "/source/" + rel
    entries = []
    dst.mkdir(parents=True, exist_ok=True)
    for child in sorted(path.iterdir(), key=lambda p: (not p.is_dir(), p.name)):
        if child.name.startswith(".") or child.name in EXCLUDE:
            continue
        if child.is_file() and child.suffix not in ALLOW_SUFFIX:
            continue
        link = source_link(child.relative_to(ROOT).as_posix())
        if link == SOURCE_ZIP:
            continue
        entries.append(f'<li><a href="{html.escape(link)}">{html.escape(child.name)}{"/" if child.is_dir() else ""}</a></li>')
    title = html.escape(rel)
    (dst / "index.html").write_text(
        '<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
        f'<title>{title} — mini-format source</title><link rel="stylesheet" href="/base.css"><link rel="stylesheet" href="/docs.css">'
        f'<main class="wrap prose" style="padding-block:3rem"><a href="/docs/metodologia/">← Documentation / Documentación</a><h1>{title}</h1>'
        f'<p>Public source files · <a href="{SOURCE_ZIP}">Download all source</a></p><ul>{"".join(entries)}</ul></main></html>', encoding="utf-8")
    return "/source/" + rel + "/"


def local_sources(text: str) -> str:
    def replace(match: re.Match) -> str:
        attr, url = match.groups()
        tail = html.unescape(url)[len(REPO):]
        found = re.match(r"/(?:blob|tree|raw)/main/(.*)", tail)
        target = source_link(found.group(1)) if found else SOURCE_ZIP
        return f'{attr}="{html.escape(target, quote=True)}"'
    text = re.sub(r'(href|src)="(' + re.escape(REPO) + r'[^"]*)"', replace, text)
    # The landing source is also a rendered file; rebuild previously localized
    # evidence links after clearing the generated source directory.
    return re.sub(r'(href|src)="/source/([^"]+)"', lambda m: f'{m.group(1)}="{html.escape(source_link(m.group(2)), quote=True)}"', text)


class TranslateLanding(HTMLParser):
    """Translate prose without changing DOM geometry, class names or code examples."""
    def __init__(self, mapping: dict[str, str]):
        super().__init__(convert_charrefs=False)
        self.mapping = mapping
        self.output: list[str] = []
        self.skip = 0

    def handle_starttag(self, tag, attrs):
        raw = self.get_starttag_text()
        if tag in {"script", "style", "pre"}:
            self.skip += 1
        for key, value in attrs:
            if key in {"aria-label", "title", "alt", "placeholder"} and value:
                translated = self.mapping.get(value, value)
                if translated != value:
                    raw = raw.replace(html.escape(value, quote=True), html.escape(translated, quote=True))
        self.output.append(raw)

    def handle_startendtag(self, tag, attrs):
        self.output.append(self.get_starttag_text())

    def handle_endtag(self, tag):
        if tag in {"script", "style", "pre"}:
            self.skip -= 1
        self.output.append(f"</{tag}>")

    def handle_data(self, data):
        if self.skip:
            self.output.append(data)
            return
        key = " ".join(data.split())
        value = self.mapping.get(key)
        if value is None:
            value = re.sub(r"(?<=\d),(?=\d)", ".", data).replace("IC95", "95% CI")
        else:
            value = (" " if data[:1].isspace() else "") + html.escape(value) + (" " if data[-1:].isspace() else "")
        self.output.append(value)

    def handle_entityref(self, name): self.output.append(f"&{name};")
    def handle_charref(self, name): self.output.append(f"&#{name};")
    def handle_comment(self, data): self.output.append(f"<!--{data}-->")
    def handle_decl(self, data): self.output.append(f"<!{data}>")


def localized(text: str, lang: str, path: str) -> str:
    text = re.sub(r'<html\b[^>]*>', lambda m: re.sub(r'\s(?:lang|data-localized-routes)="[^"]*"', "", m.group(0))[:-1] + f' lang="{lang}" data-localized-routes="1">', text, count=1)
    if lang == "en":
        title = re.search(r'data-title-en="([^"]+)"', text)
        if title:
            text = re.sub(r"<title>.*?</title>", f"<title>{title.group(1)}</title>", text, count=1)
        text = re.sub(r'<(span|div)([^>]*data-lang(?:-body)?="es"[^>]*)>', lambda m: f'<{m.group(1)}{m.group(2)} hidden>' if " hidden" not in m.group(2) else m.group(0), text)
        text = re.sub(r'<(span|div)([^>]*data-lang(?:-body)?="en"[^>]*)>', lambda m: f'<{m.group(1)}{m.group(2).replace(" hidden", "")}>', text)
        text = text.replace('data-lang-btn="es" aria-pressed="true"', 'data-lang-btn="es" aria-pressed="false"').replace('data-lang-btn="en" aria-pressed="false"', 'data-lang-btn="en" aria-pressed="true"')
        text = re.sub(r'href="(/(?:docs(?:/[^"#?]*)?|playground/|mesa-de-ayuda/|downloads/|)(?:[#?][^"]*)?)"', lambda m: 'href="/en' + m.group(1) + '"', text)
        text = re.sub(r'src="/app\.js(?:\?[^"]*)?"', 'src="/app.en.js"', text)
        text = text.replace('/assets/workflow.mp4', '/assets/workflow.en.mp4')
    # Every locale has an independently crawlable URL and reciprocal alternates.
    canonical = ORIGIN + ("/en" if lang == "en" else "") + path
    text = re.sub(r'<link\s+rel="(?:canonical|alternate)"[^>]*>\s*', "", text)
    text = re.sub(r'<meta\s+(?:name="description"|property="og:[^"]+")[^>]*>\s*', "", text)
    title_match = re.search(r"<title>(.*?)</title>", text)
    title = html.unescape(title_match.group(1)) if title_match else "mini-format"
    desc = ("Crea tu toolkit .mini desde muestras JSON: contrato, prompt, parser, validador y reparación. Descarga el paquete y mide el ahorro con tus datos." if lang == "es" else "Build your .mini toolkit from JSON samples: contract, prompt, parser, validation and repair. Download the package and measure savings on your data.")
    text = re.sub(r'<link\s+rel="icon"[^>]*>\s*', "", text)
    meta = '<link rel="icon" href="/favicon.svg" type="image/svg+xml">\n'
    meta += f'<meta name="description" content="{html.escape(desc, quote=True)}">\n'
    meta += f'<link rel="canonical" href="{canonical}">\n<link rel="alternate" hreflang="es" href="{ORIGIN}{path}">\n<link rel="alternate" hreflang="en" href="{ORIGIN}/en{path}">\n<link rel="alternate" hreflang="x-default" href="{ORIGIN}{path}">\n'
    meta += f'<meta property="og:type" content="website"><meta property="og:title" content="{html.escape(title, quote=True)}"><meta property="og:description" content="{html.escape(desc, quote=True)}"><meta property="og:url" content="{canonical}"><meta property="og:locale" content="{"es_ES" if lang == "es" else "en_US"}">\n'
    if path == "/":
        schema = {"@context": "https://schema.org", "@type": "SoftwareApplication", "name": "mini-format", "applicationCategory": "DeveloperApplication", "operatingSystem": "Windows, macOS, Linux", "softwareVersion": "1.2.0", "license": "https://opensource.org/license/mit", "downloadUrl": ORIGIN + "/downloads/mini-format-1.2.0.zip", "offers": {"@type": "Offer", "price": "0", "priceCurrency": "USD"}, "inLanguage": lang, "description": desc}
        meta += '<script type="application/ld+json">' + json.dumps(schema, ensure_ascii=False) + '</script>\n'
    # Avoid duplicate structured data on repeated builds.
    text = re.sub(r'<script type="application/ld\+json">.*?</script>\s*', "", text, flags=re.S)
    return text.replace("</head>", meta + "</head>", 1)


def prepare_public_site(playground_translations=()) -> None:
    from benchmarks import inject_benchmarks
    COPIED.clear()
    # This directory contains build outputs only. Resolve and validate before
    # removing stale outputs, so a formerly linked file cannot leak into a release.
    source_output = SITE / "source"
    if source_output.exists():
        if source_output.resolve() != (SITE.resolve() / "source") or source_output.is_symlink():
            raise ValueError("Unsafe generated-source output path")
        shutil.rmtree(source_output)
    mapping = json.loads((SITE / "landing.en.json").read_text(encoding="utf-8"))
    dynamic = json.loads((SITE / "animation.en.json").read_text(encoding="utf-8"))
    def js_translate(match):
        try:
            value = ast.literal_eval(match.group(0))
        except (ValueError, SyntaxError):
            return match.group(0)
        if value in dynamic:
            return json.dumps(dynamic[value], ensure_ascii=False)
        stripped = value.strip()
        if stripped in mapping:
            return json.dumps(value.replace(stripped, mapping[stripped]), ensure_ascii=False)
        return match.group(0)
    javascript = (SITE / "app.js").read_text(encoding="utf-8")
    javascript = re.sub(r"\"(?:[^\"\\]|\\.)*\"|'(?:[^'\\]|\\.)*'", js_translate, javascript)
    (SITE / "app.en.js").write_text(javascript, encoding="utf-8")
    routes = [SITE / "index.html", *(SITE / "docs").rglob("index.html"), SITE / "downloads" / "index.html",
              SITE / "playground" / "index.html", SITE / "mesa-de-ayuda" / "index.html"]
    sitemap = []
    for path in routes:
        relative = path.relative_to(SITE).as_posix()
        route = "/" + relative.removesuffix("index.html")
        content = local_sources(path.read_text(encoding="utf-8"))
        es = localized(content, "es", route)
        if route == "/":
            content = inject_benchmarks(content, "es")
            source_link("benchmark/public")
            es = localized(content, "es", route)
            translator = TranslateLanding(mapping)
            translator.feed(content)
            english = inject_benchmarks("".join(translator.output), "en")
        elif route == "/playground/":
            english = content
            for source, translated in playground_translations:
                english = english.replace(translated, source)
            for source, translated in {"Familias": "Families", "Editor y validador": "Editor and validator", "Comparar formatos": "Compare formats", "Asistente de familias": "Family wizard", "Chuleta de la norma": "Specification cheatsheet", "Cambiar tema": "Toggle theme", "Valida documentos, convierte JSON ↔ .mini, compara tokens contra JSON, YAML, XML, CSV y el codificador oficial de TOON, y diseña tu propia familia. Todo corre en tu navegador.": "Validate documents, convert JSON ↔ .mini, compare tokens with JSON, YAML, XML, CSV and the official TOON encoder, and design your own family. Everything runs in your browser.", "motor: js/mini.js · 14 familias": "engine: js/mini.js · 14 families"}.items():
                english = english.replace(source, translated)
        else:
            english = content
        if route == "/playground/" and '<script src="/docs.js"></script>' not in es:
            es = es.replace("</body>", '<script src="/docs.js"></script></body>')
            english = english.replace("</body>", '<script src="/docs.js"></script></body>')
        en = localized(english, "en", route)
        path.write_text(es, encoding="utf-8")
        destination = SITE / "en" / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(en, encoding="utf-8")
        sitemap.extend([ORIGIN + route, ORIGIN + "/en" + route])
    (SITE / "sitemap.xml").write_text('<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">' + "".join(f"<url><loc>{html.escape(url)}</loc></url>" for url in sorted(sitemap)) + "</urlset>\n", encoding="utf-8")
    (SITE / "robots.txt").write_text(f"User-agent: *\nAllow: /\nDisallow: /source/\nSitemap: {ORIGIN}/sitemap.xml\n", encoding="utf-8")
    digest_cache: dict[str, str] = {}
    rendered = routes + list((SITE / "en").rglob("*.html")) + list((SITE / "source").rglob("*.html"))
    for page in rendered:
        original = page.read_text(encoding="utf-8")
        versioned = version_assets(original, digest_cache)
        if versioned != original:
            page.write_text(versioned, encoding="utf-8")
    print(f"  public: {len(sitemap)} localized pages, {len(COPIED)} evidence files/directories")
