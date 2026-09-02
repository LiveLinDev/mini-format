"""(Re)generate contract.json + fixtures for every shipped fork.

Run:  python benchmark/make_forks.py
The script is idempotent; it is the single source of truth for the shipped
fork contracts, and it verifies the round-trip property for every fixture.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "benchmark"))

from minifmt import Contract, Registry, dumps, parse, roundtrip_ok, MiniValidationError  # noqa: E402
import domains  # noqa: E402

AUTHOR = "A. E. J. Palma Obispo, E. J. Palomino Santa Cruz (UPC)"
BLOOM = ["L1", "L2", "L3", "L4", "L5", "L6"]
DATE = {"type": "str", "desc": "generation date YYYYMMDD"}
LANG = {"type": "str", "desc": "language code"}


def F(name, type, **kw):
    d = {"name": name, "type": type}
    d.update(kw)
    return d


CONTRACTS = {
    "q": dict(
        prefix="q", version=1, parent="a", name="Formative quiz items (assessment + feedback)",
        domain="education / formative assessment", records_key="items",
        description="Fork of 'a': the same core, plus trailing feedback, hint and learning objective so that a quiz can explain each answer.",
        header={"required": ["n"], "keys": json.load(open(ROOT / "forks/a/contract.json"))["header"]["keys"]},
        core=json.load(open(ROOT / "forks/a/contract.json"))["core"],
        extensions=[F("feedback", "str", desc="explanation shown after answering"),
                    F("hint", "str", optional=True),
                    F("objective", "str", optional=True, desc="learning objective")],
    ),
    "card": dict(
        prefix="card", version=1, parent=None, name="Flashcards (spaced repetition)",
        domain="education / microlearning", records_key="cards",
        description="One flashcard per line: front, back, optional hint, tags, Bloom level and an initial ease factor for spaced repetition.",
        header={"required": ["n"], "keys": {"d": DATE, "l": LANG, "t": {"type": "str"}, "src": {"type": "str", "desc": "source lesson id"}}},
        core=[F("id", "str", unique=True), F("topic", "str"), F("front", "str"), F("back", "str"),
              F("hint", "str", optional=True), F("tags", "list", item="str", min=0, max=8),
              F("bloom", "enum", values=BLOOM), F("ease", "float", min=1.3, max=3.0)],
        extensions=[],
    ),
    "sum": dict(
        prefix="sum", version=1, parent=None, name="Micro-lesson summary segments",
        domain="education / microlearning", records_key="segments",
        description="Time-aligned summary segments of a recorded lecture (SIMA microcontent).",
        header={"required": ["n"], "keys": {"d": DATE, "l": LANG, "t": {"type": "str"}, "src": {"type": "str"}, "dur": {"type": "int", "desc": "lecture duration in seconds"}}},
        core=[F("id", "str", unique=True), F("t_start", "int", min=0), F("t_end", "int", min=0), F("title", "str"),
              F("summary", "str"), F("keywords", "list", item="str", min=1, max=10), F("bloom", "enum", values=BLOOM)],
        extensions=[],
    ),
    "map": dict(
        prefix="map", version=1, parent=None, name="Concept map edges",
        domain="education / knowledge graphs", records_key="edges",
        description="One directed relation per line (source, relation, target, weight, evidence segment).",
        header={"required": ["n"], "keys": {"d": DATE, "l": LANG, "t": {"type": "str"}, "src": {"type": "str"}}},
        core=[F("src", "str"), F("rel", "enum", values=["is_a", "has_part", "performs", "produces", "causes", "requires", "contrasts", "example_of"]),
              F("dst", "str"), F("weight", "float", min=0, max=1), F("evidence", "str", optional=True, desc="segment id supporting the edge")],
        extensions=[],
    ),
    "r": dict(
        prefix="r", version=1, parent=None, name="Analytic rubric criteria",
        domain="education / assessment", records_key="criteria",
        description="One rubric criterion per line with k ordered performance levels (k declared in the header), a weight and the evidence to inspect.",
        header={"required": ["n", "k"], "keys": {"d": DATE, "l": LANG, "t": {"type": "str"}, "k": {"type": "int", "desc": "number of performance levels"}, "scale": {"type": "str"}}},
        core=[F("id", "str", unique=True), F("dimension", "str"), F("criterion", "str"),
              F("levels", "list", item="str", count_key="k", desc="ordered level descriptors"),
              F("weight", "float", min=0, max=1), F("evidence", "str")],
        extensions=[],
    ),
    "s": dict(
        prefix="s", version=1, parent=None, name="Survey items (Likert)",
        domain="research instruments", records_key="items",
        description="Likert-type survey items grouped by construct, with scale size, anchor labels and reverse-scoring flag.",
        header={"required": ["n"], "keys": {"d": DATE, "l": LANG, "t": {"type": "str"}, "k": {"type": "int", "desc": "anchors per item"}}},
        core=[F("id", "str", unique=True), F("construct", "str"), F("statement", "str"), F("scale", "int", min=2, max=11),
              F("anchors", "list", item="str", count_key="k"), F("reverse", "bool")],
        extensions=[],
    ),
    "code": dict(
        prefix="code", version=1, parent=None, name="Programming exercises with tests",
        domain="education / programming", records_key="exercises",
        description="Auto-gradable programming exercises: statement, language, test expressions, expected type and hints.",
        header={"required": ["n"], "keys": {"d": DATE, "l": LANG, "t": {"type": "str"}}},
        core=[F("id", "str", unique=True), F("bloom", "enum", values=BLOOM), F("topic", "str"), F("statement", "str"),
              F("lang", "enum", values=["python", "javascript", "java", "sql", "c", "cpp", "go"]),
              F("tests", "list", item="str", min=1, max=10, desc="boolean test expressions"),
              F("expected", "str"), F("hints", "list", item="str", min=0, max=5)],
        extensions=[],
    ),
    "tc": dict(
        prefix="tc", version=1, parent=None, name="Software test cases",
        domain="software engineering / QA", records_key="cases",
        description="Manual or automated test cases: module, title, precondition, ordered steps, expected result, priority, type and automation flag.",
        header={"required": ["n"], "keys": {"d": DATE, "l": LANG, "t": {"type": "str"}, "proj": {"type": "str"}}},
        core=[F("id", "str", unique=True), F("module", "str"), F("title", "str"), F("precondition", "str"),
              F("steps", "list", item="str", min=1, max=20), F("expected", "str"),
              F("priority", "enum", values=["low", "medium", "high", "critical"]),
              F("type", "enum", values=["functional", "integration", "performance", "security", "usability", "regression"]),
              F("automated", "bool")],
        extensions=[],
    ),
    "log": dict(
        prefix="log", version=1, parent=None, name="Service events / incident records",
        domain="operations / observability", records_key="events",
        description="Structured events emitted by services: timestamp, level, service, code, message, tags, trace id and optional duration.",
        header={"required": ["n"], "keys": {"d": DATE, "env": {"type": "str"}, "host": {"type": "str"}}},
        core=[F("ts", "str", desc="ISO-8601 UTC timestamp"), F("level", "enum", values=["DEBUG", "INFO", "WARN", "ERROR", "CRITICAL"]),
              F("service", "str"), F("code", "str"), F("message", "str"), F("tags", "list", item="str", min=0, max=10),
              F("trace", "str", optional=True), F("duration_ms", "int", optional=True, min=0)],
        extensions=[],
    ),
    "ner": dict(
        prefix="ner", version=1, parent=None, name="Named-entity annotations",
        domain="NLP / data labelling", records_key="entities",
        description="One entity mention per line (relational pattern: several lines share a document id).",
        header={"required": ["n"], "keys": {"d": DATE, "l": LANG, "model": {"type": "str"}, "schema": {"type": "str"}}},
        core=[F("doc", "str"), F("start", "int", min=0), F("end", "int", min=0), F("text", "str"),
              F("type", "enum", values=["PERSON", "ORG", "LOC", "DATE", "PRODUCT", "CONCEPT", "MISC"]), F("conf", "float", min=0, max=1)],
        extensions=[],
    ),
    "cat": dict(
        prefix="cat", version=1, parent=None, name="Product catalogue entries",
        domain="e-commerce", records_key="products",
        description="Catalogue rows with price, currency, stock, tags and optional rating.",
        header={"required": ["n"], "keys": {"d": DATE, "store": {"type": "str"}, "cur": {"type": "str", "desc": "default currency"}}},
        core=[F("sku", "str", unique=True), F("name", "str"), F("category", "str"), F("price", "float", min=0),
              F("currency", "enum", values=["USD", "PEN", "EUR"]), F("stock", "int", min=0), F("tags", "list", item="str", min=0, max=10),
              F("rating", "float", optional=True, min=0, max=5)],
        extensions=[],
    ),
    "cls": dict(
        prefix="cls", version=1, parent=None, name="Multi-label text classification outputs",
        domain="NLP / support triage", records_key="messages",
        description="Classifier outputs: the label set is written in full and the predicted labels carry *, so both the label space and the prediction are self-describing.",
        header={"required": ["n"], "keys": {"d": DATE, "l": LANG, "model": {"type": "str"}, "k": {"type": "int", "desc": "labels in the label set"}}},
        core=[F("id", "str", unique=True), F("text", "str"),
              F("labels", "mlist", item="str", marker="at_least_one", count_key="k", json={"items": "labels", "selected": "selected"}),
              F("conf", "float", min=0, max=1), F("rationale", "str", optional=True)],
        extensions=[],
    ),
    "us": dict(
        prefix="us", version=1, parent=None, name="User stories with acceptance criteria",
        domain="software engineering / agile", records_key="stories",
        description="Product-backlog stories: epic, role, goal, benefit, acceptance criteria, story points and MoSCoW priority.",
        header={"required": ["n"], "keys": {"d": DATE, "l": LANG, "t": {"type": "str"}, "sprint": {"type": "str"}}},
        core=[F("id", "str", unique=True), F("epic", "str"), F("role", "str"), F("goal", "str"), F("benefit", "str"),
              F("acceptance", "list", item="str", min=1, max=10), F("sp", "int", min=1, max=100),
              F("priority", "enum", values=["must", "should", "could", "wont"])],
        extensions=[],
    ),
}


def write_contract(d: dict) -> None:
    d = dict(d)
    d.setdefault("author", AUTHOR)
    d.setdefault("license", "MIT")
    d.setdefault("source", "mini-format reference forks")
    p = ROOT / "forks" / d["prefix"]
    p.mkdir(parents=True, exist_ok=True)
    (p / "fixtures").mkdir(exist_ok=True)
    with open(p / "contract.json", "w", encoding="utf-8") as fh:
        json.dump(d, fh, ensure_ascii=False, indent=2)


def write_fixtures(prefix: str) -> None:
    reg = Registry.load(ROOT / "forks")
    c = reg.get(prefix)
    canon = domains.base(prefix)
    assert roundtrip_ok(canon, c), f"round-trip failed for {prefix}"
    text = dumps(canon, c)
    p = ROOT / "forks" / prefix / "fixtures"
    with open(p / "canonical.json", "w", encoding="utf-8") as fh:
        json.dump(parse(text, c).to_canonical(), fh, ensure_ascii=False, indent=1)
    (p / "valid.mini").write_text(text + "\n", encoding="utf-8")
    lines = text.split("\n")
    # bad_count: declare n+1
    hdr = lines[0].replace(f"n={len(lines)-1}", f"n={len(lines)}")
    (p / "bad_count.mini").write_text("\n".join([hdr] + lines[1:]) + "\n", encoding="utf-8")
    # bad_arity: drop the last core field of record 2
    rec = lines[2].split("|")
    (p / "bad_arity.mini").write_text("\n".join(lines[:2] + ["|".join(rec[: c.arity - 1])] + lines[3:]) + "\n", encoding="utf-8")
    # bad_type: put text in the first numeric field of record 1 if any
    numf = next((i for i, f in enumerate(c.core) if f.type in ("int", "float")), None)
    if numf is not None:
        rec = lines[1].split("|")
        rec[numf] = "many"
        (p / "bad_type.mini").write_text("\n".join([lines[0], "|".join(rec)] + lines[2:]) + "\n", encoding="utf-8")
    # bad_marker for mlist contracts: remove every * in record 1
    if any(f.type == "mlist" for f in c.core):
        (p / "bad_marker.mini").write_text("\n".join([lines[0], lines[1].replace("*", "")] + lines[2:]) + "\n", encoding="utf-8")
    # escaping: a record with every reserved character
    esc_rec = dict(canon[c.records_key][0])
    for f in c.core:
        if f.type == "str" and f.name not in ("id", "sku", "ts"):
            esc_rec[f.name] = 'pipe | and back\\slash, comma, "quotes", star* and newline\nend'
            break
    for f in c.core:
        if f.type in ("list", "mlist") and f.item == "str":
            key = f.json_items if f.type == "mlist" else f.name
            vals = list(esc_rec[key])
            vals[0] = "a, b | c \\ d*"
            esc_rec[key] = vals
            break
    esc_obj = {"header": canon["header"], c.records_key: [esc_rec]}
    assert roundtrip_ok(esc_obj, c), f"escaping round-trip failed for {prefix}"
    (p / "escaping.mini").write_text(dumps(esc_obj, c) + "\n", encoding="utf-8")
    with open(p / "escaping.json", "w", encoding="utf-8") as fh:
        json.dump(parse(dumps(esc_obj, c), c).to_canonical(), fh, ensure_ascii=False, indent=1)


def write_readme(prefix: str) -> None:
    reg = Registry.load(ROOT / "forks")
    c = reg.get(prefix)
    example = (ROOT / "forks" / prefix / "fixtures" / "valid.mini").read_text(encoding="utf-8").split("\n")[:3]
    md = [f"# `.mini-{prefix}` — {c.name}", "",
          f"**Prefix:** `{prefix}`  **Version:** {c.version}  **Parent:** {c.parent or '—'}  **Domain:** {c.domain}", "",
          c.description, "",
          "## Record layout", "", "```", c.signature(), "```", "",
          "| # | field | type | notes |", "|---|---|---|---|"]
    for i, f in enumerate(c.fields, 1):
        note = ("extension" if f in c.extensions else "core") + ("; optional" if f.optional else "") + (f"; {f.desc}" if f.desc else "")
        md.append(f"| {i} | `{f.name}` | `{f.signature().split(':',1)[1]}` | {note} |")
    md += ["", "## Header keys", "",
           "| key | type | required | description |", "|---|---|---|---|"]
    for k, hk in c.header_keys.items():
        md.append(f"| `{k}` | `{hk.type}` | {'yes' if hk.required else 'no'} | {hk.desc} |")
    md += ["", "## Example", "", "```", *example, "…", "```", "",
           "## Fixtures", "",
           "`fixtures/valid.mini` ↔ `fixtures/canonical.json` (round-trip), `fixtures/escaping.mini` ↔ `fixtures/escaping.json`, "
           "and the negative cases `bad_count.mini`, `bad_arity.mini`" + (", `bad_marker.mini`" if any(f.type == 'mlist' for f in c.core) else "") + ", `bad_type.mini`.", "",
           "## Prompt block", "", "Generate the transferable specification with `mini prompt " + prefix + "`."]
    (ROOT / "forks" / prefix / "README.md").write_text("\n".join(md) + "\n", encoding="utf-8")


if __name__ == "__main__":
    for d in CONTRACTS.values():
        write_contract(d)
    reg = Registry.load(ROOT / "forks")
    errs = reg.check()
    assert not errs, errs
    for prefix in reg.contracts:
        write_fixtures(prefix)
        write_readme(prefix)
    reg.write_index(ROOT / "forks" / "registry.json")
    print("forks:", ", ".join(reg.contracts))
    for prefix in reg.contracts:
        p = ROOT / "forks" / prefix / "fixtures"
        for bad in ("bad_count", "bad_arity", "bad_type", "bad_marker"):
            fp = p / f"{bad}.mini"
            if fp.exists():
                try:
                    parse(fp.read_text(encoding="utf-8"), reg.get(prefix))
                    raise SystemExit(f"{prefix}/{bad} should have failed")
                except MiniValidationError as e:
                    print(f"  {prefix:5s} {bad:11s} -> {sorted(set(e.codes))}")
