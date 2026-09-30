"""Selective repair of generated .mini documents.

A lenient parse of a model output separates the valid records from the
invalid lines.  Instead of asking the model to regenerate the whole document
(which re-spends every output token and may break lines that were already
correct), :func:`repair_request` builds a request that carries *only* the
invalid lines and the validator errors attached to them.  The model answers
with a small .mini document holding one corrected line per invalid line, in
the same order; :func:`merge_repair` validates each corrected line against the
contract (with the original header, so count keys still apply) and splices it
back into the original document.

Conventions of the repair answer
--------------------------------
* first significant line: ``<prefix>|n=<k>`` where ``k`` is the number of
  corrected lines;
* then exactly ``k`` lines, one per requested line, in the requested order;
* a line containing only ``-`` means "this line was not a record; drop it";
* when the header itself was requested, its correction is a full header line
  (``<prefix>|n=...|...``) in the corresponding position.

The header ``n`` of the original document is never rewritten by the merge: if
records were lost (for instance by truncation) the count mismatch (E04) stays
visible to the caller.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from ..contract import Contract
from ..errors import (E_HEADER_KEY, E_NO_COUNT, E_NO_HEADER, E_UNKNOWN_PREFIX,
                      MiniError, MiniValidationError)
from ..parser import Document, _hashable, _physical_lines, parse
from ..prompt import spec_block

HEADER_CODES = {E_NO_HEADER, E_UNKNOWN_PREFIX, E_NO_COUNT, E_HEADER_KEY}
DROP_MARK = "-"
_FENCE = re.compile(r"^\s*(```|~~~)")


# --------------------------------------------------------------------------
# Locating the document inside a model answer
# --------------------------------------------------------------------------
def extract_document(text: str, contract: Contract) -> str:
    """Return the .mini document embedded in a model answer.

    Removes leading prose and code fences: the document starts at the first
    line that begins with ``<prefix>|`` (or equals the bare prefix).  If the
    header was inside a fenced block, the text after the closing fence is
    dropped as well.  Trailing prose without a fence is kept, so that it is
    reported as invalid lines instead of being silently discarded.  When no
    header line is found, the text is returned without fences.
    """
    if text is None:
        return ""
    lines = text.replace("\r\n", "\n").split("\n")
    pref = contract.prefix
    start = None
    for i, ln in enumerate(lines):
        s = ln.strip().lstrip("﻿")
        if s == pref or s.startswith(pref + "|"):
            start = i
            break
    if start is None:
        return "\n".join(ln for ln in lines if not _FENCE.match(ln)).strip("\n")
    in_fence = any(_FENCE.match(ln) for ln in lines[:start])
    body = lines[start:]
    if in_fence:
        for j, ln in enumerate(body):
            if _FENCE.match(ln):
                body = body[:j]
                break
    else:
        body = [ln for ln in body if not _FENCE.match(ln)]
    return "\n".join(body).strip("\n")


def lenient_parse(text: str, contract: Contract) -> Tuple[Optional[Document], List[MiniError]]:
    """parse(strict=False) that never raises; returns (document|None, errors)."""
    try:
        doc = parse(text, contract, strict=False)
        return doc, list(doc.errors)
    except MiniValidationError as e:
        return None, list(e.errors)
    except MiniError as e:  # pragma: no cover - defensive
        return None, [e]


# --------------------------------------------------------------------------
# Request
# --------------------------------------------------------------------------
@dataclass
class RepairItem:
    line: int                 # 1-based physical line in the extracted document (first line of the item)
    text: str                 # original content (fragments of one record are joined with a real newline)
    errors: List[MiniError]
    is_header: bool = False
    lines: List[int] = field(default_factory=list)   # every physical line covered by the item

    def __post_init__(self) -> None:
        if not self.lines:
            self.lines = [self.line]


@dataclass
class RepairRequest:
    system: str
    user: str
    items: List[RepairItem]
    document: str             # extracted original document the line numbers refer to
    prefix: str
    max_tokens_hint: int = 256

    @property
    def needed(self) -> bool:
        return bool(self.items)

    @property
    def lines(self) -> List[int]:
        return [ln for it in self.items for ln in it.lines]


def invalid_items(document: str, contract: Contract) -> List[RepairItem]:
    """Invalid physical lines of an (extracted) document, with their errors."""
    phys = _physical_lines(document)
    if not phys:
        return []
    by_line: Dict[int, List[MiniError]] = {}
    _, errors = lenient_parse(document, contract)
    for e in errors:
        if e.line > 0:
            by_line.setdefault(e.line, []).append(e)
    header_line = phys[0][0]
    items: List[RepairItem] = []
    prev_idx = -2
    for idx, (lineno, text) in enumerate(phys):
        if lineno not in by_line:
            continue
        item = RepairItem(line=lineno, text=text, errors=by_line[lineno], is_header=(lineno == header_line))
        # a raw line break inside a value splits one record into short fragments
        if items and prev_idx == idx - 1 and not item.is_header and not items[-1].is_header:
            last = items[-1]
            n_last, n_this = _field_count(last.text, contract), _field_count(text, contract)
            if (n_last is not None and n_this is not None and n_last < contract.arity and n_this < contract.arity
                    and contract.arity <= n_last + n_this - 1 <= len(contract.fields)):
                last.text = last.text + "\n" + text
                last.errors.extend(item.errors)
                last.lines.append(lineno)
                prev_idx = idx
                continue
        items.append(item)
        prev_idx = idx
    return items


def _field_count(text: str, contract: Contract) -> Optional[int]:
    from .. import codec
    try:
        return len(codec.split_fields(text.replace("\n", " "), contract.list_separator, 0, strict=False))
    except MiniError:
        return None


def _fmt_error(e: MiniError) -> str:
    fld = f" [{e.field}]" if e.field else ""
    return f"{e.code}{fld}: {e.message}"


def repair_request(document: str, contract: Contract, lang: str = "es", *,
                   context: Optional[str] = None, include_spec: bool = True,
                   max_items: Optional[int] = None) -> RepairRequest:
    """Build the selective repair request for a generated document.

    ``document`` may be the raw model answer; it is passed through
    :func:`extract_document` first and line numbers refer to that result.
    ``context`` (optional) is the source text the document was extracted
    from; without it the request contains only the invalid lines and their
    errors.  ``include_spec`` prepends the contract's specification block to
    the system message (stable across requests, therefore cacheable).
    """
    doc_text = extract_document(document, contract)
    items = invalid_items(doc_text, contract)
    if max_items is not None:
        items = items[:max_items]
    phys = _physical_lines(doc_text)
    header_text = phys[0][1] if phys else f"{contract.prefix}|n=0"
    es = lang == "es"
    spec = spec_block(contract, lang) if include_spec else ""
    if es:
        sys_msg = ("Eres un corrector de documentos .mini. Corriges únicamente las líneas que se te "
                   "indican, conservando su contenido y respetando el formato.")
    else:
        sys_msg = ("You repair .mini documents. You fix only the lines you are given, keeping their "
                   "content and following the format.")
    if spec:
        sys_msg += "\n\n" + spec
    L: List[str] = []
    k = len(items)
    if es:
        L.append(f"Un documento .mini de la familia '{contract.prefix}' tiene {k} línea(s) inválida(s). "
                 "Corrige SOLO esas líneas.")
        L.append(f"Cabecera del documento (contexto): {header_text}")
        L.append("Líneas inválidas (número de línea, contenido y errores del validador):")
    else:
        L.append(f"A .mini document of family '{contract.prefix}' has {k} invalid line(s). "
                 "Fix ONLY those lines.")
        L.append(f"Document header (context): {header_text}")
        L.append("Invalid lines (line number, content and validator errors):")
    for it in items:
        tag = (" cabecera" if es else " header") if it.is_header else ""
        if len(it.lines) > 1:
            L.append(f"[L{it.lines[0]}-L{it.lines[-1]}] " + ("(fragmentos de un mismo registro partido por un salto de "
                     "línea sin escapar; devuelve UNA sola línea)" if es else
                     "(fragments of one record split by an unescaped line break; return ONE line)"))
            for ln, frag in zip(it.lines, it.text.split("\n")):
                L.append(f"    L{ln}: {frag}")
        else:
            L.append(f"[L{it.line}{tag}] {it.text}")
        for e in it.errors:
            L.append(f"    - {_fmt_error(e)}")
    if context:
        L.append("")
        L.append("Texto de origen (para recuperar valores):" if es else "Source text (to recover values):")
        L.append(context)
    L.append("")
    if es:
        L.append(f"Responde solo con un documento .mini: primera línea '{contract.prefix}|n={k}', seguida de "
                 f"exactamente {k} línea(s), una corrección por cada línea inválida y en el mismo orden. "
                 "Si una línea corregida es la cabecera, escribe la cabecera completa. Si una línea no es un "
                 f"registro (texto explicativo), escribe solo '{DROP_MARK}'. No repitas las líneas válidas ni "
                 "añadas explicaciones ni bloques de código.")
    else:
        L.append(f"Answer with a .mini document only: first line '{contract.prefix}|n={k}', followed by exactly "
                 f"{k} line(s), one correction per invalid line, in the same order. If a corrected line is the "
                 f"header, write the full header. If a line is not a record (explanatory text), write only "
                 f"'{DROP_MARK}'. Do not repeat valid lines, add explanations or code fences.")
    chars = sum(len(it.text) for it in items)
    hint = max(64, int(chars / 2.5) + 16 * (k + 1))
    return RepairRequest(system=sys_msg, user="\n".join(L), items=items, document=doc_text,
                         prefix=contract.prefix, max_tokens_hint=hint)


# --------------------------------------------------------------------------
# Merge
# --------------------------------------------------------------------------
@dataclass
class MergeResult:
    text: str                                   # merged document
    document: Optional[Document]                # lenient parse of the merged document
    errors: List[MiniError]                     # errors remaining after the merge
    replaced: List[int] = field(default_factory=list)    # lines replaced by a valid correction
    dropped: List[int] = field(default_factory=list)     # lines removed on request ('-')
    unresolved: List[int] = field(default_factory=list)  # requested lines still invalid
    notes: List[str] = field(default_factory=list)       # problems with the repair answer itself

    @property
    def ok(self) -> bool:
        return self.document is not None and not self.errors


def _answer_lines(repaired_text: str, contract: Contract) -> Tuple[List[str], List[str]]:
    notes: List[str] = []
    body = extract_document(repaired_text or "", contract)
    phys = _physical_lines(body)
    if not phys:
        return [], ["empty repair answer"]
    first = phys[0][1].strip()
    if first == contract.prefix or first.startswith(contract.prefix + "|"):
        lines = [t for _, t in phys[1:]]
        m = re.search(r"\|\s*n\s*=\s*(\d+)", first)
        if m and int(m.group(1)) != len(lines):
            notes.append(f"repair header declares n={m.group(1)} but has {len(lines)} lines")
    else:
        notes.append("repair answer has no header; lines taken in order")
        lines = [t for _, t in phys]
    return lines, notes


def merge_repair(original_doc: str, repaired_text: str, contract: Contract,
                 request: Optional[RepairRequest] = None) -> MergeResult:
    """Splice the corrected lines of a repair answer into the original document.

    Each corrected line is accepted only if it is valid on its own under the
    contract (validated with the original header, or with the corrected header
    when the header was part of the request).  Rejected corrections leave the
    original line in place, so the merged document never loses information
    that the lenient parser would have reported.
    """
    doc_text = request.document if request is not None else extract_document(original_doc, contract)
    items = request.items if request is not None else invalid_items(doc_text, contract)
    phys = _physical_lines(doc_text)
    answer, notes = _answer_lines(repaired_text, contract)
    if len(answer) != len(items):
        notes.append(f"expected {len(items)} corrected lines, got {len(answer)}")
    content: Dict[int, str] = {ln: t for ln, t in phys}
    order = [ln for ln, _ in phys]
    header_line = order[0] if order else None
    replaced, dropped, unresolved = [], [], []

    # header first, so that record corrections are validated against it
    pairs = list(zip(items, answer))
    for it, new in pairs:
        if it.is_header:
            cand = new.strip()
            if cand.startswith(contract.prefix + "|") or cand == contract.prefix:
                probe, errs = lenient_parse(cand, contract)
                if probe is not None and not [e for e in errs if e.code in HEADER_CODES]:
                    content[it.line] = cand
                    replaced.append(it.line)
                    continue
            unresolved.append(it.line)
    header_text = content.get(header_line, f"{contract.prefix}|n=0") if header_line is not None else f"{contract.prefix}|n=0"
    invalid_lines = {ln for it in items for ln in it.lines}
    seen = {content[ln].strip() for ln in order if ln not in invalid_lines and ln != header_line}
    # values of the `unique` fields already owned by the records that stay in the document: a
    # correction may not claim one of them (it would turn a valid record into an E11 duplicate)
    unique_names = [f.name for f in contract.fields if f.unique]
    claimed: Dict[str, set] = {name: set() for name in unique_names}
    if unique_names:
        kept = [content[ln] for ln in order if ln not in invalid_lines and ln != header_line]
        kept_doc, _ = lenient_parse("\n".join([header_text] + kept), contract)
        for rec in (kept_doc.records if kept_doc is not None else []):
            for name in unique_names:
                if rec.get(name) is not None:
                    claimed[name].add(_hashable(rec[name]))
    for it, new in pairs:
        if it.is_header:
            continue
        cand = new.strip()
        if cand == DROP_MARK:
            dropped.extend(it.lines)
            for ln in it.lines:
                content.pop(ln, None)
            continue
        if cand in seen:
            # the same record was returned twice (or already exists): keep a single copy
            notes.append(f"line {it.line}: correction duplicates another record; dropped")
            dropped.extend(it.lines)
            for ln in it.lines:
                content.pop(ln, None)
            continue
        probe, errs = lenient_parse(header_text + "\n" + cand, contract)
        line_errs = [e for e in errs if e.line > 1 or (e.line == 0 and e.code != "E04")]
        # the probe document has n from the original header: ignore the count
        if probe is not None and len(probe.records) == 1 and not line_errs and "\n" not in cand:
            clash = next((name for name in unique_names
                          if probe.records[0].get(name) is not None
                          and _hashable(probe.records[0][name]) in claimed[name]), None)
            if clash is not None:
                # SPEC §6: a `unique` value must not repeat; keep the original line instead of
                # damaging another valid record
                notes.append(f"line {it.line}: correction repeats the unique value of field '{clash}' of another record")
                unresolved.extend(it.lines)
                continue
            content[it.line] = cand
            for ln in it.lines[1:]:
                content.pop(ln, None)
            replaced.extend(it.lines)
            seen.add(cand)
            for name in unique_names:
                if probe.records[0].get(name) is not None:
                    claimed[name].add(_hashable(probe.records[0][name]))
        else:
            unresolved.extend(it.lines)
    for it in items[len(answer):]:
        unresolved.extend(it.lines)
    merged = "\n".join(content[ln] for ln in order if ln in content)
    doc, errors = lenient_parse(merged, contract)
    return MergeResult(text=merged, document=doc, errors=errors, replaced=sorted(replaced),
                       dropped=sorted(dropped), unresolved=sorted(set(unresolved)), notes=notes)
