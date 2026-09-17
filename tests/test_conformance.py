"""Ejecuta la suite de conformidad independiente del lenguaje (conformance/cases)."""
from __future__ import annotations

import json
import sys
import unittest
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "conformance"))
sys.path.insert(0, str(ROOT / "src"))

import generate  # noqa: E402
import run_python  # noqa: E402

CASES = run_python.load_cases()


class TestConformanceSuite(unittest.TestCase):
    def test_every_case_passes(self):
        for case in CASES:
            with self.subTest(case=case["id"]):
                ok, msg = run_python.run_case(case)
                self.assertTrue(ok, msg)

    def test_suite_size_and_error_code_coverage(self):
        self.assertGreaterEqual(len(CASES), 150)
        codes = {e["code"] for c in CASES for e in c["expected"].get("errors", [])}
        expected = {f"E{i:02d}" for i in range(1, 14)} | {"E20", "E21"}
        self.assertEqual(expected - codes, set())
        modes = Counter(c["mode"] for c in CASES)
        self.assertTrue({"strict", "lenient", "dumps", "contract", "fork"} <= set(modes))

    def test_case_shape(self):
        ids = [c["id"] for c in CASES]
        self.assertEqual(len(ids), len(set(ids)))
        for c in CASES:
            with self.subTest(case=c["id"]):
                self.assertIn(c["mode"], {"strict", "lenient", "dumps", "contract", "fork"})
                if c["mode"] != "contract":
                    self.assertTrue(("family" in c) != ("contract" in c))
                self.assertTrue(c["expected"])

    def test_every_spec_1_1_rule_has_cases(self):
        """HU02/HU04: each point left open by SPEC 1.0 has a 1.1 rule, an ADR and cases."""
        ids = {c["id"] for c in CASES}
        adr_dir = ROOT / "docs" / "adr"
        self.assertEqual(len(generate.SPEC_1_1_RULES), 8)
        for rule, info in generate.SPEC_1_1_RULES.items():
            with self.subTest(rule=rule):
                self.assertTrue(info["cases"])
                self.assertEqual(set(info["cases"]) - ids, set())
                self.assertEqual(len(list(adr_dir.glob(f"{info['adr']}-*.md"))), 1)
        spec = (ROOT / "SPEC.md").read_text(encoding="utf-8")
        self.assertIn("**Version:** 1.1", spec)
        for f in run_python.CASES_DIR.glob("*.json"):
            self.assertEqual(json.loads(f.read_text(encoding="utf-8"))["spec"], generate.SPEC_VERSION)

    def test_committed_cases_match_generator(self):
        built = generate.build()
        for f in sorted(run_python.CASES_DIR.glob("*.json")):
            doc = json.loads(f.read_text(encoding="utf-8"))
            self.assertEqual(doc["cases"], json.loads(json.dumps(built[doc["category"]])), f.name)
        self.assertEqual(sorted(built), sorted(p.stem for p in run_python.CASES_DIR.glob("*.json")))

    def test_runner_cli(self):
        import contextlib
        import io
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = run_python.main(["--json", "-k", "header"])
        report = json.loads(buf.getvalue())
        self.assertEqual(rc, 0)
        self.assertEqual(report["failed"], 0)
        self.assertIn("header", report["categories"])
        self.assertLess(report["total"], len(CASES))


if __name__ == "__main__":
    unittest.main(verbosity=2)
