"""V1: las corridas guardadas en evidencia/corridas/v1-* son consistentes con sus archivos de resultados.

Nada de lo que se comprueba aquí se lee de un resumen escrito a mano: cada cifra se recalcula desde
los CSV/JSON de la propia corrida con aritmética independiente del código que los generó. Si las
corridas no existen (clon sin evidencia) las pruebas se omiten; en el repositorio sí existen.
"""
from __future__ import annotations

import csv
import hashlib
import json
import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
for _p in ("src", "benchmark", "benchmark/public", "experiments", "experiments/v1_tokens", "tools"):
    sys.path.insert(0, str(ROOT / _p))

CORRIDAS = ROOT / "evidencia" / "corridas"


def _ultima(serie: str):
    c = sorted(CORRIDAS.glob(f"v1-{serie}-*")) if CORRIDAS.exists() else []
    return c[-1] if c else None


SERIE = _ultima("serie_n")
try:
    import evidencia_lib as ev
    import numpy  # noqa: F401
    import comun as C
    import criterio as K
    import errata_v7_v8 as E
    import procedencia as P
    import vocab_local as V
    HAY = SERIE is not None
except ImportError:  # pragma: no cover
    HAY = False


def _sello(d: Path) -> str:
    return d.name.split("-", 2)[2]


def _csv(p: Path):
    with open(p, newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def _sha_lf(p: Path) -> str:
    return hashlib.sha256(p.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def _f2(x: float) -> str:
    return f"{x:.2f}".replace(".", ",")


@unittest.skipUnless(HAY, "no hay corridas v1-* en evidencia/corridas")
class CorridasV1Test(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        s = _sello(SERIE)
        cls.dirs = {k: CORRIDAS / f"v1-{k}-{s}" for k in ("linea_base_n12", "serie_n", "publicos", "conciliacion")}
        cls.man = {k: json.loads((d / "manifiesto.json").read_text(encoding="utf-8")) for k, d in cls.dirs.items()}

    # ----------------------------------------------------------------- manifiestos
    def test_los_cuatro_manifiestos_validan_y_sus_hashes_coinciden(self):
        for k, m in self.man.items():
            self.assertEqual(ev.validar_corrida(m, self.dirs[k]), [], k)
            self.assertEqual((m["estudio"], m["procedencia"], m["gasto_usd"], m["estado_ejecucion"]), ("V1", "reproducido_local", 0, "ejecutado"), k)
            self.assertIn("tools/ejecutar_v1.py", m["comando"])
            for r in m["resultados"]:
                self.assertEqual(ev.sha256_archivo(ROOT / r["ruta"]), r["sha256"], r["ruta"])

    def test_tokenizadores_con_version_y_hash_de_vocabulario(self):
        for k, m in self.man.items():
            nombres = {t["nombre"]: t for t in m["tokenizadores"]}
            self.assertEqual(set(nombres), {"o200k_base", "cl100k_base", "r50k_base"})
            for n, t in nombres.items():
                self.assertEqual(t["vocabulario_sha256"], V.VOCABULARIOS[n]["sha256"])
                self.assertEqual(V.verificar_vocabulario(n), t["vocabulario_sha256"])
                self.assertEqual((t["paquete"], t["backend"], t["tipo"]), ("tiktoken", "tiktoken", "exacto_local"))
                self.assertTrue(t["version"])

    def test_el_codigo_ejecutado_esta_identificado(self):
        for k, m in self.man.items():
            self.assertTrue(m["codigo"]["commit"], k)
            if m["codigo"]["arbol_limpio"] is False:
                self.assertTrue(m["codigo"]["snapshot_sha256"])

    # ------------------------------------------------------------------ datasets
    def test_hashes_y_etiquetas_de_los_datasets(self):
        src = {f"public/{s['id']}": s for s in json.loads((ROOT / "benchmark" / "public" / "sources.json").read_text(encoding="utf-8"))}
        for k in ("publicos", "conciliacion"):
            for c in self.man[k]["conjuntos"]:
                self.assertEqual(ev.sha256_archivo(ROOT / c["ruta"]), c["sha256"], c["nombre"])
                if c["nombre"] in src:
                    s = src[c["nombre"]]
                    self.assertEqual(c["sha256"], s["sha256"])
                    self.assertEqual(c["fecha_captura_utc"], s["fetched_at_utc"])
                    self.assertEqual(c["sintetico"], c["nombre"] != "public/earthquakes")
                    self.assertTrue(c["licencia"] and c["fuente"])
                    self.assertFalse(c["replicacion_de_base"])
        self.assertEqual(sum(c["registros"] for c in self.man["publicos"]["conjuntos"]), 1902)
        for k in ("linea_base_n12", "serie_n"):
            dom = self.man[k]["conjuntos"][0]
            self.assertTrue(dom["sintetico"])
            self.assertEqual(dom["semilla"], 20260914)
            self.assertTrue(dom["replicacion_de_base"])
            self.assertEqual(dom["registros"], 168)
            self.assertEqual(dom["sha256"], ev.sha256_archivo(ROOT / "benchmark" / "domains.py"))
        contratos = self.man["serie_n"]["contratos"]
        self.assertEqual(len(contratos), 14)
        for c in contratos:
            self.assertEqual(ev.sha256_archivo(ROOT / c["ruta"]), c["sha256"])

    def test_las_series_no_cuentan_replicas_como_muestras_independientes(self):
        filas = _csv(SERIE / "tokens_largo.csv")
        for f in filas:
            self.assertEqual(f["replicacion_de_base"] == "True", int(f["n"]) > 12, f"n={f['n']}")
        proc = json.loads((SERIE / "procedencia_datos.json").read_text(encoding="utf-8"))
        self.assertEqual(proc["dominios"]["registros_base_total"], 168)
        # oráculo independiente: contenidos distintos (sin identificadores) de un documento de 100 registros
        import domains
        for p, info in proc["dominios"]["por_dominio"].items():
            ids = set(C.claves_id(p))
            doc = C.generar(p, 100, "muestreo")
            distintos = {json.dumps({k: v for k, v in r.items() if k not in ids}, sort_keys=True, ensure_ascii=False) for r in doc[domains.BASE[p]["records_key"]]}
            self.assertEqual(len(distintos), 12, p)
            self.assertEqual(info["n100_contenidos_distintos_sin_id"], 12)
            self.assertEqual(info["independientes"], 12)
        self.assertIn("replicación", proc["muestra_independiente"])

    # ------------------------------------------------------------------ criterio
    def test_el_veredicto_y_las_cifras_del_manifiesto_derivan_de_tokens_largo(self):
        filas = []
        for r in _csv(SERIE / "tokens_largo.csv"):
            filas.append({"tokenizador": r["tokenizador"], "variante": r["variante"], "dominio": r["dominio"], "n": int(r["n"]), "formato": r["formato"],
                          "tokens": None if r["tokens"] == "" else int(r["tokens"]), "comparacion_valida": r["comparacion_valida"] == "True"})
        evaluacion = K.evaluar(filas, B=2000)
        m = self.man["serie_n"]
        self.assertEqual(m["resultado"], evaluacion["primario"]["veredicto"])
        guardado = json.loads((SERIE / "criterio_v1_resultado.json").read_text(encoding="utf-8"))
        self.assertEqual(guardado["primario"]["veredicto"], m["resultado"])
        for t in ("o200k_base", "cl100k_base", "r50k_base"):
            r = evaluacion["primario"]["resumen_por_tokenizador"][t]
            self.assertEqual(m["resumen"]["criterio"]["dominios_ge_30_por_tokenizador"][t], r["dominios_ge_umbral"])
            self.assertAlmostEqual(m["resumen"]["criterio"]["media_por_dominio_pct"][t], r["media_por_dominio_pct"], places=2)
            self.assertAlmostEqual(m["resumen"]["criterio"]["agregado_suma_pct"][t], r["agregado_suma_pct"], places=2)
            # aritmética directa (sin criterio.py): Σ sobre los documentos de cada dominio
            mini: dict = {}
            jc: dict = {}
            for f in filas:
                if f["tokenizador"] == t and f["variante"] == "muestreo" and f["n"] == 100:
                    if f["formato"] == "mini":
                        mini[f["dominio"]] = mini.get(f["dominio"], 0) + f["tokens"]
                    elif f["formato"] == "json_compact":
                        jc[f["dominio"]] = jc.get(f["dominio"], 0) + f["tokens"]
            altos = sum(1 for d in mini if 100 * (1 - mini[d] / jc[d]) >= 30.0)
            self.assertEqual(altos, r["dominios_ge_umbral"])
        if m["resultado"] in ("cumple", "no_cumple"):
            self.assertTrue(m["criterio"]["fijado_antes_del_analisis"])
            self.assertTrue(m["criterio"]["sujeto_a_aprobacion_del_asesor"])
            self.assertEqual(m["criterio"]["sha256_archivo"], ev.sha256_archivo(ROOT / "experiments" / "v1_tokens" / "criterio_v1.json"))

    def test_todos_los_dominios_con_reversibilidad_verificada_antes_de_contar(self):
        filas = _csv(SERIE / "tokens_largo.csv")
        rev = _csv(SERIE / "reversibilidad.csv")
        claves = {(r["variante"], r["dominio"], r["n"], r["formato"]) for r in rev}
        for f in filas:
            base = (f["variante"], f["dominio"], f["n"])
            if f["formato"] in ("csv_reversible", "toon_reversible"):
                self.assertTrue(any((base + (f["formato"] + ":" + v,)) in claves for v in ("celdas", "columnas")))
            else:
                self.assertIn(base + (f["formato"],), claves)
            if f["reversibilidad"] == "no_reversible":
                self.assertEqual(f["comparacion_valida"], "False")
        self.assertEqual({r["formato"] for r in filas if r["reversibilidad"] == "no_reversible"}, {"csv"})
        self.assertTrue(all(r["comparacion_valida"] == "True" for r in filas if r["formato"] in ("mini", "json_compact")))
        for r in rev:
            if r["estado"] == "no_reversible":
                self.assertTrue(r["causa"], "todo no_reversible lleva su causa")
        # la tabla de ahorro frente a cada comparador excluye de forma explícita el CSV sin metadatos
        for r in _csv(SERIE / "ahorro_por_referencia.csv"):
            if r["referencia"] == "csv":
                self.assertEqual(r["estado"], "excluido_no_reversible")
                self.assertEqual(r["media_por_dominio_pct"], "")
                self.assertIn("metadatos", r["causa"])

    def test_la_serie_reproducida_coincide_con_lo_archivado(self):
        m = self.man["serie_n"]["resumen"]
        self.assertTrue(m["consistencia_con_pipeline_archivado"]["coincide"])
        arch = {(r["tokenizador"], r["variante"], r["dominio"], r["n"], r["formato"]): r["tokens"]
                for r in _csv(ROOT / "experiments" / "v1_tokens" / "results" / "tokens.csv")}
        nuevo = {(r["tokenizador"], r["variante"], r["dominio"], r["n"], r["formato"]): r["tokens"] for r in _csv(SERIE / "archivado_pipeline" / "tokens.csv")}
        self.assertEqual(nuevo, arch)
        for nombre, c in m["comparacion_con_archivado"].items():
            self.assertTrue(c.get("coincide_totalmente"), nombre)
        lb = self.man["linea_base_n12"]["resumen"]["comparacion_con_archivado"]
        for nombre, c in lb.items():
            self.assertTrue(c.get("coincide_totalmente"), nombre)
        pub = self.man["publicos"]["resumen"]["comparacion_con_archivado"]
        self.assertTrue(pub["results.csv"]["coincide_totalmente"])
        self.assertTrue(pub["results.json"]["coincide_en_datos"])
        rutas = {d["ruta"] for d in pub["results.json"]["diferencias_de_procedencia"]}
        self.assertTrue(rutas <= {"/tiktoken", "/implementation_sha256/run.py", "/implementation_sha256/src/minifmt/domain.py", "/implementation_sha256/baselines.py"}, rutas)

    # ------------------------------------------------------------------ conciliación
    def test_las_cuatro_cifras_derivan_de_los_archivos(self):
        d = self.dirs["conciliacion"]
        cif = {c["cifra_citada"]: c for c in json.loads((d / "conciliacion_cifras.json").read_text(encoding="utf-8"))["cifras"]}
        self.assertEqual(set(cif), {"33,8 %", "34,8 %", "34,99 %", "35,64 %"})
        base = self.dirs["linea_base_n12"] / "benchmark_results"
        s12 = _csv(base / "summary_12.csv")
        v338 = sum(float(r["mini_vs_json_compact_pct"]) for r in s12) / len(s12)
        self.assertAlmostEqual(cif["33,8 %"]["valor_recalculado_pct"], v338, places=6)
        self.assertEqual(round(v338, 1), 33.8)
        ar = [r for r in _csv(SERIE / "archivado_pipeline" / "ahorro_resumen.csv")
              if (r["tokenizador"], r["variante"], r["n"], r["referencia"]) == ("o200k_base", "muestreo", "100", "json_compact")][0]
        self.assertAlmostEqual(cif["34,8 %"]["valor_recalculado_pct"], float(ar["media"]), places=6)
        self.assertEqual(round(float(ar["media"]), 1), 34.8)
        pub = json.loads((self.dirs["publicos"] / "results_o200k_base.json").read_text(encoding="utf-8"))
        den = sum(x["formats"]["json_compact"]["tokens"] for x in pub["datasets"])
        num_est = sum(x["formats"]["mini"]["payload_plus_schema_tokens"] for x in pub["datasets"])
        num_doc = sum(x["formats"]["mini"]["tokens"] for x in pub["datasets"])
        self.assertEqual((den, num_est, num_doc), (468849, 304799, 301763))
        self.assertAlmostEqual(cif["34,99 %"]["valor_recalculado_pct"], 100 * (1 - num_est / den), places=9)
        self.assertAlmostEqual(cif["35,64 %"]["valor_recalculado_pct"], 100 * (1 - num_doc / den), places=9)
        self.assertEqual(round(100 * (1 - num_est / den), 2), 34.99)
        self.assertEqual(round(100 * (1 - num_doc / den), 2), 35.64)
        self.assertAlmostEqual(cif["35,64 %"]["valor_archivado_pct"], 35.64, places=2)
        md = (d / "conciliacion_cifras.md").read_text(encoding="utf-8")
        for c in cif.values():
            self.assertIn(_f2(c["valor_recalculado_pct"]) + " %", md)
            for campo in ("unidad", "estadistico", "denominador", "conjunto", "tokenizador", "archivos"):
                self.assertTrue(c[campo], f"{c['cifra_citada']}: falta {campo}")
        self.assertFalse(cif["33,8 %"]["replicacion_de_base"])
        self.assertTrue(cif["34,8 %"]["replicacion_de_base"])

    def test_desglose_cuenta_textos_completos_y_no_suma_fragmentos(self):
        filas = _csv(self.dirs["conciliacion"] / "desglose_dominio_tokenizador.csv")
        self.assertEqual(len(filas), 2 * 14 * 3 * 2)  # (n12 ciclo, n100 muestreo) x dominios x tokenizadores x (json, mini)
        for f in filas:
            if f["formato"] == "json_compact":
                self.assertEqual(int(f["estructura_compartida"]), 0)
                self.assertEqual(int(f["total_documento_mas_estructura"]), int(f["documento"]))
            else:
                self.assertGreater(int(f["estructura_compartida"]), 0)
                self.assertGreater(int(f["prompt_reutilizable_es"]), 0)
            # el conteo conjunto no es la suma de los conteos sueltos
            self.assertLessEqual(int(f["total_documento_mas_prompt_es"]), int(f["documento"]) + int(f["prompt_reutilizable_es"]) + 2)
            self.assertGreaterEqual(int(f["total_documento_mas_prompt_es"]), int(f["documento"]))
        tot = {(f["dominio"], f["tokenizador"], f["n"]): f for f in filas if f["formato"] == "mini"}
        self.assertTrue(any(int(f["total_documento_mas_estructura"]) != int(f["documento"]) + int(f["estructura_compartida"]) for f in tot.values()),
                        "si el total fuera siempre la suma, no se estaría contando el texto completo")


@unittest.skipUnless(HAY, "no hay corridas v1-* en evidencia/corridas")
class ErrataTest(unittest.TestCase):
    RAW = {
        "experiments/v7_escalamiento/results/deepseek/llamadas.jsonl": "9475ad2dd3152ef523cc1fb5d0874885353db1e28d08193a257be5f0f680c87a",
        "experiments/v7_escalamiento/results/deepseek/meta.json": "3a08b12cc41ec0990344aaa40ff73a267ff09c1d7b7d71bce6e852ace311ebc5",
        "experiments/v7_escalamiento/results/deepseek/por_lote.csv": "f049837bc859a0db89cf0f9cf6722d014a8500ed82fdd77aa2e4fa64706d297f",
        "experiments/v7_escalamiento/results/deepseek/resumen.csv": "74740c63452a882c6692a93637a780463d9740219e89798b6fd67921c4c4603b",
        "experiments/v7_escalamiento/results/deepseek_volumen/llamadas.jsonl": "a480a722b24cb0f49c24c1c8776c8acf77dc21e7324ee5baf4ca24cee494ea1a",
        "experiments/v7_escalamiento/results/deepseek_volumen/meta.json": "711b068390f89d07d1c379d3bd57cf2b7dbdc2f3e784b031e892b43b6a076874",
        "experiments/v7_escalamiento/results/deepseek_volumen/costo_real.json": "9d93fc3fcd89522dbadb1941268a8a6656e31d19cb099177f3a56e6982ab6162",
        "experiments/v7_escalamiento/results/groq/llamadas.jsonl": "811596eb0c545f55ec265b6bd81a31c8a3f2e994416a302637d69de43b123b61",
        "experiments/v7_escalamiento/results/groq/meta.json": "ba7d33d6f1316e586399f7572cae944bee53bf2a25ce52748530c692261d64fb",
        "experiments/v8_sima/datos.json": "27abd1bbc0b06d516523f9ddfa59ae2f6a4815c40e0afb0f92268c83146d9c25",
        "experiments/v8_sima/resumen.json": "92890d427f76a84ddf40d0b83326c0213e2716baeddbbf3e0164381e37aa25e3",
    }

    def test_los_datos_crudos_siguen_intactos(self):
        for rel, h in self.RAW.items():
            self.assertEqual(_sha_lf(ROOT / rel), h, f"{rel} se ha modificado: las erratas no reescriben datos crudos")

    def test_errata_json_coincide_con_lo_que_se_recalcula(self):
        for rel, contenido in E.construir_erratas().items():
            en_disco = json.loads((ROOT / rel).read_text(encoding="utf-8"))
            self.assertEqual(en_disco, json.loads(json.dumps(contenido, ensure_ascii=False)), rel)
            self.assertFalse(en_disco["datos_crudos_modificados"])

    def test_v7_corrige_lote_maximo_y_meta_de_volumen(self):
        v7 = E.verificar_v7()
        self.assertEqual(v7["lote_maximo_sin_perdida"]["resumen_csv_archivado"]["mini"], 300)
        self.assertEqual(v7["lote_maximo_sin_perdida"]["definicion_estricta_por_lote"], {"json": 100, "mini": 200})
        self.assertEqual(v7["lote_maximo_sin_perdida"]["mini_L300"]["llamadas_cortadas"], 2)
        vol = v7["deepseek_volumen"]
        self.assertEqual((vol["meta_json"]["llamadas"], vol["llamadas_jsonl_total"]), (200, 300))
        self.assertEqual({k: v["llamadas"] for k, v in vol["por_formato_en_jsonl"].items()}, {"json": 200, "mini": 100})
        self.assertAlmostEqual(vol["usd_estimado_jsonl"], 2.4182, places=4)
        md = (ROOT / "experiments" / "v7_escalamiento" / "ERRATA.md").read_text(encoding="utf-8")
        for frag in ("300", "200", "93,3", "2,4182", "0,78", "no modificado", "payload"):
            if frag == "no modificado":
                frag = "no se han modificado"
            self.assertIn(frag, md)
        lineas = E.verificar_v7()["lote_maximo_sin_perdida"]["lineas"]
        citadas = {int(x) for x in re.findall(r"analizar\.py:(\d+)", md)}
        self.assertEqual(citadas, set(lineas.values()))

    def test_v8_concilia_343_5_2_con_350_por_contadores_y_deja_pendiente_el_registro_a_registro(self):
        v8 = E.verificar_v8()["conciliacion_clases"]
        t = v8["totales_de_los_contadores"]
        self.assertEqual((t["pedidos"], t["recibidos_validos"], t["invalidas"], t["reparadas"], t["recuperadas"], t["finales"]), (350, 343, 7, 5, 2, 350))
        self.assertEqual(v8["codigos_de_error"], {"E07": 5, "E05": 2})
        self.assertTrue(v8["identidad_por_bloque_ok"])
        self.assertTrue(v8["suma_es_finales_y_pedidos"])
        self.assertEqual((v8["bloques"], t["llamadas"]), (31, 38))
        self.assertEqual((v8["bloques_con_respuesta_cruda"], v8["bloques_donde_minifmt_reproduce_los_contadores"]), (17, 17))
        self.assertIn("pendiente", v8["registro_a_registro"])
        md = (ROOT / "experiments" / "v8_sima" / "ERRATA.md").read_text(encoding="utf-8")
        self.assertIn("343 + 5 + 2 = 350", md)
        self.assertIn("NO reconciliado registro a registro", md)


class VocabulariosLocalesTest(unittest.TestCase):
    def test_hash_oficial_de_los_tres_vocabularios(self):
        import vocab_local as vl
        for n in vl.NOMBRES:
            self.assertEqual(vl.verificar_vocabulario(n), vl.VOCABULARIOS[n]["sha256"])
        self.assertEqual(vl.VOCABULARIOS["r50k_base"]["sha256"], "306cd27f03c1a714eca7108e03d66b7dc042abe8c258b44c199a7ed9838dd930")

    def test_un_vocabulario_corrupto_se_rechaza(self):
        import tempfile
        import vocab_local as vl
        d = Path(tempfile.mkdtemp())
        (d / "r50k_base.tiktoken").write_bytes(b"AAAA 0\n")
        anterior = vl.VOCAB_DIR
        try:
            vl.VOCAB_DIR = d
            with self.assertRaises(ValueError):
                vl.verificar_vocabulario("r50k_base")
            with self.assertRaises(FileNotFoundError):
                vl.verificar_vocabulario("o200k_base")
        finally:
            vl.VOCAB_DIR = anterior

    def test_tokenizadores_estrictos_no_omiten_en_silencio(self):
        try:
            import tiktoken  # noqa: F401
        except ImportError:
            self.skipTest("requiere tiktoken")
        import comun
        t = comun.tokenizadores(["o200k_base", "cl100k_base", "r50k_base"])
        self.assertEqual({n: x.backend for n, x in t.items()}, {"o200k_base": "tiktoken", "cl100k_base": "tiktoken", "r50k_base": "tiktoken"})
        self.assertEqual(t["r50k_base"].count(""), 0)
        self.assertGreater(t["r50k_base"].count("{\"campo\": 1}"), 0)
        with self.assertRaises(RuntimeError):
            comun.tokenizadores(["no_existe_base"])


if __name__ == "__main__":
    unittest.main()
