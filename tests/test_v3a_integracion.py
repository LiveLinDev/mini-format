"""V3a: invariantes de la evaluación completa sobre documentos reales del repositorio (experimentos/truncamiento)."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
for _p in (ROOT / "experiments", ROOT / "src", ROOT / "tools", ROOT / "benchmark"):
    sys.path.insert(0, str(_p))

pytest.importorskip("tiktoken")
pytest.importorskip("regex")
pytest.importorskip("yaml")
pytest.importorskip("numpy")

from truncamiento import corte as K  # noqa: E402
from truncamiento import documentos as D  # noqa: E402
from truncamiento import lectores as R  # noqa: E402
from truncamiento import nucleo as N  # noqa: E402

NOMBRES = ("ner", "cat", "comments", "earthquakes")


@pytest.fixture(scope="module")
def enc():
    return K.cargar_o200k()


@pytest.fixture(scope="module")
def docs():
    return {"ner": D.construir_dominio("ner"), "cat": D.construir_dominio("cat"),
            "comments": D.construir_snapshot("comments"), "earthquakes": D.construir_snapshot("earthquakes")}


@pytest.fixture(scope="module")
def evaluacion(docs, enc):
    out = {}
    for nombre, d in docs.items():
        filas, info, exc = N.evaluar_documento(d, enc)
        out[nombre] = (filas, info, exc)
    return out


def test_la_precondicion_de_integridad_se_cumple(docs):
    for d in docs.values():
        assert d.exclusiones == {}, d.exclusiones
        assert d.n == 50 and len(d.registros) == 50
        assert d.referencia_mini is not None and len(d.referencia_mini) == 50


def test_documentos_estan_etiquetados(docs):
    assert docs["ner"].sintetico and docs["ner"].tipo == "dominio_sintetico"
    assert docs["comments"].tipo == "snapshot_prueba_publica" and docs["comments"].sintetico
    assert docs["earthquakes"].tipo == "snapshot_real" and not docs["earthquakes"].sintetico


def test_el_texto_completo_tiene_los_50_registros_disponibles_en_todos_los_formatos(docs):
    for d in docs.values():
        for f, t in d.textos.items():
            assert len(t.fines) == 50
            assert N.disponibles(t.fines, len(t.texto.encode("utf-8"))) == 50
            assert t.fines == sorted(t.fines)


def test_fines_por_construccion_coinciden_con_el_escaner_independiente_en_cada_corte(docs, enc):
    """Dos algoritmos distintos (desplazamientos construidos vs escáner de llaves) deben contar lo mismo."""
    for d in docs.values():
        seg = K.segmentar(enc, d.textos["json"].texto)
        for k in range(1, 21):
            pre = K.prefijo_por_tokens(seg, K.limite_k(k, seg.n_tokens))
            esperado = N.disponibles(d.textos["json"].fines, pre.n_bytes)
            assert len(R.escanear_elementos(pre.texto, d.clave)) == esperado, (d.id, k)


def test_invariantes_de_las_filas(evaluacion):
    for nombre, (filas, info, exc) in evaluacion.items():
        assert exc == []
        assert len(filas) == 20 * len(N.CONDICIONES)
        for f in filas:
            assert 0 <= f["recuperados"] <= f["disponibles"] <= f["solicitados"] == 50, f
            assert f["recuperados"] <= f["identicos"] <= f["emitidos"]
            assert f["emitidos"] == f["identicos"] + f["duplicados"] + f["espurios"]
            assert f["completados_heuristicamente"] == f["identicos"] - f["recuperados"]
            assert (f["recall_disponibles"] is None) == (f["disponibles"] == 0)
            assert (f["precision"] is None) == (f["emitidos"] == 0)
            assert f["limite_tokens"] == K.limite_k(f["k"], f["tokens_ref_json"])
            assert f["truncado"] == (f["limite_tokens"] < f["tokens_texto"])


def test_todo_es_monotono_en_k(evaluacion):
    for nombre, (filas, info, exc) in evaluacion.items():
        for cond in N.CONDICIONES:
            fs = sorted((f for f in filas if f["condicion"] == cond.nombre), key=lambda f: f["k"])
            assert [f["k"] for f in fs] == list(range(1, 21))
            for campo in ("disponibles", "recuperados", "bytes_prefijo", "limite_tokens"):
                v = [f[campo] for f in fs]
                assert v == sorted(v), (nombre, cond.nombre, campo, v)


def test_json_estricto_no_recupera_nada_hasta_que_cabe_entero(evaluacion):
    for nombre, (filas, info, exc) in evaluacion.items():
        for f in (f for f in filas if f["condicion"] == "json_estricto"):
            assert f["recuperados"] == (50 if f["k"] == 20 else 0), (nombre, f["k"])
            assert f["disponibles"] >= f["recuperados"]


@pytest.mark.parametrize("cond", ["jsonl", "json_objetos_completos", "mini_tolerante"])
def test_los_lectores_capaces_recuperan_todo_lo_disponible_en_cada_corte(evaluacion, cond):
    for nombre, (filas, info, exc) in evaluacion.items():
        for f in (f for f in filas if f["condicion"] == cond):
            assert f["recuperados"] == f["disponibles"], (nombre, cond, f["k"])
            assert f["duplicados"] == 0
    # y los dos JSON que jamás emiten parciales tienen precisión perfecta
    if cond in ("jsonl", "json_objetos_completos"):
        for nombre, (filas, info, exc) in evaluacion.items():
            assert all(f["espurios"] == 0 for f in filas if f["condicion"] == cond)


def test_jiter_recupera_lo_disponible_y_a_lo_sumo_emite_un_parcial(evaluacion):
    pytest.importorskip("jiter")
    for nombre, (filas, info, exc) in evaluacion.items():
        for f in (f for f in filas if f["condicion"] == "json_parcial_jiter"):
            assert f["recuperados"] == f["disponibles"], (nombre, f["k"])
            assert f["espurios"] + f["completados_heuristicamente"] <= 1


def test_sin_cola_nunca_emite_espurios_y_pierde_a_lo_sumo_un_registro(evaluacion):
    for nombre, (filas, info, exc) in evaluacion.items():
        por_k = {(f["condicion"], f["k"]): f for f in filas}
        for k in range(1, 21):
            a, b = por_k[("mini_tolerante", k)], por_k[("mini_tolerante_sin_cola", k)]
            assert b["espurios"] == 0
            assert 0 <= a["recuperados"] - b["recuperados"] <= 1
            if not b["truncado"]:
                assert a["recuperados"] == b["recuperados"]     # sin corte, la variante no descarta nada


def test_mini_cabe_completo_antes_que_json_porque_usa_menos_tokens(docs, enc):
    for d in docs.values():
        nj = K.segmentar(enc, d.textos["json"].texto).n_tokens
        nm = K.segmentar(enc, d.textos["mini"].texto).n_tokens
        assert nm < nj


def test_la_evaluacion_es_determinista(docs, enc):
    a = N.evaluar_documento(docs["ner"], enc)[0]
    b = N.evaluar_documento(docs["ner"], enc)[0]
    assert a == b


def test_ejecutar_rapido_no_escribe_evidencia(tmp_path):
    pytest.importorskip("matplotlib")
    import ejecutar_v3a as E
    antes = sorted(p.name for p in (ROOT / "evidencia").glob("corridas/*")) if (ROOT / "evidencia" / "corridas").exists() else []
    assert E.main(["--rapido", "--salida", str(tmp_path / "salida")]) == 0
    despues = sorted(p.name for p in (ROOT / "evidencia").glob("corridas/*")) if (ROOT / "evidencia" / "corridas").exists() else []
    assert antes == despues
    assert (tmp_path / "salida" / "cortes.csv").exists() and (tmp_path / "salida" / "figura_v3a.png").exists()
