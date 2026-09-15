"""Command line interface.

    mini forks                         list registered forks
    mini validate FILE [-p PREFIX]     validate a .mini document (exit 1 on errors)
    mini diagnose FILE [-p PREFIX]     lenient parse: JSON report of lines to regenerate
    mini to-json FILE [-p PREFIX]      convert .mini -> canonical JSON
    mini from-json FILE -p PREFIX      convert canonical JSON -> .mini
    mini prompt PREFIX [--lang es]     print the transferable specification block
    mini tokens FILE [--enc o200k_base] count tokens of any text file
    mini check-forks [DIR]             verify fork invariants + fixtures (CI)
    mini new-fork PREFIX --from PARENT --add name:type ...   scaffold a fork
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import Registry, detect_prefix, dumps, parse, spec_block, canonical_equal
from .contract import Contract
from .errors import MiniError, MiniValidationError
from .registry import DEFAULT_FORKS_DIR


def _reg(args) -> Registry:
    return Registry.load(getattr(args, "forks", None) or DEFAULT_FORKS_DIR)


def _contract(args, text: str | None = None) -> Contract:
    reg = _reg(args)
    prefix = getattr(args, "prefix", None) or (detect_prefix(text) if text else None)
    if not prefix:
        sys.exit("cannot detect prefix; pass -p PREFIX")
    return reg.get(prefix)


def cmd_forks(args) -> int:
    reg = _reg(args)
    for c in reg:
        print(f"{c.prefix:6s} v{c.version}  parent={c.parent or '-':6s} arity={c.arity:2d}+{len(c.extensions)}  {c.name}")
    return 0


def cmd_validate(args) -> int:
    text = Path(args.file).read_text(encoding="utf-8")
    c = _contract(args, text)
    try:
        doc = parse(text, c, strict=True)
    except MiniValidationError as e:
        for err in e.errors:
            print(err)
        print(f"INVALID: {len(e.errors)} error(s)")
        return 1
    print(f"OK: prefix={doc.prefix} v{doc.version} records={len(doc.records)} n={doc.header.get('n')}")
    return 0


def cmd_diagnose(args) -> int:
    """Lenient parse; prints a JSON report with the lines to regenerate."""
    text = Path(args.file).read_text(encoding="utf-8")
    c = _contract(args, text)
    try:
        doc = parse(text, c, strict=False)
    except MiniValidationError as e:  # empty document
        print(json.dumps({"ok": False, "errors": [x.to_dict() for x in e.errors]}, ensure_ascii=False, indent=2))
        return 1
    print(json.dumps(doc.diagnostics(), ensure_ascii=False, indent=2))
    return 0 if doc.ok else 1


def cmd_to_json(args) -> int:
    text = Path(args.file).read_text(encoding="utf-8")
    c = _contract(args, text)
    try:
        doc = parse(text, c, strict=not args.lenient)
    except MiniValidationError as e:
        for err in e.errors:
            print(err, file=sys.stderr)
        return 1
    print(json.dumps(doc.to_canonical(), ensure_ascii=False, indent=None if args.compact else 2))
    if doc.errors:
        for err in doc.errors:
            print(err, file=sys.stderr)
    return 0


def cmd_from_json(args) -> int:
    obj = json.loads(Path(args.file).read_text(encoding="utf-8"))
    c = _contract(args)
    print(dumps(obj, c))
    return 0


def cmd_prompt(args) -> int:
    reg = _reg(args)
    c = reg.get(args.prefix)
    example = None
    fx = (reg.paths.get(args.prefix) or Path(".")) / "fixtures" / "valid.mini"
    if fx.exists() and not args.no_example:
        lines = fx.read_text(encoding="utf-8").strip().split("\n")
        example = "\n".join(lines[:1 + args.example_records])
        example = example.replace(f"n={len(lines)-1}", f"n={min(args.example_records, len(lines)-1)}")
    print(spec_block(c, args.lang, example))
    return 0


def cmd_tokens(args) -> int:
    from .tokens import get_tokenizer
    tk = get_tokenizer(args.enc)
    text = Path(args.file).read_text(encoding="utf-8")
    print(f"{tk.count(text)} tokens ({args.enc}, backend={tk.backend}); {len(text.encode('utf-8'))} bytes")
    return 0


def cmd_check_forks(args) -> int:
    forks = Path(args.dir) if args.dir else DEFAULT_FORKS_DIR
    reg = Registry.load(forks)
    errs = reg.check()
    failures = 0
    for e in errs:
        print(e)
        failures += 1
    for c in reg:
        p = reg.paths[c.prefix] / "fixtures"
        valid = p / "valid.mini"
        canon = p / "canonical.json"
        if not valid.exists() or not canon.exists():
            print(f"{c.prefix}: missing fixtures/valid.mini or fixtures/canonical.json")
            failures += 1
            continue
        try:
            doc = parse(valid.read_text(encoding="utf-8"), c)
        except MiniValidationError as e:
            print(f"{c.prefix}: valid.mini does not validate: {e}")
            failures += 1
            continue
        ref = json.loads(canon.read_text(encoding="utf-8"))
        if not canonical_equal(doc.to_canonical(), ref):
            print(f"{c.prefix}: round-trip mismatch between valid.mini and canonical.json")
            failures += 1
        if dumps(ref, c) != valid.read_text(encoding="utf-8").rstrip("\n"):
            print(f"{c.prefix}: canonical.json does not re-serialise to valid.mini byte for byte")
            failures += 1
        for bad in p.glob("bad_*.mini"):
            try:
                parse(bad.read_text(encoding="utf-8"), c)
                print(f"{c.prefix}: {bad.name} should be rejected")
                failures += 1
            except MiniValidationError:
                pass
        esc = p / "escaping.mini"
        if esc.exists():
            try:
                d2 = parse(esc.read_text(encoding="utf-8"), c)
                if (p / "escaping.json").exists() and not canonical_equal(d2.to_canonical(), json.loads((p / "escaping.json").read_text(encoding="utf-8"))):
                    print(f"{c.prefix}: escaping.mini round-trip mismatch")
                    failures += 1
            except MiniValidationError as e:
                print(f"{c.prefix}: escaping.mini invalid: {e}")
                failures += 1
        print(f"{c.prefix:6s} ok  ({len(doc.records)} records, lineage {' -> '.join(reg.lineage(c.prefix))})")
    print("FAILED" if failures else "ALL FORKS PASS", f"({len(reg.contracts)} forks)")
    return 1 if failures else 0


def cmd_new_fork(args) -> int:
    reg = _reg(args)
    if args.prefix in reg:
        sys.exit(f"prefix '{args.prefix}' already exists")
    if args.parent and args.parent not in reg:
        reg = Registry.load(DEFAULT_FORKS_DIR)
    base = reg.get(args.parent).to_dict() if args.parent else {"prefix": args.prefix, "header": {"required": ["n"], "keys": {}}, "core": [], "extensions": []}
    d = dict(base)
    d["prefix"] = args.prefix
    d["parent"] = args.parent
    d["version"] = 1
    d["name"] = args.name or f"{args.prefix} fork"
    if args.parent:
        # inherited fields (core + parent's extensions) become the child's core
        d["core"] = base["core"] + base["extensions"]
    d["extensions"] = []
    for spec in args.add or []:
        name, _, typ = spec.partition(":")
        fld = {"name": name, "type": typ or "str"}
        if typ.startswith("enum{"):
            fld = {"name": name, "type": "enum", "values": typ[5:-1].split("|")}
        if typ.startswith("list<"):
            fld = {"name": name, "type": "list", "item": typ[5:-1]}
        (d["extensions"] if args.parent else d["core"]).append(fld)
    Contract.from_dict(d)  # validate
    out = Path(args.forks or DEFAULT_FORKS_DIR) / args.prefix
    out.mkdir(parents=True, exist_ok=True)
    (out / "fixtures").mkdir(exist_ok=True)
    (out / "contract.json").write_text(json.dumps(d, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"created {out / 'contract.json'} — now add fixtures/valid.mini + fixtures/canonical.json and run 'mini check-forks'")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="mini", description=".mini reference tools")
    ap.add_argument("--forks", help="forks directory (default: bundled forks/)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("forks").set_defaults(fn=cmd_forks)
    p = sub.add_parser("validate"); p.add_argument("file"); p.add_argument("-p", "--prefix"); p.set_defaults(fn=cmd_validate)
    p = sub.add_parser("diagnose"); p.add_argument("file"); p.add_argument("-p", "--prefix"); p.set_defaults(fn=cmd_diagnose)
    p = sub.add_parser("to-json"); p.add_argument("file"); p.add_argument("-p", "--prefix"); p.add_argument("--lenient", action="store_true"); p.add_argument("--compact", action="store_true"); p.set_defaults(fn=cmd_to_json)
    p = sub.add_parser("from-json"); p.add_argument("file"); p.add_argument("-p", "--prefix", required=True); p.set_defaults(fn=cmd_from_json)
    p = sub.add_parser("prompt"); p.add_argument("prefix"); p.add_argument("--lang", default="en", choices=["en", "es"]); p.add_argument("--no-example", action="store_true"); p.add_argument("--example-records", type=int, default=2); p.set_defaults(fn=cmd_prompt)
    p = sub.add_parser("tokens"); p.add_argument("file"); p.add_argument("--enc", default="o200k_base"); p.set_defaults(fn=cmd_tokens)
    p = sub.add_parser("check-forks"); p.add_argument("dir", nargs="?"); p.set_defaults(fn=cmd_check_forks)
    p = sub.add_parser("new-fork"); p.add_argument("prefix"); p.add_argument("--from", dest="parent"); p.add_argument("--name"); p.add_argument("--add", nargs="*"); p.set_defaults(fn=cmd_new_fork)
    args = ap.parse_args(argv)
    try:
        return args.fn(args)
    except MiniError as e:
        print(e, file=sys.stderr)
        return 2


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
