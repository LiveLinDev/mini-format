"""Token benchmark: every fork × every format × several sizes × two tokenizers.

Outputs
-------
benchmark/results/tokens.csv      long table: prefix,n,tokenizer,format,tokens,bytes,payload_tokens
benchmark/results/summary_12.csv  per fork at n=12 (o200k_base): tokens per format + savings
benchmark/results/roundtrip.csv   parser round-trip + official TOON round-trip per fork
Run:  python benchmark/run_benchmark.py [--sizes 12,25,50,100,250,500]
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "benchmark"))

import domains  # noqa: E402
import formats  # noqa: E402
from minifmt import Registry, parse, canonical_equal  # noqa: E402
from minifmt.tokens import get_tokenizer  # noqa: E402

RESULTS = ROOT / "benchmark" / "results"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sizes", default="12,25,50,100,250,500")
    ap.add_argument("--tokenizers", default="o200k_base,cl100k_base")
    args = ap.parse_args()
    sizes = [int(s) for s in args.sizes.split(",")]
    toks = {name: get_tokenizer(name) for name in args.tokenizers.split(",")}
    reg = Registry.load(ROOT / "forks")
    RESULTS.mkdir(parents=True, exist_ok=True)

    rows = []
    rt_rows = []
    t0 = time.time()
    for prefix in reg.contracts:
        c = reg.get(prefix)
        docs = {n: domains.expand(prefix, n) for n in sizes}
        # official TOON encodes (batched: as-is and flattened)
        as_is = formats.toon_batch([docs[n] for n in sizes])
        flat = formats.toon_batch([formats.flatten_doc(docs[n], c) for n in sizes])
        for i, n in enumerate(sizes):
            obj = docs[n]
            texts = {
                "mini": formats.mini_ser(obj, c),
                "toon_flat": flat[i][0],
                "toon": as_is[i][0],
                "csv": formats.csv_ser(obj, c),
                "json_compact": formats.json_compact(obj, c),
                "yaml": formats.yaml_ser(obj, c),
                "xml": formats.xml_ser(obj, c),
                "json_pretty": formats.json_pretty(obj, c),
            }
            if n == 12:  # keep the 12-record documents as artefacts
                out = RESULTS / "docs" / prefix
                out.mkdir(parents=True, exist_ok=True)
                ext = {"mini": "mini", "toon_flat": "flat.toon", "toon": "toon", "csv": "csv", "json_compact": "json",
                       "yaml": "yaml", "xml": "xml", "json_pretty": "pretty.json"}
                for k, t in texts.items():
                    (out / f"dataset_12.{ext[k]}").write_text(t + "\n", encoding="utf-8")
                # round-trip checks
                back = parse(texts["mini"], c).to_canonical()
                ok = canonical_equal(back[c.records_key], obj[c.records_key])
                rt_rows.append({"prefix": prefix, "n": n, "mini_roundtrip": ok, "toon_official_roundtrip": as_is[i][1],
                                "toon_flat_roundtrip": flat[i][1]})
            for tname, tk in toks.items():
                payload = formats.payload_tokens(obj, tk.count)
                for fmt, text in texts.items():
                    rows.append({"prefix": prefix, "n": n, "tokenizer": tname, "format": fmt,
                                 "tokens": tk.count(text), "bytes": len(text.encode("utf-8")),
                                 "lines": text.count("\n") + 1, "payload_tokens": payload})
        print(f"{prefix:5s} done ({time.time()-t0:5.1f}s)", flush=True)

    with open(RESULTS / "tokens.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    with open(RESULTS / "roundtrip.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rt_rows[0].keys()))
        w.writeheader()
        w.writerows(rt_rows)

    # summary at n=12, o200k
    fmts = list(formats.FORMATS.keys())
    summary = []
    for prefix in reg.contracts:
        r = {"prefix": prefix}
        sub = {x["format"]: x for x in rows if x["prefix"] == prefix and x["n"] == 12 and x["tokenizer"] == "o200k_base"}
        for f in fmts:
            r[f] = sub[f]["tokens"]
        r["payload"] = sub["mini"]["payload_tokens"]
        r["mini_vs_json_compact_pct"] = round(100 * (1 - sub["mini"]["tokens"] / sub["json_compact"]["tokens"]), 1)
        r["mini_vs_toon_flat_pct"] = round(100 * (1 - sub["mini"]["tokens"] / sub["toon_flat"]["tokens"]), 1)
        r["mini_vs_toon_pct"] = round(100 * (1 - sub["mini"]["tokens"] / sub["toon"]["tokens"]), 1)
        r["mini_vs_csv_pct"] = round(100 * (1 - sub["mini"]["tokens"] / sub["csv"]["tokens"]), 1)
        r["mini_overhead_pct"] = round(100 * (1 - sub["mini"]["payload_tokens"] / sub["mini"]["tokens"]), 1)
        r["json_overhead_pct"] = round(100 * (1 - sub["json_compact"]["payload_tokens"] / sub["json_compact"]["tokens"]), 1)
        r["toon_flat_overhead_pct"] = round(100 * (1 - sub["toon_flat"]["payload_tokens"] / sub["toon_flat"]["tokens"]), 1)
        summary.append(r)
    with open(RESULTS / "summary_12.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(summary[0].keys()))
        w.writeheader()
        w.writerows(summary)
    print(json.dumps(summary, indent=1)[:3000])
    print(f"total {time.time()-t0:.1f}s; rows={len(rows)}")


if __name__ == "__main__":
    main()
