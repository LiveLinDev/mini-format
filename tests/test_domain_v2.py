"""Tests for mini-domain/2 adaptive codec, lean anti-CoT prompts, and KV-cache workflow."""
from __future__ import annotations

import json
from pathlib import Path
import sys
from types import SimpleNamespace
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from minifmt import domain
from minifmt.workflow import Workflow


def test_domain_v2_roundtrips_all_delimiters_and_edge_strings():
    sample = [
        {
            "id": 1000,
            "flag": True,
            "url": "https://cdn.example.com/items/1000",
            "coords": [34.05, -118.24],
            "note": "simple",
            "extra": None,
        },
        {
            "id": 1001,
            "flag": False,
            "url": "https://cdn.example.com/items/1001",
            "coords": [34.05, -118.24],
            "note": '"quoted start',
            "opt": 7,
        },
        {
            "id": 1002,
            "flag": True,
            "url": "https://cdn.example.com/items/1002",
            "coords": [10.0, 20.0],
            "note": "[bracketed] and {braced}\nmultiline\\slash",
            "extra": "?",
            "opt": None,
        },
        {
            "id": 1003,
            "flag": False,
            "url": "https://cdn.example.com/items/1003",
            "coords": [34.05, -118.24],
            "note": "",
            "extra": "~",
        },
        {
            "id": 1004,
            "flag": True,
            "url": "https://cdn.example.com/items/1004",
            "coords": [34.05, -118.24],
            "note": "multi word text with, comma",
        },
    ]
    c = domain.infer_contract([sample], "item")
    for sep in (None, "|", " ", ",", "\t"):
        wire = domain.encode_v2(sample, c, delimiter=sep, token_counter=len)
        assert "|v=2.0|" in wire.splitlines()[0]
        assert domain.decode(wire, c) == sample


def test_domain_v2_wrapped_envelope_constants_and_all_empty_rows():
    doc = {
        "meta": {"source": "api", "env": "prod"},
        "records": [
            {"id": 10, "const": "same_constant_value", "tag": "alpha"},
            {"id": 11, "const": "same_constant_value", "tag": "alpha"},
            {"id": 12, "const": "same_constant_value", "tag": "alpha"},
            {"id": 13, "const": "same_constant_value", "tag": "alpha"},
        ],
    }
    c = domain.infer_contract([doc], "wrap", record_path=["records"])
    wire = domain.encode_v2(doc, c, delimiter=" ")
    assert "|d=" in wire.splitlines()[0]
    assert "|m=" in wire.splitlines()[0]
    assert domain.decode(wire, c) == doc


def test_domain_v2_header_validation_rejects_bad_versions_and_flags():
    data = [{"id": 1, "name": "a"}, {"id": 2, "name": "b"}]
    c = domain.infer_contract([data], "row")
    v1_wire = domain.encode(data, c)
    v2_wire = domain.encode_v2(data, c, delimiter="|")

    # v=2 (without .0) remains rejected for v1 backwards-compat
    with pytest.raises(domain.DomainError, match="D_CONTRACT"):
        domain.decode(v1_wire.replace("|v=1|", "|v=2|"), c)
    # v1 cannot carry v2 header options
    with pytest.raises(domain.DomainError, match="D_HEADER"):
        domain.decode(v1_wire.replace("|n=2|", "|s=sp|n=2|"), c)
    for bad in (
        v2_wire.replace("|n=2|", "|s=bad|n=2|"),
        v2_wire.replace("|n=2|", "|b=0|n=2|"),
        v2_wire.replace("|n=2|", "|z=0|n=2|"),
        v2_wire.replace("|n=2|", "|tl=99|n=2|"),
        v2_wire.replace("|n=2|", "|p=bad|n=2|"),
        v2_wire.replace("|n=2|", "|dt=bad|n=2|"),
    ):
        with pytest.raises(domain.DomainError):
            domain.decode(bad, c)


def test_make_lean_prompt_and_extended_compact_rows(tmp_path):
    data = [
        {"id": 1, "active": True, "note": None, "titulo": "First item"},
        {"id": 2, "active": False, "opt": "x", "note": "ok", "titulo": "Second item"},
    ]
    c = domain.infer_contract([data], "ticket")
    full_en = domain.make_prompt(c, "en", data)
    lean_en = domain.make_lean_prompt(c, "en", data)
    lean_es = domain.make_prompt(c, "es", data, lean=True)
    assert len(lean_en) < len(full_en) // 2
    assert "Schema:" not in lean_en and "`?`" in lean_en and "`~`" in lean_es

    # Strict compact_rows continues to reject nullable/optional unless allow_nullable=True
    with pytest.raises(domain.DomainError, match="D_COMPACT_SCHEMA"):
        domain.encode_rows(data, c, last_text_field="titulo")
    rows_wire = domain.encode_rows(
        data, c, last_text_field="titulo", allow_nullable=True, compact_bools=True
    )
    assert "1 1 ~ ? First item" in rows_wire
    assert domain.decode_rows(
        rows_wire, c, last_text_field="titulo", expected_records=2,
        allow_nullable=True, compact_bools=True,
    ) == data
    rows_p = domain.make_rows_prompt(
        c, last_text_field="titulo", expected_records=2, lang="es",
        allow_nullable=True, compact_bools=True,
    )
    assert "0/1" in rows_p and "?" in rows_p
    pos = domain.positional_json_request("Task", c, expected_records=2, lang="en", allow_nullable=True)
    assert "prefixItems" in pos["schema"]["items"]


@pytest.mark.parametrize("data", [
    [{"items": [1], "title": "Report [beta]"}],
    [{"items": ["literal ] bracket"], "ids": [3, 4], "title": "Report [beta]"}],
])
def test_extended_compact_rows_keep_json_columns_and_trailing_text_separate(data):
    contract = domain.infer_contract([data], "report")
    options = {"last_text_field": "title", "allow_nullable": True}
    wire = domain.encode_rows(data, contract, **options)
    assert domain.decode_rows(wire, contract, expected_records=1, **options) == data


def test_projected_compact_rows_restore_known_nested_fields():
    data = [
        {"ticket": {"id": 42, "active": True}, "title": "First item"},
        {"ticket": {"id": 11, "active": False}, "title": "~"},
    ]
    contract = domain.infer_contract([data], "ticket")
    options = {
        "last_text_field": "title", "expected_records": 2,
        "known_rows": [{"ticket/id": 42}, {"ticket/id": 11}],
        "allow_nullable": True, "compact_bools": True,
    }
    prompt = domain.make_rows_prompt(contract, **options)
    assert "ticket/id" not in prompt
    assert '"ticket/active"=0/1' in prompt
    assert "Example: 1 Sample request" in prompt
    assert domain.decode_rows('1 First item\n\n0 "~"', contract, **options) == data


def test_workflow_lean_kv_cache_and_run_compact(tmp_path, monkeypatch):
    sample = [{"id": 1, "titulo": "Acceso"}, {"id": 2, "titulo": "Factura"}]
    bundle = tmp_path / ".mini"
    domain.build_bundle([sample], "ticket", bundle, lang="en")
    assert (bundle / "prompt.lean.en.md").is_file()
    assert (bundle / "prompt.lean.es.md").is_file()

    flow = Workflow(bundle, lang="en", prompt_style="lean", kv_cache_first=True)
    p = flow.prompt("Classify tickets", expected_records=2)
    assert p.startswith("Output format (replaces JSON instructions):")
    assert "# .mini output" in p

    # run_compact
    compact_wire = domain.encode_rows(sample, flow.contract, last_text_field="titulo")
    assert flow.run_compact(lambda _: compact_wire, "Classify", last_text_field="titulo", expected_records=2) == sample

    # complete with kv_cache_first=True prepends system message at index 0
    captured_msgs = []
    wire_v1 = domain.encode(sample, flow.contract)
    def fake_create(**kwargs):
        captured_msgs.append(kwargs["messages"])
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=wire_v1), finish_reason="stop")])

    res = flow.complete(fake_create, messages=[{"role": "user", "content": "hi"}], expected_records=2)
    assert res == sample
    assert captured_msgs[0][0]["role"] == "system"
    assert "# .mini output" in captured_msgs[0][0]["content"]
    assert captured_msgs[0][1] == {"role": "user", "content": "hi"}


def test_domain_cli_v2_and_lean_prompt(tmp_path, capsys):
    data = [{"id": 1, "name": "uno"}, {"id": 2, "name": "dos"}, {"id": 3, "name": "tres"}]
    bundle = tmp_path / ".mini"
    domain.build_bundle([data], "row", bundle, lang="en")
    in_json = tmp_path / "in.json"
    in_json.write_text(json.dumps(data), encoding="utf-8")
    out_mini = tmp_path / "out.mini"
    assert domain.main(["encode", str(in_json), "--contract", str(bundle / "contract.json"), "--version", "2", "--out", str(out_mini)]) == 0
    assert "|v=2.0|" in out_mini.read_text(encoding="utf-8").splitlines()[0]
    assert domain.main(["prompt", "--contract", str(bundle / "contract.json"), "--lean", "--lang", "en"]) == 0
    assert "Columns" in capsys.readouterr().out
