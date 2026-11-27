"""Tests verifying lossless round-trips for all 2026 competitor encoders and bench.py mini_v2."""
from __future__ import annotations

import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from benchmark import competitors
from benchmark.public.baselines import equivalent
from minifmt import bench, domain


def test_all_competitors_roundtrip_flat_wrapped_and_nested():
    docs = [
        ("flat", [{"id": 1, "tag": "hi, there", "n": 2.5, "ok": True, "opt": None},
                  {"id": 2, "tag": "123numeric", "n": -1, "ok": False}]),
        ("wrapped", {"meta": {"batch": "B1"}, "items": [
            {"id": 10, "arr": [1, 2, 3], "obj": {"k": "v"}},
            {"id": 11, "arr": [], "obj": {"k": "a\nb"}},
        ]}),
    ]
    for name, doc in docs:
        for enc_fn, dec_fn in (
            (competitors.ison_encode, competitors.ison_decode),
            (competitors.lean_encode, competitors.lean_decode),
            (competitors.tonl_encode, competitors.tonl_decode),
            (competitors.hedl_encode, competitors.hedl_decode),
            (competitors.raif_encode, competitors.raif_decode),
            (competitors.json_positional_encode, competitors.json_positional_decode),
            (competitors.json_short_encode, competitors.json_short_decode),
        ):
            encoded = enc_fn(doc, name)
            decoded = dec_fn(encoded, name, doc)
            assert equivalent(decoded, doc), f"{enc_fn.__name__} failed on {name}"


def test_run_bench_domain_includes_mini_v2(tmp_path):
    doc = [{"id": i, "prefix_url": f"https://cdn.example.com/{i}", "const": "shared_label"} for i in range(1, 7)]
    c = domain.infer_contract([doc], "row")
    cfile = tmp_path / "contract.json"
    dfile = tmp_path / "doc.json"
    cfile.write_text(json.dumps(c), encoding="utf-8")
    dfile.write_text(json.dumps(doc), encoding="utf-8")
    report = bench.run_bench(str(dfile), contract_path=str(cfile), enc="o200k_base")
    fmts = [r["format"] for r in report["formats"]]
    assert "mini_v2" in fmts and "mini" in fmts
    assert "saving vs JSON compact" in bench.format_table(report)
