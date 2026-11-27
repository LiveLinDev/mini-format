"""Tests for constrained-decoding grammar compilers (GBNF, Lark, Regex) and CLI."""
from __future__ import annotations

import json
from pathlib import Path
import re
import sys
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from minifmt import Contract, Field, cli, contract_to_gbnf, contract_to_lark, contract_to_regex, dumps
from minifmt.domain import encode, encode_rows, infer_contract


def _spec_contract() -> Contract:
    return Contract.from_dict({
        "prefix": "tk",
        "version": 1,
        "name": "Ticket",
        "core": [
            {"name": "id", "type": "int"},
            {"name": "prio", "type": "enum", "values": ["high", "med", "low"]},
            {"name": "ok", "type": "bool"},
            {"name": "day", "type": "date", "optional": True},
            {"name": "title", "type": "str"},
        ],
        "extensions": [],
    })


def test_spec_contract_grammars_and_regex_match():
    c = _spec_contract()
    gbnf = contract_to_gbnf(c, expected_records=2)
    lark = contract_to_lark(c, expected_records=2)
    regex = contract_to_regex(c, expected_records=2)

    assert "root ::=" in gbnf and '"high" | "low" | "med"' in gbnf
    assert "start:" in lark and 'BOOLV: "true" | "false"' in lark

    sample = {
        "header": {"n": 2},
        "records": [
            {"id": 1, "prio": "high", "ok": True, "day": "2026-11-26", "title": "Auth bug"},
            {"id": 2, "prio": "low", "ok": False, "day": None, "title": "UI glitch"},
        ],
    }
    wire = dumps(sample, c)
    assert re.fullmatch(regex, wire) is not None
    assert re.fullmatch(regex, wire.replace("high", "invalid_enum")) is None


def test_domain_contract_compact_rows_grammar():
    data = [{"id": 1, "score": 9.5, "titulo": "Error acceso"}, {"id": 2, "score": 4.0, "titulo": "Factura doble"}]
    dc = infer_contract([data], "ticket")
    wire = encode(data, dc, shared=False, dictionaries=False)
    rows_wire = encode_rows(data, dc, last_text_field="titulo")

    std_re = contract_to_regex(dc, expected_records=2)
    rows_re = contract_to_regex(dc, compact_rows=True, last_text_field="titulo", expected_records=2)
    assert re.fullmatch(std_re, wire) is not None
    assert re.fullmatch(rows_re, rows_wire) is not None

    gbnf_rows = contract_to_gbnf(dc, compact_rows=True, last_text_field="titulo", expected_records=2)
    lark_rows = contract_to_lark(dc, compact_rows=True, last_text_field="titulo", expected_records=2)
    assert "tailstr ::=" in gbnf_rows and "TAILSTR" in lark_rows


def test_cli_grammar_outputs_and_errors(tmp_path, capsys):
    data = [{"id": 1, "name": "ok"}]
    dc = infer_contract([data], "item")
    cfile = tmp_path / "contract.json"
    cfile.write_text(json.dumps(dc), encoding="utf-8")
    out = tmp_path / "out.lark"
    assert cli.main(["grammar", str(cfile), "--format", "lark", "--out", str(out)]) == 0
    assert "start:" in out.read_text(encoding="utf-8")
    assert cli.main(["grammar", "a", "--format", "gbnf"]) == 0
    assert "root ::=" in capsys.readouterr().out
    with pytest.raises(ValueError, match="unsupported grammar delimiter"):
        contract_to_gbnf(dc, delimiter=";")
