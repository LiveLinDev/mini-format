"""Vocabularios de tiktoken desde ``benchmark/vocab``: sin red y con hash verificado.

tiktoken descarga ``<nombre>.tiktoken`` de la red salvo que exista en su caché local
un archivo cuyo nombre sea el sha1 de la URL. ``preparar_cache()`` crea esa caché
a partir de los vocabularios versionados en el repositorio (tras comprobar su
SHA-256 contra el hash oficial de ``tiktoken_ext.openai_public``) y apunta
``TIKTOKEN_CACHE_DIR`` a ella. Así ``tiktoken.get_encoding`` (y por tanto
``minifmt.tokens.get_tokenizer``) funciona igual en un clon limpio sin conexión.

``modo_sin_red()`` hace que cualquier intento de conexión HTTP falle de inmediato
(proxy inalcanzable): si algún paso intentara descargar algo, la corrida se rompe
en vez de hacerlo en silencio.
"""
from __future__ import annotations

import hashlib
import os
import shutil
import tempfile
from pathlib import Path
from typing import Any, Dict, List

VOCAB_DIR = Path(__file__).resolve().parent / "vocab"

# URL oficial y SHA-256 oficial (tiktoken_ext.openai_public) de cada vocabulario.
VOCABULARIOS: Dict[str, Dict[str, str]] = {
    "o200k_base": {
        "url": "https://openaipublic.blob.core.windows.net/encodings/o200k_base.tiktoken",
        "sha256": "446a9538cb6c348e3516120d7c08b09f57c36495e2acfffe59a5bf8b0cfb1a2d",
    },
    "cl100k_base": {
        "url": "https://openaipublic.blob.core.windows.net/encodings/cl100k_base.tiktoken",
        "sha256": "223921b76ee99bde995b7ff738513eef100fb51d18c93597a113bcffe865b2a7",
    },
    "r50k_base": {
        "url": "https://openaipublic.blob.core.windows.net/encodings/r50k_base.tiktoken",
        "sha256": "306cd27f03c1a714eca7108e03d66b7dc042abe8c258b44c199a7ed9838dd930",
    },
}
NOMBRES: List[str] = list(VOCABULARIOS)


def _sha256(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def ruta_vocabulario(nombre: str) -> Path:
    return VOCAB_DIR / f"{nombre}.tiktoken"


def verificar_vocabulario(nombre: str) -> str:
    """Devuelve el SHA-256 del vocabulario versionado; falla si no es el oficial."""
    if nombre not in VOCABULARIOS:
        raise KeyError(f"vocabulario desconocido: {nombre}")
    p = ruta_vocabulario(nombre)
    if not p.exists():
        raise FileNotFoundError(f"falta {p}: no se sustituye por una descarga")
    h = _sha256(p)
    if h != VOCABULARIOS[nombre]["sha256"]:
        raise ValueError(f"{p}: sha256 {h} distinto del oficial {VOCABULARIOS[nombre]['sha256']}")
    return h


def preparar_cache(nombres: List[str] | None = None) -> Path:
    """Crea la caché de tiktoken desde ``benchmark/vocab`` y la activa en este proceso."""
    destino = Path(tempfile.gettempdir()) / "minifmt-tiktoken-cache-v1"
    destino.mkdir(parents=True, exist_ok=True)
    for n in (nombres or NOMBRES):
        verificar_vocabulario(n)
        nombre_cache = hashlib.sha1(VOCABULARIOS[n]["url"].encode()).hexdigest()
        f = destino / nombre_cache
        if not f.exists() or _sha256(f) != VOCABULARIOS[n]["sha256"]:
            shutil.copyfile(ruta_vocabulario(n), f)
    os.environ["TIKTOKEN_CACHE_DIR"] = str(destino)
    return destino


def modo_sin_red() -> None:
    """Cualquier conexión HTTP(S) saliente de Python falla al instante."""
    for k in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "http_proxy", "https_proxy", "all_proxy"):
        os.environ[k] = "http://127.0.0.1:9"
    for k in ("NO_PROXY", "no_proxy"):
        os.environ.pop(k, None)


def info_tokenizador(nombre: str, tokenizador: Any = None) -> Dict[str, Any]:
    """Ficha del tokenizador para el manifiesto (versión, hash del vocabulario, tipo)."""
    from importlib import metadata
    try:
        version = metadata.version("tiktoken")
    except Exception:
        version = None
    return {
        "nombre": nombre,
        "paquete": "tiktoken",
        "version": version,
        "vocabulario_sha256": verificar_vocabulario(nombre),
        "vocabulario_ruta": f"benchmark/vocab/{nombre}.tiktoken",
        "backend": getattr(tokenizador, "backend", None),
        "tipo": "exacto_local",
        "nota": "conteo local de texto con el vocabulario de OpenAI; aproximación para Anthropic, Google o DeepSeek (no es su conteo de solicitud ni su usage)",
    }
