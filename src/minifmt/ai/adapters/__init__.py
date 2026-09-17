"""Generation adapters with a common interface (see :mod:`.base`)."""
from __future__ import annotations

from typing import Any

from .anthropic_adapter import AnthropicAdapter
from .base import Adapter, AdapterError, MissingKeyError, redact, redact_headers
from .deepseek_adapter import DeepSeekAdapter
from .groq_adapter import GroqAdapter
from .openai_adapter import OpenAIAdapter
from .simulated import DEFAULT_PROFILE, PROFILES, SimTarget, SimulatedAdapter

ADAPTERS = {"openai": OpenAIAdapter, "anthropic": AnthropicAdapter, "groq": GroqAdapter,
            "deepseek": DeepSeekAdapter, "simulado": SimulatedAdapter, "simulated": SimulatedAdapter}


def get_adapter(provider: str, model: str, **options: Any) -> Adapter:
    try:
        cls = ADAPTERS[provider.lower()]
    except KeyError:
        raise AdapterError(f"unknown provider '{provider}' (known: {', '.join(sorted(ADAPTERS))})") from None
    return cls(model, **options)


__all__ = ["Adapter", "AdapterError", "MissingKeyError", "OpenAIAdapter", "AnthropicAdapter", "GroqAdapter",
           "DeepSeekAdapter",
           "SimulatedAdapter", "SimTarget", "DEFAULT_PROFILE", "PROFILES", "get_adapter", "redact", "redact_headers"]
