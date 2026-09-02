"""Contract model: the machine-readable description of a .mini family (a fork).

A contract fixes, for one prefix, the ordered core fields, the optional
extension tail, the header keys and the typing/validation rules.  The parser
and the serializer are *interpreters* of the contract: adding a new fork never
requires writing code, only a ``contract.json`` file plus fixtures.

Contract JSON (abridged)::

    {
      "prefix": "a", "version": 1, "name": "Assessment items",
      "parent": null, "list_separator": ",",
      "header": {"required": ["n"], "keys": {"n": {"type": "int"}, ...}},
      "core": [ {"name": "id", "type": "str", "unique": true}, ... ],
      "extensions": [ {"name": "feedback", "type": "str"} ],
      "records_key": "items"
    }

Field types
-----------
str, int, float, bool, enum(values), list(item), mlist(item, marker),
tuple(items).  ``mlist`` is a list in which elements may carry the selection
marker ``*``; ``tuple`` is a fixed, named, comma-separated group that maps to
a JSON object (one level of nesting without nesting syntax).
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from .errors import E_CONTRACT, E_FORK, MiniError

SCALAR_TYPES = {"str", "int", "float", "bool", "enum"}
COMPOSITE_TYPES = {"list", "mlist", "tuple"}
ALL_TYPES = SCALAR_TYPES | COMPOSITE_TYPES
MARKER_MODES = {"exactly_one", "at_least_one", "at_most_one", "any"}


@dataclass
class Field:
    name: str
    type: str
    optional: bool = False
    unique: bool = False
    values: Optional[List[str]] = None          # enum
    item: str = "str"                            # list / mlist element type
    item_values: Optional[List[str]] = None      # enum items inside a list
    min: Optional[float] = None                  # numeric range or list arity
    max: Optional[float] = None
    marker: str = "exactly_one"                  # mlist rule
    items: List["Field"] = field(default_factory=list)  # tuple components
    count_key: Optional[str] = None              # header key fixing the exact list arity
    json_items: str = "items"                    # mlist canonical keys
    json_selected: str = "selected"
    desc: str = ""
    default: Any = None

    @staticmethod
    def from_dict(d: Dict[str, Any], path: str = "") -> "Field":
        where = f"{path}.{d.get('name', '?')}" if path else str(d.get("name", "?"))
        if "name" not in d or "type" not in d:
            raise MiniError(E_CONTRACT, 0, f"field {where}: 'name' and 'type' are required")
        t = d["type"]
        if t not in ALL_TYPES:
            raise MiniError(E_CONTRACT, 0, f"field {where}: unknown type '{t}'")
        f = Field(
            name=d["name"], type=t,
            optional=bool(d.get("optional", False)),
            unique=bool(d.get("unique", False)),
            values=list(d["values"]) if "values" in d else None,
            item=d.get("item", "str"),
            item_values=list(d["item_values"]) if "item_values" in d else None,
            min=d.get("min"), max=d.get("max"),
            marker=d.get("marker", "exactly_one"), count_key=d.get("count_key"),
            desc=d.get("desc", ""), default=d.get("default"),
        )
        if t == "enum" and not f.values:
            raise MiniError(E_CONTRACT, 0, f"field {where}: enum requires 'values'")
        if t in ("list", "mlist"):
            if f.item not in SCALAR_TYPES:
                raise MiniError(E_CONTRACT, 0, f"field {where}: list item type must be scalar")
            if f.item == "enum" and not f.item_values:
                raise MiniError(E_CONTRACT, 0, f"field {where}: enum items require 'item_values'")
        if t == "mlist":
            if f.marker not in MARKER_MODES:
                raise MiniError(E_CONTRACT, 0, f"field {where}: bad marker mode '{f.marker}'")
            j = d.get("json", {})
            f.json_items = j.get("items", "items")
            f.json_selected = j.get("selected", "correct" if f.marker == "exactly_one" else "selected")
        if t == "tuple":
            comps = d.get("items") or []
            if not comps:
                raise MiniError(E_CONTRACT, 0, f"field {where}: tuple requires 'items'")
            f.items = [Field.from_dict(c, where) for c in comps]
            for c in f.items:
                if c.type not in SCALAR_TYPES:
                    raise MiniError(E_CONTRACT, 0, f"field {where}: tuple components must be scalar")
        return f

    def to_dict(self) -> Dict[str, Any]:
        d: Dict[str, Any] = {"name": self.name, "type": self.type}
        if self.optional:
            d["optional"] = True
        if self.unique:
            d["unique"] = True
        if self.values is not None:
            d["values"] = self.values
        if self.type in ("list", "mlist"):
            d["item"] = self.item
            if self.item_values is not None:
                d["item_values"] = self.item_values
            if self.count_key:
                d["count_key"] = self.count_key
        if self.min is not None:
            d["min"] = self.min
        if self.max is not None:
            d["max"] = self.max
        if self.type == "mlist":
            d["marker"] = self.marker
            d["json"] = {"items": self.json_items, "selected": self.json_selected}
        if self.type == "tuple":
            d["items"] = [c.to_dict() for c in self.items]
        if self.desc:
            d["desc"] = self.desc
        if self.default is not None:
            d["default"] = self.default
        return d

    # Short human/LLM readable signature, e.g.  options: mlist<str>[2..6]*1
    def signature(self) -> str:
        if self.type == "enum":
            body = "enum{" + "|".join(self.values or []) + "}"
        elif self.type in ("list", "mlist"):
            it = self.item if self.item != "enum" else "{" + "|".join(self.item_values or []) + "}"
            body = f"{self.type}<{it}>"
            if self.min is not None or self.max is not None:
                lo = "" if self.min is None else int(self.min)
                hi = "" if self.max is None else int(self.max)
                body += f"[{lo}..{hi}]"
            if self.type == "mlist":
                body += {"exactly_one": "*1", "at_least_one": "*1+", "at_most_one": "*0..1", "any": "*"}[self.marker]
        elif self.type == "tuple":
            body = "tuple(" + ",".join(f"{c.name}:{c.type}" for c in self.items) + ")"
        else:
            body = self.type
            if self.min is not None or self.max is not None:
                body += f"[{'' if self.min is None else self.min}..{'' if self.max is None else self.max}]"
        return f"{self.name}:{body}" + ("?" if self.optional else "")


@dataclass
class HeaderKey:
    name: str
    type: str = "str"
    required: bool = False
    item: str = "str"
    items: List[Field] = field(default_factory=list)
    values: Optional[List[str]] = None
    default: Any = None
    desc: str = ""

    @staticmethod
    def from_dict(name: str, d: Dict[str, Any], required: bool) -> "HeaderKey":
        t = d.get("type", "str")
        if t not in ALL_TYPES or t == "mlist":
            raise MiniError(E_CONTRACT, 0, f"header key {name}: unsupported type '{t}'")
        hk = HeaderKey(name=name, type=t, required=required, item=d.get("item", "str"),
                       values=d.get("values"), default=d.get("default"), desc=d.get("desc", ""))
        if t == "tuple":
            hk.items = [Field.from_dict(c, f"header.{name}") for c in d.get("items", [])]
        return hk

    def as_field(self) -> Field:
        return Field(name=self.name, type=self.type, optional=not self.required, values=self.values,
                     item=self.item, items=self.items, default=self.default)


@dataclass
class Contract:
    prefix: str
    version: int = 1
    name: str = ""
    description: str = ""
    parent: Optional[str] = None
    list_separator: str = ","
    header_keys: Dict[str, HeaderKey] = field(default_factory=dict)
    core: List[Field] = field(default_factory=list)
    extensions: List[Field] = field(default_factory=list)
    records_key: str = "records"
    domain: str = ""
    author: str = ""
    license: str = "MIT"
    source: str = ""

    # ------------------------------------------------------------------ io
    @staticmethod
    def from_dict(d: Dict[str, Any]) -> "Contract":
        if "prefix" not in d:
            raise MiniError(E_CONTRACT, 0, "contract requires 'prefix'")
        prefix = str(d["prefix"])
        if not prefix or not prefix[0].isalpha() or not all(ch.isalnum() or ch in "_-" for ch in prefix):
            raise MiniError(E_CONTRACT, 0, f"prefix '{prefix}' must match [A-Za-z][A-Za-z0-9_-]*")
        c = Contract(
            prefix=prefix, version=int(d.get("version", 1)), name=d.get("name", ""),
            description=d.get("description", ""), parent=d.get("parent"),
            list_separator=d.get("list_separator", ","), records_key=d.get("records_key", "records"),
            domain=d.get("domain", ""), author=d.get("author", ""), license=d.get("license", "MIT"),
            source=d.get("source", ""),
        )
        if len(c.list_separator) != 1 or c.list_separator in "|\\*\n":
            raise MiniError(E_CONTRACT, 0, "list_separator must be a single character other than | \\ * or newline")
        hdr = d.get("header", {})
        required = set(hdr.get("required", ["n"]))
        required.add("n")
        keys = dict(hdr.get("keys", {}))
        keys.setdefault("n", {"type": "int", "desc": "number of records"})
        keys.setdefault("v", {"type": "int", "default": 1, "desc": "contract version"})
        for k, spec in keys.items():
            c.header_keys[k] = HeaderKey.from_dict(k, spec, k in required)
        for k in required:
            if k not in c.header_keys:
                c.header_keys[k] = HeaderKey(name=k, type="str", required=True)
        c.core = [Field.from_dict(f) for f in d.get("core", [])]
        c.extensions = [Field.from_dict(f) for f in d.get("extensions", [])]
        if not c.core:
            raise MiniError(E_CONTRACT, 0, "contract requires at least one core field")
        names = [f.name for f in c.core + c.extensions]
        if len(names) != len(set(names)):
            raise MiniError(E_CONTRACT, 0, "duplicate field names in contract")
        for f in c.extensions:
            f.optional = True  # extensions are optional by definition
        return c

    @staticmethod
    def load(path: str | Path) -> "Contract":
        with open(path, "r", encoding="utf-8") as fh:
            return Contract.from_dict(json.load(fh))

    def to_dict(self) -> Dict[str, Any]:
        return {
            "prefix": self.prefix, "version": self.version, "name": self.name,
            "description": self.description, "parent": self.parent, "domain": self.domain,
            "list_separator": self.list_separator, "records_key": self.records_key,
            "header": {
                "required": [k for k, v in self.header_keys.items() if v.required],
                "keys": {k: {kk: vv for kk, vv in {
                    "type": v.type, "item": v.item if v.type == "list" else None,
                    "items": [c.to_dict() for c in v.items] if v.type == "tuple" else None,
                    "values": v.values, "default": v.default, "desc": v.desc or None,
                }.items() if vv is not None} for k, v in self.header_keys.items()},
            },
            "core": [f.to_dict() for f in self.core],
            "extensions": [f.to_dict() for f in self.extensions],
            "author": self.author, "license": self.license, "source": self.source,
        }

    # -------------------------------------------------------------- helpers
    @property
    def fields(self) -> List[Field]:
        return self.core + self.extensions

    @property
    def arity(self) -> int:
        return len(self.core)

    def field_index(self) -> Dict[str, int]:
        return {f.name: i for i, f in enumerate(self.fields)}

    def signature(self) -> str:
        """Compact textual signature of the record layout."""
        core = " | ".join(f.signature() for f in self.core)
        ext = " | ".join(f.signature() for f in self.extensions)
        return core + (f" || {ext}" if ext else "")

    # ---------------------------------------------------------------- forks
    def check_fork_of(self, parent: "Contract") -> List[MiniError]:
        """Verify the fork invariants against the declared parent contract.

        I3 (stable core): the child's core must start with the parent's full
        field list (core + extensions of the parent become the child's
        prefix of fields) and keep names, order and types.
        I4 (tail extension): only appended fields may be new.
        """
        errs: List[MiniError] = []
        parent_fields = parent.fields
        child_fields = self.fields
        if len(child_fields) < len(parent_fields):
            errs.append(MiniError(E_FORK, 0, f"fork '{self.prefix}' drops fields of parent '{parent.prefix}'"))
            return errs
        for i, (pf, cf) in enumerate(zip(parent_fields, child_fields)):
            if pf.name != cf.name or pf.type != cf.type:
                errs.append(MiniError(E_FORK, 0,
                    f"fork '{self.prefix}' changes inherited field #{i+1}: parent {pf.signature()} != child {cf.signature()}"))
            if pf.type in ("list", "mlist") and pf.item != cf.item:
                errs.append(MiniError(E_FORK, 0, f"fork '{self.prefix}' changes item type of '{pf.name}'"))
            if pf.type == "tuple" and [c.name for c in pf.items] != [c.name for c in cf.items]:
                errs.append(MiniError(E_FORK, 0, f"fork '{self.prefix}' changes tuple layout of '{pf.name}'"))
        if self.list_separator != parent.list_separator:
            errs.append(MiniError(E_FORK, 0, "fork changes list_separator of its parent"))
        for k, hk in parent.header_keys.items():
            if hk.required and not (k in self.header_keys and self.header_keys[k].required):
                errs.append(MiniError(E_FORK, 0, f"fork drops required header key '{k}'"))
        return errs
