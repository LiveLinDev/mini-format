"""/sima/: ninguna llamada de pago sin confirmación explícita (diálogo accesible propio).

Usa un Chromium real (Playwright) contra el sitio construido y se OMITE, diciéndolo, si Playwright/Chromium no están o si el
sitio no se ha construido (python sitio/construir.py). El servicio de SIMA es de terceros y de pago: aquí se SIMULA con
`page.route` y se registra cada petición; estas pruebas no contactan sima.pmoluna.com.
"""
from __future__ import annotations

import functools
import http.server
import json
import threading
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SITIO = ROOT / "sitio"

playwright_api = pytest.importorskip("playwright.sync_api", reason="Playwright no está instalado: se omiten las pruebas de navegador")
CONSTRUIDO = (SITIO / "sima" / "index.html").exists()
pytestmark = pytest.mark.skipif(not CONSTRUIDO, reason="el sitio no está construido (python sitio/construir.py)")


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


def simular_sima(pagina, peticiones: list):
    """Responde con datos falsos y registra cada petición (método, url)."""
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
    pagina.route("https://sima.pmoluna.com/**", manejar)


def test_sima_no_hace_ninguna_llamada_de_pago_al_cargar_y_pide_confirmacion(navegador, base_url):
    contexto = navegador.new_context(viewport={"width": 1280, "height": 900})
    pagina = contexto.new_page()
    peticiones = []
    simular_sima(pagina, peticiones)
    pagina.goto(base_url + "/sima/")
    pagina.wait_for_timeout(700)
    assert peticiones == [("GET", "https://sima.pmoluna.com/api/mini/estado/")], "al cargar solo puede haber el GET de estado"
    posts = lambda: [p for p in peticiones if p[0] == "POST"]
    dialogo = pagina.locator("#dlg-fondo")
    assert dialogo.is_hidden()
    # Procesar: abre el diálogo, dice el servidor, el modelo y que consume crédito; el foco empieza en Cancelar
    pagina.click("#vivo-procesar")
    assert dialogo.is_visible() and pagina.get_attribute("#dlg", "role") == "alertdialog" and pagina.get_attribute("#dlg", "aria-modal") == "true"
    texto = pagina.inner_text("#dlg")
    assert "consume crédito" in texto and "sima.pmoluna.com" in texto and "DeepSeek" in texto and "solo lectura" in texto
    assert pagina.evaluate("document.activeElement.id") == "dlg-cancelar"
    assert posts() == []
    # el foco no escapa del diálogo con Tab
    pagina.keyboard.press("Tab")
    assert pagina.evaluate("document.activeElement.id") == "dlg-continuar"
    pagina.keyboard.press("Tab")
    assert pagina.evaluate("document.activeElement.id") == "dlg-cancelar"
    # Esc cancela y devuelve el foco al botón; clic fuera también cancela
    pagina.keyboard.press("Escape")
    assert dialogo.is_hidden() and pagina.evaluate("document.activeElement.id") == "vivo-procesar" and posts() == []
    pagina.click("#comparar-iniciar")
    pagina.mouse.click(5, 450)
    assert dialogo.is_hidden() and posts() == []
    pagina.click("#comparar-iniciar")
    pagina.click("#dlg-cancelar")
    assert dialogo.is_hidden() and posts() == []
    # solo «Continuar» envía el POST, y exactamente uno por confirmación
    pagina.click("#comparar-iniciar")
    pagina.click("#dlg-continuar")
    pagina.wait_for_timeout(400)
    assert posts() == [("POST", "https://sima.pmoluna.com/api/mini/comparar/")]
    pagina.click("#vivo-procesar")
    pagina.click("#dlg-continuar")
    pagina.wait_for_timeout(400)
    assert posts() == [("POST", "https://sima.pmoluna.com/api/mini/comparar/"), ("POST", "https://sima.pmoluna.com/api/mini/clase/")]
    contexto.close()


def test_el_dialogo_de_sima_nombra_el_servidor_que_se_haya_elegido_y_esta_en_ingles(navegador, base_url):
    contexto = navegador.new_context(viewport={"width": 1280, "height": 900}, locale="en-US")
    pagina = contexto.new_page()
    simular_sima(pagina, [])
    pagina.goto(base_url + "/sima/?sima=http://127.0.0.1:9")
    pagina.click('[data-lang-btn="en"]')
    pagina.evaluate("document.querySelector('#vivo-procesar').disabled = false")
    pagina.click("#vivo-procesar")
    texto = pagina.inner_text("#dlg")
    assert "uses credit from a paid provider" in texto and "127.0.0.1:9" in texto and "read-only" in texto
    contexto.close()
