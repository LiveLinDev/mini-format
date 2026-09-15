"""Error model of the .mini reference implementation.

Every violation is reported with a stable error code, the 1-based line number
of the offending physical line (0 for document-level errors) and a human
readable message.  Codes are part of the public contract of the format so
that validators written in other languages can be compared field by field.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List


# --- Stable error codes -----------------------------------------------------
E_NO_HEADER = "E01"        # document has no header line
E_UNKNOWN_PREFIX = "E02"   # header prefix is not registered / does not match contract
E_NO_COUNT = "E03"         # header does not declare n
E_COUNT_MISMATCH = "E04"   # number of records != n
E_ARITY = "E05"            # record has fewer core fields than the contract requires (or too many)
E_TYPE = "E06"             # a scalar value does not match its declared type
E_LIST_ARITY = "E07"       # list / tuple has an invalid number of elements
E_MARKER = "E08"           # marker (*) count violates the field's marker rule
E_ESCAPE = "E09"           # invalid escape sequence or dangling backslash
E_ENUM = "E10"             # value not in the enumerated set
E_UNIQUE = "E11"           # duplicate value in a field declared unique
E_HEADER_KEY = "E12"       # header key missing / malformed
E_RANGE = "E13"            # numeric value out of declared range
E_CONTRACT = "E20"         # the contract itself is invalid
E_FORK = "E21"             # fork invariant violated (core changed, prefix clash, ...)


@dataclass
class MiniError(Exception):
    """A single validation error."""

    code: str
    line: int
    message: str
    field: str = ""

    def __str__(self) -> str:  # pragma: no cover - trivial
        where = f"line {self.line}" if self.line else "document"
        fld = f" [{self.field}]" if self.field else ""
        return f"{self.code} {where}{fld}: {self.message}"

    def to_dict(self) -> dict:
        """Plain representation (code, line, field, message) for reports."""
        return {"code": self.code, "line": self.line, "field": self.field, "message": self.message}


@dataclass
class MiniValidationError(Exception):
    """Raised by strict parsing when one or more errors were collected."""

    errors: List[MiniError] = field(default_factory=list)

    def __str__(self) -> str:  # pragma: no cover - trivial
        return "\n".join(str(e) for e in self.errors)

    @property
    def codes(self) -> List[str]:
        return [e.code for e in self.errors]
