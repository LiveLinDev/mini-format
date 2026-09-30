"""V3a: lectores de salida truncada, con oráculos calculables a mano (experiments/truncamiento/lectores.py).

El documento de referencia tiene 3 registros; para cada posición de corte se sabe, sin ejecutar ningún lector,
cuántos registros completos hay (los que terminan en o antes del corte).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
for _p in (ROOT / "experiments", ROOT / "src"):
    sys.path.insert(0, str(_p))

from truncamiento import lectores as R  # noqa: E402
from truncamiento import nucleo as N  # noqa: E402
from truncamiento.documentos import canon, construir_json_compacto, construir_jsonl  # noqa: E402

# ---- documento de 3 registros; las cadenas llevan llaves, corchetes, comillas escapadas y Unicode a propósito
REG = [
    {"id": 1, "t": "x{y}[z]", "v": 10},
    {"id": 2, "t": 'q"}],{', "v": 20},
    {"id": 3, "t": "adiós ñ 日本", "v": 30},
]
DOC = {"header": {"n": 3, "k": "h}"}, "items": REG}
TEXTO = json.dumps(DOC, ensure_ascii=False, separators=(",", ":"))


def _fines_a_mano(texto: str, registros) -> list:
    """Índice (en caracteres) donde termina cada registro: buscando su texto, sin usar ningún lector."""
    fines, desde = [], 0
    for r in registros:
        s = json.dumps(r, ensure_ascii=False, separators=(",", ":"))
        i = texto.index(s, desde)
        desde = i + len(s)
        fines.append(desde)
    return fines


FINES = _fines_a_mano(TEXTO, REG)


def _disponibles(p: int) -> int:
    return sum(1 for f in FINES if f <= p)


# ------------------------------------------------------------------ casos literales, contados a mano
CORTE_A = '{"header":{"n":3,"k":"h}"},"items":[{"id":1,"t":"x{y}[z]","v":10},{"id":2,"t":"q\\"}],{","v":2'
# registro 1 completo; el 2 llega con v=2 en lugar de 20 (valor final cortado)


def test_corte_a_mano_un_registro_completo_y_otro_con_el_valor_final_cortado():
    assert json.loads(TEXTO) == DOC
    assert R.leer_json_estricto(CORTE_A, "items").registros == []
    objs = R.leer_json_objetos_completos(CORTE_A, "items").registros
    assert objs == [REG[0]]
    assert R.leer_jsonl(CORTE_A, True).registros == []  # no hay saltos de línea: la línea 1 es la envoltura incompleta
    pytest.importorskip("jiter")
    parcial = R.leer_json_parcial_jiter(CORTE_A, "items").registros
    assert parcial[0] == REG[0]
    assert parcial[1] == {"id": 2, "t": 'q"}],{', "v": 2}   # jiter entrega el valor cortado como si fuera el dato
    m = N.clasificar(parcial, REG, disp=1, solicitados=3)
    assert (m["disponibles"], m["recuperados"], m["espurios"], m["identicos"]) == (1, 1, 1, 1)
    assert m["precision"] == 0.5 and m["recall_disponibles"] == 1.0 and m["recall_solicitados"] == pytest.approx(1 / 3)


def test_texto_completo_lo_leen_todos_los_json():
    assert R.leer_json_estricto(TEXTO, "items").registros == REG
    assert R.leer_json_objetos_completos(TEXTO, "items").registros == REG
    pytest.importorskip("jiter")
    assert R.leer_json_parcial_jiter(TEXTO, "items").registros == REG


# ------------------------------------------------------------------ todas las posiciones de corte
def test_escaner_propio_emite_exactamente_los_registros_completos_en_cada_corte():
    for p in range(len(TEXTO) + 1):
        esperado = REG[: _disponibles(p)]
        got = R.leer_json_objetos_completos(TEXTO[:p], "items").registros
        assert got == esperado, f"corte {p}: {TEXTO[:p]!r}"


def test_escaner_propio_es_causal():
    completo = R.escanear_elementos(TEXTO, "items")
    for p in range(len(TEXTO) + 1):
        parcial = R.escanear_elementos(TEXTO[:p], "items")
        assert parcial == completo[: len(parcial)]


def test_json_estricto_solo_lee_el_documento_completo():
    for p in range(len(TEXTO)):
        assert R.leer_json_estricto(TEXTO[:p], "items").registros == [], p
    assert len(R.leer_json_estricto(TEXTO, "items").registros) == 3


def test_jiter_recupera_todo_lo_disponible_en_cada_corte_y_solo_emite_a_lo_sumo_un_parcial_extra():
    pytest.importorskip("jiter")
    for p in range(len(TEXTO) + 1):
        pre = TEXTO[:p]
        lec = R.leer_json_parcial_jiter(pre, "items")
        m = N.clasificar(lec.registros, REG, _disponibles(p), 3)
        assert m["recuperados"] == _disponibles(p), f"corte {p}"
        assert m["duplicados"] == 0
        # solo el último elemento puede estar incompleto
        assert m["espurios"] + m["completados_heuristicamente"] <= 1


# ------------------------------------------------------------------ escáner: estructura
def test_la_clave_anidada_con_el_mismo_nombre_no_confunde_al_escaner():
    t = '{"meta":{"items":[{"x":1}]},"items":[{"id":1},{"id":2}],"otro":[{"z":9}]}'
    assert R.leer_json_objetos_completos(t, "items").registros == [{"id": 1}, {"id": 2}]


def test_arreglo_en_la_raiz():
    t = '[{"id":1,"a":[{"n":1}]},{"id":2,"a":[]},{"id":3'
    assert R.leer_json_objetos_completos(t, None).registros == [{"id": 1, "a": [{"n": 1}]}, {"id": 2, "a": []}]


def test_cadena_sin_cerrar_con_delimitadores_dentro_no_emite_nada():
    t = '{"items":[{"id":1},{"t":"abc}],{'
    assert R.leer_json_objetos_completos(t, "items").registros == [{"id": 1}]
    t2 = '{"items":[{"id":1},{"t":"abc\\'       # termina en una barra de escape
    assert R.leer_json_objetos_completos(t2, "items").registros == [{"id": 1}]


def test_las_claves_con_el_nombre_de_los_registros_dentro_de_cadenas_se_ignoran():
    t = '{"header":{"note":"\\"items\\":["},"items":[{"id":1}]}'
    assert R.leer_json_objetos_completos(t, "items").registros == [{"id": 1}]


def test_elementos_que_no_son_objetos_se_ignoran():
    t = '{"items":[1,{"id":2},"x",[3],{"id":4}]}'
    assert R.leer_json_objetos_completos(t, "items").registros == [{"id": 2}, {"id": 4}]


# ------------------------------------------------------------------ JSON Lines
def test_jsonl_descarta_la_linea_final_incompleta_y_salta_la_envoltura():
    tx = construir_jsonl({"header": {"n": 3}}, REG).texto
    lineas = tx.split("\n")
    assert len(lineas) == 5 and lineas[-1] == ""          # envoltura + 3 registros + fin
    fines = _fines_a_mano_jsonl(tx)
    for p in range(len(tx) + 1):
        got = R.leer_jsonl(tx[:p], True).registros
        assert got == REG[: sum(1 for f in fines if f <= p)], p


def _fines_a_mano_jsonl(tx: str):
    out, pos = [], 0
    for i, linea in enumerate(tx.split("\n")[:-1]):
        pos += len(linea)
        if i >= 1:
            out.append(pos)
        pos += 1
    return out


def test_jsonl_acepta_la_ultima_linea_sin_lf_si_es_un_objeto_completo():
    assert R.leer_jsonl('{"a":1}\n{"a":2}', False).registros == [{"a": 1}, {"a": 2}]
    assert R.leer_jsonl('{"a":1}\n{"a":', False).registros == [{"a": 1}]


# ------------------------------------------------------------------ construcción de desplazamientos
def test_fines_por_construccion_coinciden_con_los_calculados_buscando_el_texto():
    tf = construir_json_compacto(DOC, "items")
    assert tf.texto == TEXTO
    en_bytes = [len(TEXTO[:f].encode("utf-8")) for f in FINES]
    assert tf.fines == en_bytes


def test_fines_json_con_arreglo_en_la_raiz_y_con_cola():
    doc = [{"a": 1}, {"a": "ñ"}]
    tf = construir_json_compacto(doc, None)
    assert tf.texto == '[{"a":1},{"a":"ñ"}]'
    # '[' (1) + '{"a":1}' (7) = 8; ',' (1) + '{"a":"ñ"}' (9 caracteres, 10 bytes) = 19
    assert tf.fines == [8, 19]
    doc2 = {"items": [{"a": 1}], "total": 9}
    tf2 = construir_json_compacto(doc2, "items")
    # '{"items":' (9) + '[' (1) + '{"a":1}' (7) = 17
    assert tf2.texto == '{"items":[{"a":1}],"total":9}' and tf2.fines == [17]


# ------------------------------------------------------------------ .mini tolerante
MINI = ("cls|n=3|d=20260603|l=es|model=m|k=3\n"
        "m1|hola|a*,b,c|0.91|x\n"
        "m2|adiós|a,b*,c|0.5|yy\n"
        "m3|uno|a,b,c*|0.75|z")
MINI_REF = [
    {"id": "m1", "text": "hola", "labels": ["a", "b", "c"], "selected": [0], "conf": 0.91, "rationale": "x"},
    {"id": "m2", "text": "adiós", "labels": ["a", "b", "c"], "selected": [1], "conf": 0.5, "rationale": "yy"},
    {"id": "m3", "text": "uno", "labels": ["a", "b", "c"], "selected": [2], "conf": 0.75, "rationale": "z"},
]


@pytest.fixture(scope="module")
def cls_contract():
    from minifmt import Registry
    return Registry.load(ROOT / "forks").get("cls")


def _fines_mini(texto: str):
    out, pos = [], 0
    for i, linea in enumerate(texto.split("\n")):
        pos += len(linea.encode("utf-8"))
        if i >= 1:
            out.append(pos)
        pos += 1
    return out


def test_mini_texto_completo(cls_contract):
    assert R.leer_mini_tolerante(MINI, cls_contract, truncado=False).registros == MINI_REF


def test_mini_corte_despues_del_campo_final_completo_de_la_linea_2(cls_contract):
    # "m2|adiós|a,b*,c|0.5|yy" completo, sin LF: el registro 2 está disponible y el lector tolerante lo acepta.
    pre = MINI[: MINI.index("m3") - 1]
    lec = R.leer_mini_tolerante(pre, cls_contract, truncado=True)
    assert lec.registros == MINI_REF[:2]
    # variante sin cola: el consumidor descarta la última línea sin LF (aquí pierde un registro disponible)
    assert R.leer_mini_tolerante(pre, cls_contract, truncado=True, sin_cola=True).registros == MINI_REF[:1]
    # si el texto NO se cortó, la variante no descarta nada
    assert R.leer_mini_tolerante(MINI, cls_contract, truncado=False, sin_cola=True).registros == MINI_REF


@pytest.mark.parametrize("corte,rationale_emitido", [("|0.5|y", "y"), ("|0.5|", None)])
def test_mini_corte_en_el_campo_final_emite_un_registro_valido_pero_espurio(cls_contract, corte, rationale_emitido):
    """'…|0.5|y' (de 'yy') y '…|0.5|' son líneas VÁLIDAS pero distintas de la referencia: el riesgo del .mini sin cierre."""
    pre = MINI[: MINI.index(corte) + len(corte)]
    lec = R.leer_mini_tolerante(pre, cls_contract, truncado=True)
    assert [r["id"] for r in lec.registros] == ["m1", "m2"]
    assert lec.registros[1]["rationale"] == rationale_emitido
    disp = sum(1 for f in _fines_mini(MINI) if f <= len(pre.encode("utf-8")))
    assert disp == 1                        # a mano: solo m1 terminó
    m = N.clasificar(lec.registros, MINI_REF, disp, 3)
    assert (m["emitidos"], m["recuperados"], m["espurios"], m["duplicados"], m["completados_heuristicamente"]) == (2, 1, 1, 0, 0)
    assert m["precision"] == 0.5 and m["recall_disponibles"] == 1.0
    # la variante sin cola evita ese registro espurio
    lec2 = R.leer_mini_tolerante(pre, cls_contract, truncado=True, sin_cola=True)
    assert N.clasificar(lec2.registros, MINI_REF, disp, 3)["espurios"] == 0


def test_mini_corte_antes_del_ultimo_campo_se_descarta_por_aridad(cls_contract):
    pre = MINI[: MINI.index("|0.5") + len("|0.5")]        # faltan 'rationale' completo: 4 campos < 5
    assert R.leer_mini_tolerante(pre, cls_contract, truncado=True).registros == MINI_REF[:1]


def test_mini_corte_en_cualquier_posicion_recupera_todo_lo_disponible(cls_contract):
    fines = _fines_mini(MINI)
    datos = MINI.encode("utf-8")
    for p in range(len(datos) + 1):
        try:
            pre = datos[:p].decode("utf-8")
        except UnicodeDecodeError:
            continue                                   # corte dentro de 'ó': el prefijo real descarta la cola incompleta
        lec = R.leer_mini_tolerante(pre, cls_contract, truncado=p < len(datos))
        disp = sum(1 for f in fines if f <= p)
        m = N.clasificar(lec.registros, MINI_REF, disp, 3)
        assert m["recuperados"] == disp, f"corte {p}: {pre!r}"
        assert m["duplicados"] == 0


def test_mini_corte_a_mitad_de_la_cabecera_no_emite_nada(cls_contract):
    for p in range(len("cls|n=3|d=20260603|l=es|model=m|k=3")):
        assert R.leer_mini_tolerante(MINI[:p], cls_contract, truncado=True).registros == [], p


def test_mini_corte_a_mitad_del_texto_del_registro_2_solo_deja_el_1(cls_contract):
    # "m2|adi": 2 campos < aridad 5 -> la línea cortada se descarta (E02); recupera solo m1
    pre = MINI[: MINI.index("adi") + 3]
    lec = R.leer_mini_tolerante(pre, cls_contract, truncado=True)
    assert lec.registros == MINI_REF[:1]


def test_mini_domain_lee_linea_a_linea_y_omite_la_linea_cortada():
    from minifmt import domain as dom
    doc = {"total": 9, "rows": [{"a": 1, "b": "uno"}, {"a": 2, "b": "dos"}, {"a": 3, "b": "tres"}]}
    c = dom.infer_contract([doc], prefix="t")
    texto = dom.encode(doc, c)
    lineas = texto.split("\n")
    assert len(lineas) == 4
    # texto completo
    assert R.leer_mini_tolerante(texto, c, truncado=False).registros == doc["rows"]
    # cortada la última línea a la mitad de una celda numérica/cadena
    pre = "\n".join(lineas[:3]) + "\n" + lineas[3][:1]
    lec = R.leer_mini_tolerante(pre, c, truncado=True)
    assert lec.registros[:2] == doc["rows"][:2]
    # cabecera cortada: nada
    assert R.leer_mini_tolerante(lineas[0][:10], c, truncado=True).registros == []
    # misma lectura que diagnose() de la biblioteca sobre qué líneas son válidas
    diag = dom.diagnose(pre, c)
    assert len(lec.registros) == len(diag["valid_lines"])


def test_un_arreglo_hermano_anterior_no_se_confunde_con_el_de_registros():
    t = '{"otro":[{"z":9}],"items":[{"id":1},{"id":2}]}'
    assert R.leer_json_objetos_completos(t, "items").registros == [{"id": 1}, {"id": 2}]
    # si aún no ha empezado el arreglo de registros, no hay nada que emitir
    assert R.leer_json_objetos_completos('{"otro":[{"z":9}],"it', "items").registros == []
