"""Contract-driven serializers used by the benchmark.

Every format is generated from the *same* canonical object so that the
comparison is between equivalent documents:

* ``json_compact`` / ``json_pretty`` — ``json.dumps`` with/without indent
* ``yaml`` — PyYAML block style, unicode preserved
* ``xml`` — one element per record, scalars as child elements, lists as
  ``<i>`` children (selected elements carry ``sel="1"``), tuples as attributes
* ``csv`` — RFC 4180 rows over a *flattened* schema (fixed-arity lists become
  numbered columns, variable lists are ';'-joined, tuples become columns);
  document metadata is dropped because CSV cannot carry it
* ``toon`` — the official TOON encoder (spec 4.1) applied to the canonical
  object as is (nested objects / arrays inside records force list form)
* ``toon_flat`` — the official TOON encoder applied to the flattened schema
  (tabular form, the best case for TOON)
* ``mini`` — the reference .mini serializer
* ``payload`` — not a format: the content-only token lower bound (each leaf
  value tokenised alone and summed), used to compute structural overhead
"""
from __future__ import annotations

import csv
import io
import json
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Tuple
from xml.sax.saxutils import escape as xesc

import yaml

from minifmt import Contract, dumps
from minifmt.values import format_number

HERE = Path(__file__).resolve().parent
NODE_CMD = ["node", "--experimental-strip-types", "--experimental-transform-types", str(HERE / "toon_ref" / "toon_encode.mjs")]


# --------------------------------------------------------------- flattening
def list_arity(f, header: Dict[str, Any]) -> int | None:
    if f.count_key and isinstance(header.get(f.count_key), int):
        return int(header[f.count_key])
    if f.min is not None and f.max is not None and f.min == f.max:
        return int(f.min)
    return None


def flatten_record(rec: Dict[str, Any], c: Contract, header: Dict[str, Any]) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    for f in c.fields:
        if f.type in ("str", "int", "float", "bool", "enum"):
            out[f.name] = rec.get(f.name)
        elif f.type == "list":
            vals = rec.get(f.name) or []
            k = list_arity(f, header)
            if k:
                for i in range(k):
                    out[f"{f.name}_{i+1}"] = vals[i] if i < len(vals) else None
            else:
                out[f.name] = ";".join(_s(v) for v in vals)
        elif f.type == "mlist":
            vals = rec.get(f.json_items) or []
            sel = rec.get(f.json_selected)
            k = list_arity(f, header)
            if k:
                for i in range(k):
                    out[f"{f.json_items}_{i+1}"] = vals[i] if i < len(vals) else None
            else:
                out[f.json_items] = ";".join(_s(v) for v in vals)
            if isinstance(sel, list):
                out[f.json_selected] = ";".join(str(i + 1) for i in sel)
            else:
                out[f.json_selected] = (sel + 1) if sel is not None else None
        elif f.type == "tuple":
            t = rec.get(f.name) or {}
            for comp in f.items:
                out[f"{f.name}_{comp.name}"] = t.get(comp.name)
    return out


def _s(v: Any) -> str:
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, float):
        return format_number(v)
    return "" if v is None else str(v)


def flatten_doc(obj: Dict[str, Any], c: Contract) -> Dict[str, Any]:
    header = obj["header"]
    rows = [flatten_record(r, c, header) for r in obj[c.records_key]]
    return {"header": header, c.records_key: rows}


# ------------------------------------------------------------------ formats
def json_compact(obj: Dict[str, Any], c: Contract) -> str:
    return json.dumps(obj, ensure_ascii=False, separators=(",", ":"))


def json_pretty(obj: Dict[str, Any], c: Contract) -> str:
    return json.dumps(obj, ensure_ascii=False, indent=2)


def yaml_ser(obj: Dict[str, Any], c: Contract) -> str:
    return yaml.safe_dump(obj, allow_unicode=True, sort_keys=False, default_flow_style=False, width=10**6)


def xml_ser(obj: Dict[str, Any], c: Contract) -> str:
    hdr = obj["header"]
    Q = {'"': "&quot;"}
    attrs = " ".join(f'{k}="{xesc(_s(v), Q)}"' for k, v in hdr.items() if not isinstance(v, (list, dict)))
    L = [f"<{c.prefix} {attrs}>"]
    for k, v in hdr.items():
        if isinstance(v, list):
            L.append(f"  <{k}>" + "".join(f"<i>{xesc(_s(x))}</i>" for x in v) + f"</{k}>")
        elif isinstance(v, dict):
            L.append(f"  <{k} " + " ".join(f'{kk}="{xesc(_s(vv))}"' for kk, vv in v.items()) + "/>")
    for rec in obj[c.records_key]:
        L.append("  <rec>")
        for f in c.fields:
            if f.type in ("str", "int", "float", "bool", "enum"):
                v = rec.get(f.name)
                if v is not None:
                    L.append(f"    <{f.name}>{xesc(_s(v))}</{f.name}>")
            elif f.type == "list":
                vals = rec.get(f.name) or []
                L.append(f"    <{f.name}>" + "".join(f"<i>{xesc(_s(x))}</i>" for x in vals) + f"</{f.name}>")
            elif f.type == "mlist":
                vals = rec.get(f.json_items) or []
                sel = rec.get(f.json_selected)
                sels = set(sel if isinstance(sel, list) else ([sel] if sel is not None else []))
                SEL = ' sel="1"'
                L.append(f"    <{f.json_items}>" + "".join(f"<i{SEL if i in sels else ''}>{xesc(_s(x))}</i>" for i, x in enumerate(vals)) + f"</{f.json_items}>")
            elif f.type == "tuple":
                t = rec.get(f.name)
                if t is not None:
                    L.append(f"    <{f.name} " + " ".join(f'{comp.name}="{xesc(_s(t.get(comp.name)))}"' for comp in f.items if t.get(comp.name) is not None) + "/>")
        L.append("  </rec>")
    L.append(f"</{c.prefix}>")
    return "\n".join(L)


def csv_ser(obj: Dict[str, Any], c: Contract) -> str:
    flat = flatten_doc(obj, c)
    rows = flat[c.records_key]
    cols = list(rows[0].keys()) if rows else []
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n", quoting=csv.QUOTE_MINIMAL)
    w.writerow(cols)
    for r in rows:
        w.writerow([_s(r.get(k)) for k in cols])
    return buf.getvalue().rstrip("\n")


def toon_batch(docs: List[Dict[str, Any]]) -> List[Tuple[str, bool]]:
    """Encode many documents with the official TOON encoder in one node call."""
    proc = subprocess.run(NODE_CMD, input=json.dumps(docs, ensure_ascii=False).encode("utf-8"),
                          capture_output=True, check=True)
    res = json.loads(proc.stdout.decode("utf-8"))
    return [(r["toon"], bool(r["roundtrip"])) for r in res]


def toon_ser(obj: Dict[str, Any], c: Contract) -> str:
    return toon_batch([obj])[0][0]


def toon_flat_ser(obj: Dict[str, Any], c: Contract) -> str:
    return toon_batch([flatten_doc(obj, c)])[0][0]


def mini_ser(obj: Dict[str, Any], c: Contract) -> str:
    return dumps(obj, c)


FORMATS = {
    "mini": mini_ser,
    "toon_flat": toon_flat_ser,
    "toon": toon_ser,
    "csv": csv_ser,
    "json_compact": json_compact,
    "yaml": yaml_ser,
    "xml": xml_ser,
    "json_pretty": json_pretty,
}
LABELS = {
    "mini": ".mini", "toon_flat": "TOON (flattened, tabular)", "toon": "TOON (official, as-is)", "csv": "CSV (flattened)",
    "json_compact": "JSON compact", "yaml": "YAML", "xml": "XML", "json_pretty": "JSON pretty",
}


# ------------------------------------------------------------------ payload
def leaf_values(obj: Any) -> List[str]:
    """All scalar leaves of an object as text (the irreducible content)."""
    out: List[str] = []
    if isinstance(obj, dict):
        for v in obj.values():
            out.extend(leaf_values(v))
    elif isinstance(obj, list):
        for v in obj:
            out.extend(leaf_values(v))
    elif obj is not None:
        out.append(_s(obj))
    return out


def payload_tokens(obj: Dict[str, Any], count) -> int:
    return sum(count(v) for v in leaf_values(obj) if v != "")
