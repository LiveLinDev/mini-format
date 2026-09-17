"""Conversion between .mini contracts and JSON Schema (and Pydantic models).

``from_json_schema`` turns a JSON Schema into a :class:`~minifmt.contract.Contract`;
``to_json_schema`` describes the canonical object of a contract (SPEC §7) as a
JSON Schema (draft 2020-12); ``from_pydantic`` accepts a Pydantic model class
(``pydantic`` is optional and never imported by this module).

Accepted input
--------------
* **Record schema**: an object whose properties are the fields of a record.
* **Document schema**: an object with exactly one property that is an array of
  objects (the records, whose name becomes ``records_key``).  A ``header``
  object property and the remaining scalar properties become header keys; a
  ``prefix`` property with ``const`` provides the prefix.

Local references (``#/$defs/...``, ``#/definitions/...``) are resolved; a
nullable value may be written as ``type: [T, "null"]``, ``anyOf``/``oneOf``
with ``{"type": "null"}`` or an ``enum`` containing ``null``.

Mapping rules
-------------
``string`` -> ``str`` (``enum``/``const`` of strings -> ``enum``),
``integer`` -> ``int``, ``number`` -> ``float`` (``minimum``/``maximum`` ->
``min``/``max``; an integer ``exclusiveMinimum``/``exclusiveMaximum`` is
converted to an inclusive bound), ``boolean`` -> ``bool``, array of scalars ->
``list`` (``minItems``/``maxItems`` -> ``min``/``max``), object of scalars ->
``tuple``.  Required properties form the core in declaration order (a required
nullable property is a core field marked ``optional``); the remaining
properties form the extension tail.  Anything deeper than one level of nesting
(arrays of objects or arrays inside a record, objects inside objects) is
rejected with E20, citing SPEC §12.  Validation keywords without a contract
equivalent (``pattern``, ``format``, ``minLength``...) are reported through
``warnings`` and ignored, or raise E20 with ``strict=True``.

``to_json_schema`` records what JSON Schema cannot express (prefix, version,
parent, list separator, ``unique``, marked lists, ``count_key``...) in
``x-mini`` annotations, which validators ignore and ``from_json_schema`` reads
back, so contract -> JSON Schema -> contract is lossless.
"""
from __future__ import annotations

import copy
from typing import Any, Dict, List, Optional, Tuple

from .contract import Contract
from .errors import E_CONTRACT, MiniError

__all__ = ["from_json_schema", "to_json_schema", "from_pydantic", "SCHEMA_DIALECT"]

SCHEMA_DIALECT = "https://json-schema.org/draft/2020-12/schema"
X = "x-mini"

_SCALAR_JSON = {"string": "str", "integer": "int", "number": "float", "boolean": "bool"}
_JSON_OF = {"str": "string", "int": "integer", "float": "number", "bool": "boolean", "enum": "string",
            "date": "string", "decimal": "string"}
# SPEC 1.1 §6: forma textual de decimal
_DECIMAL_PATTERN = r"^-?[0-9]+(\.[0-9]+)?$"
_ANNOTATIONS = {"title", "description", "default", "examples", "$comment", "readOnly", "writeOnly",
                "deprecated", "$schema", "$id", "$defs", "definitions", "additionalProperties",
                "unevaluatedProperties", "type", "enum", "const", "properties", "required", "items",
                "minimum", "maximum", "exclusiveMinimum", "exclusiveMaximum", "minItems", "maxItems",
                "anyOf", "oneOf", "allOf", "$ref", "discriminator", "propertyNames"}
_LIMIT = "not representable in a .mini contract: nesting deeper than one level (SPEC §12)"


def _fail(msg: str) -> MiniError:
    return MiniError(E_CONTRACT, 0, msg)


class _Ctx:
    def __init__(self, root: Dict[str, Any], strict: bool, warnings: Optional[List[str]]):
        self.root = root
        self.strict = strict
        self.warnings = warnings if warnings is not None else []

    def resolve(self, node: Any, path: str) -> Dict[str, Any]:
        seen = 0
        while isinstance(node, dict) and "$ref" in node:
            ref = node["$ref"]
            if not isinstance(ref, str) or not ref.startswith("#/"):
                raise _fail(f"{path}: only local $ref are supported, got {ref!r}")
            target: Any = self.root
            for part in ref[2:].split("/"):
                part = part.replace("~1", "/").replace("~0", "~")
                if not isinstance(target, dict) or part not in target:
                    raise _fail(f"{path}: unresolvable $ref {ref!r}")
                target = target[part]
            extra = {k: v for k, v in node.items() if k != "$ref"}
            node = dict(target, **extra) if extra else target
            seen += 1
            if seen > 32:
                raise _fail(f"{path}: recursive $ref {ref!r} ({_LIMIT})")
        if node is True or node == {}:
            return {}
        if not isinstance(node, dict):
            raise _fail(f"{path}: schema must be an object")
        if "allOf" in node:
            parts = node["allOf"]
            if len(parts) != 1:
                raise _fail(f"{path}: allOf with several schemas is not supported")
            merged = dict(self.resolve(parts[0], path))
            merged.update({k: v for k, v in node.items() if k != "allOf"})
            return merged
        return node

    def unsupported(self, path: str, keywords: List[str]) -> None:
        if not keywords:
            return
        msg = f"{path}: ignored keywords without contract equivalent: {', '.join(sorted(keywords))}"
        if self.strict:
            raise _fail(msg)
        self.warnings.append(msg)


def _split_null(ctx: _Ctx, node: Dict[str, Any], path: str) -> Tuple[Dict[str, Any], bool]:
    """Return (schema without the null alternative, nullable)."""
    node = ctx.resolve(node, path)
    for key in ("anyOf", "oneOf"):
        if key in node:
            alts = [ctx.resolve(a, path) for a in node[key]]
            non_null = [a for a in alts if a.get("type") != "null"]
            if len(non_null) != 1:
                raise _fail(f"{path}: {key} with several non-null alternatives is not representable")
            inner = dict(non_null[0])
            for k, v in node.items():
                if k != key:
                    inner.setdefault(k, v)
            inner, nullable = _split_null(ctx, inner, path)
            return inner, nullable or len(alts) != len(non_null)
    t = node.get("type")
    nullable = False
    if isinstance(t, list):
        types = [x for x in t if x != "null"]
        nullable = len(types) != len(t)
        if len(types) != 1:
            raise _fail(f"{path}: union types {t} are not representable")
        node = dict(node, type=types[0])
    if "enum" in node and None in node["enum"]:
        node = dict(node, enum=[v for v in node["enum"] if v is not None])
        nullable = True
    return node, nullable


def _kind(node: Dict[str, Any]) -> str:
    t = node.get("type")
    if t is None:
        if "enum" in node or "const" in node:
            return "string"
        if "properties" in node:
            return "object"
        if "items" in node:
            return "array"
    return t if isinstance(t, str) else ""


def _scalar(ctx: _Ctx, name: str, node: Dict[str, Any], path: str, item: bool = False) -> Dict[str, Any]:
    kind = _kind(node)
    out: Dict[str, Any] = {}
    ignored = [k for k in node if k not in _ANNOTATIONS and not k.startswith("x-")]
    if "enum" in node or "const" in node:
        values = list(node["enum"]) if "enum" in node else [node["const"]]
        if not values or not all(isinstance(v, str) for v in values):
            raise _fail(f"{path}: only string enums are representable, got {values!r}")
        if kind not in ("string", ""):
            raise _fail(f"{path}: enum of type {kind!r} is not representable")
        out["type"] = "enum"
        out["values"] = values
    elif kind == "string" and (node.get("format") == "date" or (node.get(X) or {}).get("type") == "date"):
        out["type"] = "date"
        ignored = [k for k in ignored if k not in ("format", "pattern", "formatMinimum", "formatMaximum", X)]
    elif kind == "string" and (node.get("format") == "decimal" or (node.get(X) or {}).get("type") == "decimal"):
        out["type"] = "decimal"
        ignored = [k for k in ignored if k not in ("format", "pattern", X)]
    elif kind in _SCALAR_JSON:
        out["type"] = _SCALAR_JSON[kind]
    elif kind in ("array", "object"):
        raise _fail(f"{path}: {kind} inside {'a list' if item else 'a tuple'} is {_LIMIT}")
    else:
        raise _fail(f"{path}: unsupported or missing type {node.get('type')!r}")
    if out["type"] in ("int", "float"):
        lo, hi = node.get("minimum"), node.get("maximum")
        for key, bound, step in (("exclusiveMinimum", "lo", 1), ("exclusiveMaximum", "hi", -1)):
            val = node.get(key)
            if isinstance(val, bool) or val is None:
                if val is True:
                    ignored.append(key)
                continue
            if out["type"] == "int" and float(val).is_integer():
                val = int(val) + step
                if bound == "lo":
                    lo = val if lo is None else max(lo, val)
                else:
                    hi = val if hi is None else min(hi, val)
            else:
                ignored.append(key)
        if lo is not None:
            out["min"] = lo
        if hi is not None:
            out["max"] = hi
    elif out["type"] in ("date", "decimal"):
        ann = node.get(X) or {}
        lo = ann.get("min", node.get("formatMinimum"))
        hi = ann.get("max", node.get("formatMaximum"))
        if item and (lo is not None or hi is not None):
            ignored.append("formatMinimum/formatMaximum")
        else:
            if lo is not None:
                out["min"] = lo
            if hi is not None:
                out["max"] = hi
    else:
        ignored += [k for k in ("minimum", "maximum", "exclusiveMinimum", "exclusiveMaximum") if k in node]
    ctx.unsupported(path, ignored)
    return out


def _desc_default(field: Dict[str, Any], node: Dict[str, Any], outer: Dict[str, Any]) -> None:
    desc = outer.get("description", node.get("description"))
    if isinstance(desc, str) and desc:
        field["desc"] = desc
    default = outer.get("default", node.get("default"))
    if default is not None and not isinstance(default, (dict, list)):
        field["default"] = default


def _field(ctx: _Ctx, name: str, raw: Any, required: bool, path: str) -> Optional[Dict[str, Any]]:
    """Convert one property. Returns None for properties that belong to a marked list."""
    outer = ctx.resolve(raw, path)
    ann = outer.get(X) or {}
    if ann.get("selected_of"):
        return None
    node, nullable = _split_null(ctx, outer, path)
    ann = dict(node.get(X) or {}, **ann)
    kind = _kind(node)
    f: Dict[str, Any] = {"name": ann.get("field", name)}
    if kind == "array":
        items, item_null = _split_null(ctx, node.get("items", {}), f"{path}/items")
        if item_null:
            ctx.unsupported(path, ["items(null)"])
        if _kind(items) in ("array", "object"):
            raise _fail(f"{path}: array of {_kind(items)}s is {_LIMIT}")
        sc = _scalar(ctx, name, items, f"{path}/items", item=True)
        f["type"] = "mlist" if ann.get("type") == "mlist" else "list"
        f["item"] = sc["type"]
        if sc["type"] == "enum":
            f["item_values"] = sc["values"]
        if "minItems" in node:
            f["min"] = node["minItems"]
        if "maxItems" in node:
            f["max"] = node["maxItems"]
        if ann.get("count_key"):
            f["count_key"] = ann["count_key"]
        if f["type"] == "mlist":
            f["marker"] = ann.get("marker", "exactly_one")
            f["json"] = {"items": name, "selected": ann.get("selected", "selected")}
        extra = [k for k in node if k not in _ANNOTATIONS and not k.startswith("x-")]
        ctx.unsupported(path, extra)
    elif kind == "object":
        props = node.get("properties")
        if not isinstance(props, dict) or not props:
            raise _fail(f"{path}: object without properties is not representable")
        req = set(node.get("required", []))
        comps = []
        for cname, craw in props.items():
            cnode, cnull = _split_null(ctx, craw, f"{path}/properties/{cname}")
            if _kind(cnode) in ("array", "object"):
                raise _fail(f"{path}/properties/{cname}: {_kind(cnode)} inside an object is {_LIMIT}")
            comp = {"name": cname}
            comp.update(_scalar(ctx, cname, cnode, f"{path}/properties/{cname}"))
            if cnull or cname not in req:
                comp["optional"] = True
            _desc_default(comp, cnode, ctx.resolve(craw, path))
            comps.append(comp)
        f["type"] = "tuple"
        f["items"] = comps
    else:
        f.update(_scalar(ctx, name, node, path))
    if ann.get("unique"):
        f["unique"] = True
    if nullable and required:
        f["optional"] = True
    _desc_default(f, node, outer)
    return f


def _is_record_array(ctx: _Ctx, raw: Any, path: str) -> bool:
    node, _ = _split_null(ctx, raw, path)
    if _kind(node) != "array":
        return False
    items, _ = _split_null(ctx, node.get("items", {}), path)
    return _kind(items) == "object"


def _header_key(ctx: _Ctx, name: str, raw: Any, path: str) -> Dict[str, Any]:
    f = _field(ctx, name, raw, True, path) or {}
    if f.get("type") == "mlist":
        raise _fail(f"{path}: marked lists are not allowed in the header")
    hk: Dict[str, Any] = {"type": f["type"]}
    for k in ("item", "items", "values", "default", "desc"):
        if k in f:
            hk[k] = f[k]
    if f["type"] == "list" and "item_values" in f:
        hk["values"] = f["item_values"]
    return hk


def from_json_schema(schema: Dict[str, Any], prefix: Optional[str] = None, *, name: Optional[str] = None,
                     records_key: Optional[str] = None, strict: bool = False,
                     warnings: Optional[List[str]] = None) -> Contract:
    """Build a contract from a JSON Schema (record or document form).

    ``prefix`` is required unless the schema carries it (``x-mini`` or a
    ``prefix`` property with ``const``).  Non-representable validation
    keywords are appended to ``warnings`` (or raise E20 when ``strict``).
    Raises :class:`MiniError` E20 for structures beyond SPEC §12.
    """
    if not isinstance(schema, dict):
        raise _fail("JSON Schema must be an object")
    ctx = _Ctx(schema, strict, warnings)
    root = ctx.resolve(schema, "#")
    meta = dict(root.get(X) or {})
    if _kind(root) != "object" or not isinstance(root.get("properties"), dict):
        raise _fail("#: the schema must describe an object with properties (a record or a document)")
    props: Dict[str, Any] = root["properties"]
    arrays = [k for k, v in props.items() if _is_record_array(ctx, v, f"#/properties/{k}")]
    wanted = records_key
    if not wanted and meta.get("records_key") in arrays:
        wanted = meta["records_key"]
    if wanted:
        if wanted not in props:
            raise _fail(f"#: records property '{wanted}' not found")
        arrays = [wanted] if wanted in arrays else []
        if not arrays:
            raise _fail(f"#/properties/{wanted}: records property must be an array of objects")
    elif not (set(props) - set(arrays) <= {"prefix", "header"}):
        # A record with arrays of objects is not a document wrapper: its nesting is rejected below.
        arrays = []
    header_keys: Dict[str, Any] = {}
    header_required: List[str] = []
    if arrays:
        if len(arrays) > 1:
            raise _fail(f"#: several record arrays ({', '.join(arrays)}) are not representable in one document (SPEC §12)")
        rkey = arrays[0]
        arr, _ = _split_null(ctx, props[rkey], f"#/properties/{rkey}")
        record, _ = _split_null(ctx, arr.get("items", {}), f"#/properties/{rkey}/items")
        base = f"#/properties/{rkey}/items"
        for k, raw in props.items():
            p = f"#/properties/{k}"
            if k == rkey:
                continue
            node, _ = _split_null(ctx, raw, p)
            if k == "prefix" and ("const" in node or "enum" in node):
                if not prefix and not meta.get("prefix"):
                    vals = [node["const"]] if "const" in node else node["enum"]
                    if len(vals) == 1:
                        meta["prefix"] = vals[0]
                continue
            if k == "header" and _kind(node) == "object":
                hreq = set(node.get("required", []))
                for hk, hraw in (node.get("properties") or {}).items():
                    header_keys[hk] = _header_key(ctx, hk, hraw, f"{p}/properties/{hk}")
                    if hk in hreq:
                        header_required.append(hk)
                continue
            if _kind(node) == "array" and _is_record_array(ctx, raw, p):
                continue
            header_keys[k] = _header_key(ctx, k, raw, p)
            if k in root.get("required", []):
                header_required.append(k)
        rkey = records_key or meta.get("records_key") or rkey
    else:
        record, base = root, "#"
        rkey = records_key or meta.get("records_key") or "records"
    if _kind(record) != "object" or not isinstance(record.get("properties"), dict):
        raise _fail(f"{base}: records must be objects with properties")
    required = set(record.get("required", []))
    core: List[Dict[str, Any]] = []
    extensions: List[Dict[str, Any]] = []
    for pname, raw in record["properties"].items():
        f = _field(ctx, pname, raw, pname in required, f"{base}/properties/{pname}")
        if f is None:
            continue
        (core if pname in required else extensions).append(f)
        if pname not in required:
            f.pop("optional", None)
    prefix = prefix or meta.get("prefix")
    if not prefix:
        raise _fail("a prefix is required (pass prefix=...)")
    if not core:
        raise _fail(f"{base}: at least one required property is needed to form the contract core")
    d: Dict[str, Any] = {
        "prefix": prefix,
        "version": meta.get("version", 1),
        "name": name if name is not None else (root.get("title") or ""),
        "description": root.get("description", ""),
        "parent": meta.get("parent"),
        "domain": meta.get("domain", ""),
        "list_separator": meta.get("list_separator", ","),
        "records_key": rkey,
        "header": {"required": sorted(set(header_required) | {"n"}), "keys": header_keys},
        "core": core,
        "extensions": extensions,
    }
    for k in ("author", "license", "source"):
        if k in meta:
            d[k] = meta[k]
    if "header_order" in meta:
        d["header"]["keys"] = {k: header_keys[k] for k in meta["header_order"] if k in header_keys}
        d["header"]["keys"].update({k: v for k, v in header_keys.items() if k not in d["header"]["keys"]})
    return Contract.from_dict(d)


# ----------------------------------------------------------------- export
def _nullable(s: Dict[str, Any]) -> Dict[str, Any]:
    t = s.get("type")
    if isinstance(t, str):
        s["type"] = [t, "null"]
    if "enum" in s:
        s["enum"] = list(s["enum"]) + [None]
    return s


def _scalar_schema(ftype: str, values: Optional[List[str]], lo: Any = None, hi: Any = None) -> Dict[str, Any]:
    s: Dict[str, Any] = {"type": _JSON_OF[ftype]}
    if ftype == "enum":
        s["enum"] = list(values or [])
    if ftype in ("int", "float"):
        if lo is not None:
            s["minimum"] = lo
        if hi is not None:
            s["maximum"] = hi
    elif ftype in ("date", "decimal"):
        ann: Dict[str, Any] = {"type": ftype}
        if ftype == "date":
            s["format"] = "date"
        else:
            s["pattern"] = _DECIMAL_PATTERN
        if lo is not None:
            ann["min"] = lo
        if hi is not None:
            ann["max"] = hi
        s[X] = ann
    return s


def _field_schemas(f: Any, sep_optional: bool) -> List[Tuple[str, Dict[str, Any]]]:
    """Property schemas of one field (two for a marked list)."""
    ann: Dict[str, Any] = {}
    if f.unique:
        ann["unique"] = True
    if f.type in ("list", "mlist"):
        s: Dict[str, Any] = {"type": "array", "items": _scalar_schema(f.item, f.item_values)}
        if f.min is not None:
            s["minItems"] = f.min
        if f.max is not None:
            s["maxItems"] = f.max
        if f.count_key:
            ann["count_key"] = f.count_key
    elif f.type == "tuple":
        s = {"type": "object", "properties": {}, "required": [], "additionalProperties": False}
        for c in f.items:
            cs = _scalar_schema(c.type, c.values, c.min, c.max)
            if c.optional:
                _nullable(cs)
            else:
                s["required"].append(c.name)
            if c.desc:
                cs["description"] = c.desc
            if c.default is not None:
                cs["default"] = c.default
            s["properties"][c.name] = cs
    else:
        s = _scalar_schema(f.type, f.values, f.min, f.max)
    if f.optional or sep_optional:
        _nullable(s)
    if f.desc:
        s["description"] = f.desc
    if f.default is not None:
        s["default"] = f.default
    if f.type != "mlist":
        if ann:
            s[X] = dict(s.get(X) or {}, **ann)
        return [(f.name, s)]
    ann.update({"type": "mlist", "marker": f.marker, "selected": f.json_selected})
    if f.name != f.json_items:
        ann["field"] = f.name
    s[X] = ann
    if f.marker in ("exactly_one", "at_most_one"):
        sel: Dict[str, Any] = {"type": "integer", "minimum": 0}
        if f.marker == "at_most_one" or f.optional or sep_optional:
            sel["type"] = ["integer", "null"]
    else:
        sel = {"type": "array", "items": {"type": "integer", "minimum": 0}}
        if f.optional or sep_optional:
            sel["type"] = ["array", "null"]
    sel["description"] = f"index of the selected element(s) of '{f.json_items}'"
    sel[X] = {"selected_of": f.name}
    return [(f.json_items, s), (f.json_selected, sel)]


def to_json_schema(contract: Contract, record_only: bool = False) -> Dict[str, Any]:
    """Describe the canonical object of ``contract`` as a JSON Schema (2020-12).

    With ``record_only=True`` only one record is described.  ``x-mini``
    annotations keep the contract information that JSON Schema lacks.
    """
    c = contract
    props: Dict[str, Any] = {}
    required: List[str] = []
    for f in c.core:
        for key, s in _field_schemas(f, False):
            props[key] = s
            required.append(key)
    for f in c.extensions:
        for key, s in _field_schemas(f, True):
            props[key] = s
    record = {"type": "object", "properties": props, "required": required, "additionalProperties": False}
    meta: Dict[str, Any] = {"prefix": c.prefix, "version": c.version, "records_key": c.records_key,
                            "list_separator": c.list_separator}
    for k in ("parent", "domain", "author", "license", "source"):
        v = getattr(c, k)
        if v:
            meta[k] = v
    if record_only:
        out = {"$schema": SCHEMA_DIALECT, "title": c.name or c.prefix}
        if c.description:
            out["description"] = c.description
        out.update(record)
        out[X] = meta
        return out
    hprops: Dict[str, Any] = {}
    hreq: List[str] = []
    for k, hk in c.header_keys.items():
        f = hk.as_field()
        f.optional = False
        if hk.type == "list":
            f.item_values = hk.values
            f.values = None
        f.desc = hk.desc
        s = _field_schemas(f, False)[0][1]
        if not hk.required:
            _nullable(s)
        else:
            hreq.append(k)
        hprops[k] = s
    meta["header_order"] = list(c.header_keys)
    out = {"$schema": SCHEMA_DIALECT, "title": c.name or c.prefix}
    if c.description:
        out["description"] = c.description
    out.update({
        "type": "object",
        "properties": {
            "prefix": {"const": c.prefix},
            "header": {"type": "object", "properties": hprops, "required": hreq},
            c.records_key: {"type": "array", "items": record},
        },
        "required": ["prefix", "header", c.records_key],
        X: meta,
    })
    return out


def from_pydantic(model: Any, prefix: str, **options: Any) -> Contract:
    """Build a contract from a Pydantic model class (v2 ``model_json_schema``, v1 ``schema``).

    Pydantic is not a dependency of ``minifmt``: the model is only asked for
    its JSON Schema.  Options are those of :func:`from_json_schema`.
    """
    if hasattr(model, "model_json_schema"):
        schema = model.model_json_schema()
    elif hasattr(model, "schema"):
        schema = model.schema()
    else:
        raise TypeError("expected a Pydantic model class")
    return from_json_schema(copy.deepcopy(schema), prefix, **options)
