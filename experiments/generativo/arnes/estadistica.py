"""Intervalos de confianza para proporciones."""
from __future__ import annotations

import math
import random
from operator import itemgetter
from typing import List, Optional, Sequence, Tuple

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


# --------------------------------------------------------------------------
# Resúmenes robustos y bootstrap por conglomerados
# --------------------------------------------------------------------------
def mediana(valores) -> Optional[float]:
    v = sorted(float(x) for x in valores if x is not None)
    if not v:
        return None
    n = len(v)
    return v[n // 2] if n % 2 else (v[n // 2 - 1] + v[n // 2]) / 2


def percentil(valores, p: float) -> Optional[float]:
    """Percentil por rango más cercano (nearest-rank): el valor ordenado de posición ceil(p·n). None si no hay datos.

    Con n < 20 el p95 coincide con el máximo; el informe debe mostrar ``n`` junto a él.
    """
    v = sorted(float(x) for x in valores if x is not None)
    if not v:
        return None
    return v[max(0, math.ceil(p * len(v)) - 1)]


def _ic_percentiles(reps: List[float], nivel: float) -> Tuple[float, float]:
    reps = sorted(reps)
    a = (1 - nivel) / 2
    lo = reps[max(0, int(math.floor(a * len(reps))))]
    hi = reps[min(len(reps) - 1, int(math.ceil((1 - a) * len(reps))) - 1)]
    return lo, hi


def bootstrap_razon(clusters: Sequence[Tuple[float, float]], *, n_boot: int = 1000, semilla: int = 12345,
                    nivel: float = 0.95) -> Tuple[Optional[float], Optional[float], Optional[float]]:
    """Razón Σnum/Σden con IC por bootstrap de CONGLOMERADOS (se remuestrean conglomerados enteros, no registros).

    Cada conglomerado es una solicitud (o un documento) con su ``(numerador, denominador)``.  Devuelve
    ``(estimación, inferior, superior)``; todo ``None`` si el denominador total es 0 (nunca 0 ni NaN).
    """
    cl = [(float(a), float(b)) for a, b in clusters if b]
    tot_d = sum(b for _, b in cl)
    if not cl or tot_d == 0:
        return None, None, None
    est = sum(a for a, _ in cl) / tot_d
    n = len(cl)
    if n == 1:
        return est, est, est
    nums = [a for a, _ in cl]
    dens = [b for _, b in cl]
    rng = random.Random(semilla)
    reps: List[float] = []
    for _ in range(n_boot):
        idx = rng.choices(range(n), k=n)
        g = itemgetter(*idx)
        d = sum(g(dens))
        if d:
            reps.append(sum(g(nums)) / d)
    if not reps:
        return est, None, None
    lo, hi = _ic_percentiles(reps, nivel)
    return est, lo, hi


def bootstrap_diferencia(pares: Sequence[Tuple[Tuple[float, float], Tuple[float, float]]], *, n_boot: int = 1000,
                         semilla: int = 12345, nivel: float = 0.95) -> Tuple[Optional[float], Optional[float], Optional[float]]:
    """Diferencia pareada de razones (segundo − primero) con IC por bootstrap de pares (conglomerados).

    ``pares`` = [((num1, den1), (num2, den2)), ...] de la MISMA unidad (misma solicitud o misma tarea/modelo/repetición).
    Un par cuyo denominador sea 0 en cualquiera de los dos lados se excluye (no cuenta como 0).
    """
    par = [(a, b) for a, b in pares if a[1] and b[1]]
    if not par:
        return None, None, None

    def dif(sel) -> Optional[float]:
        d1 = sum(par[i][0][1] for i in sel)
        d2 = sum(par[i][1][1] for i in sel)
        if not d1 or not d2:
            return None
        return sum(par[i][1][0] for i in sel) / d2 - sum(par[i][0][0] for i in sel) / d1

    n = len(par)
    est = dif(range(n))
    if n == 1 or est is None:
        return est, est, est
    rng = random.Random(semilla)
    reps = [x for x in (dif(rng.choices(range(n), k=n)) for _ in range(n_boot)) if x is not None]
    if not reps:
        return est, None, None
    lo, hi = _ic_percentiles(reps, nivel)
    return est, lo, hi
