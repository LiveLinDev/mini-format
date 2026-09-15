"""Intervalos de confianza para proporciones."""
from __future__ import annotations

import math
from typing import Tuple

Z95 = 1.959963984540054


def wilson(exitos: int, n: int, z: float = Z95) -> Tuple[float, float, float]:
    """Proporción e intervalo de Wilson (por defecto al 95 %). Devuelve (p, inferior, superior)."""
    if n <= 0:
        return (float("nan"), float("nan"), float("nan"))
    if exitos < 0 or exitos > n:
        raise ValueError(f"éxitos fuera de rango: {exitos}/{n}")
    p = exitos / n
    den = 1 + z * z / n
    centro = (p + z * z / (2 * n)) / den
    medio = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / den
    lo = 0.0 if exitos == 0 else max(0.0, centro - medio)
    hi = 1.0 if exitos == n else min(1.0, centro + medio)
    return (p, lo, hi)


def fmt_ic(exitos: int, n: int, decimales: int = 1) -> str:
    p, lo, hi = wilson(exitos, n)
    if n == 0:
        return "—"
    return f"{100 * p:.{decimales}f} [{100 * lo:.{decimales}f}–{100 * hi:.{decimales}f}]"
