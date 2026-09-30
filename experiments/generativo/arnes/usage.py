"""Usage por categorías a partir de la respuesta de cada proveedor.

Estructura (acordada con el flujo de infraestructura)::

    {"entrada_sin_cache": int, "entrada_cache_lectura": int, "entrada_cache_escritura": int,
     "salida": int, "razonamiento": int|None, "razonamiento_incluido_en_salida": bool,
     "otros_usd": {nombre: "decimal"}}

Sin doble conteo:

* Anthropic informa ``input_tokens`` (sin caché), ``cache_read_input_tokens`` y
  ``cache_creation_input_tokens`` por separado; ``output_tokens`` incluye el
  pensamiento y no hay un contador de razonamiento aparte (``None``).
* OpenAI y los proveedores compatibles (Groq, DeepSeek): ``prompt_tokens`` INCLUYE los
  tokens en caché (``prompt_tokens_details.cached_tokens``), que se restan para
  obtener la entrada sin caché; ``completion_tokens`` INCLUYE el razonamiento
  (``completion_tokens_details.reasoning_tokens``).  No informan escritura de caché (0).

Si el proveedor no entrega usage, el resultado es ``None``: nunca se inventan cifras.
"""
from __future__ import annotations

from typing import Any, Dict, Mapping, Optional


def _i(v: Any) -> int:
    return int(v or 0)


def usage_de_respuesta(proveedor: str, r: Mapping[str, Any]) -> Optional[Dict[str, Any]]:
    """``r`` es el resultado común de un adaptador (con ``raw``, ``input_tokens`` y ``output_tokens``)."""
    if proveedor in ("simulado", "simulated"):
        if r.get("input_tokens") is None or r.get("output_tokens") is None:
            return None
        return {"entrada_sin_cache": _i(r["input_tokens"]), "entrada_cache_lectura": 0, "entrada_cache_escritura": 0,
                "salida": _i(r["output_tokens"]), "razonamiento": None, "razonamiento_incluido_en_salida": True,
                "otros_usd": {}, "nocional": True}
    raw = r.get("raw")
    u = raw.get("usage") if isinstance(raw, Mapping) else None
    if not isinstance(u, Mapping):
        return None
    if proveedor == "anthropic":
        if u.get("input_tokens") is None or u.get("output_tokens") is None:
            return None
        return {"entrada_sin_cache": _i(u.get("input_tokens")),
                "entrada_cache_lectura": _i(u.get("cache_read_input_tokens")),
                "entrada_cache_escritura": _i(u.get("cache_creation_input_tokens")),
                "salida": _i(u.get("output_tokens")), "razonamiento": None,
                "razonamiento_incluido_en_salida": True, "otros_usd": {}}
    if u.get("prompt_tokens") is None or u.get("completion_tokens") is None:
        return None
    det_in = u.get("prompt_tokens_details") or {}
    det_out = u.get("completion_tokens_details") or {}
    if u.get("prompt_cache_hit_tokens") is not None:            # DeepSeek informa acierto y fallo de caché por separado
        cacheados = _i(u.get("prompt_cache_hit_tokens"))
    else:
        cacheados = _i(det_in.get("cached_tokens"))
    razon = det_out.get("reasoning_tokens")
    return {"entrada_sin_cache": max(0, _i(u.get("prompt_tokens")) - cacheados),
            "entrada_cache_lectura": cacheados, "entrada_cache_escritura": 0,
            "salida": _i(u.get("completion_tokens")), "razonamiento": None if razon is None else _i(razon),
            "razonamiento_incluido_en_salida": True, "otros_usd": {}}


def es_negativa(proveedor: str, r: Mapping[str, Any]) -> bool:
    """El proveedor se negó a responder (``refusal`` de OpenAI / Anthropic, filtro de contenido)."""
    stop = (r.get("stop_reason") or "")
    if stop in ("refusal", "content_filter"):
        return True
    raw = r.get("raw")
    if isinstance(raw, Mapping):
        for ch in raw.get("choices") or []:
            if (ch.get("message") or {}).get("refusal"):
                return True
    return False
