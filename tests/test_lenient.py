"""Modo tolerante: recuperación parcial y diagnóstico de líneas a regenerar."""
from __future__ import annotations

import json
import unittest
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from minifmt import MiniValidationError, Registry, parse  # noqa: E402

REG = Registry.load(ROOT / "forks")
A = REG.get("a")
A_TEXT = (ROOT / "forks/a/fixtures/valid.mini").read_text(encoding="utf-8").rstrip("\n")
LINES = A_TEXT.split("\n")


def lenient(text, contract=A):
    return parse(text, contract, strict=False)


def strict_codes(text, contract=A):
    try:
        parse(text, contract)
    except MiniValidationError as e:
        return [(x.code, x.line) for x in e.errors]
    return []


class TestLenientRecovery(unittest.TestCase):
    def test_valid_document_has_clean_diagnostics(self):
        doc = lenient(A_TEXT)
        self.assertTrue(doc.ok)
        self.assertEqual(doc.invalid_lines(), [])
        self.assertEqual(doc.missing_records, 0)
        self.assertFalse(doc.truncated)
        self.assertEqual(doc.record_lines, list(range(2, 14)))
        self.assertEqual(doc.header_line, 1)
        d = doc.diagnostics()
        self.assertEqual(d["valid_records"], 12)
        json.dumps(d)  # serialisable

    def test_truncated_last_record_is_reported_with_its_line(self):
        cut = A_TEXT[: A_TEXT.rindex("|5|arte")]  # cut in the middle of the last record
        doc = lenient(cut)
        self.assertEqual(len(doc.records), 11)
        self.assertEqual(doc.invalid_lines(), [13])
        self.assertTrue(doc.truncated)
        self.assertEqual(doc.missing_records, 0)
        self.assertEqual(sorted((e.code, e.line) for e in doc.errors), [("E05", 13)])
        # strict mode rejects the same document with the same error
        self.assertEqual(strict_codes(cut), [("E05", 13)])

    def test_truncated_after_complete_lines_reports_missing_records(self):
        text = "\n".join(LINES[:6])  # header + 5 records, n=12
        doc = lenient(text)
        self.assertEqual(len(doc.records), 5)
        self.assertEqual(doc.missing_records, 7)
        self.assertTrue(doc.truncated)
        self.assertEqual(doc.invalid_lines(), [])
        self.assertEqual([(e.code, e.line) for e in doc.document_errors()], [("E04", 0)])

    def test_truncated_inside_escape_is_dangling_backslash(self):
        text = "\n".join(LINES[:11] + [LINES[11][: LINES[11].index("\\") + 1]])
        doc = lenient(text)
        self.assertEqual(len(doc.records), 10)
        self.assertEqual(doc.invalid_lines(), [12])
        self.assertTrue(doc.truncated)
        self.assertIn("E09", [e.code for e in doc.errors])

    def test_invalid_middle_lines_are_listed_for_regeneration(self):
        lines = list(LINES)
        lines[3] = lines[3].replace("|L3|", "|L9|")          # E10 on line 4
        lines[7] = lines[7].replace("newton*", "newton")     # E08 on line 8
        lines[9] = lines[9].replace("porque*", "porque\\q")  # E09 on line 10
        doc = lenient("\n".join(lines))
        self.assertEqual(len(doc.records), 9)
        self.assertEqual(doc.invalid_lines(), [4, 8, 10])
        self.assertFalse(doc.truncated)
        self.assertNotIn(4, doc.record_lines)
        self.assertEqual([r["id"] for r in doc.records], ["i1", "i2", "i4", "i5", "i6", "i8", "i10", "i11", "i12"])

    def test_lenient_invalid_escape_is_reported_not_silently_accepted(self):
        text = "\n".join([LINES[0].replace("n=12", "n=1"), LINES[1].replace("Biología", "Bio\\logía")])
        doc = lenient(text)
        self.assertEqual([(e.code, e.line) for e in doc.errors], [("E09", 2)])
        self.assertEqual(doc.records, [])
        self.assertFalse(doc.ok)

    def test_header_escape_error_is_a_validation_error(self):
        bad = A_TEXT.replace("t=evaluación transversal", "t=eval\\uación", 1)
        self.assertEqual(strict_codes(bad), [("E09", 1)])
        doc = lenient(bad)
        self.assertEqual(len(doc.records), 12)
        self.assertEqual([e.code for e in doc.header_errors()], ["E09"])
        dangling = A_TEXT.replace("|k=4", "|k=4\\", 1)
        self.assertEqual(strict_codes(dangling), [("E09", 1)])
        self.assertEqual(lenient(dangling).header["k"], 4)

    def test_rejected_record_does_not_claim_unique_value(self):
        lines = list(LINES)
        lines[1] = lines[1].replace("|1|biología", "|9|biología")  # line 2 invalid (E13), id i1
        lines[2] = lines[2].replace("i2|", "i1|", 1)                 # line 3 valid, id i1
        doc = lenient("\n".join(lines))
        self.assertEqual([(e.code, e.line) for e in doc.errors], [("E13", 2)])
        self.assertEqual(doc.records[0]["id"], "i1")
        self.assertEqual(doc.record_lines[0], 3)

    def test_duplicate_of_accepted_record_is_rejected(self):
        lines = list(LINES)
        lines[2] = lines[2].replace("i2|", "i1|", 1)
        doc = lenient("\n".join(lines))
        self.assertEqual([(e.code, e.line) for e in doc.errors], [("E11", 3)])
        self.assertEqual(doc.invalid_lines(), [3])

    def test_error_to_dict(self):
        doc = lenient(A_TEXT.replace("cloroplastos*", "cloroplastos"))
        self.assertEqual(doc.diagnostics()["errors"][0]["code"], "E08")
        self.assertEqual(set(doc.errors[0].to_dict()), {"code", "line", "field", "message"})

    def test_unique_list_values_are_hashable(self):
        from minifmt import Contract
        c = Contract.from_dict({"prefix": "u", "core": [{"name": "tags", "type": "list", "unique": True}]})
        doc = parse("u|n=2\na,b\na,b", c, strict=False)
        self.assertEqual([(e.code, e.line) for e in doc.errors], [("E11", 3)])


if __name__ == "__main__":
    unittest.main(verbosity=2)
