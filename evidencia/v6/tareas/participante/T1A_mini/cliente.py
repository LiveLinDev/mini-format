"""T1: completa procesar(texto). Puedes usar este archivo o escribir tu cliente en TypeScript."""
import json
import os

RESPUESTA = "respuesta.mini"
SALIDA = os.path.join("entrega", "salida_T1.json")


def procesar(texto: str) -> dict:
    """Devuelve {"validos": [...], "rechazados": [{"posicion": int, "motivo": str}]}."""
    raise NotImplementedError


if __name__ == "__main__":
    with open(RESPUESTA, encoding="utf-8") as fh:
        resultado = procesar(fh.read())
    os.makedirs("entrega", exist_ok=True)
    with open(SALIDA, "w", encoding="utf-8") as fh:
        json.dump(resultado, fh, ensure_ascii=False, indent=2)
