"""Los dos ejemplos funcionan juntos y el recorrido se puede usar en móvil y con teclado."""
from __future__ import annotations

import functools
import http.server
import threading
from pathlib import Path

import pytest

pw = pytest.importorskip("playwright.sync_api")
SITE = Path(__file__).resolve().parents[1] / "sitio"


class SilentHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass


@pytest.fixture(scope="module")
def base_url():
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), functools.partial(SilentHandler, directory=str(SITE)))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_port}"
    server.shutdown()
    server.server_close()


@pytest.fixture(scope="module")
def browser():
    with pw.sync_playwright() as p:
        browser = p.chromium.launch()
        yield browser
        browser.close()


@pytest.fixture
def page(browser):
    context = browser.new_context(viewport={"width": 1440, "height": 900}, locale="es-PE")
    page = context.new_page()
    errors = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    page.route("https://fonts.googleapis.com/**", lambda route: route.abort())
    yield page
    assert not errors, errors
    context.close()


def test_inicio_lleva_a_un_recorrido_con_las_dos_demos(page, base_url, tmp_path):
    page.emulate_media(color_scheme="dark")
    page.goto(base_url + "/")
    page.locator(".cf-preview a").click()
    pw.expect(page).to_have_url(base_url + "/ejemplo/#como-funciona")
    pw.expect(page.get_by_role("heading", level=1)).to_have_text("¿Cómo funciona .mini?", use_inner_text=True)
    heading = page.get_by_role("heading", level=1).bounding_box()
    header = page.locator(".site-header").bounding_box()
    assert heading["y"] >= header["y"] + header["height"], "el enlace deja el título visible bajo la cabecera"
    assert page.locator("#mesa-de-ayuda #ejecutar").count() == 1
    assert page.locator("#comparacion #sel-n button").count() == 5
    assert page.locator("iframe").count() == 0
    ids = page.locator("[id]").evaluate_all("es => es.map(e => e.id)")
    assert len(ids) == len(set(ids)), "las demos comparten la página sin duplicar ids"
    page.screenshot(path=str(tmp_path / "ejemplos-desktop.png"))
    page.locator("#proceso").screenshot(path=str(tmp_path / "como-funciona.png"))


def test_recorrido_se_navega_con_teclado_y_conserva_la_muestra(page, base_url):
    page.goto(base_url + "/ejemplo/")
    first = page.locator("#paso-datos")
    first.focus()
    first.press("ArrowRight")
    pw.expect(page.locator("#como-contrato")).to_be_visible()
    pw.expect(page.locator("#como-datos")).to_be_hidden()
    page.locator("#paso-contrato").press("ArrowRight")
    pw.expect(page.locator("#como-respuesta pre").first).to_contain_text("tk|n=2")
    page.locator(".ej-prompt summary").click()
    pw.expect(page.locator('#como-respuesta pre[data-lang="es"]')).to_be_visible()
    page.locator("#paso-respuesta").press("End")
    pw.expect(page.locator("#como-validacion")).to_contain_text("2 registros válidos y 0 errores")


@pytest.mark.parametrize("format,scenario,count", [
    ("mini", "ok", "10"), ("mini", "error", "10"), ("mini", "cortada", "10"),
    ("json", "ok", "10"), ("json", "error", "0"), ("json", "cortada", "0"),
])
def test_demo_valida_y_repara_sin_interferir_con_los_lotes(page, base_url, format, scenario, count):
    page.goto(base_url + "/ejemplo/#mesa-de-ayuda")
    page.locator(f'[data-formato="{format}"]').click()
    page.locator(f'[data-escenario="{scenario}"]').click()
    page.locator("#ejecutar").click()
    pw.expect(page.locator("#resultado")).to_be_visible(timeout=8000)
    pw.expect(page.locator("#cuentaTickets")).to_have_text(count)
    page.locator("#sel-n button").first.click()
    pw.expect(page.locator("#mas-mini")).to_contain_text("192 registros")
    assert page.url == base_url + "/ejemplo/#mesa-de-ayuda"


def test_idioma_actualiza_la_explicacion_y_ambas_demos(page, base_url):
    page.goto(base_url + "/ejemplo/")
    page.locator('[data-lang-btn="en"]').click()
    pw.expect(page.get_by_role("heading", level=1)).to_have_text("How does .mini work?", use_inner_text=True)
    pw.expect(page.locator("#respuesta")).to_contain_text("Create tickets with AI")
    pw.expect(page.locator("#notaModo")).to_contain_text("Recorded model answers")
    pw.expect(page.locator("#cifras")).to_contain_text("Tokens in .mini")
    page.locator('[data-lang-btn="es"]').click()
    pw.expect(page.locator("#respuesta")).to_contain_text("Crear tickets con IA")


def test_movil_y_movimiento_reducido(page, base_url, tmp_path):
    page.set_viewport_size({"width": 375, "height": 812})
    page.emulate_media(reduced_motion="reduce")
    page.goto(base_url + "/ejemplo/")
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth"), "desbordamiento en móvil"
    page.locator("#paso-respuesta").click()
    pw.expect(page.locator("#como-respuesta")).to_be_visible()
    page.locator("#ejecutar").click()
    pw.expect(page.locator("#resultado")).to_be_visible(timeout=8000)
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
    page.screenshot(path=str(tmp_path / "ejemplos-mobile.png"), full_page=True)
    page.locator('.ej-contents a[href="#proceso"]').click()
    page.screenshot(path=str(tmp_path / "proceso-mobile.png"))
    page.locator('.ej-contents a[href="#mesa-de-ayuda"]').click()
    page.screenshot(path=str(tmp_path / "mesa-mobile.png"))


def test_explicacion_disponible_sin_javascript(browser, base_url):
    context = browser.new_context(java_script_enabled=False, locale="es-PE", viewport={"width": 375, "height": 812})
    page = context.new_page()
    page.goto(base_url + "/ejemplo/")
    for panel in ("como-datos", "como-contrato", "como-respuesta", "como-validacion"):
        pw.expect(page.locator("#" + panel)).to_be_visible()
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
    context.close()
