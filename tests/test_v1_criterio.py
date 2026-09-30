"""V1: el criterio documental se evalúa con la interpretación FIJADA en criterio_v1.json.

Oráculos independientes del código bajo prueba:

* casos sintéticos con ahorros conocidos (p. ej. un dominio al 29,99 % no alcanza el umbral);
* las tablas archivadas de ``experiments/v1_tokens/results`` (ahorros por dominio e IC95 ya
  calculados por el pipeline original) y los recuentos 12/10/8 de la auditoría.
"""
from __future__ import annotations

import copy
import csv
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
for _p in ("src", "benchmark", "benchmark/public", "experiments", "experiments/v1_tokens"):
    sys.path.insert(0, str(ROOT / _p))

try:
    import numpy  # noqa: F401
    HAY_NUMPY = True
except ImportError:  # pragma: no cover
    HAY_NUMPY = False

if HAY_NUMPY:
    import criterio as K

RES = ROOT / "experiments" / "v1_tokens" / "results"
DOMINIOS = ["a", "card", "cat", "cls", "code", "log", "map", "ner", "q", "r", "s", "sum", "tc", "us"]
TOKS = ["o200k_base", "cl100k_base", "r50k_base"]


def _fila(t, d, n, f, tokens, valida=True, variante="muestreo"):
    return {"tokenizador": t, "variante": variante, "dominio": d, "n": n, "formato": f, "tokens": tokens,
            "comparacion_valida": valida}


def _sintetico(ahorros, valido_json=None):
    """``ahorros[t][d]`` = ahorro en % (ΣT json = 100000 por dominio repartido en 2 documentos)."""
    filas = []
    for t in TOKS:
        for d in DOMINIOS:
            mini = round(100000 * (1 - ahorros[t][d] / 100))
            for n, (m, j) in zip((100, 100), ((mini // 2, 50000), (mini - mini // 2, 50000))):
                ok = True if valido_json is None else valido_json.get((t, d), True)
                filas.append(_fila(t, d, n, "mini", m))
                filas.append(_fila(t, d, n, "json_compact", j, ok))
    return filas


@unittest.skipUnless(HAY_NUMPY, "requiere numpy")
class CriterioSinteticoTest(unittest.TestCase):
    def ahorros(self, por_tokenizador_altos):
        """Los primeros ``k`` dominios al 35 %, el resto al 29,9 %."""
        return {t: {d: (35.0 if i < por_tokenizador_altos[t] else 29.9) for i, d in enumerate(DOMINIOS)} for t in TOKS}

    def test_cumple_solo_si_cada_tokenizador_llega_a_diez_dominios(self):
        ev = K.evaluar(_sintetico(self.ahorros({t: 10 for t in TOKS})), B=200)
        self.assertEqual(ev["primario"]["veredicto"], "cumple")
        self.assertTrue(all(v["dominios_ge_umbral"] == 10 for v in ev["primario"]["decision_por_tokenizador"].values()))

    def test_no_cumple_si_un_solo_tokenizador_se_queda_en_nueve(self):
        ev = K.evaluar(_sintetico(self.ahorros({"o200k_base": 14, "cl100k_base": 12, "r50k_base": 9})), B=200)
        self.assertEqual(ev["primario"]["veredicto"], "no_cumple")
        self.assertFalse(ev["primario"]["decision_por_tokenizador"]["r50k_base"]["cumple"])
        self.assertTrue(ev["primario"]["decision_por_tokenizador"]["o200k_base"]["cumple"])

    def test_el_umbral_se_compara_sin_redondear(self):
        a = {t: {d: 29.96 for d in DOMINIOS} for t in TOKS}  # redondea a 30,0 pero NO alcanza 30
        ev = K.evaluar(_sintetico(a), B=100)
        self.assertEqual(ev["primario"]["veredicto"], "no_cumple")
        self.assertEqual(ev["primario"]["resumen_por_tokenizador"]["o200k_base"]["dominios_ge_umbral"], 0)

    def test_suma_todos_los_documentos_del_dominio_y_no_promedia_porcentajes(self):
        # dominio con dos documentos de tamaños muy distintos: manda el ratio de sumas
        filas = [_fila("o200k_base", "a", 100, "mini", 70), _fila("o200k_base", "a", 100, "json_compact", 100),
                 _fila("o200k_base", "a", 100, "mini", 900), _fila("o200k_base", "a", 100, "json_compact", 1000)]
        a = K.ahorros_dominio(filas, "o200k_base", "muestreo", 100)
        self.assertAlmostEqual(a["ahorro_pct"]["a"], 100 * (1 - 970 / 1100), places=9)  # no (30 + 10) / 2

    def test_un_dominio_sin_reversibilidad_verificada_se_excluye_y_se_dice(self):
        a = self.ahorros({t: 12 for t in TOKS})
        ev = K.evaluar(_sintetico(a, {("o200k_base", "a"): False}), B=100)
        r = ev["primario"]["resumen_por_tokenizador"]["o200k_base"]
        self.assertEqual(r["dominios_validos"], 13)
        self.assertEqual(r["dominios_excluidos"], ["a"])
        self.assertEqual(ev["primario"]["resumen_por_tokenizador"]["cl100k_base"]["dominios_validos"], 14)

    def test_con_un_subconjunto_de_dominios_no_hay_veredicto(self):
        filas = [f for f in _sintetico(self.ahorros({t: 14 for t in TOKS})) if f["dominio"] in DOMINIOS[:5]]
        ev = K.evaluar(filas, B=100)
        self.assertEqual(ev["primario"]["veredicto"], "no_evaluable")
        self.assertFalse(ev["primario"]["alcance_completo"])

    def test_el_umbral_sale_del_archivo_de_criterio_no_del_codigo(self):
        filas = _sintetico(self.ahorros({t: 10 for t in TOKS}))
        crit = K.cargar_criterio()
        self.assertEqual(K.evaluar(filas, crit, B=100)["primario"]["veredicto"], "cumple")
        otro = copy.deepcopy(crit)
        otro["interpretacion_primaria"]["umbral_pct"] = 36.0
        self.assertEqual(K.evaluar(filas, otro, B=100)["primario"]["veredicto"], "no_cumple")
        otro = copy.deepcopy(crit)
        otro["interpretacion_primaria"]["min_dominios"] = 11
        self.assertEqual(K.evaluar(filas, otro, B=100)["primario"]["veredicto"], "no_cumple")

    def test_referencia_no_reversible_queda_excluida_en_la_tabla(self):
        filas = []
        for d in DOMINIOS:
            filas += [_fila("o200k_base", d, 100, "mini", 60), _fila("o200k_base", d, 100, "json_compact", 100),
                      _fila("o200k_base", d, 100, "csv", 50, valida=False)]
        for f in filas:
            f.setdefault("decodificacion", "autocontenida")
        rev = [{"formato": "csv", "estado": "no_reversible", "causa": "descarta los metadatos"}]
        t = K.tabla_referencias(filas, rev, 30.0, B=50)
        csv_ = next(r for r in t if r["referencia"] == "csv")
        self.assertEqual(csv_["estado"], "excluido_no_reversible")
        self.assertIsNone(csv_["media_por_dominio_pct"])
        self.assertIn("metadatos", csv_["causa"])
        js = next(r for r in t if r["referencia"] == "json_compact")
        self.assertAlmostEqual(js["media_por_dominio_pct"], 40.0)


@unittest.skipUnless(HAY_NUMPY and (RES / "tokens.csv").exists(), "requiere numpy y los resultados archivados")
class CriterioFrenteAlArchivoTest(unittest.TestCase):
    """Con los conteos ARCHIVADOS de V1 el criterio debe coincidir con lo que calculó el pipeline original."""

    @classmethod
    def setUpClass(cls):
        with open(RES / "tokens.csv", newline="", encoding="utf-8") as fh:
            cls.filas = [{"tokenizador": r["tokenizador"], "variante": r["variante"], "dominio": r["dominio"], "n": int(r["n"]),
                          "formato": r["formato"], "tokens": int(r["tokens"]), "comparacion_valida": True} for r in csv.DictReader(fh)
                         if r["formato"] in ("mini", "json_compact")]
        with open(RES / "ahorro_resumen.csv", newline="", encoding="utf-8") as fh:
            cls.resumen = [r for r in csv.DictReader(fh) if r["referencia"] == "json_compact"]
        with open(RES / "ahorro_por_dominio.csv", newline="", encoding="utf-8") as fh:
            cls.por_dominio = [r for r in csv.DictReader(fh) if r["referencia"] == "json_compact"]

    def test_ahorro_por_dominio_igual_al_archivado(self):
        for t in TOKS:
            a = K.ahorros_dominio(self.filas, t, "muestreo", 100)
            for r in self.por_dominio:
                if r["tokenizador"] == t and r["variante"] == "muestreo" and r["n"] == "100":
                    self.assertAlmostEqual(a["ahorro_pct"][r["dominio"]], float(r["ahorro_pct"]), places=4)

    def test_media_e_ic95_iguales_a_los_archivados_en_todas_las_series(self):
        for r in self.resumen:
            s = K.resumen_serie(self.filas, r["tokenizador"], r["variante"], int(r["n"]), 30.0)
            self.assertAlmostEqual(s["media_por_dominio_pct"], float(r["media"]), places=4)
            self.assertAlmostEqual(s["ic95_media"][0], float(r["ic95_inf"]), places=4)
            self.assertAlmostEqual(s["ic95_media"][1], float(r["ic95_sup"]), places=4)

    def test_recuentos_de_la_auditoria_y_veredicto(self):
        ev = K.evaluar(self.filas, B=2000)
        r = ev["primario"]["resumen_por_tokenizador"]
        self.assertEqual({t: r[t]["dominios_ge_umbral"] for t in TOKS}, {"o200k_base": 12, "cl100k_base": 10, "r50k_base": 8})
        self.assertEqual(ev["primario"]["veredicto"], "no_cumple")
        self.assertAlmostEqual(r["r50k_base"]["agregado_suma_pct"], 29.17, places=2)
        self.assertAlmostEqual(r["o200k_base"]["media_por_dominio_pct"], 34.81, places=2)

    def test_efecto_de_n_con_n1_a_27_por_ciento(self):
        ev = K.evaluar(self.filas, B=200)
        e = next(x for x in ev["efecto_n"] if x["variante"] == "muestreo" and x["n"] == 1 and x["tokenizador"] == "o200k_base")
        self.assertAlmostEqual(e["media_por_dominio_pct"], 27.0, places=1)
        self.assertFalse(e["replicacion_de_base"])
        self.assertTrue(next(x for x in ev["efecto_n"] if x["n"] == 100)["replicacion_de_base"])

    def test_interpretacion_fijada_antes_del_analisis_y_sujeta_a_aprobacion(self):
        c = json.loads((ROOT / "experiments" / "v1_tokens" / "criterio_v1.json").read_text(encoding="utf-8"))
        self.assertTrue(c["fijado_antes_del_analisis"])
        self.assertTrue(c["sujeto_a_aprobacion_del_asesor"])
        self.assertEqual(c["fijado_el"], "2026-09-30")
        ip = c["interpretacion_primaria"]
        self.assertEqual((ip["n"], ip["variante"], ip["umbral_pct"], ip["min_dominios"], ip["referencia"]), (100, "muestreo", 30.0, 10, "json_compact"))
        self.assertEqual(ip["tokenizadores"], TOKS)
        self.assertIn("ya eran conocidas", c["declaracion"])


if __name__ == "__main__":
    unittest.main()
