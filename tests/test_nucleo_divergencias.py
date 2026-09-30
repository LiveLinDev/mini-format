"""Divergencias Python <-> TypeScript halladas por el fuzz diferencial de la auditoría V5.

1. ``\\=`` en una clave de cabecera (SPEC §3.2, §3.3, §5): defecto de la implementación Python, ya corregido.
2. Enteros mayores que 2^53: Python es exacto; TypeScript pierde precisión (ts/test/bigint.test.ts). La SPEC
   no fija una precisión máxima para ``int``; la decisión está pendiente (docs/adr/0018-*.md, «Propuesta»),
   aquí solo se fija el comportamiento exacto de la referencia Python.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from minifmt import Contract, dumps, parse  # noqa: E402

HD = Contract.from_dict({
    "prefix": "hd", "records_key": "rows",
    "header": {"required": ["n", "src"], "keys": {"src": {"type": "str"}, "lang": {"type": "str", "default": "es"}}},
    "core": [{"name": "id", "type": "str"}],
})
BI = Contract.from_dict({"prefix": "bi", "records_key": "rows", "core": [{"name": "id", "type": "int"}]})


def codes(doc):
    return sorted((e.code, e.line) for e in doc.errors)


class EscapedEqualsInHeader(unittest.TestCase):
    """Oráculo: la norma, no el otro motor. Sin '=' sin escapar no hay separador (E12); '\\=' es E09."""

    def test_unknown_key_with_escaped_equals_is_dropped_with_e09_and_e12(self):
        doc = parse("hd|n=1|src=s|foo\\=bar\nx", HD, strict=False)
        self.assertEqual(codes(doc), [("E09", 1), ("E12", 1)])
        self.assertEqual(doc.header, {"n": 1, "src": "s", "lang": "es", "v": 1})
        self.assertFalse(any("foo" in k for k in doc.header), "no debe quedar una clave rota")
        self.assertEqual(len(doc.records), 1)

    def test_n_written_with_escaped_equals_is_missing(self):
        doc = parse("hd|n\\=1|src=s\nx", HD, strict=False)
        self.assertEqual(codes(doc), [("E03", 1), ("E09", 1), ("E12", 1)])
        self.assertNotIn("n", doc.header)

    def test_escaped_equals_after_the_separator_is_only_an_invalid_escape(self):
        doc = parse("hd|n=1|src=a\\=b\nx", HD, strict=False)
        self.assertEqual(codes(doc), [("E09", 1)])

    def test_valid_equals_signs_in_values_stay_literal(self):
        doc = parse("hd|n=1|src=a=b=c\nx", HD, strict=False)
        self.assertEqual(doc.errors, [])
        self.assertEqual(doc.header["src"], "a=b=c")


class BigIntegersPython(unittest.TestCase):
    """Python entrega y escribe enteros arbitrariamente grandes sin pérdida."""

    def test_parse_is_exact_beyond_2_53(self):
        for text in ("9007199254740993", "-9007199254740993", "123456789012345678901234567890", str(2 ** 64)):
            doc = parse("bi|n=1\n" + text, BI)
            self.assertEqual(doc.records[0]["id"], int(text))

    def test_dumps_is_exact_beyond_2_53(self):
        value = 2 ** 60 + 2 ** 8
        out = dumps({"prefix": "bi", "header": {"n": 1}, "rows": [{"id": value}]}, BI)
        self.assertEqual(out, "bi|n=1\n" + str(value))
        self.assertEqual(parse(out, BI).records[0]["id"], value)


if __name__ == "__main__":
    unittest.main()
