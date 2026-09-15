"""Deterministic simulated adapter for testing experiment harnesses offline.

It never touches the network.  Given the same (seed, model, prompt) it always
returns the same answer.  What to answer is decided by an *oracle*: a callable
``oracle(system, user) -> SimTarget | None`` supplied by the harness, which
knows which reference records a prompt is asking for and in which rendering.
The adapter renders those records and injects plausible generation faults:

* text level: prose before/after the document, code fences, random truncation,
  hard truncation at ``max_tokens``;
* record level: omitted record, content drift, enum drift (not in structured mode);
* rendering level, only when the value contains the triggering character:
  naive pipe lines with unescaped ``|``/newlines and a spurious header row;
  JSON with a raw quote/newline inside a string or a trailing comma;
  .mini with an unescaped ``|``, an unprotected list separator, a single
  backslash, a raw newline, or a wrong ``n``.

The fault rates are *assumptions of the simulator*, not measurements; results
obtained with this adapter validate the harness only.
"""
from __future__ import annotations

import copy
import difflib
import hashlib
import json
import random
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple

from ... import codec
from ...contract import Contract, Field
from ...serializer import encode_field, encode_header, encode_record
from ...values import format_number
from .base import Adapter, AdapterError, result

DEFAULT_PROFILE: Dict[str, float] = {
    # text level
    "prose_before": 0.08, "prose_after": 0.05, "code_fence": 0.12, "random_truncation": 0.03,
    # record level
    "omit_record": 0.01, "content_drift": 0.01, "enum_drift": 0.03,
    # naive pipe lines (no escaping rule was given to the model)
    "pipe_raw_naive": 0.85, "newline_raw_naive": 0.5, "header_row_naive": 0.10,
    # JSON without structured mode
    "json_raw_quote": 0.06, "json_raw_newline": 0.08, "json_trailing_comma": 0.02,
    # .mini following the specification block
    "mini_pipe_unescaped": 0.08, "mini_sep_unprotected": 0.10, "mini_backslash_single": 0.15,
    "mini_newline_raw": 0.05, "mini_wrong_n": 0.03,
    # selective repair
    "repair_success": 0.85,
}
# multipliers applied to every fault rate (repair failure scales the same way)
PROFILES: Dict[str, float] = {"fuerte": 0.4, "medio": 1.0, "debil": 2.0,
                              "strong": 0.4, "medium": 1.0, "weak": 2.0, "perfecto": 0.0}
UNSCALED = {"pipe_raw_naive", "newline_raw_naive"}  # behaviour when no rule is given, not a failure rate


@dataclass
class SimTarget:
    kind: str                                  # mini | json | json_schema | pipe | repair | text
    contract: Optional[Contract] = None
    records: List[Dict[str, Any]] = field(default_factory=list)
    header: Dict[str, Any] = field(default_factory=dict)
    repair_items: List[Tuple[str, bool]] = field(default_factory=list)   # (line text, is_header)
    repair_context: bool = False               # the repair request carries the source text
    text: str = ""


Oracle = Callable[[str, str], Optional[SimTarget]]


def _count_tokens(text: str) -> int:
    try:
        from ...tokens import count_tokens
        return count_tokens(text)
    except Exception:  # noqa: BLE001 - vocab or regex unavailable
        return max(1, len(text) // 4)


def _truncate_tokens(text: str, n: int) -> str:
    try:
        import tiktoken  # type: ignore
        enc = tiktoken.get_encoding("o200k_base")
        ids = enc.encode(text, disallowed_special=())
        return enc.decode(ids[:n]) if len(ids) > n else text
    except Exception:  # noqa: BLE001
        return text[: n * 4]


def naive_cell(value: Any, f: Field, rec: Dict[str, Any]) -> str:
    """How a hand-written 'fields separated by |' instruction renders a value."""
    def s(v: Any) -> str:
        if v is None:
            return ""
        if isinstance(v, bool):
            return "true" if v else "false"
        if isinstance(v, float):
            return format_number(v)
        return str(v)
    if f.type == "mlist":
        items = rec.get(f.json_items) or []
        sel = rec.get(f.json_selected)
        sels = set(sel if isinstance(sel, list) else ([sel] if sel is not None else []))
        return ",".join(s(x) + ("*" if i in sels else "") for i, x in enumerate(items))
    if f.type == "list":
        return ",".join(s(x) for x in (value or []))
    if f.type == "tuple":
        value = value or {}
        return ",".join(s(value.get(c.name)) for c in f.items)
    return s(value)


class SimulatedAdapter(Adapter):
    provider = "simulado"

    def __init__(self, model: str = "sim", *, oracle: Optional[Oracle] = None, profile: Any = "medio",
                 seed: int = 0, structured: bool = True, **options: Any):
        super().__init__(model, **options)
        self.oracle = oracle
        self.seed = seed
        self.supports_structured = structured
        mult = PROFILES.get(profile, 1.0) if isinstance(profile, str) else 1.0
        rates = dict(DEFAULT_PROFILE)
        if isinstance(profile, dict):
            mult = float(profile.get("multiplier", 1.0))
            rates.update({k: v for k, v in profile.items() if k in DEFAULT_PROFILE})
        for k in rates:
            if k in UNSCALED:
                continue
            if k == "repair_success":
                rates[k] = max(0.0, min(1.0, 1 - (1 - rates[k]) * mult))
            else:
                rates[k] = max(0.0, min(1.0, rates[k] * mult))
        self.rates = rates

    # ------------------------------------------------------------------ api
    def generate(self, system: str, user: str, *, max_tokens: int, temperature: Optional[float],
                 response_format: Optional[Dict[str, Any]] = None, seed: Optional[int] = None) -> Dict[str, Any]:
        self._check_format(response_format)
        h = hashlib.sha256(f"{self.seed}\x00{seed}\x00{self.model}\x00{system}\x00{user}".encode("utf-8")).hexdigest()
        rng = random.Random(int(h[:16], 16))
        target = self.oracle(system, user) if self.oracle else None
        faults: List[str] = []
        structured = response_format is not None
        if target is None:
            text = "OK"
        elif target.kind == "text":
            text = target.text
        elif target.kind == "repair":
            text = self._render_repair(target, rng, faults)
        else:
            recs = self._record_faults(target, rng, faults, structured or target.kind == "json_schema")
            if target.kind == "mini":
                text = self._render_mini(target, recs, rng, faults)
            elif target.kind == "pipe":
                text = self._render_pipe(target, recs, rng, faults)
            elif target.kind in ("json", "json_schema"):
                text = self._render_json(target, recs, rng, faults, structured or target.kind == "json_schema")
            else:
                raise AdapterError(f"unknown simulated target kind {target.kind}")
            if not (structured or target.kind == "json_schema"):
                text = self._text_faults(text, rng, faults)
        stop = "end_turn"
        out_tokens = _count_tokens(text)
        if out_tokens > max_tokens:
            text = _truncate_tokens(text, max_tokens)
            out_tokens = min(max_tokens, _count_tokens(text))
            stop = "max_tokens"
            faults.append("max_tokens")
        in_tokens = _count_tokens(system) + _count_tokens(user) + 8
        latency = 180.0 + 0.02 * in_tokens + 11.0 * out_tokens + rng.uniform(0, 120)
        raw = {"simulado": True, "fallas": faults, "perfil": {k: round(v, 4) for k, v in self.rates.items()}}
        return result(text, in_tokens, out_tokens, latency, raw, stop_reason=stop, model=self.model,
                      provider=self.provider)

    # ------------------------------------------------------------ faults
    def _p(self, name: str, rng: random.Random) -> bool:
        return rng.random() < self.rates.get(name, 0.0)

    def _record_faults(self, t: SimTarget, rng: random.Random, faults: List[str], constrained: bool) -> List[Dict[str, Any]]:
        out = []
        c = t.contract
        for i, rec in enumerate(t.records):
            if self._p("omit_record", rng):
                faults.append(f"omit_record:{i}")
                continue
            r = copy.deepcopy(rec)
            if c is not None and self._p("content_drift", rng):
                strs = [f for f in c.fields[1:] if f.type == "str" and r.get(f.name)]
                if strs:
                    f = rng.choice(strs)
                    words = str(r[f.name]).split(" ")
                    r[f.name] = " ".join(words[:-1]) if len(words) > 1 else str(r[f.name]) + "s"
                    faults.append(f"content_drift:{i}:{f.name}")
            if c is not None and not constrained and self._p("enum_drift", rng):
                enums = [f for f in c.fields if f.type == "enum" and r.get(f.name)]
                if enums:
                    f = rng.choice(enums)
                    v = str(r[f.name])
                    r[f.name] = v.lower() if v.lower() != v else v.upper()
                    faults.append(f"enum_drift:{i}:{f.name}")
            out.append(r)
        return out

    def _text_faults(self, text: str, rng: random.Random, faults: List[str]) -> str:
        if self._p("code_fence", rng):
            text = "```\n" + text + "\n```"
            faults.append("code_fence")
        if self._p("prose_before", rng):
            text = "Aquí tienes el resultado solicitado:\n\n" + text
            faults.append("prose_before")
        if self._p("prose_after", rng):
            text = text + "\n\nSi necesitas otro formato, avísame."
            faults.append("prose_after")
        if self._p("random_truncation", rng) and len(text) > 20:
            cut = int(len(text) * rng.uniform(0.3, 0.95))
            text = text[:cut]
            faults.append(f"random_truncation:{cut}")
        return text

    # --------------------------------------------------------- renderers
    def _render_mini(self, t: SimTarget, recs: List[Dict[str, Any]], rng: random.Random, faults: List[str]) -> str:
        c = t.contract
        assert c is not None
        n = len(recs)
        if self._p("mini_wrong_n", rng):
            n = n + rng.choice([-1, 1])
            faults.append("mini_wrong_n")
        lines = [encode_header(t.header, c, max(0, n))]
        sep = c.list_separator
        for i, rec in enumerate(recs):
            cells = []
            for f in c.fields:
                try:
                    cell = encode_field(rec.get(f.name), f, sep, rec)
                except Exception:  # noqa: BLE001 - drifted value that the serializer rejects
                    cell = codec.escape_scalar(naive_cell(rec.get(f.name), f, rec))
                if "\\|" in cell and self._p("mini_pipe_unescaped", rng):
                    cell = cell.replace("\\|", "|")
                    faults.append(f"mini_pipe_unescaped:{i}:{f.name}")
                if f.type in ("list", "mlist", "tuple") and ("\\" + sep) in cell and self._p("mini_sep_unprotected", rng):
                    cell = cell.replace("\\" + sep, sep)
                    faults.append(f"mini_sep_unprotected:{i}:{f.name}")
                if "\\\\" in cell and self._p("mini_backslash_single", rng):
                    cell = cell.replace("\\\\", "\\")
                    faults.append(f"mini_backslash_single:{i}:{f.name}")
                if "\\n" in cell.replace("\\\\", "") and self._p("mini_newline_raw", rng):
                    cell = cell.replace("\\n", "\n")
                    faults.append(f"mini_newline_raw:{i}:{f.name}")
                cells.append(cell)
            while len(cells) > c.arity and cells[-1] == "":
                cells.pop()
            lines.append("|".join(cells))
        return "\n".join(lines)

    def _render_pipe(self, t: SimTarget, recs: List[Dict[str, Any]], rng: random.Random, faults: List[str]) -> str:
        c = t.contract
        assert c is not None
        lines = []
        if self._p("header_row_naive", rng):
            lines.append("|".join(f.name for f in c.fields))
            faults.append("header_row_naive")
        for i, rec in enumerate(recs):
            cells = []
            for f in c.fields:
                cell = naive_cell(rec.get(f.name), f, rec)
                if "|" in cell and not self._p("pipe_raw_naive", rng):
                    cell = cell.replace("|", "/")
                    faults.append(f"pipe_replaced:{i}:{f.name}")
                if "\n" in cell:
                    if self._p("newline_raw_naive", rng):
                        faults.append(f"newline_raw:{i}:{f.name}")
                    else:
                        cell = cell.replace("\n", " ")
                cells.append(cell)
            lines.append("|".join(cells))
        return "\n".join(lines)

    def _render_json(self, t: SimTarget, recs: List[Dict[str, Any]], rng: random.Random, faults: List[str],
                     constrained: bool) -> str:
        c = t.contract
        key = c.records_key if c is not None else "records"
        text = json.dumps({key: recs}, ensure_ascii=False, indent=None if constrained else 1)
        if constrained:
            return text
        if '\\"' in text and self._p("json_raw_quote", rng):
            text = text.replace('\\"', '"', 1)
            faults.append("json_raw_quote")
        if "\\n" in text and self._p("json_raw_newline", rng):
            text = text.replace("\\n", "\n", 1)
            faults.append("json_raw_newline")
        if self._p("json_trailing_comma", rng) and text.rstrip().endswith("]}"):
            idx = text.rstrip().rfind("}", 0, len(text.rstrip()) - 2)
            if idx > 0:
                text = text[: idx + 1] + "," + text[idx + 1:]
                faults.append("json_trailing_comma")
        return text

    def _render_repair(self, t: SimTarget, rng: random.Random, faults: List[str]) -> str:
        c = t.contract
        assert c is not None
        clean = []
        for rec in t.records:
            try:
                clean.append(encode_record(rec, c))
            except Exception:  # noqa: BLE001
                clean.append("")
        out = [f"{c.prefix}|n={len(t.repair_items)}"]
        for j, (line, is_header) in enumerate(t.repair_items):
            if is_header:
                out.append(encode_header(t.header, c, len(t.records)))
                continue
            if "|" not in line:
                out.append("-")
                faults.append(f"repair_drop:{j}")
                continue
            try:
                n_fields = len(codec.split_fields(line.replace("\n", " "), c.list_separator, 0, strict=False))
            except Exception:  # noqa: BLE001
                n_fields = c.arity
            if n_fields < c.arity and "\n" not in line and not t.repair_context:
                # a truncated record: without the source text the missing values cannot be recovered
                out.append(line)
                faults.append(f"repair_no_information:{j}")
                continue
            scores = [difflib.SequenceMatcher(None, line, cl).ratio() for cl in clean]
            best = max(range(len(clean)), key=lambda k: scores[k]) if clean else None
            if best is not None and self._p("repair_success", rng):
                out.append(clean[best])
                faults.append(f"repair_ok:{j}")
            else:
                out.append(line)
                faults.append(f"repair_failed:{j}")
        return "\n".join(out)
