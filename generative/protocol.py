"""Generative validation protocol (v1).

Measures how reliably a language model *produces* each format, with content
held constant so that every failure is a formatting failure:

  E1  serialization fidelity  — same 12 items, six target formats, k models
  E2  fork transfer           — three forks the model has never seen (tc, log, cls),
                                specification derived mechanically from the contract
  E3  parser synthesis        — the model writes a parser from the spec block alone;
                                the parser is executed against the fixtures

For every sample we record: parseable, round_trip (field-by-field equality
with the reference), field_accuracy, and an error class.  Raw model outputs
are kept under generative/raw/ so that every number can be traced.

Prompts are built here (`build_prompt`), model outputs are evaluated here
(`evaluate`), and `run_eval.py` aggregates raw/ into results/*.csv.
"""
from __future__ import annotations

import csv
import io
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Tuple

import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "benchmark"))

import domains  # noqa: E402
from minifmt import Registry, parse, spec_block, canonical_equal, MiniValidationError  # noqa: E402
from minifmt.values import format_number  # noqa: E402

REG = Registry.load(ROOT / "forks")
NODE_DECODE = ["node", "--experimental-strip-types", "--experimental-transform-types", str(ROOT / "benchmark" / "toon_ref" / "toon_decode.mjs")]

# --------------------------------------------------------------------------
# Neutral content (identical for every format; not equal to any target syntax)
# --------------------------------------------------------------------------
def _s(v: Any) -> str:
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, float):
        return format_number(v)
    return "" if v is None else str(v)


def neutral_a(items: List[Dict[str, Any]]) -> str:
    L = []
    for k, it in enumerate(items, 1):
        L.append(
            f"Item {k}: id={it['id']}; bloom={it['bloom']}; topic={it['topic']}; statement={it['statement']}; "
            f"options={' / '.join(it['options'])}; correct option={it['options'][it['correct']]}; "
            f"irt a={_s(it['irt']['a'])} b={_s(it['irt']['b'])} c={_s(it['irt']['c'])}; difficulty={it['difficulty']}; "
            f"cat area={it['cat']['area']} exposure_cap={_s(it['cat']['exposure_cap'])} demand={it['cat']['demand']}")
    return "\n".join(L)


def neutral_generic(prefix: str, records: List[Dict[str, Any]]) -> str:
    """Neutral rendering of any fork's records: 'field = value' pairs, lists with ' / '."""
    c = REG.get(prefix)
    L = []
    for k, r in enumerate(records, 1):
        parts = []
        for f in c.fields:
            if f.type == "mlist":
                items = r.get(f.json_items) or []
                sel = r.get(f.json_selected)
                sels = sel if isinstance(sel, list) else ([sel] if sel is not None else [])
                parts.append(f"{f.json_items}={' / '.join(items)}; selected={' / '.join(items[i] for i in sels)}")
            elif f.type == "list":
                vals = r.get(f.name) or []
                parts.append(f"{f.name}=({len(vals)} items) {' / '.join(_s(x) for x in vals)}" if vals else f"{f.name}=(none)")
            elif f.type == "tuple":
                t = r.get(f.name) or {}
                parts.append(f"{f.name}: " + " ".join(f"{cmp.name}={_s(t.get(cmp.name))}" for cmp in f.items))
            else:
                v = r.get(f.name)
                parts.append(f"{f.name}={_s(v) if v is not None else '(none)'}")
        L.append(f"Record {k}: " + "; ".join(parts))
    return "\n".join(L)


# --------------------------------------------------------------------------
# Target-format specifications for E1 (assessment items, full schema)
# --------------------------------------------------------------------------
A_ITEMS = domains.base("a")["items"]
A_HEADER = domains.base("a")["header"]
FLAT_FIELDS = ["id", "bloom", "topic", "statement", "o1", "o2", "o3", "o4", "correct", "a", "b", "c", "difficulty", "area", "exposure_cap", "demand"]

SPECS_E1 = {
    "json": (
        "Produce a compact JSON document with this exact shape: {\"items\": [ {\"id\": str, \"bloom\": str, \"topic\": str, "
        "\"statement\": str, \"options\": [str, str, str, str], \"correct\": int (0-based index of the correct option), "
        "\"irt\": {\"a\": number, \"b\": number, \"c\": number}, \"difficulty\": int, "
        "\"cat\": {\"area\": str, \"exposure_cap\": number, \"demand\": str} }, ... ] }. Standard JSON, no trailing commas."),
    "yaml": (
        "Produce a YAML document with a top-level key 'items' holding a list of mappings with keys id, bloom, topic, statement, "
        "options (a list of 4 strings), correct (0-based index of the correct option), irt (mapping with a, b, c numbers), "
        "difficulty (int), cat (mapping with area, exposure_cap, demand). Quote strings that contain ':' or start with special characters."),
    "xml": (
        "Produce an XML document <assessment> containing one <item id=\"..\" bloom=\"..\" difficulty=\"..\"> per item, with children "
        "<topic>, <statement>, <options> holding four <option correct=\"true|false\"> elements (exactly one true), "
        "<irt a=\"..\" b=\"..\" c=\"..\"/> and <cat area=\"..\" exposure_cap=\"..\" demand=\"..\"/>. Escape &, < and > in text."),
    "csv": (
        "Produce an RFC-4180 CSV document with a header row and one row per item, columns in this exact order: "
        + ",".join(FLAT_FIELDS) + ". 'correct' is the 1-based number of the correct option. Quote a field with double quotes only if it "
        "contains a comma, a double quote or a line break; double any inner double quote."),
    "toon": (
        "Produce a TOON (Token-Oriented Object Notation, spec 4.x) document. First an object 'header:' with indented 'key: value' lines "
        "(model: IRT3PL, date: \"20260603\", lang: es, topic: evaluación transversal, k: 4). Then a tabular array header "
        "'items[N]{" + ",".join(FLAT_FIELDS) + "}:' where N is the number of items, followed by N rows indented by two spaces with the "
        "16 comma-separated values in that order. 'correct' is the 1-based number of the correct option. Quote a value with double quotes "
        "if it contains a comma, a colon, a double quote, a bracket/brace, or leading/trailing spaces, or if a string looks numeric; "
        "escape inner double quotes as \\\"."),
    "mini": None,  # filled from the contract (transferable spec block)
}


def _flat_row(i: Dict[str, Any]) -> Dict[str, Any]:
    return dict(zip(FLAT_FIELDS, [i["id"], i["bloom"], i["topic"], i["statement"], *i["options"], i["correct"] + 1,
                                  i["irt"]["a"], i["irt"]["b"], i["irt"]["c"], i["difficulty"], i["cat"]["area"],
                                  i["cat"]["exposure_cap"], i["cat"]["demand"]]))


def example_e1(fmt: str) -> str:
    """One-record example (1-shot) for every format, built from item 1 by the reference serializers."""
    import formats
    it = A_ITEMS[0]
    rec = {k: it[k] for k in ("id", "bloom", "topic", "statement", "options", "correct", "irt", "difficulty", "cat")}
    if fmt == "json":
        return json.dumps({"items": [rec]}, ensure_ascii=False, separators=(",", ":"))
    if fmt == "yaml":
        return yaml.safe_dump({"items": [rec]}, allow_unicode=True, sort_keys=False, width=10**6).rstrip()
    if fmt == "xml":
        opts = "".join(f'<option correct="{str(j == it["correct"]).lower()}">{o}</option>' for j, o in enumerate(it["options"]))
        return (f'<assessment><item id="{it["id"]}" bloom="{it["bloom"]}" difficulty="{it["difficulty"]}"><topic>{it["topic"]}</topic>'
                f'<statement>{it["statement"]}</statement><options>{opts}</options><irt a="{_s(it["irt"]["a"])}" b="{_s(it["irt"]["b"])}" c="{_s(it["irt"]["c"])}"/>'
                f'<cat area="{it["cat"]["area"]}" exposure_cap="{_s(it["cat"]["exposure_cap"])}" demand="{it["cat"]["demand"]}"/></item></assessment>')
    if fmt == "csv":
        buf = io.StringIO(); w = csv.DictWriter(buf, fieldnames=FLAT_FIELDS, lineterminator="\n"); w.writeheader(); w.writerow(_flat_row(it))
        return buf.getvalue().rstrip()
    if fmt == "toon":
        return formats.toon_batch([{"header": {"model": "IRT3PL", "date": "20260603", "lang": "es", "topic": "evaluación transversal", "k": 4}, "items": [_flat_row(it)]}])[0][0]
    raise KeyError(fmt)


def spec_e1(fmt: str) -> str:
    if fmt != "mini":
        return SPECS_E1[fmt] + "\nExample with one item:\n" + example_e1(fmt)
    if fmt == "mini":
        c = REG.get("a")
        ex_lines = (ROOT / "forks/a/fixtures/valid.mini").read_text(encoding="utf-8").strip().split("\n")
        example = "\n".join([ex_lines[0].replace("n=12", "n=1")] + ex_lines[1:2])
        return spec_block(c, "en", example).replace("|k=4", "|k=4") + \
            "\nHeader values to use: m=IRT3PL, d=20260603, l=es, t=evaluación transversal, bd=1,1,1,1,1,1, cat=0,-3,3,0.3,12,SH, k=4."
    return SPECS_E1[fmt]


def build_prompt_e1(fmt: str, items: List[Dict[str, Any]] = None) -> str:
    items = items or A_ITEMS
    return (
        "You are a data serializer. Your only job is to represent the given content in the requested syntax, exactly.\n\n"
        f"TARGET FORMAT ({fmt}):\n{spec_e1(fmt)}\n\n"
        f"CONTENT TO REPRESENT ({len(items)} items; keep the order of items and of options; copy every text verbatim, do not translate, "
        f"summarize, correct or reorder anything):\n{neutral_a(items)}\n\n"
        f"OUTPUT: only the {fmt} document. No explanations, no markdown code fences, no comments."
    )


def build_prompt_e2(prefix: str, records: List[Dict[str, Any]] = None) -> str:
    c = REG.get(prefix)
    base = domains.base(prefix)
    records = records or base[c.records_key]
    ex_lines = (ROOT / "forks" / prefix / "fixtures/valid.mini").read_text(encoding="utf-8").strip().split("\n")
    # example: header + ONE record only (from a record not used in the task content? all 12 are used; we show record 1)
    example = "\n".join([ex_lines[0].replace(f"n={len(ex_lines)-1}", "n=1")] + ex_lines[1:2])
    hdr = ", ".join(f"{k}={_s(v)}" for k, v in base["header"].items() if not isinstance(v, (list, dict)))
    return (
        "You are a data serializer. Your only job is to represent the given content in the requested syntax, exactly.\n\n"
        f"TARGET FORMAT (.mini, family '{prefix}'):\n{spec_block(c, 'en', example)}\n"
        f"Header values to use: {hdr}.\n\n"
        f"CONTENT TO REPRESENT ({len(records)} records; keep the order; copy every text verbatim; '(none)' means the field is empty/null):\n"
        f"{neutral_generic(prefix, records)}\n\n"
        "OUTPUT: only the .mini document. No explanations, no markdown code fences, no comments."
    )


def build_prompt_e3(prefix: str) -> str:
    c = REG.get(prefix)
    p = ROOT / "forks" / prefix / "fixtures"
    fixtures = {"valid.mini": (p / "valid.mini").read_text(encoding="utf-8"),
                "escaping.mini": (p / "escaping.mini").read_text(encoding="utf-8")}
    from minifmt import parser_prompt
    return parser_prompt(c, fixtures, "en") + (
        "\n\nDeliver a single Python 3 file defining `def parse(text: str) -> dict` (raise ValueError on invalid input, "
        "mentioning the line number). No third-party imports. Do not include tests or a main block. "
        "OUTPUT: only the Python code, no markdown fences, no explanations."
    )


# --------------------------------------------------------------------------
# Parsers: model output -> canonical records (list of dicts in the 'a' shape)
# --------------------------------------------------------------------------
def strip_fences(text: str) -> str:
    text = text.strip()
    text = re.sub(r"^```[a-zA-Z.\-]*\n?", "", text)
    text = re.sub(r"\n?```$", "", text)
    return text.strip()


def _num(x: Any) -> float:
    return float(x)


def canon_from_generic(d: Dict[str, Any]) -> Dict[str, Any]:
    """Normalise a JSON/YAML-like item into the reference record shape."""
    return {
        "id": str(d["id"]), "bloom": str(d["bloom"]), "topic": str(d["topic"]), "statement": str(d["statement"]),
        "options": [str(o) for o in d["options"]], "correct": int(d["correct"]),
        "irt": {"a": _num(d["irt"]["a"]), "b": _num(d["irt"]["b"]), "c": _num(d["irt"]["c"])},
        "difficulty": int(d["difficulty"]),
        "cat": {"area": str(d["cat"]["area"]), "exposure_cap": _num(d["cat"]["exposure_cap"]), "demand": str(d["cat"]["demand"])},
    }


def canon_from_flat(row: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "id": str(row["id"]), "bloom": str(row["bloom"]), "topic": str(row["topic"]), "statement": str(row["statement"]),
        "options": [str(row["o1"]), str(row["o2"]), str(row["o3"]), str(row["o4"])], "correct": int(row["correct"]) - 1,
        "irt": {"a": _num(row["a"]), "b": _num(row["b"]), "c": _num(row["c"])},
        "difficulty": int(row["difficulty"]),
        "cat": {"area": str(row["area"]), "exposure_cap": _num(row["exposure_cap"]), "demand": str(row["demand"])},
    }


def parse_json(text: str) -> List[Dict[str, Any]]:
    obj = json.loads(strip_fences(text))
    items = obj["items"] if isinstance(obj, dict) else obj
    return [canon_from_generic(i) for i in items]


def parse_yaml(text: str) -> List[Dict[str, Any]]:
    obj = yaml.safe_load(strip_fences(text))
    items = obj["items"] if isinstance(obj, dict) else obj
    return [canon_from_generic(i) for i in items]


def parse_xml(text: str) -> List[Dict[str, Any]]:
    import xml.etree.ElementTree as ET
    root = ET.fromstring(strip_fences(text))
    out = []
    for it in root.iter("item"):
        opts, correct = [], None
        for j, op in enumerate(it.find("options").findall("option")):
            opts.append((op.text or "").strip())
            if (op.get("correct", "false").lower() == "true"):
                correct = j
        if correct is None:
            raise ValueError("no correct option")
        irt, cat = it.find("irt"), it.find("cat")
        out.append({
            "id": it.get("id"), "bloom": it.get("bloom"), "topic": (it.findtext("topic") or "").strip(),
            "statement": (it.findtext("statement") or "").strip(), "options": opts, "correct": correct,
            "irt": {"a": _num(irt.get("a")), "b": _num(irt.get("b")), "c": _num(irt.get("c"))},
            "difficulty": int(it.get("difficulty")),
            "cat": {"area": cat.get("area"), "exposure_cap": _num(cat.get("exposure_cap")), "demand": cat.get("demand")},
        })
    return out


def parse_csv(text: str) -> List[Dict[str, Any]]:
    rows = list(csv.DictReader(io.StringIO(strip_fences(text))))
    if not rows or list(rows[0].keys()) != FLAT_FIELDS:
        raise ValueError(f"bad CSV header: {list(rows[0].keys()) if rows else 'empty'}")
    return [canon_from_flat(r) for r in rows]


def toon_decode_batch(texts: List[str]) -> List[Tuple[bool, Any]]:
    proc = subprocess.run(NODE_DECODE, input=json.dumps(texts).encode("utf-8"), capture_output=True, check=True)
    res = json.loads(proc.stdout.decode("utf-8"))
    return [(r["ok"], r.get("value") if r["ok"] else r.get("error")) for r in res]


def parse_toon(text: str) -> List[Dict[str, Any]]:
    ok, val = toon_decode_batch([strip_fences(text)])[0]
    if not ok:
        raise ValueError(f"TOON decode: {val}")
    items = val["items"] if isinstance(val, dict) and "items" in val else val
    if not isinstance(items, list):
        raise ValueError("TOON: no items array")
    out = []
    for r in items:
        if not isinstance(r, dict) or any(k not in r for k in FLAT_FIELDS):
            raise ValueError("TOON: row lacks the 16 fields")
        out.append(canon_from_flat(r))
    return out


def parse_mini_a(text: str) -> List[Dict[str, Any]]:
    doc = parse(strip_fences(text), REG.get("a"), strict=True)
    return [canon_from_generic({**r, "irt": r["irt"], "cat": r["cat"]}) for r in doc.records]


PARSERS_E1 = {"json": parse_json, "yaml": parse_yaml, "xml": parse_xml, "csv": parse_csv, "toon": parse_toon, "mini": parse_mini_a}
REF_A = [canon_from_generic(i) for i in A_ITEMS]


# --------------------------------------------------------------------------
# Metrics
# --------------------------------------------------------------------------
def field_accuracy(parsed: List[Dict[str, Any]], ref: List[Dict[str, Any]]) -> float:
    if not parsed:
        return 0.0
    total, ok = 0, 0
    for p, r in zip(parsed, ref):
        for k in r:
            total += 1
            if canonical_equal(p.get(k), r[k]):
                ok += 1
    total += abs(len(parsed) - len(ref)) * len(ref[0])
    return ok / total if total else 0.0


ERROR_CLASSES = [
    ("count", r"n=|count|declares n|rows|length|expected \d+ (items|rows|records)|E04"),
    ("arity", r"arity|E05|fields, core|lacks the 16|bad CSV header|row has"),
    ("marker", r"marker|E08|no correct option"),
    ("delimiter", r"E07|elements but header|unterminated|quote|delimiter|Expecting , delimiter|expected string or|Unexpected character"),
    ("escape", r"E09|backslash|escape"),
    ("type", r"E06|E10|E13|invalid literal|could not convert|ValueError: could not"),
    ("structure", r"json|yaml|xml|toon|mapping|syntax|Expecting|not well-formed|mismatched tag|no items|KeyError|TypeError|AttributeError|IndexError"),
]


def classify(error: str) -> str:
    for name, pat in ERROR_CLASSES:
        if re.search(pat, error, flags=re.I):
            return name
    return "other" if error else ""


def evaluate_e1(fmt: str, text: str) -> Dict[str, Any]:
    return _evaluate(PARSERS_E1[fmt], text, REF_A)


def _evaluate(parser, text: str, ref: List[Dict[str, Any]]) -> Dict[str, Any]:
    res = {"parseable": False, "round_trip": False, "field_accuracy": 0.0, "n_records": 0, "error": "", "error_class": ""}
    try:
        parsed = parser(text)
        res["parseable"] = True
        res["n_records"] = len(parsed)
    except MiniValidationError as e:
        res["error"] = "; ".join(str(x) for x in e.errors)[:300]
        res["error_class"] = classify(res["error"])
        # lenient recovery for .mini: how many records survive?
        return res
    except Exception as e:  # noqa: BLE001
        res["error"] = f"{type(e).__name__}: {e}"[:300]
        res["error_class"] = classify(res["error"])
        return res
    acc = field_accuracy(parsed, ref)
    res["field_accuracy"] = round(acc, 4)
    res["round_trip"] = len(parsed) == len(ref) and acc == 1.0
    if not res["round_trip"]:
        res["error"] = "content mismatch"
        res["error_class"] = "content"
    return res


def evaluate_e2(prefix: str, text: str) -> Dict[str, Any]:
    c = REG.get(prefix)
    ref = domains.base(prefix)[c.records_key]
    ref = [{k: v for k, v in r.items()} for r in ref]

    def p(t: str):
        doc = parse(strip_fences(t), c, strict=True)
        return doc.records

    res = _evaluate(p, text, ref)
    # lenient recovery rate (records salvaged without the strict count check)
    try:
        doc = parse(strip_fences(text), c, strict=False)
        good = sum(1 for r, x in zip(doc.records, ref) if canonical_equal(r, x))
        res["recovered_pct"] = round(100 * good / len(ref), 1)
    except Exception:  # noqa: BLE001
        res["recovered_pct"] = 0.0
    return res


def evaluate_e3(prefix: str, code: str) -> Dict[str, Any]:
    """Run a model-written parser against the fork's fixtures in a subprocess."""
    import tempfile
    c = REG.get(prefix)
    p = ROOT / "forks" / prefix / "fixtures"
    harness = f'''
import json, sys, traceback
sys.path.insert(0, {str(ROOT / "src")!r})
from minifmt import canonical_equal
code = open(sys.argv[1], encoding="utf-8").read()
ns = {{}}
exec(compile(code, "model_parser.py", "exec"), ns)
parse = ns["parse"]
out = {{}}
fx = {str(p)!r}
MLISTS = {json.dumps([(f.name, f.json_items, f.json_selected) for f in c.fields if f.type == "mlist"])}
def norm(o):
    # accept either canonical shape or bare list of records
    if isinstance(o, dict) and {c.records_key!r} in o: o = o[{c.records_key!r}]
    elif isinstance(o, dict) and "records" in o: o = o["records"]
    # accept the nested marked-list shape {{items, correct}} under the field name (spec §7 uses sibling keys)
    for r in o if isinstance(o, list) else []:
        for name, jitems, jsel in MLISTS:
            v = r.get(name)
            if isinstance(v, dict) and ("items" in v or jitems in v):
                r[jitems] = v.get(jitems, v.get("items"))
                r[jsel] = v.get(jsel, v.get("correct", v.get("selected")))
                if name not in (jitems, jsel): r.pop(name, None)
    return o
try:
    ref = json.load(open(fx + "/canonical.json", encoding="utf-8"))[{c.records_key!r}]
    got = norm(parse(open(fx + "/valid.mini", encoding="utf-8").read()))
    out["valid_ok"] = canonical_equal(got, ref)
except Exception as e:
    out["valid_ok"] = False; out["valid_err"] = f"{{type(e).__name__}}: {{e}}"[:200]
try:
    ref = json.load(open(fx + "/escaping.json", encoding="utf-8"))[{c.records_key!r}]
    got = norm(parse(open(fx + "/escaping.mini", encoding="utf-8").read()))
    out["escaping_ok"] = canonical_equal(got, ref)
except Exception as e:
    out["escaping_ok"] = False; out["escaping_err"] = f"{{type(e).__name__}}: {{e}}"[:200]
import glob, os
rej = 0; tot = 0
for bad in sorted(glob.glob(fx + "/bad_*.mini")):
    tot += 1
    try:
        parse(open(bad, encoding="utf-8").read()); out[os.path.basename(bad)] = "ACCEPTED (should reject)"
    except Exception:
        rej += 1; out[os.path.basename(bad)] = "rejected"
out["negatives_rejected"] = f"{{rej}}/{{tot}}"
out["all_ok"] = out["valid_ok"] and out["escaping_ok"] and rej == tot
print(json.dumps(out))
'''
    with tempfile.TemporaryDirectory() as td:
        code_path = Path(td) / "model_parser.py"
        code_path.write_text(strip_fences(code), encoding="utf-8")
        h = Path(td) / "harness.py"
        h.write_text(harness, encoding="utf-8")
        try:
            proc = subprocess.run([sys.executable, str(h), str(code_path)], capture_output=True, text=True, timeout=60)
            if proc.returncode != 0:
                return {"all_ok": False, "error": (proc.stderr or proc.stdout)[-300:]}
            return json.loads(proc.stdout.strip().split("\n")[-1])
        except subprocess.TimeoutExpired:
            return {"all_ok": False, "error": "timeout"}


if __name__ == "__main__":
    # print the prompts so they can be inspected / archived
    out = ROOT / "generative" / "prompts"
    out.mkdir(parents=True, exist_ok=True)
    for fmt in PARSERS_E1:
        (out / f"e1_{fmt}.txt").write_text(build_prompt_e1(fmt), encoding="utf-8")
    for pf in ("tc", "log", "cls"):
        (out / f"e2_{pf}.txt").write_text(build_prompt_e2(pf), encoding="utf-8")
    for pf in ("a", "tc", "log", "cls"):
        (out / f"e3_{pf}.txt").write_text(build_prompt_e3(pf), encoding="utf-8")
    # self-check: the reference serializations must evaluate as perfect
    import formats
    c = REG.get("a")
    obj = domains.base("a")
    flat_rows = [dict(zip(FLAT_FIELDS, [i["id"], i["bloom"], i["topic"], i["statement"], *i["options"], i["correct"] + 1,
                                        i["irt"]["a"], i["irt"]["b"], i["irt"]["c"], i["difficulty"], i["cat"]["area"],
                                        i["cat"]["exposure_cap"], i["cat"]["demand"]])) for i in A_ITEMS]
    buf = io.StringIO(); w = csv.DictWriter(buf, fieldnames=FLAT_FIELDS, lineterminator="\n"); w.writeheader(); w.writerows(flat_rows)
    toon_doc = formats.toon_batch([{"header": {"model": "IRT3PL", "date": "20260603", "lang": "es", "topic": "evaluación transversal", "k": 4}, "items": flat_rows}])[0][0]
    checks = {"json": formats.json_compact(obj, c), "yaml": formats.yaml_ser(obj, c), "csv": buf.getvalue(),
              "toon": toon_doc, "mini": formats.mini_ser(obj, c), "xml": None}
    checks.pop("xml")
    for k, t in checks.items():
        r = evaluate_e1(k, t)
        print(k, r["parseable"], r["round_trip"], r["field_accuracy"], r["error"])
    from minifmt.tokens import get_tokenizer
    tk = get_tokenizer("o200k_base")
    for fmt in PARSERS_E1:
        print("prompt tokens", fmt, tk.count(spec_e1(fmt)))
