#!/usr/bin/env python3
"""Reconstruye los objetos de la aplicación desde una respuesta .mini especializada, con su mapa explícito.

Es INDEPENDIENTE de experiments/optimizacion: solo usa la biblioteca minifmt y la biblioteca estándar.
Lee ``contrato_especializado.json`` y ``mapa.json`` de la carpeta de un dominio, valida la respuesta con el
contrato (modo estricto) y aplica el mapa campo por campo, en el orden original de claves.

    python examples/optimizacion/reconstruir.py tickets
    python examples/optimizacion/reconstruir.py eventos --mini otra_respuesta.mini --esperado otros_datos.json

Si ``--esperado`` (por omisión, ``datos_originales.json``) existe, compara el resultado con él: mismos valores,
mismos TIPOS y mismo orden de claves. Sale con código 1 si algo falla. Sin red ni claves.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List

AQUI = Path(__file__).resolve().parent
sys.path.insert(0, str(AQUI.parents[1] / "src"))

from minifmt import parse  # noqa: E402
from minifmt.contract import Contract  # noqa: E402
from minifmt.errors import MiniValidationError  # noqa: E402


def decodificar_valor(campo: Dict[str, Any], valor: Any) -> Any:
    t = campo["tratamiento"]
    if t == "pasa":
        return valor
    if t == "codigos":
        inverso = {codigo: etiqueta for etiqueta, codigo in campo["codigos"].items()}
        return inverso[valor]
    if t == "id_prefijo":
        ancho = campo["ancho"]
        return campo["prefijo"] + (str(valor).zfill(ancho) if ancho else str(valor))
    if t == "escalado":
        return valor / campo["factor"]
    if t == "hhmm":
        return f"{valor // 60:02d}:{valor % 60:02d}"
    raise ValueError(f"tratamiento desconocido: {t}")


def reconstruir(directorio: Path, texto_mini: str) -> List[Dict[str, Any]]:
    mapa = json.loads((directorio / "mapa.json").read_text(encoding="utf-8"))
    contrato = Contract.load(directorio / "contrato_especializado.json")
    doc = parse(texto_mini, contrato, strict=True)          # E10, E13, E04... si algo no cumple el contrato
    canonico = doc.to_canonical()
    cabecera = canonico["header"]
    salida = []
    for reg in canonico["records"]:
        objeto: Dict[str, Any] = {}
        for campo in mapa["campos"]:                        # orden ORIGINAL de claves del objeto
            if campo["tratamiento"] == "constante":
                objeto[campo["campo"]] = cabecera[campo["clave_cabecera"]]
            else:
                objeto[campo["campo"]] = decodificar_valor(campo, reg[campo["nombre_en_contrato"]])
        salida.append(objeto)
    return salida


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("dominio", help="carpeta del dominio (p. ej. tickets)")
    ap.add_argument("--mini", help="respuesta .mini (por omisión respuesta_especializada.mini)")
    ap.add_argument("--esperado", help="JSON con los objetos esperados (por omisión datos_originales.json)")
    args = ap.parse_args(argv)
    d = Path(args.dominio)
    if not d.is_dir():
        d = AQUI / args.dominio
    mini = Path(args.mini) if args.mini else d / "respuesta_especializada.mini"
    try:
        objetos = reconstruir(d, mini.read_text(encoding="utf-8"))
    except MiniValidationError as e:
        for err in e.errors:
            print(err)
        print(f"INVALIDO: {len(e.errors)} error(es)")
        return 1
    print(f"OK: {len(objetos)} registros reconstruidos desde {mini.name}")
    esperado = Path(args.esperado) if args.esperado else d / "datos_originales.json"
    if esperado.exists():
        ref = json.loads(esperado.read_text(encoding="utf-8"))
        if json.dumps(objetos, ensure_ascii=False, separators=(",", ":")) != json.dumps(ref, ensure_ascii=False, separators=(",", ":")):
            print(f"FALLA: la reconstrucción no es idéntica a {esperado.name} (valores, tipos u orden de claves)")
            return 1
        print(f"OK: idénticos a {esperado.name} (valores, tipos y orden de claves)")
    else:
        print(json.dumps(objetos[:3], ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
