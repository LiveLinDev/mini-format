"""Comportamientos que la norma deja abiertos o contradice (ADR 0017, «Propuesta», no vigente).

Las pruebas ``expectedFailure`` afirman lo que SPEC §9 ya exige (ida y vuelta del objeto y estabilidad del
texto emitido) sobre objetos que el serializador acepta hoy y luego altera. Documentan el defecto sin
cambiar el comportamiento; si se adopta la propuesta pasan a ser pruebas ordinarias (mientras tanto, un
«éxito inesperado» hace fallar la suite y avisa de que hay que quitar la marca).

Las demás pruebas FIJAN el comportamiento actual (no normativo) para que un cambio sea deliberado.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from minifmt import Contract, MiniError, dumps, parse  # noqa: E402

C = Contract.from_dict({
    "prefix": "p", "records_key": "rows",
    "core": [{"name": "id", "type": "str"}],
    "extensions": [
        {"name": "opt", "type": "str"},
        {"name": "ls", "type": "list", "item": "str"},
        {"name": "dec", "type": "decimal"},
        {"name": "tp", "type": "tuple", "items": [{"name": "a", "type": "str"}, {"name": "b", "type": "str"}]},
    ],
})


def obj(**rec):
    return {"prefix": "p", "header": {"n": 1}, "rows": [dict({"id": "a"}, **rec)]}


def read_back(o):
    return parse(dumps(o, C), C).to_canonical()["rows"][0]


class RoundTripOfOuterWhitespace(unittest.TestCase):
    """D-1 (ADR 0017): SPEC §9 exige parse(dumps(o)) = o; hoy se pierde el espacio exterior sin aviso."""

    @unittest.expectedFailure
    def test_leading_space_is_preserved(self):
        self.assertEqual(read_back(obj(id=" a"))["id"], " a")

    @unittest.expectedFailure
    def test_trailing_space_is_preserved(self):
        self.assertEqual(read_back(obj(id="hola "))["id"], "hola ")

    @unittest.expectedFailure
    def test_non_breaking_space_is_preserved(self):
        self.assertEqual(read_back(obj(id=" x"))["id"], " x")

    @unittest.expectedFailure
    def test_empty_string_in_an_optional_field_is_preserved(self):
        self.assertEqual(read_back(obj(opt=""))["opt"], "")

    @unittest.expectedFailure
    def test_list_elements_with_outer_space_are_preserved(self):
        self.assertEqual(read_back(obj(ls=[" a", "b "]))["ls"], [" a", "b "])


class ListElementsTheSerializerCannotWrite(unittest.TestCase):
    """D-2 (ADR 0017): objetos válidos para los que dumps falla con un código que no describe la causa."""

    @unittest.expectedFailure
    def test_element_with_space_before_a_quote(self):
        self.assertEqual(read_back(obj(ls=[' "a']))["ls"], [' "a'])

    @unittest.expectedFailure
    def test_element_with_space_after_an_asterisk(self):
        self.assertEqual(read_back(obj(ls=["a* "]))["ls"], ["a* "])

    def test_current_behaviour_is_an_error_with_the_wrong_cause(self):
        with self.assertRaises(MiniError) as cm:
            dumps(obj(ls=[' "a']), C)
        self.assertEqual(cm.exception.code, "E09")
        with self.assertRaises(MiniError) as cm:
            dumps(obj(ls=["a* "]), C)
        self.assertEqual(cm.exception.code, "E08")


class DecimalStabilityOfTheEmittedText(unittest.TestCase):
    """D-4 (ADR 0017): SPEC §9, segunda cláusula: dumps(parse(t)) = t para todo t emitido por el serializador."""

    @unittest.expectedFailure
    def test_emitted_text_is_stable_for_a_non_canonical_decimal(self):
        for raw in ("007.50", "-0.0"):
            text = dumps(obj(dec=raw), C)
            self.assertEqual(dumps(parse(text, C).to_canonical(), C), text, raw)

    def test_current_behaviour_the_object_read_back_is_canonical(self):
        self.assertEqual(read_back(obj(dec="007.50"))["dec"], "7.50")
        self.assertEqual(read_back(obj(dec="-0.0"))["dec"], "0.0")


# Conjunto que hoy recortan las dos implementaciones (Python: str.isspace; TypeScript: lista copiada
# en ts/src/codec.ts). SPEC §3.5 no lo define (B-1, ADR 0017). U+000A separa líneas y no cuenta.
TRIMMED = [0x09, 0x0B, 0x0C, 0x0D, 0x1C, 0x1D, 0x1E, 0x1F, 0x20, 0x85, 0xA0, 0x1680, *range(0x2000, 0x200B),
           0x2028, 0x2029, 0x202F, 0x205F, 0x3000]
NOT_TRIMMED = [0x200B, 0x200C, 0x200D, 0x2060, 0xFEFF, 0x180E, 0x86, 0x00AD, 0x2800, 0x3164]


class WhitespaceSetOfTheReference(unittest.TestCase):
    """B-1 (ADR 0017): el conjunto de «whitespace» que recortan hoy las implementaciones (no normativo)."""

    def value_of(self, cp):
        ch = chr(cp)
        return parse("p|n=1\n" + ch + "x" + ch, C, strict=False).records[0]["id"]

    def test_listed_characters_are_trimmed_at_both_ends_of_a_field(self):
        for cp in TRIMMED:
            with self.subTest(cp=hex(cp)):
                self.assertEqual(self.value_of(cp), "x")

    def test_neighbouring_non_space_characters_are_kept(self):
        for cp in NOT_TRIMMED:
            with self.subTest(cp=hex(cp)):
                self.assertEqual(self.value_of(cp), chr(cp) + "x" + chr(cp))


if __name__ == "__main__":
    unittest.main()
