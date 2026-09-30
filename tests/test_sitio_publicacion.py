"""tools/verificar_publicacion.py contra servidores HTTP locales, y el SEO de las páginas bilingües en línea (publicar.py)."""
from __future__ import annotations

import io
import json
import sys
import threading
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "sitio"))

import verificar_publicacion as vp  # noqa: E402

SHA = "48cf38c1b23f6fc69dcd2f2b4d7409dc07ed1be2"
PORTADA = b"<html><title>portada</title><body>mini-format portada</body></html>"


@contextmanager
def servidor(rutas: dict, desconocida=(404, b"no encontrado")):
    """Servidor local: `rutas` = {ruta: (estado, cuerpo[, cabeceras])}; lo demás responde `desconocida`."""
    class H(BaseHTTPRequestHandler):
        def do_GET(self):
            estado, cuerpo, *resto = rutas.get(self.path, desconocida)
            self.send_response(estado)
            for k, v in (resto[0] if resto else {}).items():
                self.send_header(k, v)
            self.send_header("Content-Length", str(len(cuerpo)))
            self.end_headers()
            self.wfile.write(cuerpo)

        def log_message(self, *args):
            pass

    srv = ThreadingHTTPServer(("127.0.0.1", 0), H)
    hilo = threading.Thread(target=srv.serve_forever, daemon=True)
    hilo.start()
    try:
        yield f"http://127.0.0.1:{srv.server_address[1]}"
    finally:
        srv.shutdown()
        srv.server_close()


def sitio_sano(commit=SHA) -> dict:
    rutas = {r: (200, b"<html>" + r.encode() + b"</html>") for r in vp.RUTAS_CLAVE}
    rutas["/"] = (200, PORTADA)
    rutas["/404.html"] = (200, b"<html>error</html>")
    rutas["/version.json"] = (200, json.dumps({"commit": commit, "construido": "2026-09-30T00:00:00+00:00", "mini_format": "1.2.1", "spec": "1.1"}).encode())
    return rutas


def test_sitio_actualizado_y_con_404_real_sale_limpio():
    with servidor(sitio_sano()) as base:
        informe = vp.verificar(base, esperado=SHA[:7], timeout=5)
    assert informe["ok"] and informe["errores"] == [] and informe["advertencias"] == []
    assert informe["actualizacion"] == "actualizado"
    assert informe["respuesta_ruta_inventada"] == "404 real" and informe["ruta_inventada"]["estado"] == 404


def test_soft_404_con_la_portada_es_una_advertencia_y_no_una_aprobacion_silenciosa():
    with servidor(sitio_sano(), desconocida=(200, PORTADA)) as base:
        informe = vp.verificar(base, esperado=SHA, timeout=5)
        estricto = vp.verificar(base, esperado=SHA, timeout=5, estricto=True)
    assert informe["ok"], "un soft-404 no debe impedir un despliegue que sí llegó"
    assert informe["respuesta_ruta_inventada"] == "soft-404 (200 con la portada)"
    assert any("soft-404" in a and "NGINX_404.md" in a for a in informe["advertencias"])
    assert not estricto["ok"] and any("(--estricto)" in e and "soft-404" in e for e in estricto["errores"])


def test_soft_404_con_otra_pagina_tambien_se_detecta():
    with servidor(sitio_sano(), desconocida=(200, b"<html>otra cosa</html>")) as base:
        informe = vp.verificar(base, timeout=5)
    assert informe["respuesta_ruta_inventada"] == "soft-404 (200 con otra página)" and informe["advertencias"]


def test_version_distinta_nunca_se_presenta_como_sitio_actualizado():
    with servidor(sitio_sano(commit="1" * 40)) as base:
        informe = vp.verificar(base, esperado=SHA, timeout=5)
        salida = io.StringIO()
        vp.imprimir(informe, salida)
    assert not informe["ok"] and informe["actualizacion"] == "NO ACTUALIZADO"
    assert any("SITIO NO ACTUALIZADO" in e and "1" * 40 in e and SHA in e for e in informe["errores"])
    texto = salida.getvalue()
    assert "actualización: NO ACTUALIZADO" in texto and "RESULTADO: FALLÓ" in texto and "actualización: actualizado" not in texto


def test_el_sello_local_no_coincide_con_ningun_commit():
    with servidor(sitio_sano(commit="local")) as base:
        informe = vp.verificar(base, esperado=SHA, timeout=5)
    assert not informe["ok"] and informe["actualizacion"] == "NO ACTUALIZADO"


def test_sin_esperado_no_afirma_que_este_actualizado():
    with servidor(sitio_sano()) as base:
        informe = vp.verificar(base, timeout=5)
    assert informe["ok"] and "no verificado" in informe["actualizacion"] and "actualizado" != informe["actualizacion"]


def test_una_ruta_clave_que_no_responde_200_es_un_error():
    rutas = sitio_sano()
    rutas["/validacion/"] = (500, b"boom")
    rutas["/economia/"] = (301, b"", {"Location": "/"})   # las redirecciones no se siguen: no es un 200
    with servidor(rutas) as base:
        informe = vp.verificar(base, esperado=SHA, timeout=5)
    assert not informe["ok"]
    assert any(e.startswith("/validacion/ responde 500") for e in informe["errores"])
    assert any(e.startswith("/economia/ responde 301") for e in informe["errores"])


def test_version_json_ausente_o_invalido_es_un_error():
    for version in [(404, b"x"), (200, b"no es json"), (200, b'{"sin": "commit"}'), (200, b"[1, 2]")]:
        rutas = sitio_sano()
        rutas["/version.json"] = version
        with servidor(rutas) as base:
            informe = vp.verificar(base, esperado=SHA, timeout=5)
        assert not informe["ok"] and informe["actualizacion"] == "no verificable", version


def test_404_html_ausente_es_advertencia_no_error():
    rutas = sitio_sano()
    rutas["/404.html"] = (404, b"")
    with servidor(rutas) as base:
        informe = vp.verificar(base, esperado=SHA, timeout=5)
    assert informe["ok"] and any("/404.html" in a for a in informe["advertencias"])


def test_sitio_inalcanzable_falla_sin_excepcion():
    with servidor({}) as base:
        pass   # el servidor ya está cerrado: el puerto rechaza la conexión
    informe = vp.verificar(base, esperado=SHA, timeout=2, rutas=("/",))
    assert not informe["ok"] and informe["actualizacion"] == "no verificable" and informe["errores"]


@pytest.mark.parametrize("publicado, esperado, coincide", [
    (SHA, SHA, True), (SHA, SHA[:7], True), (SHA[:12], SHA, True), (SHA.upper(), SHA[:10], True),
    (SHA, "abcdef1", False), ("local", SHA, False), (SHA, "local", False), (SHA, SHA[:6], False), ("", SHA, False), (SHA, "g" * 40, False),
])
def test_comparacion_de_commits(publicado, esperado, coincide):
    assert vp._coincide(publicado, esperado) is coincide


def test_cli_devuelve_codigos_de_salida_y_json(capsys):
    with servidor(sitio_sano()) as base:
        assert vp.main(["--base", base, "--esperado", SHA, "--timeout", "5", "--json"]) == 0
        datos = json.loads(capsys.readouterr().out)
        assert datos["ok"] and datos["actualizacion"] == "actualizado"
        assert vp.main(["--base", base, "--esperado", "1234567", "--timeout", "5"]) == 1
        assert "SITIO NO ACTUALIZADO" in capsys.readouterr().out


# --------------------------------------------------------------------------- publicar.py: páginas bilingües en línea
def test_seo_en_linea_no_promete_copia_en_ingles_ni_hreflang():
    import publicar
    pagina = ('<!doctype html><html lang="es" data-title-es="T" data-title-en="T"><head><title>Taller — mini-format</title>'
              '<meta name="description" content="Mi descripción propia"></head><body>x</body></html>')
    salida = publicar.seo_en_linea(pagina, "/taller/")
    assert '<link rel="canonical" href="https://mini-format.pmoluna.com/taller/">' in salida
    assert "hreflang" not in salida and "/en/taller/" not in salida
    assert 'content="Mi descripción propia"' in salida and salida.count('name="description"') == 1
    assert 'property="og:url" content="https://mini-format.pmoluna.com/taller/"' in salida
    assert "data-localized-routes" not in salida, "docs.js redirigiría a /en/taller/, que no existe"
    assert publicar.seo_en_linea(salida, "/taller/") == salida, "idempotente: dos builds seguidos dan la misma página"


def test_las_rutas_en_linea_incluyen_las_paginas_nuevas_y_se_pueden_registrar():
    import publicar
    assert {"taller", "sima", "ejemplo", "validacion", "economia"} <= publicar.RUTAS_EN_LINEA
    publicar.registrar_en_linea("/otra-cosa/")
    try:
        assert "otra-cosa" in publicar.RUTAS_EN_LINEA
    finally:
        publicar.RUTAS_EN_LINEA.discard("otra-cosa")


def test_el_enlace_al_zip_de_fuentes_sale_de_la_version_del_paquete():
    import minifmt
    import publicar
    assert publicar.SOURCE_ZIP == f"/downloads/mini-format-{minifmt.__version__}-source.zip"
