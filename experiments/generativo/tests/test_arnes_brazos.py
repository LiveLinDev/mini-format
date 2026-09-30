"""Condiciones del Plan de Validación v3: A (JSON mínimo), B, C, D y los brazos X+1; paridad y aplicabilidad."""
from __future__ import annotations

import json

import pytest

from arnes import brazos as B
from arnes import ejecucion as X
from arnes import metricas as M
from arnes import tareas as T
from arnes.ejecucion import ErrorConfig, validar_config


@pytest.fixture(scope="module")
def cls():
    return T.construir("ext-cls")


@pytest.fixture(scope="module")
def card():
    return T.construir("gen-card")


def test_conjunto_de_brazos_es_el_del_plan():
    assert {"A", "B", "C", "D"} <= set(B.BRAZOS_PRIMARIOS)
    assert set(B.BASE_REPARACION) == {"A+1", "B+1", "C+1", "D+1"}           # UNA reparación por cada formato
    assert "D+R" not in B.BRAZOS                                            # nombre del arnés anterior
    assert B.base_de("D+1") == "D" and B.base_de("C") == "C"
    assert [B.formato_de(b) for b in ("A", "B", "C", "D", "A0")] == ["json", "json", "json", "mini", "pipe"]


def test_A_es_json_con_instruccion_minima(cls):
    a = B.construir_prompt(cls, "A")
    b = B.construir_prompt(cls, "B")
    assert a.response_format is None and "JSON" in a.system
    # mínima: nombres de campo y forma, sin tipos, rangos, ejemplo ni reglas
    for nombre in B.nombres_json(cls.contrato):
        assert nombre in a.system
    for extra in ("Ejemplo", "entre 0 y 1", "opcional", "null", "lista de"):
        assert extra not in a.system
    # B sí lleva el contrato completo: es estrictamente más informativo que A
    assert len(b.system) > 2 * len(a.system)
    assert "entre 0 y 1" in b.system and "opcional" in b.system and "Ejemplo" in b.system


def test_B_y_C_tienen_el_mismo_contrato_y_C_agrega_la_restriccion_nativa(card):
    b, c = B.construir_prompt(card, "B"), B.construir_prompt(card, "C")
    assert b.system == c.system and b.response_format is None
    assert c.response_format["type"] == "json_schema" and c.response_format["schema"]["required"] == [card.contrato.records_key]


def test_paridad_de_contrato_entre_B_y_D(card):
    """B no puede saber menos que D: el rango de una lista y la descripción del dominio están en ambos."""
    b = B.construir_prompt(card, "B").system
    d = B.construir_prompt(card, "D").system
    assert "entre 0 y 8 elementos" in d and "entre 0 y 8 elementos" in b
    assert card.contrato.description in b and card.contrato.description in d


def test_mismo_mensaje_de_usuario_en_todos_los_brazos(cls):
    users = {B.construir_prompt(cls, b).user for b in B.BRAZOS}
    assert len(users) == 1


def test_lectores_de_brazos_de_reparacion_son_los_de_su_base(cls):
    ref = B.salida_referencia(cls, "B")
    assert M.evaluar(B.leer("B+1", ref, cls), cls)["exacto"]
    assert M.evaluar(B.leer("A", ref, cls), cls)["exacto"]
    mini = B.salida_referencia(cls, "D")
    assert M.evaluar(B.leer("D+1", mini, cls), cls)["exacto"]


def test_json_invalido_en_A_pierde_todo_pero_se_clasifica(cls):
    m = M.evaluar(B.leer("A", '{"messages": [{"id": "m1", "text": "hola "mundo""}]}', cls), cls)
    assert not m["sintaxis_ok"] and m["validos_finales"] == 0 and m["solicitados"] == len(cls.registros)


# ------------------------------------------------------------------ C no aplicable (no es un fallo)
def test_C_no_aplicable_queda_registrada_con_motivo():
    cfg = {"nombre": "x", "semilla": 1, "tareas": ["ext-cls"], "repeticiones": 1, "brazos": ["A", "C", "C+1", "D"],
           "modelos": [{"proveedor": "groq", "modelo": "llama-3.3-70b-versatile", "estructurado": False},
                       {"proveedor": "openai", "modelo": "gpt-4.1-mini", "estructurado": True}],
           "experimentos": {"v2": {"activo": True}}}
    cfg = dict(cfg, max_tokens=1000, idioma="es", temperatura=0, reparacion={}, controles={}, presupuesto={})
    en = X.enumerar_completo(cfg, X.Contexto(cfg))
    na = {x["id"]: x for x in en.no_aplicables}
    assert len(na) == 2 and all("llama" in i for i in na) and {x["brazo"] for x in na.values()} == {"C", "C+1"}
    assert all("estructurado" in x["motivo"] for x in na.values())
    # no figuran entre las celdas ejecutables ni se sustituyen por otra condición
    assert not [u for u in en.unidades if u.proveedor == "groq" and u.brazo in ("C", "C+1")]
    assert [u.brazo for u in en.unidades if u.proveedor == "groq"].count("A") == 1


def test_orden_aleatorizado_reproducible_y_con_semilla_registrada():
    cfg = {"nombre": "x", "semilla": 7, "tareas": ["ext-cls", "gen-card"], "repeticiones": 3, "brazos": ["A", "B", "D", "B+1", "D+1"],
           "modelos": [{"proveedor": "openai", "modelo": "gpt-4.1-mini", "estructurado": True}],
           "experimentos": {"v2": {"activo": True}}, "max_tokens": 1000, "idioma": "es", "temperatura": 0, "reparacion": {},
           "controles": {}, "presupuesto": {}}
    ctx = X.Contexto(cfg)
    a, b = X.enumerar_completo(cfg, ctx), X.enumerar_completo(cfg, ctx)
    assert [u.id for u in a.unidades] == [u.id for u in b.unidades] and a.orden_semilla == b.orden_semilla
    canon = X.enumerar_completo(dict(cfg, controles={"aleatorizar": False}), ctx)
    assert sorted(u.id for u in canon.unidades) == sorted(u.id for u in a.unidades)
    assert [u.id for u in canon.unidades] != [u.id for u in a.unidades]          # de verdad cambia el orden
    otra = X.enumerar_completo(dict(cfg, controles={"semilla_orden": 99}), ctx)
    assert [u.id for u in otra.unidades] != [u.id for u in a.unidades] and otra.orden_semilla == 99
    ids = [u.id for u in a.unidades]
    for u in a.unidades:
        if u.brazo.endswith("+1"):
            assert ids.index(u.id_brazo(u.brazo[:-2])) < ids.index(u.id)


def test_validar_config_rechaza_brazos_inconsistentes():
    base = {"tareas": ["ext-cls"], "modelos": [{"proveedor": "a", "modelo": "b"}], "repeticiones": 1,
            "experimentos": {"v2": {"activo": True}}}
    with pytest.raises(ErrorConfig, match="D\\+1"):
        validar_config(dict(base, brazos=["D+R"]))
    with pytest.raises(ErrorConfig, match="requiere"):
        validar_config(dict(base, brazos=["B+1"]))
    with pytest.raises(ErrorConfig):
        validar_config(dict(base, brazos=["A"], experimentos={"v3b": {"brazos": ["Z"]}}))
    validar_config(dict(base, brazos=["A", "A+1"]))


def test_politica_de_limite_v3b_comun_por_tarea(cls):
    cfg = {"tareas": ["ext-cls"], "idioma": "es"}
    ctx = X.Contexto(cfg)
    ecfg = {"fraccion_max_tokens": 0.5}
    lim = {b: X.limite_v3b(ecfg, ctx, cls, ["A", "B", "D"], b) for b in ("A", "B", "D")}
    assert len(set(lim.values())) == 1                                   # el MISMO límite para todos los brazos
    por_brazo = {b: X.limite_v3b(dict(ecfg, politica_limite="fraccion_por_brazo"), ctx, cls, ["A", "B", "D"], b) for b in ("A", "B", "D")}
    assert len(set(por_brazo.values())) > 1                              # la política anterior sí los distinguía
    assert X.limite_v3b({"politica_limite": "fijo", "limite_tokens": 300}, ctx, cls, ["A"], "A") == 300
