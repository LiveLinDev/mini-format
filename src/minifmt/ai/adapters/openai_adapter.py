"""OpenAI Chat Completions adapter (uses the installed ``openai`` package)."""
from __future__ import annotations

from typing import Any, Dict, Optional

from .base import Adapter, AdapterError, api_key, result


def to_openai_format(response_format: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """Neutral response_format -> OpenAI ``response_format`` (strict JSON schema)."""
    if response_format is None:
        return None
    if response_format.get("type") != "json_schema":
        raise AdapterError(f"unsupported response_format type {response_format.get('type')}")
    return {"type": "json_schema",
            "json_schema": {"name": response_format.get("name", "salida"), "strict": True,
                            "schema": response_format["schema"]}}


class OpenAIAdapter(Adapter):
    provider = "openai"
    env_var = "OPENAI_API_KEY"

    def __init__(self, model: str, *, structured: bool = True, client: Any = None, send_temperature: bool = True,
                 timeout: float = 120.0, max_retries: int = 3, extra_body: Optional[Dict[str, Any]] = None, **options: Any):
        super().__init__(model, **options)
        self.supports_structured = structured
        self.send_temperature = send_temperature
        self.extra_body = dict(extra_body or {})
        self._client = client
        self._timeout = timeout
        self._max_retries = max_retries

    @property
    def client(self) -> Any:
        if self._client is None:
            from openai import OpenAI  # installed dependency of the experiment
            self._client = OpenAI(api_key=api_key(self.env_var), timeout=self._timeout, max_retries=self._max_retries)
        return self._client

    def build_params(self, system: str, user: str, *, max_tokens: int, temperature: Optional[float],
                     response_format: Optional[Dict[str, Any]], seed: Optional[int]) -> Dict[str, Any]:
        params: Dict[str, Any] = {
            "model": self.model,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
            "max_completion_tokens": int(max_tokens),
        }
        if temperature is not None and self.send_temperature:
            params["temperature"] = temperature
        if seed is not None:
            params["seed"] = int(seed) % (2 ** 31)
        rf = to_openai_format(response_format)
        if rf is not None:
            params["response_format"] = rf
        params.update(self.extra_body)
        return params

    def generate(self, system: str, user: str, *, max_tokens: int, temperature: Optional[float],
                 response_format: Optional[Dict[str, Any]] = None, seed: Optional[int] = None) -> Dict[str, Any]:
        self._check_format(response_format)
        params = self.build_params(system, user, max_tokens=max_tokens, temperature=temperature,
                                   response_format=response_format, seed=seed)
        t0 = self._clock()
        try:
            resp = self.client.chat.completions.create(**params)
        except AdapterError:
            raise
        except Exception as e:  # noqa: BLE001 - openai.* exceptions
            status = getattr(e, "status_code", None)
            raise AdapterError(f"OpenAI error: {type(e).__name__}: {e}", status=status,
                               retryable=status in (408, 429, 500, 502, 503, 504)) from None
        latency = (self._clock() - t0) * 1000
        raw = resp.model_dump() if hasattr(resp, "model_dump") else resp
        choice = raw["choices"][0]
        msg = choice.get("message") or {}
        text = msg.get("content") or msg.get("refusal") or ""
        usage = raw.get("usage") or {}
        return result(text, usage.get("prompt_tokens"), usage.get("completion_tokens"), latency, raw,
                      stop_reason=choice.get("finish_reason"), model=raw.get("model", self.model), provider=self.provider)
