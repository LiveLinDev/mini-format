"""Incremental (streaming) reader of .mini documents.

A model response usually arrives token by token.  :class:`Reader` accepts
fragments of text (or UTF-8 bytes, possibly split in the middle of a
multi-byte character) and emits every record as soon as its line is closed by
LF.  When the stream ends, the resulting :class:`~minifmt.parser.Document`,
records and errors are identical to those of ``parse(full_text, contract,
strict=...)``; the Python API mirrors ``createReader``/``readRecords`` of the
TypeScript library (``ts/src/stream.ts``).

Memory: the reader keeps only the current unfinished line, the error list and
the values of fields declared ``unique`` (needed for E11).  Accepted records
are retained only when ``keep_records=True`` (the default of :class:`Reader`;
:func:`read_records` defaults to ``False`` because it yields every record to
the caller).

Differences with :func:`~minifmt.parser.parse` are limited to the empty
document: ``parse`` always raises E01, whereas a lenient reader returns a
result whose ``errors`` hold E01 (a strict reader raises, like ``parse``).
"""
from __future__ import annotations

import codecs
from dataclasses import dataclass, field
from typing import (Any, Callable, Dict, Generator, Iterable, List, NamedTuple, Optional,
                    Union)

from . import codec
from .contract import Contract
from .errors import (E_ARITY, E_COUNT_MISMATCH, E_NO_HEADER, E_UNIQUE, E_UNKNOWN_PREFIX,
                     MiniError, MiniValidationError)
from .parser import Document, MList, _hashable, decode_field, parse_header

Chunk = Union[str, bytes, bytearray, memoryview]

__all__ = ["Reader", "ReaderResult", "ReaderProgress", "StreamRecord", "IncompleteRecord",
           "create_reader", "read_records"]


class StreamRecord(NamedTuple):
    """Record emitted as soon as its line is closed with LF."""
    record: Dict[str, Any]
    line: int    #: physical line, 1-based
    index: int   #: position among the valid records, 0-based


@dataclass
class IncompleteRecord:
    """Last line received without a final LF that failed validation (typical of a truncated output)."""
    line: int
    text: str
    fields_seen: int            #: ``|``-separated fields present (approximate, escapes not resolved)
    is_header: bool
    errors: List[MiniError] = field(default_factory=list)


class ReaderProgress(NamedTuple):
    expected: Optional[int]
    received: int
    valid: int
    errors: int


@dataclass
class ReaderResult:
    document: Document
    records: List[Dict[str, Any]]
    errors: List[MiniError]
    expected: Optional[int]     #: ``n`` declared in the header (None if absent or not an integer)
    received: int               #: significant record lines received (valid or not)
    valid: int                  #: valid records
    missing: int                #: max(0, expected - received)
    excess: int                 #: max(0, received - expected)
    terminated: bool            #: the stream ended with LF (or nothing was pending)
    incomplete: Optional[IncompleteRecord]
    truncated: bool             #: incomplete last record or fewer record lines than ``n``
    complete: bool              #: no errors of any kind
    #: records completed by ``end()`` itself (a last valid line without LF); already counted in ``valid``
    final_records: List[StreamRecord] = field(default_factory=list)


def _count_fields_approx(line: str) -> int:
    n, i = 1, 0
    while i < len(line):
        if line[i] == "\\":
            i += 1
        elif line[i] == "|":
            n += 1
        i += 1
    return n


def _declared_count(header: Optional[Dict[str, Any]]) -> Optional[int]:
    if not header or "n" not in header:
        return None
    n = header["n"]
    return n if isinstance(n, int) and not isinstance(n, bool) else None


def _as_contract(contract: Union[Contract, Dict[str, Any]]) -> Contract:
    if isinstance(contract, Contract):
        return contract
    if isinstance(contract, dict):
        return Contract.from_dict(contract)
    raise TypeError("contract must be a Contract or a contract dict")


class _LineEngine:
    """Line-by-line interpreter with the exact semantics of ``parser.parse``."""

    def __init__(self, contract: Contract, strict: bool, keep_records: bool):
        self.contract = contract
        self.strict = strict
        self.keep_records = keep_records
        self.prefix = ""
        self.header: Optional[Dict[str, Any]] = None
        self.version = 1
        self.records: List[Dict[str, Any]] = []
        self.record_lines: List[int] = []
        self.errors: List[MiniError] = []
        self.physical = 0
        self.significant = 0
        self.header_line = 0
        self.last_line = 0
        self.valid = 0
        self._uniques: Dict[str, Dict[Any, int]] = {f.name: {} for f in contract.fields if f.unique}

    @property
    def record_line_count(self) -> int:
        return max(0, self.significant - 1)

    def feed(self, raw: str) -> Optional[StreamRecord]:
        self.physical += 1
        lineno = self.physical
        line = raw
        if lineno == 1 and line.startswith("\ufeff"):
            line = line[1:]
        line = line.rstrip("\r")
        if line.strip() == "":
            return None
        self.significant += 1
        self.last_line = lineno
        if self.header is None:
            self._accept_header(line, lineno)
            return None
        return self._accept_record(line, lineno)

    def _accept_header(self, line: str, lineno: int) -> None:
        c = self.contract
        self.header_line = lineno
        prefix, header, errs = parse_header(line, lineno, c, self.strict)
        self.prefix, self.header = prefix, header
        self.errors.extend(errs)
        if prefix != c.prefix:
            self.errors.append(MiniError(E_UNKNOWN_PREFIX, lineno, f"header prefix '{prefix}' does not match contract '{c.prefix}'"))
        self.version = int(header.get("v", 1) or 1)

    def _accept_record(self, line: str, lineno: int) -> Optional[StreamRecord]:
        c = self.contract
        sep = c.list_separator
        try:
            toks = codec.split_fields(line, sep, lineno, strict=True)
        except MiniError as e:
            self.errors.append(e)
            return None
        nf = len(toks)
        if nf < c.arity:
            self.errors.append(MiniError(E_ARITY, lineno, f"record has {nf} fields, core requires {c.arity}"))
            return None
        fields = c.fields
        if nf > len(fields):
            if self.version > c.version:
                toks = toks[:len(fields)]
                nf = len(toks)
            else:
                self.errors.append(MiniError(E_ARITY, lineno, f"record has {nf} fields, contract allows at most {len(fields)}"))
                return None
        rec: Dict[str, Any] = {}
        rec_errs: List[MiniError] = []
        for i, f in enumerate(fields):
            if i >= nf:
                if f.type == "mlist":
                    rec[f.json_items], rec[f.json_selected] = None, None
                else:
                    rec[f.name] = f.default
                continue
            try:
                val = decode_field(toks[i], f, lineno, sep, self.header)
            except MiniError as e:
                rec_errs.append(e)
                continue
            if isinstance(val, MList):
                rec[f.json_items], rec[f.json_selected] = val[0], val[1]
            else:
                rec[f.name] = val
        for name, seen in self._uniques.items():
            v = rec.get(name)
            if v is not None and _hashable(v) in seen:
                rec_errs.append(MiniError(E_UNIQUE, lineno, f"duplicate value '{v}' (first seen line {seen[_hashable(v)]})", name))
        if rec_errs:
            self.errors.extend(rec_errs)
            return None
        for name, seen in self._uniques.items():
            v = rec.get(name)
            if v is not None:
                seen[_hashable(v)] = lineno
        self.valid += 1
        if self.keep_records:
            self.records.append(rec)
            self.record_lines.append(lineno)
        return StreamRecord(rec, lineno, self.valid - 1)

    def finish(self) -> Document:
        c = self.contract
        if self.header is None:
            errors = list(self.errors) + [MiniError(E_NO_HEADER, 0, "empty document: header missing")]
            return Document(prefix="", version=1, header={}, records=[], contract=c, errors=errors, lines=0)
        errors = list(self.errors)
        n = self.header.get("n")
        total = self.record_line_count
        if isinstance(n, int) and n != total:
            errors.append(MiniError(E_COUNT_MISMATCH, 0, f"header declares n={n} but document has {total} record lines"))
        return Document(prefix=self.prefix, version=self.version, header=self.header, records=self.records,
                        contract=c, errors=errors, lines=self.significant, header_line=self.header_line,
                        record_lines=self.record_lines, record_line_count=total, last_line=self.last_line)


class Reader:
    """Incremental reader for one document of ``contract``.

    ``strict=False`` (default) is tolerant; with ``strict=True`` :meth:`end`
    raises :class:`MiniValidationError` (carrying ``.result``) if there were
    errors.  Callbacks ``on_header(prefix, header, line)``,
    ``on_record(StreamRecord)`` and ``on_error(MiniError)`` are optional.
    """

    def __init__(self, contract: Union[Contract, Dict[str, Any]], strict: bool = False, keep_records: bool = True,
                 on_header: Optional[Callable[[str, Dict[str, Any], int], None]] = None,
                 on_record: Optional[Callable[[StreamRecord], None]] = None,
                 on_error: Optional[Callable[[MiniError], None]] = None):
        self._contract = _as_contract(contract)
        self._strict = bool(strict)
        self._engine = _LineEngine(self._contract, self._strict, keep_records)
        self._pending: List[str] = []
        self._pending_len = 0
        self._ended = False
        self._decoder: Any = None
        self._mode: Optional[str] = None
        self._reported = 0
        self._on_header, self._on_record, self._on_error = on_header, on_record, on_error

    # ------------------------------------------------------------ helpers
    def _flush_errors(self) -> None:
        errs = self._engine.errors
        if self._on_error is not None:
            while self._reported < len(errs):
                self._on_error(errs[self._reported])
                self._reported += 1
        else:
            self._reported = len(errs)

    def _feed_line(self, raw: str, out: List[StreamRecord]) -> None:
        eng = self._engine
        had_header = eng.header is not None
        rec = eng.feed(raw)
        if not had_header and eng.header is not None and self._on_header is not None:
            self._on_header(eng.prefix, eng.header, eng.physical)
        if rec is not None:
            out.append(rec)
            if self._on_record is not None:
                self._on_record(rec)
        self._flush_errors()

    def _to_text(self, chunk: Chunk) -> str:
        if isinstance(chunk, str):
            if self._mode == "bytes":
                raise TypeError("do not mix str and bytes chunks in one stream")
            self._mode = "str"
            return chunk
        if isinstance(chunk, (bytes, bytearray, memoryview)):
            if self._mode == "str":
                raise TypeError("do not mix str and bytes chunks in one stream")
            self._mode = "bytes"
            if self._decoder is None:
                self._decoder = codecs.getincrementaldecoder("utf-8")(errors="replace")
            return self._decoder.decode(bytes(chunk), final=False)
        raise TypeError(f"chunk must be str or bytes, not {type(chunk).__name__}")

    def _take_pending(self, tail: str = "") -> str:
        if not self._pending:
            return tail
        self._pending.append(tail)
        text = "".join(self._pending)
        self._pending, self._pending_len = [], 0
        return text

    # ---------------------------------------------------------------- API
    def push(self, chunk: Chunk) -> List[StreamRecord]:
        """Add a fragment (str, or UTF-8 bytes; do not mix both). Returns the records completed by it."""
        if self._ended:
            raise RuntimeError("mini reader already ended")
        return self._push_text(self._to_text(chunk))

    def _push_text(self, text: str) -> List[StreamRecord]:
        out: List[StreamRecord] = []
        if not text:
            return out
        start = 0
        idx = text.find("\n")
        while idx >= 0:
            self._feed_line(self._take_pending(text[start:idx]), out)
            start = idx + 1
            idx = text.find("\n", start)
        if start < len(text):
            self._pending.append(text[start:] if start else text)
            self._pending_len += 1
            if self._pending_len > 256:  # keep many one-character fragments compact
                self._pending, self._pending_len = ["".join(self._pending)], 1
        return out

    def end(self, chunk: Optional[Chunk] = None) -> ReaderResult:
        """Close the stream (optionally with a last fragment) and return the final result."""
        if self._ended:
            raise RuntimeError("mini reader already ended")
        if chunk is not None:
            self.push(chunk)
        if self._decoder is not None:
            tail = self._decoder.decode(b"", final=True)
            if tail:
                self._push_text(tail)
        self._ended = True
        eng = self._engine
        rest = self._take_pending()
        terminated = rest.strip() == ""
        errs_before = len(eng.errors)
        had_header = eng.header is not None
        line_no = eng.physical + 1
        final: List[StreamRecord] = []
        self._feed_line(rest, final)
        incomplete: Optional[IncompleteRecord] = None
        if not terminated:
            line_errors = [e for e in eng.errors[errs_before:] if e.line == line_no]
            if line_errors:
                incomplete = IncompleteRecord(line=line_no, text=rest, fields_seen=_count_fields_approx(rest),
                                              is_header=not had_header, errors=line_errors)
        document = eng.finish()
        if self._on_error is not None:
            for e in document.errors[len(eng.errors):]:
                self._on_error(e)
        expected = _declared_count(eng.header)
        received = eng.record_line_count
        missing = 0 if expected is None else max(0, expected - received)
        excess = 0 if expected is None else max(0, received - expected)
        result = ReaderResult(document=document, records=document.records, errors=document.errors,
                              expected=expected, received=received, valid=eng.valid, missing=missing,
                              excess=excess, terminated=terminated, incomplete=incomplete,
                              truncated=incomplete is not None or missing > 0,
                              complete=not document.errors, final_records=final)
        if self._strict and document.errors:
            exc = MiniValidationError(list(document.errors))
            exc.result = result  # type: ignore[attr-defined]
            raise exc
        return result

    @property
    def contract(self) -> Contract:
        return self._contract

    @property
    def prefix(self) -> str:
        return self._engine.prefix

    @property
    def header(self) -> Optional[Dict[str, Any]]:
        return self._engine.header

    @property
    def records(self) -> List[Dict[str, Any]]:
        return self._engine.records

    @property
    def errors(self) -> List[MiniError]:
        return self._engine.errors

    @property
    def pending(self) -> str:
        """Text of the current line, still without LF."""
        if len(self._pending) > 1:
            self._pending, self._pending_len = ["".join(self._pending)], 1
        return self._pending[0] if self._pending else ""

    @property
    def progress(self) -> ReaderProgress:
        eng = self._engine
        return ReaderProgress(_declared_count(eng.header), eng.record_line_count, eng.valid, len(eng.errors))

    @property
    def ended(self) -> bool:
        return self._ended


def create_reader(contract: Union[Contract, Dict[str, Any]], **options: Any) -> Reader:
    """Create an incremental reader for ``contract`` (see :class:`Reader`)."""
    return Reader(contract, **options)


def read_records(chunks: Union[Iterable[Chunk], Chunk], contract: Union[Contract, Dict[str, Any]],
                 keep_records: bool = False, **options: Any) -> Generator[StreamRecord, None, ReaderResult]:
    """Consume an iterable of fragments and yield records as they complete.

    The generator's return value (``StopIteration.value``, or the result of
    ``yield from``) is the final :class:`ReaderResult`.  Records are not
    retained unless ``keep_records=True``, so memory does not grow with the
    number of records.  For asynchronous sources, drive a :class:`Reader`
    directly (``for rec in reader.push(chunk)`` inside ``async for``).
    """
    reader = Reader(contract, keep_records=keep_records, **options)
    if isinstance(chunks, (str, bytes, bytearray, memoryview)):
        chunks = [chunks]
    for chunk in chunks:
        for rec in reader.push(chunk):
            yield rec
    result = reader.end()
    for rec in result.final_records:
        yield rec
    return result
