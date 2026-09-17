"""CLI, registro, bloque de especificación, tokenizador y ramas del contrato/serializador."""
from __future__ import annotations

import contextlib
import io
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from minifmt import (Contract, MiniError, MiniValidationError, Registry, dumps,  # noqa: E402
                     parse, parser_prompt, roundtrip_ok, spec_block)
from minifmt import cli  # noqa: E402
from minifmt.contract import Field, HeaderKey  # noqa: E402
from minifmt.parser import detect_prefix  # noqa: E402
from minifmt.values import coerce_from_json, decode_scalar, encode_scalar, format_number  # noqa: E402

FORKS = ROOT / "forks"
REG = Registry.load(FORKS)
A = REG.get("a")


def run_cli(*argv):
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        try:
            rc = cli.main(list(argv))
        except SystemExit as e:  # argparse / sys.exit paths
            rc = e.code
    return rc, out.getvalue(), err.getvalue()


class TestCli(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def write(self, name, text):
        p = self.tmp / name
        p.write_text(text, encoding="utf-8")
        return str(p)

    def test_forks_lists_every_contract(self):
        rc, out, _ = run_cli("forks")
        self.assertEqual(rc, 0)
        self.assertEqual(len(out.strip().splitlines()), len(REG.contracts))
        self.assertIn("parent=a", out)

    def test_validate_ok_and_invalid(self):
        rc, out, _ = run_cli("validate", str(FORKS / "a/fixtures/valid.mini"))
        self.assertEqual(rc, 0)
        self.assertIn("OK: prefix=a", out)
        rc, out, _ = run_cli("validate", str(FORKS / "a/fixtures/bad_marker.mini"), "-p", "a")
        self.assertEqual(rc, 1)
        self.assertIn("E08", out)
        self.assertIn("INVALID: 1 error(s)", out)

    def test_validate_without_detectable_prefix(self):
        rc, _, _ = run_cli("validate", self.write("empty.mini", "\n\n"))
        self.assertNotEqual(rc, 0)

    def test_unknown_prefix_is_reported(self):
        rc, _, err = run_cli("validate", self.write("zz.mini", "zz|n=0"))
        self.assertEqual(rc, 2)
        self.assertIn("unknown prefix", err)

    def test_to_json_strict_lenient_compact(self):
        rc, out, _ = run_cli("to-json", str(FORKS / "tc/fixtures/valid.mini"))
        self.assertEqual(rc, 0)
        self.assertEqual(len(json.loads(out)["cases"]), 12)
        bad = str(FORKS / "a/fixtures/bad_type.mini")
        rc, _, err = run_cli("to-json", bad)
        self.assertEqual(rc, 1)
        self.assertIn("E06", err)
        rc, out, err = run_cli("to-json", bad, "--lenient", "--compact")
        self.assertEqual(rc, 0)
        self.assertEqual(len(json.loads(out)["items"]), 11)
        self.assertEqual(len(out.strip().splitlines()), 1)
        self.assertIn("E06", err)

    def test_from_json_roundtrip(self):
        rc, out, _ = run_cli("from-json", str(FORKS / "log/fixtures/canonical.json"), "-p", "log")
        self.assertEqual(rc, 0)
        self.assertEqual(out.rstrip("\n"), (FORKS / "log/fixtures/valid.mini").read_text(encoding="utf-8").rstrip("\n"))

    def test_diagnose(self):
        text = (FORKS / "a/fixtures/valid.mini").read_text(encoding="utf-8")
        rc, out, _ = run_cli("diagnose", self.write("ok.mini", text))
        self.assertEqual(rc, 0)
        self.assertTrue(json.loads(out)["ok"])
        cut = text[:text.index("\ni4|") + 10]
        rc, out, _ = run_cli("diagnose", self.write("cut.mini", cut))
        rep = json.loads(out)
        self.assertEqual(rc, 1)
        self.assertEqual(rep["invalid_lines"], [5])
        self.assertEqual(rep["missing_records"], 8)
        self.assertTrue(rep["truncated"])
        rc, out, _ = run_cli("diagnose", self.write("blank.mini", "   \n"), "-p", "a")
        self.assertEqual(rc, 1)
        self.assertEqual(json.loads(out)["errors"][0]["code"], "E01")

    def test_prompt(self):
        rc, out, _ = run_cli("prompt", "a", "--lang", "es")
        self.assertEqual(rc, 0)
        self.assertIn("FORMATO .mini", out)
        self.assertIn("Ejemplo válido", out)
        self.assertIn("a|n=2", out)
        rc, out, _ = run_cli("prompt", "log", "--no-example")
        self.assertNotIn("Valid example", out)

    def test_tokens(self):
        rc, out, _ = run_cli("tokens", self.write("t.txt", "hello world"))
        self.assertEqual(rc, 0)
        self.assertTrue(out.startswith("2 tokens"))

    def test_check_forks_passes_on_official_forks(self):
        rc, out, _ = run_cli("check-forks")
        self.assertEqual(rc, 0)
        self.assertIn(f"ALL FORKS PASS ({len(REG.contracts)} forks)", out)

    def test_check_forks_detects_broken_fixtures(self):
        forks = self.tmp / "forks"
        for p in ("a", "q"):
            shutil.copytree(FORKS / p, forks / p)
        fx = forks / "a" / "fixtures"
        (fx / "bad_count.mini").write_text((fx / "valid.mini").read_text(encoding="utf-8"), encoding="utf-8")
        canon = json.loads((fx / "canonical.json").read_text(encoding="utf-8"))
        canon["items"][0]["topic"] = "otro"
        (fx / "canonical.json").write_text(json.dumps(canon, ensure_ascii=False), encoding="utf-8")
        (fx / "escaping.json").write_text(json.dumps(canon, ensure_ascii=False), encoding="utf-8")
        (forks / "q" / "fixtures" / "valid.mini").write_text("q|n=1\nbroken", encoding="utf-8")
        rc, out, _ = run_cli("check-forks", str(forks))
        self.assertEqual(rc, 1)
        self.assertIn("round-trip mismatch", out)
        self.assertIn("does not re-serialise", out)
        self.assertIn("bad_count.mini should be rejected", out)
        self.assertIn("escaping.mini round-trip mismatch", out)
        self.assertIn("q: valid.mini does not validate", out)
        self.assertIn("FAILED", out)

    def test_check_forks_missing_fixtures_and_invalid_escaping(self):
        forks = self.tmp / "forks"
        shutil.copytree(FORKS / "a", forks / "a")
        shutil.copytree(FORKS / "log", forks / "log")
        (forks / "log" / "fixtures" / "canonical.json").unlink()
        (forks / "a" / "fixtures" / "escaping.mini").write_text("a|n=1|k=4\nbad\\q", encoding="utf-8")
        rc, out, _ = run_cli("check-forks", str(forks))
        self.assertEqual(rc, 1)
        self.assertIn("log: missing fixtures", out)
        self.assertIn("escaping.mini invalid", out)

    def test_new_fork_scaffold(self):
        forks = self.tmp / "forks"
        shutil.copytree(FORKS / "a", forks / "a")
        rc, out, _ = run_cli("--forks", str(forks), "new-fork", "quiz2", "--from", "a", "--name", "Quiz 2",
                             "--add", "feedback:str", "level:enum{easy|hard}", "refs:list<str>")
        self.assertEqual(rc, 0)
        c = Contract.load(forks / "quiz2" / "contract.json")
        self.assertEqual([f.name for f in c.core], [f.name for f in A.fields])
        self.assertEqual([(f.name, f.type) for f in c.extensions], [("feedback", "str"), ("level", "enum"), ("refs", "list")])
        self.assertEqual(c.check_fork_of(A), [])
        rc, _, _ = run_cli("--forks", str(forks), "new-fork", "tick", "--add", "id:str", "title")
        self.assertEqual(rc, 0)
        self.assertEqual([f.name for f in Contract.load(forks / "tick" / "contract.json").core], ["id", "title"])
        rc, _, _ = run_cli("--forks", str(forks), "new-fork", "a")
        self.assertNotEqual(rc, 0)

    def test_module_entry_point(self):
        import runpy
        out = io.StringIO()
        argv = sys.argv
        try:
            sys.argv = ["minifmt", "forks"]
            with contextlib.redirect_stdout(out), self.assertRaises(SystemExit) as cm:
                runpy.run_module("minifmt", run_name="__main__")
        finally:
            sys.argv = argv
        self.assertEqual(cm.exception.code, 0)
        self.assertIn("a ", out.getvalue())


class TestRegistry(unittest.TestCase):
    def test_lineage_index_and_membership(self):
        self.assertEqual(REG.lineage("q"), ["q", "a"])
        self.assertIn("a", REG)
        self.assertNotIn("zz", REG)
        index = REG.to_index()
        self.assertEqual({e["prefix"] for e in index}, set(REG.contracts))
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "registry.json"
            REG.write_index(p)
            self.assertEqual(json.loads(p.read_text(encoding="utf-8")), index)
        committed = json.loads((FORKS / "registry.json").read_text(encoding="utf-8"))
        self.assertEqual(committed, index)

    def test_add_get_and_errors(self):
        reg = Registry()
        reg.add(Contract.from_dict({"prefix": "x", "core": [{"name": "id", "type": "str"}]}))
        with self.assertRaises(MiniError):
            reg.add(Contract.from_dict({"prefix": "x", "core": [{"name": "id", "type": "str"}]}))
        with self.assertRaises(MiniError):
            reg.get("nope")
        reg.add(Contract.from_dict({"prefix": "y", "parent": "ghost", "core": [{"name": "id", "type": "str"}]}))
        self.assertEqual([e.code for e in reg.check()], ["E21"])

    def test_load_rejects_folder_mismatch_and_duplicates(self):
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            (d / "wrong").mkdir()
            (d / "wrong" / "contract.json").write_text(json.dumps({"prefix": "x", "core": [{"name": "id", "type": "str"}]}), encoding="utf-8")
            with self.assertRaises(MiniError):
                Registry.load(d)
            (d / "wrong" / "contract.json").unlink()
            for name in ("x", "x2"):
                (d / name).mkdir(exist_ok=True)
                (d / name / "contract.json").write_text(json.dumps({"prefix": "x", "core": [{"name": "id", "type": "str"}]}), encoding="utf-8")
            with self.assertRaises(MiniError) as cm:
                Registry.load(d)
            self.assertIn("twice", str(cm.exception))


class TestPrompt(unittest.TestCase):
    def test_spec_block_es_and_en_cover_every_type(self):
        for c in REG:
            for lang in ("en", "es"):
                block = spec_block(c, lang, example=f"{c.prefix}|n=0")
                for f in c.fields:
                    self.assertIn(f.name, block)
        es = spec_block(REG.get("q"), "es")
        self.assertIn("Campos de extensión", es)
        self.assertIn("exactamente un", es)
        self.assertIn("al menos un", spec_block(REG.get("cls"), "es"))
        self.assertIn("at least one", spec_block(REG.get("cls"), "en"))
        c = Contract.from_dict({"prefix": "m", "core": [
            {"name": "a", "type": "mlist", "marker": "at_most_one"},
            {"name": "b", "type": "mlist", "marker": "any", "item": "enum", "item_values": ["x", "y"], "min": 1},
            {"name": "t", "type": "tuple", "items": [{"name": "p", "type": "int"}]},
            {"name": "r", "type": "float", "min": 0, "max": 1, "desc": "ratio"}]})
        en, es = spec_block(c, "en"), spec_block(c, "es")
        self.assertIn("at most one", en)
        self.assertIn("zero or more", en)
        self.assertIn("{x|y}", en)
        self.assertIn("fixed tuple", en)
        self.assertIn("como máximo un", es)
        self.assertIn("cero o más", es)
        self.assertIn("tupla fija", es)
        self.assertIn("ratio", en)

    def test_parser_prompt(self):
        fx = {"valid.mini": "a|n=0"}
        self.assertIn("TASK: write a deterministic Python parser", parser_prompt(A, fx, "en"))
        es = parser_prompt(A, fx, "es")
        self.assertIn("TAREA", es)
        self.assertIn("--- fixture: valid.mini ---", es)


class TestTokenizerFallback(unittest.TestCase):
    """El BPE en Python puro debe contar exactamente como tiktoken."""

    SAMPLES = ["hello world", "a|n=2|k=4\ni1|L1|Biología|¿Dónde?|x*,y|0.9,-1,0.25",
               "  leading spaces\r\n\ttabs and 12345 numbers don't", '{"k": [1, 2.5, "ñ"]}']

    def test_pure_python_matches_reference_counts(self):
        try:
            import regex  # noqa: F401
        except ImportError:  # pragma: no cover
            self.skipTest("regex not installed")
        from minifmt import tokens
        for name in ("o200k_base", "cl100k_base"):
            vocab = tokens.VOCAB_DIR / f"{name}.tiktoken"
            if not vocab.exists():  # pragma: no cover
                self.skipTest("vocab files not available")
            bpe = tokens._PurePythonBPE(name, tokens._load_ranks(vocab), tokens.PATTERNS[name])
            ref = tokens.Tokenizer(name)
            for s in self.SAMPLES:
                self.assertEqual(bpe.count(s), ref.count(s), (name, s))
                self.assertEqual(bpe.count(s), bpe.count(s))  # cached path
            if ref.backend == "tiktoken":
                self.assertEqual(ref.encode("hello world"), ref._enc.encode("hello world"))
        self.assertEqual(tokens.count_tokens("hello world"), 2)

    def test_backend_fallback_without_tiktoken(self):
        from minifmt import tokens
        saved = sys.modules.get("tiktoken")
        sys.modules["tiktoken"] = None  # make the import fail
        try:
            tk = tokens.Tokenizer("o200k_base")
        finally:
            if saved is None:
                del sys.modules["tiktoken"]
            else:
                sys.modules["tiktoken"] = saved
        self.assertEqual(tk.backend, "pure-python")
        self.assertEqual(tk.count("hello world"), 2)
        self.assertEqual(len(tk.encode("hello world")), 2)


class TestContractAndSerializerBranches(unittest.TestCase):
    def test_contract_roundtrip_to_dict_and_signature(self):
        for c in REG:
            again = Contract.from_dict(c.to_dict())
            self.assertEqual(again.signature(), c.signature())
            self.assertEqual(again.check_fork_of(c), [])
        c = Contract.from_dict({"prefix": "z", "header": {"required": ["n", "src"], "keys": {}},
                                "core": [{"name": "e", "type": "list", "item": "enum", "item_values": ["p"], "min": 0, "max": 2},
                                         {"name": "m", "type": "mlist", "marker": "at_least_one"},
                                         {"name": "i", "type": "int", "min": 1, "default": 3}],
                                "extensions": [{"name": "x", "type": "str"}]})
        self.assertIn("list<{p}>[0..2]", c.signature())
        self.assertIn("*1+", c.signature())
        self.assertIn("int[1..]", c.signature())
        self.assertIn(" || x:str?", c.signature())
        self.assertEqual(c.header_keys["src"].type, "str")
        self.assertTrue(c.header_keys["src"].required)
        self.assertEqual(c.field_index()["x"], 3)
        self.assertEqual(c.to_dict()["core"][2]["default"], 3)
        with self.assertRaises(MiniError):
            HeaderKey.from_dict("bad", {"type": "mlist"}, False)
        with self.assertRaises(MiniError):
            Field.from_dict({"name": "l", "type": "list", "item": "enum"})

    def test_fork_item_and_tuple_layout_changes(self):
        d = A.to_dict()
        d["prefix"], d["parent"] = "ch", "a"
        d["core"][4]["item"] = "int"
        d["core"][5]["items"] = d["core"][5]["items"][:2]
        d["header"]["required"] = ["n"]
        d["header"]["keys"]["k"] = {"type": "int"}
        errs = Contract.from_dict(d).check_fork_of(A)
        msgs = " ".join(e.message for e in errs)
        self.assertIn("item type", msgs)
        self.assertIn("tuple layout", msgs)
        parent = Contract.from_dict({"prefix": "p", "header": {"required": ["n", "src"]}, "core": [{"name": "id", "type": "str"}]})
        child = Contract.from_dict({"prefix": "c", "core": [{"name": "id", "type": "str"}]})
        self.assertIn("required header key 'src'", child.check_fork_of(parent)[0].message)

    def test_serializer_error_branches(self):
        c = Contract.from_dict({"prefix": "s", "records_key": "rows", "core": [
            {"name": "id", "type": "str"},
            {"name": "l", "type": "list"},
            {"name": "m", "type": "mlist", "marker": "at_least_one", "json": {"items": "m", "selected": "sel"}},
            {"name": "t", "type": "tuple", "items": [{"name": "a", "type": "int"}]}],
            "extensions": [{"name": "om", "type": "mlist", "marker": "at_most_one", "json": {"items": "om", "selected": "osel"}}]})
        good = {"id": "r", "l": ["x"], "m": ["a", "b"], "sel": [1], "t": {"a": 1}}
        self.assertEqual(dumps({"records": [good]}, c), "s|n=1\nr|x|a,b*|1")
        bad_cases = [
            dict(good, l="x"),                    # list expected
            dict(good, sel=[]),                   # at_least_one
            dict(good, m=None),                   # required mlist null
            dict(good, t=[1]),                    # tuple expects object
            dict(good, om=["a", "b"], osel=[0, 1]),  # at_most_one violated
        ]
        for rec in bad_cases:
            with self.assertRaises(MiniError, msg=rec):
                dumps({"rows": [rec]}, c)
        from minifmt.serializer import encode_field
        self.assertEqual(encode_field((["a", "b"], 0), c.fields[4], ","), "a*,b")
        hdr = Contract.from_dict({"prefix": "h", "header": {"keys": {"v": {"type": "int", "default": 1}, "tp": {"type": "tuple", "items": [
            {"name": "a", "type": "int"}, {"name": "b", "type": "str"}]}}}, "core": [{"name": "id", "type": "str"}]})
        self.assertEqual(dumps({"header": {"v": 2, "tp": {"a": 1, "b": None}, "gone": None}, "records": [{"id": "x"}]}, hdr),
                         "h|n=1|v=2|tp=1,\nx")
        self.assertTrue(roundtrip_ok({"header": {}, "records": [{"id": "x"}]}, hdr))

    def test_roundtrip_ok_fills_missing_extensions(self):
        q = REG.get("q")
        canon = json.loads((FORKS / "a/fixtures/canonical.json").read_text(encoding="utf-8"))
        self.assertTrue(roundtrip_ok(canon, q))
        c = Contract.from_dict({"prefix": "e", "core": [{"name": "id", "type": "str"}],
                                "extensions": [{"name": "om", "type": "mlist", "marker": "any", "json": {"items": "om", "selected": "osel"}}]})
        self.assertTrue(roundtrip_ok({"records": [{"id": "x"}]}, c))

    def test_values_helpers(self):
        f_int = Field(name="i", type="int")
        f_float = Field(name="f", type="float")
        with self.assertRaises(MiniError):
            decode_scalar("1e999", f_float, 1)       # non-finite
        self.assertEqual(format_number(True), "true")
        self.assertEqual(format_number(1e20), "100000000000000000000")
        self.assertEqual(format_number(1e-7), "0.0000001")
        for x in (1.5e300, 1e-300, -2.5e-9, 123456789.125):
            self.assertEqual(float(format_number(x)), x)  # exact, whatever the notation
        self.assertEqual(encode_scalar(None, f_int), "")
        self.assertIsNone(coerce_from_json(None, f_int))
        self.assertEqual(coerce_from_json("3", f_int), 3)
        self.assertEqual(coerce_from_json(1, Field(name="b", type="bool")), True)
        self.assertEqual(coerce_from_json(3, Field(name="s", type="str")), "3")

    def test_parser_misc_branches(self):
        self.assertIsNone(detect_prefix("\n \n"))
        self.assertEqual(detect_prefix("﻿a|n=1"), "a")
        c = Contract.from_dict({"prefix": "o", "records_key": "rows", "core": [{"name": "id", "type": "str"}],
                                "extensions": [{"name": "m", "type": "mlist", "marker": "any", "json": {"items": "m", "selected": "s"}},
                                               {"name": "l", "type": "list", "min": 1}]})
        doc = parse("o|n=1\nx", c)
        self.assertEqual(doc.records[0], {"id": "x", "m": None, "s": None, "l": None})
        # SPEC 1.1 Â§6: an empty optional list (or marked list) is null, even with min
        self.assertEqual(parse("o|n=1\nx||", c).records[0], {"id": "x", "m": None, "s": None, "l": None})
        self.assertEqual(parse("o|n=1\nx||a,", c).records[0]["l"], ["a", ""])  # bare empty element is ""
        req = Contract.from_dict({"prefix": "r", "core": [{"name": "l", "type": "list", "min": 1}]})
        self.assertEqual(parse("r|n=1\n", req, strict=False).errors[0].code, "E04")
        with self.assertRaises(MiniValidationError) as cm:
            parse("r|n=1\n|", req)
        self.assertIn("E05", cm.exception.codes)
        self.assertEqual(str(MiniError("E01", 0, "m")), "E01 document: m")
        self.assertEqual(str(MiniError("E06", 3, "m", "f")), "E06 line 3 [f]: m")
        self.assertIn("E06", str(MiniValidationError([MiniError("E06", 3, "m")])))
        hk = Contract.from_dict({"prefix": "h", "header": {"keys": {"when": {"type": "str", "default": "hoy"}}},
                                 "core": [{"name": "id", "type": "str"}]})
        self.assertEqual(parse("h|n=1||\nx", hk).header["when"], "hoy")


if __name__ == "__main__":
    unittest.main(verbosity=2)
