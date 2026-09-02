"""Deterministic complementary experiments.

  ABL  ablation: Haiku outputs produced under the backslash-only draft spec,
       evaluated with the final v1.0 parser (raw/e1_ablation/)
  E4   prompt tax / break-even: fixed cost of teaching each format (spec block
       tokens) versus per-record savings -> number of records after which .mini
       is cheaper than the alternative even counting the specification
  E5   truncation recovery: cut every format's 100-record document at 200
       random byte offsets and count the records recoverable by a lenient
       reader (one that keeps complete records and drops the broken tail)
Outputs results/ablation.csv, results/e4_breakeven.csv, results/e5_truncation.csv
"""
from __future__ import annotations

import csv
import json
import random
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "benchmark"))
import protocol as P  # noqa: E402
import domains  # noqa: E402
import formats  # noqa: E402
from minifmt import parse  # noqa: E402
from minifmt.tokens import get_tokenizer  # noqa: E402

RES = HERE / "results"
RES.mkdir(exist_ok=True)


def write_csv(path, rows):
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)


# ------------------------------------------------------------------ ABL
def ablation():
    rows = []
    d = HERE / "raw" / "e1_ablation" / "haiku" / "mini_backslash_only"
    for f in sorted(d.glob("*.txt")):
        r = P.evaluate_e1("mini", f.read_text(encoding="utf-8"))
        rows.append({"model": "haiku", "spec": "v1-draft (backslash only)", "sample": f.stem, **r})
    d2 = HERE / "raw" / "e1" / "haiku" / "mini"
    for f in sorted(d2.glob("*.txt")):
        r = P.evaluate_e1("mini", f.read_text(encoding="utf-8"))
        rows.append({"model": "haiku", "spec": "v1.0 (quotes or escapes + count key)", "sample": f.stem, **r})
    write_csv(RES / "ablation.csv", rows)
    for spec in sorted({r["spec"] for r in rows}):
        g = [r for r in rows if r["spec"] == spec]
        print(f"ABL {spec}: n={len(g)} parseable={100*sum(r['parseable'] for r in g)/len(g):.1f}% round_trip={100*sum(r['round_trip'] for r in g)/len(g):.1f}%")


# ------------------------------------------------------------------ E4
def breakeven():
    tk = get_tokenizer("o200k_base")
    c = P.REG.get("a")
    spec_tokens = {fmt: tk.count(P.spec_e1(fmt)) for fmt in P.PARSERS_E1}
    # marginal tokens per record from the benchmark scaling (n=100 -> 500)
    docs = {n: domains.expand("a", n) for n in (100, 500)}
    flat = formats.toon_batch([formats.flatten_doc(docs[n], c) for n in (100, 500)])
    texts = {
        "json": {n: formats.json_compact(docs[n], c) for n in docs},
        "yaml": {n: formats.yaml_ser(docs[n], c) for n in docs},
        "xml": {n: formats.xml_ser(docs[n], c) for n in docs},
        "csv": {n: formats.csv_ser(docs[n], c) for n in docs},
        "toon": {100: flat[0][0], 500: flat[1][0]},
        "mini": {n: formats.mini_ser(docs[n], c) for n in docs},
    }
    per_rec = {f: (tk.count(t[500]) - tk.count(t[100])) / 400 for f, t in texts.items()}
    rows = []
    for f in texts:
        if f == "mini":
            continue
        save = per_rec[f] - per_rec["mini"]
        extra_spec = spec_tokens["mini"] - spec_tokens[f]
        be = (extra_spec / save) if save > 0 else float("inf")
        rows.append({"alternative": f, "spec_tokens_alt": spec_tokens[f], "spec_tokens_mini": spec_tokens["mini"],
                     "tokens_per_record_alt": round(per_rec[f], 2), "tokens_per_record_mini": round(per_rec["mini"], 2),
                     "saving_per_record": round(save, 2), "breakeven_records": (round(be, 1) if be != float("inf") else "never"),
                     "breakeven_documents_of_12": (round(be / 12, 2) if be != float("inf") else "never")})
    write_csv(RES / "e4_breakeven.csv", rows)
    for r in rows:
        print("E4", r)


# ------------------------------------------------------------------ E5
def lenient_records(fmt: str, text: str, c) -> int:
    """Records recoverable from a possibly truncated document by a lenient reader."""
    if fmt == "mini":
        try:
            return len(parse(text, c, strict=False).records)
        except Exception:  # noqa: BLE001
            return 0
    if fmt == "csv":
        import io
        try:
            rows = list(csv.reader(io.StringIO(text)))
        except Exception:  # noqa: BLE001
            return 0
        if not rows:
            return 0
        width = len(rows[0])
        return sum(1 for r in rows[1:] if len(r) == width and all(x != "" for x in (r[0], r[-1])))
    if fmt == "toon_flat":
        lines = text.split("\n")
        try:
            hdr = next(i for i, l in enumerate(lines) if l.startswith(f"{c.records_key}["))
        except StopIteration:
            return 0
        width = lines[hdr].count(",") + 1
        good = 0
        for l in lines[hdr + 1:]:
            if not l.startswith("  "):
                break
            # a complete row has the declared number of fields (quote-aware count)
            n_fields, inq = 1, False
            for ch in l:
                if ch == '"':
                    inq = not inq
                elif ch == "," and not inq:
                    n_fields += 1
            if n_fields == width and not inq and l.rstrip() == l:
                good += 1
        return good
    if fmt in ("json", "json_pretty"):
        try:
            obj = json.loads(text)
            return len(obj[c.records_key])
        except Exception:  # noqa: BLE001
            return 0
    if fmt == "yaml":
        import yaml
        try:
            obj = yaml.safe_load(text)
            return len(obj[c.records_key]) if isinstance(obj, dict) and isinstance(obj.get(c.records_key), list) else 0
        except Exception:  # noqa: BLE001
            return 0
    if fmt == "xml":
        import xml.etree.ElementTree as ET
        try:
            root = ET.fromstring(text)
            return len(root.findall("rec"))
        except Exception:  # noqa: BLE001
            return 0
    raise KeyError(fmt)


def truncation(n_cuts: int = 200, n_records: int = 100, seed: int = 7):
    rng = random.Random(seed)
    rows = []
    for prefix in ("a", "tc", "log"):
        c = P.REG.get(prefix)
        obj = domains.expand(prefix, n_records)
        flat = formats.toon_batch([formats.flatten_doc(obj, c)])[0][0]
        texts = {"mini": formats.mini_ser(obj, c), "toon_flat": flat, "csv": formats.csv_ser(obj, c),
                 "json": formats.json_compact(obj, c), "yaml": formats.yaml_ser(obj, c), "xml": formats.xml_ser(obj, c)}
        for fmt, text in texts.items():
            L = len(text)
            rec = []
            for _ in range(n_cuts):
                cut = rng.randint(L // 10, L - 1)
                frac = cut / L
                got = lenient_records(fmt, text[:cut], c)
                rec.append((frac, got))
            mean_rec = sum(g for _, g in rec) / len(rec)
            # expected complete records at the cut point ≈ frac*n
            eff = sum(g / max(1, int(f * n_records)) for f, g in rec) / len(rec)
            rows.append({"prefix": prefix, "format": fmt, "cuts": n_cuts, "mean_records_recovered": round(mean_rec, 1),
                         "recovery_efficiency": round(100 * min(1.0, eff), 1),
                         "zero_recovery_pct": round(100 * sum(1 for _, g in rec if g == 0) / len(rec), 1)})
    write_csv(RES / "e5_truncation.csv", rows)
    for r in rows:
        print("E5", r)


if __name__ == "__main__":
    ablation()
    breakeven()
    truncation()
