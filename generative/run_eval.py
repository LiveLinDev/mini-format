"""Aggregate raw model outputs (generative/raw/**) into results CSVs.

Layout of raw/:
  raw/e1/<model>/<fmt>/<k>.txt        E1 serialization fidelity
  raw/e2/<model>/<prefix>/<k>.txt     E2 fork transfer
  raw/e3/<model>/<prefix>/<k>.py      E3 parser synthesis
Outputs: results/e1_samples.csv, results/e1_summary.csv, results/e2_*.csv, results/e3_*.csv
"""
from __future__ import annotations

import csv
import sys
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import protocol as P  # noqa: E402

RAW = HERE / "raw"
RES = HERE / "results"


def write_csv(path: Path, rows):
    if not rows:
        return
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)


def pct(xs):
    return round(100 * sum(1 for x in xs if x) / len(xs), 1) if xs else 0.0


def main():
    RES.mkdir(exist_ok=True)
    # ------------------------------------------------------------- E1
    rows = []
    for f in sorted((RAW / "e1").glob("*/*/*.txt")) if (RAW / "e1").exists() else []:
        model, fmt, k = f.parent.parent.name, f.parent.name, f.stem
        r = P.evaluate_e1(fmt, f.read_text(encoding="utf-8"))
        rows.append({"model": model, "format": fmt, "sample": k, **r})
    write_csv(RES / "e1_samples.csv", rows)
    summ = []
    groups = defaultdict(list)
    for r in rows:
        groups[(r["model"], r["format"])].append(r)
    for (model, fmt), g in sorted(groups.items()):
        classes = defaultdict(int)
        for r in g:
            if r["error_class"]:
                classes[r["error_class"]] += 1
        summ.append({"model": model, "format": fmt, "n": len(g), "parseable_pct": pct([r["parseable"] for r in g]),
                     "round_trip_pct": pct([r["round_trip"] for r in g]),
                     "mean_field_accuracy": round(sum(r["field_accuracy"] for r in g) / len(g), 4),
                     "errors": "; ".join(f"{k}:{v}" for k, v in sorted(classes.items()))})
    write_csv(RES / "e1_summary.csv", summ)
    for s in summ:
        print("E1", s)
    # ------------------------------------------------------------- E2
    rows = []
    for f in sorted((RAW / "e2").glob("*/*/*.txt")) if (RAW / "e2").exists() else []:
        model, prefix, k = f.parent.parent.name, f.parent.name, f.stem
        r = P.evaluate_e2(prefix, f.read_text(encoding="utf-8"))
        rows.append({"model": model, "prefix": prefix, "sample": k, **r})
    write_csv(RES / "e2_samples.csv", rows)
    summ = []
    groups = defaultdict(list)
    for r in rows:
        groups[(r["model"], r["prefix"])].append(r)
    for (model, prefix), g in sorted(groups.items()):
        classes = defaultdict(int)
        for r in g:
            if r["error_class"]:
                classes[r["error_class"]] += 1
        summ.append({"model": model, "prefix": prefix, "n": len(g), "parseable_pct": pct([r["parseable"] for r in g]),
                     "round_trip_pct": pct([r["round_trip"] for r in g]),
                     "mean_field_accuracy": round(sum(r["field_accuracy"] for r in g) / len(g), 4),
                     "mean_recovered_pct": round(sum(r["recovered_pct"] for r in g) / len(g), 1),
                     "errors": "; ".join(f"{k}:{v}" for k, v in sorted(classes.items()))})
    write_csv(RES / "e2_summary.csv", summ)
    for s in summ:
        print("E2", s)
    # ------------------------------------------------------------- E3
    rows = []
    for f in sorted((RAW / "e3").glob("*/*/*.py")) if (RAW / "e3").exists() else []:
        model, prefix, k = f.parent.parent.name, f.parent.name, f.stem
        r = P.evaluate_e3(prefix, f.read_text(encoding="utf-8"))
        rows.append({"model": model, "prefix": prefix, "sample": k, "all_ok": r.get("all_ok"), "valid_ok": r.get("valid_ok"),
                     "escaping_ok": r.get("escaping_ok"), "negatives_rejected": r.get("negatives_rejected"),
                     "detail": "; ".join(f"{k}={v}" for k, v in r.items() if k not in ("all_ok", "valid_ok", "escaping_ok", "negatives_rejected"))[:300]})
    write_csv(RES / "e3_samples.csv", rows)
    for r in rows:
        print("E3", r)


if __name__ == "__main__":
    main()
