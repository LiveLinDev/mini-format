"""Reparación selectiva equivalente para JSON (A+1, B+1, C+1) y auditoría de identidades (también para .mini)."""
from __future__ import annotations

import json

import pytest

from minifmt.ai import merge_repair, repair_request

from arnes import auditoria as AU
from arnes import brazos as B
from arnes import json_tolerante as J
from arnes import tareas as T


@pytest.fixture(scope="module")
def cls():
    return T.construir("ext-cls")


def _doc(t, mut=None):
    """Documento JSON de referencia de la tarea, con una mutación opcional sobre la lista de registros."""
    regs = [B._registro_json(r, t.contrato) for r in t.registros]
    if mut:
        mut(regs)
    return json.dumps({t.contrato.records_key: regs}, ensure_ascii=False, indent=1)


# ------------------------------------------------------------------ escáner tolerante
def test_dividir_documento_valido(cls):
    items, _ = J.dividir_registros(_doc(cls), "messages")
    assert len(items) == len(cls.registros) and all(i.objeto is not None and i.error is None for i in items)


def test_un_objeto_roto_no_invalida_a_los_demas(cls):
    texto = _doc(cls).replace('"id": "m3"', '"id": "m3" "x"', 1)           # coma que falta: json.loads rechaza TODO el documento
    with pytest.raises(ValueError):
        json.loads(texto)
    items, _ = J.dividir_registros(texto, "messages")
    malos = [i for i in items if i.objeto is None]
    assert len(items) == len(cls.registros) and len(malos) == 1 and "JSON inválido" in malos[0].error


def test_salto_de_linea_crudo_y_comilla_suelta_dentro_de_una_cadena(cls):
    texto = _doc(cls)
    texto = texto.replace('"conf": 0.91', '"conf": 0.91', 1)
    roto = texto.replace("Tengo", 'Tengo "una\ncomilla" suelta', 1) if "Tengo" in texto else None
    # construye el caso directamente sobre un objeto conocido
    doc = '{"messages": [{"id": "a", "text": "dijo "hola" y\nse fue", "labels": ["x"], "selected": [0], "conf": 0.5}, {"id": "b", "text": "ok", "labels": ["x"], "selected": [0], "conf": 0.5}]}'
    items, _ = J.dividir_registros(doc, "messages")
    assert len(items) == 2 and items[0].objeto is None and items[1].objeto["id"] == "b"


def test_truncado_marca_el_ultimo_objeto_incompleto(cls):
    texto = _doc(cls)
    corte = texto[: texto.index('"id": "m6"') + 25]
    items, _ = J.dividir_registros(corte, "messages")
    assert items[-1].incompleto and items[-1].objeto is None
    assert all(not i.incompleto for i in items[:-1])


def test_sin_lista_no_es_reparable_y_null_es_un_descarte(cls):
    assert J.dividir_registros("lo siento, no puedo", "messages")[0] is None
    items, _ = J.dividir_registros('{"messages": [null, {"id": "a"}]}', "messages")
    assert items[0].nulo and items[1].objeto == {"id": "a"}


# ------------------------------------------------------------------ clasificación y solicitud
def test_clasifica_contrato_identidad_y_no_objetos(cls):
    def mut(regs):
        regs[1]["conf"] = "alta"                   # tipo
        regs[3]["id"] = regs[0]["id"]              # identidad repetida
        regs[5]["labels"] = None                   # obligatorio nulo
    items, _ = J.dividir_registros(_doc(cls, mut), "messages")
    rech = J.clasificar_items(items, cls)
    assert [r.item.indice for r in rech] == [1, 3, 5]
    assert rech[1].identidad_repetida and "identidad repetida" in rech[1].motivos[0]
    assert "conf" in rech[0].motivos[0]


def test_la_solicitud_lleva_solo_lo_rechazado(cls):
    def mut(regs):
        regs[2]["conf"] = 7.0                      # fuera de rango 0..1
    sol = J.solicitud_reparacion_json(_doc(cls, mut), cls, "SISTEMA-BASE")
    assert sol.needed and sol.lines == [3] and "SISTEMA-BASE" in sol.system
    assert "[O3]" in sol.user and "E13 [conf]" in sol.user                         # el diagnóstico del validador viaja
    validos = [B._registro_json(r, cls.contrato)["id"] for i, r in enumerate(cls.registros) if i != 2]
    # ningún objeto válido se reenvía
    assert not any(f'"id": "{v}"' in sol.user for v in validos)
    assert not J.solicitud_reparacion_json(_doc(cls), cls, "S").needed


# ------------------------------------------------------------------ fusión
def _rep(obj_list, clave="messages"):
    return json.dumps({clave: obj_list}, ensure_ascii=False)


def test_fusion_acepta_la_correccion_y_no_toca_los_validos(cls):
    def mut(regs):
        regs[2]["conf"] = 7.0
    original = _doc(cls, mut)
    sol = J.solicitud_reparacion_json(original, cls, "S")
    bueno = B._registro_json(cls.registros[2], cls.contrato)
    f = J.fusionar_json(original, _rep([bueno]), sol, cls)
    assert f.ok and f.reemplazados == [3] and f.registros[2] == bueno
    validos_antes = [B._registro_json(r, cls.contrato) for i, r in enumerate(cls.registros) if i != 2]
    assert [r for i, r in enumerate(f.registros) if i != 2] == validos_antes      # intactos y en su posición
    assert len(f.registros) == len(cls.registros)


def test_fusion_rechaza_identidad_duplicada(cls):
    def mut(regs):
        regs[2]["conf"] = 7.0
    original = _doc(cls, mut)
    sol = J.solicitud_reparacion_json(original, cls, "S")
    otro = B._registro_json(cls.registros[0], cls.contrato)                # devuelve el registro 1 en lugar del 3
    f = J.fusionar_json(original, _rep([otro]), sol, cls)
    assert not f.ok and f.sin_resolver == [3] and f.rechazos_identidad_duplicada == 1
    ids = [r["id"] for r in f.registros]
    assert len(ids) == len(set(ids)) and len(f.registros) == len(cls.registros) - 1


def test_fusion_rechaza_identidad_inventada(cls):
    def mut(regs):
        regs[2]["conf"] = 7.0
    original = _doc(cls, mut)
    sol = J.solicitud_reparacion_json(original, cls, "S")
    inventado = dict(B._registro_json(cls.registros[2], cls.contrato), id="zz99")
    f = J.fusionar_json(original, _rep([inventado]), sol, cls)
    assert f.rechazos_identidad_inventada == 1 and f.sin_resolver == [3]


def test_fusion_identidad_repetida_puede_cambiar_a_una_nueva(cls):
    def mut(regs):
        regs[3]["id"] = regs[0]["id"]
    original = _doc(cls, mut)
    sol = J.solicitud_reparacion_json(original, cls, "S")
    nuevo = dict(B._registro_json(cls.registros[3], cls.contrato), id="nuevo-1")
    f = J.fusionar_json(original, _rep([nuevo]), sol, cls)
    assert f.ok and f.reemplazados == [4] and len({r["id"] for r in f.registros}) == len(cls.registros)


def test_fusion_correccion_aun_invalida_null_y_conteo_distinto(cls):
    def mut(regs):
        regs[1]["conf"] = 9.0
        regs[4]["conf"] = 9.0
    original = _doc(cls, mut)
    sol = J.solicitud_reparacion_json(original, cls, "S")
    sigue_mal = dict(B._registro_json(cls.registros[1], cls.contrato), conf=9.0)
    f = J.fusionar_json(original, _rep([sigue_mal, None]), sol, cls)
    assert f.sin_resolver == [2] and f.descartados == [5] and not f.ok
    f2 = J.fusionar_json(original, _rep([B._registro_json(cls.registros[1], cls.contrato)]), sol, cls)
    assert any("se esperaban 2" in n for n in f2.notas) and f2.sin_resolver == [5]


def test_rondas_encadenadas_conservan_lo_no_resuelto(cls):
    def mut(regs):
        regs[1]["conf"] = 9.0
    original = _doc(cls, mut)
    sol1 = J.solicitud_reparacion_json(original, cls, "S")
    f1 = J.fusionar_json(original, _rep([{"id": "m2"}]), sol1, cls)        # respuesta inútil
    assert f1.sin_resolver == [2]
    sol2 = J.solicitud_reparacion_json(f1.texto, cls, "S", items=f1.items)    # el objeto roto sigue en la lista de ítems
    assert sol2.needed and sol2.lines == [2]
    f2 = J.fusionar_json(f1.texto, _rep([B._registro_json(cls.registros[1], cls.contrato)]), sol2, cls)
    assert f2.ok and len(f2.registros) == len(cls.registros)


# ------------------------------------------------------------------ auditoría independiente
def test_auditar_json_cuenta_duplicados_y_sobrescritos(cls):
    items, _ = J.dividir_registros(_doc(cls), "messages")
    finales = [i.objeto for i in items]
    ok = AU.auditar_json(items, [], finales, cls.contrato, 0)
    assert ok["validos_sobrescritos"] == 0 and ok["identidades_duplicadas_finales"] == 0
    malo = list(finales)
    malo[1] = dict(malo[0])                                             # identidad duplicada Y se perdió el válido m2
    r = AU.auditar_json(items, [], malo, cls.contrato, 2)
    assert r["validos_sobrescritos"] == 1 and r["identidades_duplicadas_finales"] == 1
    assert r["correcciones_rechazadas_identidad"] == 2


def test_auditar_mini_detecta_identidad_duplicada_e_inventada(cls):
    c = cls.contrato
    doc = B.salida_referencia(cls, "D")
    lineas = doc.split("\n")
    roto = list(lineas)
    roto[3] = "x|solo dos campos"                                        # línea rota (era m3)
    original = "\n".join(roto)
    # corrección que duplica la identidad de otra línea
    dup = list(lineas)
    dup[3] = lineas[1]
    r = AU.auditar_mini(original, "\n".join(dup), [4], ["x|solo dos campos"], c)
    assert r["identidades_duplicadas_finales"] == 1 and r["validos_sobrescritos"] == 0
    # corrección con una identidad que no era la de la línea rota
    inv = list(lineas)
    inv[3] = lineas[3].replace(lineas[3].split("|")[0], "zz9", 1)
    r2 = AU.auditar_mini(original, "\n".join(inv), [4], ["x|solo dos campos"], c)
    assert r2["identidades_inventadas"] == 1 and r2["identidades_duplicadas_finales"] == 0
    # si la línea válida cambia, se marca el sobrescrito
    sobre = list(lineas)
    sobre[2] = sobre[2].replace("|", "|X", 1)
    assert AU.auditar_mini(original, "\n".join(sobre), [4], ["x|solo dos campos"], c)["validos_sobrescritos"] == 1


def test_contrato_sin_identidad_da_none_no_cero():
    t = T.construir("ext-log")                                          # log no tiene campo unique
    assert AU.identidades_mini(B.salida_referencia(t, "D"), t.contrato) is None
    r = AU.auditar_json([], [], [], t.contrato, 0)
    assert r["identidades_duplicadas_finales"] is None and r["identidades_inventadas"] is None


def test_merge_repair_del_nucleo_y_la_auditoria_son_coherentes(cls):
    """Tolera el arreglo D-3 del núcleo: con o sin él, la auditoría marca duplicados si y solo si se aceptó una corrección duplicada."""
    c = cls.contrato
    lineas = B.salida_referencia(cls, "D").split("\n")
    roto = list(lineas)
    roto[3] = roto[3].replace("|", ";", 2)                                # rompe la línea 4 (aridad)
    original = "\n".join(roto)
    req = repair_request(original, c, "es")
    assert req.needed and req.lines == [4]
    respuesta = f"cls|n=1\n{lineas[1]}"                                   # devuelve el contenido del registro 2 (identidad repetida)
    merged = merge_repair(original, respuesta, c, req)
    aud = AU.auditar_mini(req.document, merged.text, req.lines, [i.text for i in req.items], c)
    aceptada = bool(merged.replaced)
    assert (aud["identidades_duplicadas_finales"] > 0) == aceptada
    # si no se aceptó la corrección, no queda ninguna identidad repetida ni se toca un registro válido
    if not aceptada:
        assert aud["identidades_duplicadas_finales"] == 0 and aud["validos_sobrescritos"] == 0
