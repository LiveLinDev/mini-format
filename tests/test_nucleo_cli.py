"""V5 (e): la CLI y los ejemplos del repositorio, ejecutados como procesos reales (``python -m minifmt``).

A diferencia de tests/test_cli_tools.py (llama a ``cli.main`` dentro del proceso), aquí cada orden es un proceso nuevo
con el entorno limpio: comprueba códigos de salida, salida estándar y archivos escritos, como los vería una persona o el CI.
No usa red ni claves. Incluye la recuperación desde los ejemplos de ``examples/`` (mesa de ayuda, teléfonos).
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from typing import List, Tuple

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from minifmt import Registry  # noqa: E402

REG = Registry.load(ROOT / "forks")
MUESTRA = ("a", "cls", "tc")  # muestra representativa a nivel de proceso; 14/14 lo comprueba check-forks


def mini(*args: str, cwd: Path, entrada: str = "") -> Tuple[int, str, str]:
    entorno = dict(os.environ, PYTHONIOENCODING="utf-8", PYTHONPATH=str(ROOT / "src"))
    p = subprocess.run([sys.executable, "-m", "minifmt", *args], cwd=cwd, env=entorno, input=entrada,
                       capture_output=True, text=True, encoding="utf-8")
    return p.returncode, p.stdout, p.stderr


class CliComoProceso(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="mini-cli-"))

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_forks_lista_las_catorce_familias(self):
        rc, salida, _ = mini("forks", cwd=self.tmp)
        self.assertEqual(rc, 0)
        for c in REG:
            self.assertIn(c.prefix, salida)
        self.assertEqual(len(list(REG)), 14)

    def test_check_forks_14_de_14(self):
        rc, salida, _ = mini("check-forks", cwd=self.tmp)
        self.assertEqual(rc, 0, salida)
        self.assertIn("ALL FORKS PASS (14 forks)", salida)

    def test_las_familias_de_muestra_validan_y_hacen_ida_y_vuelta_con_los_ficheros_publicados(self):
        """valid.mini -> to-json == canonical.json y canonical.json -> from-json == valid.mini (salvo el LF final)."""
        for c in (REG.get(p) for p in MUESTRA):
            fx = REG.paths[c.prefix] / "fixtures"
            with self.subTest(familia=c.prefix):
                rc, salida, err = mini("validate", str(fx / "valid.mini"), "-p", c.prefix, cwd=self.tmp)
                self.assertEqual(rc, 0, salida + err)
                self.assertIn(f"prefix={c.prefix}", salida)
                destino = self.tmp / f"{c.prefix}.json"
                rc, _, err = mini("to-json", str(fx / "valid.mini"), "-p", c.prefix, "--out", str(destino), cwd=self.tmp)
                self.assertEqual(rc, 0, err)
                self.assertEqual(json.loads(destino.read_text(encoding="utf-8")),
                                 json.loads((fx / "canonical.json").read_text(encoding="utf-8")))
                texto = self.tmp / f"{c.prefix}.mini"
                rc, _, err = mini("from-json", str(fx / "canonical.json"), "-p", c.prefix, "--out", str(texto), cwd=self.tmp)
                self.assertEqual(rc, 0, err)
                self.assertEqual(texto.read_bytes().decode("utf-8").rstrip("\n"),
                                 (fx / "valid.mini").read_text(encoding="utf-8").rstrip("\n"))
                self.assertNotIn(b"\r", texto.read_bytes(), "la salida debe usar LF en todos los sistemas")

    def test_los_ficheros_negativos_salen_con_codigo_1_y_el_codigo_de_error_esperado(self):
        esperado = {"bad_arity": "E05", "bad_type": "E06", "bad_marker": "E08", "bad_count": "E04"}
        for c in (REG.get(p) for p in MUESTRA):
            for f in sorted((REG.paths[c.prefix] / "fixtures").glob("bad_*.mini")):
                with self.subTest(familia=c.prefix, fichero=f.name):
                    rc, salida, err = mini("validate", str(f), "-p", c.prefix, cwd=self.tmp)
                    self.assertEqual(rc, 1, salida + err)
                    self.assertIn(esperado[f.stem], salida + err)
                    self.assertIn("INVALID", salida + err)

    def test_diagnose_informa_las_lineas_a_regenerar(self):
        rc, salida, err = mini("diagnose", str(REG.paths["a"] / "fixtures" / "bad_type.mini"), "-p", "a", cwd=self.tmp)
        self.assertEqual(rc, 1, err)  # el informe se imprime y la salida 1 indica que el documento tiene errores
        d = json.loads(salida)
        self.assertEqual(d["declared_n"], 12)
        self.assertEqual(len(d["invalid_lines"]), 1)
        self.assertEqual(d["valid_records"], 11)

    def test_prompt_en_los_dos_idiomas(self):
        for c in (REG.get(p) for p in ("a", "cls", "tc")):
            for idioma in ("en", "es"):
                with self.subTest(familia=c.prefix, idioma=idioma):
                    rc, salida, err = mini("prompt", c.prefix, "--lang", idioma, cwd=self.tmp)
                    self.assertEqual(rc, 0, err)
                    self.assertIn(c.prefix + "|n=", salida)
                    self.assertGreater(len(salida), 500)

    def test_un_prefijo_desconocido_falla_con_un_mensaje(self):
        rc, salida, err = mini("prompt", "no-existe", cwd=self.tmp)
        self.assertNotEqual(rc, 0)
        self.assertTrue((salida + err).strip())

    def test_ejemplo_telefonos_build_from_json_validate_to_json(self):
        muestras = [str(ROOT / "examples" / "phones.json"), str(ROOT / "examples" / "phones-extra.json")]
        rc, _, err = mini("build", *muestras, "--prefix", "phone", "--out", str(self.tmp / ".mini"), cwd=self.tmp)
        self.assertEqual(rc, 0, err)
        contrato = self.tmp / ".mini" / "contract.json"
        self.assertTrue(contrato.is_file())
        rc, _, err = mini("from-json", muestras[0], "--contract", str(contrato), "--out", "phones.mini", cwd=self.tmp)
        self.assertEqual(rc, 0, err)
        rc, salida, err = mini("validate", "phones.mini", "--contract", str(contrato), cwd=self.tmp)
        self.assertEqual(rc, 0, salida + err)
        rc, _, err = mini("to-json", "phones.mini", "--contract", str(contrato), "--out", "vuelta.json", cwd=self.tmp)
        self.assertEqual(rc, 0, err)
        self.assertEqual(json.loads((self.tmp / "vuelta.json").read_text(encoding="utf-8")),
                         json.loads(Path(muestras[0]).read_text(encoding="utf-8")))

    def test_ejemplo_mesa_de_ayuda_respuestas_grabadas(self):
        base = ROOT / "examples" / "mesa-de-ayuda"
        rc, _, err = mini("from-schema", str(base / "ticket.schema.json"), "-p", "tk", "--out", "contrato_tk.json", cwd=self.tmp)
        self.assertEqual(rc, 0, err)
        rc, salida, err = mini("validate", str(base / "grabaciones" / "mini" / "ok.mini"), "--contract", "contrato_tk.json", cwd=self.tmp)
        self.assertEqual((rc, "OK" in salida), (0, True), salida + err)
        rc, salida, err = mini("validate", str(base / "grabaciones" / "mini" / "error.mini"), "--contract", "contrato_tk.json", cwd=self.tmp)
        self.assertEqual(rc, 1)
        self.assertIn("E10 line 6", salida + err)
        rc, salida, err = mini("validate", str(base / "grabaciones" / "mini" / "cortada.mini"), "--contract", "contrato_tk.json", cwd=self.tmp)
        self.assertEqual(rc, 1)
        self.assertTrue("E04" in salida + err and "E05" in salida + err, salida + err)

    def test_to_schema_produce_un_json_schema_valido_por_familia(self):
        for prefijo in ("a", "cls", "tc"):
            with self.subTest(familia=prefijo):
                rc, salida, err = mini("to-schema", prefijo, cwd=self.tmp)
                self.assertEqual(rc, 0, err)
                esquema = json.loads(salida)
                self.assertEqual(esquema["type"], "object")
                self.assertIn("properties", esquema)

    def test_tokens_sin_extras_dice_como_instalarlos(self):
        """Una instalacion sin tiktoken ni benchmark/vocab no debe terminar con un FileNotFoundError crudo."""
        from unittest import mock

        from minifmt import cli
        archivo = self.tmp / "texto.txt"
        archivo.write_text("hola", encoding="utf-8")
        with mock.patch("minifmt.tokens.get_tokenizer", side_effect=FileNotFoundError("benchmark/vocab/o200k_base.tiktoken")):
            with self.assertRaises(SystemExit) as cm:
                cli.main(["tokens", str(archivo)])
        self.assertIn("mini-format[bench]", str(cm.exception.code))

    def test_sin_argumentos_la_ayuda_no_es_un_error_de_python(self):
        rc, salida, err = mini("--help", cwd=self.tmp)
        self.assertEqual(rc, 0)
        self.assertNotIn("Traceback", salida + err)
        for orden in ("forks", "validate", "check-forks", "from-schema", "bench"):
            self.assertIn(orden, salida)


if __name__ == "__main__":
    unittest.main()
