"""V5 (a) y (c): propiedades con Hypothesis y oráculo independiente.

Para cada objeto canónico generado (por familia oficial y por contrato generado al azar) se comprueba:

1. ``parse(dumps(o)) == o`` (SPEC §9) con tipos exactos (entero, decimal y fecha como cadena...).
2. ``dumps(parse(t)) == t`` para el texto ``t`` emitido por el serializador (estabilidad, §9).
3. El decodificador independiente (conformance/oraculo, escrito desde la gramática de la SPEC y sin importar
   minifmt) lee ``t`` y devuelve el mismo objeto: así un defecto compartido por parser y serializador de la
   biblioteca no pasa desapercibido.
4. js/mini.js (vía un proceso de Node persistente) lee ``t`` y devuelve el mismo objeto, y su ``dumps`` produce
   un texto que el parser de Python lee como el mismo objeto.

Además: valores fuera de rango, duplicados ``unique`` y un registro de menos se rechazan con el código de la
norma en el serializador y en el parser.

Los textos generados son «canónicos» (sin espacio exterior ni CR): para el resto de cadenas el serializador no
garantiza la ida y vuelta (D-1, ADR 0017 propuesta; pruebas ``expectedFailure`` en test_nucleo_propuestas.py).
Semilla fija (``derandomize``): mismas entradas en cada ejecución. ``MINI_PROP_EJEMPLOS`` cambia el número de
ejemplos por propiedad (por omisión 150).
"""
from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path
from typing import Any, Dict

from hypothesis import HealthCheck, assume, given, settings
from hypothesis import strategies as st

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

import nucleo_generadores as gen  # noqa: E402
from decodificador import decodificar  # noqa: E402
from minifmt import Contract, MiniError, MiniValidationError, Registry, dumps, parse  # noqa: E402
from minifmt.serializer import encode_header, encode_record  # noqa: E402

EJEMPLOS = int(os.environ.get("MINI_PROP_EJEMPLOS", "150"))
AJUSTES = settings(max_examples=EJEMPLOS, derandomize=True, deadline=None, database=None,
                   suppress_health_check=list(HealthCheck), print_blob=True)

REG = Registry.load(ROOT / "forks")
FAMILIAS = {c.prefix: (c, __import__("json").loads((REG.paths[c.prefix] / "contract.json").read_text(encoding="utf-8"))) for c in REG}


def exacto(a: Any, b: Any) -> bool:
    """Igualdad con tipos: bool distinto de int, dict/list recursivos, int y float no se mezclan."""
    if isinstance(a, bool) or isinstance(b, bool):
        return isinstance(a, bool) and isinstance(b, bool) and a == b
    if isinstance(a, dict) and isinstance(b, dict):
        return a.keys() == b.keys() and all(exacto(a[k], b[k]) for k in a)
    if isinstance(a, list) and isinstance(b, list):
        return len(a) == len(b) and all(exacto(x, y) for x, y in zip(a, b))
    return type(a) is type(b) and a == b


def numerico(a: Any, b: Any) -> bool:
    """Como ``exacto`` pero los números se comparan por valor (un JSON que pasa por JS pierde el ``.0``)."""
    if isinstance(a, bool) or isinstance(b, bool):
        return isinstance(a, bool) and isinstance(b, bool) and a == b
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        # JS no distingue entero de float y JSON.stringify escribe los dobles grandes con dígitos de más:
        # más allá de 2^53 se compara como double
        if isinstance(a, int) and isinstance(b, int) and abs(a) <= 2 ** 53 and abs(b) <= 2 ** 53:
            return a == b
        return float(a) == float(b)
    if isinstance(a, dict) and isinstance(b, dict):
        return a.keys() == b.keys() and all(numerico(a[k], b[k]) for k in a)
    if isinstance(a, list) and isinstance(b, list):
        return len(a) == len(b) and all(numerico(x, y) for x, y in zip(a, b))
    return a == b


class Propiedades(unittest.TestCase):
    servidor = None

    @classmethod
    def setUpClass(cls):
        cls.servidor = gen.ServidorJS() if gen.hay_node() else None

    @classmethod
    def tearDownClass(cls):
        if cls.servidor is not None:
            cls.servidor.cerrar()

    # ---------------------------------------------------------------- comprobación común
    def comprobar(self, cjson: Dict[str, Any], c: Contract, obj: Dict[str, Any]) -> None:
        rk = c.records_key
        texto = dumps(obj, c)
        esperado_cab = gen.cabecera_esperada(c, obj["header"], len(obj[rk]))
        # 1. ida y vuelta del objeto, con tipos exactos
        vuelta = parse(texto, c).to_canonical()
        self.assertTrue(exacto(vuelta[rk], obj[rk]), f"registros distintos\n{texto!r}\n{vuelta[rk]}\n{obj[rk]}")
        self.assertTrue(exacto(vuelta["header"], esperado_cab), f"cabecera distinta\n{texto!r}\n{vuelta['header']}\n{esperado_cab}")
        # 2. el texto emitido es estable
        self.assertEqual(dumps(vuelta, c), texto)
        # 3. el oráculo independiente lee lo mismo
        orc = decodificar(texto, cjson, estricto=True)
        self.assertEqual(orc.errores, set(), f"el oráculo rechaza el texto del serializador\n{texto!r}")
        self.assertTrue(exacto(orc.canonico[rk], obj[rk]), f"el oráculo lee otra cosa\n{texto!r}\n{orc.canonico[rk]}\n{obj[rk]}")
        self.assertTrue(exacto(orc.canonico["header"], esperado_cab), f"cabecera del oráculo\n{texto!r}")
        # 4. js/mini.js lee lo mismo y su serializador produce texto que Python lee igual
        if self.servidor is not None:
            js = self.servidor.consultar("parse", cjson, texto)
            self.assertNotIn("excepcion", js, js)
            self.assertEqual(js["errs"], [], f"js/mini.js rechaza el texto\n{texto!r}")
            self.assertTrue(numerico(js["canon"][rk], obj[rk]), f"js/mini.js lee otra cosa\n{texto!r}\n{js['canon'][rk]}\n{obj[rk]}")
            texto_js = self.servidor.consultar("dumps", cjson, obj)
            self.assertIn("texto", texto_js, f"js/mini.js no serializa: {texto_js}\n{obj}")
            self.assertTrue(numerico(parse(texto_js["texto"], c).to_canonical()[rk], obj[rk]),
                            f"el texto de js/mini.js se lee distinto\n{texto_js['texto']!r}")

    # ---------------------------------------------------------------- por familia oficial
    @given(st.data())
    @AJUSTES
    def test_ida_y_vuelta_por_familia(self, data):
        prefijo = data.draw(st.sampled_from(sorted(FAMILIAS)))
        c, cjson = FAMILIAS[prefijo]
        obj = data.draw(gen.objeto(c))
        self.comprobar(cjson, c, obj)

    # ---------------------------------------------------------------- por contrato generado
    @given(st.data())
    @AJUSTES
    def test_ida_y_vuelta_por_contrato_generado(self, data):
        cjson = data.draw(gen.contrato_aleatorio())
        try:
            c = Contract.from_dict(cjson)
        except MiniError:
            assume(False)  # contrato generado inválido (la estrategia actual no los produce)
        obj = data.draw(gen.objeto(c))
        self.comprobar(cjson, c, obj)

    # ---------------------------------------------------------------- rechazos con el código de la norma
    @given(st.data())
    @AJUSTES
    def test_unique_repetido_se_rechaza_con_e11_en_la_linea_del_segundo(self, data):
        prefijo = data.draw(st.sampled_from(sorted(FAMILIAS)))
        c, cjson = FAMILIAS[prefijo]
        unicos = [f for f in c.fields if f.unique]
        assume(bool(unicos))
        obj = data.draw(gen.objeto(c, max_registros=4).filter(lambda o: len(o[c.records_key]) >= 2))
        f = unicos[0]
        obj[c.records_key][1][f.name] = obj[c.records_key][0][f.name]
        with self.assertRaises(MiniError) as cm:
            dumps(obj, c)
        self.assertEqual((cm.exception.code, cm.exception.line), ("E11", 3))
        # el mismo documento armado línea a línea (sin la comprobación de dumps) también es E11 para el parser y el oráculo
        lineas = [encode_header(obj["header"], c, len(obj[c.records_key]))] + [encode_record(r, c) for r in obj[c.records_key]]
        texto = "\n".join(lineas)
        with self.assertRaises(MiniValidationError) as err:
            parse(texto, c)
        self.assertIn(("E11", 3), {(e.code, e.line) for e in err.exception.errors})
        self.assertIn(("E11", 3), decodificar(texto, cjson, estricto=True).errores)

    @given(st.data())
    @AJUSTES
    def test_registro_de_menos_es_e04_y_no_hay_otro_error(self, data):
        prefijo = data.draw(st.sampled_from(sorted(FAMILIAS)))
        c, cjson = FAMILIAS[prefijo]
        obj = data.draw(gen.objeto(c).filter(lambda o: len(o[c.records_key]) >= 1))
        lineas = dumps(obj, c).split("\n")
        quitar = data.draw(st.integers(1, len(lineas) - 1))
        texto = "\n".join(lineas[:quitar] + lineas[quitar + 1:])
        with self.assertRaises(MiniValidationError) as err:
            parse(texto, c)
        self.assertEqual({(e.code, e.line) for e in err.exception.errors}, {("E04", 0)})
        self.assertEqual(decodificar(texto, cjson, estricto=True).errores, {("E04", 0)})

    @given(st.data())
    @AJUSTES
    def test_fuera_de_rango_se_rechaza_con_e13_en_la_linea_del_registro(self, data):
        cjson = data.draw(gen.contrato_aleatorio())
        c = Contract.from_dict(cjson)
        acotados = [f for f in c.fields if f.type == "int" and f.max is not None and not f.optional]
        assume(bool(acotados))
        obj = data.draw(gen.objeto(c).filter(lambda o: len(o[c.records_key]) >= 1))
        f = acotados[0]
        obj[c.records_key][0][f.name] = int(f.max) + 1
        with self.assertRaises(MiniError) as cm:
            dumps(obj, c)
        self.assertEqual((cm.exception.code, cm.exception.line), ("E13", 2))


if __name__ == "__main__":
    unittest.main()
