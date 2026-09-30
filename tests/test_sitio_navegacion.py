"""Cabecera, pie y menú móvil unificados; portada sin JavaScript; 404; diálogo de pago de /sima/.

La primera mitad es estática (funciones de sitio/construir.py y fuentes del sitio). La segunda usa un Chromium real
(Playwright) contra el sitio construido y se OMITE, diciéndolo, si Playwright/Chromium no están o si el sitio no se ha
construido (python sitio/construir.py).
"""
from __future__ import annotations

import functools
import http.server
import json
import re
import sys
import threading
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SITIO = ROOT / "sitio"
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(SITIO))

import construir  # noqa: E402
import modulos  # noqa: E402

# Emojis y dingbats de texto (✓ ✕ ✎ ★ ➜ ⏳ …) que el producto no usa: los iconos son SVG en línea.
PROHIBIDOS = re.compile("[←-⇿⌀-⏿☀-➿⬀-⯿\U0001F000-\U0001FAFF]")
A = modulos.ANCLA


def region_de(html: str, nombre: str) -> str:
    m = re.search(rf"<!-- {A} {nombre} {A} -->\n(.*?)\n<!-- {A} /{nombre} {A} -->", html, re.S)
    assert m, f"faltan las anclas {nombre}"
    return m.group(1)


# --------------------------------------------------------------------------- menú y pie: un solo contrato
def test_el_menu_tiene_validacion_junto_a_documentacion():
    rutas = [r for r, _, _ in construir.NAV]
    assert rutas[:2] == ["docs", "validacion"]
    assert len(rutas) == 10 and {"taller", "ejemplo", "sima", "docs/spec", "docs/errors", "docs/forks", "playground", "mesa-de-ayuda"} <= set(rutas)
    es, en = {r: e for r, e, _ in construir.NAV}, {r: e for r, _, e in construir.NAV}
    assert (es["validacion"], en["validacion"]) == ("Validación", "Validation")


@pytest.mark.parametrize("activo, esperado", [
    ("docs", "docs"), ("docs/spec", "docs/spec"), ("docs/spec/cambios", "docs/spec"), ("docs/errors/E06", "docs/errors"),
    ("docs/forks/a", "docs/forks"), ("docs/quickstart", "docs"), ("validacion", "validacion"), ("playground", "playground"),
    ("mesa-de-ayuda", "mesa-de-ayuda"), ("taller", "taller"), ("docsx", ""), ("", ""), ("economia", ""),
])
def test_ruta_activa_es_la_mas_especifica_por_segmentos(activo, esperado):
    assert construir.ruta_activa(activo) == esperado
    cabecera = construir.encabezado(activo)
    assert cabecera.count('aria-current="page"') == (1 if esperado else 0)
    if esperado:
        assert f'<a href="/{esperado}/" aria-current="page">' in cabecera


def test_la_cabecera_tiene_boton_de_menu_accesible_y_lista_controlada():
    h = construir.encabezado("docs")
    boton = re.search(r'<button type="button" class="nav-toggle"[^>]*>', h).group(0)
    assert 'aria-expanded="false"' in boton and 'aria-controls="nav-links"' in boton
    assert '<ul class="nav-links" id="nav-links">' in h
    assert h.index("nav-toggle") < h.index('id="nav-links"'), "el botón va antes de la lista: el foco baja del botón a los enlaces"
    assert '<svg class="ico-abrir"' in h and 'aria-hidden="true"' in h
    assert 'class="sr"' in h and "Menú" in h and "Menu" in h, "nombre accesible bilingüe"


def test_portada_y_resto_de_paginas_comparten_menu_y_solo_difieren_en_lo_previsto():
    portada, otra = construir.cabecera("", portada=True), construir.cabecera("docs")
    assert portada.startswith('<a class="skip" href="#main">') and otra.startswith('<a class="skip" href="#contenido">')
    assert 'class="search"' in portada and 'class="search"' not in otra
    assert 'href="#instalar"' in portada and 'href="/docs/quickstart/"' in otra
    sacar = lambda h: re.findall(r'<li><a href="(/[^"]+)"', h)
    assert sacar(portada) == sacar(otra) == [f"/{r}/" for r, _, _ in construir.NAV]


def test_el_pie_enlaza_validacion_economia_y_las_paginas_de_integracion():
    pie = construir.pie()
    for destino in ("/validacion/", "/economia/", "/taller/", "/ejemplo/", "/sima/", "/mesa-de-ayuda/", "/docs/metodologia/"):
        assert f'href="{destino}"' in pie, destino
    assert "mini-format " + construir.__version__ in pie and "SPEC " + construir.SPEC_VERSION in pie
    assert 'data-lang="en"' in pie


def normalizar(html: str) -> str:
    """publicar.py reescribe la evidencia (GitHub -> /source/...) y sella los recursos (?v=) después de sincronizar: se igualan para comparar."""
    html = re.sub(r'href="(?:https://github\.com/LiveLinDev/mini-format/[^"]*|/source/[^"]*)"', 'href="EVIDENCIA"', html)
    return re.sub(r"\?v=[0-9a-f]{16}", "", html)   # y el sellado de recursos


def test_la_portada_y_la_404_no_se_desincronizan_de_cabecera_y_pie():
    portada = (SITIO / "index.html").read_text(encoding="utf-8")
    assert region_de(portada, "CABECERA") == construir.encabezado("", portada=True)
    assert normalizar(region_de(portada, "PIE")) == normalizar(construir.pie())
    e404 = (SITIO / "404.html").read_text(encoding="utf-8")
    assert normalizar(region_de(e404, "CABEZA")) == construir.cabeza()
    assert region_de(e404, "CABECERA") == construir.cabecera("")
    assert normalizar(region_de(e404, "PIE")) == normalizar(construir.pie())


def test_sincronizar_es_idempotente_sobre_las_fuentes(tmp_path, monkeypatch):
    for nombre in ("index.html", "404.html"):
        (tmp_path / nombre).write_text((SITIO / nombre).read_text(encoding="utf-8"), encoding="utf-8")
    monkeypatch.setattr(construir, "SITIO", tmp_path)
    construir.sincronizar_portada(), construir.sincronizar_404()      # la primera vez puede reescribir los enlaces de evidencia
    assert construir.sincronizar_portada() is False and construir.sincronizar_404() is False, "sincronizar dos veces no cambia nada"
    # y si alguien las desincroniza a mano, el build las repara
    texto = (tmp_path / "index.html").read_text(encoding="utf-8").replace(">Validación</span>", ">VALIDACION</span>", 1)
    (tmp_path / "index.html").write_text(texto, encoding="utf-8")
    assert construir.sincronizar_portada() is True and ">VALIDACION<" not in (tmp_path / "index.html").read_text(encoding="utf-8")


def test_la_portada_enlaza_las_paginas_que_antes_no_enlazaba():
    portada = (SITIO / "index.html").read_text(encoding="utf-8")
    for destino in ("/validacion/", "/taller/", "/sima/", "/ejemplo/", "/docs/"):
        assert f'href="{destino}"' in region_de(portada, "CABECERA"), destino
        assert f'href="{destino}"' in region_de(portada, "PIE") or destino == "/docs/", destino
    assert '<script>document.documentElement.classList.add("js")</script>' in portada.split("</head>")[0]


def test_ningun_icono_de_la_interfaz_nueva_es_un_emoji_o_un_dingbat():
    piezas = {
        "cabecera": construir.cabecera("docs") + construir.encabezado("", portada=True), "pie": construir.pie(),
        "404": (SITIO / "404.html").read_text(encoding="utf-8"), "docs.js": (SITIO / "docs.js").read_text(encoding="utf-8"),
        "base.css": (SITIO / "base.css").read_text(encoding="utf-8"),
        "validacion.py": (SITIO / "validacion.py").read_text(encoding="utf-8"), "economia.py": (SITIO / "economia.py").read_text(encoding="utf-8"),
    }
    sima = (ROOT / "examples" / "sima" / "plantilla.html").read_text(encoding="utf-8")
    piezas["sima: diálogo"] = sima[sima.index('<div class="sm-dlg-fondo"'): sima.index("<script>__MINI_JS__")]
    for nombre, texto in piezas.items():
        assert not PROHIBIDOS.search(texto), f"{nombre} contiene un emoji o dingbat: {PROHIBIDOS.findall(texto)[:5]}"


def test_css_nuevo_sin_colores_sueltos():
    """Los estilos añadidos usan los tokens (rgb(var(--x))): ni hex ni rgb() literales en el menú, el diálogo y las páginas de aviso."""
    base = (SITIO / "base.css").read_text(encoding="utf-8")
    menu = base[base.index("/* menú móvil"): base.index(".btn{")]
    docs = (SITIO / "docs.css").read_text(encoding="utf-8")
    aviso = docs[docs.index("/* páginas de aviso"):]
    sima = (ROOT / "examples" / "sima" / "plantilla.html").read_text(encoding="utf-8")
    dialogo = sima[sima.index("/* confirmación antes de gastar"): sima.index("  @media (max-width: 640px) {\n    .sm-barra {")]
    for nombre, css in {"menú móvil": menu, "páginas de aviso": aviso, "diálogo de pago": dialogo}.items():
        assert not re.search(r"#[0-9a-fA-F]{3,8}\b", css), nombre
        assert not re.search(r"rgb\(\s*\d", css), nombre


def test_sin_js_la_marca_js_es_lo_unico_que_cambia_el_contenido_de_rv():
    base = (SITIO / "base.css").read_text(encoding="utf-8")
    assert "html:not(.js) .rv{ opacity:1; transform:none }" in base
    heads = [construir.cabeza(), construir.JS_FLAG]
    assert all('classList.add("js")' in h for h in heads)


# --------------------------------------------------------------------------- navegador real
playwright_api = pytest.importorskip("playwright.sync_api", reason="Playwright no está instalado: se omiten las pruebas de navegador")
CONSTRUIDO = (SITIO / "docs" / "index.html").exists() and (SITIO / "validacion" / "index.html").exists() and (SITIO / "404.html").exists()


class _Silencioso(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass


@pytest.fixture(scope="module")
def base_url():
    servidor = http.server.ThreadingHTTPServer(("127.0.0.1", 0), functools.partial(_Silencioso, directory=str(SITIO)))
    hilo = threading.Thread(target=servidor.serve_forever, daemon=True)
    hilo.start()
    yield f"http://127.0.0.1:{servidor.server_address[1]}"
    servidor.shutdown()
    servidor.server_close()


@pytest.fixture(scope="module")
def navegador():
    with playwright_api.sync_playwright() as p:
        try:
            chromium = p.chromium.launch()
        except Exception as error:  # noqa: BLE001
            pytest.skip(f"no hay Chromium de Playwright: {str(error).splitlines()[0]}")
        yield chromium
        chromium.close()


SIMA_API = "https://sima.pmoluna.com/**"


def simular_sima(pagina, peticiones: list):
    """SIMA es un servicio de terceros de pago: en las pruebas se responde con datos falsos y se registra cada petición."""
    def manejar(route):
        r = route.request
        peticiones.append((r.method, r.url))
        cab = {"access-control-allow-origin": "*", "access-control-allow-headers": "*", "access-control-allow-methods": "*"}
        if r.method == "OPTIONS":
            return route.fulfill(status=204, headers=cab)
        if r.url.endswith("/api/mini/estado/"):
            return route.fulfill(status=200, headers=cab, content_type="application/json",
                                 body=json.dumps({"proveedor": "DeepSeek", "modelo": "deepseek-chat", "lector": "minifmt"}))
        return route.fulfill(status=500, headers=cab, content_type="application/json", body=json.dumps({"error": "simulado"}))
    pagina.route(SIMA_API, manejar)


ANCHOS = [360, 375, 768, 1024, 1280, 1440]
PAGINAS = ["/", "/en/", "/docs/", "/docs/metodologia/", "/mesa-de-ayuda/", "/taller/", "/sima/", "/ejemplo/", "/playground/",
           "/validacion/", "/economia/", "/404.html", "/downloads/"]
JS_DESBORDE = """() => { const de = document.documentElement; return {sw: de.scrollWidth, cw: de.clientWidth}; }"""


@pytest.mark.skipif(not CONSTRUIDO, reason="el sitio no está construido")
@pytest.mark.parametrize("ancho", ANCHOS)
def test_sin_desplazamiento_horizontal_ni_errores_de_consola(navegador, base_url, ancho):
    problemas = []
    contexto = navegador.new_context(viewport={"width": ancho, "height": 800})
    for ruta in PAGINAS:
        pagina = contexto.new_page()
        errores = []
        pagina.on("console", lambda m, e=errores: e.append(m.text) if m.type == "error" else None)
        pagina.on("pageerror", lambda x, e=errores: e.append(str(x)))
        simular_sima(pagina, [])
        pagina.goto(base_url + ruta, wait_until="load")
        pagina.wait_for_timeout(250)
        medida = pagina.evaluate(JS_DESBORDE)
        if medida["sw"] > medida["cw"]:
            problemas.append(f"{ruta} a {ancho}px: scrollWidth {medida['sw']} > {medida['cw']}")
        if errores:
            problemas.append(f"{ruta} a {ancho}px: errores de consola {errores[:2]}")
        pagina.close()
    contexto.close()
    assert problemas == []


@pytest.mark.skipif(not CONSTRUIDO, reason="el sitio no está construido")
@pytest.mark.parametrize("ruta", ["/", "/taller/", "/docs/"])
def test_menu_movil_abre_cierra_con_esc_al_elegir_y_al_hacer_clic_fuera(navegador, base_url, ruta):
    contexto = navegador.new_context(viewport={"width": 375, "height": 1000})
    pagina = contexto.new_page()
    simular_sima(pagina, [])
    pagina.goto(base_url + ruta)
    boton = pagina.locator(".nav-toggle")
    lista = pagina.locator("#nav-links")
    assert boton.is_visible() and not lista.is_visible(), "cerrado al cargar"
    assert boton.get_attribute("aria-expanded") == "false" and boton.get_attribute("aria-controls") == "nav-links"
    assert boton.evaluate("e => e.getBoundingClientRect().width") >= 40 and boton.evaluate("e => e.getBoundingClientRect().height") >= 40
    # abrir
    boton.click()
    assert boton.get_attribute("aria-expanded") == "true" and lista.is_visible()
    enlaces = pagina.locator("#nav-links a:visible")
    assert [a for a in enlaces.evaluate_all("els => els.map(e => e.getAttribute('href'))")][:2] == ["/docs/", "/validacion/"]
    assert enlaces.count() >= 10
    # Esc cierra y devuelve el foco al botón
    pagina.locator("#nav-links a").first.focus()
    pagina.keyboard.press("Escape")
    assert boton.get_attribute("aria-expanded") == "false" and not lista.is_visible()
    assert pagina.evaluate("document.activeElement.className") == "nav-toggle"
    # elegir un enlace cierra el menú (se frena la navegación para observar el estado)
    pagina.evaluate("document.addEventListener('click', e => { if (e.target.closest('#nav-links a')) e.preventDefault(); })")
    boton.click()
    pagina.locator("#nav-links a", has_text="Playground").first.click()
    assert boton.get_attribute("aria-expanded") == "false" and not lista.is_visible()
    # clic fuera cierra
    boton.click()
    assert lista.is_visible()
    pagina.mouse.click(5, 980)
    assert not lista.is_visible() and boton.get_attribute("aria-expanded") == "false"
    # el foco visible del botón se dibuja con el anillo del sistema
    pagina.keyboard.press("Tab")                     # el foco por teclado dibuja el anillo de :focus-visible
    boton.focus()
    assert pagina.evaluate("getComputedStyle(document.querySelector('.nav-toggle')).boxShadow") != "none"
    # al ensanchar la ventana se cierra y la lista vuelve a ser la barra de escritorio
    boton.click()
    pagina.set_viewport_size({"width": 1440, "height": 700})
    pagina.wait_for_function("document.querySelector('.nav-toggle').getAttribute('aria-expanded') === 'false'")   # el aviso de matchMedia es asíncrono
    assert not boton.is_visible() and lista.is_visible() and boton.get_attribute("aria-expanded") == "false"
    contexto.close()


@pytest.mark.skipif(not CONSTRUIDO, reason="el sitio no está construido")
@pytest.mark.parametrize("ancho", [1340, 1366, 1440, 1600, 1920])
def test_en_escritorio_los_diez_enlaces_caben_en_una_linea_sin_boton(navegador, base_url, ancho):
    contexto = navegador.new_context(viewport={"width": ancho, "height": 700})
    for ruta in ("/", "/taller/", "/validacion/"):
        pagina = contexto.new_page()
        simular_sima(pagina, [])
        pagina.goto(base_url + ruta)
        assert not pagina.locator(".nav-toggle").is_visible(), (ruta, ancho)
        enlaces = pagina.locator("#nav-links > li:not(.nav-cta) a")
        assert enlaces.count() == 10
        alturas = enlaces.evaluate_all("els => els.map(e => Math.round(e.getBoundingClientRect().height))")
        assert max(alturas) < 40, f"{ruta} a {ancho}px: algún enlace se parte en dos líneas"
        assert pagina.evaluate("document.documentElement.scrollWidth <= document.documentElement.clientWidth")
        assert not pagina.locator(".nav-links .nav-cta").is_visible(), "el CTA duplicado solo existe en el menú móvil estrecho"
        pagina.close()
    contexto.close()


@pytest.mark.skipif(not CONSTRUIDO, reason="el sitio no está construido")
def test_selector_de_idioma_buscador_y_descargar_siguen_funcionando(navegador, base_url):
    contexto = navegador.new_context(viewport={"width": 1440, "height": 800}, locale="es-PE")
    pagina = contexto.new_page()
    simular_sima(pagina, [])
    pagina.goto(base_url + "/taller/")
    assert pagina.locator('#nav-links li:first-child a span:visible').inner_text() == "Documentación"
    pagina.click('[data-lang-btn="en"]')
    assert pagina.evaluate("document.documentElement.lang") == "en"
    assert pagina.locator('#nav-links li:nth-child(2) a span:visible').inner_text() == "Validation"
    assert pagina.locator(".nav > .btn span:visible").inner_text() == "Install"
    # portada: EN navega a la copia /en/, y «Descargar» lleva al bloque de instalación
    pagina.evaluate("localStorage.clear()")
    pagina.goto(base_url + "/")
    assert pagina.locator(".nav > .btn").get_attribute("href") == "#instalar" and pagina.locator("#instalar").count() == 1
    pagina.click('[data-lang-btn="en"]')
    pagina.wait_for_url("**/en/")
    assert pagina.locator(".nav > .btn span:visible").inner_text() == "Download"
    assert pagina.locator("#nav-links li:nth-child(2) a").get_attribute("href") == "/validacion/", "las páginas en línea no tienen copia /en/"
    # buscador: solo hay sitio en pantallas muy anchas; apunta a la documentación
    pagina.set_viewport_size({"width": 1920, "height": 800})
    assert pagina.locator("a.search").is_visible() and pagina.locator("a.search").get_attribute("href") == "/en/docs/"
    contexto.close()


@pytest.mark.skipif(not CONSTRUIDO, reason="el sitio no está construido")
def test_quien_entra_por_en_conserva_el_ingles_en_las_paginas_en_linea(navegador, base_url):
    contexto = navegador.new_context(viewport={"width": 1440, "height": 800}, locale="es-PE")
    pagina = contexto.new_page()
    simular_sima(pagina, [])
    pagina.goto(base_url + "/en/")
    pagina.goto(base_url + "/validacion/")
    assert pagina.evaluate("document.documentElement.lang") == "en"
    contexto.close()
    otro = navegador.new_context(viewport={"width": 1440, "height": 800}, locale="es-PE")
    p2 = otro.new_page()
    p2.goto(base_url + "/validacion/")
    assert p2.evaluate("document.documentElement.lang") == "es", "sin pasar por /en/, manda el idioma del navegador"
    otro.close()


# --------------------------------------------------------------------------- sin JavaScript
JS_OCULTOS = """() => {
  // Texto propio de un elemento que, sin JavaScript, no se ve. Se ignoran los gemelos del idioma que no se muestra
  // (el HTML estático ya los trae con `hidden`) y lo que nunca es contenido (scripts, estilos, .sr).
  // También se ignoran los mandos que solo existen con JavaScript (pestañas, «animar», vídeo y terminal animados, CTA duplicado
  // del menú móvil, buscador): son controles o decoración animada, no texto que el visitante deba leer.
  const ignorar = 'script,style,template,noscript,option,title,head,.sr,[data-lang][hidden],[data-lang-body][hidden],' +
    '[role="tablist"],.replay,.cmd-row .seg,#cmp-toggle,.term,.term-foot,.demo-video,.nav-cta,.search,.nav > .btn';
  const res = [];
  document.querySelectorAll('body *').forEach(e => {
    if (e.closest(ignorar)) return;
    const propio = Array.from(e.childNodes).some(n => n.nodeType === 3 && n.textContent.trim().length > 1);
    if (!propio) return;
    for (let x = e; x && x !== document.body; x = x.parentElement) {
      const s = getComputedStyle(x);
      if (s.display === 'none' || s.visibility === 'hidden' || parseFloat(s.opacity) === 0) {
        res.push(e.tagName + '.' + (e.className || '') + ' ' + e.textContent.trim().slice(0, 50));
        break;
      }
    }
  });
  return res;
}"""


@pytest.mark.skipif(not CONSTRUIDO, reason="el sitio no está construido")
@pytest.mark.parametrize("ancho", [375, 1440])
@pytest.mark.parametrize("ruta", ["/", "/en/"])
def test_la_portada_con_javascript_desactivado_muestra_todo_el_texto(navegador, base_url, ancho, ruta):
    contexto = navegador.new_context(viewport={"width": ancho, "height": 900}, java_script_enabled=False)
    pagina = contexto.new_page()
    pagina.goto(base_url + ruta)
    assert pagina.evaluate("document.documentElement.classList.contains('js')") is False
    assert pagina.evaluate(JS_OCULTOS) == [], "texto oculto sin JavaScript"
    # cada elemento de aparición (.rv) es opaco y las barras tienen ancho
    assert pagina.evaluate("Array.from(document.querySelectorAll('.rv')).every(e => getComputedStyle(e).opacity === '1')")
    assert pagina.evaluate("Array.from(document.querySelectorAll('.bar .fill')).every(e => e.getBoundingClientRect().width > 0)")
    # los cuatro paneles del benchmark y las pestañas de código se ven apilados
    assert pagina.evaluate("Array.from(document.querySelectorAll('[role=tabpanel]')).every(e => e.getClientRects().length > 0)")
    # y hay navegación: a 375 px los enlaces salen en línea (no hay botón que dependa de JS)
    assert not pagina.locator(".nav-toggle").is_visible()
    assert pagina.locator("#nav-links a:visible").count() >= 10
    if ancho == 375:
        assert pagina.evaluate("document.documentElement.scrollWidth <= document.documentElement.clientWidth")
    contexto.close()


@pytest.mark.skipif(not CONSTRUIDO, reason="el sitio no está construido")
@pytest.mark.parametrize("ruta", ["/validacion/", "/economia/", "/docs/", "/404.html", "/sima/"])
def test_las_demas_paginas_se_leen_y_navegan_sin_javascript(navegador, base_url, ruta):
    contexto = navegador.new_context(viewport={"width": 375, "height": 800}, java_script_enabled=False)
    pagina = contexto.new_page()
    pagina.goto(base_url + ruta)
    assert len(pagina.inner_text("main").strip()) > 100
    assert pagina.locator("#nav-links a:visible").count() >= 10
    assert pagina.evaluate("document.documentElement.scrollWidth <= document.documentElement.clientWidth")
    contexto.close()
