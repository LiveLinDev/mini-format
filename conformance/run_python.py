"""Runner de la suite de conformidad para la implementación Python (``minifmt``).

    python conformance/run_python.py              # resumen por categoría
    python conformance/run_python.py -v           # detalle de cada fallo
    python conformance/run_python.py -k escapes   # filtra por id o categoría

La semántica de cada modo está descrita en ``conformance/README.md``; un
runner de otra implementación debe reproducir exactamente la misma lógica.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
CASES_DIR = HERE / "cases"
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from minifmt import Contract, MiniError, MiniValidationError, canonical_equal, dumps, parse  # noqa: E402

_CONTRACTS: Dict[str, Contract] = {}


def load_cases(cases_dir: Path = CASES_DIR) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for f in sorted(cases_dir.glob("*.json")):
        doc = json.loads(f.read_text(encoding="utf-8"))
        out.extend(doc["cases"])
    return out


def family_contract(prefix: str, forks_dir: Path = ROOT / "forks") -> Contract:
    if prefix not in _CONTRACTS:
        _CONTRACTS[prefix] = Contract.load(forks_dir / prefix / "contract.json")
    return _CONTRACTS[prefix]


def case_contract(case: Dict[str, Any]) -> Contract:
    if "contract" in case:
        return Contract.from_dict(case["contract"])
    return family_contract(case["family"])


def _pairs(errors: Iterable[Any]) -> set:
    out = set()
    for e in errors:
        if isinstance(e, dict):
            out.add((e["code"], int(e["line"])))
        else:
            out.add((e.code, int(e.line)))
    return out


def _fmt(pairs: set) -> str:
    return ", ".join(f"{c}@{l}" for c, l in sorted(pairs, key=lambda p: (p[1], p[0]))) or "(none)"


def _check_errors(expected: List[dict], got: Iterable[Any]) -> Optional[str]:
    exp, act = _pairs(expected), _pairs(got)
    if exp != act:
        return f"errors: expected {_fmt(exp)}, got {_fmt(act)}"
    return None


def run_case(case: Dict[str, Any]) -> Tuple[bool, str]:
    """Run one case; returns (passed, message)."""
    mode, exp = case["mode"], case["expected"]
    try:
        if mode == "contract":
            try:
                Contract.from_dict(case["input"])
                got: List[Any] = []
            except MiniError as e:
                got = [e]
            msg = _check_errors(exp.get("errors", []), got)
            return (msg is None, msg or "ok")

        if mode == "fork":
            child = case_contract(case)
            parent = case["parent"]
            parent_c = family_contract(parent) if isinstance(parent, str) else Contract.from_dict(parent)
            msg = _check_errors(exp.get("errors", []), child.check_fork_of(parent_c))
            return (msg is None, msg or "ok")

        contract = case_contract(case)

        if mode == "dumps":
            try:
                text = dumps(case["input"], contract)
            except MiniError as e:
                if exp.get("rejected"):
                    return True, "ok"
                return False, f"serializer rejected the object: {e}"
            if exp.get("rejected"):
                return False, f"serializer should reject, produced {text!r}"
            if text != exp["mini"]:
                return False, f"dumps: expected {exp['mini']!r}, got {text!r}"
            try:
                parse(text, contract)
            except MiniValidationError as e:
                return False, f"serialized text does not parse: {e}"
            return True, "ok"

        if mode == "strict":
            try:
                doc = parse(case["input"], contract, strict=True)
            except MiniValidationError as e:
                if "errors" not in exp:
                    return False, f"unexpected rejection: {_fmt(_pairs(e.errors))}"
                msg = _check_errors(exp["errors"], e.errors)
                return (msg is None, msg or "ok")
            if exp.get("errors"):
                return False, f"should be rejected with {_fmt(_pairs(exp['errors']))}"
            canon = doc.to_canonical()
            if not canonical_equal(canon, exp["canonical"]):
                return False, "canonical mismatch: got " + json.dumps(canon, ensure_ascii=False)[:400]
            if "mini" in exp:
                text = dumps(canon, contract)
                if text != exp["mini"]:
                    return False, f"re-serialization: expected {exp['mini']!r}, got {text!r}"
                back = parse(text, contract).to_canonical()
                if not canonical_equal(back, exp["canonical"]):
                    return False, "round-trip mismatch after re-serialization"
            return True, "ok"

        if mode == "lenient":
            try:
                doc = parse(case["input"], contract, strict=False)
            except MiniValidationError as e:  # document-level failure: no records at all
                if "canonical" in exp:
                    return False, f"lenient parse produced no document: {_fmt(_pairs(e.errors))}"
                msg = _check_errors(exp.get("errors", []), e.errors)
                return (msg is None, msg or "ok")
            if "canonical" not in exp:
                return False, "lenient parse should fail at document level"
            msg = _check_errors(exp.get("errors", []), doc.errors)
            if msg:
                return False, msg
            canon = doc.to_canonical()
            if not canonical_equal(canon, exp["canonical"]):
                return False, "canonical mismatch: got " + json.dumps(canon, ensure_ascii=False)[:400]
            diag = exp.get("diagnostics")
            if diag:
                got_diag = {"invalid_lines": doc.invalid_lines(), "missing_records": doc.missing_records}
                for k, v in diag.items():
                    if got_diag.get(k) != v:
                        return False, f"diagnostics.{k}: expected {v}, got {got_diag.get(k)}"
            return True, "ok"

        return False, f"unknown mode {mode!r}"
    except Exception as e:  # noqa: BLE001 - any crash is a failure of the implementation
        return False, f"crash: {type(e).__name__}: {e}"


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="Run the .mini conformance suite against minifmt")
    ap.add_argument("-v", "--verbose", action="store_true")
    ap.add_argument("-k", "--filter", help="substring of case id or category")
    ap.add_argument("--json", action="store_true", help="print a JSON report")
    args = ap.parse_args(argv)
    cases = load_cases()
    if args.filter:
        cases = [c for c in cases if args.filter in c["id"] or args.filter == c["category"]]
    per_cat: Dict[str, Counter] = defaultdict(Counter)
    failures = []
    for case in cases:
        ok, msg = run_case(case)
        per_cat[case["category"]]["pass" if ok else "fail"] += 1
        if not ok:
            failures.append((case["id"], msg))
    if args.json:
        print(json.dumps({"total": len(cases), "failed": len(failures),
                          "categories": {k: dict(v) for k, v in sorted(per_cat.items())},
                          "failures": [{"id": i, "message": m} for i, m in failures]}, ensure_ascii=False, indent=2))
    else:
        for cat in sorted(per_cat):
            c = per_cat[cat]
            print(f"{cat:12s} {c['pass']:4d}/{c['pass'] + c['fail']:<4d}")
        for cid, msg in failures:
            print(f"FAIL {cid}: {msg}" if args.verbose else f"FAIL {cid}")
        print(f"{len(cases) - len(failures)}/{len(cases)} cases passed")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
