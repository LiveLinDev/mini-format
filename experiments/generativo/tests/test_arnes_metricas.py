"""Sintaxis, cumplimiento del contrato y exactitud del contenido por separado; validez sobre TODOS los solicitados."""
from __future__ import annotations

import json

import pytest

from arnes import brazos as B
from arnes import ejecucion as X
from arnes import metricas as M
from arnes import tareas as T
from arnes.brazos import Lectura


@pytest.fixture(scope="module")
def cls():
    return T.construir("ext-cls")


@pytest.fixture(scope="module")
def card():
    return T.construir("gen-card")


def _json(t, mut=None, n=None):
    regs = [B._registro_json(r, t.contrato) for r in t.registros]
    if mut:
        mut(regs)
    if n is not None:
        regs = regs[:n]
    return json.dumps({t.contrato.records_key: regs}, ensure_ascii=False)


def test_referencia_perfecta_todo_en_su_maximo(cls):
    m = M.evaluar(B.leer("B", _json(cls), cls), cls)
    n = len(cls.registros)
    assert (m["sintaxis_ok"], m["solicitados"], m["validos_contrato"], m["validos_finales"], m["exactos_contenido"]) == (True, n, n, n, n)
    assert m["identidades_duplicadas"] == 0 and m["excedentes"] == 0


def test_valido_por_contrato_pero_inexacto_en_contenido(cls):
    """Un registro que cumple el contrato pero dice otra cosa NO es exacto: las dos medidas no se funden."""
    def mut(regs):
        regs[0]["text"] = "Texto distinto pero perfectamente válido"
    m = M.evaluar(B.leer("B", _json(cls, mut), cls), cls)
    n = len(cls.registros)
    assert m["validos_contrato"] == n and m["validos_finales"] == n          # cumple el contrato...
    assert m["exactos_contenido"] == n - 1 and not m["exacto"]                # ...pero no es lo que había en la entrada


def test_sintaxis_valida_sin_cumplir_contrato(cls):
    def mut(regs):
        regs[2]["conf"] = 5.0                     # fuera de rango
        regs[3]["conf"] = "alta"                  # tipo
    m = M.evaluar(B.leer("B", _json(cls, mut), cls), cls)
    assert m["sintaxis_ok"] is True
    assert m["aceptados"] == len(cls.registros) and m["validos_contrato"] == len(cls.registros) - 2


def test_los_ausentes_cuentan_en_el_denominador(cls):
    n = len(cls.registros)
    m = M.evaluar(B.leer("B", _json(cls, n=4), cls), cls)
    assert m["solicitados"] == n and m["validos_finales"] == 4 and m["aceptados"] == 4
    assert round(m["validos_finales"] / m["solicitados"], 4) == round(4 / n, 4)       # validez sobre lo SOLICITADO, no sobre lo recibido
    m0 = M.evaluar(B.leer("B", "sin lista", cls), cls)
    assert m0["solicitados"] == n and m0["validos_finales"] == 0 and m0["sintaxis_ok"] is False


def test_generativa_contrato_unicidad_y_excedentes(card):
    n = card.n_solicitados

    def mut(regs):
        regs[1]["id"] = regs[0]["id"]             # identidad repetida
        regs[2]["bloom"] = "L9"                   # enumeración
    m = M.evaluar(B.leer("B", _json(card, mut), card), card)
    assert m["identidades_duplicadas"] == 1 and m["validos_contrato"] == n - 2 and m["exactos_contenido"] is None
    # documento con más registros de los pedidos: el exceso no infla la validez
    def dup(regs):
        regs.extend([dict(regs[0], id=f"x{i}") for i in range(3)])
    m2 = M.evaluar(B.leer("B", _json(card, dup), card), card)
    assert m2["validos_finales"] == n and m2["excedentes"] == 3


def test_d_lector_solo_entrega_registros_validos(cls):
    doc = B.salida_referencia(cls, "D")
    lineas = doc.split("\n")
    lineas[2] = "m3|solo dos campos"
    m = M.evaluar(B.leer("D", "\n".join(lineas), cls), cls)
    n = len(cls.registros)
    assert m["sintaxis_ok"] and m["validos_contrato"] == n - 1 and m["validos_finales"] == n - 1 and m["perdidos_detectados"] == 1
    assert m["detectado"]                      # el lector avisó de la línea rota


def test_desenlaces_categoricos(cls):
    lect = B.leer("B", "respuesta rara", cls)
    assert X.clasificar_desenlace("openai", {"text": "respuesta rara", "stop_reason": "stop"}, lect, False) == "formato_invalido"
    assert X.clasificar_desenlace("openai", {"text": "", "stop_reason": "stop"}, B.leer("B", "", cls), False) == "vacia"
    assert X.clasificar_desenlace("openai", {"text": "{", "stop_reason": "length"}, lect, True) == "truncada"
    assert X.clasificar_desenlace("openai", None, None, False) == "error_tecnico"
    assert X.clasificar_desenlace("openai", {"text": "x", "stop_reason": "refusal"}, lect, False) == "negativa"
    ok = B.leer("B", _json(cls), cls)
    assert X.clasificar_desenlace("openai", {"text": _json(cls), "stop_reason": "stop"}, ok, False) == "ok"
    # orden de prioridad: una negativa truncada es negativa
    assert X.clasificar_desenlace("openai", {"text": "x", "stop_reason": "refusal"}, lect, True) == "negativa"


def test_lectura_vacia_no_divide_por_cero(cls):
    m = M.evaluar(Lectura([], [], parseable=False), cls)
    assert m["validos_contrato"] == 0 and m["validos_finales"] == 0 and m["aceptados"] == 0
