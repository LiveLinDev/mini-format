"""Cobertura con métrica definida: LÍNEAS y RAMAS por separado, en Python y en TypeScript.

    python tools/cobertura.py                       # Python y TypeScript
    python tools/cobertura.py --solo python         # solo Python (coverage --branch)
    python tools/cobertura.py --solo ts             # solo TypeScript (node --experimental-test-coverage)
    python tools/cobertura.py --json cobertura.json # además escribe el resumen en JSON

Definición de las métricas (la misma en los dos lenguajes):

* LÍNEAS  = líneas ejecutables cubiertas / líneas ejecutables. Python: ``covered_lines / num_statements`` del
  informe JSON de ``coverage``. TypeScript: ``LH / LF`` del informe lcov de Node.
* RAMAS   = ramas cubiertas / ramas. Python: ``covered_branches / num_branches`` (``coverage run --branch``).
  TypeScript: ``BRH / BRF`` del informe lcov.
  No se usa el porcentaje combinado que imprime ``coverage report`` (mezcla líneas y ramas).

Alcance: el paquete ``minifmt`` (``src/minifmt``) y ``ts/src``. Quedan fuera las pruebas, ``tools/``, ``conformance/``,
``sitio/``, ``generative/`` y ``experiments/`` (el oráculo y las herramientas se prueban, pero no cuentan para la métrica).

Puerta: falla (salida 1) si las LÍNEAS de cualquiera de los dos lenguajes son < 90 %, o si alguna prueba falla.
Las RAMAS se reportan con su propio valor y un objetivo de 90 % que solo avisa (no rompe la integración continua).

La medición de Python ejecuta la suite completa (``tests`` y ``experiments/generativo/tests``) bajo ``coverage``, de modo que
el resumen incluye también los conteos de pytest; los archivos de trabajo van a un directorio temporal que se borra.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

RAIZ = Path(__file__).resolve().parent.parent
MINIMO_LINEAS = 90.0
OBJETIVO_RAMAS = 90.0


def _pct(cubiertas: int, total: int) -> Optional[float]:
    return None if total == 0 else round(100.0 * cubiertas / total, 2)


def _resumen_pytest(salida: str) -> Dict[str, Optional[int]]:
    """Conteos de la última línea de pytest (``258 passed, 1 skipped, 11 xfailed, 6291 subtests passed in 63s``)."""
    ultima = ""
    for linea in salida.splitlines():
        if re.search(r"\bin [0-9.]+s\b", linea) and re.search(r"\b(passed|failed|error|skipped)\b", linea):
            ultima = linea
    cuenta = {clave: None for clave in ("passed", "failed", "skipped", "xfailed", "xpassed", "errors", "subtests_passed", "subtests_failed")}
    for n, palabra in re.findall(r"(\d+) (subtests passed|subtests failed|passed|failed|skipped|xfailed|xpassed|errors?)", ultima):
        clave = {"subtests passed": "subtests_passed", "subtests failed": "subtests_failed", "error": "errors", "errors": "errors"}.get(palabra, palabra)
        cuenta[clave] = int(n)
    return cuenta


def medir_python(timeout: int = 1800) -> Dict[str, Any]:
    """Ejecuta pytest bajo ``coverage run --branch`` y devuelve líneas, ramas y conteos de pytest."""
    tmp = Path(tempfile.mkdtemp(prefix="mini-cov-"))
    inicio = time.monotonic()
    try:
        entorno = dict(os.environ, COVERAGE_FILE=str(tmp / ".coverage"), PYTHONIOENCODING="utf-8",
                       PYTHONPATH=str(RAIZ / "src") + os.pathsep + os.environ.get("PYTHONPATH", ""))
        orden = [sys.executable, "-m", "coverage", "run", "--branch", "--source=minifmt", "-m", "pytest", "-q", "-p", "no:cacheprovider",
                 "tests", "experiments/generativo/tests"]
        prueba = subprocess.run(orden, cwd=RAIZ, env=entorno, capture_output=True, stdin=subprocess.DEVNULL, text=True, encoding="utf-8", timeout=timeout)
        informe = tmp / "cov.json"
        json_ = subprocess.run([sys.executable, "-m", "coverage", "json", "-o", str(informe)], cwd=RAIZ, env=entorno,
                               capture_output=True, stdin=subprocess.DEVNULL, text=True, encoding="utf-8")
        if not informe.is_file():
            return {"estado": "error", "motivo": "coverage no produjo el informe: " + (json_.stderr or json_.stdout)[-400:],
                    "pytest": _resumen_pytest(prueba.stdout), "salida_pytest": prueba.stdout[-1500:]}
        t = json.loads(informe.read_text(encoding="utf-8"))["totals"]
        return {
            "estado": "ejecutado",
            "lineas": {"cubiertas": t["covered_lines"], "total": t["num_statements"], "porcentaje": _pct(t["covered_lines"], t["num_statements"])},
            "ramas": {"cubiertas": t["covered_branches"], "total": t["num_branches"], "porcentaje": _pct(t["covered_branches"], t["num_branches"])},
            "pytest": _resumen_pytest(prueba.stdout), "codigo_salida_pytest": prueba.returncode,
            "segundos": round(time.monotonic() - inicio, 1), "salida_pytest": prueba.stdout[-1500:],
        }
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def leer_lcov(texto: str) -> Dict[str, Any]:
    """Totales de un informe lcov: líneas (LH/LF), ramas (BRH/BRF), funciones (FNH/FNF)."""
    suma = {clave: 0 for clave in ("LF", "LH", "BRF", "BRH", "FNF", "FNH")}
    for linea in texto.splitlines():
        clave, _, valor = linea.partition(":")
        if clave in suma:
            suma[clave] += int(valor)
    return {
        "lineas": {"cubiertas": suma["LH"], "total": suma["LF"], "porcentaje": _pct(suma["LH"], suma["LF"])},
        "ramas": {"cubiertas": suma["BRH"], "total": suma["BRF"], "porcentaje": _pct(suma["BRH"], suma["BRF"])},
        "funciones": {"cubiertas": suma["FNH"], "total": suma["FNF"], "porcentaje": _pct(suma["FNH"], suma["FNF"])},
    }


def medir_ts(timeout: int = 900) -> Dict[str, Any]:
    """Ejecuta las pruebas de ts/ con la cobertura experimental de Node y lee el informe lcov."""
    node = shutil.which("node")
    if node is None:
        return {"estado": "no_disponible", "motivo": "node no está instalado"}
    if not (RAIZ / "ts" / "node_modules" / "typescript").is_dir():
        return {"estado": "no_disponible", "motivo": "faltan las dependencias de ts/ (npm ci --prefix ts)"}
    tmp = Path(tempfile.mkdtemp(prefix="mini-cov-ts-"))
    inicio = time.monotonic()
    try:
        lcov = tmp / "ts.lcov"
        orden = [node, "--experimental-strip-types", "--no-warnings", "--test", "--experimental-test-coverage",
                 "--test-coverage-include=src/**", "--test-reporter=lcov", f"--test-reporter-destination={lcov}",
                 "--test-reporter=spec", "--test-reporter-destination=stdout"]
        archivos = sorted(str(p.relative_to(RAIZ / "ts")).replace("\\", "/") for p in (RAIZ / "ts" / "test").glob("*.test.ts"))
        prueba = subprocess.run(orden + archivos, cwd=RAIZ / "ts", capture_output=True, stdin=subprocess.DEVNULL, text=True, encoding="utf-8", timeout=timeout)
        if not lcov.is_file():
            return {"estado": "error", "motivo": "node no produjo el informe lcov", "salida": (prueba.stdout + prueba.stderr)[-1500:]}
        resultado = leer_lcov(lcov.read_text(encoding="utf-8"))
        conteo = {k: None for k in ("tests", "pass", "fail", "skipped", "todo")}
        for clave, valor in re.findall(r"^[ℹi#] (tests|pass|fail|skipped|todo) (\d+)", prueba.stdout, re.M):
            conteo[clave] = int(valor)
        resultado.update({"estado": "ejecutado", "pruebas": conteo, "codigo_salida": prueba.returncode,
                          "segundos": round(time.monotonic() - inicio, 1)})
        return resultado
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def evaluar(resumen: Dict[str, Any]) -> Dict[str, Any]:
    """Aplica la puerta (líneas >= 90 %) y el objetivo (ramas >= 90 %)."""
    fallos: List[str] = []
    avisos: List[str] = []
    for nombre in ("python", "typescript"):
        r = resumen.get(nombre)
        if not r or r.get("estado") != "ejecutado":
            if r and r.get("estado") in ("error",):
                fallos.append(f"{nombre}: {r.get('motivo')}")
            continue
        if r["lineas"]["porcentaje"] is None or r["lineas"]["porcentaje"] < MINIMO_LINEAS:
            fallos.append(f"{nombre}: líneas {r['lineas']['porcentaje']} % < {MINIMO_LINEAS:g} %")
        if r["ramas"]["porcentaje"] is None or r["ramas"]["porcentaje"] < OBJETIVO_RAMAS:
            avisos.append(f"{nombre}: ramas {r['ramas']['porcentaje']} % < objetivo {OBJETIVO_RAMAS:g} % (solo aviso)")
        if nombre == "python":
            p = r["pytest"]
            if (p.get("failed") or 0) or (p.get("errors") or 0) or r.get("codigo_salida_pytest") not in (0,):
                fallos.append(f"python: pytest falló ({p})")
        else:
            if (r["pruebas"].get("fail") or 0) or r.get("codigo_salida") not in (0,):
                fallos.append(f"typescript: las pruebas fallaron ({r['pruebas']})")
    return {"minimo_lineas": MINIMO_LINEAS, "objetivo_ramas": OBJETIVO_RAMAS, "fallos": fallos, "avisos": avisos, "cumple": not fallos}


def imprimir(resumen: Dict[str, Any]) -> None:
    print(f"{'lenguaje':<12}{'líneas':>18}{'ramas':>18}")
    for nombre in ("python", "typescript"):
        r = resumen.get(nombre)
        if not r:
            continue
        if r.get("estado") != "ejecutado":
            print(f"{nombre:<12}{r.get('estado')}: {r.get('motivo')}")
            continue
        l, b = r["lineas"], r["ramas"]
        print(f"{nombre:<12}{l['porcentaje']:>9}% ({l['cubiertas']}/{l['total']}){b['porcentaje']:>9}% ({b['cubiertas']}/{b['total']})")
    if "python" in resumen and resumen["python"].get("pytest"):
        print("pytest:", {k: v for k, v in resumen["python"]["pytest"].items() if v is not None})
    if "typescript" in resumen and resumen["typescript"].get("pruebas"):
        print("node --test:", {k: v for k, v in resumen["typescript"]["pruebas"].items() if v is not None})
    ev = resumen["evaluacion"]
    for aviso in ev["avisos"]:
        print("AVISO:", aviso)
    for fallo in ev["fallos"]:
        print("FALLO:", fallo)
    print("Puerta (líneas >= %g %% en cada lenguaje medido):" % ev["minimo_lineas"], "CUMPLE" if ev["cumple"] else "NO CUMPLE")


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="Cobertura de líneas y de ramas (Python y TypeScript)")
    ap.add_argument("--solo", choices=("python", "ts"), default=None)
    ap.add_argument("--json", default=None, help="escribe el resumen en este archivo JSON")
    args = ap.parse_args(argv)
    resumen: Dict[str, Any] = {"metrica": {"lineas": "líneas ejecutables cubiertas / líneas ejecutables",
                                          "ramas": "ramas cubiertas / ramas (coverage --branch; BRH/BRF de lcov)"}}
    if args.solo in (None, "python"):
        resumen["python"] = medir_python()
    if args.solo in (None, "ts"):
        resumen["typescript"] = medir_ts()
    resumen["evaluacion"] = evaluar(resumen)
    imprimir(resumen)
    if args.json:
        Path(args.json).write_text(json.dumps(resumen, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return 0 if resumen["evaluacion"]["cumple"] else 1


if __name__ == "__main__":
    sys.exit(main())
