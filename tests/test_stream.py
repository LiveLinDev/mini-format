"""HU10: lector incremental (streaming) equivalente a parse().

Escenario 1: un documento entregado por fragmentos (texto de 1 carácter,
fragmentos aleatorios, bytes UTF-8 sueltos o partidos en mitad de un carácter
multibyte) produce los mismos registros, errores y diagnósticos que parse(),
en todas las familias oficiales y en los casos de conformidad strict/lenient.

Escenario 2: el pico de memoria no crece con el número de registros.  La
prueba compara 10 000 con 200 000 registros; la versión de 1 000 000 tarda
varios minutos con tracemalloc y se ejecuta solo con MINI_STREAM_MILLION=1.
"""
from __future__ import annotations

import os
import random
import sys
import tracemalloc
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "conformance"))
sys.path.insert(0, str(ROOT / "src"))

import run_python  # noqa: E402
from minifmt import Contract, MiniValidationError, Registry, parse  # noqa: E402
from minifmt import stream as stream_mod  # noqa: E402
from minifmt.stream import Reader, create_reader, read_records  # noqa: E402

REG = Registry.load(ROOT / "forks")


def _errs(errors):
    return [e.to_dict() for e in errors]


def _reference(text, contract, strict):
    """(canonical, errors, diagnostics) of parse(), or ('raise', errors)."""
    try:
        doc = parse(text, contract, strict=strict)
    except MiniValidationError as e:
        return ("raise", _errs(e.errors))
    return (doc.to_canonical(), _errs(doc.errors), doc.diagnostics())


def _streamed(chunks, contract, strict):
    reader = Reader(contract, strict=strict)
    emitted = []
    try:
        for ch in chunks:
            emitted.extend(reader.push(ch))
        res = reader.end()
        emitted.extend(res.final_records)
    except MiniValidationError as e:
        return ("raise", _errs(e.errors)), emitted, getattr(e, "result", None)
    return (res.document.to_canonical(), _errs(res.errors), res.document.diagnostics()), emitted, res


def _text_splits(text, rng):
    yield "one-char", list(text)
    for _ in range(3):
        cuts, i = [], 0
        while i < len(text):
            k = rng.randint(1, 17)
            cuts.append(text[i:i + k])
            i += k
        yield "random", cuts
    yield "whole", [text]


def _byte_splits(text, rng):
    data = text.encode("utf-8")
    yield "one-byte", [data[i:i + 1] for i in range(len(data))]
    cuts, i = [], 0
    while i < len(data):
        k = rng.randint(1, 9)
        cuts.append(data[i:i + k])
        i += k
    yield "random-bytes", cuts


def _documents():
    """(label, text, contract) over every official family fixture and applicable conformance case."""
    for c in REG:
        for f in sorted((REG.paths[c.prefix] / "fixtures").glob("*.mini")):
            yield f"{c.prefix}/{f.name}", f.read_text(encoding="utf-8"), c
    for case in run_python.load_cases():
        if case["mode"] in ("strict", "lenient"):
            yield f"case/{case['id']}", case["input"], run_python.case_contract(case)


class TestEquivalenceWithParse(unittest.TestCase):
    def check(self, label, text, contract):
        rng = random.Random(label)
        for strict in (False, True):
            ref = _reference(text, contract, strict)
            for kind, chunks in list(_text_splits(text, rng)) + list(_byte_splits(text, rng)):
                with self.subTest(doc=label, strict=strict, split=kind):
                    got, emitted, res = _streamed(chunks, contract, strict)
                    if ref[0] == "raise" and not strict and got[0] != "raise":
                        # parse() raises E01 for an empty document even in lenient mode;
                        # the tolerant reader reports the same errors in its result.
                        self.assertEqual(ref[1], got[1])
                        self.assertEqual(res.valid, 0)
                        continue
                    self.assertEqual(ref, got)
                    if got[0] != "raise":
                        # every accepted record was emitted once, in order, with its line
                        self.assertEqual([r.record for r in emitted], res.records)
                        self.assertEqual([r.line for r in emitted], res.document.record_lines)
                        self.assertEqual([r.index for r in emitted], list(range(len(emitted))))

    def test_official_families_and_conformance_cases(self):
        n = 0
        for label, text, contract in _documents():
            self.check(label, text, contract)
            n += 1
        self.assertGreater(n, 150)

    def test_line_break_and_bom_variants(self):
        c = REG.get("card")
        base = (REG.paths["card"] / "fixtures" / "valid.mini").read_text(encoding="utf-8").rstrip("\n")
        variants = {
            "lf-final": base + "\n", "crlf": base.replace("\n", "\r\n") + "\r\n", "bom": "\ufeff" + base,
            "blank-lines": base.replace("\n", "\n\n  \n"), "truncated": base[:-7],
            "multibyte": base.replace("|", "|ñá€😀", 3), "only-blank": "\n \n", "empty": "",
        }
        for name, text in variants.items():
            self.check(f"variant/{name}", text, c)


class TestReaderApi(unittest.TestCase):
    def setUp(self):
        self.c = REG.get("card")
        self.text = (REG.paths["card"] / "fixtures" / "valid.mini").read_text(encoding="utf-8")

    def test_records_are_emitted_when_their_line_closes(self):
        seen = []
        headers = []
        reader = create_reader(self.c, on_record=seen.append, on_header=lambda p, h, l: headers.append((p, h["n"], l)))
        lines = self.text.split("\n")
        self.assertEqual(reader.push(lines[0]), [])
        self.assertIsNone(reader.header)
        self.assertEqual(reader.push("\n"), [])
        self.assertEqual(headers, [("card", 12, 1)])
        self.assertEqual(reader.push(lines[1][:5]), [])
        self.assertEqual(reader.pending, lines[1][:5])
        out = reader.push(lines[1][5:] + "\n" + lines[2][:3])
        self.assertEqual(len(out), 1)
        self.assertEqual((out[0].line, out[0].index), (2, 0))
        self.assertEqual(seen, out)
        self.assertEqual(reader.progress, stream_mod.ReaderProgress(12, 1, 1, 0))
        self.assertEqual(reader.pending, lines[2][:3])
        self.assertFalse(reader.ended)

    def test_truncated_output_is_reported(self):
        cut = self.text.rstrip("\n")
        cut = cut[:cut.rfind("|")]  # drop the last field(s) of the last record, no final LF
        res = Reader(self.c).end(cut)
        self.assertFalse(res.terminated)
        self.assertTrue(res.truncated)
        self.assertFalse(res.complete)
        self.assertIsNotNone(res.incomplete)
        self.assertEqual(res.incomplete.line, 13)
        self.assertFalse(res.incomplete.is_header)
        self.assertEqual(res.expected, 12)
        self.assertEqual(res.received, 12)
        self.assertEqual(res.valid, 11)
        self.assertEqual(res.document.truncated, parse(cut, self.c, strict=False).truncated)

    def test_missing_and_excess_counts(self):
        lines = self.text.rstrip("\n").split("\n")
        res = Reader(self.c).end("\n".join(lines[:6]) + "\n")
        self.assertEqual((res.expected, res.received, res.missing, res.excess), (12, 5, 7, 0))
        self.assertTrue(res.truncated and res.terminated and res.incomplete is None)
        res = Reader(self.c).end("\n".join(lines + lines[1:2]).replace("|n=12", "|n=11") + "\n")
        self.assertEqual((res.missing, res.excess), (0, 2))

    def test_strict_reader_raises_with_result(self):
        reader = Reader(self.c, strict=True)
        reader.push(self.text.replace("|n=12", "|n=13"))
        with self.assertRaises(MiniValidationError) as cm:
            reader.end()
        self.assertEqual(cm.exception.codes, ["E04"])
        self.assertEqual(cm.exception.result.valid, 12)

    def test_empty_document(self):
        res = Reader(self.c).end()
        self.assertEqual([e.code for e in res.errors], ["E01"])
        with self.assertRaises(MiniValidationError):
            Reader(self.c, strict=True).end("  \n")

    def test_on_error_receives_every_error_once(self):
        bad = self.text.replace("|n=12", "|n=40").replace("\nc2|", "\nc1|", 1)
        got = []
        res = Reader(self.c, on_error=got.append).end(bad)
        self.assertEqual(_errs(got), _errs(res.errors))
        self.assertEqual({e.code for e in got}, {"E04", "E11"})

    def test_misuse(self):
        reader = Reader(self.c)
        reader.push("card|n=1\n")
        with self.assertRaises(TypeError):
            reader.push(b"x")
        with self.assertRaises(TypeError):
            Reader(self.c).push(42)
        reader.end()
        with self.assertRaises(RuntimeError):
            reader.push("x")
        with self.assertRaises(RuntimeError):
            reader.end()
        with self.assertRaises(TypeError):
            Reader("card")

    def test_contract_dict_and_split_multibyte_character(self):
        c = {"prefix": "t", "core": [{"name": "w", "type": "str"}]}
        data = "t|n=2\nñandú\n😀|\\|\n".replace("|\\|", "\\|").encode("utf-8")
        reader = Reader(c)
        recs = []
        for i in range(len(data)):
            recs.extend(reader.push(data[i:i + 1]))
        res = reader.end()
        self.assertEqual([r.record["w"] for r in recs], ["ñandú", "😀|"])
        self.assertTrue(res.complete)
        # a character cut at the very end is decoded (with replacement) when the stream closes
        res = Reader(c).end("t|n=1\nñ".encode("utf-8")[:-1])
        self.assertEqual(res.records[0]["w"], "\ufffd")

    def test_read_records_generator_returns_result(self):
        def run():
            result = yield from read_records(iter(self.text), self.c)
            return result

        gen = run()
        records = []
        try:
            while True:
                records.append(next(gen))
        except StopIteration as stop:
            result = stop.value
        self.assertEqual(len(records), 12)
        self.assertEqual(result.valid, 12)
        self.assertEqual(result.records, [])  # not retained by default
        kept = list(read_records(self.text.encode("utf-8"), self.c, keep_records=True))
        self.assertEqual(len(kept), 12)

    def test_file_object_as_source(self):
        path = REG.paths["a"] / "fixtures" / "valid.mini"
        with open(path, "rb") as fh:
            got = [r.record for r in read_records(fh, REG.get("a"))]
        self.assertEqual(got, parse(path.read_text(encoding="utf-8"), REG.get("a")).records)


# ----------------------------------------------------------------- memory
_MEM_CONTRACT = Contract.from_dict({"prefix": "m", "core": [{"name": "id", "type": "int"}, {"name": "tag", "type": "str"}],
                                   "extensions": [{"name": "note", "type": "str"}]})


def _generated(n):
    """Lazily generated document of n records (never materialised)."""
    yield f"m|n={n}\n"
    for i in range(n):
        yield f"{i}|r{i % 7}\n"


def _peak(n):
    tracemalloc.start()
    try:
        count = 0
        gen = read_records(_generated(n), _MEM_CONTRACT)
        try:
            while True:
                next(gen)
                count += 1
        except StopIteration as stop:
            result = stop.value
        _, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
    assert count == n and result.complete and result.valid == n
    return peak


class TestConstantMemory(unittest.TestCase):
    SMALL = 10_000

    def assert_flat(self, big):
        _peak(1_000)  # warm-up: caches and lazily created objects
        small = _peak(self.SMALL)
        large = _peak(big)
        # a retained record costs well over 100 bytes; a growing reader would exceed this bound by far
        self.assertLess(large, small * 1.5 + 64_000, f"peak {small} B for {self.SMALL} vs {large} B for {big}")

    def test_peak_memory_does_not_grow_200k(self):
        self.assert_flat(200_000)

    @unittest.skipUnless(os.environ.get("MINI_STREAM_MILLION") == "1",
                         "1 000 000 records take minutes under tracemalloc; set MINI_STREAM_MILLION=1")
    def test_peak_memory_does_not_grow_1m(self):
        self.assert_flat(1_000_000)


if __name__ == "__main__":
    unittest.main()
