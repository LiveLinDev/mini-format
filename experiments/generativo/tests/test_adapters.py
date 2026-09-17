"""Adaptadores: interfaz común, redacción de claves y adaptador simulado (sin red)."""
from __future__ import annotations

import json
import logging

import pytest

from minifmt import Registry
from minifmt.ai.adapters import (AdapterError, AnthropicAdapter, DeepSeekAdapter, GroqAdapter, MissingKeyError, OpenAIAdapter,
                                 SimTarget, SimulatedAdapter, get_adapter, redact, redact_headers)
from minifmt.ai.adapters.http import post_json

from conftest import ROOT

CLAVE_FALSA = "sk-prueba-0123456789abcdefghij"
RF = {"type": "json_schema", "name": "salida", "schema": {"type": "object", "properties": {}, "required": [],
                                                           "additionalProperties": False}}
CLAVES_RESULTADO = {"text", "input_tokens", "output_tokens", "latency_ms", "raw", "stop_reason", "model", "provider"}


# ------------------------------------------------------------------ redacción
def test_redact_oculta_claves(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", CLAVE_FALSA)
    s = redact(f"fallo con {CLAVE_FALSA} y Bearer gsk_abcdefghijklmnop y sk-otra1234567890")
    assert CLAVE_FALSA not in s and "gsk_abcdefghijklmnop" not in s and "sk-otra1234567890" not in s
    h = redact_headers({"Authorization": "Bearer x", "x-api-key": "y", "anthropic-version": "2023-06-01"})
    assert h["Authorization"] == "***" and h["x-api-key"] == "***" and h["anthropic-version"] == "2023-06-01"


def test_falta_clave_no_revela_nada(sin_claves):
    ad = AnthropicAdapter("claude-haiku-4-5", transport=lambda *a: (200, b"{}"))
    with pytest.raises(MissingKeyError) as e:
        ad.generate("s", "u", max_tokens=10, temperature=0)
    assert "ANTHROPIC_API_KEY" in str(e.value)


def test_fabrica_de_adaptadores():
    assert isinstance(get_adapter("openai", "gpt-4.1-mini"), OpenAIAdapter)
    assert isinstance(get_adapter("groq", "x"), GroqAdapter)
    assert isinstance(get_adapter("deepseek", "x"), DeepSeekAdapter)
    with pytest.raises(AdapterError):
        get_adapter("desconocido", "x")
    assert CLAVE_FALSA not in repr(get_adapter("anthropic", "m"))


# ------------------------------------------------------------------ Anthropic (HTTP)
def test_anthropic_payload_y_respuesta(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", CLAVE_FALSA)
    visto = {}

    def transporte(url, headers, body, timeout):
        visto.update(url=url, headers=dict(headers), body=json.loads(body))
        return 200, json.dumps({"model": "claude-haiku-4-5", "stop_reason": "end_turn",
                                "content": [{"type": "text", "text": "{\"a\": 1}"}],
                                "usage": {"input_tokens": 12, "output_tokens": 5, "cache_read_input_tokens": 3}}).encode()

    ad = AnthropicAdapter("claude-haiku-4-5", transport=transporte)
    r = ad.generate("sistema", "usuario", max_tokens=100, temperature=0.2, response_format=RF, seed=1)
    assert set(r) == CLAVES_RESULTADO
    assert r["text"] == "{\"a\": 1}" and r["input_tokens"] == 15 and r["output_tokens"] == 5
    assert visto["url"].endswith("/v1/messages")
    assert visto["headers"]["x-api-key"] == CLAVE_FALSA and visto["headers"]["anthropic-version"] == "2023-06-01"
    assert visto["body"]["system"] == "sistema" and visto["body"]["temperature"] == 0.2
    assert visto["body"]["output_config"]["format"]["type"] == "json_schema"
    sin_temp = AnthropicAdapter("claude-sonnet-5", send_temperature=False, transport=transporte)
    sin_temp.generate("s", "u", max_tokens=10, temperature=0.7)
    assert "temperature" not in visto["body"]


def test_anthropic_error_http_redactado(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", CLAVE_FALSA)
    ad = AnthropicAdapter("m", transport=lambda *a: (400, f"clave {CLAVE_FALSA} inválida".encode()))
    with pytest.raises(AdapterError) as e:
        ad.generate("s", "u", max_tokens=10, temperature=0)
    assert e.value.status == 400 and CLAVE_FALSA not in str(e.value)


def test_reintentos_en_429(caplog, monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", CLAVE_FALSA)
    estados = [429, 503, 200]

    def transporte(url, headers, body, timeout):
        st = estados.pop(0)
        return st, (b'{"choices": [{"message": {"content": "ok"}, "finish_reason": "stop"}], '
                    b'"usage": {"prompt_tokens": 3, "completion_tokens": 1}}' if st == 200 else b"lento")

    esperas = []
    with caplog.at_level(logging.WARNING):
        out = post_json("https://x/y", {"authorization": "Bearer " + CLAVE_FALSA}, {"a": 1}, transport=transporte,
                        sleep=esperas.append)
    assert out["choices"][0]["message"]["content"] == "ok" and len(esperas) == 2
    assert CLAVE_FALSA not in caplog.text


# ------------------------------------------------------------------ Groq (HTTP)
def test_groq_payload(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", CLAVE_FALSA)
    visto = {}

    def transporte(url, headers, body, timeout):
        visto.update(headers=dict(headers), body=json.loads(body))
        return 200, json.dumps({"model": "llama", "choices": [{"message": {"content": "hola"}, "finish_reason": "length"}],
                                "usage": {"prompt_tokens": 7, "completion_tokens": 2}}).encode()

    ad = GroqAdapter("llama-3.3-70b-versatile", transport=transporte)
    r = ad.generate("s", "u", max_tokens=50, temperature=0, seed=42)
    assert r["stop_reason"] == "length" and r["input_tokens"] == 7
    assert visto["headers"]["authorization"] == "Bearer " + CLAVE_FALSA
    assert visto["body"]["seed"] == 42 and visto["body"]["messages"][0]["role"] == "system"
    with pytest.raises(AdapterError):
        ad.generate("s", "u", max_tokens=5, temperature=0, response_format=RF)   # sin modo estructurado declarado


# ------------------------------------------------------------------ DeepSeek (HTTP, API de OpenAI)
def test_deepseek_payload(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", CLAVE_FALSA)
    visto = {}

    def transporte(url, headers, body, timeout):
        visto.update(url=url, headers=dict(headers), body=json.loads(body))
        return 200, json.dumps({"model": "deepseek-chat", "choices": [{"message": {"content": "tk|n=0"}, "finish_reason": "stop"}],
                                "usage": {"prompt_tokens": 11, "completion_tokens": 3}}).encode()

    ad = DeepSeekAdapter("deepseek-chat", transport=transporte)
    r = ad.generate("s", "u", max_tokens=64, temperature=0)
    assert r["provider"] == "deepseek" and r["output_tokens"] == 3
    assert visto["url"] == "https://api.deepseek.com/chat/completions"
    assert visto["headers"]["authorization"] == "Bearer " + CLAVE_FALSA
    # DeepSeek usa max_tokens, no max_completion_tokens
    assert visto["body"]["max_tokens"] == 64 and "max_completion_tokens" not in visto["body"]


def test_deepseek_exige_clave(monkeypatch):
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    with pytest.raises(MissingKeyError):
        DeepSeekAdapter("deepseek-chat", transport=lambda *a: (200, b"{}")).generate("s", "u", max_tokens=8, temperature=0)

# ------------------------------------------------------------------ OpenAI (cliente inyectado)
class _Resp:
    def model_dump(self):
        return {"model": "gpt-4.1-mini", "choices": [{"message": {"content": "{}"}, "finish_reason": "stop"}],
                "usage": {"prompt_tokens": 9, "completion_tokens": 1}}


class _Cliente:
    def __init__(self):
        self.params = None
        cliente = self

        class _Comp:
            def create(self, **params):
                cliente.params = params
                return _Resp()

        class _Chat:
            completions = _Comp()

        self.chat = _Chat()


def test_openai_parametros():
    cli = _Cliente()
    ad = OpenAIAdapter("gpt-4.1-mini", client=cli)
    r = ad.generate("s", "u", max_tokens=64, temperature=0.3, response_format=RF, seed=7)
    assert set(r) == CLAVES_RESULTADO and r["input_tokens"] == 9
    p = cli.params
    assert p["max_completion_tokens"] == 64 and p["seed"] == 7 and p["temperature"] == 0.3
    assert p["response_format"]["type"] == "json_schema" and p["response_format"]["json_schema"]["strict"] is True


# ------------------------------------------------------------------ simulado
REG = Registry.load(ROOT / "forks")


def _oraculo_log():
    import json as _j
    c = REG.get("log")
    canon = _j.loads((ROOT / "forks/log/fixtures/canonical.json").read_text(encoding="utf-8"))
    obj = SimTarget(kind="mini", contract=c, records=canon["events"], header={"env": "staging"})
    return lambda s, u: obj


def test_simulado_determinista_y_trunca():
    ad = SimulatedAdapter("sim", oracle=_oraculo_log(), profile="debil", seed=3)
    r1 = ad.generate("s", "u", max_tokens=4000, temperature=0.7, seed=11)
    r2 = ad.generate("s", "u", max_tokens=4000, temperature=0.7, seed=11)
    assert r1["text"] == r2["text"] and set(r1) == CLAVES_RESULTADO
    assert r1["raw"]["simulado"] is True
    distintas = {ad.generate("s", "u", max_tokens=4000, temperature=0.7, seed=k)["text"] for k in range(20)}
    assert len(distintas) > 1                      # la semilla de la muestra cambia las fallas inyectadas
    corto = ad.generate("s", "u", max_tokens=30, temperature=0.7, seed=11)
    assert corto["stop_reason"] == "max_tokens" and corto["output_tokens"] <= 30


def test_simulado_perfecto_produce_referencia():
    from minifmt import parse
    ad = SimulatedAdapter("sim", oracle=_oraculo_log(), profile="perfecto")
    r = ad.generate("s", "u", max_tokens=4000, temperature=0)
    doc = parse(r["text"], REG.get("log"))
    assert len(doc.records) == 12 and r["raw"]["fallas"] == []


def test_simulado_sin_modo_estructurado():
    ad = SimulatedAdapter("sim", structured=False)
    with pytest.raises(AdapterError):
        ad.generate("s", "u", max_tokens=10, temperature=0, response_format=RF)
    assert SimulatedAdapter("sim").generate("s", "u", max_tokens=10, temperature=0)["text"] == "OK"
