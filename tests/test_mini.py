"""Test-suite of the .mini reference implementation (unittest / pytest compatible).

    python -m unittest discover -s tests -v
    pytest -q
"""
from __future__ import annotations

import json
import random
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from minifmt import (Contract, MiniValidationError, Registry, canonical_equal,  # noqa: E402
                     dumps, parse, roundtrip_ok, spec_block)
from minifmt import codec  # noqa: E402
from minifmt.errors import (E_ARITY, E_COUNT_MISMATCH, E_ENUM, E_ESCAPE, E_FORK, E_LIST_ARITY,  # noqa: E402
                            E_MARKER, E_NO_COUNT, E_RANGE, E_TYPE, E_UNIQUE, E_UNKNOWN_PREFIX, MiniError)

REG = Registry.load(ROOT / "forks")
A = REG.get("a")
A_TEXT = (ROOT / "forks/a/fixtures/valid.mini").read_text(encoding="utf-8")
A_CANON = json.loads((ROOT / "forks/a/fixtures/canonical.json").read_text(encoding="utf-8"))


def codes(text, contract=A):
    try:
        parse(text, contract)
    except MiniValidationError as e:
        return sorted(set(e.codes))
    return []


class TestCodec(unittest.TestCase):
    RESERVED = ["|", ",", "*", "\\", "\n", '"', ";", "=", " "]

    def test_escape_roundtrip_scalar_fuzz(self):
        rng = random.Random(7)
        alphabet = list("abcXYZ019 áéñ¿?") + self.RESERVED
        for _ in range(2000):
            s = "".join(rng.choice(alphabet) for _ in range(rng.randint(0, 12)))
            s = s.strip()  # surrounding whitespace is not significant by design
            enc = codec.escape_scalar(s)
            toks = codec.split_fields(enc, ",", 1)
            self.assertEqual(len(toks), 1, (s, enc))
            self.assertEqual(codec.text_of(toks[0]), s)

    def test_escape_roundtrip_list_fuzz(self):
        rng = random.Random(11)
        alphabet = list("ab 9é") + self.RESERVED
        for _ in range(2000):
            elems = ["".join(rng.choice(alphabet) for _ in range(rng.randint(1, 8))).strip() or "x" for _ in range(rng.randint(1, 5))]
            marked = rng.randrange(len(elems))
            enc = ",".join(codec.escape_element(e, ",") + ("*" if i == marked else "") for i, e in enumerate(elems))
            toks = codec.split_fields(enc, ",", 1)
            self.assertEqual(len(toks), 1)
            parsed = codec.split_list(toks[0], ",")
            self.assertEqual([t for t, _ in parsed], elems, enc)
            self.assertEqual([i for i, (_, m) in enumerate(parsed) if m], [marked])

    def test_dangling_backslash_is_error(self):
        with self.assertRaises(MiniError) as cm:
            codec.tokenize("abc\\", ",", 3)
        self.assertEqual(cm.exception.code, E_ESCAPE)

    def test_over_escaping_is_harmless(self):
        toks = codec.split_fields("Si 3x+6=18\\, x?", ",", 1)
        self.assertEqual(codec.text_of(toks[0]), "Si 3x+6=18, x?")


class TestParserA(unittest.TestCase):
    def test_valid_document(self):
        doc = parse(A_TEXT, A)
        self.assertEqual(len(doc.records), 12)
        self.assertEqual(doc.header["n"], 12)
        self.assertEqual(doc.records[10]["options"][0], "impacto, justicia y evidencia")
        self.assertEqual(doc.records[10]["correct"], 0)
        self.assertEqual(doc.records[0]["irt"], {"a": 0.9, "b": -1.0, "c": 0.25})

    def test_roundtrip_fixture(self):
        self.assertTrue(canonical_equal(parse(A_TEXT, A).to_canonical(), A_CANON))
        self.assertEqual(dumps(A_CANON, A), A_TEXT.rstrip("\n"))
        self.assertTrue(roundtrip_ok(A_CANON, A))

    def test_count_mismatch(self):
        self.assertEqual(codes(A_TEXT.replace("n=12", "n=13")), [E_COUNT_MISMATCH])

    def test_missing_n(self):
        self.assertIn(E_NO_COUNT, codes(A_TEXT.replace("|n=12", "")))

    def test_wrong_prefix(self):
        self.assertIn(E_UNKNOWN_PREFIX, codes("zz" + A_TEXT[1:]))

    def test_arity(self):
        lines = A_TEXT.strip().split("\n")
        lines[1] = "|".join(lines[1].split("|")[:5])
        self.assertEqual(codes("\n".join(lines)), [E_ARITY])
        lines = A_TEXT.strip().split("\n")
        lines[1] = lines[1] + "|extra"
        self.assertEqual(codes("\n".join(lines)), [E_ARITY])

    def test_marker_rules(self):
        self.assertEqual(codes(A_TEXT.replace("cloroplastos*", "cloroplastos")), [E_MARKER])
        self.assertEqual(codes(A_TEXT.replace("núcleo,", "núcleo*,", 1)), [E_MARKER])

    def test_type_enum_range_unique(self):
        self.assertEqual(codes(A_TEXT.replace("|L1|", "|L9|", 1)), [E_ENUM])
        self.assertEqual(codes(A_TEXT.replace("|0.9,-1,0.25|", "|x,-1,0.25|", 1)), [E_TYPE])
        self.assertEqual(codes(A_TEXT.replace("|1|biología", "|7|biología", 1)), [E_RANGE])
        self.assertEqual(codes(A_TEXT.replace("\ni2|", "\ni1|", 1)), [E_UNIQUE])

    def test_list_arity_from_header(self):
        # unescaped comma splits an option -> 5 elements, header says k=4
        self.assertEqual(codes(A_TEXT.replace("impacto\\, justicia", "impacto, justicia")), [E_LIST_ARITY])
        self.assertEqual(codes(A_TEXT.replace("|0.9,-1,0.25|", "|0.9,-1|", 1)), [E_LIST_ARITY])

    def test_lenient_mode_recovers_valid_records(self):
        bad = A_TEXT.replace("cloroplastos*", "cloroplastos")
        doc = parse(bad, A, strict=False)
        self.assertEqual(len(doc.records), 11)
        self.assertEqual([e.code for e in doc.errors], [E_MARKER])

    def test_crlf_bom_blank_lines(self):
        text = "﻿" + A_TEXT.replace("\n", "\r\n\r\n")
        self.assertEqual(len(parse(text, A).records), 12)

    def test_escaping_fixture(self):
        esc = (ROOT / "forks/a/fixtures/escaping.mini").read_text(encoding="utf-8")
        ref = json.loads((ROOT / "forks/a/fixtures/escaping.json").read_text(encoding="utf-8"))
        self.assertTrue(canonical_equal(parse(esc, A).to_canonical(), ref))
        self.assertIn("\n", ref["items"][0]["topic"])
        self.assertTrue(ref["items"][0]["options"][0].endswith("*"))


class TestAllForks(unittest.TestCase):
    def test_registry_invariants(self):
        self.assertEqual(REG.check(), [])
        self.assertGreaterEqual(len(REG.contracts), 14)

    def test_every_fork_roundtrips(self):
        for c in REG:
            p = REG.paths[c.prefix] / "fixtures"
            text = (p / "valid.mini").read_text(encoding="utf-8")
            ref = json.loads((p / "canonical.json").read_text(encoding="utf-8"))
            doc = parse(text, c)
            self.assertTrue(canonical_equal(doc.to_canonical(), ref), c.prefix)
            self.assertEqual(dumps(ref, c), text.rstrip("\n"), c.prefix)
            for bad in p.glob("bad_*.mini"):
                with self.assertRaises(MiniValidationError, msg=f"{c.prefix}/{bad.name}"):
                    parse(bad.read_text(encoding="utf-8"), c)

    def test_prompt_block_mentions_every_field(self):
        for c in REG:
            block = spec_block(c, "en")
            for f in c.fields:
                self.assertIn(f.name, block)
            self.assertIn(c.prefix + "|", block)


class TestForkProtocol(unittest.TestCase):
    def test_q_is_valid_fork_of_a(self):
        q = REG.get("q")
        self.assertEqual(q.check_fork_of(A), [])
        self.assertEqual([f.name for f in q.core], [f.name for f in A.core])

    def test_fork_that_reorders_core_is_rejected(self):
        d = A.to_dict()
        d["prefix"], d["parent"] = "bad", "a"
        d["core"][1], d["core"][2] = d["core"][2], d["core"][1]
        errs = Contract.from_dict(d).check_fork_of(A)
        self.assertTrue(errs and all(e.code == E_FORK for e in errs))

    def test_fork_that_drops_field_is_rejected(self):
        d = A.to_dict()
        d["prefix"], d["parent"] = "bad", "a"
        d["core"] = d["core"][:-1]
        self.assertTrue(Contract.from_dict(d).check_fork_of(A))

    def test_older_parser_reads_newer_same_prefix_documents(self):
        """A v1 parser ignores an unknown tail only when the same-prefix header says v2."""
        q = REG.get("q")
        lines = A_TEXT.strip().split("\n")
        lines[0] += "|v=2"
        lines[1] += "|future"
        doc = parse("\n".join(lines), A)
        self.assertEqual(len(doc.records), 12)
        self.assertEqual(doc.header["v"], 2)
        self.assertNotIn("future", doc.records[0])
        # child parser accepts parent documents (extensions optional)
        atext = "q" + A_TEXT[1:]
        doc = parse(atext, q)
        self.assertEqual(len(doc.records), 12)
        self.assertIsNone(doc.records[0]["feedback"])

    def test_extension_tail_may_be_partially_omitted(self):
        q = REG.get("q")
        text = (ROOT / "forks/q/fixtures/valid.mini").read_text(encoding="utf-8")
        lines = text.strip().split("\n")
        lines[1] = "|".join(lines[1].split("|")[:A.arity + 1])  # keep feedback, drop hint/objective
        doc = parse("\n".join(lines), q)
        self.assertIsNotNone(doc.records[0]["feedback"])
        self.assertIsNone(doc.records[0]["hint"])


class TestDateDecimal(unittest.TestCase):
    """SPEC 1.1 §6: date and decimal accept native Python values when serialising."""

    C = Contract.from_dict({"prefix": "dd", "records_key": "rows", "core": [
        {"name": "day", "type": "date"}, {"name": "amount", "type": "decimal", "min": 0}]})

    def test_native_values_are_serialised_as_canonical_text(self):
        import datetime
        import decimal
        text = dumps({"rows": [{"day": datetime.date(2024, 2, 29), "amount": decimal.Decimal("12.50")},
                               {"day": "2024-03-01", "amount": 7}]}, self.C)
        self.assertEqual(text, "dd|n=2\n2024-02-29|12.50\n2024-03-01|7")
        rows = parse(text, self.C).records
        self.assertEqual(rows[0], {"day": "2024-02-29", "amount": "12.50"})

    def test_errors_carry_parser_codes_and_lines(self):
        with self.assertRaises(MiniError) as cm:
            dumps({"rows": [{"day": "2024-01-01", "amount": "1"}, {"day": "2024-01-02", "amount": "-1"}]}, self.C)
        self.assertEqual((cm.exception.code, cm.exception.line), (E_RANGE, 3))
        with self.assertRaises(MiniError) as cm:
            dumps({"rows": [{"day": "2024-01-01", "amount": 0.1}]}, self.C)
        self.assertEqual((cm.exception.code, cm.exception.line), (E_TYPE, 2))
        self.assertEqual(codes("dd|n=1\n2023-02-29|1", self.C), [E_TYPE])


class TestTokens(unittest.TestCase):
    def test_reproduces_published_counts(self):
        from minifmt.tokens import get_tokenizer
        tk = get_tokenizer("o200k_base")
        self.assertEqual(tk.count("hello world"), 2)
        legacy = ROOT / "benchmark" / "results" / "docs" / "a" / "dataset_12.json"
        if legacy.exists():
            self.assertGreater(tk.count(legacy.read_text(encoding="utf-8")), 1000)


if __name__ == "__main__":
    unittest.main(verbosity=2)
