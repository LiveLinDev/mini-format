"""Token comparison of one document across serialization formats (``mini bench``).

A ``.mini`` file is converted to its canonical object (SPEC §7, integral
numbers written as integers); a ``.json`` file is validated against the
contract and measured as provided.  The object is serialised as ``.mini``,
compact JSON, indented JSON,
YAML, CSV and TOON with the same rules as the reference benchmark
(``benchmark/formats.py``): CSV uses the flattened schema, ``toon`` is the
official TOON encoder applied to the canonical object as is and ``toon_flat``
to the flattened schema.  Tokens are counted with :mod:`minifmt.tokens` and
every format is compared with compact JSON.

Formats whose dependency is missing are reported as unavailable, never
estimated: YAML needs ``pyyaml``; TOON needs ``node`` and the vendored
official bundle ``benchmark/toon_ref/toon.bundle.js`` of a source checkout.
For a domain-profile contract (``--contract``) the ``.mini`` text is produced
by :mod:`minifmt.domain` and CSV is emitted only for flat tabular data.
"""
from __future__ import annotations

import csv
import io
import json
import shutil
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .contract import Contract
from .serializer import dumps
from .values import format_number

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
TOON_BUNDLE = REPO_ROOT / "benchmark" / "toon_ref" / "toon.bundle.js"
BASELINE = "json_compact"
LABELS = {
    "mini": ".mini", "json_compact": "JSON compact", "json_pretty": "JSON indented", "yaml": "YAML",
    "csv": "CSV (flattened)", "toon": "TOON (official, as-is)", "toon_flat": "TOON (flattened, tabular)",
}
_SCALARS = ("str", "int", "float", "bool", "enum")

_TOON_JS = (
    "const fs=require('fs'),vm=require('vm');"
    "vm.runInThisContext(fs.readFileSync(process.argv[1],'utf8'));"
    "const docs=JSON.parse(fs.readFileSync(0,'utf8'));"
    "process.stdout.write(JSON.stringify(docs.map(d=>{const t=TOON.encode(d);let rt=false;"
    "try{rt=JSON.stringify(TOON.decode(t))===JSON.stringify(d)}catch(e){}return {toon:t,roundtrip:rt}})));"
)


class BenchError(ValueError):
    """Actionable error of ``mini bench`` (missing tokenizer, unreadable input...)."""


class Unavailable(Exception):
    pass


# ------------------------------------------------------------ flattening
# Same rules as benchmark/formats.py (flatten_record / flatten_doc / csv_ser).
def _s(v: Any) -> str:
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, float):
        return format_number(v)
    return "" if v is None else str(v)


def _list_arity(f: Any, header: Dict[str, Any]) -> Optional[int]:
    if f.count_key and isinstance(header.get(f.count_key), int):
        return int(header[f.count_key])
    if f.min is not None and f.max is not None and f.min == f.max:
        return int(f.min)
    return None


def flatten_record(rec: Dict[str, Any], c: Contract, header: Dict[str, Any]) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    for f in c.fields:
        if f.type in _SCALARS:
            out[f.name] = rec.get(f.name)
        elif f.type in ("list", "mlist"):
            key = f.name if f.type == "list" else f.json_items
            vals = rec.get(key) or []
            k = _list_arity(f, header)
            if k:
                for i in range(k):
                    out[f"{key}_{i+1}"] = vals[i] if i < len(vals) else None
            else:
                out[key] = ";".join(_s(v) for v in vals)
            if f.type == "mlist":
                sel = rec.get(f.json_selected)
                if isinstance(sel, list):
                    out[f.json_selected] = ";".join(str(i + 1) for i in sel)
                else:
                    out[f.json_selected] = (sel + 1) if sel is not None else None
        elif f.type == "tuple":
            t = rec.get(f.name) or {}
            for comp in f.items:
                out[f"{f.name}_{comp.name}"] = t.get(comp.name)
    return out


def flatten_doc(obj: Dict[str, Any], c: Contract) -> Dict[str, Any]:
    header = obj["header"]
    return {"header": header, c.records_key: [flatten_record(r, c, header) for r in obj[c.records_key]]}


def _csv(rows: List[Dict[str, Any]]) -> str:
    cols = list(rows[0].keys()) if rows else []
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n", quoting=csv.QUOTE_MINIMAL)
    w.writerow(cols)
    for r in rows:
        w.writerow([_s(r.get(k)) for k in cols])
    return buf.getvalue().rstrip("\n")


def _tabular_rows(value: Any) -> List[Dict[str, Any]]:
    """Rows of flat JSON (a list of flat objects, or an object holding exactly one)."""
    if isinstance(value, dict):
        lists = [v for v in value.values() if isinstance(v, list)]
        if len(lists) != 1 or any(isinstance(v, dict) for v in value.values()):
            raise Unavailable("not tabular: the document is not a single array of flat objects")
        value = lists[0]
    if not isinstance(value, list) or not value or not all(isinstance(r, dict) for r in value):
        raise Unavailable("not tabular: the document is not a single array of flat objects")
    cols: List[str] = []
    for r in value:
        for k, v in r.items():
            if isinstance(v, (dict, list)):
                raise Unavailable(f"not tabular: field '{k}' is nested")
            if k not in cols:
                cols.append(k)
    return [{k: r.get(k) for k in cols} for r in value]


# ------------------------------------------------------------------ TOON
def toon_encode(docs: List[Any], bundle: Optional[Path] = None) -> List[Tuple[str, bool]]:
    """Encode documents with the vendored official TOON bundle through ``node``."""
    bundle = Path(bundle) if bundle else TOON_BUNDLE
    node = shutil.which("node")
    if not node:
        raise Unavailable("node not found on PATH (needed by the official TOON encoder)")
    if not bundle.is_file():
        raise Unavailable(f"official TOON bundle not found ({bundle}); run from a source checkout")
    proc = subprocess.run([node, "-e", _TOON_JS, str(bundle)],
                          input=json.dumps(docs, ensure_ascii=False).encode("utf-8"), capture_output=True)
    if proc.returncode != 0:
        raise Unavailable("TOON encoder failed: " + proc.stderr.decode("utf-8", "replace").strip()[:200])
    return [(r["toon"], bool(r["roundtrip"])) for r in json.loads(proc.stdout.decode("utf-8"))]


# ----------------------------------------------------------------- bench
def _tokenizer(enc: str) -> Any:
    from .tokens import get_tokenizer
    try:
        tk = get_tokenizer(enc)
        tk.count("mini")
        return tk
    except Exception as e:  # noqa: BLE001 - any failure means "no usable tokenizer"
        raise BenchError(
            f"no tokenizer available for encoding '{enc}': install tiktoken "
            f"(pip install \"mini-format[bench]\") or run from a source checkout with the 'regex' package "
            f"and benchmark/vocab/{enc}.tiktoken ({type(e).__name__}: {e})") from None


def serialize_family(obj: Dict[str, Any], c: Contract, toon_bundle: Optional[Path] = None) -> Dict[str, Any]:
    """Texts per format for a canonical object of a .mini family (str, or Unavailable)."""
    out: Dict[str, Any] = {
        "mini": dumps(obj, c),
        "json_compact": json.dumps(obj, ensure_ascii=False, separators=(",", ":")),
        "json_pretty": json.dumps(obj, ensure_ascii=False, indent=2),
    }
    out["yaml"] = _yaml(obj)
    out["csv"] = _csv(flatten_doc(obj, c)[c.records_key])
    try:
        (as_is, _), (flat, _) = toon_encode([obj, flatten_doc(obj, c)], toon_bundle)
        out["toon"], out["toon_flat"] = as_is, flat
    except Unavailable as e:
        out["toon"] = out["toon_flat"] = e
    return out


def serialize_domain(value: Any, contract: Dict[str, Any], toon_bundle: Optional[Path] = None) -> Dict[str, Any]:
    from . import domain
    out: Dict[str, Any] = {
        "mini": domain.dumps(value, contract),
        "json_compact": json.dumps(value, ensure_ascii=False, separators=(",", ":")),
        "json_pretty": json.dumps(value, ensure_ascii=False, indent=2),
        "yaml": _yaml(value),
    }
    try:
        out["csv"] = _csv(_tabular_rows(value))
    except Unavailable as e:
        out["csv"] = e
    try:
        out["toon"] = toon_encode([value], toon_bundle)[0][0]
    except Unavailable as e:
        out["toon"] = e
    return out


def _yaml(obj: Any) -> Any:
    try:
        import yaml  # type: ignore
    except ImportError:
        return Unavailable("PyYAML not installed (pip install \"mini-format[bench]\")")
    return yaml.safe_dump(obj, allow_unicode=True, sort_keys=False, default_flow_style=False, width=10**6)


def _plain_numbers(value: Any) -> Any:
    """Integral floats as integers (JSON does not distinguish 3.0 from 3; SPEC §6)."""
    if isinstance(value, float) and value.is_integer():
        return int(value)
    if isinstance(value, dict):
        return {k: _plain_numbers(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_plain_numbers(v) for v in value]
    return value


def load_document(path: Path, prefix: Optional[str] = None, contract_path: Optional[str] = None,
                  forks: Optional[str] = None) -> Tuple[str, Any, Any, Dict[str, Any]]:
    """Return (kind, contract, canonical value, info) for a .mini or .json file."""
    from .parser import detect_prefix, parse
    from .registry import DEFAULT_FORKS_DIR, Registry
    text = Path(path).read_text(encoding="utf-8-sig")
    is_json = Path(path).suffix.lower() == ".json"
    if contract_path:
        from . import domain
        dc = domain.load_contract(contract_path)
        value = json.loads(text) if is_json else domain.decode(text, dc)
        return "domain", dc, value, {"profile": dc.get("profile"), "prefix": dc.get("prefix")}
    reg = Registry.load(forks or DEFAULT_FORKS_DIR)
    if is_json:
        obj = json.loads(text)
        p = prefix or (obj.get("prefix") if isinstance(obj, dict) else None)
        if not p:
            raise BenchError("cannot detect the family of a JSON document; pass -p PREFIX")
        c = reg.get(p)
        parse(dumps(obj, c), c)  # validate against the contract; the document is measured as provided
        if c.records_key not in obj:
            raise BenchError(f"JSON document lacks the records key '{c.records_key}' of family '{p}'")
    else:
        p = prefix or detect_prefix(text)
        if not p:
            raise BenchError("cannot detect prefix; pass -p PREFIX")
        c = reg.get(p)
        obj = _plain_numbers(parse(text, c).to_canonical())
    return "family", c, obj, {"prefix": c.prefix, "records": len(obj[c.records_key])}


def run_bench(path: str, prefix: Optional[str] = None, contract_path: Optional[str] = None,
              enc: str = "o200k_base", forks: Optional[str] = None,
              toon_bundle: Optional[Path] = None) -> Dict[str, Any]:
    """Measure tokens per format; returns a JSON-serialisable report."""
    tk = _tokenizer(enc)
    kind, contract, value, info = load_document(Path(path), prefix, contract_path, forks)
    texts = serialize_family(value, contract, toon_bundle) if kind == "family" else serialize_domain(value, contract, toon_bundle)
    base = tk.count(texts[BASELINE])
    rows = []
    for name, text in texts.items():
        row: Dict[str, Any] = {"format": name, "label": LABELS[name]}
        if isinstance(text, Exception):
            row.update(available=False, reason=str(text))
        else:
            n = tk.count(text)
            row.update(available=True, tokens=n, bytes=len(text.encode("utf-8")),
                       saving_vs_json_compact=round((base - n) / base * 100, 1) if base else 0.0)
        rows.append(row)
    order = ["mini", "toon_flat", "toon", "csv", "json_compact", "yaml", "json_pretty"]
    rows.sort(key=lambda r: order.index(r["format"]))
    report = {"file": str(path), "kind": kind, "encoding": enc, "backend": tk.backend,
              "baseline": BASELINE, "baseline_tokens": base}
    report.update(info)
    report["formats"] = rows
    return report


def format_table(report: Dict[str, Any]) -> str:
    head = f"{report['file']}  ({report['kind']}"
    if report.get("prefix"):
        head += f" {report['prefix']}"
    if report.get("records") is not None:
        head += f", {report['records']} records"
    head += f"; {report['encoding']} via {report['backend']})"
    lines = [head, f"{'format':28s} {'tokens':>8s} {'bytes':>8s} {'saving vs JSON compact':>24s}"]
    for r in report["formats"]:
        if r["available"]:
            lines.append(f"{r['label']:28s} {r['tokens']:8d} {r['bytes']:8d} {r['saving_vs_json_compact']:23.1f}%")
        else:
            lines.append(f"{r['label']:28s} {'n/a':>8s} {'':8s}  unavailable: {r['reason']}")
    return "\n".join(lines)
