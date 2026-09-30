"""V1: ``tools/ejecutar_v1.py --rapido`` corre de extremo a extremo, sin red, sin pisar lo archivado.

Usa un directorio temporal como salida: el repositorio no recibe ninguna corrida nueva. Un subconjunto de
dominios (3) nunca puede dar veredicto del criterio (exige 14): el manifiesto debe decir ``no_evaluable``.
"""
from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

try:
    import numpy  # noqa: F401
    import tiktoken  # noqa: F401
    import yaml  # noqa: F401
    HAY = shutil.which("node") is not None
except ImportError:  # pragma: no cover
    HAY = False

ARCHIVADOS = ["benchmark/public/results.json", "benchmark/public/results.csv", "benchmark/results/tokens.csv",
              "benchmark/results/summary_12.csv", "experiments/v1_tokens/results/tokens.csv",
              "experiments/v1_tokens/results/ahorro_resumen.csv"]


def _h(rel: str) -> str:
    return hashlib.sha256((ROOT / rel).read_bytes()).hexdigest()


@unittest.skipUnless(HAY, "requiere numpy, tiktoken, PyYAML y node")
class EjecutarV1RapidoTest(unittest.TestCase):
    def test_rapido_extremo_a_extremo(self):
        import evidencia_lib as ev
        antes = {r: _h(r) for r in ARCHIVADOS}
        corridas_antes = sorted(p.name for p in (ROOT / "evidencia" / "corridas").glob("*")) if (ROOT / "evidencia" / "corridas").exists() else []
        salida = Path(tempfile.mkdtemp(prefix="v1-rapido-"))
        try:
            r = subprocess.run([sys.executable, str(ROOT / "tools" / "ejecutar_v1.py"), "--rapido", "--sello", "t1", "--salida-base", str(salida)],
                               cwd=str(ROOT), capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=900)
            self.assertEqual(r.returncode, 0, r.stderr[-3000:])
            resumen = json.loads(r.stdout.strip().splitlines()[-1])
            self.assertEqual((resumen["estado"], resumen["veredicto"]), ("parcial", "no_evaluable"))
            self.assertIn("total", resumen["tiempos_s"])
            for k in ("linea_base_n12", "serie_n", "publicos", "conciliacion"):
                d = salida / f"v1-{k}-t1"
                m = json.loads((d / "manifiesto.json").read_text(encoding="utf-8"))
                self.assertEqual(ev.validar_corrida(m, d), [], k)
                self.assertEqual((m["estado_ejecucion"], m["resultado"], m["procedencia"]), ("parcial", "no_evaluable", "reproducido_local"), k)
                self.assertTrue(any("rapido" in x.lower() for x in m["limitaciones"]), k)
                self.assertEqual(m["parametros"]["sin_red"], True)
            serie = salida / "v1-serie_n-t1"
            filas = list(__import__("csv").DictReader(open(serie / "tokens_largo.csv", newline="", encoding="utf-8")))
            self.assertEqual({f["dominio"] for f in filas}, {"a", "log", "cls"})
            self.assertEqual({int(f["n"]) for f in filas}, {1, 12, 100})
            self.assertEqual({f["tokenizador"] for f in filas}, {"o200k_base", "cl100k_base", "r50k_base"})
            crit = json.loads((serie / "criterio_v1_resultado.json").read_text(encoding="utf-8"))
            self.assertFalse(crit["primario"]["alcance_completo"])
            # los conteos coinciden con lo archivado en las filas comunes (mismas series, mismo tokenizador)
            cmp = json.loads((serie / "manifiesto.json").read_text(encoding="utf-8"))["resumen"]["comparacion_con_archivado"]
            self.assertTrue(cmp["experiments/v1_tokens/results/tokens.csv"]["coincide_en_filas_comunes"])
            self.assertEqual(cmp["experiments/v1_tokens/results/tokens.csv"]["celdas_distintas"], 0)
        finally:
            shutil.rmtree(salida, ignore_errors=True)
        self.assertEqual({r: _h(r) for r in ARCHIVADOS}, antes, "la reproducción no debe pisar lo archivado")
        corridas_despues = sorted(p.name for p in (ROOT / "evidencia" / "corridas").glob("*")) if (ROOT / "evidencia" / "corridas").exists() else []
        self.assertEqual(corridas_despues, corridas_antes, "--salida-base no debe escribir en evidencia/corridas")


if __name__ == "__main__":
    unittest.main()
