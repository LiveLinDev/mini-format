"""Utilidades compartidas por los experimentos V1 (tokens) y V4 (costos).

No modifica ``benchmark/`` ni ``src/``: solo los importa.
"""
from __future__ import annotations

import copy
import csv
import json
import random
import sys
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence, Tuple

ROOT = Path(__file__).resolve().parent.parent
EXP = ROOT / "experiments"
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "benchmark"))

import domains  # noqa: E402
import formats  # noqa: E402
from minifmt import Registry  # noqa: E402
from minifmt.tokens import get_tokenizer  # noqa: E402

SEMILLA = 20260914
TAMANOS = [1, 5, 10, 25, 50, 100, 250]

# Formatos del experimento (clave interna -> etiqueta en español)
FORMATOS = ["json_pretty", "json_compact", "yaml", "xml", "csv", "toon", "toon_flat", "mini"]
ETIQUETAS = {
    "json_pretty": "JSON indentado",
    "json_compact": "JSON compacto",
    "yaml": "YAML",
    "xml": "XML",
    "csv": "CSV (aplanado)",
    "toon": "TOON (oficial, tal cual)",
    "toon_flat": "TOON (aplanado, tabular)",
    "mini": ".mini",
}

def registro() -> Registry:
    return Registry.load(ROOT / "forks")


# --------------------------------------------------------------- tokenizadores
import vocab_local  # noqa: E402  (benchmark/vocab_local.py: vocabularios locales, sin red)

TOKENIZADORES_V1 = tuple(vocab_local.NOMBRES)  # o200k_base, cl100k_base, r50k_base


def tokenizadores(nombres: Sequence[str], estricto: bool = True) -> Dict[str, Any]:
    """Tokenizadores tiktoken con el vocabulario de ``benchmark/vocab`` (sin red).

    Comprueba el SHA-256 de cada vocabulario contra el oficial y activa la caché
    local de tiktoken, de modo que ni o200k_base, ni cl100k_base ni r50k_base se
    descargan. Con ``estricto`` (por defecto) un tokenizador no disponible o que
    cayera al respaldo de Python puro es un ERROR, no una omisión silenciosa.
    """
    vocab_local.preparar_cache([n for n in nombres if n in vocab_local.VOCABULARIOS])
    out: Dict[str, Any] = {}
    for n in nombres:
        try:
            t = get_tokenizer(n)
        except Exception as e:  # tokenizador desconocido o vocabulario ausente
            if estricto:
                raise RuntimeError(f"tokenizador {n} no disponible: {e!r}") from e
            print(f"AVISO: tokenizador {n} no disponible ({e!r}); se omite", flush=True)
            continue
        if estricto and t.backend != "tiktoken":
            raise RuntimeError(f"tokenizador {n}: el backend es {t.backend!r}, no tiktoken (conteo no equivalente)")
        out[n] = t
    return out


# ------------------------------------------------------------------ datos
_CLAVES_ID = {"log": ["trace"], "ner": ["doc"]}


def claves_id(prefix: str) -> List[str]:
    b = domains.BASE[prefix]
    return [b["id"]] if b["id"] else _CLAVES_ID.get(prefix, [])


def generar(prefix: str, n: int, variante: str = "muestreo", semilla: int = SEMILLA) -> Dict[str, Any]:
    """Documento sintético determinista de ``n`` registros.

    * ``ciclo``: exactamente ``domains.expand`` (protocolo original del benchmark).
    * ``muestreo``: se parte de ``domains.expand`` (identificadores frescos y
      cabecera) y el contenido de cada registro se toma de los 12 registros
      base en bloques de 12 barajados con ``random.Random(f"{semilla}:{prefix}")``
      (muestreo sin reemplazo dentro de cada bloque). Así, n=1 no es siempre
      el primer registro y el orden deja de ser periódico, pero los 12
      registros base siguen apareciendo con la misma frecuencia.
    """
    doc = domains.expand(prefix, n)
    if variante == "ciclo":
        return doc
    if variante != "muestreo":
        raise ValueError(variante)
    b = domains.BASE[prefix]
    base_recs = b["records"]
    k = len(base_recs)
    rng = random.Random(f"{semilla}:{prefix}")
    orden: List[int] = []
    while len(orden) < n:
        bloque = list(range(k))
        rng.shuffle(bloque)
        orden.extend(bloque)
    ids = claves_id(prefix)
    recs = []
    for i, r in enumerate(doc[b["records_key"]]):
        nuevo = copy.deepcopy(base_recs[orden[i]])
        for key in ids:
            nuevo[key] = r[key]
        recs.append(nuevo)
    doc[b["records_key"]] = recs
    return doc


def serializar_todos(docs: List[Dict[str, Any]], c) -> List[Dict[str, Tuple[str, Optional[bool]]]]:
    """Serializa cada documento en todos los formatos (TOON en una sola llamada a node)."""
    as_is = formats.toon_batch(docs)
    flat = formats.toon_batch([formats.flatten_doc(d, c) for d in docs])
    out = []
    for i, obj in enumerate(docs):
        out.append({
            "json_pretty": (formats.json_pretty(obj, c), None),
            "json_compact": (formats.json_compact(obj, c), None),
            "yaml": (formats.yaml_ser(obj, c), None),
            "xml": (formats.xml_ser(obj, c), None),
            "csv": (formats.csv_ser(obj, c), None),
            "toon": as_is[i],
            "toon_flat": flat[i],
            "mini": (formats.mini_ser(obj, c), None),
        })
    return out


# ------------------------------------------------------------ estadística
def bootstrap_media(valores: Sequence[float], B: int = 10000, semilla: int = SEMILLA,
                    alfa: float = 0.05) -> Tuple[float, float]:
    """IC percentil de la media re-muestreando dominios con reemplazo."""
    import numpy as np
    x = np.asarray(valores, dtype=float)
    rng = np.random.default_rng(semilla)
    idx = rng.integers(0, len(x), size=(B, len(x)))
    medias = x[idx].mean(axis=1)
    return float(np.quantile(medias, alfa / 2)), float(np.quantile(medias, 1 - alfa / 2))


def resumen(valores: Sequence[float]) -> Dict[str, float]:
    import numpy as np
    x = np.asarray(valores, dtype=float)
    lo, hi = bootstrap_media(x)
    return {"k": len(x), "media": float(x.mean()), "mediana": float(np.median(x)), "min": float(x.min()),
            "max": float(x.max()), "ic95_inf": lo, "ic95_sup": hi}


def cruce(ns: Sequence[float], ahorro: Sequence[float], umbral: float) -> float:
    """Menor n (interpolación lineal sobre la rejilla medida) con ahorro(n) ≥ umbral.

    * Si ya se cumple en el primer punto de la rejilla (n=1) se devuelve 1.
    * Si no se alcanza dentro de la rejilla se extrapola con la pendiente del
      último tramo (el crecimiento es lineal: R² ≥ 0,9999, ver ajuste_lineal.csv);
      si esa pendiente no es positiva se devuelve ``inf``.
    """
    if ahorro[0] >= umbral:
        return float(ns[0])
    for i in range(1, len(ns)):
        if ahorro[i] >= umbral:
            x0, x1, y0, y1 = ns[i - 1], ns[i], ahorro[i - 1], ahorro[i]
            return float(x0 + (umbral - y0) * (x1 - x0) / (y1 - y0))
    pend = (ahorro[-1] - ahorro[-2]) / (ns[-1] - ns[-2])
    if pend <= 0:
        return float("inf")
    return float(ns[-1] + (umbral - ahorro[-1]) / pend)


# ------------------------------------------------------------------ E/S
def escribir_csv(path: Path, filas: List[Dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    campos: List[str] = []
    for f in filas:
        for k in f:
            if k not in campos:
                campos.append(k)
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=campos, lineterminator="\n")
        w.writeheader()
        for f in filas:
            w.writerow({k: (round(v, 6) if isinstance(v, float) else v) for k, v in f.items()})


def leer_csv(path: Path) -> List[Dict[str, str]]:
    with open(path, newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))
