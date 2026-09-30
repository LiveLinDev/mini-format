"""V3a: métricas por corte y agregación por conglomerados (experiments/truncamiento/nucleo.py y analisis.py)."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
for _p in (ROOT / "experiments", ROOT / "src"):
    sys.path.insert(0, str(_p))

pytest.importorskip("numpy")

from truncamiento import analisis as A  # noqa: E402
from truncamiento import nucleo as N  # noqa: E402

REF = [{"id": i, "v": i * 10} for i in range(1, 6)]   # 5 registros


# ------------------------------------------------------------------ clasificar
def test_todo_recuperado():
    m = N.clasificar(REF[:3], REF, disp=3, solicitados=5)
    assert (m["recuperados"], m["emitidos"], m["espurios"], m["duplicados"], m["completados_heuristicamente"]) == (3, 3, 0, 0, 0)
    assert m["recall_disponibles"] == 1.0 and m["recall_solicitados"] == 0.6 and m["precision"] == 1.0


def test_cero_disponibles_es_null_y_no_cero_ni_uno():
    m = N.clasificar([], REF, disp=0, solicitados=5)
    assert m["recall_disponibles"] is None
    assert m["precision"] is None           # tampoco hay emitidos
    assert m["recall_solicitados"] == 0.0   # este denominador (n solicitados) nunca es cero


def test_cero_disponibles_pero_algo_emitido_sigue_sin_recall_y_baja_la_precision():
    m = N.clasificar([{"id": 1}], REF, disp=0, solicitados=5)   # un registro inventado/parcial antes de que haya nada completo
    assert m["recall_disponibles"] is None
    assert m["espurios"] == 1 and m["precision"] == 0.0


def test_inventados_no_cuentan():
    emitidos = REF[:2] + [{"id": 99, "v": 990}, {"id": 98, "v": 980}]
    m = N.clasificar(emitidos, REF, disp=2, solicitados=5)
    assert (m["recuperados"], m["espurios"], m["emitidos"]) == (2, 2, 4)
    assert m["precision"] == 0.5 and m["recall_disponibles"] == 1.0


def test_duplicados_no_cuentan_ni_inflan_el_recall():
    emitidos = [REF[0], REF[0], REF[1], REF[1], REF[1]]
    m = N.clasificar(emitidos, REF, disp=2, solicitados=5)
    assert m["recuperados"] == 2 and m["duplicados"] == 3 and m["espurios"] == 0
    assert m["recall_disponibles"] == 1.0 and m["precision"] == pytest.approx(2 / 5)


def test_completado_heuristicamente_no_cuenta_como_recuperado():
    # el lector emite el registro 3 idéntico a la referencia, pero su texto NO estaba completo en el prefijo
    m = N.clasificar(REF[:3], REF, disp=2, solicitados=5)
    assert m["identicos"] == 3 and m["recuperados"] == 2 and m["completados_heuristicamente"] == 1
    assert m["recall_disponibles"] == 1.0
    assert m["precision"] == pytest.approx(2 / 3)


def test_registro_parcial_con_valor_cortado_es_espurio():
    emitidos = [REF[0], {"id": 2, "v": 2}]          # v=20 llegó como 2
    m = N.clasificar(emitidos, REF, disp=1, solicitados=5)
    assert (m["recuperados"], m["espurios"]) == (1, 1) and m["precision"] == 0.5


def test_referencia_con_registros_repetidos_usa_multiconjunto():
    ref = [{"a": 1}, {"a": 1}, {"a": 2}]
    m = N.clasificar([{"a": 1}, {"a": 1}], ref, disp=2, solicitados=3)
    assert (m["recuperados"], m["duplicados"], m["espurios"]) == (2, 0, 0)
    m2 = N.clasificar([{"a": 1}, {"a": 1}, {"a": 1}], ref, disp=3, solicitados=3)
    assert m2["duplicados"] == 1 and m2["recuperados"] == 2


def test_la_clasificacion_no_depende_del_orden_de_claves():
    assert N.clasificar([{"b": 2, "a": 1}], [{"a": 1, "b": 2}], 1, 1)["recuperados"] == 1


def test_disponibles_por_desplazamiento():
    fines = [10, 20, 30]
    assert [N.disponibles(fines, p) for p in (0, 9, 10, 11, 20, 29, 30, 99)] == [0, 0, 1, 1, 2, 2, 3, 3]


# ------------------------------------------------------------------ razón por conglomerados
def test_razon_a_mano():
    r = A.razon_conglomerados([1, 3], [2, 4], "t")
    assert r["punto"] == pytest.approx(4 / 6, abs=1e-6) and r["n_documentos"] == 2


def test_razon_con_denominador_total_cero_es_null():
    r = A.razon_conglomerados([0, 0], [0, 0], "t")
    assert r["punto"] is None and r["ic95_inf"] is None


def test_razon_un_solo_documento_no_inventa_intervalo():
    r = A.razon_conglomerados([3], [4], "t")
    assert r["punto"] == 0.75 and r["ic95_inf"] is None and r["ic95_sup"] is None


def test_datos_constantes_dan_ic_degenerado():
    r = A.razon_conglomerados([9] * 6, [10] * 6, "t")
    assert r["punto"] == 0.9 and r["ic95_inf"] == pytest.approx(0.9) and r["ic95_sup"] == pytest.approx(0.9)


def test_el_ic_por_documento_es_mas_ancho_que_tratar_los_cortes_como_independientes():
    """4 documentos muy distintos, 20 cortes idénticos cada uno: el IC de conglomerados refleja solo 4 observaciones."""
    p_doc = [0.2, 0.4, 0.6, 0.8]
    num = [p * 100 for p in p_doc]
    den = [100.0] * 4
    r = A.razon_conglomerados(num, den, "t")
    ancho_conglomerado = r["ic95_sup"] - r["ic95_inf"]
    # IC de Wilson tratando los 400 cortes como independientes (la crítica a la versión anterior)
    import math
    n, p = 400, sum(num) / sum(den)
    z = 1.96
    medio = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / (1 + z * z / n)
    assert ancho_conglomerado > 3 * (2 * medio)


def test_documentos_sin_disponibles_no_distorsionan_la_razon():
    a = A.razon_conglomerados([5, 0], [10, 0], "t")
    b = A.razon_conglomerados([5], [10], "t")
    assert a["punto"] == b["punto"] == 0.5


def test_bootstrap_es_determinista():
    a = A.razon_conglomerados([1, 2, 3, 4], [4, 4, 4, 4], "x")
    b = A.razon_conglomerados([1, 2, 3, 4], [4, 4, 4, 4], "x")
    assert a == b


# ------------------------------------------------------------------ criterio primario
def _fila(doc, k, rec, disp, truncado=True, cond="mini_tolerante", emitidos=None):
    e = rec if emitidos is None else emitidos
    return {"documento": doc, "tipo": "dominio_sintetico", "condicion": cond, "k": k, "truncado": truncado,
            "recuperados": rec, "disponibles": disp, "emitidos": e, "solicitados": 50, "espurios": e - rec,
            "duplicados": 0, "completados_heuristicamente": 0, "fallo_lector": False, "limite_tokens": 10 * k,
            "tokens_ref_json": 200, "tokens_texto": 150}


def test_criterio_umbral_exacto_cumple():
    filas = [_fila("d1", 1, 9, 10), _fila("d2", 1, 9, 10)]
    c = A.criterio_primario(filas)
    assert c["punto"] == 0.9 and c["veredicto_regla_fijada"] == "cumple" and c["aprobacion_asesor"] == "pendiente"


def test_criterio_por_debajo_no_cumple():
    c = A.criterio_primario([_fila("d1", 1, 8, 10), _fila("d1", 2, 9, 10)])
    assert c["punto"] == pytest.approx(17 / 20) and c["veredicto_regla_fijada"] == "no_cumple"


def test_criterio_excluye_cortes_sin_disponibles_y_los_cuenta():
    filas = [_fila("d1", 1, 0, 0), _fila("d1", 2, 10, 10), _fila("d2", 1, 0, 0)]
    c = A.criterio_primario(filas)
    assert c["punto"] == 1.0 and c["n_cortes_excluidos_disponibles_cero"] == 2 and c["n_cortes_total"] == 3


def test_criterio_solo_truncados_separa_los_cortes_completos():
    filas = [_fila("d1", 1, 5, 10, truncado=True), _fila("d1", 2, 10, 10, truncado=False)]
    c = A.criterio_primario(filas)
    assert c["punto"] == 0.75 and c["solo_truncados"]["punto"] == 0.5 and c["solo_truncados"]["n_cortes"] == 1


def test_criterio_sin_ningun_disponible_es_no_evaluable():
    c = A.criterio_primario([_fila("d1", 1, 0, 0), _fila("d2", 1, 0, 0)])
    assert c["punto"] is None and c["veredicto_regla_fijada"] == "no_evaluable"


def test_criterio_solo_mira_la_condicion_primaria():
    filas = [_fila("d1", 1, 10, 10), _fila("d1", 1, 0, 10, cond="jsonl")]
    assert A.criterio_primario(filas)["punto"] == 1.0
    assert A.criterio_primario(filas, "jsonl")["punto"] == 0.0


def test_precision_excluye_cortes_sin_emitidos_y_los_cuenta():
    filas = [_fila("d1", 1, 0, 0, emitidos=0), _fila("d1", 2, 4, 4, emitidos=5)]
    r = A.resumen_condicion(filas, "t")
    assert r["precision"]["punto"] == 0.8 and r["precision"]["n_cortes_sin_emitidos_null"] == 1
    assert r["n_cortes_disponibles_cero"] == 1
