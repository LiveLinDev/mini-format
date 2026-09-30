"""Economía: vectores dorados, oráculo independiente con Decimal y paridad con el espejo JS.

El oráculo NO reutiliza la lógica de ``experiments/economia/calculo.py``: recalcula con
``decimal.Decimal`` (ROUND_HALF_UP) y, para el punto de equilibrio, por FUERZA BRUTA sobre k
(el código usa una fórmula cerrada), de modo que un error en la fórmula se detecte.
"""
from __future__ import annotations

import json
import random
import shutil
import subprocess
import sys
import unittest
from decimal import ROUND_HALF_UP, Decimal, getcontext
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "experiments" / "economia"))

import calculo as C  # noqa: E402

getcontext().prec = 120
VECTORES = ROOT / "evidencia" / "vectores" / "economia.json"
SITIO_JS = ROOT / "sitio" / "economia-calculo.js"
Q6 = Decimal("0.000001")
Q9 = Decimal("0.000000000")
Q4 = Decimal("0.0001")


def d(x) -> Decimal:
    return Decimal(str(x))


def q(x: Decimal, exp: Decimal) -> str:
    return format(x.quantize(exp, rounding=ROUND_HALF_UP), "f")


def _vectores():
    return json.loads(VECTORES.read_text(encoding="utf-8"))["vectores"]


def _tarifa(pin="0.75", pca="0.075", pce=None, pout="4.5", estado="verificada"):
    return {"proveedor": "P", "modelo_api_id": "m", "moneda": "USD", "entrada_sin_cache_por_millon": pin,
            "entrada_cache_lectura_por_millon": pca, "entrada_cache_escritura_por_millon": pce,
            "salida_por_millon": pout, "estado": estado}


def _usage(es=0, cl=0, ce=0, sal=0, raz=0, incl=True):
    return {"entrada_sin_cache": es, "entrada_cache_lectura": cl, "entrada_cache_escritura": ce, "salida": sal,
            "razonamiento": raz, "razonamiento_incluido_en_salida": incl}


def _sol(id_, usages, **extra):
    s = {"id": id_, "intentos": [{"fase": "generacion", "modelo": "m", "proveedor": "P", "usage": u} for u in usages]}
    s.update(extra)
    return s


class VectoresDorados(unittest.TestCase):
    def test_todos_los_vectores(self):
        vs = _vectores()
        self.assertGreaterEqual(len(vs), 60)
        ids = [v["id"] for v in vs]
        self.assertEqual(len(ids), len(set(ids)), "ids repetidos")
        for v in vs:
            with self.subTest(v["id"]):
                if v.get("error"):
                    with self.assertRaises((ValueError, TypeError)):
                        C.ejecutar(v["operacion"], v["entrada"])
                else:
                    self.assertEqual(C.ejecutar(v["operacion"], v["entrada"]), v["salida"])

    def test_casos_dificiles_presentes(self):
        """Los vectores obligatorios del encargo no pueden desaparecer del archivo."""
        ids = {v["id"] for v in _vectores()}
        for oblig in ("razon_sin_ahorro", "total_cero_validos", "solicitud_categorias_sin_solape_razonamiento_incluido",
                      "solicitud_razonamiento_aparte", "solicitud_cache_lectura_y_escritura", "solicitud_tarifa_no_verificada",
                      "equilibrio_inexistente", "redondeo_limite_half_up", "escenario_a_solo_salida",
                      "escenario_b_perfiles_1000_usd", "equilibrio_empate_exacto_no_es_ahorro"):
            self.assertIn(oblig, ids)

    def test_las_salidas_doradas_no_contienen_float(self):
        def recorre(x):
            if isinstance(x, float):
                self.fail(f"float en una salida dorada: {x}")
            elif isinstance(x, dict):
                for y in x.values():
                    recorre(y)
            elif isinstance(x, list):
                for y in x:
                    recorre(y)
        for v in _vectores():
            if "salida" in v:
                recorre(v["salida"])


class RedondeoYRazon(unittest.TestCase):
    def test_half_up_no_es_bancario(self):
        self.assertEqual(C.fmt(C.a_fraccion("0.0000005"), 6), "0.000001")
        self.assertEqual(C.fmt(C.a_fraccion("0.0000015"), 6), "0.000002")   # el redondeo al par daria 0.000002 y 0.000000 en el otro
        self.assertEqual(C.fmt(C.a_fraccion("0.0000025"), 6), "0.000003")   # half-even daria 0.000002
        self.assertEqual(C.fmt(C.a_fraccion("-2.5"), 0), "-3")
        self.assertEqual(C.fmt(C.a_fraccion("-0.0000004"), 6), "0.000000")

    def test_razon_y_ahorro_contra_decimal(self):
        rng = random.Random(7)
        for _ in range(300):
            tj = rng.randint(1, 5000)
            tm = rng.randint(0, 9000)
            r = C.razon_y_ahorro(tm, tj)
            rr = d(tm) / d(tj)
            self.assertEqual(r["razon"], q(rr, Q6))
            self.assertEqual(r["ahorro_salida_pct"], q(100 * (1 - rr), Q4))
            self.assertEqual(r["hay_ahorro"], tm < tj)

    def test_json_cero_no_definido(self):
        r = C.razon_y_ahorro(5, 0)
        self.assertIsNone(r["razon"])
        self.assertIsNone(r["ahorro_salida_pct"])
        self.assertEqual(r["estado"], "no_definido")

    def test_float_rechazado(self):
        with self.assertRaises(TypeError):
            C.a_fraccion(0.1)
        with self.assertRaises(TypeError):
            C.razon_y_ahorro(1.5, 3)


class CostoPorCategorias(unittest.TestCase):
    def test_contra_oraculo_decimal_aleatorio(self):
        rng = random.Random(20260930)
        precios = ["0", "0.075", "0.1", "0.25", "0.75", "1.25", "2", "4.5", "10", "25.5"]
        for i in range(400):
            pin, pca, pce, pout = (rng.choice(precios) for _ in range(4))
            t = _tarifa(pin, pca, pce, pout)
            n_int = rng.randint(1, 3)
            usages, esperado_total = [], Decimal(0)
            cat = {k: Decimal(0) for k in C.CATEGORIAS}
            for _j in range(n_int):
                incl = rng.choice([True, False])
                sal = rng.randint(0, 3000)
                raz = rng.randint(0, sal) if incl else rng.randint(0, 2000)
                u = _usage(rng.randint(0, 5000), rng.randint(0, 5000), rng.randint(0, 5000), sal, raz, incl)
                u["otros_usd"] = {"x": "0.000123"}
                usages.append(u)
                cat["entrada_sin_cache"] += d(u["entrada_sin_cache"]) * d(pin) / 10**6
                cat["entrada_cache_lectura"] += d(u["entrada_cache_lectura"]) * d(pca) / 10**6
                cat["entrada_cache_escritura"] += d(u["entrada_cache_escritura"]) * d(pce) / 10**6
                cat["salida"] += d(sal) * d(pout) / 10**6
                if not incl:
                    cat["razonamiento"] += d(raz) * d(pout) / 10**6
                cat["otros"] += d("0.000123")
            esperado_total = sum(cat.values())
            r = C.costo_solicitud(_sol("s", usages), [t])
            self.assertEqual(r["estado"], "calculado", i)
            for k in C.CATEGORIAS:
                self.assertEqual(r["categorias"][k], q(cat[k], Q6), (i, k))
            self.assertEqual(r["costo_usd"], q(esperado_total, Q6), i)

    def test_sin_doble_conteo_del_razonamiento(self):
        t = _tarifa(pin="0", pca="0", pout="10")
        dentro = C.costo_solicitud(_sol("a", [_usage(0, 0, 0, 1000, 400, True)]), [t])
        aparte = C.costo_solicitud(_sol("b", [_usage(0, 0, 0, 1000, 400, False)]), [t])
        self.assertEqual(dentro["costo_usd"], "0.010000")                 # 1000 x 10 / 1e6
        self.assertEqual(dentro["categorias"]["razonamiento"], "0.000000")  # ya va dentro de salida
        self.assertEqual(aparte["costo_usd"], "0.014000")                 # + 400 x 10 / 1e6
        self.assertEqual(aparte["categorias"]["razonamiento"], "0.004000")

    def test_categorias_no_solapadas_suman_el_total(self):
        t = _tarifa(pin="2", pca="0.2", pce="2.5", pout="10")
        r = C.costo_solicitud(_sol("s", [_usage(1000, 4000, 2000, 500, 0, False)]), [t])
        partes = sum(d(v) for v in r["categorias"].values())
        self.assertEqual(d(r["costo_usd"]), partes)
        self.assertEqual(r["costo_usd"], "0.012800")  # 0.002 + 0.0008 + 0.005 + 0.005

    def test_tarifa_no_verificada_es_none_con_motivo(self):
        r = C.costo_solicitud(_sol("s", [_usage(10, 0, 0, 10)]), [_tarifa(estado="no_verificada", pin=None, pca=None, pout=None)])
        self.assertIsNone(r["costo_usd"])
        self.assertEqual(r["estado"], "tarifa_no_verificada")
        self.assertIn("tarifa no verificada", r["motivo"])
        self.assertIsNone(r["categorias"])

    def test_modelo_sin_tarifa_no_inventa_precio(self):
        r = C.costo_solicitud({"id": "s", "intentos": [{"fase": "generacion", "modelo": "otro", "proveedor": "Q", "usage": _usage(1, 0, 0, 1)}]}, [_tarifa()])
        self.assertIsNone(r["costo_usd"])
        self.assertEqual(r["estado"], "tarifa_no_verificada")

    def test_usage_ausente_es_no_informado_no_cero(self):
        u = _usage(10, None, None, 10)
        r = C.costo_solicitud(_sol("s", [u]), [_tarifa()])
        self.assertEqual(r["estado"], "usage_no_informado")
        self.assertIsNone(r["costo_usd"])
        # si la tarifa no publica precio de esa categoria, null equivale a 'no se usa'
        r2 = C.costo_solicitud(_sol("s", [u]), [_tarifa(pca=None, pce=None)])
        self.assertEqual(r2["estado"], "calculado")

    def test_precio_cero_verificado_no_es_precio_ausente(self):
        t = _tarifa(pin="0", pca="0", pout="0")
        r = C.costo_solicitud(_sol("s", [_usage(100, 0, 0, 100)]), [t])
        self.assertEqual(r["costo_usd"], "0.000000")
        self.assertEqual(r["estado"], "calculado")

    def test_busqueda_por_proveedor_y_modelo(self):
        ts = [_tarifa(), dict(_tarifa(), proveedor="Q", modelo_api_id="z", alias=["z-latest"])]
        self.assertIsNotNone(C.buscar_tarifa(ts, "p", "m"))
        self.assertIsNotNone(C.buscar_tarifa(ts, "Q", "z-latest"))
        self.assertIsNone(C.buscar_tarifa(ts, "Q", "m"))
        self.assertIsNone(C.buscar_tarifa(ts, "P", "M"))  # el id de modelo es exacto


class CostoTotalYPor1000(unittest.TestCase):
    def test_reparaciones_incluidas_y_agrupadas_por_original(self):
        t = _tarifa()
        orig = _sol("g1", [_usage(1000, 0, 0, 400)], registros_solicitados=10, registros_validos_finales=10)
        rep = _sol("g1-rep", [_usage(300, 0, 0, 60)], grupo="g1", registros_solicitados=2, registros_validos_finales=2)
        r = C.costo_total([orig, rep], [t])
        self.assertEqual(len(r["grupos"]), 1)
        self.assertEqual(r["grupos"][0]["n_solicitudes"], 2)
        esperado = (d(1000) + d(300)) * d("0.75") / 10**6 + (d(400) + d(60)) * d("4.5") / 10**6
        self.assertEqual(r["costo_total_usd"], q(esperado, Q6))
        # los validos son los de la ORIGINAL: no 10 + 2
        self.assertEqual(r["registros_validos_finales"], "10")
        self.assertEqual(r["costo_por_1000_validos"]["costo_por_1000_validos_usd"], q(1000 * esperado / 10, Q6))

    def test_cero_validos_no_definido_e_informa_costo(self):
        t = _tarifa()
        r = C.costo_total([_sol("g", [_usage(1000, 0, 0, 400)], registros_solicitados=10, registros_validos_finales=0)], [t])
        p = r["costo_por_1000_validos"]
        self.assertIsNone(p["costo_por_1000_validos_usd"])
        self.assertEqual(p["estado"], "no_definido")
        self.assertEqual(p["costo_incurrido_usd"], r["costo_total_usd"])
        self.assertNotEqual(p["costo_incurrido_usd"], "0.000000")

    def test_validos_no_informados_no_se_suponen_cero(self):
        r = C.costo_total([_sol("g", [_usage(10, 0, 0, 10)], registros_solicitados=10)], [_tarifa()])
        self.assertIsNone(r["registros_validos_finales"])
        self.assertIsNone(r["costo_por_1000_validos"]["costo_por_1000_validos_usd"])

    def test_total_con_tarifa_faltante_no_es_total(self):
        ok = _sol("a", [_usage(1000, 0, 0, 400)], registros_validos_finales=5)
        mal = {"id": "b", "registros_validos_finales": 5, "intentos": [{"fase": "generacion", "modelo": "x", "proveedor": "Q", "usage": _usage(1, 0, 0, 1)}]}
        r = C.costo_total([ok, mal], [_tarifa()])
        self.assertIsNone(r["costo_total_usd"])
        self.assertEqual(r["estado"], "tarifa_no_verificada")
        self.assertIsNotNone(r["costo_parcial_verificado_usd"])   # cota inferior etiquetada, no total
        self.assertIsNone(r["costo_por_1000_validos"]["costo_por_1000_validos_usd"])

    def test_grupo_ambiguo_lanza(self):
        with self.assertRaises(ValueError):
            C.costo_total([{"id": "a", "grupo": "x", "registros_validos_finales": 1, "intentos": []},
                           {"id": "b", "grupo": "x", "registros_validos_finales": 2, "intentos": []}], [_tarifa()])

    def test_orden_de_grupos_es_el_de_primera_aparicion(self):
        r = C.costo_total([_sol("10", [_usage(1)]), _sol("2", [_usage(1)]), _sol("1", [_usage(1)])], [_tarifa()])
        self.assertEqual([g["grupo"] for g in r["grupos"]], ["10", "2", "1"])


class Escenarios(unittest.TestCase):
    def test_escenario_a_es_proyeccion(self):
        t = _tarifa(pout="4.5")
        r = C.escenario_a({"tarifa": t, "t_mini": 650, "t_json": 1000})
        self.assertEqual(r["tipo"], "proyeccion")
        self.assertIn("no es la respuesta real", r["aviso_es"])
        self.assertEqual(r["tokens_json_referencia"], "1000000")
        self.assertEqual(r["solo_salida"]["costo_json_usd"], "4.500000")     # 1e6 x 4.5 / 1e6
        self.assertEqual(r["solo_salida"]["costo_mini_usd"], "2.925000")     # 650000 x 4.5 / 1e6
        self.assertEqual(r["solo_salida"]["ahorro_usd"], "1.575000")
        self.assertEqual(r["solo_salida"]["ahorro_pct"], "35.0000")

    def test_escenario_a_sin_ahorro_lo_dice(self):
        r = C.escenario_a({"tarifa": _tarifa(), "t_mini": 1200, "t_json": 1000})
        self.assertFalse(r["solo_salida"]["hay_ahorro"])
        self.assertTrue(r["solo_salida"]["ahorro_usd"].startswith("-"))

    def test_escenario_a_tarifa_no_verificada(self):
        r = C.escenario_a({"tarifa": _tarifa(estado="no_verificada", pin=None, pca=None, pout=None), "t_mini": 650, "t_json": 1000})
        self.assertIsNone(r["solo_salida"]["costo_json_usd"])
        self.assertEqual(r["solo_salida"]["estado"], "tarifa_no_verificada")

    def test_escenario_b_contra_oraculo(self):
        rng = random.Random(11)
        for _ in range(200):
            presupuesto = rng.choice(["1000", "10", "250.50"])
            costo = Decimal(rng.randint(1, 900000)) / Decimal(10**6)
            rv = Decimal(rng.randint(0, 5000)) / Decimal(100)
            tok = rng.randint(1, 5000)
            r = C.escenario_b({"presupuesto_usd": presupuesto, "alternativas": [
                {"nombre": "A", "costo_lote_usd": format(costo, "f"), "tokens_salida_por_lote": str(tok), "registros_validos_por_lote": format(rv, "f")}]})
            fila = r["alternativas"][0]
            lotes = int(d(presupuesto) / costo)   # trunc = floor para positivos
            self.assertEqual(fila["lotes"], str(lotes))
            self.assertEqual(fila["registros_utiles"], str(int(lotes * rv)))
            self.assertEqual(fila["tokens_salida_capacidad"], str(lotes * tok))
            self.assertLessEqual(d(fila["gasto_usd"]), d(presupuesto))

    def test_escenario_b_es_ilustrativo(self):
        r = C.escenario_b({"presupuesto_usd": "1000", "alternativas": [{"nombre": "A", "costo_lote_usd": "1", "registros_validos_por_lote": "1"}]})
        self.assertTrue(r["presupuesto_ilustrativo"])
        self.assertIn("no autoriza gastar", r["aviso_es"])
        self.assertEqual(r["presupuesto_usd"], "1000.00")

    def test_escenario_b_cero_validos_medidos_da_cero_utiles_y_sin_pct(self):
        r = C.escenario_b({"presupuesto_usd": "10", "alternativas": [
            {"nombre": "A", "costo_lote_usd": "1", "registros_validos_por_lote": "0"},
            {"nombre": "B", "costo_lote_usd": "1", "registros_validos_por_lote": "5"}]})
        self.assertEqual(r["alternativas"][0]["registros_utiles"], "0")
        self.assertIsNone(r["comparacion"][0]["registros_utiles_vs_referencia_pct"])   # dividir por 0 utiles no esta definido

    def test_escenario_b_no_compara_tokens_como_trabajo(self):
        """La capacidad se mide en registros utiles por lote, no en tokens: un formato con menos
        tokens pero menos validos por lote puede rendir menos registros utiles."""
        r = C.escenario_b({"presupuesto_usd": "100", "alternativas": [
            {"nombre": "JSON", "costo_lote_usd": "0.01", "tokens_salida_por_lote": "1000", "registros_validos_por_lote": "25"},
            {"nombre": "mini", "costo_lote_usd": "0.0075", "tokens_salida_por_lote": "700", "registros_validos_por_lote": "15"}]})
        a, b = r["alternativas"]
        # 10000 lotes x 25 = 250000 frente a floor(100 / 0.0075) = 13333 lotes x 15 = 199995
        self.assertEqual((a["registros_utiles"], b["registros_utiles"]), ("250000", "199995"))
        self.assertEqual(r["comparacion"][0]["registros_utiles_vs_referencia_pct"], "-20.0020")  # 100 x (199995/250000 - 1)


def _costo_fuerza_bruta(perfil, tarifa, k):
    """Costo de un lote de k registros, recalculado con Decimal (sin la forma lineal del código)."""
    pin = d(tarifa["entrada_sin_cache_por_millon"])
    pout = d(tarifa["salida_por_millon"])
    pca = d(tarifa["entrada_cache_lectura_por_millon"])
    pinstr = pca if perfil.get("instruccion_en_cache") else pin
    entrada = (d(perfil.get("tokens_instruccion", 0)) * pinstr + d(k) * d(perfil.get("tokens_entrada_por_registro", 0)) * pin) / 10**6
    salida = (d(perfil.get("tokens_salida_por_registro", 0)) * k + d(perfil.get("tokens_salida_fijos", 0))) * pout / 10**6
    return entrada + salida + d(perfil.get("reintentos_por_lote", 0)) * (entrada + d(perfil.get("fraccion_reparada", 1)) * salida)


class PuntoDeEquilibrio(unittest.TestCase):
    def test_contra_fuerza_bruta(self):
        rng = random.Random(99)
        t = _tarifa(pin="1", pca="0.1", pout="4")
        for i in range(300):
            pj = {"tokens_instruccion": rng.randint(0, 600), "tokens_salida_por_registro": str(rng.randint(1, 30)),
                  "tokens_salida_fijos": rng.randint(0, 8), "reintentos_por_lote": rng.choice(["0", "0.1", "0.25"]),
                  "fraccion_reparada": "1", "instruccion_en_cache": rng.random() < 0.3}
            pm = {"tokens_instruccion": rng.randint(0, 900), "tokens_salida_por_registro": str(rng.randint(1, 30)),
                  "tokens_salida_fijos": rng.randint(0, 8), "reintentos_por_lote": rng.choice(["0", "0.05"]),
                  "fraccion_reparada": rng.choice(["0.1", "1"]), "instruccion_en_cache": rng.random() < 0.3}
            r = C.punto_equilibrio({"tarifa": t, "perfil_json": pj, "perfil_mini": pm})["total"]
            ahorra = [k for k in range(1, 4001) if _costo_fuerza_bruta(pj, t, k) - _costo_fuerza_bruta(pm, t, k) > 0]
            if not ahorra:
                self.assertEqual(r["estado"], "sin_ahorro_neto", (i, pj, pm))
                self.assertIsNone(r["k_minimo"])
                self.assertIn("No hay ahorro neto", r["mensaje_es"])
            else:
                self.assertEqual(r["k_minimo"], str(ahorra[0]), (i, pj, pm))
                if r["k_maximo"] is not None:
                    self.assertEqual(r["k_maximo"], str(ahorra[-1]), (i, pj, pm))
                    self.assertEqual(r["estado"], "solo_hasta_k")
                else:
                    self.assertEqual(ahorra[-1], 4000, (i, pj, pm))   # sin tope: ahorra hasta el limite buscado
                    self.assertEqual(ahorra, list(range(ahorra[0], 4001)))
                    self.assertIn(r["estado"], ("siempre_ahorra", "desde_k"))

    def test_empate_exacto_no_cuenta_como_ahorro(self):
        t = _tarifa(pin="1", pca="0.1", pout="4")
        r = C.punto_equilibrio({"tarifa": t, "perfil_json": {"tokens_instruccion": 100, "tokens_salida_por_registro": "10"},
                                "perfil_mini": {"tokens_instruccion": 420, "tokens_salida_por_registro": "6"}})["total"]
        self.assertEqual(r["k_equilibrio_exacto"], "20.0000")
        self.assertEqual(r["k_minimo"], "21")        # en k = 20 los costos son iguales

    def test_sin_ahorro_neto_se_dice_explicitamente(self):
        t = _tarifa(pin="1", pca="0.1", pout="4")
        p = {"tokens_instruccion": 100, "tokens_salida_por_registro": "10"}
        r = C.punto_equilibrio({"tarifa": t, "perfil_json": p, "perfil_mini": p})
        for variante in ("solo_salida", "total"):
            self.assertEqual(r[variante]["estado"], "sin_ahorro_neto")
            self.assertIn("No hay ahorro neto", r[variante]["mensaje_es"])
            self.assertIn("no net saving", r[variante]["mensaje_en"])

    def test_tarifa_no_verificada(self):
        r = C.punto_equilibrio({"tarifa": _tarifa(estado="no_verificada", pin=None, pca=None, pout=None),
                                "perfil_json": {"tokens_salida_por_registro": "10"}, "perfil_mini": {"tokens_salida_por_registro": "5"}})
        self.assertEqual(r["total"]["estado"], "tarifa_no_verificada")
        self.assertIsNone(r["total"].get("k_minimo"))


class ParidadConJavaScript(unittest.TestCase):
    """Entradas aleatorias: Python y el espejo JS deben producir el mismo JSON (si hay Node)."""

    @unittest.skipUnless(shutil.which("node"), "node no está disponible")
    def test_paridad_aleatoria(self):
        rng = random.Random(4242)
        t = _tarifa("0.75", "0.075", "0.9375", "4.5")
        casos = []
        for i in range(120):
            tipo = i % 4
            pj = {"tokens_instruccion": rng.randint(0, 600), "tokens_salida_por_registro": str(rng.randint(1, 30)) + rng.choice(["", ".5", ".25"]),
                  "tokens_salida_fijos": rng.randint(0, 8), "reintentos_por_lote": rng.choice(["0", "0.1", "0.25"]),
                  "fraccion_validos": rng.choice(["1", "0.97"]), "instruccion_en_cache": rng.random() < 0.3}
            pm = dict(pj, tokens_instruccion=rng.randint(0, 900), tokens_salida_por_registro=str(rng.randint(1, 30)),
                      fraccion_reparada="0.1", instruccion_en_cache=rng.random() < 0.3)
            if tipo == 0:
                casos.append(["punto_equilibrio", {"tarifa": t, "perfil_json": pj, "perfil_mini": pm, "k_referencia": rng.randint(1, 120)}])
            elif tipo == 1:
                casos.append(["escenario_b", {"presupuesto_usd": "1000", "k": rng.randint(1, 100), "tarifa": t,
                                               "alternativas": [{"nombre": "J", "perfil": pj}, {"nombre": "M", "perfil": pm}]}])
            elif tipo == 2:
                casos.append(["escenario_a", {"tarifa": t, "t_mini": rng.randint(0, 9000), "t_json": rng.randint(0, 9000),
                                               "total": {"k": rng.randint(1, 100), "perfil_json": pj, "perfil_mini": pm}}])
            else:
                u = _usage(rng.randint(0, 9000), rng.randint(0, 9000), rng.randint(0, 9000), rng.randint(500, 9000), rng.randint(0, 400), rng.random() < .5)
                casos.append(["costo_total", {"solicitudes": [_sol("s1", [u, u], registros_validos_finales=rng.randint(0, 50)),
                                                              _sol("s2", [u], grupo="s1")], "tarifas": [t]}])
        esperado = [C.ejecutar(op, e) for op, e in casos]
        runner = (
            "const E=require(process.argv[1]);const c=JSON.parse(require('fs').readFileSync(0,'utf8'));"
            "process.stdout.write(JSON.stringify(c.map(([op,e])=>E.ejecutar(op,e))));"
        )
        r = subprocess.run(["node", "-e", runner, str(SITIO_JS)], input=json.dumps(casos), capture_output=True, text=True, encoding="utf-8", timeout=120)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(json.loads(r.stdout), esperado)


if __name__ == "__main__":
    unittest.main()
