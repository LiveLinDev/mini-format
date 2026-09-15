"""Lectores por brazo, métricas por muestra, esquema JSON e intervalos de Wilson."""
from __future__ import annotations

import json
import math

import pytest

from arnes import brazos as B
from arnes import metricas as M
from arnes import tareas as T
from arnes.estadistica import fmt_ic, wilson


@pytest.fixture(scope="module")
def tc():
    return T.construir("ext-tc")


@pytest.fixture(scope="module")
def cls():
    return T.construir("ext-cls")


@pytest.fixture(scope="module")
def gen_card():
    return T.construir("gen-card")


# ------------------------------------------------------------------ Wilson
def test_wilson_valores_conocidos():
    p, lo, hi = wilson(5, 10)
    assert p == 0.5 and math.isclose(lo, 0.2366, abs_tol=1e-4) and math.isclose(hi, 0.7634, abs_tol=1e-4)
    p, lo, hi = wilson(0, 10)
    assert lo == 0.0 and math.isclose(hi, 0.2775, abs_tol=1e-4)
    p, lo, hi = wilson(10, 10)
    assert hi == 1.0 and math.isclose(lo, 0.7225, abs_tol=1e-4)
    assert all(math.isnan(x) for x in wilson(0, 0))
    assert fmt_ic(0, 0) == "—"
    with pytest.raises(ValueError):
        wilson(11, 10)


# ------------------------------------------------------------------ tareas
def test_tareas_estresadas_contienen_caracteres_conflictivos(tc, cls):
    for t in (tc, cls):
        todo = json.dumps(t.registros, ensure_ascii=False)
        for ch in ('|', '\\"', ',', '\\n', '\\\\'):
            assert ch in todo, (t.id, ch)
        assert t.estres
    assert "<<<" in tc.texto_entrada or "<<<" in cls.texto_entrada


def test_catalogo_cubre_al_menos_diez_dominios():
    ids = T.catalogo()
    assert len({i.split("-", 1)[1] for i in ids}) >= 10
    assert any(i.startswith("gen-") for i in ids)


# ------------------------------------------------------------------ referencia perfecta
@pytest.mark.parametrize("brazo", ["B", "C", "D"])
def test_referencia_de_brazos_con_escape_es_exacta(tc, cls, brazo):
    for t in (tc, cls):
        texto = B.salida_referencia(t, brazo)
        m = M.evaluar(B.leer(brazo, texto, t), t)
        assert m["exacto"] and m["correctos"] == len(t.registros), (t.id, brazo, m)
        assert m["incorrectos_sin_aviso"] == 0 and m["avisos"] == 0


def test_brazo_A_corrompe_o_pierde_con_texto_real(cls):
    texto = B.salida_referencia(cls, "A")
    m = M.evaluar(B.leer("A", texto, cls), cls)
    assert not m["exacto"]
    assert m["incorrectos_sin_aviso"] > 0          # coma dentro de una etiqueta -> lista partida en silencio
    assert m["perdidos_detectados"] > 0            # barra vertical en el texto -> aridad incorrecta con aviso


def test_A_fila_de_encabezado_se_acepta_sin_aviso(tc):
    fila_enc = "|".join(f.name for f in tc.contrato.fields)
    texto = fila_enc + "\n" + B.salida_referencia(tc, "A")
    lect = B.leer("A", texto, tc)
    assert any(r["id"] == "id" for r in lect.registros)   # 'automated' -> False: nadie avisa
    m = M.evaluar(lect, tc)
    assert m["espurios"] >= 1


def test_json_invalido_pierde_todo_con_aviso(cls):
    m = M.evaluar(B.leer("B", "Aquí está: {\"messages\": [", cls), cls)
    assert not m["parseable"] and m["correctos"] == 0
    assert m["perdidos_detectados"] == len(cls.registros) and m["perdidos_sin_aviso"] == 0


def test_json_con_cercas_se_lee(cls):
    texto = "```json\n" + B.salida_referencia(cls, "B") + "\n```"
    assert M.evaluar(B.leer("B", texto, cls), cls)["exacto"]


def test_json_valor_distinto_es_incorrecto_sin_aviso(cls):
    obj = json.loads(B.salida_referencia(cls, "C"))
    obj["messages"][0]["conf"] = 0.1
    del obj["messages"][1]
    m = M.evaluar(B.leer("C", json.dumps(obj), cls), cls)
    assert m["incorrectos_sin_aviso"] == 1 and m["perdidos_sin_aviso"] == 1 and not m["detectado"]


def test_D_error_de_enumeracion_se_detecta(tc):
    texto = B.salida_referencia(tc, "D").replace("|high|", "|alta|", 1)
    m = M.evaluar(B.leer("D", texto, tc), tc)
    assert m["perdidos_detectados"] == 1 and m["incorrectos_sin_aviso"] == 0


def test_D_con_prosa_y_cercas(tc):
    texto = "Claro:\n```\n" + B.salida_referencia(tc, "D") + "\n```"
    assert M.evaluar(B.leer("D", texto, tc), tc)["exacto"]


def test_normalizacion_de_espacios_y_nulos():
    assert M.campo_igual("a\nb", "a b")
    assert M.campo_igual("", None)
    assert M.campo_igual(1, 1.0)
    assert not M.campo_igual(True, 1)


# ------------------------------------------------------------------ generativas
def test_generativa_contra_contrato(gen_card):
    obj = json.loads(B.salida_referencia(gen_card, "B"))
    m = M.evaluar(B.leer("B", json.dumps(obj), gen_card), gen_card)
    assert m["exacto"] and m["correctos"] == gen_card.n_solicitados
    obj["cards"][0]["bloom"] = "nivel-1"          # fuera de la enumeración
    obj["cards"][1]["ease"] = "2.5"               # tipo JSON incorrecto
    obj["cards"][2]["id"] = obj["cards"][3]["id"]  # id repetido (unique)
    m = M.evaluar(B.leer("B", json.dumps(obj), gen_card), gen_card)
    assert m["incorrectos_sin_aviso"] == 3 and m["correctos"] == gen_card.n_solicitados - 3


def test_generativa_faltan_registros(gen_card):
    texto = "\n".join(B.salida_referencia(gen_card, "A").split("\n")[:4])
    m = M.evaluar(B.leer("A", texto, gen_card), gen_card)
    assert 0 < m["aceptados"] <= 4
    assert m["perdidos"] == gen_card.n_solicitados - m["aceptados"]


# ------------------------------------------------------------------ prompts y esquema
def test_esquema_json_estricto(cls):
    esq = B.esquema_json(cls.contrato)
    reg = esq["properties"]["messages"]["items"]
    assert reg["additionalProperties"] is False
    assert set(reg["required"]) == set(reg["properties"]) == {"id", "text", "labels", "selected", "conf", "rationale"}
    assert reg["properties"]["rationale"]["anyOf"][1] == {"type": "null"}
    assert reg["properties"]["selected"]["type"] == "array"


def test_prompts_por_brazo(cls):
    pa, pb, pc, pd = (B.construir_prompt(cls, b) for b in "ABCD")
    assert "separados por |" in pa.system and pa.response_format is None
    assert pb.response_format is None and pc.response_format["type"] == "json_schema"
    assert "FORMATO .mini" in pd.system and "k=6" in pd.system
    assert pa.user == pb.user == pc.user == pd.user          # mismo contenido en todos los brazos
    assert B.construir_prompt(cls, "D+R").system == pd.system
