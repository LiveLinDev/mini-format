"""HU12: contratos .mini desde/hacia JSON Schema y modelos Pydantic.

Escenario 1: cinco esquemas externos de un nivel (tests/fixtures/schemas, con su
procedencia en ``$comment``) se convierten en contratos que aprueban la misma
verificación que ``mini check-forks`` (se ejecuta el comando sobre un directorio
de familias temporal con fixtures generados desde los ``examples`` del esquema).

Escenario 2: un esquema con anidación de más de un nivel produce E20 citando
SPEC §12.
"""
from __future__ import annotations

import contextlib
import io
import json
import shutil
import sys
import tempfile
import unittest
from enum import Enum
from pathlib import Path
from typing import List, Optional

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from minifmt import Contract, MiniError, MiniValidationError, Registry, cli, dumps, parse  # noqa: E402
from minifmt.schema import from_json_schema, from_pydantic, to_json_schema  # noqa: E402

SCHEMAS = ROOT / "tests" / "fixtures" / "schemas"
EXTERNAL = {
    # file -> (prefix, expected record signature)
    "library_book.schema.json": ("book", "isbn:str | title:str | authors:list<str>[1..8] | year:int[1450..2100] | "
                                 "language:enum{es|en|pt|fr} | available:bool || call_number:str? | subjects:list<str>[..5]?"),
    "weather_observation.schema.json": ("wx", "station_id:str | observed_at:str | temperature_c:float[-90..60] | "
                                        "humidity_pct:int[0..100] | wind:tuple(speed_kmh:float,direction_deg:int) | "
                                        "condition:enum{clear|cloudy|rain|fog|storm} | pressure_hpa:float[850..1090]? || remarks:str?"),
    "support_ticket.schema.json": ("tk", "ticket_id:str | subject:str | priority:enum{low|normal|high|urgent} | "
                                   "status:enum{open|pending|solved|closed} | created:str | requester_email:str | assignee:str? || "
                                   "labels:list<str>[..6]? | satisfaction:int[1..5]?"),
    "job_posting.pydantic.schema.json": ("job", "code:str | title:str | contract:enum{full_time|part_time|internship|temporary} | "
                                         "remote:bool | salary_min:int[0..]? | skills:list<str>[..10] || city:str? | deadline:date?"),
    "pharmacy_item.schema.json": ("rx", "sku:str | generic_name:str | form:enum{tablet|capsule|syrup|injection|cream} | strength:str | "
                                  "units_in_stock:int[0..] | unit_price:float | currency:enum{PEN} | prescription_required:bool || "
                                  "storage:enum{room|refrigerated}? | atc_codes:list<str>[..3]?"),
}

try:
    import jsonschema  # type: ignore
except ImportError:  # pragma: no cover
    jsonschema = None
try:
    import pydantic  # type: ignore

    class _Probe(pydantic.BaseModel):
        a: int

    _Probe.model_json_schema()
    PYDANTIC_V2 = True
except Exception:  # pragma: no cover - absent, v1, or unusable on this interpreter (e.g. Python 3.9.0)
    pydantic = None
    PYDANTIC_V2 = False


def run_cli(*argv):
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        try:
            rc = cli.main(list(argv))
        except SystemExit as e:
            rc = e.code
    return rc, out.getvalue(), err.getvalue()


def load(name):
    return json.loads((SCHEMAS / name).read_text(encoding="utf-8"))


def example_records(schema, contract):
    ex = schema["examples"]
    if contract.records_key in schema.get("properties", {}):
        return ex[0][contract.records_key]
    return ex


def write_family(forks_dir: Path, contract: Contract, records) -> None:
    """Materialise a family folder with the fixtures that check-forks requires."""
    folder = forks_dir / contract.prefix
    (folder / "fixtures").mkdir(parents=True)
    (folder / "contract.json").write_text(json.dumps(contract.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
    text = dumps({"header": {}, contract.records_key: records}, contract)
    canonical = parse(text, contract).to_canonical()
    (folder / "fixtures" / "valid.mini").write_text(text + "\n", encoding="utf-8")
    (folder / "fixtures" / "canonical.json").write_text(json.dumps(canonical, ensure_ascii=False, indent=2), encoding="utf-8")
    lines = text.split("\n")
    (folder / "fixtures" / "bad_count.mini").write_text("\n".join(lines[:-1]) + "\n", encoding="utf-8")
    (folder / "fixtures" / "bad_arity.mini").write_text("\n".join(lines[:-1] + ["only-one-field"]) + "\n", encoding="utf-8")


class TestExternalSchemas(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_five_one_level_schemas_pass_check_forks(self):
        forks = self.tmp / "forks"
        forks.mkdir()
        for name, (prefix, signature) in EXTERNAL.items():
            with self.subTest(schema=name):
                schema = load(name)
                self.assertIn("Provenance", schema["$comment"])
                warnings = []
                c = from_json_schema(schema, prefix, warnings=warnings)
                self.assertEqual(c.signature(), signature)
                records = example_records(schema, c)
                write_family(forks, c, records)
                # every example value survives the .mini round trip
                back = parse(dumps({"header": {}, c.records_key: records}, c), c).records
                for src, got in zip(records, back):
                    for k, v in src.items():
                        if isinstance(v, dict):  # tuple: absent optional components decode as null
                            self.assertEqual({kk: got[k][kk] for kk in v}, v, k)
                        else:
                            self.assertEqual(got[k], v, k)
        rc, out, err = run_cli("check-forks", str(forks))
        self.assertEqual(rc, 0, out + err)
        self.assertIn("ALL FORKS PASS (5 forks)", out)

    @unittest.skipIf(jsonschema is None, "jsonschema not installed")
    def test_examples_are_valid_instances_of_their_schema(self):
        for name in EXTERNAL:
            schema = load(name)
            validator = jsonschema.Draft7Validator(schema)
            for ex in schema["examples"]:
                self.assertEqual(list(validator.iter_errors(ex)), [], name)

    def test_non_representable_keywords_are_reported(self):
        warnings = []
        from_json_schema(load("library_book.schema.json"), "book", warnings=warnings)
        self.assertTrue(any("pattern" in w for w in warnings))
        self.assertTrue(any("minLength" in w for w in warnings))
        with self.assertRaises(MiniError) as cm:
            from_json_schema(load("library_book.schema.json"), "book", strict=True)
        self.assertEqual(cm.exception.code, "E20")

    def test_document_form_with_header_and_prefix(self):
        schema = {"type": "object", "properties": {
            "prefix": {"const": "inv"},
            "header": {"type": "object", "properties": {"store": {"type": "string"}, "k": {"type": "integer"}},
                       "required": ["store"]},
            "rows": {"type": "array", "items": {"type": "object", "properties": {"sku": {"type": "string"}},
                                                "required": ["sku"]}}}}
        c = from_json_schema(schema)
        self.assertEqual((c.prefix, c.records_key), ("inv", "rows"))
        self.assertTrue(c.header_keys["store"].required)
        self.assertFalse(c.header_keys["k"].required)
        self.assertEqual(c.header_keys["k"].type, "int")
        # explicit records_key turns a record-with-array into a document wrapper
        c2 = from_json_schema({"type": "object", "properties": {
            "store": {"type": "string"}, "rows": schema["properties"]["rows"]}, "required": ["store"]},
            "inv", records_key="rows")
        self.assertEqual(list(c2.header_keys)[:1], ["store"])
        self.assertTrue(c2.header_keys["store"].required)


class TestNestingLimit(unittest.TestCase):
    def assert_limit(self, schema, where):
        with self.assertRaises(MiniError) as cm:
            from_json_schema(schema, "x")
        self.assertEqual(cm.exception.code, "E20")
        self.assertIn("SPEC §12", cm.exception.message)
        self.assertIn(where, cm.exception.message)

    def test_nested_fixture_is_rejected(self):
        schema = load("nested_order.schema.json")
        self.assert_limit(schema, "customer/properties/address")

    def test_each_kind_of_deep_nesting(self):
        obj = {"type": "object", "properties": {"a": {"type": "string"}}}
        cases = {
            "array of objects": ({"id": {"type": "string"}, "lines": {"type": "array", "items": obj}}, "lines"),
            "array of arrays": ({"id": {"type": "string"}, "m": {"type": "array", "items": {"type": "array"}}}, "/m"),
            "object in object": ({"id": {"type": "string"}, "o": {"type": "object", "properties": {"in": obj}}}, "o/properties/in"),
            "array in object": ({"id": {"type": "string"}, "o": {"type": "object", "properties": {
                "l": {"type": "array", "items": {"type": "string"}}}}}, "o/properties/l"),
        }
        for label, (props, where) in cases.items():
            with self.subTest(label):
                self.assert_limit({"type": "object", "properties": props, "required": ["id"]}, where)

    def test_recursive_reference_is_rejected(self):
        schema = {"$defs": {"Node": {"$ref": "#/$defs/Node"}}, "type": "object",
                  "properties": {"id": {"type": "string"}, "n": {"$ref": "#/$defs/Node"}}, "required": ["id"]}
        self.assert_limit(schema, "recursive")

    def test_other_unrepresentable_inputs(self):
        for schema in ({"type": "array"}, {"type": "object", "properties": {"a": {"type": "string"}}},
                       {"type": "object", "properties": {"a": {"enum": [1, 2]}}, "required": ["a"]},
                       {"type": "object", "properties": {"a": {"type": ["string", "integer"]}}, "required": ["a"]}):
            with self.assertRaises(MiniError):
                from_json_schema(schema, "x")


class TestRoundTrip(unittest.TestCase):
    def test_contract_to_schema_to_contract_is_lossless_for_official_families(self):
        reg = Registry.load(ROOT / "forks")
        for c in reg:
            with self.subTest(prefix=c.prefix):
                schema = json.loads(json.dumps(to_json_schema(c)))
                warnings = []
                back = from_json_schema(schema, warnings=warnings)
                self.assertEqual(back.to_dict(), Contract.from_dict(c.to_dict()).to_dict())
                self.assertEqual(warnings, [])
                rec = from_json_schema(to_json_schema(c, record_only=True))
                self.assertEqual([f.to_dict() for f in rec.fields], [f.to_dict() for f in c.fields])

    def test_external_schema_round_trip(self):
        for name, (prefix, _) in EXTERNAL.items():
            c = from_json_schema(load(name), prefix)
            again = from_json_schema(to_json_schema(c))
            self.assertEqual(again.to_dict(), c.to_dict(), name)

    def test_date_and_decimal_types(self):
        """SPEC 1.1: date y decimal se convierten en ambos sentidos sin pérdida."""
        schema = {
            "type": "object",
            "title": "Factura",
            "properties": {
                "id": {"type": "integer"},
                "fecha": {"type": "string", "format": "date", "formatMinimum": "2020-01-01"},
                "monto": {"type": "string", "format": "decimal"},
                "pagos": {"type": "array", "items": {"type": "string", "format": "date"}},
            },
            "required": ["id", "fecha", "monto", "pagos"],
        }
        warnings = []
        c = from_json_schema(schema, "fac", warnings=warnings)
        self.assertEqual(warnings, [])
        self.assertEqual([(f.name, f.type, f.min) for f in c.fields],
                         [("id", "int", None), ("fecha", "date", "2020-01-01"), ("monto", "decimal", None), ("pagos", "list", None)])
        self.assertEqual(c.fields[3].item, "date")
        exported = json.loads(json.dumps(to_json_schema(c)))
        self.assertEqual(from_json_schema(exported).to_dict(), c.to_dict())
        doc = parse("fac|n=1\n1|2024-02-29|10.50|2024-01-01,2024-02-01\n", c)
        self.assertEqual(doc.records[0]["fecha"], "2024-02-29")
        with self.assertRaises(MiniValidationError) as err:
            parse("fac|n=1\n1|2024-02-30|10.50|2024-01-01\n", c)
        self.assertEqual([(x.code, x.line) for x in err.exception.errors], [("E06", 2)])
        with self.assertRaises(MiniValidationError) as err:
            parse("fac|n=1\n1|2019-12-31|1|2024-01-01\n", c)
        self.assertEqual([x.code for x in err.exception.errors], ["E13"])

    @unittest.skipIf(jsonschema is None, "jsonschema not installed")
    def test_canonical_fixtures_validate_against_exported_schema(self):
        reg = Registry.load(ROOT / "forks")
        for c in reg:
            canonical = json.loads((reg.paths[c.prefix] / "fixtures" / "canonical.json").read_text(encoding="utf-8"))
            errors = list(jsonschema.Draft7Validator(to_json_schema(c)).iter_errors(canonical))
            self.assertEqual(errors, [], c.prefix)


if PYDANTIC_V2:
    class ContractKind(str, Enum):
        full_time = "full_time"
        part_time = "part_time"
        internship = "internship"
        temporary = "temporary"

    class Salary(pydantic.BaseModel):
        amount: float = pydantic.Field(ge=0)
        currency: str

    class JobPosting(pydantic.BaseModel):
        code: str
        title: str
        contract: ContractKind
        remote: bool
        salary_min: Optional[int] = pydantic.Field(ge=0)
        skills: List[str] = pydantic.Field(max_length=10)
        city: Optional[str] = None
        deadline: Optional[str] = None

    class Postings(pydantic.BaseModel):
        postings: List[JobPosting]

    class Offer(pydantic.BaseModel):
        code: str
        salary: Salary
        note: Optional[str] = None

    class Address(pydantic.BaseModel):
        city: str

    class Customer(pydantic.BaseModel):
        name: str
        address: Address

    class Order(pydantic.BaseModel):
        order_id: str
        customer: Customer


@unittest.skipUnless(PYDANTIC_V2, "pydantic v2 not installed")
class TestPydantic(unittest.TestCase):
    def test_model_matches_documented_schema_fixture(self):
        from_model = from_pydantic(Postings, "job")
        self.assertEqual(from_model.signature(), EXTERNAL["job_posting.pydantic.schema.json"][1])
        self.assertEqual(from_model.records_key, "postings")
        self.assertEqual(from_json_schema(Postings.model_json_schema(), "job").to_dict(), from_model.to_dict())

    def test_one_level_submodel_becomes_tuple(self):
        c = from_pydantic(Offer, "of")
        self.assertEqual(c.signature(), "code:str | salary:tuple(amount:float,currency:str) || note:str?")
        rec = {"code": "A1", "salary": {"amount": 3500, "currency": "PEN"}}
        self.assertEqual(parse(dumps({"header": {}, "records": [rec]}, c), c).records[0]["salary"]["amount"], 3500)

    def test_deep_model_is_rejected(self):
        with self.assertRaises(MiniError) as cm:
            from_pydantic(Order, "o")
        self.assertIn("SPEC §12", cm.exception.message)

    def test_rejects_non_models(self):
        with self.assertRaises(TypeError):
            from_pydantic(object(), "x")


class TestSchemaCli(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_from_schema_and_to_schema(self):
        out = self.tmp / "contract.json"
        rc, _, err = run_cli("from-schema", str(SCHEMAS / "support_ticket.schema.json"), "-p", "tk", "--out", str(out))
        self.assertEqual(rc, 0, err)
        self.assertIn("warning:", err)
        c = Contract.load(out)
        self.assertEqual(c.records_key, "tickets")
        rc, text, err = run_cli("to-schema", str(out))
        self.assertEqual(rc, 0, err)
        self.assertEqual(from_json_schema(json.loads(text)).to_dict(), c.to_dict())
        rc, text, _ = run_cli("to-schema", "a", "--record")
        self.assertEqual(rc, 0)
        self.assertEqual(json.loads(text)["x-mini"]["prefix"], "a")
        self.assertIn("options", json.loads(text)["properties"])

    def test_from_schema_nested_fails_with_spec_reference(self):
        rc, out, err = run_cli("from-schema", str(SCHEMAS / "nested_order.schema.json"), "-p", "ord")
        self.assertEqual(rc, 2)
        self.assertIn("SPEC §12", err)
        self.assertEqual(out, "")

    def test_from_schema_strict_and_missing_input(self):
        rc, _, err = run_cli("from-schema", str(SCHEMAS / "library_book.schema.json"), "-p", "b", "--strict")
        self.assertEqual(rc, 2)
        self.assertIn("E20", err)
        rc, _, _ = run_cli("from-schema", "-p", "b")
        self.assertNotEqual(rc, 0)

    @unittest.skipUnless(PYDANTIC_V2, "pydantic v2 not installed")
    def test_from_schema_pydantic_option(self):
        mod = self.tmp / "hu12_models.py"
        mod.write_text("from typing import List, Optional\nfrom pydantic import BaseModel\n"
                       "class Item(BaseModel):\n    sku: str\n    qty: int\n    tags: List[str]\n    note: Optional[str] = None\n",
                       encoding="utf-8")
        sys.path.insert(0, str(self.tmp))
        try:
            rc, text, err = run_cli("from-schema", "--pydantic", "hu12_models:Item", "-p", "it")
        finally:
            sys.path.remove(str(self.tmp))
            sys.modules.pop("hu12_models", None)
        self.assertEqual(rc, 0, err)
        self.assertEqual(Contract.from_dict(json.loads(text)).signature(), "sku:str | qty:int | tags:list<str> || note:str?")


if __name__ == "__main__":
    unittest.main()
