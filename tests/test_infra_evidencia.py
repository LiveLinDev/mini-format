"""Evidencia: honestidad de los estudios, validación de corridas, derivados deterministas y su verificación.

Cada prueba trabaja sobre una copia temporal de la raíz del repositorio (solo lo necesario) para poder
crear corridas y editar el registro sin tocar los datos versionados.
"""
from __future__ import annotations

import copy
import io
import json
import shutil
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

import evidencia as EV  # noqa: E402
import evidencia_lib as lib  # noqa: E402

FIJADO = "2026-09-30T19:00:00Z"
DESPUES = "2026-10-05T12:00:00Z"
ANTES = "2026-09-01T12:00:00Z"
ARCHIVOS_NECESARIOS = [
    "evidencia/estudios.json",
    "evidencia/tarifas/tarifas.json",
    "evidencia/tarifas/fuentes.json",
    "experiments/v8_sima/resumen.json",
    "experiments/v7_escalamiento/results/deepseek_volumen/costo_real.json",
]


def manifiesto(estudio, run_id, procedencia="reproducido_local", fecha=DESPUES, componente=None, resumen=None,
               estado="ejecutado", modelo=None, so="Linux 6.8", gasto=None, parametros=None, **extra):
    m = {
        "esquema": lib.ESQUEMA_CORRIDA, "run_id": run_id, "estudio": estudio, "pareja": None, "intento": None,
        "procedencia": procedencia, "fecha_utc": fecha,
        "codigo": {"commit": "a" * 40, "rama": "prueba", "arbol_limpio": True, "snapshot_sha256": None, "archivos_modificados": []},
        "entorno": {"so": so, "arquitectura": "x86_64", "python": "3.11.0", "node": None, "dependencias": {}},
        "comando": "python experiments/algo.py", "conjuntos": [], "contratos": [], "tokenizadores": [], "modelo": modelo,
        "parametros": dict(parametros or {}), "prompts": [], "tarifas": None, "resultados": [], "conteos": None,
        "resumen": resumen or {}, "criterio": None, "estado_ejecucion": estado, "resultado": "no_evaluable",
        "limitaciones": [], "gasto_usd": gasto, "notas": "",
    }
    if componente:
        m["parametros"]["componente"] = componente
    m.update(extra)
    return m


RESUMEN_V1_OK = {"dominios_que_superan_umbral_min_tokenizador": 12, "tokenizadores_medidos": 3, "dominios_medidos": 14, "ahorro_medio_pct": 34.99}


class Base(unittest.TestCase):
    def setUp(self):
        self.raiz = Path(tempfile.mkdtemp(prefix="evid_"))
        self.addCleanup(shutil.rmtree, self.raiz, True)
        for rel in ARCHIVOS_NECESARIOS:
            dst = self.raiz / rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy(ROOT / rel, dst)
        casos = self.raiz / "conformance" / "cases"
        casos.mkdir(parents=True, exist_ok=True)
        for p in (ROOT / "conformance" / "cases").glob("*.json"):
            shutil.copy(p, casos / p.name)

    # --- ayudas
    def registro(self):
        return json.loads((self.raiz / "evidencia" / "estudios.json").read_text(encoding="utf-8"))

    def guardar_registro(self, doc):
        (self.raiz / "evidencia" / "estudios.json").write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")

    def estudio(self, doc, id_):
        return next(e for e in doc["estudios"] if e["id"] == id_)

    def declarar(self, id_, **campos):
        doc = self.registro()
        self.estudio(doc, id_).update(campos)
        self.guardar_registro(doc)

    def corrida(self, m, archivos=None):
        d = self.raiz / "evidencia" / "corridas" / m["run_id"]
        d.mkdir(parents=True, exist_ok=True)
        for nombre, contenido in (archivos or {}).items():
            (d / nombre).write_text(contenido, encoding="utf-8")
            m.setdefault("resultados", []).append({"ruta": f"evidencia/corridas/{m['run_id']}/{nombre}", "sha256": lib.sha256_archivo(d / nombre), "bytes": (d / nombre).stat().st_size})
        lib.escribir_json(d / "manifiesto.json", m)
        return d

    def estudios(self):
        return EV.comprobar_estudios(self.raiz)

    def nombres(self, textos):
        return "\n".join(textos)


class HonestidadDeEstudios(Base):
    def test_el_registro_versionado_es_honesto(self):
        errores, avisos, evals = EV.comprobar_estudios(ROOT)
        self.assertEqual(errores, [])
        doc = json.loads((ROOT / "evidencia" / "estudios.json").read_text(encoding="utf-8"))
        self.assertEqual([e["id"] for e in doc["estudios"]], list(EV.ESTUDIOS_REQUERIDOS))
        self.assertNotIn("cumple", {e["resultado"] for e in doc["estudios"]})
        self.assertNotIn("no_cumple", {e["resultado"] for e in doc["estudios"]})
        self.assertNotIn("ejecutado", {e["estado_ejecucion"] for e in doc["estudios"]} - {e["estado_ejecucion"] for e in doc["estudios"] if evals[e["id"]]["estado_calculado"] == "ejecutado"})

    def test_estados_iniciales_honestos(self):
        doc = self.registro()
        estado = {e["id"]: e["estado_ejecucion"] for e in doc["estudios"]}
        self.assertEqual((estado["V2"], estado["V3b"], estado["V4"]), ("bloqueado", "bloqueado", "bloqueado"))
        self.assertEqual(estado["V6b"], "pendiente")
        self.assertIn(estado["V6a"], ("parcial", "pendiente"))
        self.assertEqual((estado["V1"], estado["V5"]), ("parcial", "parcial"))
        for e in doc["estudios"]:
            if e["estado_ejecucion"] == "bloqueado":
                self.assertTrue(e["bloqueo"]["causa"])

    def test_ejecutado_sin_corridas_es_error(self):
        self.declarar("V1", estado_ejecucion="ejecutado")
        errores, _, _ = self.estudios()
        self.assertTrue(any("V1: declara ejecutado" in e and "faltan componentes" in e for e in errores), errores)

    def test_cumple_sin_corridas_es_error(self):
        self.declarar("V1", estado_ejecucion="ejecutado", resultado="cumple")
        errores, _, _ = self.estudios()
        texto = self.nombres(errores)
        self.assertIn("declara ejecutado", texto)
        self.assertIn("declara cumple pero el recálculo", texto)

    def test_resultado_exige_estado_ejecutado(self):
        self.declarar("V6b", resultado="cumple")
        errores, _, _ = self.estudios()
        self.assertTrue(any("resultado cumple exige estado ejecutado" in e for e in errores))

    def test_ciclo_completo_cumple_se_recalcula(self):
        self.corrida(manifiesto("V1", "v1-20261005", componente="tokens_por_dominio_y_tokenizador", resumen=RESUMEN_V1_OK))
        errores, avisos, evals = self.estudios()
        self.assertEqual(errores, [])
        self.assertEqual(evals["V1"]["estado_calculado"], "ejecutado")
        self.assertEqual(evals["V1"]["resultado_calculado"], "cumple")
        # el registro sigue diciendo parcial/no_evaluable: advertencia de registro desactualizado, no error
        self.assertTrue(any("V1: registro desactualizado" in a for a in avisos), avisos)
        self.declarar("V1", estado_ejecucion="ejecutado", resultado="cumple")
        errores, avisos, _ = self.estudios()
        self.assertEqual((errores, [a for a in avisos if a.startswith("V1")]), ([], []))

    def test_no_cumple_por_un_predicado(self):
        r = dict(RESUMEN_V1_OK, dominios_que_superan_umbral_min_tokenizador=9)
        self.corrida(manifiesto("V1", "v1-20261005", resumen=r))
        self.declarar("V1", estado_ejecucion="ejecutado", resultado="cumple")
        errores, _, evals = self.estudios()
        self.assertEqual(evals["V1"]["resultado_calculado"], "no_cumple")
        self.assertTrue(any("declara cumple pero el recálculo desde los predicados da no_cumple" in e for e in errores))
        self.declarar("V1", resultado="no_cumple")
        errores, _, _ = self.estudios()
        self.assertEqual(errores, [])

    def test_lo_simulado_asistido_o_historico_no_acredita_ejecucion(self):
        for i, proc in enumerate(("simulado", "asistido_ia", "reportado_historico")):
            with self.subTest(proc):
                shutil.rmtree(self.raiz / "evidencia" / "corridas", ignore_errors=True)
                self.corrida(manifiesto("V1", f"v1-x{i}", procedencia=proc, resumen=RESUMEN_V1_OK))
                self.declarar("V1", estado_ejecucion="ejecutado", resultado="cumple")
                errores, _, evals = self.estudios()
                self.assertEqual(evals["V1"]["estado_calculado"], "pendiente")
                self.assertTrue(any("declara ejecutado" in e for e in errores))
                self.assertFalse(evals["V1"]["cuenta"][f"v1-x{i}"][0])
        self.declarar("V1", estado_ejecucion="parcial", resultado="no_evaluable")

    def test_criterio_fijado_despues_de_los_datos_no_es_evaluable(self):
        self.corrida(manifiesto("V1", "v1-antes", fecha=ANTES, resumen=RESUMEN_V1_OK))
        _, _, evals = self.estudios()
        self.assertEqual(evals["V1"]["estado_calculado"], "ejecutado")
        self.assertEqual(evals["V1"]["resultado_calculado"], "no_evaluable")
        self.assertIn("DESPUÉS", evals["V1"]["motivo_resultado"])

    def test_dato_faltante_es_no_evaluable_nunca_cero(self):
        r = {k: v for k, v in RESUMEN_V1_OK.items() if k != "tokenizadores_medidos"}
        self.corrida(manifiesto("V1", "v1-falta", resumen=r))
        _, _, evals = self.estudios()
        self.assertEqual(evals["V1"]["resultado_calculado"], "no_evaluable")
        p = next(x for x in evals["V1"]["predicados"] if x["id"] == "tokenizadores")
        self.assertIsNone(p["valor_observado"])
        self.assertIsNone(p["cumple"])   # no es False: no se inventa un 0
        self.declarar("V1", estado_ejecucion="ejecutado", resultado="no_cumple")
        errores, _, _ = self.estudios()
        self.assertTrue(any("declara no_cumple pero el recálculo" in e for e in errores))

    def test_v2_necesita_tres_modelos_reales_de_dos_proveedores(self):
        def real(i, prov, mod, pct):
            return manifiesto("V2", f"v2-{i}", procedencia="api_real", modelo={"proveedor": prov, "modelo_pedido": mod, "modelo_devuelto": mod, "endpoint": None},
                              gasto=0.5, resumen={"validos_finales_pct_d1": pct, "validos_iniciales_pct_d": 80})
        self.corrida(real(1, "OpenAI", "gpt-4.1-mini", 97))
        self.corrida(real(2, "OpenAI", "gpt-5.4-mini", 96))
        _, _, ev2 = self.estudios()
        self.assertEqual(ev2["V2"]["estado_calculado"], "parcial")   # 2 de 3 corridas mínimas
        self.corrida(real(3, "OpenAI", "gpt-5-mini", 98))
        _, _, ev3 = self.estudios()
        self.assertEqual(ev3["V2"]["estado_calculado"], "ejecutado")
        self.assertEqual(ev3["V2"]["resultado_calculado"], "no_cumple")   # 3 modelos pero 1 proveedor
        self.assertIn("proveedores", ev3["V2"]["motivo_resultado"])
        self.corrida(real(3, "Anthropic", "claude-haiku-4-5-20251001", 94))   # el peor modelo < 95
        _, _, ev4 = self.estudios()
        self.assertEqual(ev4["V2"]["resultado_calculado"], "no_cumple")
        self.assertIn("validos_finales", ev4["V2"]["motivo_resultado"])
        self.corrida(real(3, "Anthropic", "claude-haiku-4-5-20251001", 99))
        _, _, ev5 = self.estudios()
        self.assertEqual(ev5["V2"]["resultado_calculado"], "cumple")
        self.assertEqual({p["id"]: p["valor_observado"] for p in ev5["V2"]["predicados"]}, {"validos_finales": 96, "modelos": 3, "proveedores": 2})

    def test_v5_varios_componentes_exigen_parametros_componente(self):
        self.corrida(manifiesto("V5", "v5-sin-componente", resumen={"conformidad_pct": 100}))
        _, _, e = self.estudios()
        self.assertEqual(e["V5"]["estado_calculado"], "pendiente")
        self.assertIn("parametros.componente", e["V5"]["cuenta"]["v5-sin-componente"][1])
        self.corrida(manifiesto("V5", "v5-suite", componente="suite_de_conformidad", resumen={"conformidad_pct": 100, "defectos_bloqueantes": 0}))
        self.corrida(manifiesto("V5", "v5-cob", componente="cobertura", resumen={"cobertura_python_pct": 94, "cobertura_ts_lineas_pct": 97}))
        _, _, e = self.estudios()
        self.assertEqual(e["V5"]["estado_calculado"], "parcial")
        for i, so in enumerate(("Linux 6.8", "Windows 10", "Darwin 23.1")):
            self.corrida(manifiesto("V5", f"v5-ci-{i}", componente="ci_tres_sistemas", so=so, resumen={"conformidad_pct": 100}))
        _, _, e = self.estudios()
        self.assertEqual(e["V5"]["estado_calculado"], "ejecutado")
        self.assertEqual(e["V5"]["resultado_calculado"], "cumple")
        os_ = next(p for p in e["V5"]["predicados"] if p["id"] == "sistemas_operativos")
        self.assertEqual(os_["valor_observado"], 3)

    def test_v5_tres_corridas_en_el_mismo_so_no_son_tres_sistemas(self):
        self.corrida(manifiesto("V5", "v5-suite", componente="suite_de_conformidad", resumen={"conformidad_pct": 100, "defectos_bloqueantes": 0}))
        self.corrida(manifiesto("V5", "v5-cob", componente="cobertura", resumen={"cobertura_python_pct": 94, "cobertura_ts_lineas_pct": 97}))
        for i in range(3):
            self.corrida(manifiesto("V5", f"v5-ci-{i}", componente="ci_tres_sistemas", so=f"Linux 6.{i}", resumen={}))
        _, _, e = self.estudios()
        self.assertEqual(e["V5"]["resultado_calculado"], "no_cumple")
        self.assertIn("sistemas_operativos", e["V5"]["motivo_resultado"])

    def test_componente_desconocido_es_error(self):
        self.corrida(manifiesto("V1", "v1-raro", componente="no_existe", resumen=RESUMEN_V1_OK))
        errores, _, evals = self.estudios()
        self.assertTrue(any("no existe en el estudio V1" in e for e in errores))
        self.assertEqual(evals["V1"]["estado_calculado"], "pendiente")

    def test_parcial_sin_nada_que_lo_sostenga_es_error(self):
        self.declarar("V6b", estado_ejecucion="parcial")
        errores, _, _ = self.estudios()
        self.assertTrue(any("V6b: declara parcial pero no hay corridas" in e for e in errores))

    def test_bloqueado_y_pendiente_exigen_coherencia(self):
        self.declarar("V2", bloqueo=None)
        errores, _, _ = self.estudios()
        self.assertTrue(any("V2: bloqueado exige bloqueo" in e for e in errores))
        self.declarar("V6b", bloqueo={"causa": "x", "desbloquea": "y"})
        errores, _, _ = self.estudios()
        self.assertTrue(any("V6b: pendiente no lleva bloqueo" in e for e in errores))

    def test_bloqueado_con_corridas_es_advertencia_de_registro_desactualizado(self):
        self.corrida(manifiesto("V2", "v2-1", procedencia="api_real", modelo={"proveedor": "OpenAI", "modelo_pedido": "m"}, gasto=0.1, resumen={}))
        _, avisos, _ = self.estudios()
        self.assertTrue(any("V2: registro desactualizado: declara bloqueado" in a for a in avisos))

    def test_exploratorio_no_admite_criterio_ni_resultado(self):
        doc = self.registro()
        self.estudio(doc, "V7")["criterio"] = copy.deepcopy(self.estudio(doc, "V1")["criterio"])
        self.guardar_registro(doc)
        errores, _, _ = self.estudios()
        self.assertTrue(any("exploratorio no tiene criterio" in e for e in errores))

    def test_clasificacion_metodologica(self):
        doc = self.registro()
        self.estudio(doc, "V6a")["clasificacion"]["tipo"] = "controlado"
        self.estudio(doc, "V6b")["clasificacion"]["tipo"] = "naturalista"
        self.guardar_registro(doc)
        errores, _, _ = self.estudios()
        texto = self.nombres(errores)
        self.assertIn("V6a: clasificacion.tipo debe ser naturalista", texto)
        self.assertIn("V6b: clasificacion.tipo debe ser controlado", texto)

    def test_procedencia_simulada_no_se_puede_admitir_en_un_componente(self):
        doc = self.registro()
        self.estudio(doc, "V1")["componentes"][0]["procedencias_admitidas"] = ["reproducido_local", "simulado"]
        self.guardar_registro(doc)
        errores, _, _ = self.estudios()
        self.assertTrue(any("procedencias_admitidas debe ser un subconjunto" in e for e in errores))

    def test_antecedente_estricto_que_ya_no_coincide_es_error_y_el_flexible_advertencia(self):
        p = self.raiz / "experiments" / "v8_sima" / "resumen.json"
        d = json.loads(p.read_text(encoding="utf-8"))
        d["clases"]["items_pedidos"] = 351
        p.write_text(json.dumps(d), encoding="utf-8")
        cases = self.raiz / "conformance" / "cases"
        total = sum(len(json.loads(f.read_text(encoding="utf-8"))["cases"]) for f in cases.glob("*.json"))
        quitados = len(json.loads((cases / "unique.json").read_text(encoding="utf-8"))["cases"])
        (cases / "unique.json").unlink()   # el total baja; el registro declara el anterior
        errores, avisos, _ = self.estudios()
        self.assertTrue(any("«Ítems pedidos» dice 350 y el archivo da 351" in e for e in errores))
        self.assertTrue(any("Casos en conformance/cases" in a and str(total - quitados) in a for a in avisos))
        self.assertFalse(any("Casos en conformance/cases" in e for e in errores))

    def test_registro_incompleto_o_con_claves_raras(self):
        doc = self.registro()
        doc["estudios"].pop()                      # falta V8
        self.estudio(doc, "V1")["estado"] = "x"   # clave desconocida
        self.guardar_registro(doc)
        errores, _, _ = self.estudios()
        texto = self.nombres(errores)
        self.assertIn("falta el estudio V8", texto)
        self.assertIn("claves desconocidas", texto)


class Agregaciones(unittest.TestCase):
    def test_agregaciones(self):
        from decimal import Decimal as D
        a = EV._agregar
        self.assertEqual(a([3, 1, 2], "min"), D(1))
        self.assertEqual(a([3, 1, 2], "max"), D(3))
        self.assertEqual(a([3, 1, 2], "suma"), D(6))
        self.assertEqual(a([0.1, 0.2], "suma"), D("0.3"))        # sin error de coma flotante
        self.assertEqual(a([7], "unico"), D(7))
        self.assertIsNone(a([7, 8], "unico"))                     # ambiguo: no se elige
        self.assertIsNone(a([], "min"))
        self.assertIsNone(a([1, "x"], "suma"))
        self.assertIsNone(a([True], "suma"))                      # un booleano no es un número
        self.assertEqual(a(["a", "b", "a"], "conteo_distintos"), D(2))
        self.assertIsNone(a([], "conteo_distintos"))              # sin datos no hay 0 distintos
        self.assertEqual(a(["Linux 6.8", "Linux 5.15", "Windows 10", "Darwin 23"], "conteo_distintos_familia"), D(3))

    def test_valores_que_son_objetos_aportan_sus_valores(self):
        """Un resumen {tokenizador: n} se agrega por sus valores (el peor tokenizador) o por el número de claves."""
        from decimal import Decimal as D
        a = EV._agregar
        por_tok = {"cl100k_base": 10, "o200k_base": 12, "r50k_base": 8}
        self.assertEqual(a([por_tok], "min"), D(8))
        self.assertEqual(a([por_tok], "max"), D(12))
        self.assertEqual(a([por_tok, {"x": 1}], "min"), D(1))
        self.assertEqual(a([por_tok], "conteo_claves"), D(3))
        self.assertEqual(a([por_tok, {"r50k_base": 9, "extra": 1}], "conteo_claves"), D(4))
        self.assertIsNone(a([3], "conteo_claves"))                 # un escalar no tiene claves
        self.assertIsNone(a([{}], "conteo_claves"))                # un objeto vacío no es 0 tokenizadores medidos
        self.assertIsNone(a([{"a": "x"}], "min"))                   # valores no numéricos: no evaluable

    def test_comparaciones(self):
        from decimal import Decimal as D
        self.assertTrue(EV._comparar(D(95), ">=", D(95)))
        self.assertFalse(EV._comparar(D("94.99"), ">=", D(95)))
        self.assertTrue(EV._comparar(D(0), "==", D(0)))
        self.assertIsNone(EV._comparar(None, ">=", D(1)))


class ValidacionDeCorridas(Base):
    def test_corrida_valida(self):
        self.corrida(manifiesto("V1", "v1-ok"), archivos={"datos.csv": "a,b\n1,2\n"})
        errores, _, corridas = EV.validar(self.raiz)
        self.assertEqual(errores, [])
        self.assertEqual(len(corridas), 1)

    def test_sha256_de_resultados_alterado(self):
        d = self.corrida(manifiesto("V1", "v1-sha"), archivos={"datos.csv": "a,b\n1,2\n"})
        (d / "datos.csv").write_text("a,b\n1,3\n", encoding="utf-8")
        errores, _, _ = EV.validar(self.raiz)
        self.assertTrue(any("SHA-256 distinto" in e for e in errores), errores)

    def test_falta_el_archivo_de_resultados(self):
        d = self.corrida(manifiesto("V1", "v1-falta"), archivos={"datos.csv": "x"})
        (d / "datos.csv").unlink()
        errores, _, _ = EV.validar(self.raiz)
        self.assertTrue(any("falta el archivo de resultados" in e for e in errores))

    def test_run_id_distinto_de_la_carpeta(self):
        d = self.corrida(manifiesto("V1", "v1-a"))
        d.rename(d.parent / "v1-b")
        errores, _, _ = EV.validar(self.raiz)
        self.assertTrue(any("debe coincidir con el nombre de la carpeta" in e for e in errores))

    def test_api_real_sin_modelo_ni_gasto(self):
        self.corrida(manifiesto("V2", "v2-real", procedencia="api_real"))
        errores, _, _ = EV.validar(self.raiz)
        texto = self.nombres(errores)
        self.assertIn("api_real exige modelo", texto)
        self.assertIn("api_real exige gasto_usd", texto)

    def test_simulado_declarando_cumple_es_error(self):
        self.corrida(manifiesto("V1", "v1-sim", procedencia="simulado", resultado="cumple", criterio={"t": 1}))
        errores, _, _ = EV.validar(self.raiz)
        self.assertTrue(any("simulado no puede declararse cumple" in e for e in errores))

    def test_estudio_desconocido_y_v3_generico(self):
        self.corrida(manifiesto("ZZ", "zz-1"))
        self.corrida(manifiesto("V3", "v3-1"))
        errores, avisos, _ = EV.validar(self.raiz)
        self.assertTrue(any("estudio 'ZZ' desconocido" in e for e in errores))
        self.assertTrue(any("'V3' genérico" in a for a in avisos))

    def test_detecta_secretos_en_manifiesto_y_resultados(self):
        clave = "sk-" + "a1B2c3D4e5F6g7H8i9J0k1L2"
        self.corrida(manifiesto("V1", "v1-secreto", notas="usé la clave " + clave))
        self.corrida(manifiesto("V1", "v1-secreto2"), archivos={"log.txt": "Authorization: Bearer abcdefghijklmnopqrstuvwxyz0123456789\n"})
        errores, _, _ = EV.validar(self.raiz)
        texto = self.nombres(errores)
        self.assertIn("v1-secreto: posible secreto (clave tipo sk-)", texto)
        self.assertIn("v1-secreto2: posible secreto (cabecera Authorization)", texto)

    def test_no_marca_falsos_positivos_comunes(self):
        self.corrida(manifiesto("V1", "v1-limpio", notas="task-specific-identifier-for-the-experiment y tokens: 12345, sk-corto"),
                     archivos={"r.json": json.dumps({"tokens": "1234567890123456789012345", "token_count": 5})})
        errores, _, _ = EV.validar(self.raiz)
        self.assertEqual(errores, [])

    def test_resultado_publicable_no_puede_estar_en_restringida(self):
        m = manifiesto("V6b", "v6b-x", procedencia="participantes")
        m["resultados"] = [{"ruta": "evidencia/restringida/sesion1.json", "sha256": "0" * 64, "bytes": 1}]
        self.corrida(m)
        errores, _, _ = EV.validar(self.raiz)
        self.assertTrue(any("no puede vivir en evidencia/restringida" in e for e in errores))

    def test_manifiesto_ausente_o_ilegible(self):
        (self.raiz / "evidencia" / "corridas" / "sin-manifiesto").mkdir(parents=True)
        d = self.raiz / "evidencia" / "corridas" / "roto"
        d.mkdir()
        (d / "manifiesto.json").write_text("{no es json", encoding="utf-8")
        errores, _, _ = EV.validar(self.raiz)
        texto = self.nombres(errores)
        self.assertIn("sin-manifiesto: falta manifiesto.json", texto)
        self.assertIn("roto: manifiesto.json no es JSON válido", texto)


class DerivadosDeterministas(Base):
    def _preparar(self):
        self.corrida(manifiesto("V1", "v1-20261005", componente="tokens_por_dominio_y_tokenizador", resumen=RESUMEN_V1_OK),
                     archivos={"tokens.csv": "dominio,ahorro\na,34.9\n"})
        self.corrida(manifiesto("V2", "v2-simulado", procedencia="simulado", resumen={"validos_finales_pct_d1": 100}))
        self.declarar("V1", estado_ejecucion="ejecutado", resultado="cumple")

    def test_dos_regeneraciones_son_identicas_byte_a_byte(self):
        self._preparar()
        EV.regenerar(self.raiz)
        primera = {p.name: p.read_bytes() for p in (self.raiz / "evidencia" / "derivados").iterdir()}
        EV.regenerar(self.raiz)
        segunda = {p.name: p.read_bytes() for p in (self.raiz / "evidencia" / "derivados").iterdir()}
        self.assertEqual(primera, segunda)
        self.assertEqual(set(primera), {"estudios.json", "estudios.csv", "corridas.csv", "tarifas.json", "tarifas.csv"})
        # también entre dos derivaciones en memoria y con el orden de los manifiestos cambiado
        self.assertEqual(EV.derivar(self.raiz), EV.derivar(self.raiz))

    def test_no_hay_marcas_de_tiempo_de_ejecucion(self):
        self._preparar()
        a = EV.derivar(self.raiz)
        import time
        time.sleep(1.1)
        b = EV.derivar(self.raiz)
        self.assertEqual(a, b)

    def test_contenido_derivado_por_estudio(self):
        self._preparar()
        EV.regenerar(self.raiz)
        d = json.loads((self.raiz / "evidencia" / "derivados" / "estudios.json").read_text(encoding="utf-8"))
        v1 = next(e for e in d["estudios"] if e["id"] == "V1")
        self.assertEqual((v1["estado_ejecucion"], v1["estado_calculado"], v1["resultado"], v1["resultado_calculado"]), ("ejecutado", "ejecutado", "cumple", "cumple"))
        self.assertEqual(v1["procedencias_que_cuentan"], {"reproducido_local": 1})
        self.assertEqual(v1["fecha_ultima_corrida"], DESPUES)
        self.assertEqual(v1["commit_ultima_corrida"], "a" * 40)
        self.assertEqual(v1["cifras_principales"][0]["valor"], 34.99)
        self.assertEqual(v1["cifras_principales"][0]["procedencias"], ["reproducido_local"])
        self.assertEqual(v1["corridas"][0]["datos"][0]["ruta"], "evidencia/corridas/v1-20261005/tokens.csv")
        self.assertEqual(len(v1["corridas"][0]["datos"][0]["sha256"]), 64)
        v2 = next(e for e in d["estudios"] if e["id"] == "V2")
        self.assertTrue(v2["hay_simulado_o_asistido"])
        self.assertEqual(v2["n_corridas"], 1)
        self.assertEqual(v2["n_corridas_que_cuentan"], 0)
        self.assertFalse(v2["corridas"][0]["cuenta"])
        self.assertIn("simulado", v2["corridas"][0]["motivo"])
        # todo antecedente queda marcado como NO evidencia y con su procedencia
        for e in d["estudios"]:
            for a in e["antecedentes"]:
                self.assertFalse(a["cuenta_como_evidencia"])
        self.assertEqual(d["totales"]["por_estado_ejecucion"]["ejecutado"], 1)

    def test_editar_una_cifra_derivada_hace_fallar_verificar(self):
        self._preparar()
        EV.regenerar(self.raiz)
        errores, _ = EV.verificar(self.raiz)
        self.assertEqual(errores, [])
        p = self.raiz / "evidencia" / "derivados" / "estudios.json"
        p.write_text(p.read_text(encoding="utf-8").replace('"valor": 34.99', '"valor": 38.5'), encoding="utf-8")
        errores, _ = EV.verificar(self.raiz)
        self.assertTrue(any("evidencia/derivados/estudios.json difiere" in e for e in errores), errores)
        EV.regenerar(self.raiz)
        self.assertEqual(EV.verificar(self.raiz)[0], [])

    def test_editar_un_csv_o_las_tarifas_derivadas_tambien_falla(self):
        self._preparar()
        EV.regenerar(self.raiz)
        for nombre, buscar, poner in (("estudios.csv", "V1,", "V1, "), ("tarifas.csv", "gpt-5.4-mini,verificada,0.75", "gpt-5.4-mini,verificada,0.05"), ("tarifas.json", '"0.75"', '"0.05"')):
            with self.subTest(nombre):
                p = self.raiz / "evidencia" / "derivados" / nombre
                antes = p.read_text(encoding="utf-8")
                self.assertIn(buscar, antes)
                p.write_text(antes.replace(buscar, poner, 1), encoding="utf-8")
                errores, _ = EV.verificar(self.raiz)
                self.assertTrue(any(nombre in e for e in errores), errores)
                p.write_text(antes, encoding="utf-8")

    def test_un_derivado_que_falta_falla(self):
        EV.regenerar(self.raiz)
        (self.raiz / "evidencia" / "derivados" / "corridas.csv").unlink()
        errores, _ = EV.verificar(self.raiz)
        self.assertTrue(any("falta evidencia/derivados/corridas.csv" in e for e in errores))

    def test_cambiar_una_corrida_obliga_a_regenerar(self):
        self._preparar()
        EV.regenerar(self.raiz)
        d = self.raiz / "evidencia" / "corridas" / "v1-20261005"
        m = json.loads((d / "manifiesto.json").read_text(encoding="utf-8"))
        m["resumen"]["ahorro_medio_pct"] = 12.0
        lib.escribir_json(d / "manifiesto.json", m)
        errores, _ = EV.verificar(self.raiz)
        self.assertTrue(any("estudios.json difiere" in e for e in errores))

    def test_el_registro_incoherente_impide_regenerar_y_verificar(self):
        self.declarar("V1", estado_ejecucion="ejecutado")
        self.assertEqual(EV.main(["--raiz", str(self.raiz), "regenerar"]), 1)
        errores, _ = EV.verificar(self.raiz)
        self.assertTrue(errores)

    def test_csv_de_corridas_marca_quien_cuenta(self):
        self._preparar()
        EV.regenerar(self.raiz)
        filas = (self.raiz / "evidencia" / "derivados" / "corridas.csv").read_text(encoding="utf-8").splitlines()
        self.assertEqual(filas[0].split(",")[:3], ["run_id", "estudio", "procedencia"])
        v2 = next(f for f in filas if f.startswith("v2-simulado"))
        self.assertIn(",simulado,", v2)
        self.assertIn(",false,", v2)
        self.assertNotIn("\r", (self.raiz / "evidencia" / "derivados" / "corridas.csv").read_text(encoding="utf-8"))

    def test_tarifas_derivadas_salen_de_tarifas_json(self):
        EV.regenerar(self.raiz)
        origen = json.loads((self.raiz / "evidencia" / "tarifas" / "tarifas.json").read_text(encoding="utf-8"))
        der = json.loads((self.raiz / "evidencia" / "derivados" / "tarifas.json").read_text(encoding="utf-8"))
        self.assertEqual(len(der["tarifas"]), len(origen["tarifas"]))
        for o, d in zip(origen["tarifas"], der["tarifas"]):
            self.assertEqual((o["proveedor"], o["modelo_api_id"], o["estado"], o["salida_por_millon"]), (d["proveedor"], d["modelo_api_id"], d["estado"], d["salida_por_millon"]))
        self.assertIn("aproximación", der["nota_tokenizadores"])


class EvidenciaVersionada(unittest.TestCase):
    """Sobre los datos REALES del repositorio."""

    def test_verificar_pasa(self):
        errores, avisos = EV.verificar(ROOT)
        self.assertEqual(errores, [], "\n".join(errores))

    def test_cli(self):
        for cmd in (["validar"], ["estudios"], ["verificar"]):
            with self.subTest(cmd), redirect_stdout(io.StringIO()):
                self.assertEqual(EV.main(["--raiz", str(ROOT), *cmd]), 0)
        buf = io.StringIO()
        with redirect_stdout(buf):
            EV.main(["--raiz", str(ROOT), "estudios", "--contrato"])
        self.assertIn("parametros.componente = suite_de_conformidad", buf.getvalue())
        self.assertIn("resumen.validos_finales_pct_d1", buf.getvalue())

    def test_las_tarifas_derivadas_estan_al_dia(self):
        der = json.loads((ROOT / "evidencia" / "derivados" / "tarifas.json").read_text(encoding="utf-8"))
        ori = json.loads((ROOT / "evidencia" / "tarifas" / "tarifas.json").read_text(encoding="utf-8"))
        self.assertEqual([(t["proveedor"], t["modelo_api_id"], t["estado"]) for t in der["tarifas"]],
                         [(t["proveedor"], t["modelo_api_id"], t["estado"]) for t in ori["tarifas"]])


class EsquemaJson(unittest.TestCase):
    def setUp(self):
        try:
            import jsonschema  # noqa: F401
        except ImportError:
            self.skipTest("jsonschema no está instalado")
        self.schema = json.loads((ROOT / "evidencia" / "esquemas" / "estudio.schema.json").read_text(encoding="utf-8"))

    def test_el_registro_valida_contra_el_esquema(self):
        import jsonschema
        jsonschema.Draft202012Validator.check_schema(self.schema)
        doc = json.loads((ROOT / "evidencia" / "estudios.json").read_text(encoding="utf-8"))
        errores = list(jsonschema.Draft202012Validator(self.schema).iter_errors(doc))
        self.assertEqual(errores, [])

    def test_el_esquema_rechaza_lo_deshonesto(self):
        import jsonschema
        doc = json.loads((ROOT / "evidencia" / "estudios.json").read_text(encoding="utf-8"))
        v = jsonschema.Draft202012Validator(self.schema)
        malo = copy.deepcopy(doc)
        malo["estudios"][0]["resultado"] = "cumple"            # V1 con estado parcial
        self.assertTrue(list(v.iter_errors(malo)))
        malo = copy.deepcopy(doc)
        malo["estudios"][8]["criterio"] = copy.deepcopy(doc["estudios"][0]["criterio"])   # V7 exploratorio con criterio
        self.assertTrue(list(v.iter_errors(malo)))
        malo = copy.deepcopy(doc)
        malo["estudios"][1]["bloqueo"] = None                   # V2 bloqueado sin bloqueo
        self.assertTrue(list(v.iter_errors(malo)))
        malo = copy.deepcopy(doc)
        malo["estudios"][0]["componentes"][0]["procedencias_admitidas"] = ["simulado"]
        self.assertTrue(list(v.iter_errors(malo)))


if __name__ == "__main__":
    unittest.main()
