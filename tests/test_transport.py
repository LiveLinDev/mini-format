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


def test_transport_can_preserve_a_single_table_and_its_metadata_with_both_codecs():
    rows = [{"id": 13 + index * 3, "owner": "Equipo norte", "text": f"Tarea de revisión {index}"}
            for index in range(8)]
    source = {"entries": rows, "skip": 12, "total": 30, "complete": False}
    contract = domain.infer_contract([source])

    def prefer_adaptive(text):
        return 0 if text.startswith("=") and "|v=2.0|" in text.split("\n", 2)[1] else len(text)

    adaptive = transport.dumps(source, contract, count=prefer_adaptive)
    sections = transport.dumps(source, contract, count=lambda text: 0 if text.startswith("#") else len(text))
    assert adaptive.startswith("=") and "|v=2.0|" in adaptive.splitlines()[1]
    assert sections.startswith("#") and "^id=13:3 " in sections.splitlines()[1]
    assert transport.loads(adaptive, contract) == transport.loads(sections, contract) == source


def test_sequence_table_is_self_contained_and_keeps_scalar_types():
    rows = [{"sequence": 10 - index * 3, "note": note, "other": other, "flag": bool(index % 2)}
            for index, (note, other) in enumerate((
                ("two simple words", "123"), (' Lead\r\n"tail" ', 123), ("", "a b"), ("[literal]", None),
                ("do not split here", "A\\B\tC"), ("repeated words", "true"),
            ))]
    wire = transport.dumps(rows, count=lambda text: 0 if text.startswith("^") else len(text))
    assert wire.startswith("^sequence=10:-3 ") and wire.split("\n", 1)[0].endswith(" note")
    assert json.dumps(transport.loads(wire), sort_keys=True) == json.dumps(rows, sort_keys=True)
    for bad in ("^id=0:0 value\na\nb", "^id=1:1 id value\n1 a\n2 b", "^id=1:1 value\na",
                '^id=1:1 tag value\n"broken\na b', '^id=1:1 value\n"pending\nb'):
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


def test_model_table_has_explicit_ids_counts_and_lossless_text():
    rows = [{"id": 9 + index * 3, "ok": index % 2 == 0, "note": note}
            for index, note in enumerate(("Café listo", 'La pantalla muestra "error"', "", " línea\nsegunda ",
                                           "true", "<html>", "texto más largo", "último caso"))]
    doc = {"team": "norte", "tickets": rows, "page": 2}
    wire = transport.dumps(doc, for_model=True)
    assert wire.startswith('+{"team":"norte","page":2}\ntickets[8] id:i ok:b note:s\n9 true Café listo')
    assert transport.loads(wire) == doc
    assert transport.loads(transport.dumps(rows, for_model=True)) == rows
    for wrong in (wire.replace("tickets[8]", "tickets[7]"), wire.replace("ok:b", "id:b"),
                  wire.replace('"page":2', '"tickets":2')):
        with pytest.raises(domain.DomainError):
            transport.loads(wrong)


def test_model_table_falls_back_to_complete_json_for_nested_rows():
    doc = {"rows": [{"id": 1, "info": {"x": None}}, {"id": 2, "info": {"x": 4}}]}
    assert transport.dumps(doc, for_model=True) == domain._json(doc)
