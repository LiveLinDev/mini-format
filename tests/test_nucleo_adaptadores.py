"""Adaptadores de modelos (V5 e): pruebas con MOCK; ninguna llama a un proveedor real ni a la red.

Convención (se comprueba más abajo): toda prueba de adaptador se llama ``test_mock_*`` y el módulo dice MOCK en
este docstring. Un transporte simulado registra la petición y devuelve una respuesta fija; las claves son
valores de mentira puestos en el entorno solo durante la prueba. Una prueba que llamara a un proveedor real
tendría que llamarse ``test_real_*`` y protegerse con la variable MINI_PRUEBAS_REALES; hoy no hay ninguna, y la
fixture ``sin_red`` de tests/conftest.py hace fallar cualquier conexión externa.

Adaptadores cubiertos con MOCK: anthropic, groq, deepseek (HTTP por transporte inyectado), openai (cliente
inyectado) y simulated (determinista, sin red). Cuatro de los proveedores reales más el simulador: más de tres.
"""
from __future__ import annotations

import ast
import json
import socket
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from minifmt.ai.adapters import (AdapterError, AnthropicAdapter, DeepSeekAdapter, GroqAdapter, MissingKeyError,  # noqa: E402
                                 OpenAIAdapter, SimulatedAdapter, get_adapter, redact)

CLAVE_FALSA = "sk-mock-0123456789abcdefghij"


class Transporte:
    """MOCK de transporte HTTP: guarda lo recibido y devuelve una respuesta fija."""

    def __init__(self, respuesta):
        self.respuesta, self.llamadas = respuesta, []

    def __call__(self, url, headers, body, timeout):
        self.llamadas.append({"url": url, "headers": dict(headers), "body": json.loads(body)})
        return 200, json.dumps(self.respuesta).encode()


def _sin_claves():
    return mock.patch.dict("os.environ", {k: "" for k in ("OPENAI_API_KEY", "ANTHROPIC_API_KEY", "GROQ_API_KEY", "DEEPSEEK_API_KEY")})


class AdaptadoresMock(unittest.TestCase):
    def test_mock_anthropic_construye_la_peticion_y_lee_el_uso(self):
        t = Transporte({"model": "m", "stop_reason": "end_turn", "content": [{"type": "text", "text": "hola"}],
                        "usage": {"input_tokens": 7, "output_tokens": 2}})
        with mock.patch.dict("os.environ", {"ANTHROPIC_API_KEY": CLAVE_FALSA}):
            r = AnthropicAdapter("m", transport=t).generate("sis", "usr", max_tokens=50, temperature=0.0)
        (llamada,) = t.llamadas
        self.assertTrue(llamada["url"].endswith("/v1/messages"))
        self.assertEqual(llamada["headers"]["x-api-key"], CLAVE_FALSA)
        self.assertEqual(llamada["body"]["system"], "sis")
        self.assertEqual((r["text"], r["input_tokens"], r["output_tokens"], r["provider"]), ("hola", 7, 2, "anthropic"))

    def test_mock_groq_construye_la_peticion_y_lee_el_uso(self):
        t = Transporte({"model": "m", "choices": [{"message": {"content": "hola"}, "finish_reason": "stop"}],
                        "usage": {"prompt_tokens": 9, "completion_tokens": 3}})
        with mock.patch.dict("os.environ", {"GROQ_API_KEY": CLAVE_FALSA}):
            r = GroqAdapter("m", transport=t).generate("sis", "usr", max_tokens=50, temperature=0.0, seed=3)
        (llamada,) = t.llamadas
        self.assertTrue(llamada["url"].endswith("/chat/completions"))
        self.assertEqual(llamada["headers"]["authorization"], "Bearer " + CLAVE_FALSA)
        self.assertEqual(llamada["body"]["max_completion_tokens"], 50)
        self.assertEqual((r["text"], r["input_tokens"], r["output_tokens"], r["provider"]), ("hola", 9, 3, "groq"))

    def test_mock_deepseek_usa_max_tokens_y_su_propia_clave(self):
        t = Transporte({"model": "m", "choices": [{"message": {"content": "hola"}, "finish_reason": "stop"}],
                        "usage": {"prompt_tokens": 4, "completion_tokens": 1}})
        with mock.patch.dict("os.environ", {"DEEPSEEK_API_KEY": CLAVE_FALSA}):
            r = DeepSeekAdapter("m", transport=t).generate("sis", "usr", max_tokens=50, temperature=0.0)
        (llamada,) = t.llamadas
        self.assertIn("deepseek", llamada["url"])
        self.assertEqual(llamada["body"]["max_tokens"], 50)
        self.assertNotIn("max_completion_tokens", llamada["body"])
        self.assertEqual(r["provider"], "deepseek")

    def test_mock_openai_con_cliente_inyectado(self):
        cliente = mock.MagicMock()
        cliente.chat.completions.create.return_value = SimpleNamespace(
            model="m", choices=[SimpleNamespace(message=SimpleNamespace(content="hola"), finish_reason="stop")],
            usage=SimpleNamespace(prompt_tokens=5, completion_tokens=2),
            model_dump=lambda: {"model": "m", "choices": [{"message": {"content": "hola"}, "finish_reason": "stop"}],
                                "usage": {"prompt_tokens": 5, "completion_tokens": 2}})
        with mock.patch.dict("os.environ", {"OPENAI_API_KEY": CLAVE_FALSA}):
            r = OpenAIAdapter("m", client=cliente).generate("sis", "usr", max_tokens=50, temperature=0.0)
        cliente.chat.completions.create.assert_called_once()
        self.assertEqual((r["text"], r["input_tokens"], r["provider"]), ("hola", 5, "openai"))

    def test_mock_el_adaptador_simulado_es_determinista_y_no_usa_red(self):
        salidas = {SimulatedAdapter("sim", profile="debil", seed=5).generate("sis", "usr", max_tokens=50, temperature=0.0, seed=2)["text"]
                   for _ in range(3)}
        self.assertEqual(len(salidas), 1, "mismo (semilla, modelo, petición) => misma respuesta")
        self.assertEqual(SimulatedAdapter("sim").provider, "simulado")
        self.assertIsInstance(get_adapter("simulated", "sim"), SimulatedAdapter)

    def test_mock_sin_clave_no_se_hace_ninguna_llamada(self):
        t = Transporte({})
        with _sin_claves():
            for cls in (AnthropicAdapter, GroqAdapter, DeepSeekAdapter):
                with self.assertRaises(MissingKeyError):
                    cls("m", transport=t).generate("s", "u", max_tokens=1, temperature=0.0)
        self.assertEqual(t.llamadas, [], "sin clave el adaptador debe fallar ANTES de llamar")

    def test_mock_los_errores_no_revelan_la_clave(self):
        with mock.patch.dict("os.environ", {"GROQ_API_KEY": CLAVE_FALSA}):
            ad = GroqAdapter("m", transport=lambda *a: (401, ("clave " + CLAVE_FALSA + " rechazada").encode()), retries=0)
            with self.assertRaises(AdapterError) as cm:
                ad.generate("s", "u", max_tokens=1, temperature=0.0)
        self.assertNotIn(CLAVE_FALSA, str(cm.exception))
        self.assertNotIn(CLAVE_FALSA, redact(f"x {CLAVE_FALSA}"))


class NingunaPruebaUsaLaRed(unittest.TestCase):
    def test_la_fixture_sin_red_bloquea_destinos_externos(self):
        with self.assertRaises(RuntimeError):
            socket.create_connection(("example.com", 80), timeout=1)
        with self.assertRaises(RuntimeError):
            socket.socket().connect(("203.0.113.7", 443))  # dirección de documentación (TEST-NET-3)

    def test_sin_red_permite_el_bucle_local(self):
        servidor = socket.socket()
        servidor.bind(("127.0.0.1", 0))
        servidor.listen(1)
        try:
            cliente = socket.create_connection(servidor.getsockname(), timeout=2)
            cliente.close()
        finally:
            servidor.close()

    def test_las_pruebas_de_adaptadores_se_declaran_mock(self):
        """Toda prueba de este módulo se llama test_mock_*/test_la_*/etc. y el módulo dice MOCK; ninguna se llama test_real_*."""
        arbol = ast.parse(Path(__file__).read_text(encoding="utf-8"))
        self.assertIn("MOCK", ast.get_docstring(arbol) or "")
        nombres = [n.name for n in ast.walk(arbol) if isinstance(n, ast.FunctionDef) and n.name.startswith("test_")]
        self.assertTrue(nombres)
        self.assertFalse([n for n in nombres if n.startswith("test_real")], "las pruebas reales no existen sin MINI_PRUEBAS_REALES")
        for clase in (n for n in ast.walk(arbol) if isinstance(n, ast.ClassDef) and n.name == "AdaptadoresMock"):
            for f in (n for n in clase.body if isinstance(n, ast.FunctionDef) and n.name.startswith("test_")):
                self.assertTrue(f.name.startswith("test_mock_"), f.name)

    def test_las_pruebas_typescript_de_adaptadores_declaran_fetch_simulado(self):
        ts = (ROOT / "ts" / "test" / "adapters.test.ts").read_text(encoding="utf-8")
        self.assertIn("MOCK", ts.split("*/", 1)[0], "ts/test/adapters.test.ts debe declararse MOCK en su cabecera")
        self.assertIn("fakeFetch", ts)
        self.assertIn("network access is forbidden in tests", ts, "el fetch global debe quedar sustituido por uno que falla")


if __name__ == "__main__":
    unittest.main()
