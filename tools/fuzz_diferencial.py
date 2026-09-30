"""Fuzz diferencial de .mini: Python (minifmt) contra js/mini.js contra el oráculo independiente.

    python tools/fuzz_diferencial.py                      # presupuesto por omisión: 100 s
    python tools/fuzz_diferencial.py --presupuesto 30     # segundos (máximo 120)
    python tools/fuzz_diferencial.py --documentos 4000    # cuenta fija (reproducible al bit)
    python tools/fuzz_diferencial.py --semilla 7 --salida resumen.json

Toma como base los fixtures oficiales de las catorce familias y los casos strict/lenient de la suite de
conformidad, y produce mutantes deterministas (semilla fija) insertando, borrando, cortando o duplicando
trozos con un alfabeto de caracteres hostiles (``| , * \\ " ; =``, escapes, espacios Unicode, BOM, CR...).
Cada documento se analiza en modo tolerante con los tres motores y se comparan el objeto canónico y el
conjunto de pares (código, línea).

Todo el trabajo intermedio va a un directorio temporal que se borra al terminar (la versión de la auditoría
dejaba ficheros de 80 MB). Sale con 1 si hay una divergencia que no figure en ``DIFERENCIAS_CONOCIDAS`` o una
excepción no controlada en cualquiera de los motores. Las cuentas por clase se imprimen siempre.

Con ``--presupuesto`` el número de documentos depende de la velocidad de la máquina (la semilla y el orden
son fijos, así que los primeros N documentos son siempre los mismos); usar ``--documentos`` para comparar
ejecuciones.
"""
from __future__ import annotations

import argparse
import json
import random
import shutil
import subprocess
import sys
import tempfile
import time
from collections import Counter
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional, Tuple

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "src"))
sys.path.insert(0, str(RAIZ / "conformance" / "oraculo"))

from minifmt import Contract, MiniError, MiniValidationError, Registry, parse  # noqa: E402

from decodificador import decodificar, iguales  # noqa: E402

SEMILLA_POR_OMISION = 20260930
PRESUPUESTO_MAXIMO = 120.0
LOTE = 1500

ALFABETO = ["|", ",", "*", "\\", "\n", '"', ";", "=", " ", "\t", "\r", "\r\n", "\\n", "\\,", "\\|", "\\*", '\\"', "\\\\",
            '""', "\u0085", "\u001c", "\u00a0", "\u2028", "\u3000", "\ufeff", "\u200b", "\u000b", "\u000c",
            "á", "ñ", "€", "\U0001F600", "é", "١", "５", "0", "1", "-", "+", ".", "e", "E", "9", "x", "NaN"]

# Diferencias entre motores que están documentadas y no son defectos (clave -> explicación).
DIFERENCIAS_CONOCIDAS = {
    "vacio_python_lanza": "documento vacío en modo tolerante: Python lanza E01, TypeScript devuelve un Document con E01 (ts/README)",
    "entero_grande": "entero fuera de ±2^53: Python exacto, TypeScript/JS aproximado (ADR 0018, propuesta)",
}


def mutar(texto: str, rng: random.Random) -> str:
    s = texto
    for _ in range(rng.randint(1, 4)):
        op = rng.random()
        if not s:
            s = rng.choice(ALFABETO)
            continue
        i = rng.randrange(len(s) + 1)
        if op < 0.40:
            s = s[:i] + rng.choice(ALFABETO) + s[i:]
        elif op < 0.60:
            s = s[:i] + s[min(len(s), i + rng.randint(1, 3)):]
        elif op < 0.75:
            s = s[:i]
        elif op < 0.90:
            lineas = s.split("\n")
            k = rng.randrange(len(lineas))
            lineas.insert(k, lineas[k])
            s = "\n".join(lineas)
        else:
            j = min(len(s), i + rng.randint(1, 6))
            s = s[:i] + s[i:j] * 2 + s[j:]
    return s


def documentos_base() -> Tuple[Dict[str, dict], List[Tuple[str, str, str]]]:
    """Contratos (por clave) y documentos base (etiqueta, clave de contrato, texto)."""
    contratos: Dict[str, dict] = {}
    docs: List[Tuple[str, str, str]] = []
    reg = Registry.load(RAIZ / "forks")
    for c in reg:
        clave = "fam:" + c.prefix
        contratos[clave] = json.loads((reg.paths[c.prefix] / "contract.json").read_text(encoding="utf-8"))
        for f in sorted((reg.paths[c.prefix] / "fixtures").glob("*.mini")):
            docs.append((f"{c.prefix}/{f.name}", clave, f.read_text(encoding="utf-8")))
    for archivo in sorted((RAIZ / "conformance" / "cases").glob("*.json")):
        for caso in json.loads(archivo.read_text(encoding="utf-8"))["cases"]:
            if caso["mode"] not in ("strict", "lenient"):
                continue
            if "contract" in caso:
                clave = "caso:" + caso["id"]
                contratos[clave] = caso["contract"]
            else:
                clave = "fam:" + caso["family"]
            docs.append((f"caso/{caso['id']}", clave, caso["input"]))
    return contratos, docs


def generar(docs: List[Tuple[str, str, str]], semilla: int) -> Iterator[Dict[str, Any]]:
    """Flujo determinista de entradas: primero los originales, luego rondas de un mutante por documento."""
    for etiqueta, clave, texto in docs:
        yield {"label": etiqueta, "contract": clave, "text": texto, "mut": False}
    rng = random.Random(semilla)
    ronda = 0
    while True:
        for etiqueta, clave, texto in docs:
            yield {"label": f"{etiqueta}#r{ronda}", "contract": clave, "text": mutar(texto, rng), "mut": True}
        ronda += 1


def analizar_python(entrada: Dict[str, Any], contratos_py: Dict[str, Contract]) -> Dict[str, Any]:
    try:
        d = parse(entrada["text"], contratos_py[entrada["contract"]], strict=False)
        return {"canon": d.to_canonical(), "errs": sorted({(e.code, e.line) for e in d.errors})}
    except MiniValidationError as e:
        return {"canon": None, "errs": sorted({(x.code, x.line) for x in e.errors}), "lanzo": True}
    except MiniError as e:
        return {"canon": None, "errs": [(e.code, e.line)], "lanzo": True}
    except Exception as e:  # defecto: excepción no controlada
        return {"pyexc": f"{type(e).__name__}: {str(e)[:100]}"}


def analizar_js(lote: List[Dict[str, Any]], contratos: Dict[str, dict], tmp: Path, node: str) -> List[Dict[str, Any]]:
    entrada, salida = tmp / "lote.json", tmp / "lote_js.json"
    usados = {e["contract"] for e in lote}
    entrada.write_text(json.dumps({"contracts": {k: contratos[k] for k in usados}, "inputs": lote}, ensure_ascii=False),
                       encoding="utf-8")
    proc = subprocess.run([node, "--no-warnings", str(RAIZ / "tools" / "fuzz_motor_js.mjs"), str(entrada), str(salida)],
                          capture_output=True, text=True, encoding="utf-8")
    if proc.returncode != 0:
        raise RuntimeError(f"node falló: {proc.stderr[:400]}")
    resultado = json.loads(salida.read_text(encoding="utf-8"))
    entrada.unlink()
    salida.unlink()
    return resultado


def _pares(x: Dict[str, Any]) -> List[Tuple[str, int]]:
    return sorted((c, int(l)) for c, l in x.get("errs", []))


def _enteros_grandes(valor: Any) -> bool:
    if isinstance(valor, bool):
        return False
    if isinstance(valor, int):
        return abs(valor) > 2 ** 53
    if isinstance(valor, float):
        return abs(valor) >= 2 ** 53
    if isinstance(valor, list):
        return any(_enteros_grandes(v) for v in valor)
    if isinstance(valor, dict):
        return any(_enteros_grandes(v) for v in valor.values())
    return False


def comparar(entrada: Dict[str, Any], py: Dict[str, Any], js: Dict[str, Any], contrato: dict) -> List[str]:
    """Clases de divergencia de esta entrada (lista vacía: los tres motores coinciden)."""
    clases: List[str] = []
    if "pyexc" in py:
        clases.append("excepcion_python")
    if "jsexc" in js:
        clases.append("excepcion_js")
    if clases:
        return clases
    orc = decodificar(entrada["text"], contrato, estricto=False)
    # --- Python frente a js/mini.js
    if _pares(py) == [("E01", 0)] and _pares(js) == [("E01", 0)] and py.get("lanzo") and py["canon"] is None:
        pass  # diferencia de API documentada (vacío en modo tolerante)
    elif _pares(py) != _pares(js):
        clases.append("py_js_errores")
    elif not iguales(py.get("canon"), js.get("canon")):
        clases.append("py_js_entero_grande" if _enteros_grandes(py.get("canon")) else "py_js_canonico")
    # --- Python frente al oráculo (registros y errores; la cabecera solo si no hubo E09 en ella)
    if _pares(py) != sorted(orc.errores):
        clases.append("py_oraculo_errores")
    else:
        clave = contrato.get("records_key", "records")
        pc, oc = py.get("canon"), orc.canonico
        if (pc is None) != (oc is None):
            clases.append("py_oraculo_documento")
        elif pc is not None and oc is not None:
            if not iguales(pc.get(clave), oc.get(clave)):
                clases.append("py_oraculo_entero_grande" if _enteros_grandes(pc.get(clave)) else "py_oraculo_registros")
            elif not any(c == "E09" and l == 1 for c, l in _pares(py)) and not iguales(
                    {k: v for k, v in pc["header"].items()}, oc["header"]):
                clases.append("py_oraculo_cabecera")
    return clases


def ejecutar(presupuesto: Optional[float], documentos: Optional[int], semilla: int, node: str = "node",
             maximo_ejemplos: int = 8) -> Dict[str, Any]:
    inicio = time.monotonic()
    contratos, docs = documentos_base()
    contratos_py = {k: Contract.from_dict(v) for k, v in contratos.items()}
    flujo = generar(docs, semilla)
    tmp = Path(tempfile.mkdtemp(prefix="mini-fuzz-"))
    cuentas: Counter = Counter()
    ejemplos: Dict[str, List[Dict[str, Any]]] = {}
    total = 0
    try:
        while True:
            restante = None if documentos is None else documentos - total
            if restante is not None and restante <= 0:
                break
            if presupuesto is not None and time.monotonic() - inicio >= presupuesto:
                break
            lote = [e for _, e in zip(range(LOTE if restante is None else min(LOTE, restante)), flujo)]
            resultados_js = analizar_js(lote, contratos, tmp, node)
            for entrada, js in zip(lote, resultados_js):
                py = analizar_python(entrada, contratos_py)
                clases = comparar(entrada, py, js, contratos[entrada["contract"]])
                total += 1
                for clase in clases:
                    cuentas[clase] += 1
                    if len(ejemplos.setdefault(clase, [])) < maximo_ejemplos:
                        ejemplos[clase].append({"etiqueta": entrada["label"], "texto": entrada["text"][:200],
                                                "py": {k: v for k, v in py.items() if k != "canon"},
                                                "js": {k: v for k, v in js.items() if k != "canon"}})
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    inesperadas = {k: v for k, v in cuentas.items() if k not in DIFERENCIAS_CONOCIDAS}
    return {"semilla": semilla, "documentos": total, "base": len(docs), "segundos": round(time.monotonic() - inicio, 1),
            "divergencias": dict(cuentas), "inesperadas": inesperadas, "ejemplos": ejemplos}


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--presupuesto", type=float, default=None, help=f"segundos (máximo {PRESUPUESTO_MAXIMO:g}); por omisión 100")
    ap.add_argument("--documentos", type=int, default=None, help="número exacto de documentos (sustituye al presupuesto)")
    ap.add_argument("--semilla", type=int, default=SEMILLA_POR_OMISION)
    ap.add_argument("--node", default="node")
    ap.add_argument("--salida", default=None, help="escribe el resumen JSON en este archivo")
    args = ap.parse_args(argv)
    presupuesto = None if args.documentos is not None else min(args.presupuesto or 100.0, PRESUPUESTO_MAXIMO)
    resumen = ejecutar(presupuesto, args.documentos, args.semilla, args.node)
    texto = json.dumps(resumen, ensure_ascii=False, indent=2)
    if args.salida:
        Path(args.salida).write_text(texto + "\n", encoding="utf-8")
    print(texto)
    return 1 if resumen["inesperadas"] else 0


if __name__ == "__main__":
    sys.exit(main())
