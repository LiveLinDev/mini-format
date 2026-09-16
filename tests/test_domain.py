"""Lossless generated-domain and standalone bundle integration tests."""
from __future__ import annotations

import contextlib
import hashlib
import io
import json
import os
import random
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from minifmt import cli
from minifmt.domain import (DomainError, _strict_json, apply_replacements, build_bundle, decode,
                            diagnose, encode, infer_contract, json_schema,
                            load_contract, make_prompt, repair)


class DomainTests(unittest.TestCase):
    def roundtrip(self, documents):
        contract = infer_contract(documents, "phone")
        for document in documents:
            wire = encode(document, contract)
            restored = decode(wire, contract)
            self.assertEqual(restored, document)
            self.assertEqual(json.dumps(restored, sort_keys=True), json.dumps(document, sort_keys=True))
            self.assertEqual(encode(restored, contract), wire)
        return contract

    def test_empty_and_scalar_roots(self):
        for value in ({}, [], None, True, False, 0, 1.0, -0.0, 1e150, "", "ñ雪🌊", "  spaced  "):
            with self.subTest(value=value):
                self.roundtrip([value])

    def test_optional_and_null_are_distinct(self):
        values = [{"id": 1, "note": None}, {"id": 2}, {"id": 3, "note": ""}, {"id": 4, "note": "?"}, {"id": 5, "note": "~"}]
        contract = self.roundtrip([values])
        text = encode(values, contract, shared=False)
        self.assertIn("1|~", text)
        self.assertIn("2|?", text)
        self.assertIn('3|""', text)

    def test_nested_objects_arrays_and_heterogeneous_json(self):
        values = [
            {"id": 1, "nested": {"a": 2, "b": None}, "arr": [{"x": "yes"}, {"x": "no", "extra": []}], "mixed": [1, "one", None, {}, [], {"?": 0}]},
            {"id": 2, "nested": {"a": 3}, "arr": [], "mixed": [{"$missing": True}, False]},
        ]
        self.roundtrip([values])

    def test_flattened_nested_paths_and_empty_objects_are_lossless(self):
        data = [{"a/b": {"~key": i, "empty": {}}, "a": {"b/~key": str(i)}, "optional": {"value": None}} for i in range(4)]
        data.append({"a/b": {"~key": 4, "empty": {}}, "a": {"b/~key": "4"}})
        c = self.roundtrip([data])
        self.assertIn("a~1b/~0key", c["record_fields"])
        self.assertIn("a/b~1~0key", c["record_fields"])
        self.assertIn("optional", c["record_fields"])

    def test_nullable_object_rows(self):
        self.roundtrip([[None, {"a": 1}, {"a": 2}]])
        self.roundtrip([None, {"a": 1}])

    def test_multiple_samples_expand_schema_without_freezing_values(self):
        samples = [[{"id": 1, "brand": "A"}], [{"id": 2, "brand": "A", "rating": None}, {"id": 3, "brand": "B", "rating": 4.5}]]
        contract = self.roundtrip(samples)
        fresh = [{"id": 99, "brand": "Different", "rating": 0.0}]
        self.assertEqual(decode(encode(fresh, contract), contract), fresh)
        self.assertEqual(contract["sample_documents"], 2)
        self.assertEqual(contract["sample_records"], 3)

    def test_wrappers_and_explicit_record_pointer(self):
        data = {"meta": {"page": 1, "currency": "PEN"}, "data": {"phones": [{"id": 1}, {"id": 2}]}, "other": [1, 2, 3]}
        c = self.roundtrip([data])
        self.assertEqual(c["record_path"], ["data", "phones"])
        explicit = infer_contract([data], "phone", record_path=["other"])
        self.assertEqual(decode(encode(data, explicit), explicit), data)
        with self.assertRaises(DomainError):
            infer_contract([data], record_path=["missing"])

    def test_escaping_preserves_cr_lf_quotes_backslashes_and_spaces(self):
        strings = ["a|b", "a\\b", "a\nb", "a\rb", "a\r\nb", '"quoted"', "\\n", " ", "x\t y", "~", "?", "", "-", "123", "false", "null", "[]", "{}", "\ufeffvalue"]
        self.roundtrip([[{"text": string} for string in strings]])

    def test_type_and_new_key_fail_without_coercion(self):
        c = infer_contract([[{"id": 1, "ok": True}]])
        for bad in ([{"id": "1", "ok": True}], [{"id": True, "ok": True}], [{"id": 1, "ok": 1}], [{"id": 1}], [{"id": 1, "ok": True, "new": 0}]):
            with self.subTest(value=bad), self.assertRaises(DomainError):
                encode(bad, c)

    def test_unknown_empty_and_null_samples_stay_open(self):
        c = infer_contract([[{"a": None, "b": []}]])
        new = [{"a": {"future": [1, 2]}, "b": [1, "x", {}]}]
        self.assertEqual(decode(encode(new, c), c), new)

    def test_shared_columns_are_explicit_and_not_permanent(self):
        data = [{"id": i, "vendor": "A sufficiently long shared brand", "enabled": True} for i in range(50)]
        c = infer_contract([data])
        optimized, plain = encode(data, c), encode(data, c, shared=False)
        self.assertIn("|d=", optimized.splitlines()[0])
        self.assertLess(len(optimized), len(plain))
        self.assertEqual(decode(optimized, c), data)
        for row in data:
            row["vendor"] = "Changed independently"
        self.assertEqual(decode(encode(data, c), c), data)
        same = [{"a": "all identical"}] * 30
        self.roundtrip([same])

    def test_repeated_strings_use_explicit_lossless_vocabulary(self):
        strings = ["reviewed and published", "automatic validation", "needs manual review"]
        data = [{"id": index, "status": strings[index % 3]} for index in range(120)]
        c = infer_contract([data])
        optimized, plain = encode(data, c), encode(data, c, dictionaries=False)
        self.assertIn("|e=", optimized.splitlines()[0])
        self.assertLess(len(optimized), len(plain))
        self.assertEqual(decode(optimized, c), data)
        fresh = [{"id": 500, "status": "entirely new vocabulary"}]
        self.assertEqual(decode(encode(fresh, c), c), fresh)
        bad = optimized.rsplit("|", 1)[0] + "|999"
        self.assertFalse(diagnose(bad, c)["ok"])
        self.roundtrip([[{"text": value} for value in ["?", "~", '"quote', "a|b\\c"] * 30]])

    def test_bad_headers_and_cells_fail_with_location(self):
        data = [{"id": 1}, {"id": 2}]
        c = infer_contract([data])
        wire = encode(data, c)
        for bad in (wire.replace("n=2", "n=3"), wire.replace("v=1", "v=2"), wire.replace("h=", "h=X"), wire + "\n3|extra", wire.replace("\n1\n", "\ntrue\n"), wire.replace("\n1\n", "\n1\\q\n")):
            report = diagnose(bad, c)
            self.assertFalse(report["ok"])
            self.assertGreater(report["errors"][0]["line"], 0)
            self.assertIn("repair_prompt", report)

    def test_shared_column_header_validation(self):
        c = infer_contract([[{"a": 1}, {"a": 2}]])
        header = encode([], c).splitlines()[0]
        for defaults in ('[[0,"1"],[0,"2"]]', '[[false,"1"]]', '[[99,"1"]]', '{}', '[[0,1]]'):
            report = diagnose(header + "|d=" + defaults, c)
            self.assertFalse(report["ok"])

    def test_transport_repair_never_invents_values_or_records(self):
        data = [{"id": 1}, {"id": 2}]
        c = infer_contract([data])
        wire = encode(data, c)
        wrapped = "\ufeff```mini\r\n" + wire.replace("\n", "\r\n") + "\r\n```\r\n"
        report = repair(wrapped, c)
        self.assertTrue(report["ok"])
        self.assertEqual(decode(report["text"], c), data)
        mismatch = wire.replace("n=2", "n=9")
        self.assertFalse(repair(mismatch, c)["ok"])
        accepted = repair(mismatch, c, fix_count=True)
        self.assertTrue(accepted["ok"])
        self.assertEqual(decode(accepted["text"], c), data)
        invalid = wire.replace("\n1\n", "\n?\n")
        self.assertFalse(repair(invalid, c, fix_count=True)["ok"])
        self.assertFalse(repair("Here is your response:\n" + wire, c)["ok"])

    def test_selective_diagnostics_and_verified_line_replacement(self):
        data = [{"id": 1}, {"id": 2}, {"id": 3}]
        c = infer_contract([data])
        correct = encode(data, c)
        bad = correct.replace("\n1\n2\n", "\nfalse\n?\n")
        report = diagnose(bad, c)
        self.assertEqual(report["invalid_lines"], [2, 3])
        self.assertEqual(report["valid_lines"], [4])
        self.assertEqual(report["recoverable_records"], 1)
        self.assertEqual(len(report["errors"]), 2)
        self.assertEqual(apply_replacements(bad, {"2": "1", "3": "2"}, c), correct)
        with self.assertRaises(DomainError):
            apply_replacements(bad, {"4": "100"}, c)
        with self.assertRaises(DomainError):
            apply_replacements(bad, {"2": "1\n2"}, c)
        with self.assertRaises(DomainError):
            apply_replacements(bad, {"2": "false", "3": "2"}, c)

    def test_reject_non_json_values_and_duplicate_input_keys(self):
        for value in (float("nan"), float("inf"), {1: "bad"}, (1, 2), {"nested": float("nan")}):
            with self.subTest(value=value), self.assertRaises(DomainError):
                infer_contract([value])
        for text in ('{"a":1,"a":2}', '[NaN]', '[Infinity]'):
            with self.assertRaises(ValueError):
                _strict_json(text)

    def test_json_schema_matches_optional_nullable_and_arrays(self):
        c = infer_contract([[{"id": 1, "note": None, "tags": []}, {"id": 2, "note": "ok", "extra": False, "tags": ["a"]}]])
        schema = json_schema(c)
        item = schema["items"]
        self.assertFalse(item["additionalProperties"])
        self.assertNotIn("extra", item["required"])
        self.assertEqual(item["properties"]["note"]["type"], ["string", "null"])
        self.assertEqual(item["properties"]["tags"]["items"]["type"], "string")

    def test_schema_fingerprint_rejects_wrong_bundle(self):
        c = infer_contract([[{"x": 1}]], "demo")
        other = infer_contract([[{"y": 1}]], "demo")
        with self.assertRaises(DomainError):
            decode(encode([{"x": 1}], c), other)
        c["schema"]["items"]["fields"][0]["name"] = "changed"
        with self.assertRaises(DomainError):
            encode([{"changed": 1}], c)

    def test_fuzz_random_json_roundtrips(self):
        rng = random.Random(20260916)
        def value(depth=0):
            choices = [None, True, False, rng.randint(-10, 10), rng.random(), rng.choice(["", "?", "~", "ñ|\\\n", " x "])]
            if depth < 3:
                choices += [[value(depth+1) for _ in range(rng.randrange(4))], {key: value(depth+1) for key in ["a", "b", "c"][:rng.randrange(4)]}]
            return rng.choice(choices)
        for _ in range(60):
            self.roundtrip([value() for _ in range(rng.randrange(1, 5))])

    def test_prompts_describe_lossless_rules_in_both_languages(self):
        c = infer_contract([[{"a": 1}]])
        for lang, keyword in (("en", "absent"), ("es", "ausente")):
            prompt = make_prompt(c, lang)
            self.assertIn(keyword, prompt)
            self.assertIn(c["schema_id"], prompt)
            self.assertIn("mini-domain/1", prompt)


class BundleIntegration(unittest.TestCase):
    def test_build_and_run_standalone_without_installed_package(self):
        sample = {"products": [{"id": 1, "name": "One|phone", "spec": {"ram": 8}}, {"id": 2, "name": "Two", "spec": {"ram": 16}}], "total": 2}
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            bundle = root / ".mini"
            c = build_bundle([sample], "phone", bundle)
            self.assertEqual(load_contract(bundle / "contract.json"), c)
            manifest = json.loads((bundle / "manifest.json").read_text(encoding="utf-8"))
            for name, expected in manifest["files"].items():
                self.assertEqual(hashlib.sha256((bundle / name).read_bytes()).hexdigest(), expected)
            env = dict(os.environ)
            env.pop("PYTHONPATH", None)
            def run(script, *args):
                return subprocess.run([sys.executable, "-I", str(bundle / script), *map(str, args)], cwd=root, env=env, text=True, encoding="utf-8", capture_output=True)
            # parser.py is standalone even under isolated Python (-I).
            encoded = run("parser.py", "encode", bundle / "example.json")
            self.assertEqual(encoded.returncode, 0, encoded.stderr)
            decoded = run("parser.py", "decode", bundle / "example.mini")
            self.assertEqual(decoded.returncode, 0, decoded.stderr)
            self.assertEqual(json.loads(decoded.stdout), sample)
            valid = run("parser.py", "validate", bundle / "example.mini")
            self.assertEqual(valid.returncode, 0, valid.stderr)
            prompt = run("parser.py", "prompt", "--lang", "es")
            self.assertEqual(prompt.returncode, 0, prompt.stderr)
            self.assertIn("línea", prompt.stdout)
            # Wrapper entrypoints intentionally import their adjacent parser;
            # normal execution includes that directory, unlike Python -I.
            validate = subprocess.run([sys.executable, str(bundle / "validator.py"), str(bundle / "example.mini")], cwd=root, env=env, capture_output=True, text=True)
            self.assertEqual(validate.returncode, 0, validate.stderr)
            with self.assertRaises(DomainError):
                build_bundle([sample], "phone", bundle)

    def test_cli_build_convert_diagnose_and_failed_repair(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            first, second = root / "one.json", root / "two.json"
            first.write_text('[{"id":1}]', encoding="utf-8")
            second.write_text('[{"id":2,"note":null}]', encoding="utf-8")
            bundle = root / "bundle"
            def run(*args):
                out, err = io.StringIO(), io.StringIO()
                with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                    rc = cli.main(list(map(str, args)))
                return rc, out.getvalue(), err.getvalue()
            self.assertEqual(run("build", first, second, "--prefix", "phone", "--out", bundle)[0], 0)
            contract = bundle / "contract.json"
            wire = root / "response.mini"
            rc, _, err = run("from-json", second, "--contract", contract, "--out", wire)
            self.assertEqual(rc, 0, err)
            rc, output, _ = run("to-json", wire, "--contract", contract, "--compact")
            self.assertEqual(rc, 0)
            self.assertEqual(json.loads(output), [{"id": 2, "note": None}])
            self.assertEqual(run("validate", wire, "--contract", contract)[0], 0)
            wire.write_text(wire.read_text(encoding="utf-8").replace("n=1", "n=8"), encoding="utf-8")
            target = root / "repaired.mini"
            self.assertEqual(run("repair", wire, "--contract", contract, "--out", target)[0], 1)
            self.assertFalse(target.exists())
            self.assertEqual(run("repair", wire, "--contract", contract, "--out", target, "--fix-count")[0], 0)
            self.assertTrue(target.exists())


if __name__ == "__main__":
    unittest.main()
