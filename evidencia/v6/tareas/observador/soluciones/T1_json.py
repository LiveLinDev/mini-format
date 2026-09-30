"""Solución de referencia T1 (condición JSON). Solo observador."""
import json
import sys

from jsonschema import Draft7Validator


def procesar(texto: str, esquema: dict, clave: str) -> dict:
    datos = json.loads(texto)
    validador = Draft7Validator(esquema)
    validos, rechazados = [], []
    for i, registro in enumerate(datos[clave], start=1):
        errores = sorted(validador.iter_errors(registro), key=lambda e: list(e.path))
        if errores:
            rechazados.append({"posicion": i, "motivo": errores[0].message})
        else:
            validos.append(registro)
    return {"validos": validos, "rechazados": rechazados}


if __name__ == "__main__":
    respuesta, esquema, clave = sys.argv[1:4]
    with open(respuesta, encoding="utf-8") as fh:
        texto = fh.read()
    with open(esquema, encoding="utf-8") as fh:
        esq = json.load(fh)
    print(json.dumps(procesar(texto, esq, clave), ensure_ascii=False))
