""".mini — forkable, token-efficient notation for LLM structured outputs.

Public API
----------
>>> from minifmt import Registry, parse, dumps, roundtrip_ok
>>> reg = Registry.load()             # discovers forks/*/contract.json
>>> doc = parse(text, reg.get("a"))   # -> Document (canonical JSON via .to_canonical())
>>> text2 = dumps(doc.to_canonical(), reg.get("a"))
"""
from __future__ import annotations

from typing import Any, Dict

from .contract import Contract, Field
from .errors import MiniError, MiniValidationError
from .parser import Document, detect_prefix, parse
from .prompt import parser_prompt, spec_block
from .registry import Registry
from .schema import from_json_schema, from_pydantic, to_json_schema
from .serializer import dumps
from .stream import Reader, ReaderResult, StreamRecord, create_reader, read_records
from .values import scalar_equal

__version__ = "1.1.0"
SPEC_VERSION = "1.1"

__all__ = ["Contract", "Field", "MiniError", "MiniValidationError", "Document", "parse",
           "dumps", "detect_prefix", "Registry", "spec_block", "parser_prompt",
           "canonical_equal", "roundtrip_ok", "Reader", "ReaderResult", "StreamRecord", "create_reader",
           "read_records", "from_json_schema", "to_json_schema", "from_pydantic", "__version__", "SPEC_VERSION"]


def canonical_equal(a: Any, b: Any) -> bool:
    """Structural equality tolerant to int/float representation differences."""
    if isinstance(a, dict) and isinstance(b, dict):
        return a.keys() == b.keys() and all(canonical_equal(a[k], b[k]) for k in a)
    if isinstance(a, list) and isinstance(b, list):
        return len(a) == len(b) and all(canonical_equal(x, y) for x, y in zip(a, b))
    return scalar_equal(a, b)


def roundtrip_ok(obj: Dict[str, Any], contract: Contract) -> bool:
    """obj -> .mini -> obj' must equal obj (and text -> obj -> text must be stable)."""
    text = dumps(obj, contract)
    back = parse(text, contract).to_canonical()
    ref = {"prefix": contract.prefix, "header": dict(obj.get("header", {})),
           contract.records_key: obj.get(contract.records_key, obj.get("records", []))}
    ref["header"]["n"] = len(ref[contract.records_key])
    ref["header"].setdefault("v", contract.header_keys["v"].default if "v" in contract.header_keys else 1)
    # extension fields omitted in obj are None in back
    for r in ref[contract.records_key]:
        for f in contract.extensions:
            if f.type == "mlist":
                r.setdefault(f.json_items, None)
                r.setdefault(f.json_selected, None)
            else:
                r.setdefault(f.name, None)
    return canonical_equal(back, ref) and dumps(back, contract) == text
