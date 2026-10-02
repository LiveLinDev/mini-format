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
    mini build SAMPLE.json [MORE.json] --prefix NAME --out .mini
    mini bench FILE [-p PREFIX | --contract PATH] [--enc o200k_base] [--format table|json]
    mini from-schema SCHEMA.json -p PREFIX [--out contract.json]   JSON Schema -> contract
    mini from-schema --pydantic module:Model -p PREFIX              Pydantic model -> contract
    mini to-schema PREFIX|contract.json [--record] [--out FILE]     contract -> JSON Schema
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


def _escribir(ruta: Path, texto: str) -> None:
    """Escribe UTF-8 con LF en todos los sistemas (write_text usaria CRLF en Windows y la salida no seria reproducible)."""
    with ruta.open("w", encoding="utf-8", newline="\n") as fh:
        fh.write(texto)


def _reg(args) -> Registry:
    return Registry.load(getattr(args, "forks", None) or DEFAULT_FORKS_DIR)


def _contract_file(args) -> Contract | None:
    """Core contract passed with --contract; None if absent or if it belongs to the mini-domain/1 profile.

    `mini from-schema` writes base-profile contracts, so every command that accepts --contract must be able to
    read them back; domain-profile contracts keep going through the toolkit commands.
    """
    path = getattr(args, "contract", None)
    if not path:
        return None
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        sys.exit(f"cannot read contract {path}: {e}")
    if isinstance(data, dict) and str(data.get("profile", "")).startswith("mini-domain/"):
        return None
    return Contract.from_dict(data)


def _is_domain(args) -> bool:
    return bool(getattr(args, "contract", None)) and _contract_file(args) is None


def _contract(args, text: str | None = None) -> Contract:
    core = _contract_file(args)
    if core is not None:
        return core
    reg = _reg(args)
    prefix = getattr(args, "prefix", None) or (detect_prefix(text) if text else None)
    if not prefix:
        sys.exit("cannot detect prefix; pass -p PREFIX")
    return reg.get(prefix)


def cmd_forks(args) -> int:
    reg = _reg(args)
    if not reg.contracts:
        print("No contracts loaded. Build your own with 'mini build' or download the optional example families and pass --forks DIR.")
        return 0
    for c in reg:
        print(f"{c.prefix:6s} v{c.version}  parent={c.parent or '-':6s} arity={c.arity:2d}+{len(c.extensions)}  {c.name}")
    return 0


def cmd_validate(args) -> int:
    if _is_domain(args):
        return _domain_command(args, "validate")
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
    if _is_domain(args):
        return _domain_command(args, "diagnose")
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
    if _is_domain(args):
        if args.lenient:
            sys.exit("domain profiles require strict decoding; use diagnose or repair")
        return _domain_command(args, "decode")
    text = Path(args.file).read_text(encoding="utf-8")
    c = _contract(args, text)
    try:
        doc = parse(text, c, strict=not args.lenient)
    except MiniValidationError as e:
        for err in e.errors:
            print(err, file=sys.stderr)
        return 1
    output = json.dumps(doc.to_canonical(), ensure_ascii=False, indent=None if args.compact else 2)
    if args.out:
        _escribir(Path(args.out), output + "\n")
    else:
        print(output)
    if doc.errors:
        for err in doc.errors:
            print(err, file=sys.stderr)
    return 0


def cmd_from_json(args) -> int:
    if _is_domain(args):
        return _domain_command(args, "encode")
    if not args.prefix and not args.contract:
        sys.exit("Para convertir tus datos, ejecuta primero 'mini' (asistente) o 'mini build MUESTRA.json --prefix NOMBRE --out .mini'; después usa el parser.py generado. 'from-json' necesita un contrato existente.")
    obj = json.loads(Path(args.file).read_text(encoding="utf-8"))
    c = _contract(args)
    output = dumps(obj, c)
    if args.out:
        _escribir(Path(args.out), output + "\n")
    else:
        print(output)
    return 0


def cmd_prompt(args) -> int:
    if _is_domain(args):
        from .domain import load_contract, make_prompt
        print(make_prompt(load_contract(args.contract), args.lang))
        return 0
    core = _contract_file(args)
    if core is not None:
        print(spec_block(core, args.lang))
        return 0
    if not args.prefix:
        sys.exit("pass PREFIX or --contract PATH")
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
    try:
        tk = get_tokenizer(args.enc)
    except (FileNotFoundError, ImportError) as e:
        # una instalacion sin extras no trae benchmark/vocab ni tiktoken: el mensaje debe decir como arreglarlo
        sys.exit(f"mini tokens needs a tokenizer ({type(e).__name__}): install the extras with 'pip install mini-format[bench]'")
    text = Path(args.file).read_text(encoding="utf-8")
    print(f"{tk.count(text)} tokens ({args.enc}, backend={tk.backend}); {len(text.encode('utf-8'))} bytes")
    return 0


def cmd_check_forks(args) -> int:
    forks = Path(args.dir or args.forks) if (args.dir or args.forks) else DEFAULT_FORKS_DIR
    if forks is None:
        sys.exit("no sample families installed; download the optional families ZIP and pass its forks/ path to check-forks")
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
        sys.exit(f"unknown parent '{args.parent}'; pass --forks DIR if using the optional families")
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
    out = Path(args.forks or DEFAULT_FORKS_DIR or Path.cwd() / "forks") / args.prefix
    out.mkdir(parents=True, exist_ok=True)
    (out / "fixtures").mkdir(exist_ok=True)
    _escribir(out / "contract.json", json.dumps(d, ensure_ascii=False, indent=2) + "\n")
    print(f"created {out / 'contract.json'} — now add fixtures/valid.mini + fixtures/canonical.json and run 'mini check-forks'")
    return 0


def _domain_command(args, command):
    from .domain import main as domain_main
    argv = [command, args.file, "--contract", args.contract]
    if getattr(args, "out", None):
        argv += ["--out", args.out]
    if getattr(args, "fix_count", False):
        argv.append("--fix-count")
    if command == "decode" and getattr(args, "compact", False):
        argv.append("--compact")
    return domain_main(argv)


def cmd_build(args):
    from .domain import _strict_json, build_bundle
    samples = [_strict_json(Path(name).read_text(encoding="utf-8-sig")) for name in args.samples]
    path = None
    if args.records is not None:
        if args.records and not args.records.startswith("/"):
            sys.exit("--records must be a JSON Pointer, for example /products")
        path = [part.replace("~1", "/").replace("~0", "~") for part in args.records[1:].split("/")] if args.records else []
    contract = build_bundle(samples, args.prefix, args.out, source_names=[Path(name).name for name in args.samples], record_path=path)
    print(f"Built {args.out}: {contract['profile']}, {contract['sample_documents']} samples, {contract['sample_records']} records, schema={contract['schema_id']}")
    print(f"Start with {Path(args.out) / 'GUIA.md'}")
    print(f"Validate: python \"{Path(args.out) / 'validator.py'}\" response.mini")
    return 0


def cmd_repair(args):
    return _domain_command(args, "repair")


def cmd_bench(args) -> int:
    from .bench import BenchError, format_table, run_bench
    try:
        report = run_bench(args.file, prefix=args.prefix, contract_path=args.contract, enc=args.enc,
                           forks=getattr(args, "forks", None))
    except BenchError as e:
        print(f"mini bench: {e}", file=sys.stderr)
        return 2
    except MiniValidationError as e:
        for err in e.errors:
            print(err, file=sys.stderr)
        print(f"mini bench: the document is not valid for its contract ({len(e.errors)} error(s))", file=sys.stderr)
        return 1
    if args.format == "json":
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(format_table(report))
    return 0


def _write_or_print(data, out) -> None:
    text = json.dumps(data, ensure_ascii=False, indent=2)
    if out:
        _escribir(Path(out), text + "\n")
        print(f"wrote {out}", file=sys.stderr)
    else:
        print(text)


def cmd_from_schema(args) -> int:
    from .schema import from_json_schema, from_pydantic
    warnings: list = []
    opts = dict(name=args.name, records_key=args.records_key, strict=args.strict, warnings=warnings)
    if args.pydantic:
        import importlib
        mod, _, attr = args.pydantic.partition(":")
        if not attr:
            sys.exit("--pydantic expects module:Model")
        if str(Path.cwd()) not in sys.path:
            sys.path.insert(0, str(Path.cwd()))
        model = getattr(importlib.import_module(mod), attr)
        contract = from_pydantic(model, args.prefix, **opts)
    else:
        if not args.schema:
            sys.exit("pass SCHEMA.json or --pydantic module:Model")
        schema = json.loads(Path(args.schema).read_text(encoding="utf-8-sig"))
        contract = from_json_schema(schema, args.prefix, **opts)
    for w in warnings:
        print(f"warning: {w}", file=sys.stderr)
    _write_or_print(contract.to_dict(), args.out)
    return 0


def cmd_to_schema(args) -> int:
    from .schema import to_json_schema
    src = Path(args.source)
    contract = Contract.load(src) if src.suffix.lower() == ".json" and src.is_file() else _reg(args).get(args.source)
    _write_or_print(to_json_schema(contract, record_only=args.record), args.out)
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="mini", description="Crea tu propio formato .mini y úsalo con IA")
    ap.add_argument("--forks", help="directory of your contracts or the optional example families")
    sub = ap.add_subparsers(dest="cmd")
    sub.add_parser("setup", aliases=["init"], help="crea tu .mini paso a paso: datos, nombre y carpeta").set_defaults(fn=lambda args: _onboard())
    sub.add_parser("forks").set_defaults(fn=cmd_forks)
    p = sub.add_parser("validate"); p.add_argument("file"); p.add_argument("-p", "--prefix"); p.add_argument("--contract"); p.set_defaults(fn=cmd_validate)
    p = sub.add_parser("diagnose"); p.add_argument("file"); p.add_argument("-p", "--prefix"); p.add_argument("--contract"); p.set_defaults(fn=cmd_diagnose)
    p = sub.add_parser("to-json"); p.add_argument("file"); p.add_argument("-p", "--prefix"); p.add_argument("--contract"); p.add_argument("--lenient", action="store_true"); p.add_argument("--compact", action="store_true"); p.add_argument("--out"); p.set_defaults(fn=cmd_to_json)
    p = sub.add_parser("from-json"); p.add_argument("file"); p.add_argument("-p", "--prefix"); p.add_argument("--contract"); p.add_argument("--out"); p.set_defaults(fn=cmd_from_json)
    p = sub.add_parser("prompt"); p.add_argument("prefix", nargs="?"); p.add_argument("--contract"); p.add_argument("--lang", default="en", choices=["en", "es"]); p.add_argument("--no-example", action="store_true"); p.add_argument("--example-records", type=int, default=2); p.set_defaults(fn=cmd_prompt)
    p = sub.add_parser("tokens"); p.add_argument("file"); p.add_argument("--enc", default="o200k_base"); p.set_defaults(fn=cmd_tokens)
    p = sub.add_parser("check-forks"); p.add_argument("dir", nargs="?"); p.set_defaults(fn=cmd_check_forks)
    p = sub.add_parser("new-fork"); p.add_argument("prefix"); p.add_argument("--from", dest="parent"); p.add_argument("--name"); p.add_argument("--add", nargs="*"); p.set_defaults(fn=cmd_new_fork)
    p = sub.add_parser("build", help="create a standalone domain toolkit from JSON samples"); p.add_argument("samples", nargs="+"); p.add_argument("--prefix", required=True); p.add_argument("--out", default=".mini"); p.add_argument("--records", help="JSON Pointer selecting the record array (auto-detected by default)"); p.set_defaults(fn=cmd_build)
    p = sub.add_parser("repair", help="repair a generated-domain response without guessing data"); p.add_argument("file"); p.add_argument("--contract", required=True); p.add_argument("--out"); p.add_argument("--fix-count", action="store_true"); p.set_defaults(fn=cmd_repair)
    p = sub.add_parser("bench", help="compare tokens of a document across formats"); p.add_argument("file"); p.add_argument("-p", "--prefix"); p.add_argument("--contract", help="domain-profile contract (mini build)"); p.add_argument("--enc", default="o200k_base"); p.add_argument("--format", default="table", choices=["table", "json"]); p.set_defaults(fn=cmd_bench)
    p = sub.add_parser("from-schema", help="convert a JSON Schema or Pydantic model into a contract"); p.add_argument("schema", nargs="?"); p.add_argument("-p", "--prefix", required=True); p.add_argument("--pydantic", metavar="MODULE:MODEL"); p.add_argument("--name"); p.add_argument("--records-key"); p.add_argument("--strict", action="store_true", help="fail on keywords without contract equivalent"); p.add_argument("--out"); p.set_defaults(fn=cmd_from_schema)
    p = sub.add_parser("to-schema", help="describe a contract as JSON Schema"); p.add_argument("source", help="registered PREFIX or path to contract.json"); p.add_argument("--record", action="store_true", help="describe one record instead of the canonical document"); p.add_argument("--out"); p.set_defaults(fn=cmd_to_schema)
    if argv is None:
        argv = sys.argv[1:]
    if argv == ["help"]:
        ap.print_help()
        return 0
    if not argv:
        if sys.stdin.isatty():
            return _onboard()
        print("Bienvenido a .mini. Ejecuta 'mini setup' para crear tu formato paso a paso.")
        print("El asistente te pregunta por tus datos, su nombre y la carpeta de salida.")
        print("También puedes ejecutar 'mini init' o consultar 'mini --help'.")
        return 0
    args = ap.parse_args(argv)
    if args.cmd is None:
        ap.print_help()
        return 0
    try:
        return args.fn(args)
    except (MiniError, OSError, ValueError) as e:
        print(e, file=sys.stderr)
        return 2


def _onboard() -> int:
    from .onboarding import run
    return run()


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
