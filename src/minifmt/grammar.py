"""Compile .mini contracts into constrained-decoding grammars (GBNF, Lark, Regex).

Works with both SPEC 1.1 contracts (``minifmt.Contract``) and learned domain
contracts (``mini-domain/1``, ``mini-domain/2`` dictionaries). Standard library only.
"""
from __future__ import annotations

import re
from typing import Any

from .contract import Contract


def _schema_from_spec(contract: Contract) -> dict[str, Any]:
    fields = []
    for f in contract.fields:
        t = f.type
        if t == "int":
            node: dict[str, Any] = {"type": "integer"}
        elif t in ("float", "decimal"):
            node = {"type": "number"}
        elif t == "bool":
            node = {"type": "boolean"}
        elif t == "enum":
            node = {"type": "string", "enum": list(f.values or ())}
        elif t == "date":
            node = {"type": "string", "pattern": "date"}
        elif t in ("list", "mlist", "tuple"):
            node = {"type": "json"}
        else:
            node = {"type": "string"}
        if f.optional:
            node["nullable"] = True
        fields.append({"name": f.name, "optional": bool(f.optional), "schema": node})
    return {
        "kind": "spec",
        "prefix": contract.prefix,
        "schema_id": None,
        "record_path": [contract.records_key],
        "fields": fields,
    }


def _schema_from_domain(contract: dict[str, Any]) -> dict[str, Any]:
    from .domain import _fields, _row_schema

    row_schema = _row_schema(contract)
    fields = _fields(row_schema)
    return {
        "kind": "domain",
        "prefix": contract["prefix"],
        "schema_id": contract["schema_id"],
        "record_path": contract["record_path"],
        "fields": fields,
    }


def _normalize(contract: Contract | dict[str, Any]) -> dict[str, Any]:
    if isinstance(contract, Contract):
        return _schema_from_spec(contract)
    if isinstance(contract, dict) and "schema" in contract and "prefix" in contract:
        return _schema_from_domain(contract)
    if isinstance(contract, dict) and "prefix" in contract and ("core" in contract or "extensions" in contract):
        return _schema_from_spec(Contract.from_dict(contract))
    raise TypeError("contract must be a minifmt.Contract or domain contract dict")


def _escape_gbnf_lit(text: str) -> str:
    return '"' + text.replace("\\", "\\\\").replace('"', '\\"') + '"'


def _ordered_fields(fields: list[dict[str, Any]], compact_rows: bool, last_text_field: str | None) -> list[dict[str, Any]]:
    if not compact_rows or not last_text_field:
        return fields
    tail = [f for f in fields if f["name"] == last_text_field]
    if not tail:
        raise ValueError(f"last_text_field {last_text_field!r} not found in contract fields")
    return [f for f in fields if f["name"] != last_text_field] + tail


def contract_to_gbnf(
    contract: Contract | dict[str, Any],
    *,
    compact_rows: bool = False,
    last_text_field: str | None = None,
    expected_records: int | None = None,
    delimiter: str = "|",
) -> str:
    """Compile a contract into a llama.cpp GBNF grammar for guaranteed-valid .mini output."""
    info = _normalize(contract)
    fields = _ordered_fields(info["fields"], compact_rows, last_text_field)
    sep = " " if compact_rows else delimiter
    if sep not in ("|", " ", ",", "\t"):
        raise ValueError(f"unsupported grammar delimiter: {delimiter!r}")
    sep_lit = _escape_gbnf_lit(sep)
    rules: list[str] = []

    if compact_rows:
        if expected_records is not None:
            rep = " ".join(["row"] * expected_records)
            rules.append(f"root ::= {rep}" if rep else 'root ::= ""')
        else:
            rules.append('root ::= row ("\\n" row)* "\\n"?')
        # Add newline separation for fixed counts cleanly
        if expected_records is not None:
            if expected_records <= 0:
                rules[-1] = 'root ::= ""'
            else:
                joined = ' "\\n" '.join(["row"] * expected_records)
                rules[-1] = f'root ::= {joined} "\\n"?'
    else:
        hdr = f'{_escape_gbnf_lit(info["prefix"])} "|"'
        if info["kind"] == "domain":
            count_rule = f'"{expected_records}"' if expected_records is not None else "uint"
            hdr += f' "v=1|n=" {count_rule} "|h=" {_escape_gbnf_lit(info["schema_id"])}'
            if info["record_path"]:
                hdr += ' "|m=" jval'
        else:
            count_rule = f'"{expected_records}"' if expected_records is not None else "uint"
            hdr += f' "n=" {count_rule} ("|" hpair)*'
        rules.append(f'header ::= {hdr}')
        if expected_records is not None and expected_records > 0:
            rows_expr = ' ("\\n" row)' * expected_records if False else " ".join(['"\\n" row'] * expected_records)
            rules.append(f'root ::= header {rows_expr} "\\n"?')
        elif expected_records == 0:
            rules.append('root ::= header "\\n"?')
        else:
            rules.append('root ::= header ("\\n" row)* "\\n"?')

    field_rules: list[str] = []
    for idx, field in enumerate(fields):
        rname = f"col{idx}"
        node = field["schema"]
        ftype = node["type"]
        is_tail = compact_rows and idx == len(fields) - 1
        if "enum" in node and node["enum"]:
            alts = " | ".join(_escape_gbnf_lit(v) for v in sorted(node["enum"], key=lambda s: (-len(s), s)))
            core = f"({alts})"
        elif node.get("pattern") == "date":
            core = "datev"
        elif ftype == "integer":
            core = "intv"
        elif ftype == "number":
            core = "numv"
        elif ftype == "boolean":
            core = "boolv"
        elif ftype == "string":
            if is_tail:
                core = "tailstr"
            elif sep == " ":
                core = '(bare-nosp | jstr)'
            elif sep == ",":
                core = '(bare-nocm | jstr)'
            elif sep == "\t":
                core = '(bare-notb | jstr)'
            else:
                core = '(bare-nopi | jstr)'
        else:
            core = "jval"
        if node.get("nullable"):
            core = f'("~" | {core})'
        if field.get("optional"):
            core = f'("" | {core})' if info["kind"] == "spec" else f'("?" | {core})'
        rules.append(f"{rname} ::= {core}")
        field_rules.append(rname)

    rules.append(f"row ::= {f' {sep_lit} '.join(field_rules)}" if field_rules else 'row ::= "-"')
    rules.extend([
        'hpair ::= [a-z_]+ "=" [^|\\r\\n]+',
        'uint ::= "0" | [1-9] [0-9]*',
        'intv ::= "-"? uint',
        'numv ::= "-"? uint ("." [0-9]+)? ([eE] [+-]? [0-9]+)?',
        'boolv ::= "true" | "false"',
        'datev ::= [0-9] [0-9] [0-9] [0-9] "-" [0-9] [0-9] "-" [0-9] [0-9]',
        'bare-nopi ::= ([^\\\\|\\r\\n"?~] | "\\\\" [\\\\|nr]) ([^\\\\|\\r\\n] | "\\\\" [\\\\|nr])*',
        'bare-nosp ::= ([^\\\\ \\t\\r\\n"?~] | "\\\\" [\\\\snr]) ([^\\\\ \\t\\r\\n] | "\\\\" [\\\\snr])*',
        'bare-nocm ::= ([^\\\\,\\r\\n"?~] | "\\\\" [\\\\,nr]) ([^\\\\,\\r\\n] | "\\\\" [\\\\,nr])*',
        'bare-notb ::= ([^\\\\\\t\\r\\n"?~] | "\\\\" [\\\\tnr]) ([^\\\\\\t\\r\\n] | "\\\\" [\\\\tnr])*',
        'tailstr ::= ([^\\r\\n" ] [^\\r\\n]* | jstr)',
        'jstr ::= "\\"" ([^"\\\\\\r\\n] | "\\\\" ["\\\\/bfnrt] | "\\\\u" [0-9a-fA-F]{4})* "\\""',
        'jval ::= jstr | numv | boolv | "null" | jarr | jobj',
        'jarr ::= "[" ws (jval ("," ws jval)*)? ws "]"',
        'jobj ::= "{" ws (jstr ":" ws jval ("," ws jstr ":" ws jval)*)? ws "}"',
        'ws ::= [ ]*',
    ])
    return "\n".join(rules) + "\n"


def contract_to_lark(
    contract: Contract | dict[str, Any],
    *,
    compact_rows: bool = False,
    last_text_field: str | None = None,
    expected_records: int | None = None,
    delimiter: str = "|",
) -> str:
    """Compile a contract into a standalone Lark grammar for vLLM / XGrammar / Outlines."""
    info = _normalize(contract)
    fields = _ordered_fields(info["fields"], compact_rows, last_text_field)
    sep = " " if compact_rows else delimiter
    if sep not in ("|", " ", ",", "\t"):
        raise ValueError(f"unsupported grammar delimiter: {delimiter!r}")
    sep_lit = _escape_gbnf_lit(sep)
    rules: list[str] = []

    if compact_rows:
        if expected_records is not None and expected_records > 0:
            rules.append("start: " + ' "\\n" '.join(["row"] * expected_records) + ' "\\n"?')
        elif expected_records == 0:
            rules.append('start: ""')
        else:
            rules.append('start: row ("\\n" row)* "\\n"?')
    else:
        hdr = f'{_escape_gbnf_lit(info["prefix"])} "|"'
        count_rule = _escape_gbnf_lit(str(expected_records)) if expected_records is not None else "UINT"
        if info["kind"] == "domain":
            hdr += f' "v=1|n=" {count_rule} "|h=" {_escape_gbnf_lit(info["schema_id"])}'
            if info["record_path"]:
                hdr += ' "|m=" jval'
        else:
            hdr += f' "n=" {count_rule} ("|" HPAIR)*'
        rules.append(f"header: {hdr}")
        if expected_records is not None and expected_records > 0:
            rules.append("start: header " + " ".join(['"\\n" row'] * expected_records) + ' "\\n"?')
        elif expected_records == 0:
            rules.append('start: header "\\n"?')
        else:
            rules.append('start: header ("\\n" row)* "\\n"?')

    field_rules: list[str] = []
    for idx, field in enumerate(fields):
        rname = f"col_{idx}"
        node = field["schema"]
        ftype = node["type"]
        is_tail = compact_rows and idx == len(fields) - 1
        if "enum" in node and node["enum"]:
            alts = " | ".join(_escape_gbnf_lit(v) for v in sorted(node["enum"], key=lambda s: (-len(s), s)))
            core = f"({alts})"
        elif node.get("pattern") == "date":
            core = "DATEV"
        elif ftype == "integer":
            core = "INTV"
        elif ftype == "number":
            core = "NUMV"
        elif ftype == "boolean":
            core = "BOOLV"
        elif ftype == "string":
            if is_tail:
                core = "(TAILSTR | JSTR)"
            elif sep == " ":
                core = "(BARE_NOSP | JSTR)"
            elif sep == ",":
                core = "(BARE_NOCM | JSTR)"
            elif sep == "\t":
                core = "(BARE_NOTB | JSTR)"
            else:
                core = "(BARE_NOPI | JSTR)"
        else:
            core = "jval"
        if node.get("nullable"):
            core = f'("~" | {core})'
        if field.get("optional"):
            core = f'("" | {core})' if info["kind"] == "spec" else f'("?" | {core})'
        rules.append(f"{rname}: {core}")
        field_rules.append(rname)

    rules.append(f"row: {f' {sep_lit} '.join(field_rules)}" if field_rules else 'row: "-"')
    rules.extend([
        "jval: JSTR | NUMV | BOOLV | \"null\" | jarr | jobj",
        'jarr: "[" (jval ("," jval)*)? "]"',
        'jobj: "{" (JSTR ":" jval ("," JSTR ":" jval)*)? "}"',
        r'HPAIR: /[a-z_]+=[^|\r\n]+/',
        r'UINT: /0|[1-9][0-9]*/',
        r'INTV: /-?(?:0|[1-9][0-9]*)/',
        r'NUMV: /-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?(?:[eE][+-]?[0-9]+)?/',
        'BOOLV: "true" | "false"',
        r'DATEV: /[0-9]{4}-[0-9]{2}-[0-9]{2}/',
        r'BARE_NOPI: /(?:[^\\|\r\n"?~]|\\[\\|nr])(?:[^\\|\r\n]|\\[\\|nr])*/',
        r'BARE_NOSP: /(?:[^\\ \t\r\n"?~]|\\[\\snr])(?:[^\\ \t\r\n]|\\[\\snr])*/',
        r'BARE_NOCM: /(?:[^\\,\r\n"?~]|\\[\\,nr])(?:[^\\,\r\n]|\\[\\,nr])*/',
        r'BARE_NOTB: /(?:[^\\\t\r\n"?~]|\\[\\tnr])(?:[^\\\t\r\n]|\\[\\tnr])*/',
        r'TAILSTR: /[^"\r\n ][^\r\n]*/',
        r'JSTR: /"(?:[^"\\\r\n]|\\["\\/bfnrt]|\\u[0-9a-fA-F]{4})*"/',
    ])
    return "\n".join(rules) + "\n"


def _field_regex(field: dict[str, Any], sep: str, is_tail: bool, kind: str = "domain") -> str:
    node = field["schema"]
    ftype = node["type"]
    jstr = r'"(?:[^"\\\r\n]|\\["\\/bfnrt]|\\u[0-9a-fA-F]{4})*"'
    if "enum" in node and node["enum"]:
        alts = "|".join(re.escape(v) for v in sorted(node["enum"], key=lambda s: (-len(s), s)))
        core = f"(?:{alts})"
    elif node.get("pattern") == "date":
        core = r"[0-9]{4}-[0-9]{2}-[0-9]{2}"
    elif ftype == "integer":
        core = r"-?(?:0|[1-9][0-9]*)"
    elif ftype == "number":
        core = r"-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?(?:[eE][+-]?[0-9]+)?"
    elif ftype == "boolean":
        core = r"(?:true|false)"
    elif ftype == "string":
        if is_tail:
            core = rf'(?:[^"\r\n ][^\r\n]*|{jstr})'
        elif sep == " ":
            core = rf'(?:(?:[^\\ \t\r\n"?~]|\\[\\snr])(?:[^\\ \t\r\n]|\\[\\snr])*|{jstr})'
        elif sep == ",":
            core = rf'(?:(?:[^\\,\r\n"?~]|\\[\\,nr])(?:[^\\,\r\n]|\\[\\,nr])*|{jstr})'
        elif sep == "\t":
            core = rf'(?:(?:[^\\\t\r\n"?~]|\\[\\tnr])(?:[^\\\t\r\n]|\\[\\tnr])*|{jstr})'
        else:
            core = rf'(?:(?:[^\\|\r\n"?~]|\\[\\|nr])(?:[^\\|\r\n]|\\[\\|nr])*|{jstr})'
    else:
        core = r"[^\r\n|]+" if sep == "|" else rf'(?:{jstr}|\[[^\r\n]*\]|\{{[^\r\n]*\}}|[^\\{re.escape(sep)}\r\n]+)'
    if node.get("nullable") and kind != "spec":
        core = rf"(?:~|{core})"
    if field.get("optional"):
        core = rf"(?:{core})?" if kind == "spec" else rf"(?:\?|{core})"
    return core


def contract_to_regex(
    contract: Contract | dict[str, Any],
    *,
    compact_rows: bool = False,
    last_text_field: str | None = None,
    expected_records: int | None = None,
    delimiter: str = "|",
) -> str:
    """Compile a flat or record-based contract into a single constrained-decoding regex."""
    info = _normalize(contract)
    fields = _ordered_fields(info["fields"], compact_rows, last_text_field)
    sep = " " if compact_rows else delimiter
    if sep not in ("|", " ", ",", "\t"):
        raise ValueError(f"unsupported grammar delimiter: {delimiter!r}")
    row_pat = re.escape(sep).join(_field_regex(f, sep, compact_rows and idx == len(fields) - 1, kind=info["kind"])
                                   for idx, f in enumerate(fields)) if fields else "-"
    if compact_rows:
        if expected_records is not None:
            if expected_records <= 0:
                return r"\Z"
            return row_pat + (rf"\n{row_pat}" * (expected_records - 1)) + r"\n?"
        return rf"{row_pat}(?:\n{row_pat})*\n?"
    prefix = re.escape(info["prefix"])
    cnt = str(expected_records) if expected_records is not None else r"(?:0|[1-9][0-9]*)"
    if info["kind"] == "domain":
        hdr = rf"{prefix}\|v=1\|n={cnt}\|h={re.escape(info['schema_id'])}"
        if info["record_path"]:
            hdr += r"\|m=[^\r\n|]+"
    else:
        hdr = rf"{prefix}\|n={cnt}(?:\|[a-z_]+=[^\r\n|]+)*"
    if expected_records is not None:
        return hdr + (rf"\n{row_pat}" * expected_records) + r"\n?"
    return rf"{hdr}(?:\n{row_pat})*\n?"
