"""DeepSeek adapter over plain HTTPS (OpenAI-compatible Chat Completions endpoint).

DeepSeek publishes the OpenAI Chat Completions API, so the transport of
:class:`~minifmt.ai.adapters.groq_adapter.GroqAdapter` is reused; only the
endpoint, the key and the output-limit field differ (``max_tokens`` instead of
``max_completion_tokens``).
"""
from __future__ import annotations

from typing import Any, Dict, Optional

from .groq_adapter import GroqAdapter

DEEPSEEK_URL = "https://api.deepseek.com/chat/completions"


class DeepSeekAdapter(GroqAdapter):
    provider = "deepseek"
    env_var = "DEEPSEEK_API_KEY"

    def __init__(self, model: str, *, url: str = DEEPSEEK_URL, **options: Any):
        super().__init__(model, url=url, **options)

    def build_payload(self, system: str, user: str, *, max_tokens: int, temperature: Optional[float],
                      response_format: Optional[Dict[str, Any]], seed: Optional[int]) -> Dict[str, Any]:
        payload = super().build_payload(system, user, max_tokens=max_tokens, temperature=temperature,
                                        response_format=response_format, seed=seed)
        payload["max_tokens"] = payload.pop("max_completion_tokens")
        return payload
