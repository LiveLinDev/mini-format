"""Token counting.

Uses the official ``tiktoken`` package when it is installed.  Otherwise it
falls back to a pure-Python byte-pair encoder that loads the *official*
OpenAI rank files vendored in ``benchmark/vocab`` (``o200k_base.tiktoken``,
sha256 446a9538…; ``cl100k_base.tiktoken``) and applies the official
pre-tokenisation regular expressions published in
``tiktoken_ext/openai_public.py``.  The fallback is exact (same ranks, same
regex, same merge rule) but slower; it exists so that the benchmark can be
reproduced in sandboxes without access to package registries.
"""
from __future__ import annotations

import base64
import functools
from pathlib import Path
from typing import Dict, List, Optional

VOCAB_DIR = Path(__file__).resolve().parent.parent.parent / "benchmark" / "vocab"

# Official patterns (OpenAI tiktoken, tiktoken_ext/openai_public.py)
PATTERNS = {
    "cl100k_base": r"""'(?i:[sdmt]|ll|ve|re)|[^\r\n\p{L}\p{N}]?+\p{L}++|\p{N}{1,3}+| ?[^\s\p{L}\p{N}]++[\r\n]*+|\s++$|\s*[\r\n]|\s+(?!\S)|\s""",
    "o200k_base": "|".join([
        r"""[^\r\n\p{L}\p{N}]?[\p{Lu}\p{Lt}\p{Lm}\p{Lo}\p{M}]*[\p{Ll}\p{Lm}\p{Lo}\p{M}]+(?i:'s|'t|'re|'ve|'m|'ll|'d)?""",
        r"""[^\r\n\p{L}\p{N}]?[\p{Lu}\p{Lt}\p{Lm}\p{Lo}\p{M}]+[\p{Ll}\p{Lm}\p{Lo}\p{M}]*(?i:'s|'t|'re|'ve|'m|'ll|'d)?""",
        r"""\p{N}{1,3}""",
        r""" ?[^\s\p{L}\p{N}]+[\r\n/]*""",
        r"""\s*[\r\n]+""",
        r"""\s+(?!\S)""",
        r"""\s+""",
    ]),
}


class _PurePythonBPE:
    def __init__(self, name: str, ranks: Dict[bytes, int], pat_str: str):
        import regex  # third-party 'regex' supports \p{..} classes

        self.name = name
        self.ranks = ranks
        self._pat = regex.compile(pat_str)
        self._cache: Dict[bytes, int] = {}

    def _bpe_len(self, piece: bytes) -> int:
        if piece in self.ranks:
            return 1
        hit = self._cache.get(piece)
        if hit is not None:
            return hit
        parts = [bytes([b]) for b in piece]
        ranks = self.ranks
        while len(parts) > 1:
            best_i, best_r = -1, None
            for i in range(len(parts) - 1):
                r = ranks.get(parts[i] + parts[i + 1])
                if r is not None and (best_r is None or r < best_r):
                    best_i, best_r = i, r
            if best_r is None:
                break
            parts[best_i:best_i + 2] = [parts[best_i] + parts[best_i + 1]]
        n = len(parts)
        if len(self._cache) < 500_000:
            self._cache[piece] = n
        return n

    def count(self, text: str) -> int:
        total = 0
        for m in self._pat.finditer(text):
            total += self._bpe_len(m.group().encode("utf-8"))
        return total

    def encode(self, text: str) -> List[int]:  # pragma: no cover - not needed for counting
        out: List[int] = []
        for m in self._pat.finditer(text):
            piece = m.group().encode("utf-8")
            if piece in self.ranks:
                out.append(self.ranks[piece]); continue
            parts = [bytes([b]) for b in piece]
            while len(parts) > 1:
                best_i, best_r = -1, None
                for i in range(len(parts) - 1):
                    r = self.ranks.get(parts[i] + parts[i + 1])
                    if r is not None and (best_r is None or r < best_r):
                        best_i, best_r = i, r
                if best_r is None:
                    break
                parts[best_i:best_i + 2] = [parts[best_i] + parts[best_i + 1]]
            out.extend(self.ranks[p] for p in parts)
        return out


def _load_ranks(path: Path) -> Dict[bytes, int]:
    ranks: Dict[bytes, int] = {}
    with open(path, "rb") as fh:
        for line in fh:
            if not line.strip():
                continue
            tok, rank = line.split()
            ranks[base64.b64decode(tok)] = int(rank)
    return ranks


class Tokenizer:
    """Thin wrapper exposing ``count(text)`` and ``.backend``."""

    def __init__(self, name: str = "o200k_base", vocab_dir: Optional[Path] = None):
        self.name = name
        try:
            import tiktoken  # type: ignore
            self._enc = tiktoken.get_encoding(name)
            self.backend = "tiktoken"
            self._pp = None
        except Exception:
            vd = Path(vocab_dir) if vocab_dir else VOCAB_DIR
            self._pp = _PurePythonBPE(name, _load_ranks(vd / f"{name}.tiktoken"), PATTERNS[name])
            self._enc = None
            self.backend = "pure-python"

    def count(self, text: str) -> int:
        if self._enc is not None:
            return len(self._enc.encode(text, disallowed_special=()))
        return self._pp.count(text)  # type: ignore[union-attr]

    def encode(self, text: str) -> List[int]:
        if self._enc is not None:
            return self._enc.encode(text, disallowed_special=())
        return self._pp.encode(text)  # type: ignore[union-attr]


@functools.lru_cache(maxsize=4)
def get_tokenizer(name: str = "o200k_base") -> Tokenizer:
    return Tokenizer(name)


def count_tokens(text: str, name: str = "o200k_base") -> int:
    return get_tokenizer(name).count(text)
