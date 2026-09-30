"""V3a: cortes controlados sobre salidas guardadas (sin llamadas).

Para cada muestra de V2 de los brazos generadores se corta el texto de la
respuesta en ``cortes`` posiciones aleatorias (semilla fija por muestra) y se
aplica el lector del brazo al prefijo.  Métricas por corte:

* ``recuperados``: registros correctos aceptados por el lector en el prefijo;
* ``correctos_completo``: registros correctos en la respuesta sin cortar;
* ``ideal``: ``floor(fraccion_cortada × correctos_completo)`` (misma
  aproximación que E5);
* ``eficiencia``: ``min(1, recuperados / ideal)``, o ``None`` si ``ideal`` es 0 (denominador cero: no hay nada
  recuperable, no es un fracaso ni un éxito).

V3a HEREDADA y exploratoria: corta las respuestas guardadas de cada brazo.  La V3a del Plan de Validación
(documento canónico único, fracciones predefinidas, JSON parcial y JSON Lines) es otro flujo:
``experiments/truncamiento/``.
"""
from __future__ import annotations

import hashlib
import random
from typing import Any, Dict, Iterable, List

from . import brazos as B
from . import metricas as M
from .tareas import Tarea


def cortes_muestra(muestra: Dict[str, Any], tarea: Tarea, cortes: int, semilla: int) -> List[Dict[str, Any]]:
    texto = (muestra.get("respuesta") or {}).get("text") or ""
    brazo = muestra["brazo"]
    if len(texto) < 10:
        return []
    completo = M.evaluar(B.leer(brazo, texto, tarea), tarea)["correctos"]
    h = int(hashlib.sha256(f"{semilla}|{muestra['id']}".encode("utf-8")).hexdigest()[:12], 16)
    rng = random.Random(h)
    filas = []
    L = len(texto)
    for _ in range(cortes):
        pos = rng.randint(L // 10, L - 1)
        frac = pos / L
        m = M.evaluar(B.leer(brazo, texto[:pos], tarea), tarea)
        ideal = int(frac * completo)
        filas.append({"id": muestra["id"], "tarea": muestra["tarea"], "brazo": brazo, "proveedor": muestra["proveedor"],
                      "modelo": muestra["modelo"], "fraccion": round(frac, 4), "correctos_completo": completo,
                      "recuperados": m["correctos"], "ideal": ideal,
                      "eficiencia": (min(1.0, m["correctos"] / ideal) if ideal > 0 else None),
                      "incorrectos_sin_aviso": m["incorrectos_sin_aviso"], "detectado": m["detectado"],
                      "cero": m["correctos"] == 0})
    return filas


def cortes_controlados(muestras: Iterable[Dict[str, Any]], tareas: Dict[str, Tarea], cortes: int = 20,
                       semilla: int = 7, brazos=("A", "B", "C", "D"), experimento: str = "v2") -> List[Dict[str, Any]]:
    out = []
    for s in muestras:
        if s.get("experimento") != experimento or s.get("brazo") not in brazos:
            continue
        t = tareas.get(s["tarea"])
        if t is None:
            continue
        out.extend(cortes_muestra(s, t, cortes, semilla))
    return out
