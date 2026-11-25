"""Estudio de formatos (experiments/estudio_formatos): cálculos de ver.py y cortes.py sobre datos fijos.

No llama a ningún modelo: ``resultados.json`` es sintético y ``respuesta.mini`` / ``respuesta.json`` son una pareja
de respuestas reales grabadas del estudio.
"""
from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import unittest
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
ESTUDIO = RAIZ / "experiments" / "estudio_formatos"
FIJOS = Path(__file__).resolve().parent / "fixtures" / "estudio_formatos"


def _modulo(nombre):
    spec = importlib.util.spec_from_file_location(f"estudio_formatos_{nombre}", ESTUDIO / f"{nombre}.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


ver = _modulo("ver")
cortes = _modulo("cortes")
medir = _modulo("medir")


class Ver(unittest.TestCase):
    def setUp(self):
        self.corridas = ver.cargar(FIJOS / "resultados.json")
        self.tarifas = ver.tarifas_por_proveedor(FIJOS / "tarifas.json", FIJOS / "proveedores.json")

    def fila(self, filas, prov, fmt):
        return next(f for f in filas if f["proveedor"] == prov and f["formato"] == fmt)

    def test_solo_cuentan_las_corridas_completas(self):
        self.assertEqual(len(self.corridas), 5)

    def test_wilson(self):
        lo, hi = ver.wilson(60, 60)
        self.assertAlmostEqual(lo, 0.9398, places=3)
        self.assertAlmostEqual(hi, 1.0)
        lo, hi = ver.wilson(40, 60)
        self.assertAlmostEqual(lo, 0.5406, places=3)
        self.assertAlmostEqual(hi, 0.7727, places=3)
        self.assertEqual(ver.wilson(0, 0), (0.0, 0.0))

    def test_percentil_por_rango_mas_cercano(self):
        self.assertEqual(ver.percentil([3.0, 1.0, 2.0], 95), 3.0)
        self.assertEqual(ver.percentil([1, 2, 3, 4, 5, 6, 7, 8, 9, 10], 50), 5)
        self.assertIsNone(ver.percentil([None], 95))

    def test_tokens_y_cambio_frente_a_json(self):
        f = self.fila(ver.tokens(self.corridas), "modelo-a", "mini")
        self.assertEqual(f["salida_generacion_media"], 500)
        self.assertEqual(f["salida_total_media"], 520)
        self.assertEqual(f["razonamiento_medio"], 100)
        self.assertAlmostEqual(f["cambio_vs_json_pct"], -50.0)
        self.assertIsNone(self.fila(ver.tokens(self.corridas), "modelo-b", "mini")["razonamiento_medio"])

    def test_validez_e_intervalo(self):
        f = self.fila(ver.validez(self.corridas), "modelo-a", "json")
        self.assertEqual((f["validos"], f["solicitados"], f["respuestas_completas"]), (20, 40, 1))
        self.assertAlmostEqual(f["validez_pct"], 50.0)
        self.assertLess(f["ic95_pct"][0], 50.0)
        self.assertGreater(f["ic95_pct"][1], 50.0)

    def test_reparacion_antes_y_despues(self):
        f = self.fila(ver.reparacion(self.corridas), "modelo-a", "mini")
        self.assertAlmostEqual(f["validez_antes_pct"], 97.5)
        self.assertAlmostEqual(f["validez_despues_pct"], 100.0)
        self.assertEqual((f["corridas_con_correccion"], f["tokens_correccion"]), (1, 40))

    def test_latencia(self):
        f = self.fila(ver.latencia(self.corridas), "modelo-a", "json")
        self.assertAlmostEqual(f["media_s"], 11.0)
        self.assertEqual(f["p95_s"], 12.0)
        self.assertAlmostEqual(f["corrida_completa_media_s"], 16.5)

    def test_costo_solo_con_tarifa_verificada(self):
        filas = ver.costo(self.corridas, self.tarifas)
        a_json = self.fila(filas, "modelo-a", "json")
        # 3 000 tokens × 10 USD/M / 40 válidos × 1 000
        self.assertAlmostEqual(a_json["usd_por_mil_validos"], 0.75)
        a_mini = self.fila(filas, "modelo-a", "mini")
        self.assertAlmostEqual(a_mini["usd_por_mil_validos"], 0.26)
        self.assertAlmostEqual(a_mini["cambio_vs_json_pct"], 100 * (0.26 / 0.75 - 1))
        b = self.fila(filas, "modelo-b", "mini")
        self.assertIsNone(b["usd_por_mil_validos"])
        self.assertEqual(b["tarifa_estado"], "no_verificada")

    def test_cli_tablas_y_json(self):
        args = ["--resultados", str(FIJOS / "resultados.json"), "--tarifas", str(FIJOS / "tarifas.json"),
                "--proveedores", str(FIJOS / "proveedores.json")]
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.assertEqual(ver.main(["todo"] + args), 0)
        texto = out.getvalue()
        for titulo in ("== tokens", "== validez", "== reparacion", "== latencia", "== costo", "no_verificada"):
            self.assertIn(titulo, texto)
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.assertEqual(ver.main(["validez", "--json"] + args), 0)
        self.assertEqual(len(json.loads(out.getvalue())), 3)

    def test_sin_tarifas_ni_entrada(self):
        t = ver.tarifas_por_proveedor(FIJOS / "no_existe.json", FIJOS / "proveedores.json")
        self.assertEqual(t["modelo-a"], (None, "sin entrada", None))


class Cortes(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.lector = cortes.LectorMini()
        cls.mini = (FIJOS / "respuesta.mini").read_text(encoding="utf-8")
        cls.json = (FIJOS / "respuesta.json").read_text(encoding="utf-8")

    def test_posiciones_dentro_del_texto(self):
        p = cortes.posiciones(2100)
        self.assertEqual(len(p), 20)
        self.assertEqual(p[0], 100)
        self.assertLess(p[-1], 2100)

    def test_fines_de_registro(self):
        self.assertEqual(len(self.lector.fines(self.mini)), 20)
        self.assertEqual(len(cortes.fines_json(self.json)), 20)

    def test_mini_recupera_los_registros_completos_y_json_estricto_ninguno(self):
        r = cortes.medir_par(self.mini, self.json, self.lector)
        self.assertGreater(r["mini"]["registros_completos"], 0)
        self.assertGreaterEqual(r["mini"]["recuperacion_pct"], 95.0)
        self.assertEqual(r["json"]["recuperados"], 0)
        self.assertEqual(r["json"]["recuperacion_pct"], 0.0)

    def test_corte_en_la_cabecera_no_entrega_registros(self):
        self.assertEqual(self.lector.recuperar(self.mini[:10]), [])

    def test_respuesta_completa_se_lee_entera(self):
        # con la señal de corte, la última línea solo se conserva si la respuesta terminó en un salto de línea
        completa = self.mini.rstrip("\n")
        self.assertEqual(len(self.lector.recuperar(completa + "\n")), 20)
        self.assertEqual(len(self.lector.recuperar(completa)), 19)
        self.assertEqual(len(cortes.leer_json_estricto(self.json)), 20)
        self.assertEqual(cortes.leer_json_estricto('{"a": 1}'), [])

    def test_cli_par_y_carpeta(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.assertEqual(cortes.main([str(FIJOS / "respuesta.mini"), str(FIJOS / "respuesta.json")]), 0)
        self.assertIn("JSON (json.loads): 0 de", out.getvalue())
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.assertEqual(cortes.main(["--todas", str(ESTUDIO / "corridas"), "--json-salida"]), 0)
        res = json.loads(out.getvalue())
        # las 9 parejas del estudio entran en el denominador; ninguna se omite
        self.assertEqual((res["parejas"], res["procesadas"], res["no_procesadas"]), (9, 9, 0))
        self.assertEqual(res["cortes_por_formato"], 180)
        self.assertEqual(len(res["detalle"]), 9)
        self.assertGreaterEqual(res["total"]["mini"]["recuperacion_pct"], 95.0)
        self.assertEqual(res["total"]["json"]["recuperados"], 0)
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.assertEqual(cortes.main(["--todas", str(ESTUDIO / "corridas")]), 0)
        self.assertIn("Parejas procesadas: 9 de 9 · 180 cortes por formato", out.getvalue())

    def test_la_pareja_corregida_se_corta_tras_aplicar_la_correccion_grabada(self):
        res = cortes.medir_todas(ESTUDIO / "corridas", self.lector)
        haiku2 = next(f for f in res["detalle"] if f["proveedor"] == "claude-haiku-5-5" and f["repeticion"] == "2")
        self.assertEqual(haiku2["estado"], "procesada")
        self.assertIn("respuesta_2_correccion.txt", haiku2["referencia"]["mini"])
        self.assertEqual(haiku2["referencia"]["json"], "primera respuesta")
        texto, _ = cortes.referencia_mini(ESTUDIO / "corridas" / "claude-haiku-5-5" / "mini" / "2", self.lector)
        self.assertEqual(len(self.lector.completo(texto)), 20)

    def test_una_pareja_que_no_se_puede_procesar_se_informa(self):
        import shutil
        import tempfile
        with tempfile.TemporaryDirectory() as t:
            destino = Path(t) / "corridas"
            shutil.copytree(ESTUDIO / "corridas" / "claude-opus-5-5", destino / "claude-opus-5-5")
            (destino / "claude-opus-5-5" / "json" / "2" / "respuesta_1.json").write_text("[{", encoding="utf-8")
            res = cortes.medir_todas(destino, self.lector)
            self.assertEqual((res["parejas"], res["procesadas"], res["no_procesadas"]), (3, 2, 1))
            fallida = next(f for f in res["detalle"] if f["estado"] == "no procesada")
            self.assertEqual(fallida["repeticion"], "2")
            self.assertTrue(fallida["motivo"])
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                self.assertEqual(cortes.main(["--todas", str(destino)]), 0)
            self.assertIn("NO PROCESADA", out.getvalue())
            self.assertIn("Parejas procesadas: 2 de 3", out.getvalue())

    def test_correcciones_insuficientes(self):
        primera = self.mini.replace("ticket|", "otro|", 1)
        with self.assertRaises(ValueError):
            self.lector.aplicar_correcciones(primera, ["texto que no corrige nada"])


class Medir(unittest.TestCase):
    def test_validar_json_con_el_contrato_de_la_aplicacion(self):
        app = medir.cargar_app()
        bien = (FIJOS / "respuesta.json").read_text(encoding="utf-8")
        r = medir.validar_json(bien, app)
        self.assertEqual((r["leido"], r["validos"], r["error"]), (True, 20, None))
        datos = json.loads(bien)
        datos[2]["id"] = "3"
        r = medir.validar_json(json.dumps(datos), app)
        self.assertEqual(r["validos"], 19)
        self.assertIn("[3]", r["error"])
        r = medir.validar_json(json.dumps(datos[:5]).replace("]", ""), app)
        self.assertEqual((r["leido"], r["validos"]), (False, 0))

    def test_validos_mini_con_ajustes_locales(self):
        import tempfile
        with tempfile.TemporaryDirectory() as t:
            wf = medir.nueva_toolkit(Path(t) / "kit")
            texto = (FIJOS / "respuesta.mini").read_text(encoding="utf-8")
            self.assertEqual(medir.validos_mini("```mini\n" + texto + "```\n", wf)["validos"], 20)
            self.assertEqual(medir.validos_mini("# Título\n" + texto, wf)["validos"], 0)

    def test_corridas_grabadas_completas(self):
        doc = json.loads((ESTUDIO / "corridas" / "resultados.json").read_text(encoding="utf-8"))
        self.assertEqual(len(doc["corridas"]), 18)
        self.assertTrue(all(c["estado"] == "completa" for c in doc["corridas"]))
        for c in doc["corridas"]:
            for llamada in c["llamadas"]:
                self.assertTrue((ESTUDIO / "corridas" / c["carpeta"] / llamada["archivo"]).is_file())


if __name__ == "__main__":
    unittest.main()
