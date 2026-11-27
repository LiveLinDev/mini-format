import json
from random import Random
import subprocess
import sys

import pytest

from minifmt import domain, transport


def test_adaptive_transport_restores_values_and_types():
    source = [
        {"id": 8, "desc": "one\r\ntwo", "flag": False, "price": 2.5},
        {"id": 10, "desc": "true", "flag": True, "price": 0, "tags": [None, "a|b"]},
        {"id": 12, "desc": "  leading and trailing  ", "flag": False, "price": None},
        {"id": 14, "desc": 'literal "quote"', "flag": True, "price": 3.25},
    ]
    scorer = lambda text: len(text.encode("utf-8"))
    docs = (None, False, [], {}, "1\t\n", source, {"rows": source, "other": [{"v": 1}, {"v": 2}]})
    for doc in docs:
        encoded = transport.dumps(doc, count=scorer)
        assert scorer(encoded) <= scorer(domain._json(doc))
        restored = transport.loads(encoded)
        assert json.dumps(restored, sort_keys=True) == json.dumps(doc, sort_keys=True)
    assert type(transport.loads(transport.dumps(source))[0]["flag"]) is bool


def test_table_factoring_checks_all_reconstructed_dimensions():
    rows = [{"id": i * 3 + 5, "group": i // 8, "file": f"report_2026_{i}.html",
             "long": f"Valor {i}, incluye\r\n dos líneas y | delimitador"} for i in range(72)]
    contract = domain.infer_contract([rows], prefix="records")
    sidecar = ["records", [], transport._schema_wire(contract["schema"])]
    text = transport._best_rows(sidecar, domain.encode(rows, contract), len)
    assert text.startswith(":") and transport.loads(text, contract) == rows
    metadata = json.loads(text.split("\n", 1)[0][1:])
    methods = {rule[0] for rule in metadata[-1].values()}
    assert {"s", "g"} <= methods
    with pytest.raises(domain.DomainError):
        transport.loads(text.split("\n", 1)[0] + "\n")


def test_separate_tables_decode_with_no_out_of_band_state():
    doc = {"effect": True, "first": [{"a": i, "value": str(i)} for i in range(2, 28)],
           "second": [{"x": i, "note": "middle"} for i in range(50)]}
    def prefer_sections(text):
        return -1 if text.startswith("#") else len(text.encode("utf-8"))
    wire = transport.dumps(doc, count=prefer_sections)
    assert wire.startswith("#") and transport.loads(wire) == doc
    for bad in (wire[:-1], wire+"x", '#[{},[["repeat",1],["repeat",1]]]\n11',
                '|\na 1\na 2', '|\nrows[id|id]\n 1|2'):
        with pytest.raises(domain.DomainError):
            transport.loads(bad)


def test_well_typed_json_controls_stay_lossless_when_compacted():
    rng = Random(20261127)
    values = ["", '"text', "a=val", "false", "null", "a,b", "c | d", "x\tz", "E\u2028F", None, True, 4, 4.5]
    for _ in range(60):
        def block():
            return [{"id": i, "a": rng.choice(values), "b": {"k": rng.choice(values)}} for i in range(5)]
        source = {"two words": "yes", "x": block(), "y": block()}
        contract = domain.infer_contract([source])
        for separator in ("|", "\t"):
            wire = transport._tree(source, separator, len)
            assert transport.loads(wire, contract) == source
        assert transport.loads(transport.dumps(source, contract), contract) == source
    with pytest.raises(domain.DomainError, match="expected"):
        transport.loads('{"two words":0,"x":[],"y":[]}', contract)


def test_transport_cli_keeps_unicode_under_a_pipe():
    source = '{"id":23,"title":"Café \u2615"}'.encode()
    pack = subprocess.run([sys.executable, "-m", "minifmt.transport", "encode", "-"],
                          input=source, check=True, capture_output=True).stdout
    restored = subprocess.run([sys.executable, "-m", "minifmt.transport", "decode", "-"],
                              input=pack, check=True, capture_output=True).stdout
    assert restored == source
