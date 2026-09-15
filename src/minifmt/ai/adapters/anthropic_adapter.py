"""Anthropic Messages API adapter over plain HTTPS (no SDK dependency).

Endpoint ``POST https://api.anthropic.com/v1/messages`` with headers
``x-api-key`` and ``anthropic-version: 2023-06-01``.  Structured output uses
``output_config.format = {"type": "json_schema", "schema": ...}``.  Some
recent models reject sampling parameters; set ``send_temperature=False`` for
them in the experiment configuration.
"""
from __future__ import annotations

from typing import Any, Dict, Optional

from .base import Adapter, AdapterError, api_key, result
from .http import Transport, post_json

ANTHROPIC_URL = "https://api.anthropic.com/v1/messages"
ANTHROPIC_VERSION = "2023-06-01"


class AnthropicAdapter(Adapter):
    provider = "anthropic"
    env_var = "ANTHROPIC_API_KEY"

    def __init__(self, model: str, *, structured: bool = True, send_temperature: bool = True,
                 transport: Optional[Transport] = None, timeout: float = 300.0, retries: int = 3,
                 url: str = ANTHROPIC_URL, extra_body: Optional[Dict[str, Any]] = None, **options: Any):
        super().__init__(model, **options)
        self.supports_structured = structured
        self.send_temperature = send_temperature
        self.transport = transport
        self.timeout = timeout
        self.retries = retries
        self.url = url
        self.extra_body = dict(extra_body or {})

    def build_payload(self, system: str, user: str, *, max_tokens: int, temperature: Optional[float],
                      response_format: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "model": self.model,
            "max_tokens": int(max_tokens),
            "system": system,
            "messages": [{"role": "user", "content": user}],
        }
        if temperature is not None and self.send_temperature:
            payload["temperature"] = temperature
        if response_format is not None:
            if response_format.get("type") != "json_schema":
                raise AdapterError(f"unsupported response_format type {response_format.get('type')}")
            payload["output_config"] = {"format": {"type": "json_schema", "schema": response_format["schema"]}}
        for k, v in self.extra_body.items():
            if k == "output_config" and "output_config" in payload:
                payload["output_config"] = {**v, **payload["output_config"]}
            else:
                payload[k] = v
        return payload

    def generate(self, system: str, user: str, *, max_tokens: int, temperature: Optional[float],
                 response_format: Optional[Dict[str, Any]] = None, seed: Optional[int] = None) -> Dict[str, Any]:
        self._check_format(response_format)  # the Messages API has no seed parameter
        payload = self.build_payload(system, user, max_tokens=max_tokens, temperature=temperature,
                                     response_format=response_format)
        headers = {"x-api-key": api_key(self.env_var), "anthropic-version": ANTHROPIC_VERSION}
        t0 = self._clock()
        raw = post_json(self.url, headers, payload, timeout=self.timeout, retries=self.retries, transport=self.transport)
        latency = (self._clock() - t0) * 1000
        text = "".join(b.get("text", "") for b in raw.get("content", []) if b.get("type") == "text")
        usage = raw.get("usage") or {}
        inp = usage.get("input_tokens")
        if inp is not None:
            inp += int(usage.get("cache_creation_input_tokens") or 0) + int(usage.get("cache_read_input_tokens") or 0)
        return result(text, inp, usage.get("output_tokens"), latency, raw, stop_reason=raw.get("stop_reason"),
                      model=raw.get("model", self.model), provider=self.provider)
