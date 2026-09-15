"""Groq adapter over plain HTTPS (OpenAI-compatible Chat Completions endpoint).

Structured output (``response_format`` JSON schema) is available only on some
Groq-hosted models; declare it per model with ``structured=True``.
"""
from __future__ import annotations

from typing import Any, Dict, Optional

from .base import Adapter, api_key, result
from .http import Transport, post_json
from .openai_adapter import to_openai_format

GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"


class GroqAdapter(Adapter):
    provider = "groq"
    env_var = "GROQ_API_KEY"

    def __init__(self, model: str, *, structured: bool = False, send_temperature: bool = True,
                 transport: Optional[Transport] = None, timeout: float = 120.0, retries: int = 3,
                 url: str = GROQ_URL, extra_body: Optional[Dict[str, Any]] = None, **options: Any):
        super().__init__(model, **options)
        self.supports_structured = structured
        self.send_temperature = send_temperature
        self.transport = transport
        self.timeout = timeout
        self.retries = retries
        self.url = url
        self.extra_body = dict(extra_body or {})

    def build_payload(self, system: str, user: str, *, max_tokens: int, temperature: Optional[float],
                      response_format: Optional[Dict[str, Any]], seed: Optional[int]) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "model": self.model,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
            "max_completion_tokens": int(max_tokens),
        }
        if temperature is not None and self.send_temperature:
            payload["temperature"] = temperature
        if seed is not None:
            payload["seed"] = int(seed) % (2 ** 31)
        rf = to_openai_format(response_format)
        if rf is not None:
            payload["response_format"] = rf
        payload.update(self.extra_body)
        return payload

    def generate(self, system: str, user: str, *, max_tokens: int, temperature: Optional[float],
                 response_format: Optional[Dict[str, Any]] = None, seed: Optional[int] = None) -> Dict[str, Any]:
        self._check_format(response_format)
        payload = self.build_payload(system, user, max_tokens=max_tokens, temperature=temperature,
                                     response_format=response_format, seed=seed)
        headers = {"authorization": "Bearer " + api_key(self.env_var)}
        t0 = self._clock()
        raw = post_json(self.url, headers, payload, timeout=self.timeout, retries=self.retries, transport=self.transport)
        latency = (self._clock() - t0) * 1000
        choice = (raw.get("choices") or [{}])[0]
        text = (choice.get("message") or {}).get("content") or ""
        usage = raw.get("usage") or {}
        return result(text, usage.get("prompt_tokens"), usage.get("completion_tokens"), latency, raw,
                      stop_reason=choice.get("finish_reason"), model=raw.get("model", self.model), provider=self.provider)
