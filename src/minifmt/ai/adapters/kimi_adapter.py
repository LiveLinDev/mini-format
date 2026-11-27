"""Kimi (Moonshot AI) adapter over plain HTTPS (OpenAI-compatible Chat Completions endpoint).

Kimi publishes the OpenAI Chat Completions API at ``https://api.moonshot.ai/v1`` and reads the key from
``MOONSHOT_API_KEY`` (platform.kimi.ai/docs, consulted 2026-11-12). The transport of
:class:`~minifmt.ai.adapters.groq_adapter.GroqAdapter` is reused. Differences documented for ``kimi-k3.1-pro``:

* thinking is always on; ``reasoning_effort`` (``low`` / ``high`` / ``max``) is a top-level request field
  (pass it through ``extra_body``);
* ``temperature`` and ``top_p`` are fixed by the provider, so the adapter never sends them;
* the answer is ``message.content``; ``message.reasoning_content`` is ignored by the reader;
* ``response_format`` accepts ``json_schema`` with ``strict: true``.
"""
from __future__ import annotations

from typing import Any, Optional

from .groq_adapter import GroqAdapter

KIMI_URL = "https://api.moonshot.ai/v1/chat/completions"


class KimiAdapter(GroqAdapter):
    provider = "kimi"
    env_var = "MOONSHOT_API_KEY"

    def __init__(self, model: str, *, url: str = KIMI_URL, send_temperature: Optional[bool] = None, **options: Any):
        # temperature is fixed by the provider for the K3 series: never sent, whatever the caller asks
        super().__init__(model, url=url, send_temperature=False, **options)
