"""Tokenizadores locales (sin red) para el estudio de optimización.

Cuentan el texto COMPLETO que se transmitiría con los vocabularios BPE archivados en
``benchmark/vocab`` (sha256 verificado contra los hashes oficiales de tiktoken):

* ``o200k_base``, ``cl100k_base`` y ``r50k_base`` (GPT-2).

Son conteos locales de texto: aproximan, y no reemplazan, el conteo de solicitud ni el ``usage`` de
un proveedor. Para los modelos que no son de OpenAI (Anthropic, Google, DeepSeek...) son solo una
aproximación. Nunca se estima por caracteres/4.

Con ``tiktoken`` instalado se construye un ``Encoding`` desde los archivos locales (exacto, rápido);
si falta, se usa el BPE en Python puro del proyecto (mismos rangos y mismo patrón, más lento).
"""
from __future__ import annotations

import hashlib
import sys
from pathlib import Path
from typing import Dict, List, Optional

RAIZ = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RAIZ / "src"))

VOCAB = RAIZ / "benchmark" / "vocab"

NOMBRES = ("o200k_base", "cl100k_base", "r50k_base")

# sha256 de cada archivo de vocabulario = expected_hash oficial de tiktoken_ext.openai_public
SHA256_VOCAB = {
    "o200k_base": "446a9538cb6c348e3516120d7c08b09f57c36495e2acfffe59a5bf8b0cfb1a2d",
    "cl100k_base": "223921b76ee99bde995b7ff738513eef100fb51d18c93597a113bcffe865b2a7",
    "r50k_base": "306cd27f03c1a714eca7108e03d66b7dc042abe8c258b44c199a7ed9838dd930",
}

# Patrones oficiales de pre-tokenización (tiktoken_ext/openai_public.py)
PATRON_R50K = r"""'(?:[sdmt]|ll|ve|re)| ?\p{L}+| ?\p{N}+| ?[^\s\p{L}\p{N}]+|\s+(?!\S)|\s+"""
ESPECIALES = {"r50k_base": {"<|endoftext|>": 50256}}


def _patron(nombre: str) -> str:
    if nombre == "r50k_base":
        return PATRON_R50K
    from minifmt.tokens import PATTERNS
    return PATTERNS[nombre]


def sha256_vocab(nombre: str) -> str:
    return hashlib.sha256((VOCAB / f"{nombre}.tiktoken").read_bytes()).hexdigest()


class Tokenizador:
    """``contar(texto)`` = número de tokens del texto completo."""

    def __init__(self, nombre: str, forzar_puro: bool = False):
        if nombre not in NOMBRES:
            raise ValueError(f"tokenizador desconocido: {nombre}")
        self.nombre = nombre
        ruta = VOCAB / f"{nombre}.tiktoken"
        self.sha256_vocabulario = sha256_vocab(nombre)
        if self.sha256_vocabulario != SHA256_VOCAB[nombre]:
            raise RuntimeError(f"vocabulario {ruta.name} alterado: sha256 {self.sha256_vocabulario}")
        self._enc = None
        self._puro = None
        self.paquete: Optional[str] = None
        self.version: Optional[str] = None
        if not forzar_puro:
            try:
                import tiktoken
                from tiktoken.load import load_tiktoken_bpe
                rangos = load_tiktoken_bpe(str(ruta))
                self._enc = tiktoken.Encoding(name=nombre, pat_str=_patron(nombre), mergeable_ranks=rangos,
                                              special_tokens=ESPECIALES.get(nombre, {}))
                self.backend = "tiktoken(vocabulario local)"
                self.paquete, self.version = "tiktoken", getattr(tiktoken, "__version__", None)
            except Exception:
                self._enc = None
        if self._enc is None:
            from minifmt.tokens import _PurePythonBPE, _load_ranks
            self._puro = _PurePythonBPE(nombre, _load_ranks(ruta), _patron(nombre))
            self.backend = "python-puro(vocabulario local)"
            self.paquete, self.version = "regex", None
            try:
                from importlib import metadata
                self.version = metadata.version("regex")
            except Exception:
                pass

    def contar(self, texto: str) -> int:
        if self._enc is not None:
            return len(self._enc.encode(texto, disallowed_special=()))
        return self._puro.count(texto)  # type: ignore[union-attr]

    def ids(self, texto: str) -> List[int]:
        if self._enc is not None:
            return self._enc.encode(texto, disallowed_special=())
        return self._puro.encode(texto)  # type: ignore[union-attr]

    def describir(self) -> Dict[str, object]:
        return {"nombre": self.nombre, "paquete": self.paquete, "version": self.version,
                "vocabulario_sha256": self.sha256_vocabulario, "tipo": "aproximacion",
                "backend": self.backend}


_CACHE: Dict[str, Tokenizador] = {}


def obtener(nombre: str) -> Tokenizador:
    if nombre not in _CACHE:
        _CACHE[nombre] = Tokenizador(nombre)
    return _CACHE[nombre]


def todos() -> Dict[str, Tokenizador]:
    return {n: obtener(n) for n in NOMBRES}
