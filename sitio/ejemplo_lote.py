# -*- coding: utf-8 -*-
"""Datos de la página /ejemplo/: un lote grande de registros en .mini y en JSON.

El lote se genera con el mismo generador combinatorio del experimento V7, de modo que los textos
son los mismos en el sitio y en el experimento. Los tokens se cuentan con el tokenizador o200k_base
(el mismo de los benchmarks), sin llamar a ningún modelo.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Dict, List

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "experiments" / "v7_escalamiento"))

TAMANOS = (50, 200, 1000)
LIMITES = (1000, 2000, 4000)      # límites de tokens de salida que se simulan
PRIORIDADES = ("alta", "media", "baja")
MUESTRA = 8                        # registros que se muestran en pantalla


def _ticket(mensaje: Dict[str, str], i: int) -> Dict[str, Any]:
    """Ticket coherente con el mensaje: la categoría viene del generador; el resto es determinista."""
    asunto = mensaje["asunto"]
    resumen = asunto[0].upper() + asunto[1:]
    if len(resumen) > 74:
        resumen = resumen[:71].rstrip() + "..."
    return {"id": mensaje["id"], "prioridad": PRIORIDADES[(i * 7 + len(asunto)) % 3],
            "categoria": mensaje["categoria"], "resumen": resumen, "horas": 1 + (i * 3 + len(asunto)) % 8}


def _completos_mini(texto: str) -> int:
    """Registros completos en un documento .mini truncado: las líneas terminadas tras la cabecera."""
    lineas = texto.split("\n")
    return max(0, len(lineas) - 2) if not texto.endswith("\n") else max(0, len(lineas) - 2)


def _completos_json(texto: str) -> int:
    """Objetos cerrados dentro del arreglo, aunque el texto esté truncado."""
    profundidad, en_texto, escape, completos = 0, False, False, 0
    for c in texto:
        if escape:
            escape = False
        elif c == "\\":
            escape = True
        elif c == '"':
            en_texto = not en_texto
        elif not en_texto:
            if c == "{":
                profundidad += 1
            elif c == "}":
                profundidad -= 1
                if profundidad == 1:
                    completos += 1
    return completos


def _legible_json(texto: str) -> bool:
    try:
        json.loads(texto)
        return True
    except ValueError:
        return False


def datos_ejemplo() -> Dict[str, Any]:
    import entrada
    from minifmt import dumps, from_json_schema
    from minifmt.tokens import get_tokenizer

    tk = get_tokenizer("o200k_base")
    esquema = json.loads((RAIZ / "examples" / "mesa-de-ayuda" / "ticket.schema.json").read_text(encoding="utf-8"))
    contrato = from_json_schema(esquema, "tk")

    lotes: List[Dict[str, Any]] = []
    for n in TAMANOS:
        mensajes = entrada.mensajes(n)
        tickets = [_ticket(m, i) for i, m in enumerate(mensajes)]
        textos = {
            "mini": dumps({"header": {}, contrato.records_key: tickets}, contrato),
            "json": json.dumps({"tickets": tickets}, ensure_ascii=False, separators=(",", ":")),
            "json_indentado": json.dumps({"tickets": tickets}, ensure_ascii=False, indent=2),
        }
        tokens = {k: tk.count(v) for k, v in textos.items()}

        cortes = []
        for limite in LIMITES:
            corte: Dict[str, Any] = {"limite": limite}
            for formato in ("mini", "json"):
                if tokens[formato] <= limite:
                    corte[formato] = {"cabe": True, "completos": n, "aprovechables": n}
                    continue
                trozo = _prefijo(textos[formato], limite, tk)
                if formato == "mini":
                    completos = _completos_mini(trozo)
                    corte[formato] = {"cabe": False, "completos": completos, "aprovechables": completos}
                else:
                    completos = _completos_json(trozo)
                    corte[formato] = {"cabe": False, "completos": completos,
                                      "aprovechables": completos if _legible_json(trozo) else 0}
            cortes.append(corte)

        lineas_mini = textos["mini"].split("\n")
        lotes.append({
            "n": n,
            "tokens": tokens,
            "bytes": {k: len(v.encode("utf-8")) for k, v in textos.items()},
            "por_registro": {k: round(v / n, 1) for k, v in tokens.items()},
            "ahorro": {k: round(100 * (tokens[k] - tokens["mini"]) / tokens[k], 1) for k in ("json", "json_indentado")},
            "muestra": {
                "mini": "\n".join(lineas_mini[:MUESTRA + 1]),
                "json": json.dumps({"tickets": tickets[:MUESTRA]}, ensure_ascii=False, indent=2),
            },
            "cortes": cortes,
        })

    return {"lotes": lotes, "tamanos": list(TAMANOS), "limites": list(LIMITES), "muestra": MUESTRA,
            "semilla": entrada.SEMILLA, "entrada": entrada.ENTRADA_VERSION,
            "combinaciones": entrada.combinaciones(), "contrato": contrato.to_dict(),
            "campos": [f.name for f in contrato.fields], "tokenizador": "o200k_base"}


def _prefijo(texto: str, limite: int, tk) -> str:
    """El trozo más largo del texto que cabe en el límite de tokens (búsqueda binaria, sin decodificar)."""
    bajo, alto = 0, len(texto)
    while bajo < alto:
        medio = (bajo + alto + 1) // 2
        if tk.count(texto[:medio]) <= limite:
            bajo = medio
        else:
            alto = medio - 1
    return texto[:bajo]
