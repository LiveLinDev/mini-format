"""V1: la reversibilidad objeto -> texto -> objeto se comprueba ANTES de contar tokens.

El oráculo es independiente del código bajo prueba: los textos se corrompen a mano (se cambia
un valor, un tipo o un metadato) y cada verificador debe declararlos ``no_reversible``; los
objetos de partida salen de ``benchmark/domains.py`` y se comparan con su copia profunda.
"""
from __future__ import annotations

import copy
import json
import shutil
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
for _p in ("src", "benchmark", "benchmark/public", "experiments", "experiments/v1_tokens"):
    sys.path.insert(0, str(ROOT / _p))

try:
    import yaml  # noqa: F401
    import tiktoken  # noqa: F401
    HAY_DEPENDENCIAS = shutil.which("node") is not None
except ImportError:  # pragma: no cover
    HAY_DEPENDENCIAS = False

if HAY_DEPENDENCIAS:
    import comun as C
    import reversibilidad as R
    from minifmt import Registry


@unittest.skipUnless(HAY_DEPENDENCIAS, "requiere PyYAML, tiktoken y node")
class ReversibilidadTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.reg = Registry.load(ROOT / "forks")

    def doc(self, p, n=4):
        return C.generar(p, n, "ciclo"), self.reg.get(p)

    # ------------------------------------------------------------- aceptación
    def test_los_ocho_formatos_y_los_tres_comparadores_son_reversibles_salvo_csv_sin_metadatos(self):
        for p in ("a", "card", "cls", "map", "log"):
            d, c = self.doc(p)
            original = copy.deepcopy(d)
            ser = C.serializar_todos([d], c)
            textos = [{f: t for f, (t, _) in s.items()} for s in ser]
            res = R.verificar_lote([d], textos, c)[0]
            self.assertEqual(d, original, "la verificación no debe mutar el objeto")
            for f, r in res.items():
                if f == "csv":
                    self.assertEqual(r.estado, "no_reversible", f"{p}: el CSV sin metadatos no puede ser reversible")
                    self.assertIn("metadatos", r.causa)
                else:
                    self.assertTrue(r.aceptado, f"{p}/{f}: {r.estado} {r.causa}")
            ext = R.comparadores_reversibles([d], c)[0]
            for nombre, e in ext.items():
                self.assertTrue(e["resultado"].aceptado, f"{p}/{nombre}: {e['resultado'].causa}")

    def test_mini_declara_las_normalizaciones_que_aplica(self):
        d, c = self.doc("a", 3)
        from minifmt import dumps
        r = R.verificar_mini(d, dumps(d, c), c)
        self.assertEqual(r.estado, "reversible_normalizado")
        self.assertTrue(any("header.n" in x for x in r.normalizaciones))

    # ----------------------------------------------------------------- rechazo
    def test_json_y_yaml_detectan_un_valor_cambiado(self):
        d, _ = self.doc("card", 3)
        malo = copy.deepcopy(d)
        malo["cards"][1]["ease"] = 9.9
        self.assertEqual(R.verificar_json(d, json.dumps(malo)).estado, "no_reversible")
        import yaml as y
        self.assertEqual(R.verificar_yaml(d, y.safe_dump(malo, allow_unicode=True)).estado, "no_reversible")
        self.assertIn("$/cards/1/ease", R.verificar_json(d, json.dumps(malo)).causa)

    def test_un_booleano_no_equivale_a_un_numero(self):
        self.assertEqual(R.comparar({"x": True}, {"x": 1}).estado, "no_reversible")
        self.assertEqual(R.comparar({"x": 1}, {"x": 1.0}).estado, "reversible")
        self.assertEqual(R.comparar({"x": None}, {}).estado, "reversible_normalizado")
        self.assertEqual(R.comparar({"x": [1, 2]}, {"x": [1]}).estado, "no_reversible")

    def test_xml_con_contrato_detecta_un_tipo_o_un_valor_alterado(self):
        d, c = self.doc("a", 2)
        texto = C.serializar_todos([d], c)[0]["xml"][0]
        self.assertTrue(R.verificar_xml_contrato(d, texto, c).aceptado)
        roto = texto.replace("<difficulty>1</difficulty>", "<difficulty>2</difficulty>", 1)
        self.assertNotEqual(roto, texto)
        self.assertEqual(R.verificar_xml_contrato(d, roto, c).estado, "no_reversible")
        self.assertEqual(R.verificar_xml_contrato(d, "<a><rec>", c).estado, "no_reversible")

    def test_csv_con_esquema_y_xml_tipado_detectan_alteraciones(self):
        d, c = self.doc("cat", 3)
        e = R.comparadores_reversibles([d], c)[0]
        texto = e["csv_rev:celdas"]["texto"]
        self.assertTrue(e["csv_rev:celdas"]["resultado"].aceptado)
        # mismo texto con el metadato del envoltorio borrado: ya no se puede reconstruir el documento
        sin_meta = "\n".join(l for l in texto.split("\n") if not l.startswith("#meta "))
        import baselines as B
        with self.assertRaises(Exception):
            B.csv_decode(sin_meta, json.loads(e["csv_rev:celdas"]["mapa"]))
        xt = e["xml_tipado"]["texto"]
        self.assertEqual(R.verificar_xml_tipado(d, xt.replace("<number>", "<str>", 1)).estado, "no_reversible")

    def test_toon_estricto_y_mini_detectan_texto_dañado(self):
        d, c = self.doc("a", 3)
        toon = C.serializar_todos([d], c)[0]["toon"][0]
        dec = R.decodificar_toon_lote([toon, toon + "\n  basura: [", ])
        self.assertTrue(R.verificar_toon(d, dec[0]).aceptado)
        self.assertEqual(R.verificar_toon(d, dec[1]).estado, "no_reversible")
        from minifmt import dumps
        texto = dumps(d, c)
        lineas = texto.split("\n")
        lineas[2] = lineas[2].replace("|", "¦", 1)
        self.assertEqual(R.verificar_mini(d, "\n".join(lineas), c).estado, "no_reversible")

    def test_cada_dominio_declara_csv_no_reversible_con_su_causa(self):
        for p in self.reg.contracts:
            d, c = self.doc(p, 2)
            texto = C.serializar_todos([d], c)[0]["csv"][0]
            r = R.verificar_csv_contrato(d, texto, c)
            self.assertEqual(r.estado, "no_reversible", p)
            self.assertIn("descarta los metadatos", r.causa)
            self.assertEqual(r.detalle["registros"][:10], "reversible", f"{p}: los registros sí deben reconstruirse")


if __name__ == "__main__":
    unittest.main()
