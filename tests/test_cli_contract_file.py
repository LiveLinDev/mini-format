"""--contract acepta el contrato que escribe `mini from-schema` (perfil base), no solo los toolkits de dominio."""
from __future__ import annotations

import contextlib
import io
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from minifmt import cli  # noqa: E402

ESQUEMA = ROOT / "examples" / "mesa-de-ayuda" / "ticket.schema.json"
BUENO = ("tk|n=2\n"
         "T-1|alta|acceso|No puede entrar|2\n"
         "T-2|baja|pago|Cobro duplicado|3\n")


def run_cli(*argv):
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        try:
            rc = cli.main([str(a) for a in argv])
        except SystemExit as e:
            rc = e.code
    return rc, out.getvalue(), err.getvalue()


class TestContratoBase(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.contrato = self.tmp / "contrato_tk.json"
        rc, _, _ = run_cli("from-schema", ESQUEMA, "-p", "tk", "--out", self.contrato)
        self.assertEqual(rc, 0)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def archivo(self, nombre, texto):
        ruta = self.tmp / nombre
        ruta.write_text(texto, encoding="utf-8")
        return ruta

    def test_validate_documento_valido(self):
        rc, out, _ = run_cli("validate", self.archivo("ok.mini", BUENO), "--contract", self.contrato)
        self.assertEqual(rc, 0)
        self.assertIn("OK: prefix=tk", out)
        self.assertIn("records=2", out)

    def test_validate_informa_linea_y_codigo(self):
        malo = BUENO.replace("|pago|", "|facturacion|")
        rc, out, _ = run_cli("validate", self.archivo("malo.mini", malo), "--contract", self.contrato)
        self.assertEqual(rc, 1)
        self.assertIn("E10 line 3 [categoria]", out)

    def test_diagnose_respuesta_cortada(self):
        cortada = "tk|n=3\nT-1|alta|acceso|No puede entrar|2\nT-2|baja|pa"
        rc, out, _ = run_cli("diagnose", self.archivo("cortada.mini", cortada), "--contract", self.contrato)
        self.assertEqual(rc, 1)
        informe = json.loads(out)
        self.assertEqual(informe["valid_records"], 1)
        self.assertEqual(informe["declared_n"], 3)

    def test_to_json_y_from_json(self):
        rc, out, _ = run_cli("to-json", self.archivo("ok.mini", BUENO), "--contract", self.contrato, "--compact")
        self.assertEqual(rc, 0)
        objeto = json.loads(out)
        self.assertEqual(objeto["records"][0]["horas"], 2)
        rc, out, _ = run_cli("from-json", self.archivo("ok.json", json.dumps(objeto)), "--contract", self.contrato)
        self.assertEqual(rc, 0)
        self.assertEqual(out.strip(), BUENO.strip())

    def test_prompt_desde_el_archivo(self):
        rc, out, _ = run_cli("prompt", "--contract", self.contrato, "--lang", "es")
        self.assertEqual(rc, 0)
        self.assertIn("tk|n=", out)

    def test_contrato_ilegible(self):
        rc, _, _ = run_cli("validate", self.archivo("ok.mini", BUENO), "--contract", self.archivo("roto.json", "{"))
        self.assertNotEqual(rc, 0)

    def test_toolkit_de_dominio_sigue_su_camino(self):
        destino = self.tmp / ".mini"
        rc, _, _ = run_cli("build", ROOT / "examples" / "phones.json", "--prefix", "phone", "--out", destino)
        self.assertEqual(rc, 0)
        rc, out, _ = run_cli("prompt", "--contract", destino / "contract.json", "--lang", "es")
        self.assertEqual(rc, 0)
        self.assertIn("phone", out)


if __name__ == "__main__":
    unittest.main()
