"""Minimal JSON-over-HTTPS client: httpx when installed, urllib otherwise.

A ``transport`` callable can be injected for tests; it receives
``(url, headers, body_bytes, timeout)`` and returns ``(status, body_bytes)``.
Nothing here logs request headers; errors are redacted.
"""
from __future__ import annotations

import json
import logging
import random
import time
from typing import Any, Callable, Dict, Mapping, Optional, Tuple

from .base import AdapterError, redact, redact_headers

log = logging.getLogger("minifmt.ai.http")

Transport = Callable[[str, Mapping[str, str], bytes, float], Tuple[int, bytes]]
RETRYABLE = {408, 409, 429, 500, 502, 503, 504, 529}


def _httpx_transport(url: str, headers: Mapping[str, str], body: bytes, timeout: float) -> Tuple[int, bytes]:
    import httpx  # type: ignore
    r = httpx.post(url, headers=dict(headers), content=body, timeout=timeout)
    return r.status_code, r.content


def _urllib_transport(url: str, headers: Mapping[str, str], body: bytes, timeout: float) -> Tuple[int, bytes]:
    import urllib.error
    import urllib.request
    req = urllib.request.Request(url, data=body, headers=dict(headers), method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310 - fixed https endpoints
            return resp.status, resp.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()


def default_transport() -> Transport:
    try:
        import httpx  # noqa: F401
        return _httpx_transport
    except ImportError:
        return _urllib_transport


def post_json(url: str, headers: Mapping[str, str], payload: Dict[str, Any], *, timeout: float = 120.0,
              retries: int = 3, transport: Optional[Transport] = None,
              sleep: Callable[[float], None] = time.sleep) -> Dict[str, Any]:
    """POST ``payload`` as JSON; retries retryable statuses with jittered backoff."""
    tp = transport or default_transport()
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    hdrs = {"content-type": "application/json", **headers}
    last: Optional[AdapterError] = None
    for attempt in range(retries + 1):
        try:
            status, raw = tp(url, hdrs, body, timeout)
        except Exception as e:  # noqa: BLE001 - network errors of either backend
            last = AdapterError(f"network error calling {url}: {type(e).__name__}: {e}", retryable=True)
        else:
            if 200 <= status < 300:
                try:
                    return json.loads(raw.decode("utf-8"))
                except ValueError as e:
                    raise AdapterError(f"non-JSON answer from {url}: {e}") from None
            snippet = raw[:500].decode("utf-8", "replace")
            last = AdapterError(f"HTTP {status} from {url}: {snippet}", status=status, retryable=status in RETRYABLE)
            if not last.retryable:
                raise last
        if attempt < retries:
            delay = min(30.0, (2 ** attempt) + random.random())
            log.warning("retrying %s in %.1fs (%s; headers=%s)", url, delay, redact(last),
                        redact_headers(hdrs))
            sleep(delay)
    assert last is not None
    raise last
