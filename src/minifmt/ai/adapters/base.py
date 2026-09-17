"""Common interface of the generation adapters.

Every adapter exposes::

    generate(system, user, *, max_tokens, temperature, response_format=None, seed=None)
        -> {"text", "input_tokens", "output_tokens", "latency_ms", "raw",
            "stop_reason", "model", "provider"}

``response_format`` is provider-neutral::

    {"type": "json_schema", "name": "<name>", "schema": {...JSON Schema...}}

and each adapter translates it to its provider's native structured-output
mode.  Adapters whose provider/model does not support it declare
``supports_structured = False``; callers must then skip the condition rather
than silently falling back to unconstrained generation.

API keys are read only from environment variables, are never returned,
logged or written anywhere; :func:`redact` masks them (and any header that
carries credentials) in every message that may reach a log.
"""
from __future__ import annotations

import os
import re
import time
from abc import ABC, abstractmethod
from typing import Any, Dict, Mapping, Optional

KEY_ENV_VARS = ("OPENAI_API_KEY", "ANTHROPIC_API_KEY", "GROQ_API_KEY", "DEEPSEEK_API_KEY")
SENSITIVE_HEADERS = {"authorization", "x-api-key", "api-key", "proxy-authorization", "cookie"}
_KEY_PATTERNS = [
    re.compile(r"sk-[A-Za-z0-9_\-]{8,}"),
    re.compile(r"gsk_[A-Za-z0-9]{8,}"),
    re.compile(r"(?i)(bearer\s+)[A-Za-z0-9_\-\.=]{8,}"),
]


class AdapterError(RuntimeError):
    """Generation failed (network, HTTP status, malformed answer...). Message is redacted."""

    def __init__(self, message: str, *, status: Optional[int] = None, retryable: bool = False):
        super().__init__(redact(message))
        self.status = status
        self.retryable = retryable


class MissingKeyError(AdapterError):
    pass


def redact(text: Any) -> str:
    """Mask API keys and credential-looking substrings in ``text``."""
    s = str(text)
    for var in KEY_ENV_VARS:
        val = os.environ.get(var)
        if val and len(val) >= 6:
            s = s.replace(val, "***")
    for pat in _KEY_PATTERNS:
        s = pat.sub(lambda m: (m.group(1) if m.groups() else "") + "***", s)
    return s


def redact_headers(headers: Mapping[str, str]) -> Dict[str, str]:
    """Copy of ``headers`` safe to log (credential headers replaced by ***)."""
    return {k: ("***" if k.lower() in SENSITIVE_HEADERS else redact(v)) for k, v in headers.items()}


def api_key(env_var: str) -> str:
    """Read an API key from the environment; raises without revealing anything."""
    val = os.environ.get(env_var, "").strip()
    if not val:
        raise MissingKeyError(f"environment variable {env_var} is not set")
    return val


def result(text: str, input_tokens: Optional[int], output_tokens: Optional[int], latency_ms: float,
           raw: Any, *, stop_reason: Optional[str] = None, model: str = "", provider: str = "") -> Dict[str, Any]:
    return {"text": text or "", "input_tokens": input_tokens, "output_tokens": output_tokens,
            "latency_ms": round(float(latency_ms), 1), "raw": raw, "stop_reason": stop_reason,
            "model": model, "provider": provider}


class Adapter(ABC):
    provider: str = "base"
    supports_structured: bool = False

    def __init__(self, model: str, **options: Any):
        self.model = model
        self.options = options

    @abstractmethod
    def generate(self, system: str, user: str, *, max_tokens: int, temperature: Optional[float],
                 response_format: Optional[Dict[str, Any]] = None, seed: Optional[int] = None) -> Dict[str, Any]:
        """Run one generation and return the common result dict."""

    # helpers ---------------------------------------------------------------
    @staticmethod
    def _clock() -> float:
        return time.perf_counter()

    def _check_format(self, response_format: Optional[Dict[str, Any]]) -> None:
        if response_format is not None and not self.supports_structured:
            raise AdapterError(f"{self.provider}:{self.model} does not support structured output")

    def __repr__(self) -> str:  # never includes credentials
        return f"<{type(self).__name__} {self.provider}:{self.model}>"
