"""Corte de un texto por límite de tokens, en frontera de token, con decodificación por bytes.

Imita un ``max_tokens`` de salida: el prefijo son los primeros ``L`` tokens del texto **propio** del formato.
Como un token BPE puede partir un carácter UTF-8 multibyte, el prefijo se reconstruye con los bytes de los
tokens y se decodifica de forma incremental: una secuencia final incompleta se **descarta** (nunca se
inserta U+FFFD ni se completa).

El tokenizador es ``o200k_base`` con el vocabulario local ``benchmark/vocab/o200k_base.tiktoken`` (hash
verificado): conteo exacto de o200k, usado como unidad de referencia, no como tokenizador de ningún otro
proveedor. No descarga nada.
"""
from __future__ import annotations

import codecs
import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

RAIZ = Path(__file__).resolve().parents[2]
VOCAB_O200K = RAIZ / "benchmark" / "vocab" / "o200k_base.tiktoken"
O200K_SHA256 = "446a9538cb6c348e3516120d7c08b09f57c36495e2acfffe59a5bf8b0cfb1a2d"
# Expresión de preordenación oficial de o200k_base (tiktoken_ext.openai_public).
_PAT_O200K = "|".join([
    r"""[^\r\n\p{L}\p{N}]?[\p{Lu}\p{Lt}\p{Lm}\p{Lo}\p{M}]*[\p{Ll}\p{Lm}\p{Lo}\p{M}]+(?i:'s|'t|'re|'ve|'m|'ll|'d)?""",
    r"""[^\r\n\p{L}\p{N}]?[\p{Lu}\p{Lt}\p{Lm}\p{Lo}\p{M}]+[\p{Ll}\p{Lm}\p{Lo}\p{M}]*(?i:'s|'t|'re|'ve|'m|'ll|'d)?""",
    r"""\p{N}{1,3}""",
    r""" ?[^\s\p{L}\p{N}]+[\r\n/]*""",
    r"""\s*[\r\n]+""",
    r"""\s+(?!\S)""",
    r"""\s+""",
])


def cargar_o200k():
    """Construye ``tiktoken.Encoding`` de o200k_base desde el vocabulario local (sin red)."""
    import tiktoken
    from tiktoken.load import load_tiktoken_bpe
    if hashlib.sha256(VOCAB_O200K.read_bytes()).hexdigest() != O200K_SHA256:
        raise RuntimeError("el vocabulario o200k_base local no coincide con el hash oficial")
    rangos = load_tiktoken_bpe(str(VOCAB_O200K), expected_hash=O200K_SHA256)
    return tiktoken.Encoding(name="o200k_base", pat_str=_PAT_O200K, mergeable_ranks=rangos,
                             special_tokens={"<|endoftext|>": 199999, "<|endofprompt|>": 200018})


def limite_k(k: int, t_ref: int, pasos: int = 20) -> int:
    """``L_k = round(k/pasos × t_ref)`` con redondeo de mitad hacia arriba hecho con enteros."""
    return (2 * k * t_ref + pasos) // (2 * pasos)


@dataclass
class Segmentado:
    """Texto tokenizado con el desplazamiento en bytes donde termina cada token."""
    texto: str
    datos: bytes              # texto en UTF-8
    fin_bytes: List[int]      # fin_bytes[i]: bytes que ocupan los i+1 primeros tokens

    @property
    def n_tokens(self) -> int:
        return len(self.fin_bytes)


@dataclass
class Prefijo:
    texto: str
    n_bytes: int              # bytes UTF-8 del texto decodificado (sin la cola incompleta)
    tokens_usados: int
    truncado: bool            # el límite dejó tokens fuera
    bytes_descartados: int    # cola UTF-8 incompleta descartada (0 si el corte cayó en frontera de carácter)


def segmentar(enc, texto: str) -> Segmentado:
    ids = enc.encode(texto, disallowed_special=())
    fin: List[int] = []
    acumulado = 0
    for t in ids:
        acumulado += len(enc.decode_single_token_bytes(t))
        fin.append(acumulado)
    datos = texto.encode("utf-8")
    if acumulado != len(datos):  # la tokenización debe ser sin pérdida
        raise AssertionError("la suma de bytes de los tokens no coincide con el texto UTF-8")
    return Segmentado(texto, datos, fin)


def prefijo_por_tokens(seg: Segmentado, limite: int) -> Prefijo:
    """Primeros ``limite`` tokens del texto, decodificados por bytes (cola UTF-8 incompleta descartada)."""
    if limite < 0:
        raise ValueError("el límite no puede ser negativo")
    total = seg.n_tokens
    if limite >= total:
        return Prefijo(seg.texto, len(seg.datos), total, False, 0)
    corte = seg.fin_bytes[limite - 1] if limite > 0 else 0
    dec = codecs.getincrementaldecoder("utf-8")("strict")
    texto = dec.decode(seg.datos[:corte], final=False)
    pendientes = len(dec.getstate()[0])
    return Prefijo(texto, corte - pendientes, limite, True, pendientes)
