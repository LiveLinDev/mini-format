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
from minifmt.domain import (DomainError, _strict_json, apply_replacements, build_bundle, columnar_json_request, decode,
                            decode_columnar_json,
                            decode_rows, diagnose, encode, encode_rows, infer_contract, json_schema,
                            load_contract, make_prompt, make_rows_prompt, repair)


class DomainTests(unittest.TestCase):
    def test_columnar_json_projects_known_fields_and_reconstructs_rows(self):
        expected = [{"id": 7, "title": "Pago", "value": 1.0}, {"id": 12, "title": "Acceso", "value": 2.5}]
        contract = infer_contract([expected])
        known = [{"id": 7}, {"id": 12}]
        allowed = {"value": [1, 2.5]}
        request = columnar_json_request("Ticket lookup", contract, expected_records=2,
                                        known_rows=known, allowed_values=allowed)
        self.assertEqual(request["schema"]["required"], ["title", "value"])
        self.assertEqual(request["schema"]["properties"]["value"], {
            "type": "array", "items": {"type": "number", "enum": [1, 2.5]}, "minItems": 2, "maxItems": 2,
        })
        self.assertEqual(decode_columnar_json('{"title":["Pago","Acceso"],"value":[1.0,2.5]}', contract,
                                              expected_records=2, known_rows=known, allowed_values=allowed), expected)
        self.assertEqual(decode_columnar_json('{"id":7,"title":"Pago","value":1.0}', contract,
                                              expected_records=1), expected[:1])
        self.assertEqual(decode_columnar_json('{"id":[],"title":[],"value":[]}', contract,
                                              expected_records=0, known_rows=[]), [])

    def test_columnar_json_rejects_bad_columns_and_values(self):
        contract = infer_contract([[{"title": "Pago", "open": True}]])
        for text, code in (
            ('{"title":["Pago"]', "D_VALUE"),
            ('{"title":["Pago"],"title":["Pago"],"open":[true]}', "D_VALUE"),
            ('{"title":["Pago"],"open":[true],"extra":1}', "D_TYPE"),
            ('{"title":"Pago","open":[true]}', "D_EXPECTED_COUNT"),
            ('{"title":["Pago"],"open":[true]}', "D_EXPECTED_COUNT"),
            ('{"title":["Pago","Acceso"],"open":[true,1]}', "D_TYPE"),
            ('{"title":["Pago","Otro"],"open":[true,false]}', "D_VALUE"),
        ):
            with self.subTest(text=text), self.assertRaises(DomainError) as raised:
                decode_columnar_json(text, contract, expected_records=2, allowed_values={"title": ["Pago", "Acceso"]})
            self.assertEqual(raised.exception.code, code)

    def test_columnar_json_rejects_invalid_projection_and_enums_before_a_call(self):
        contract = infer_contract([[{"id": 1, "score": 1.5}]])
        cases = (
            ({"known_rows": [{"id": 1, "score": 1.5}]}, "D_COMPACT_SCHEMA"),
            ({"known_rows": [{"missing": 1}]}, "D_COMPACT_SCHEMA"),
            ({"allowed_values": {"missing": [1]}}, "D_COMPACT_SCHEMA"),
            ({"allowed_values": {"score": []}}, "D_COMPACT_SCHEMA"),
            ({"allowed_values": {"score": [1, 1.0]}}, "D_COMPACT_SCHEMA"),
            ({"allowed_values": {"score": [True]}}, "D_TYPE"),
        )
        for options, code in cases:
            with self.subTest(options=options), self.assertRaises(DomainError) as raised:
                columnar_json_request("Task", contract, expected_records=1, **options)
            self.assertEqual(raised.exception.code, code)

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

    def test_compact_rows_round_trip_strings_and_scalar_types(self):
        values = [
            {"group": "\ufeffacceso", "title": "Instalar un informe", "id": 1, "open": True, "cost": -0.0},
            {"group": "cuenta personal", "title": '  "Contacto"\r\n🌊  ', "id": -2, "open": False, "cost": 1.5},
            {"group": "", "title": "", "id": 3, "open": True, "cost": 25},
            {"group": "~", "title": "? | barra \\ literal", "id": 4, "open": False, "cost": 0},
        ]
        contract = infer_contract([values], "ticket")
        wire = encode_rows(values, contract, last_text_field="title")
        wrapped = "\ufeff```mini\r\n" + wire.replace("\n", "\r\n\r\n") + "\r\n```"
        decoded = decode_rows(wrapped, contract, last_text_field="title", expected_records=len(values))
        self.assertEqual(json.dumps(decoded, sort_keys=True), json.dumps(values, sort_keys=True))
        self.assertEqual(encode_rows([], contract, last_text_field="title"), "")
        self.assertEqual(decode_rows("", contract, last_text_field="title", expected_records=0), [])
        self.assertIn("group id open cost title", make_rows_prompt(contract, last_text_field="title", expected_records=4))

    def test_compact_rows_reject_bad_shape_count_and_types(self):
        contract = infer_contract([[{"id": 1, "title": "Acceso"}]], "ticket")
        for wire, count, code in [
            ("", 1, "D_EXPECTED_COUNT"), ("1 Acceso\n2 Cobro", 1, "D_EXPECTED_COUNT"),
            ("true Acceso", 1, "D_VALUE"), ('"1" Acceso', 1, "D_VALUE"),
            ("1", 1, "D_VALUE"), ('1 "incompleto', 1, "D_VALUE"),
            ("1 X\rY", 1, "D_VALUE"), ("1 Acceso", True, "D_EXPECTED_COUNT"),
        ]:
            with self.subTest(wire=wire, count=count), self.assertRaisesRegex(DomainError, code):
                decode_rows(wire, contract, last_text_field="title", expected_records=count)
        for value in ({"id": 1, "title": "Acceso"}, [{"id": None, "title": "Acceso"}],
                      [{"id": 1, "title": "Acceso"}, {"title": "Cobro"}], [{"id": [1], "title": "Acceso"}]):
            with self.subTest(value=value), self.assertRaisesRegex(DomainError, "D_COMPACT_SCHEMA"):
                make_rows_prompt(infer_contract([value]), last_text_field="title", expected_records=1)
        with self.assertRaisesRegex(DomainError, "D_COMPACT_SCHEMA"):
            make_rows_prompt(contract, last_text_field="id", expected_records=1)

    def test_bundle_recommends_the_text_field_that_saves_quoting(self):
        data = [{"id": 1, "name": "Un título con espacios", "body": "Primera línea\nSegunda línea"}]
        with tempfile.TemporaryDirectory() as folder:
            bundle = Path(folder) / "compact"
            contract = build_bundle([data], "comment", bundle)
            settings = json.loads((bundle / "setup.json").read_text(encoding="utf-8"))
            field = settings["compact_last_text_field"]
            self.assertEqual(field, "name")
            wire = encode_rows(data, contract, last_text_field=field)
            self.assertLess(len(wire), len(encode_rows(data, contract, last_text_field="body")))
            self.assertEqual(decode_rows(wire, contract, last_text_field=field, expected_records=1), data)

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

    def test_shared_mutable_values_are_independent_after_decode(self):
        data = [{"id": i, "rules": [{"label": "A shared rule", "enabled": True}]} for i in range(8)]
        contract = infer_contract([data])
        wire = encode(data, contract)
        self.assertIn("|d=", wire.splitlines()[0])
        restored = decode(wire, contract)
        self.assertEqual(restored, data)
        restored[0]["rules"][0]["enabled"] = False
        self.assertEqual(restored[1:], data[1:])

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

    def test_count_diagnostic_checks_the_full_prefix_and_its_metadata(self):
        original = {"batch": "turno-1", "items": [{"id": 1}, {"id": 2}]}
        contract = infer_contract([original])
        header, first, _ = encode(original, contract, shared=False, dictionaries=False).split("\n")
        prefix = header + "\n" + first + "\n"
        report = diagnose(prefix, contract)
        self.assertFalse(report["ok"])
        self.assertEqual([error["code"] for error in report["errors"]], ["D_COUNT"])
        self.assertEqual(report["valid_lines"], [2])
        self.assertEqual(report["invalid_lines"], [])
        result = repair(prefix, contract, fix_count=True)
        self.assertEqual(decode(result["text"], contract), {"batch": "turno-1", "items": [{"id": 1}]})

        corrupt_metadata = header.split("|m=", 1)[0] + "|m=mal\n" + first + "\n"
        self.assertEqual(diagnose(corrupt_metadata, contract)["recoverable_records"], 0)
        self.assertFalse(repair(corrupt_metadata, contract, fix_count=True)["ok"])
        invalid_count = prefix.replace("|n=2|", "|n=invalido|")
        self.assertEqual(diagnose(invalid_count, contract)["valid_lines"], [2])

    def test_transport_repair_removes_only_the_echoed_prompt_heading(self):
        data = [{"note": "# Contrato de dominio .mini"}, {"note": "# .mini domain contract"}]
        contract = infer_contract([data])
        wire = encode(data, contract)
        for lang in ("es", "en"):
            heading = make_prompt(contract, lang).splitlines()[0]
            with self.subTest(lang=lang):
                wrapped = heading + "\n" + wire
                self.assertFalse(diagnose(wrapped, contract)["ok"])
                report = repair(wrapped, contract)
                self.assertTrue(report["ok"], report)
                self.assertEqual(report["changes"], ["removed echoed .mini prompt heading"])
                self.assertEqual(report["text"], wire)
                self.assertEqual(decode(report["text"], contract), data)
                fenced = heading + "\n\n```mini\n" + wire + "\n```"
                self.assertEqual(repair(fenced, contract)["text"], wire)
                self.assertFalse(repair(wrapped.replace("|n=2|", "|n=3|"), contract)["ok"])
        self.assertFalse(repair("# Unexpected heading\n" + wire, contract)["ok"])

    def test_transport_repair_removes_extra_trailing_blank_lines(self):
        # CP063: response saved with BOM, CRLF and an extra empty line at the end (PowerShell Out-File).
        data = [{"id": 1, "name": "Luna"}, {"id": 2, "name": "Sol"}]
        c = infer_contract([data])
        wire = encode(data, c) + "\n"
        saved = "﻿" + wire.replace("\n", "\r\n") + "\r\n"
        self.assertFalse(diagnose(saved, c)["ok"])
        report = repair(saved, c)
        self.assertTrue(report["ok"], report)
        self.assertEqual(report["changes"], ["removed UTF-8 BOM", "normalized CRLF to LF", "removed trailing blank lines"])
        self.assertEqual(report["text"], wire)
        self.assertEqual(decode(report["text"], c), data)
        for extra in (wire + "\n\n\n", wire.rstrip("\n") + "\n\n"):
            report = repair(extra, c)
            self.assertTrue(report["ok"], report)
            self.assertEqual(report["text"], wire)
        # A response that is already clean is returned unchanged.
        self.assertEqual(repair(wire, c)["changes"], [])
        # Only the trailing whitespace is transport: an empty line between records is still rejected.
        header, first, *rest = wire.rstrip("\n").split("\n")
        inner = header + "\n" + first + "\n\n" + "\n".join(rest) + "\n"
        self.assertFalse(repair(inner, c)["ok"])

    def test_transport_repair_removes_one_surplus_separator_per_invalid_row(self):
        data = [{"id": 1, "note": "Ends in |"}, {"id": 2, "note": ""}, {"id": 3, "note": "Texto"}]
        contract = infer_contract([data])
        header, first, second, third = encode(data, contract, shared=False, dictionaries=False).split("\n")
        raw = "\n".join([header, first + "|", second, third + "|", ""])
        self.assertFalse(diagnose(raw, contract)["ok"])
        result = repair(raw, contract)
        self.assertTrue(result["ok"], result)
        self.assertEqual(result["text"], "\n".join([header, first, second, third, ""]))
        self.assertEqual(result["changes"], ["removed surplus trailing row separators"])
        self.assertEqual(decode(result["text"], contract), data)

    def test_transport_repair_preserves_a_valid_empty_cell_and_rejects_other_errors(self):
        contract = infer_contract([[{"id": 1, "note": ""}]])
        wire = encode([{"id": 1, "note": ""}], contract, shared=False, dictionaries=False)
        empty = wire.removesuffix('""')
        self.assertEqual(repair(empty, contract)["text"], empty)
        for invalid in (wire + "||", wire + "|otro", (wire + "|").replace("|n=1|", "|n=2|"),
                        (wire + "|").replace("\n1|", "\nuno|")):
            with self.subTest(invalid=invalid):
                result = repair(invalid, contract)
                self.assertFalse(result["ok"])
                self.assertEqual(result["text"], invalid)

    def test_cli_repair_writes_file_for_trailing_blank_lines(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            sample = root / "sample.json"
            sample.write_text('[{"id":1,"name":"Luna"},{"id":2,"name":"Sol"}]', encoding="utf-8")
            bundle = root / "kit"
            out = io.StringIO()
            with contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(cli.main(["build", str(sample), "--prefix", "phone", "--out", str(bundle)]), 0)
            example = (bundle / "example.mini").read_bytes()
            saved = root / "saved.mini"
            saved.write_bytes(b"\xef\xbb\xbf" + example.replace(b"\n", b"\r\n") + b"\r\n")
            target = root / "repaired.mini"
            with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                rc = cli.main(["repair", str(saved), "--contract", str(bundle / "contract.json"), "--out", str(target)])
            self.assertEqual(rc, 0)
            self.assertEqual(target.read_bytes(), example)

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
