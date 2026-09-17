"""HU25: la demostración sin conexión reproduce el flujo completo en menos de 3 minutos."""
import os
import subprocess
import sys
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEMO = ROOT / "demo" / "sin-conexion" / "demo.py"


class TestDemoSinConexion(unittest.TestCase):
    def test_flujo_completo_sin_red_en_menos_de_tres_minutos(self):
        inicio = time.monotonic()
        env = dict(os.environ, PYTHONIOENCODING="utf-8")
        salida = subprocess.run([sys.executable, str(DEMO), "--rapido"], capture_output=True, text=True,
                                encoding="utf-8", env=env, timeout=180)
        duracion = time.monotonic() - inicio
        self.assertEqual(salida.returncode, 0, salida.stdout + salida.stderr)
        self.assertLess(duracion, 180)
        texto = salida.stdout
        for etapa in ("[1/6] Contrato", "[2/6] Instrucción", "[3/6] Lectura en streaming",
                      "[4/6] Validación", "[5/6] Reparación selectiva", "[6/6] Objetos tipados"):
            self.assertIn(etapa, texto)
        self.assertIn("Líneas reenviadas al modelo: [3, 6]", texto)
        self.assertIn("Documento reparado idéntico a la respuesta original: sí", texto)
        self.assertIn("red bloqueada durante toda la ejecución", texto)


if __name__ == "__main__":
    unittest.main()
