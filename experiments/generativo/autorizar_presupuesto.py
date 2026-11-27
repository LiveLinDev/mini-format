"""Escribe la autorización de gasto en el bloque ``presupuesto`` de una configuración del arnés.

La firma la da la persona que autoriza, al ejecutar ``correr_v2v3b.ps1``; este programa solo la deja registrada en el
YAML (autorizado_usd, firmado_por y fecha), sin tocar el diseño del estudio. El presupuesto no forma parte del
manifiesto congelado, por lo que autorizar no cambia el diseño.

Uso: python experiments/generativo/autorizar_presupuesto.py CONFIG.yaml TOPE_USD "Nombre de quien autoriza"
"""
from __future__ import annotations

import re
import sys
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path


def autorizar(ruta: Path, tope: Decimal, firma: str, fecha: str) -> str:
    texto = ruta.read_text(encoding="utf-8")
    bloque = re.search(r"(?ms)^presupuesto:\n(?:  .*\n)+", texto)
    if not bloque:
        raise SystemExit(f"{ruta}: no tiene bloque presupuesto")
    nuevo = (f"presupuesto:\n  autorizado_usd: {tope}\n  por_celda_max_usd: null\n"
             f"  firmado_por: \"{firma}\"\n  fecha: \"{fecha}\"\n")
    return texto[:bloque.start()] + nuevo + texto[bloque.end():]


def main(argv: list[str]) -> int:
    if len(argv) != 4:
        print(__doc__)
        return 2
    ruta, firma = Path(argv[1]), argv[3].strip()
    try:
        tope = Decimal(argv[2].replace(",", "."))
    except InvalidOperation:
        raise SystemExit("el tope debe ser un número en USD")
    if tope <= 0 or not firma:
        raise SystemExit("hace falta un tope mayor que 0 y el nombre de quien autoriza")
    fecha = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    texto = autorizar(ruta, tope, firma, fecha)  # se lee antes de abrir para escribir
    with open(ruta, "w", encoding="utf-8", newline="\n") as f:
        f.write(texto)
    print(f"{ruta.name}: autorizado {tope} USD por {firma} ({fecha})")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
