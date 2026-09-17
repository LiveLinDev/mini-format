# -*- coding: utf-8 -*-
"""Costo del formato, sin llamar a ningún modelo: tokens por registro y quiebre teórico.

Separa las dos cosas que se mezclan en una corrida real:

* el **costo del formato** — cuántos tokens ocupa el mismo registro escrito en .mini, en JSON
  compacto y en JSON indentado. Es aritmética del tokenizador, reproducible y gratuita.
* el **quiebre teórico** — cuántos registros caben en el límite de salida del modelo según esa
  tasa. La corrida real lo desplaza porque el modelo escribe resúmenes de largo variable, y esa
  diferencia es, precisamente, lo que aporta el experimento con modelo.

    python experiments/v7_escalamiento/tokens.py --n 2000 --limite 8192
"""
from __future__ import annotations

import argparse
import json
import statistics
import sys
from pathlib import Path

AQUI = Path(__file__).resolve().parent
RAIZ = AQUI.parents[1]
sys.path.insert(0, str(RAIZ / "src"))
sys.path.insert(0, str(AQUI))

from minifmt import dumps, from_json_schema                  # noqa: E402
from minifmt.tokens import count_tokens                      # noqa: E402

from entrada import ENTRADA_VERSION, PROBLEMAS, mensajes     # noqa: E402

ESQUEMA = RAIZ / "examples" / "mesa-de-ayuda" / "ticket.schema.json"
PRIORIDADES = ["baja", "media", "alta"]


def categoria_de(texto: str) -> str:
    """Categoría del problema que originó el mensaje (el generador las conoce)."""
    for plantilla, cat in PROBLEMAS:
        nucleo = plantilla.replace("{p}", "").strip(" .")[:28]
        if nucleo and nucleo in texto:
            return cat
    return "consulta"


def resumen_de(texto: str) -> str:
    """Resumen como el que escribe el modelo: la frase del problema, sin saludo ni cierre."""
    cuerpo = texto.split(",", 1)[-1].strip()
    cuerpo = cuerpo.split(".")[0].strip()
    return (cuerpo[:1].upper() + cuerpo[1:])[:90]


def tickets(n: int):
    out = []
    for i, m in enumerate(mensajes(n)):
        out.append({"id": m["id"], "prioridad": PRIORIDADES[i % 3], "categoria": categoria_de(m["mensaje"]),
                    "resumen": resumen_de(m["mensaje"]), "horas": 1 + (i % 8)})
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=2000)
    ap.add_argument("--limite", type=int, default=8192, help="límite de tokens de salida del modelo")
    a = ap.parse_args()

    contrato = from_json_schema(json.loads(ESQUEMA.read_text(encoding="utf-8")), "tk")
    regs = tickets(a.n)
    doc_mini = dumps({"header": {"n": len(regs)}, "records": regs}, contrato)
    doc_json = json.dumps({"tickets": regs}, ensure_ascii=False, separators=(",", ":"))
    doc_json_ind = json.dumps({"tickets": regs}, ensure_ascii=False, indent=2)

    formatos = {".mini": doc_mini, "JSON compacto": doc_json, "JSON indentado": doc_json_ind}
    print(f"entrada: {ENTRADA_VERSION}")
    print(f"registros: {len(regs):,} · tokenizador o200k_base · límite de salida {a.limite:,}\n")
    print(f"{'formato':16} {'tokens':>10} {'por registro':>13} {'caben en el límite':>19} {'vs .mini':>9}")
    base = None
    for nombre, doc in formatos.items():
        tot = count_tokens(doc)
        por = tot / len(regs)
        caben = int(a.limite // por)
        if base is None:
            base = por
        print(f"{nombre:16} {tot:>10,} {por:>13.2f} {caben:>19,} {por / base:>8.2f}×")

    largos = [count_tokens(l) for l in doc_mini.split("\n")[1:] if l.strip()]
    print(f"\nlínea .mini: mediana {statistics.median(largos):.1f} tokens · "
          f"mín {min(largos)} · máx {max(largos)} · desviación {statistics.pstdev(largos):.1f}")
    print("Esta tasa es la del formato. Con un modelo real, la longitud del resumen varía y el quiebre "
          "se adelanta: por eso el experimento con modelo mide menos registros por llamada que este cálculo.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
