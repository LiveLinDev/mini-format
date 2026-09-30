"""Solución de referencia T1 (condición .mini). Solo observador."""
import json
import sys

from minifmt import Contract, parse


def procesar(texto: str, contrato: Contract) -> dict:
    doc = parse(texto, contrato, strict=False)
    malas = sorted({e.line for e in doc.errors if e.line > 1})
    return {
        "validos": list(doc.records),
        "rechazados": [{"posicion": ln - 1, "motivo": "; ".join(e.code + " " + e.message for e in doc.errors if e.line == ln)}
                       for ln in malas],
    }


if __name__ == "__main__":
    respuesta, contrato = sys.argv[1:3]
    with open(respuesta, encoding="utf-8") as fh:
        texto = fh.read()
    print(json.dumps(procesar(texto, Contract.load(contrato)), ensure_ascii=False))
