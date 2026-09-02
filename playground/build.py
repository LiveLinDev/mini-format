"""Assemble playground/index.html (single self-contained file for GitHub Pages).

    python playground/build.py
Embeds js/mini.js, the official TOON browser bundle, every fork contract with
its fixtures and the benchmark summary.
"""
from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
from minifmt import Registry  # noqa: E402


def main() -> None:
    tpl = (ROOT / "playground" / "template.html").read_text(encoding="utf-8")
    mini_js = (ROOT / "js" / "mini.js").read_text(encoding="utf-8")
    toon_js = (ROOT / "benchmark" / "toon_ref" / "toon.bundle.js").read_text(encoding="utf-8")
    reg = Registry.load(ROOT / "forks")
    forks = []
    order = ["a", "q", "card", "sum", "map", "r", "s", "code", "tc", "us", "log", "ner", "cat", "cls"]
    for c in sorted(reg, key=lambda c: (order.index(c.prefix) if c.prefix in order else 99, c.prefix)):
        p = reg.paths[c.prefix]
        entry = {"prefix": c.prefix, "contract": json.loads((p / "contract.json").read_text(encoding="utf-8")),
                 "example": (p / "fixtures" / "valid.mini").read_text(encoding="utf-8")}
        esc = p / "fixtures" / "escaping.mini"
        if esc.exists():
            entry["escaping"] = esc.read_text(encoding="utf-8")
        forks.append(entry)
    bench = []
    summ = ROOT / "benchmark" / "results" / "summary_12.csv"
    if summ.exists():
        for r in csv.DictReader(open(summ, encoding="utf-8")):
            bench.append({k: (float(v) if k != "prefix" and "." in v else (int(v) if k != "prefix" else v)) for k, v in r.items()})

    def safe(js: str) -> str:  # never let the JSON close the script tag
        return js.replace("</script", "<\\/script")

    html = (tpl.replace("__MINI_JS__", safe(mini_js)).replace("__TOON_JS__", safe(toon_js))
               .replace("__FORKS_JSON__", safe(json.dumps(forks, ensure_ascii=False)))
               .replace("__BENCH_JSON__", safe(json.dumps(bench))))
    out = ROOT / "playground" / "index.html"
    out.write_text(html, encoding="utf-8")
    print(f"wrote {out} ({len(html.encode('utf-8'))/1024:.0f} KB, {len(forks)} forks, {len(bench)} bench rows)")


if __name__ == "__main__":
    main()
