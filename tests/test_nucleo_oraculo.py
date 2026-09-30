"""V5 (c) y (d): el decodificador independiente contra el corpus de conformidad y el fuzz diferencial acotado.

* El oráculo (conformance/oraculo/decodificador.py) no importa minifmt: se comprueba leyendo su código.
* Cumple todos los casos strict y lenient del corpus (expectativas escritas desde la SPEC o publicadas en los fixtures).
* Python, js/mini.js y el oráculo coinciden sobre los documentos originales y sobre 4 000 mutantes con semilla fija
  (tools/fuzz_diferencial.py; el fuzz completo de 100 s lo ejecuta tools/ejecutar_v5.py).
"""
from __future__ import annotations

import ast
import json
import shutil
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "conformance" / "oraculo"))
sys.path.insert(0, str(ROOT / "tools"))

import ejecutar  # noqa: E402
import fuzz_diferencial  # noqa: E402


class OraculoIndependiente(unittest.TestCase):
    def test_no_importa_la_biblioteca(self):
        for archivo in (ROOT / "conformance" / "oraculo").glob("decodificador.py"):
            arbol = ast.parse(archivo.read_text(encoding="utf-8"))
            for n in ast.walk(arbol):
                if isinstance(n, ast.Import):
                    nombres = [a.name for a in n.names]
                elif isinstance(n, ast.ImportFrom):
                    nombres = [n.module or ""]
                else:
                    continue
                for nombre in nombres:
                    self.assertFalse(nombre.startswith("minifmt"), f"{archivo.name} importa {nombre}")

    def test_cumple_todo_el_corpus_strict_y_lenient(self):
        total = 0
        for caso in ejecutar.cargar_casos():
            if caso["mode"] not in ("strict", "lenient"):
                continue
            total += 1
            ok, mensaje = ejecutar.ejecutar_caso(caso)
            self.assertTrue(ok, f"{caso['id']}: {mensaje}")
        self.assertGreaterEqual(total, 300)

    def test_cubre_los_trece_codigos_de_documento_y_registro(self):
        """El corpus ejerce cada código que el oráculo puede emitir: si un código dejara de aparecer, el oráculo no estaría probado."""
        vistos = set()
        for caso in ejecutar.cargar_casos():
            if caso["mode"] in ("strict", "lenient"):
                vistos |= {e["code"] for e in caso["expected"].get("errors", [])}
        self.assertEqual(vistos, {"E01", "E02", "E03", "E04", "E05", "E06", "E07", "E08", "E09", "E10", "E11", "E12", "E13"})


@unittest.skipUnless(shutil.which("node"), "node no está instalado: el fuzz contra js/mini.js necesita Node")
class FuzzDiferencialAcotado(unittest.TestCase):
    def test_python_js_y_oraculo_coinciden(self):
        resumen = fuzz_diferencial.ejecutar(None, 4000, fuzz_diferencial.SEMILLA_POR_OMISION)
        self.assertEqual(resumen["documentos"], 4000)
        self.assertEqual(resumen["inesperadas"], {}, json.dumps(resumen["ejemplos"], ensure_ascii=False)[:1500])

    def test_no_deja_archivos_temporales(self):
        import tempfile
        antes = set(Path(tempfile.gettempdir()).glob("mini-fuzz-*"))
        fuzz_diferencial.ejecutar(None, 400, 1)
        despues = set(Path(tempfile.gettempdir()).glob("mini-fuzz-*"))
        self.assertEqual(despues - antes, set())

    def test_la_semilla_es_reproducible(self):
        a = list(zip(range(300), fuzz_diferencial.generar(fuzz_diferencial.documentos_base()[1], 7)))
        b = list(zip(range(300), fuzz_diferencial.generar(fuzz_diferencial.documentos_base()[1], 7)))
        self.assertEqual([x[1]["text"] for x in a], [x[1]["text"] for x in b])


if __name__ == "__main__":
    unittest.main()
