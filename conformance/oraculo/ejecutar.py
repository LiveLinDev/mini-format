"""Ejecuta el corpus de conformidad (modos strict y lenient) contra el decodificador independiente.

    python conformance/oraculo/ejecutar.py            # resumen y lista de discrepancias
    python conformance/oraculo/ejecutar.py -v         # detalle

El oráculo no importa ``minifmt``. Un fallo aquí significa que el oráculo, escrito desde la SPEC, discrepa
de la expectativa del caso (escrita también desde la SPEC o publicada en los fixtures): hay que decidir
cuál de los dos tiene el defecto. Los modos ``dumps``, ``contract`` y ``fork`` no se ejecutan: el oráculo
solo decodifica.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Tuple

AQUI = Path(__file__).resolve().parent
RAIZ = AQUI.parent.parent
sys.path.insert(0, str(AQUI))

from decodificador import decodificar, iguales  # noqa: E402

CASOS = RAIZ / "conformance" / "cases"


def cargar_casos() -> List[Dict[str, Any]]:
    salida: List[Dict[str, Any]] = []
    for f in sorted(CASOS.glob("*.json")):
        salida.extend(json.loads(f.read_text(encoding="utf-8"))["cases"])
    return salida


def contrato_del_caso(caso: Dict[str, Any]) -> Dict[str, Any]:
    if "contract" in caso:
        return caso["contract"]
    return json.loads((RAIZ / "forks" / caso["family"] / "contract.json").read_text(encoding="utf-8"))


def pares(lista: List[Dict[str, Any]]) -> set:
    return {(e["code"], int(e["line"])) for e in lista}


def ejecutar_caso(caso: Dict[str, Any]) -> Tuple[bool, str]:
    modo, esperado = caso["mode"], caso["expected"]
    contrato = contrato_del_caso(caso)
    if modo == "strict":
        r = decodificar(caso["input"], contrato, estricto=True)
        if "errors" in esperado:
            if r.errores != pares(esperado["errors"]):
                return False, f"errores: esperado {sorted(pares(esperado['errors']))}, obtenido {sorted(r.errores)}"
            return True, ""
        if r.errores:
            return False, f"se esperaba aceptar y se obtuvo {sorted(r.errores)}"
        if not iguales(r.canonico, esperado["canonical"]):
            return False, "el objeto canónico difiere"
        return True, ""
    if modo == "lenient":
        r = decodificar(caso["input"], contrato, estricto=False)
        if r.errores != pares(esperado.get("errors", [])):
            return False, f"errores: esperado {sorted(pares(esperado.get('errors', [])))}, obtenido {sorted(r.errores)}"
        if "canonical" in esperado:
            if r.canonico is None:
                return False, "se esperaba un documento"
            clave = contrato.get("records_key", "records")
            if not iguales(r.canonico[clave], esperado["canonical"][clave]):
                return False, "los registros válidos difieren"
        elif r.canonico is not None:
            return False, "no se esperaba un documento"
        return True, ""
    return True, "omitido"


def main() -> int:
    verbose = "-v" in sys.argv
    total = fallos = omitidos = 0
    for caso in cargar_casos():
        if caso["mode"] not in ("strict", "lenient"):
            omitidos += 1
            continue
        total += 1
        ok, msg = ejecutar_caso(caso)
        if not ok:
            fallos += 1
            print(f"FALLA {caso['id']}" + (f": {msg}" if verbose else ""))
    print(f"oráculo independiente: {total - fallos}/{total} casos strict/lenient ({omitidos} de otros modos omitidos)")
    return 1 if fallos else 0


if __name__ == "__main__":
    sys.exit(main())
