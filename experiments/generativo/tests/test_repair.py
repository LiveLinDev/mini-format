"""Reparación selectiva: construcción de la solicitud y fusión."""
from __future__ import annotations

import pytest

from minifmt import Registry, parse
from minifmt.ai import extract_document, invalid_items, merge_repair, repair_request

from conftest import ROOT

REG = Registry.load(ROOT / "forks")
CLS = REG.get("cls")
LOG = REG.get("log")
VALID = (ROOT / "forks/cls/fixtures/valid.mini").read_text(encoding="utf-8").strip()
LINES = VALID.split("\n")


def _doc(lines):
    return "\n".join(lines)


def _estropear():
    ls = list(LINES)
    ls[3] = ls[3].replace("question,", "question|", 1)     # separador de campo sin escapar -> E05
    ls[5] = ls[5].replace("|0.95|", "|x0.95|", 1)            # tipo -> E06
    return ls


# ------------------------------------------------------------ extract_document
def test_extract_quita_prosa_y_cercas():
    texto = "Aquí tienes:\n```mini\n" + VALID + "\n```\nEspero que sirva."
    assert extract_document(texto, CLS) == VALID


def test_extract_sin_cerca_conserva_prosa_final_como_linea_invalida():
    texto = "Resultado:\n" + VALID + "\nFin del documento"
    doc = extract_document(texto, CLS)
    assert doc.startswith("cls|") and doc.endswith("Fin del documento")
    assert [it.text for it in invalid_items(doc, CLS)] == ["Fin del documento"]


def test_extract_sin_cabecera_devuelve_texto_sin_cercas():
    assert extract_document("```\nhola\n```", CLS) == "hola"


# ------------------------------------------------------------ repair_request
def test_documento_valido_no_necesita_reparacion():
    req = repair_request(VALID, CLS, "es")
    assert not req.needed and req.items == []


def test_solicitud_contiene_solo_lineas_invalidas_y_sus_errores():
    ls = _estropear()
    req = repair_request(_doc(ls), CLS, "es")
    assert req.lines == [4, 6]
    assert "E05" in req.user and "E06" in req.user
    assert ls[3] in req.user and ls[5] in req.user
    for i, linea in enumerate(ls[1:], start=1):   # ninguna línea válida se reenvía
        if i not in (3, 5):
            assert linea not in req.user
    assert "cls|n=2" in req.user
    assert "FORMATO .mini" in req.system            # bloque de especificación incluido
    assert req.max_tokens_hint >= 64


def test_solicitud_sin_especificacion_y_con_contexto():
    req = repair_request(_doc(_estropear()), CLS, "en", include_spec=False, context="FUENTE-XYZ")
    assert ".mini FORMAT" not in req.system
    assert "FUENTE-XYZ" in req.user and "Source text" in req.user


def test_fragmentos_de_salto_de_linea_se_unen_en_un_item():
    ls = LINES[:]
    ls[2] = ls[2].replace("flashcards, ", "flashcards,\n", 1)   # salto de línea real dentro del texto
    req = repair_request(_doc(ls), CLS, "es")
    assert len(req.items) == 1
    assert req.items[0].lines == [3, 4]
    assert "fragmentos de un mismo registro" in req.user


def test_cabecera_invalida_se_incluye_como_item():
    ls = LINES[:]
    ls[0] = "cls|d=20260603|k=6"             # falta n -> E03
    req = repair_request(_doc(ls), CLS, "es")
    assert req.items[0].is_header and req.items[0].line == 1
    assert "cabecera" in req.user


# ------------------------------------------------------------ merge_repair
def test_merge_reemplaza_lineas_corregidas():
    ls = _estropear()
    original = "Nota previa\n```\n" + _doc(ls) + "\n```"
    req = repair_request(original, CLS, "es")
    respuesta = "cls|n=2\n" + LINES[3] + "\n" + LINES[5]
    m = merge_repair(original, respuesta, CLS, req)
    assert m.ok and m.replaced == [4, 6] and m.unresolved == []
    assert m.text == VALID
    assert parse(m.text, CLS).to_canonical() == parse(VALID, CLS).to_canonical()


def test_merge_sin_solicitud_recalcula_items():
    ls = _estropear()
    m = merge_repair(_doc(ls), "cls|n=2\n" + LINES[3] + "\n" + LINES[5], CLS)
    assert m.ok


def test_merge_rechaza_correccion_invalida_y_conserva_original():
    ls = _estropear()
    req = repair_request(_doc(ls), CLS, "es")
    m = merge_repair(_doc(ls), "cls|n=2\n" + LINES[3] + "\nm5|sigue|mal|x|", CLS, req)
    assert m.replaced == [4] and m.unresolved == [6]
    assert ls[5] in m.text.split("\n")
    assert not m.ok and any(e.line for e in m.errors)


def test_merge_marca_de_eliminacion():
    ls = LINES[:]
    ls.insert(4, "Comentario del modelo sin barras")
    req = repair_request(_doc(ls), CLS, "es")
    m = merge_repair(_doc(ls), "cls|n=1\n-", CLS, req)
    assert m.dropped == [5]
    assert m.ok and m.text == VALID


def test_merge_elimina_duplicado_devuelto_por_la_reparacion():
    ls = LINES[:]
    ls[3] = ls[3].replace("question,", "question|", 1)
    req = repair_request(_doc(ls), CLS, "es")
    m = merge_repair(_doc(ls), "cls|n=1\n" + LINES[2], CLS, req)   # devuelve un registro que ya existe
    assert m.dropped == [4]
    assert any("duplica" in n or "duplicates" in n for n in m.notes)
    assert m.text.count(LINES[2]) == 1


def test_merge_une_fragmentos():
    ls = LINES[:]
    ls[2] = ls[2].replace("flashcards, ", "flashcards,\n", 1)   # salto de línea real dentro del texto
    texto = _doc(ls)
    req = repair_request(texto, CLS, "es")
    m = merge_repair(texto, "cls|n=1\n" + LINES[2], CLS, req)
    assert m.replaced == [3, 4] and m.ok and m.text == VALID


def test_merge_corrige_cabecera():
    ls = LINES[:]
    ls[0] = "cls|d=20260603|k=6"
    req = repair_request(_doc(ls), CLS, "es")
    m = merge_repair(_doc(ls), "cls|n=1\n" + LINES[0], CLS, req)
    assert m.replaced == [1] and m.ok


def test_merge_no_oculta_registros_perdidos():
    ls = LINES[:-2]                           # truncado: n=12 pero hay 10 registros
    ls[-1] = ls[-1][:12]                      # última línea cortada a la mitad
    req = repair_request(_doc(ls), CLS, "es")
    m = merge_repair(_doc(ls), "cls|n=1\n" + LINES[-3], CLS, req)
    assert m.replaced == [len(ls)]
    assert [e.code for e in m.errors] == ["E04"]     # sigue avisando que faltan registros


def test_merge_respuesta_incompleta_o_sin_cabecera():
    ls = _estropear()
    req = repair_request(_doc(ls), CLS, "es")
    m = merge_repair(_doc(ls), LINES[3], CLS, req)            # sin cabecera y con una sola línea
    assert m.replaced == [4] and m.unresolved == [6]
    assert any("no header" in n for n in m.notes) and any("expected 2" in n for n in m.notes)


@pytest.mark.parametrize("respuesta", ["", "```\n```", "no puedo"])
def test_merge_respuesta_vacia(respuesta):
    ls = _estropear()
    req = repair_request(_doc(ls), CLS, "es")
    m = merge_repair(_doc(ls), respuesta, CLS, req)
    assert m.replaced == [] and set(m.unresolved) == {4, 6}
