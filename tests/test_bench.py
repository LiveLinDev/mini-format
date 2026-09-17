"""HU20: ``mini bench`` mide tokens por formato y el ahorro frente a JSON compacto.

La prueba de determinismo reproduce, para los documentos archivados del
benchmark (``benchmark/results/docs/<familia>/dataset_12.json``), los conteos
de ``benchmark/results/tokens.csv`` (o200k_base).  Requiere un tokenizador
(tiktoken, o el respaldo puro de Python con ``regex``) y se omite si no hay
ninguno; YAML y TOON se comparan solo si PyYAML y node están disponibles.
"""
from __future__ import annotations

import contextlib
import csv
import io
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from minifmt import Registry, cli, dumps  # noqa: E402
from minifmt import bench  # noqa: E402

DOCS = ROOT / "benchmark" / "results" / "docs"
ARCHIVE = ROOT / "benchmark" / "results" / "tokens.csv"


def _tokenizer_available():
    try:
        from minifmt.tokens import get_tokenizer
        get_tokenizer("o200k_base").count("x")
        return True
    except Exception:  # noqa: BLE001
        return False


HAVE_TOKENIZER = _tokenizer_available()
try:
    import tiktoken  # noqa: F401
    HAVE_TIKTOKEN = True
except ImportError:  # pragma: no cover
    HAVE_TIKTOKEN = False


def run_cli(*argv):
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        try:
            rc = cli.main(list(argv))
        except SystemExit as e:
            rc = e.code
    return rc, out.getvalue(), err.getvalue()


def archived(prefix):
    with open(ARCHIVE, encoding="utf-8") as fh:
        return {r["format"]: (int(r["tokens"]), int(r["bytes"])) for r in csv.DictReader(fh)
                if r["prefix"] == prefix and r["n"] == "12" and r["tokenizer"] == "o200k_base"}


@unittest.skipUnless(HAVE_TOKENIZER, "no tokenizer available (tiktoken or regex + vocab)")
class TestBenchReport(unittest.TestCase):
    def test_reproduces_archived_benchmark_counts(self):
        prefixes = sorted(p.name for p in DOCS.iterdir() if (p / "dataset_12.json").is_file())
        if not HAVE_TIKTOKEN:  # the pure-Python fallback is exact but slow
            prefixes = prefixes[:1]
        self.assertTrue(prefixes)
        for prefix in prefixes:
            with self.subTest(prefix=prefix):
                ref = archived(prefix)
                rep = bench.run_bench(str(DOCS / prefix / "dataset_12.json"), prefix=prefix)
                rows = {r["format"]: r for r in rep["formats"]}
                self.assertEqual(set(rows), {"mini", "toon_flat", "toon", "csv", "json_compact", "yaml", "json_pretty"})
                compared = 0
                for fmt, row in rows.items():
                    if not row["available"]:
                        self.assertIn(fmt, ("toon", "toon_flat", "yaml"))
                        continue
                    self.assertEqual((row["tokens"], row["bytes"]), ref[fmt], fmt)
                    compared += 1
                self.assertGreaterEqual(compared, 4)
                base = ref["json_compact"][0]
                self.assertEqual(rep["baseline_tokens"], base)
                self.assertEqual(rows["mini"]["saving_vs_json_compact"], round((base - ref["mini"][0]) / base * 100, 1))
                self.assertEqual(rows["json_compact"]["saving_vs_json_compact"], 0.0)

    def test_cli_json_is_parseable_and_deterministic(self):
        fx = str(ROOT / "forks" / "card" / "fixtures" / "valid.mini")
        rc1, out1, err1 = run_cli("bench", fx, "--format", "json")
        rc2, out2, _ = run_cli("bench", fx, "-p", "card", "--format", "json", "--enc", "o200k_base")
        self.assertEqual((rc1, rc2), (0, 0), err1)
        self.assertEqual(out1, out2)
        rep = json.loads(out1)
        self.assertEqual((rep["kind"], rep["prefix"], rep["records"], rep["encoding"]), ("family", "card", 12, "o200k_base"))
        from minifmt.tokens import count_tokens
        mini = next(r for r in rep["formats"] if r["format"] == "mini")
        reg = Registry.load(ROOT / "forks")
        text = (ROOT / "forks" / "card" / "fixtures" / "valid.mini").read_text(encoding="utf-8").rstrip("\n")
        self.assertEqual(dumps(json.loads((ROOT / "forks" / "card" / "fixtures" / "canonical.json").read_text(encoding="utf-8")), reg.get("card")), text)
        self.assertEqual(mini["tokens"], count_tokens(text))

    def test_table_output(self):
        rc, out, err = run_cli("bench", str(ROOT / "forks" / "a" / "fixtures" / "valid.mini"))
        self.assertEqual(rc, 0, err)
        for label in (".mini", "JSON compact", "JSON indented", "YAML", "CSV (flattened)", "TOON (official, as-is)", "saving vs JSON compact"):
            self.assertIn(label, out)

    def test_toon_reported_unavailable_instead_of_estimated(self):
        fx = ROOT / "forks" / "card" / "fixtures" / "valid.mini"
        rep = bench.run_bench(str(fx), toon_bundle=ROOT / "no-such-bundle.js")
        toon = [r for r in rep["formats"] if r["format"].startswith("toon")]
        self.assertTrue(toon and all(not r["available"] and "reason" in r and "tokens" not in r for r in toon))
        with mock.patch.object(bench.shutil, "which", return_value=None):
            rep = bench.run_bench(str(fx))
        self.assertTrue(all("node not found" in r["reason"] for r in rep["formats"] if r["format"].startswith("toon")))
        rc, out, _ = run_cli("bench", str(fx))
        self.assertEqual(rc, 0)

    def test_domain_profile_contract(self):
        from minifmt import domain
        tmp = Path(tempfile.mkdtemp())
        try:
            sample = json.loads((ROOT / "examples" / "phones.json").read_text(encoding="utf-8"))
            domain.build_bundle([sample], "phones", tmp / "kit")
            rc, out, err = run_cli("bench", str(ROOT / "examples" / "phones.json"), "--contract", str(tmp / "kit" / "contract.json"), "--format", "json")
            self.assertEqual(rc, 0, err)
            rows = {r["format"]: r for r in json.loads(out)["formats"]}
            self.assertTrue(rows["mini"]["available"])
            self.assertFalse(rows["csv"]["available"])  # nested specs: not tabular
            self.assertIn("not tabular", rows["csv"]["reason"])
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_json_input_needs_family(self):
        tmp = Path(tempfile.mkdtemp())
        try:
            f = tmp / "doc.json"
            f.write_text(json.dumps({"header": {}, "cards": []}), encoding="utf-8")
            rc, _, err = run_cli("bench", str(f))
            self.assertEqual(rc, 2)
            self.assertIn("-p PREFIX", err)
            bad = tmp / "bad.mini"
            bad.write_text((ROOT / "forks" / "card" / "fixtures" / "bad_count.mini").read_text(encoding="utf-8"), encoding="utf-8")
            rc, out, err = run_cli("bench", str(bad))
            self.assertEqual((rc, out), (1, ""))
            self.assertIn("E04", err)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


class TestBenchWithoutTokenizer(unittest.TestCase):
    def test_clear_error_when_no_tokenizer(self):
        fx = str(ROOT / "forks" / "card" / "fixtures" / "valid.mini")
        with mock.patch("minifmt.tokens.get_tokenizer", side_effect=ImportError("No module named 'regex'")):
            rc, out, err = run_cli("bench", fx)
        self.assertEqual(rc, 2)
        self.assertEqual(out, "")
        self.assertIn("no tokenizer available for encoding 'o200k_base'", err)
        self.assertIn("tiktoken", err)
        rc, _, err = run_cli("bench", fx, "--enc", "no_such_encoding")
        self.assertEqual(rc, 2)
        self.assertIn("no tokenizer available for encoding 'no_such_encoding'", err)


if __name__ == "__main__":
    unittest.main()
