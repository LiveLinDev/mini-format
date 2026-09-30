"""Tarifas: consulta con HTTP simulado (nunca red real), verificación sin red y siembra.

Las páginas de ``tests/fixtures/tarifas`` son recortes de las páginas oficiales consultadas el
2026-09-30 (mismas filas y misma estructura HTML, sin el resto de la página).
"""
from __future__ import annotations

import copy
import http.server
import json
import shutil
import sys
import tempfile
import threading
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

import tarifas as T  # noqa: E402

FIX = ROOT / "tests" / "fixtures" / "tarifas"
REAL = ROOT / "evidencia" / "tarifas"
AHORA = "2026-10-01T10:00:00Z"

URL_A_FIXTURE = {
    "https://developers.openai.com/api/docs/pricing.md": "openai_pricing.md",
    "https://platform.claude.com/docs/en/about-claude/pricing.md": "anthropic_pricing.md",
    "https://ai.google.dev/gemini-api/docs/pricing.md.txt": "gemini_pricing.md",
    "https://api-docs.deepseek.com/quick_start/pricing": "deepseek_pricing.html",
    "https://api-docs.deepseek.com/updates": "deepseek_updates.html",
    "https://console.groq.com/docs/models": "groq_models.html",
    "https://console.groq.com/docs/deprecations": "groq_deprecations.html",
    "https://console.groq.com/docs/model/openai/gpt-oss-120b": "groq_modelo_gpt-oss-120b.html",
    "https://console.groq.com/docs/model/openai/gpt-oss-20b": "groq_modelo_gpt-oss-20b.html",
}


class Web:
    """Descargador simulado: sirve los fixtures, cuenta las descargas y permite alterar respuestas."""

    def __init__(self, cambios=None, respuestas=None):
        self.cambios = cambios or {}         # url -> función(texto) -> texto
        self.respuestas = respuestas or {}   # url -> Respuesta ya hecha (error, 403, redirección...)
        self.descargas = []

    def __call__(self, url):
        self.descargas.append(url)
        if url in self.respuestas:
            return self.respuestas[url]
        texto = (FIX / URL_A_FIXTURE[url]).read_text(encoding="utf-8")
        if url in self.cambios:
            texto = self.cambios[url](texto)
        return T.Respuesta(200, url, texto.encode("utf-8"), None)


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="tarifas_"))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        for n in ("tarifas.json", "fuentes.json"):
            shutil.copy(REAL / n, self.tmp / n)
        shutil.copytree(REAL / "consultas", self.tmp / "consultas")

    def tarifas(self):
        return {(t["proveedor"], t["modelo_api_id"]): t for t in json.loads((self.tmp / "tarifas.json").read_text(encoding="utf-8"))["tarifas"]}


class ConsultaSimulada(Base):
    def test_paginas_intactas_verifican_las_27_y_los_3_retirados_siguen_sin_verificar(self):
        antes = self.tarifas()
        web = Web()
        doc = T.consultar(self.tmp, descargar=web, ahora=AHORA)
        self.assertEqual(doc["resumen"], {"entradas": 30, "verificadas": 27, "no_verificadas": 3, "con_cambio_de_precio": 0})
        despues = self.tarifas()
        for clave, t in despues.items():
            for c in T.CAMPOS_PRECIO:
                self.assertEqual(t[c], antes[clave][c], (clave, c))   # mismos precios: no se reescribe nada
            self.assertEqual(t["estado"], antes[clave]["estado"], clave)
            self.assertEqual(t["fecha_consulta_utc"], AHORA)
        for modelo in ("deepseek-chat", "llama-3.3-70b-versatile", "llama-3.1-8b-instant"):
            t = next(v for (p, m), v in despues.items() if m == modelo)
            self.assertEqual(t["estado"], "no_verificada")
            self.assertTrue(t["motivo_no_verificada"].startswith("retirado_segun_pagina_oficial"))
            self.assertIsNone(t["salida_por_millon"])
        # una sola descarga por URL aunque haya 11 entradas de OpenAI
        self.assertEqual(len(web.descargas), len(set(web.descargas)))
        self.assertEqual(set(web.descargas), set(URL_A_FIXTURE))
        # la consulta queda registrada con hash de página y extracto
        archivo = self.tmp / "consultas" / "20261001T100000Z.json"
        self.assertTrue(archivo.exists())
        reg = json.loads(archivo.read_text(encoding="utf-8"))
        e = next(x for x in reg["entradas"] if x["modelo_api_id"] == "gpt-5.4-mini")
        self.assertEqual(e["paginas"][0]["http_status"], 200)
        self.assertEqual(len(e["paginas"][0]["sha256"]), 64)
        self.assertEqual(e["extracto"], "| gpt-5.4-mini | $0.75 | $0.075 | - | $4.50 | - | - | - | - |")

    def test_un_precio_que_cambia_se_registra_como_cambio(self):
        web = Web(cambios={"https://developers.openai.com/api/docs/pricing.md":
                           lambda s: s.replace("| gpt-5.4-mini | $0.75 | $0.075 | - | $4.50 |", "| gpt-5.4-mini | $0.75 | $0.075 | - | $5.50 |", 1)})
        doc = T.consultar(self.tmp, descargar=web, ahora=AHORA)
        e = next(x for x in doc["entradas"] if x["modelo_api_id"] == "gpt-5.4-mini")
        self.assertTrue(e["cambio_respecto_ultimo"])
        self.assertEqual(e["diferencias"], [{"campo": "salida_por_millon", "anterior": "4.5", "actual": "5.5"}])
        self.assertEqual(self.tarifas()[("OpenAI", "gpt-5.4-mini")]["salida_por_millon"], "5.5")
        self.assertEqual(doc["resumen"]["con_cambio_de_precio"], 1)

    def test_patron_roto_degrada_a_no_verificada_y_no_conserva_el_precio_activo(self):
        web = Web(cambios={"https://developers.openai.com/api/docs/pricing.md": lambda s: s.replace("| gpt-5.4-mini |", "| gpt-5.4-mini-v2 |")})
        T.consultar(self.tmp, descargar=web, ahora=AHORA)
        t = self.tarifas()[("OpenAI", "gpt-5.4-mini")]
        self.assertEqual(t["estado"], "no_verificada")
        self.assertTrue(t["motivo_no_verificada"].startswith("extracto_ausente"))
        for c in T.CAMPOS_PRECIO:
            self.assertIsNone(t[c], c)
        self.assertEqual(t["ultimo_valor_verificado"]["salida_por_millon"], "4.5")   # historia, no valor activo
        errores, _ = T.verificar(self.tmp, ahora=AHORA)
        self.assertEqual(errores, [])
        # las demás entradas de la misma página siguen verificadas
        self.assertEqual(self.tarifas()[("OpenAI", "gpt-5.4")]["estado"], "verificada")

    def test_causas_de_fallo_exactas(self):
        u = "https://developers.openai.com/api/docs/pricing.md"
        casos = {
            "http_404": T.Respuesta(404, u, b"x" * 500, None),
            "bloqueada: HTTP 403": T.Respuesta(403, u, b"x" * 500, None),
            "bloqueada: HTTP 429": T.Respuesta(429, u, b"x" * 500, None),
            "error_de_red": T.Respuesta(None, None, b"", "TimeoutError: timed out"),
            "redireccion_ajena": T.Respuesta(200, "https://developers.openai.com/", b"x" * 500, None),
            "contenido_insuficiente": T.Respuesta(200, u, b"vacio", None),
            "requiere_js": T.Respuesta(200, u, (b"<html>Please enable JavaScript to view this page. " + b"x" * 300 + b"</html>"), None),
            "extracto_ausente": T.Respuesta(200, u, b"# Pricing\n" + b"sin tabla " * 60, None),
        }
        for esperado, resp in casos.items():
            with self.subTest(esperado):
                tmp = Path(tempfile.mkdtemp(prefix="tarifas_"))
                self.addCleanup(shutil.rmtree, tmp, True)
                for n in ("tarifas.json", "fuentes.json"):
                    shutil.copy(REAL / n, tmp / n)
                shutil.copytree(REAL / "consultas", tmp / "consultas")
                doc = T.consultar(tmp, descargar=Web(respuestas={u: resp}), ahora=AHORA, modelos=["gpt-5.4-mini"])
                e = doc["entradas"][0]
                self.assertEqual(e["estado"], "no_verificada")
                self.assertTrue(e["motivo"].startswith(esperado), e["motivo"])

    def test_la_redireccion_de_groq_a_la_portada_no_se_maquilla(self):
        """groq.com/pricing redirige a la portada (bloqueo registrado por la auditoría): si una fuente
        apuntara allí, la consulta debe dar no_verificada y no inventar un precio."""
        spec = {"url": "https://groq.com/pricing", "formato": "html", "patron": r"(?P<entrada_sin_cache>\d+)"}
        r = T._evaluar_pagina(spec, T.Respuesta(200, "https://groq.com/", b"<html>" + b"portada " * 100 + b"</html>", None))
        self.assertTrue(r["motivo"].startswith("redireccion_ajena"))
        fuentes = json.loads((REAL / "fuentes.json").read_text(encoding="utf-8"))
        self.assertIn("https://groq.com/pricing", [b["url"] for b in fuentes["paginas_bloqueadas"]])
        usadas = {p["url"] for f in fuentes["fuentes"] for p in f["paginas"]}
        self.assertNotIn("https://groq.com/pricing", usadas)

    def test_solo_comprobar_no_modifica_tarifas(self):
        antes = (self.tmp / "tarifas.json").read_bytes()
        T.consultar(self.tmp, descargar=Web(respuestas={"https://developers.openai.com/api/docs/pricing.md": T.Respuesta(403, None, b"", None)}),
                    ahora=AHORA, solo_comprobar=True)
        self.assertEqual((self.tmp / "tarifas.json").read_bytes(), antes)
        self.assertTrue((self.tmp / "consultas" / "20261001T100000Z.json").exists())

    def test_precio_no_plausible(self):
        web = Web(cambios={"https://developers.openai.com/api/docs/pricing.md":
                           lambda s: s.replace("| gpt-5.4-mini | $0.75 | $0.075 | - | $4.50 |", "| gpt-5.4-mini | $0.75 | $9.075 | - | $4.50 |", 1)})
        doc = T.consultar(self.tmp, descargar=web, ahora=AHORA, modelos=["gpt-5.4-mini"])
        self.assertTrue(doc["entradas"][0]["motivo"].startswith("precio_no_plausible"))

    def test_deepseek_toma_la_tarifa_de_pico_de_cada_columna(self):
        T.consultar(self.tmp, descargar=Web(), ahora=AHORA, modelos=["deepseek-flash", "deepseek-v4-pro"])
        t = self.tarifas()
        f, p = t[("DeepSeek", "deepseek-flash")], t[("DeepSeek", "deepseek-v4-pro")]
        self.assertEqual((f["entrada_sin_cache_por_millon"], f["entrada_cache_lectura_por_millon"], f["salida_por_millon"]), ("0.3", "0.006", "1.2"))
        self.assertEqual((p["entrada_sin_cache_por_millon"], p["entrada_cache_lectura_por_millon"], p["salida_por_millon"]), ("1.32", "0.044", "3.96"))

    def test_groq_une_tabla_de_modelos_y_pagina_del_modelo(self):
        T.consultar(self.tmp, descargar=Web(), ahora=AHORA, modelos=["openai/gpt-oss-20b", "qwen/qwen3.8-27b"])
        t = self.tarifas()
        g = t[("Groq", "openai/gpt-oss-20b")]
        self.assertEqual((g["entrada_sin_cache_por_millon"], g["entrada_cache_lectura_por_millon"], g["salida_por_millon"]), ("0.075", "0.037", "0.3"))
        q = t[("Groq", "qwen/qwen3.8-27b")]
        self.assertIsNone(q["entrada_cache_lectura_por_millon"])   # sin dato de caché: no se inventa

    def test_google_toma_la_primera_tabla_standard_de_cada_seccion(self):
        T.consultar(self.tmp, descargar=Web(), ahora=AHORA, modelos=["gemini-3.8-flash", "gemini-3.1-pro-preview"])
        t = self.tarifas()
        self.assertEqual(t[("Google", "gemini-3.8-flash")]["salida_por_millon"], "3.75")          # promocional vigente hoy
        self.assertEqual(t[("Google", "gemini-3.1-pro-preview")]["entrada_sin_cache_por_millon"], "2")   # <= 200k, no 4.00

    def test_anthropic_no_confunde_la_escritura_de_cache_con_la_lectura(self):
        T.consultar(self.tmp, descargar=Web(), ahora=AHORA, modelos=["claude-opus-5-5", "claude-sonnet-5"])
        t = self.tarifas()
        o = t[("Anthropic", "claude-opus-5-5")]
        self.assertEqual((o["entrada_sin_cache_por_millon"], o["entrada_cache_escritura_por_millon"], o["entrada_cache_lectura_por_millon"], o["salida_por_millon"]),
                         ("4", "5", "0.2", "20"))
        s = t[("Anthropic", "claude-sonnet-5")]   # 'Claude Sonnet 5' no debe tomar la fila de 'Claude Sonnet 5.5'
        self.assertEqual(s["entrada_cache_lectura_por_millon"], "0.2")


class Verificar(Base):
    def _editar(self, fn):
        p = self.tmp / "tarifas.json"
        d = json.loads(p.read_text(encoding="utf-8"))
        fn(d)
        p.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")

    def test_datos_versionados_son_validos(self):
        errores, avisos = T.verificar(REAL, ahora="2026-10-01T00:00:00Z")
        self.assertEqual(errores, [])
        self.assertEqual(avisos, [])
        doc = json.loads((REAL / "tarifas.json").read_text(encoding="utf-8"))
        self.assertEqual(len(doc["tarifas"]), 30)
        self.assertEqual(sum(1 for t in doc["tarifas"] if t["estado"] == "verificada"), 27)
        self.assertEqual(sum(1 for t in doc["tarifas"] if t["estado"] == "no_verificada"), 3)
        self.assertIn("aproximación", doc["nota_tokenizadores"])

    def test_mas_de_14_dias_es_desactualizada_advertencia(self):
        errores, avisos = T.verificar(REAL, ahora="2026-10-20T00:00:00Z")
        self.assertEqual(errores, [])
        self.assertEqual(len(avisos), 27)
        self.assertTrue(all(a.startswith("desactualizada:") for a in avisos))
        _, avisos14 = T.verificar(REAL, ahora="2026-10-14T00:00:00Z")   # 13-14 dias: todavia vigente
        self.assertEqual(avisos14, [])
        self.assertEqual(T.main(["--directorio", str(REAL), "verificar", "--ahora", "2026-10-20T00:00:00Z"]), 0)
        self.assertEqual(T.main(["--directorio", str(REAL), "verificar", "--estricto", "--ahora", "2026-10-20T00:00:00Z"]), 1)

    def test_no_verificada_no_puede_llevar_precio(self):
        def f(d):
            t = next(x for x in d["tarifas"] if x["modelo_api_id"] == "deepseek-chat")
            t["salida_por_millon"] = "1.2"
        self._editar(f)
        errores, _ = T.verificar(self.tmp, ahora=AHORA)
        self.assertTrue(any("no_verificada no puede llevar precios activos" in e for e in errores))

    def test_precio_como_numero_es_error(self):
        self._editar(lambda d: d["tarifas"][0].update(salida_por_millon=15.0))
        errores, _ = T.verificar(self.tmp, ahora=AHORA)
        self.assertTrue(any("cadena decimal" in e for e in errores))

    def test_extracto_editado_no_coincide_con_su_hash(self):
        self._editar(lambda d: d["tarifas"][0].update(extracto="| gpt-5.4 | $1.00 |"))
        errores, _ = T.verificar(self.tmp, ahora=AHORA)
        self.assertTrue(any("extracto_sha256" in e for e in errores))

    def test_verificada_exige_entrada_y_salida(self):
        self._editar(lambda d: d["tarifas"][0].update(salida_por_millon=None))
        errores, _ = T.verificar(self.tmp, ahora=AHORA)
        self.assertTrue(any("verificada exige precio" in e for e in errores))

    def test_estado_invalido_y_entrada_repetida(self):
        def f(d):
            d["tarifas"][0]["estado"] = "casi_verificada"
            d["tarifas"].append(copy.deepcopy(d["tarifas"][1]))
        self._editar(f)
        errores, _ = T.verificar(self.tmp, ahora=AHORA)
        self.assertTrue(any("estado debe ser uno de" in e for e in errores))
        self.assertTrue(any("entrada repetida" in e for e in errores))

    def test_fecha_futura(self):
        self._editar(lambda d: d["tarifas"][0].update(fecha_consulta_utc="2027-01-01T00:00:00Z"))
        errores, _ = T.verificar(self.tmp, ahora=AHORA)
        self.assertTrue(any("en el futuro" in e for e in errores))

    def test_fuentes_inconsistentes(self):
        p = self.tmp / "fuentes.json"
        d = json.loads(p.read_text(encoding="utf-8"))
        d["fuentes"][0]["paginas"][0]["patron"] = "(sin cerrar"
        d["fuentes"][1]["paginas"][0]["patron"] = r"sin grupos \d+"
        d["fuentes"].pop()           # una tarifa se queda sin fuente
        d["fuentes"].append({"proveedor": "X", "modelo_api_id": "y", "paginas": [{"url": "https://x.test", "patron": "(?P<entrada_sin_cache>1)(?P<salida>2)"}]})
        p.write_text(json.dumps(d), encoding="utf-8")
        errores, _ = T.verificar(self.tmp, ahora=AHORA)
        texto = "\n".join(errores)
        self.assertIn("patrón inválido", texto)
        self.assertIn("debe declarar los grupos", texto)
        self.assertIn("falta la fuente de", texto)
        self.assertIn("no tiene entrada en tarifas.json", texto)

    def test_la_consulta_citada_debe_existir(self):
        self._editar(lambda d: d["tarifas"][0].update(consulta="19990101T000000Z.json"))
        errores, _ = T.verificar(self.tmp, ahora=AHORA)
        self.assertTrue(any("19990101T000000Z.json no existe" in e for e in errores))

    def test_falta_la_nota_de_tokenizadores(self):
        self._editar(lambda d: d.update(nota_tokenizadores=""))
        errores, _ = T.verificar(self.tmp, ahora=AHORA)
        self.assertTrue(any("nota_tokenizadores" in e for e in errores))


class MostrarYSiembra(Base):
    def test_mostrar_marca_desactualizada(self):
        texto = T.mostrar(self.tmp, proveedor="openai", ahora="2026-10-20T00:00:00Z")
        self.assertIn("desactualizada", texto)
        self.assertIn("gpt-5.4-mini", texto)
        tabla = texto.split("USD por millón")[0]
        self.assertNotIn("Anthropic", tabla)
        self.assertIn("aproximación", texto)
        tabla2 = T.mostrar(self.tmp, estado="no_verificada", ahora=AHORA).split("USD por millón")[0]
        self.assertIn("deepseek-chat", tabla2)
        self.assertNotIn("gpt-5.4", tabla2)

    def test_sembrar_no_cambia_precios_ni_pisa_consultas(self):
        origen = {"consultado_utc": "2026-09-30T18:10:00Z (paginas descargadas entre 18:09Z y 18:14Z)", "fuente_metodo": "m", "tokenizadores": [{"proveedor": "OpenAI"}], "bloqueos": ["b"], "discrepancias_repo": [],
                  "tarifas": [
                      {"proveedor": "Anthropic", "modelo_comercial": "H", "modelo_api_id": "claude-haiku-4-5-20251001 (alias: claude-haiku-4-5)", "moneda": "USD",
                       "entrada_sin_cache_por_millon": 1.0, "entrada_cache_lectura_por_millon": 0.1, "entrada_cache_escritura_por_millon": 1.25, "salida_por_millon": 5.0,
                       "otros_cargos": "", "url_oficial": "https://x.test", "extracto": "fila", "extracto_sha256": T.sha256_texto("fila"), "estado": "verificada", "notas": "n"},
                      {"proveedor": "Groq", "modelo_comercial": "Q", "modelo_api_id": "q", "moneda": "USD", "entrada_sin_cache_por_millon": None,
                       "entrada_cache_lectura_por_millon": None, "entrada_cache_escritura_por_millon": None, "salida_por_millon": None,
                       "otros_cargos": "", "url_oficial": "https://x.test", "extracto": "retirado", "extracto_sha256": T.sha256_texto("retirado"), "estado": "no_verificada", "notas": "retirado el 16-ago"}]}
        o = self.tmp / "origen.json"
        o.write_text(json.dumps(origen), encoding="utf-8")
        d = self.tmp / "nuevo"
        T.sembrar(o, d)
        doc = json.loads((d / "tarifas.json").read_text(encoding="utf-8"))
        h, q = doc["tarifas"]
        self.assertEqual(h["modelo_api_id"], "claude-haiku-4-5-20251001")
        self.assertEqual(h["alias"], ["claude-haiku-4-5"])
        self.assertEqual((h["entrada_sin_cache_por_millon"], h["entrada_cache_lectura_por_millon"], h["salida_por_millon"]), ("1", "0.1", "5"))
        self.assertEqual(h["fecha_consulta_utc"], "2026-09-30T18:10:00Z")
        self.assertIsNone(q["salida_por_millon"])
        self.assertEqual(q["motivo_no_verificada"], "retirado el 16-ago")
        with self.assertRaises(SystemExit):
            T.sembrar(o, d)          # no pisa un tarifas.json existente
        origen["tarifas"][0]["extracto"] = "otra"
        o.write_text(json.dumps(origen), encoding="utf-8")
        with self.assertRaises(SystemExit):
            T.sembrar(o, self.tmp / "otro")   # el hash del extracto no corresponde

    def test_decimal_a_cadena_conserva_el_valor(self):
        for x, s in [(2.5, "2.5"), (15.0, "15"), (0.075, "0.075"), (0.0375, "0.0375"), (1.32, "1.32"), (None, None), ("0.30", "0.3"), (0.125, "0.125")]:
            self.assertEqual(T.decimal_a_cadena(x), s)


class Http(unittest.TestCase):
    """descargar_http contra un servidor local (127.0.0.1): comprueba UA, redirección, estados y reintentos."""

    @classmethod
    def setUpClass(cls):
        cls.vistos = []
        cls.intentos = {"n": 0}

        class H(http.server.BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def do_GET(self):
                Http.vistos.append((self.path, self.headers.get("User-Agent")))
                if self.path == "/ok":
                    self._r(200, b"hola " * 100)
                elif self.path == "/redir":
                    self.send_response(302)
                    self.send_header("Location", "/ok")
                    self.end_headers()
                elif self.path == "/nada":
                    self._r(404, b"no existe")
                elif self.path == "/inestable":
                    Http.intentos["n"] += 1
                    self._r(200 if Http.intentos["n"] >= 3 else 503, b"ok" * 200)
                else:
                    self._r(500, b"error")

            def _r(self, code, body):
                self.send_response(code)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

        cls.srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), H)
        cls.base = f"http://127.0.0.1:{cls.srv.server_address[1]}"
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()
        cls.srv.server_close()

    def test_user_agent_identificable_y_redireccion(self):
        r = T.descargar_http(self.base + "/redir", timeout=5, dormir=lambda s: None)
        self.assertEqual(r.status, 200)
        self.assertTrue(r.url_final.endswith("/ok"))
        self.assertTrue(all("mini-format-tarifas" in (ua or "") for _, ua in self.vistos))

    def test_404_se_devuelve_tal_cual_y_sin_reintentos(self):
        antes = len(self.vistos)
        r = T.descargar_http(self.base + "/nada", timeout=5, dormir=lambda s: None)
        self.assertEqual(r.status, 404)
        self.assertEqual(len(self.vistos) - antes, 1)

    def test_5xx_se_reintenta_con_espera(self):
        Http.intentos["n"] = 0
        esperas = []
        r = T.descargar_http(self.base + "/inestable", timeout=5, reintentos=2, dormir=esperas.append)
        self.assertEqual(r.status, 200)
        self.assertEqual(esperas, [2.0, 4.0])

    def test_error_de_conexion(self):
        r = T.descargar_http("http://127.0.0.1:9/x", timeout=2, reintentos=0, dormir=lambda s: None)
        self.assertIsNone(r.status)
        self.assertTrue(r.error)


class HtmlATexto(unittest.TestCase):
    def test_quita_scripts_estilos_y_espacios_de_ancho_cero(self):
        t = T.html_a_texto("<html><head><style>.a{}</style><script>var x='$9';</script></head><body><div>MODEL</div><span>$0.15<!-- --> <span>input</span></span>​<p>A&amp;B</p></body></html>")
        self.assertEqual(t, "MODEL $0.15 input A&B")


if __name__ == "__main__":
    unittest.main()
