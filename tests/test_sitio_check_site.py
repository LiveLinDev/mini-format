"""Reglas de tools/check_site.py: cada una debe FALLAR cuando se rompe (no basta con que pase en el sitio real)."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SITIO = ROOT / "sitio"
sys.path.insert(0, str(ROOT / "tools"))

import check_site  # noqa: E402

TEXTO = "Texto estático de la página que se ve sin JavaScript. " * 5
MENU = ["/docs/", "/validacion/", "/docs/spec/", "/playground/"]


def cabecera(menu=MENU, toggle=True, controla="nav-links", extra_cta=True) -> str:
    boton = (f'<button type="button" class="nav-toggle" aria-expanded="false" aria-controls="{controla}">m</button>' if toggle else "")
    cta = '<li class="nav-cta"><a class="btn" href="/docs/quickstart/">Instalar</a></li>' if extra_cta else ""
    enlaces = "".join(f'<li><a href="{h}">x</a></li>' for h in menu)
    return f'<header class="site-header">{boton}<ul class="nav-links" id="nav-links">{enlaces}{cta}</ul></header>'


def pagina(cuerpo=TEXTO, *, menu=MENU, js=True, clases="", lang_spans=False, extra="") -> str:
    flag = '<script>document.documentElement.classList.add("js")</script>' if js else ""
    return (f'<!doctype html><html lang="es"><head><meta charset="utf-8">{flag}<title>t</title></head><body>{cabecera(menu)}'
            f'<main id="contenido"><p class="{clases}">{cuerpo}</p>{extra}</main></body></html>')


def sitio_valido(tmp_path: Path) -> Path:
    s = tmp_path / "s"
    (s / "docs").mkdir(parents=True)
    (s / "downloads").mkdir()
    (s / "validacion").mkdir()
    (s / "index.html").write_text(pagina(clases="rv"), encoding="utf-8")
    for ruta in ("docs", "validacion", "docs/spec", "playground", "docs/quickstart"):
        (s / ruta).mkdir(parents=True, exist_ok=True)
        (s / ruta / "index.html").write_text(pagina(), encoding="utf-8")
    (s / "404.html").write_text(
        '<!doctype html><html lang="es"><head><meta name="robots" content="noindex"><script>document.documentElement.classList.add("js")</script>'
        f'<title>404</title></head><body>{cabecera()}<main><p><span data-lang="es">{TEXTO}</span><span data-lang="en" hidden>{TEXTO}</span></p></main></body></html>',
        encoding="utf-8")
    (s / "base.css").write_text(".rv{opacity:0}\nhtml:not(.js) .rv{opacity:1}\n", encoding="utf-8")
    (s / "downloads" / "manifest.json").write_text(json.dumps({"files": []}), encoding="utf-8")
    (s / "version.json").write_text(json.dumps({"commit": "x", "construido": "y", "mini_format": "1", "spec": "1"}), encoding="utf-8")
    (s / "sitemap.xml").write_text(
        '<?xml version="1.0"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
        + "".join(f"<url><loc>{check_site.ORIGIN}{r}</loc></url>" for r in ("/", "/docs/", "/validacion/")) + "</urlset>", encoding="utf-8")
    return s


def problemas(s: Path) -> list[str]:
    return check_site.comprobar(s)


def test_un_sitio_minimo_valido_no_da_problemas(tmp_path):
    assert problemas(sitio_valido(tmp_path)) == []


def test_el_sitio_construido_pasa_todas_las_reglas():
    if not (SITIO / "docs" / "index.html").exists():
        pytest.skip("el sitio no está construido (python sitio/construir.py)")
    assert check_site.comprobar(SITIO) == []


# --------------------------------------------------------------------------- 404 real
def test_falta_404_html(tmp_path):
    s = sitio_valido(tmp_path)
    (s / "404.html").unlink()
    assert any(p.startswith("404.html: missing") and "NGINX_404.md" in p for p in problemas(s))


def test_404_sin_noindex_o_sin_idiomas(tmp_path):
    s = sitio_valido(tmp_path)
    (s / "404.html").write_text(pagina(), encoding="utf-8")
    p = problemas(s)
    assert any("noindex" in x for x in p) and any("no es bilingüe" in x for x in p)


# --------------------------------------------------------------------------- el texto no depende de JavaScript
def test_pagina_que_solo_se_rellena_con_js(tmp_path):
    s = sitio_valido(tmp_path)
    (s / "docs" / "index.html").write_text(pagina(cuerpo="", extra='<div id="app"></div><script>document.getElementById("app").textContent="hola"</script>'),
                                           encoding="utf-8")
    assert any("docs/index.html" in x and "texto visible sin JavaScript" in x for x in problemas(s))


def test_el_texto_dentro_de_hidden_o_de_scripts_no_cuenta(tmp_path):
    s = sitio_valido(tmp_path)
    (s / "docs" / "index.html").write_text(pagina(cuerpo="", extra=f'<div hidden>{TEXTO}</div><script>var x="{TEXTO}"</script><template>{TEXTO}</template>'),
                                           encoding="utf-8")
    assert any("docs/index.html" in x and "texto visible" in x for x in problemas(s))


def test_cuerpo_en_espanol_que_nace_oculto(tmp_path):
    s = sitio_valido(tmp_path)
    (s / "docs" / "index.html").write_text(pagina(extra=f'<div data-lang-body="es" hidden>{TEXTO}</div>'), encoding="utf-8")
    assert any("docs/index.html" in x and "nace oculto" in x for x in problemas(s))


def test_contenido_rv_sin_la_marca_js(tmp_path):
    s = sitio_valido(tmp_path)
    (s / "index.html").write_text(pagina(clases="rv", js=False), encoding="utf-8")
    assert any("index.html" in x and "marca «js»" in x for x in problemas(s))


def test_base_css_sin_la_regla_no_js(tmp_path):
    s = sitio_valido(tmp_path)
    (s / "base.css").write_text(".rv{opacity:0}\n", encoding="utf-8")
    assert any("html:not(.js) .rv" in x for x in problemas(s))


# --------------------------------------------------------------------------- cabecera unificada
def test_una_pagina_con_otro_menu(tmp_path):
    s = sitio_valido(tmp_path)
    (s / "docs" / "index.html").write_text(pagina(menu=["/docs/", "/playground/"]), encoding="utf-8")
    assert any("docs/index.html: el menú difiere" in x for x in problemas(s))


def test_la_portada_sin_validacion(tmp_path):
    s = sitio_valido(tmp_path)
    sin = ["/docs/", "/docs/spec/"]
    for ruta in ("index.html", "docs/index.html", "validacion/index.html"):
        (s / ruta).write_text(pagina(menu=sin), encoding="utf-8")
    assert any("no enlaza /validacion/" in x for x in problemas(s))


def test_el_boton_de_menu_debe_controlar_una_lista_existente(tmp_path):
    s = sitio_valido(tmp_path)
    (s / "docs" / "index.html").write_text(
        pagina().replace('aria-controls="nav-links"', 'aria-controls="no-existe"'), encoding="utf-8")
    assert any("docs/index.html" in x and "aria-expanded y aria-controls" in x for x in problemas(s))
    (s / "docs" / "index.html").write_text(pagina().replace(' aria-expanded="false"', ""), encoding="utf-8")
    assert any("docs/index.html" in x and "aria-expanded y aria-controls" in x for x in problemas(s))


def test_cabecera_sin_boton_de_menu(tmp_path):
    s = sitio_valido(tmp_path)
    html = pagina().replace(cabecera(), cabecera(toggle=False))
    (s / "docs" / "index.html").write_text(html, encoding="utf-8")
    assert any("docs/index.html: la cabecera no tiene botón de menú móvil" in x for x in problemas(s))


def test_el_boton_de_instalar_del_menu_no_cuenta_como_enlace_de_menu(tmp_path):
    """La portada enlaza #instalar y las demás /docs/quickstart/: son el CTA, no el menú."""
    s = sitio_valido(tmp_path)
    html = pagina(extra='<span id="instalar"></span>').replace('href="/docs/quickstart/"', 'href="#instalar"')
    (s / "docs" / "index.html").write_text(html, encoding="utf-8")
    assert problemas(s) == []


def test_el_menu_en_ingles_se_compara_sin_el_prefijo_en(tmp_path):
    s = sitio_valido(tmp_path)
    en = ["/en/docs/", "/en/validacion/", "/en/docs/spec/", "/en/playground/"]
    for ruta in ["en", "en/docs", "en/validacion", "en/docs/spec", "en/playground"]:
        (s / ruta).mkdir(parents=True, exist_ok=True)
        (s / ruta / "index.html").write_text(pagina(menu=en), encoding="utf-8")
    (s / "en" / "docs" / "quickstart").mkdir(parents=True)   # el CTA de la copia EN apunta a la ruta sin /en/: existe arriba
    assert problemas(s) == []


# --------------------------------------------------------------------------- sitemap, versión, enlaces y descargas
def test_sitemap_con_una_pagina_inexistente_o_sin_una_pagina_en_linea(tmp_path):
    s = sitio_valido(tmp_path)
    (s / "sitemap.xml").write_text(
        '<?xml version="1.0"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
        f"<url><loc>{check_site.ORIGIN}/fantasma/</loc></url></urlset>", encoding="utf-8")
    p = problemas(s)
    assert any("/fantasma/ no existe" in x for x in p) and any("falta /validacion/" in x for x in p)


def test_recursos_locales_sin_sellar(tmp_path):
    """/taller/, /sima/ y /ejemplo/ pedían base.css y docs.js sin ?v= y se quedaban con la caché vieja."""
    s = sitio_valido(tmp_path)
    (s / "docs.js").write_text("x", encoding="utf-8")
    (s / "taller").mkdir()
    (s / "taller" / "index.html").write_text(pagina(extra='<script src="/docs.js"></script><link rel="stylesheet" href="/base.css">'), encoding="utf-8")
    p = problemas(s)
    assert any("taller/index.html: /docs.js no lleva el sellado" in x for x in p)
    assert any("taller/index.html: /base.css no lleva el sellado" in x for x in p)
    (s / "taller" / "index.html").write_text(pagina(extra='<script src="/docs.js?v=abc"></script><link rel="stylesheet" href="/base.css?v=abc">'), encoding="utf-8")
    assert not [x for x in problemas(s) if "sellado" in x]


def test_version_json_incompleto(tmp_path):
    s = sitio_valido(tmp_path)
    (s / "version.json").write_text(json.dumps({"commit": "x"}), encoding="utf-8")
    assert any("version.json: faltan claves" in x for x in problemas(s))


def test_reglas_originales_siguen_activas(tmp_path):
    s = sitio_valido(tmp_path)
    (s / "docs" / "index.html").write_text(
        pagina(extra='<a id="a">1</a><a id="a">2</a><a href="/no-existe/">roto</a><a href="/validacion/#ancla-inexistente">x</a>'), encoding="utf-8")
    (s / "downloads" / "f.bin").write_bytes(b"abc")
    (s / "downloads" / "manifest.json").write_text(json.dumps({"files": [{"name": "f.bin", "bytes": 3, "sha256": "0" * 64}]}), encoding="utf-8")
    p = problemas(s)
    assert any("duplicate id a" in x for x in p)
    assert any("missing /no-existe/" in x for x in p)
    assert any("/validacion/#ancla-inexistente" in x and "missing anchor" in x for x in p)
    assert any("invalid release checksum: f.bin" in x for x in p)


def test_main_termina_con_error_si_hay_problemas(tmp_path, monkeypatch):
    s = sitio_valido(tmp_path)
    (s / "404.html").unlink()
    monkeypatch.setattr(check_site, "SITE", s)
    with pytest.raises(SystemExit) as salida:
        check_site.main()
    assert "404.html" in str(salida.value)
