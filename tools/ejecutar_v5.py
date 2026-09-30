"""UN comando que ejecuta todas las verificaciones V5 del árbol actual y registra una corrida de evidencia.

    python tools/ejecutar_v5.py                     # verificación completa (unos 8-10 min) y corrida en evidencia/corridas/
    python tools/ejecutar_v5.py --sin-corrida       # imprime el resumen y no escribe nada en evidencia/
    python tools/ejecutar_v5.py --rapido            # fuzz de 15 s y sin instalación limpia (para ensayar; la corrida queda 'parcial')
    python tools/ejecutar_v5.py --profundo          # cortes en todas las posiciones y 500 ejemplos por propiedad
    python tools/ejecutar_v5.py --evidencia-ci ci.json   # incorpora la evidencia de CI (ver más abajo)

Pasos (cada uno registra su propio resultado; uno que falle no impide ejecutar los demás):

 1. pytest (``tests`` y ``experiments/generativo/tests``) bajo ``coverage run --branch``: passed/failed/skipped/xfailed/subtests y
    cobertura de LÍNEAS y de RAMAS de ``minifmt`` (tools/cobertura.py).
 2. Conformidad: Python, js/mini.js y TypeScript, con total, por categoría y por familia; más el oráculo independiente.
 3. js/mini.js al día (``build_js.mjs --check``) y ``tests/test_js_port.mjs``.
 4. Comprobación de tipos de TypeScript.
 5. Pruebas de TypeScript con cobertura de líneas y de ramas de ``ts/src``.
 6. Fuzz diferencial Python / js/mini.js / oráculo con semilla fija y tiempo acotado.
 7. Instalación limpia: construye las distribuciones en un directorio temporal y ejecuta tools/smoke_release.py (venv nuevo,
    instalación de la rueda sin índice, CLI, ejemplos, reparación y paquete npm).
 8. Adaptadores de modelos con mocks (Python y TypeScript): más de tres proveedores, ninguna llamada real.

Criterio del estudio V5 (interpretación FIJADA antes de ejecutar; no se ajusta después de ver las cifras):
  * conformidad del 100 % en Python, TypeScript y js/mini.js;
  * cobertura de LÍNEAS >= 90 % en Python y en TypeScript (las ramas se reportan con su propio valor; objetivo 90 %, solo aviso);
  * integración continua en verde en Linux, Windows y macOS para el mismo commit.
El tercer punto no se puede verificar desde una sola máquina ni sin acceso a Actions: mientras no haya evidencia de CI
(``--evidencia-ci`` con el resultado de los tres sistemas operativos para ESTE commit), la corrida queda con
``estado_ejecucion = parcial`` y ``resultado = no_evaluable``, con las cifras locales de cada criterio en el resumen.

Formato de ``--evidencia-ci`` (JSON escrito por quien consultó Actions):
  {"commit": "<sha completo>", "url": "<enlace a la ejecución>", "sistemas": {"ubuntu-latest": "success", "windows-latest": "success", "macos-latest": "success"}}

Procedencia: ``reproducido_local``. Sin red, sin claves, sin gasto. El código se identifica con el commit o, si el árbol
tiene cambios, con el hash del snapshot (tools/evidencia_lib.py).
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "tools"))
sys.path.insert(0, str(RAIZ / "src"))
sys.path.insert(0, str(RAIZ / "conformance"))
sys.path.insert(0, str(RAIZ / "conformance" / "oraculo"))

import cobertura  # noqa: E402
import evidencia_lib  # noqa: E402
import fuzz_diferencial  # noqa: E402

UMBRAL_LINEAS = cobertura.MINIMO_LINEAS
SISTEMAS_CI = ("ubuntu-latest", "windows-latest", "macos-latest")
PAQUETES = ("tiktoken", "regex", "pyyaml", "pytest", "coverage", "hypothesis", "pydantic", "jsonschema", "build", "wheel", "markdown")


def _ejecutar(orden: List[str], cwd: Path = RAIZ, timeout: int = 900, entorno: Optional[Dict[str, str]] = None) -> subprocess.CompletedProcess:
    env = dict(os.environ, PYTHONIOENCODING="utf-8")
    env["PYTHONPATH"] = str(RAIZ / "src") + os.pathsep + env.get("PYTHONPATH", "")
    env.update(entorno or {})
    return subprocess.run(orden, cwd=cwd, env=env, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout)


def _node() -> Optional[str]:
    return shutil.which("node")


def _npm() -> Optional[str]:
    return shutil.which("npm")


def _cargar_modulo(nombre: str, ruta: Path):
    spec = importlib.util.spec_from_file_location(nombre, ruta)
    modulo = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
    spec.loader.exec_module(modulo)  # type: ignore[union-attr]
    return modulo


# ----------------------------------------------------------------------------------------------- pasos
def paso_pytest_y_cobertura_python(profundo: bool) -> Dict[str, Any]:
    entorno = {"MINI_CORTES_COMPLETO": "1", "MINI_PROP_EJEMPLOS": "500"} if profundo else {}
    os.environ.update(entorno)  # heredado por el subproceso de cobertura.medir_python
    try:
        r = cobertura.medir_python()
    finally:
        for k in entorno:
            os.environ.pop(k, None)
    r["modo"] = "profundo" if profundo else "normal"
    return r


def paso_conformidad() -> Dict[str, Any]:
    salida: Dict[str, Any] = {"estado": "ejecutado"}
    # --- Python, en el mismo proceso, con el runner de referencia
    ejecutor = _cargar_modulo("run_python_v5", RAIZ / "conformance" / "run_python.py")
    casos = ejecutor.load_cases()
    cat: Dict[str, Dict[str, int]] = {}
    fam: Dict[str, Dict[str, int]] = {}
    fallos: List[str] = []
    for caso in casos:
        ok, mensaje = ejecutor.run_case(caso)
        familia = caso.get("family") or (f"contrato:{caso['contract']['prefix']}" if isinstance(caso.get("contract"), dict) and "prefix" in caso["contract"] else "contrato_embebido")
        for grupo, clave in ((cat, caso["category"]), (fam, familia)):
            c = grupo.setdefault(clave, {"pass": 0, "fail": 0})
            c["pass" if ok else "fail"] += 1
        if not ok:
            fallos.append(f"{caso['id']}: {mensaje}")
    salida["python"] = {"total": len(casos), "pasan": len(casos) - len(fallos), "fallos": fallos, "por_categoria": cat, "por_familia": fam}
    # --- js/mini.js
    if _node():
        p = _ejecutar([_node() or "node", "--no-warnings", str(RAIZ / "tools" / "conformancia_v5.mjs")])
        try:
            salida["js"] = json.loads(p.stdout.strip().splitlines()[-1])
        except (ValueError, IndexError):
            salida["js"] = {"estado": "error", "salida": (p.stdout + p.stderr)[-800:]}
        # --- TypeScript (ts/test/conformance.test.ts), contando cada caso por su identificador
        p = _ejecutar([_node() or "node", "--experimental-strip-types", "--no-warnings", "--test", "--test-reporter=tap", "test/conformance.test.ts"],
                      cwd=RAIZ / "ts")
        ids_ok: Dict[str, bool] = {}
        for linea in p.stdout.splitlines():
            m = re.match(r"^\s+(not )?ok \d+ - (\S+)\s*(#.*)?$", linea)
            if m:
                ids_ok[m.group(2)] = m.group(1) is None
        por_id = {c["id"]: c for c in casos}
        ts_casos = {i: v for i, v in ids_ok.items() if i in por_id}
        ts_cat: Dict[str, Dict[str, int]] = {}
        ts_fam: Dict[str, Dict[str, int]] = {}
        for i, ok_ in ts_casos.items():
            c = por_id[i]
            familia = c.get("family") or (f"contrato:{c['contract']['prefix']}" if isinstance(c.get("contract"), dict) and "prefix" in c["contract"] else "contrato_embebido")
            for grupo, clave in ((ts_cat, c["category"]), (ts_fam, familia)):
                g = grupo.setdefault(clave, {"pass": 0, "fail": 0})
                g["pass" if ok_ else "fail"] += 1
        salida["typescript"] = {"total": len(casos), "ejecutados": len(ts_casos), "pasan": sum(ts_casos.values()),
                                "fallos": sorted(i for i, v in ts_casos.items() if not v), "por_categoria": ts_cat, "por_familia": ts_fam,
                                "codigo_salida": p.returncode}
    else:
        salida["js"] = salida["typescript"] = {"estado": "no_disponible", "motivo": "node no está instalado"}
    # --- oráculo independiente (solo decodifica: modos strict y lenient)
    orc = _cargar_modulo("ejecutar_oraculo_v5", RAIZ / "conformance" / "oraculo" / "ejecutar.py")
    n = f = 0
    for caso in orc.cargar_casos():
        if caso["mode"] in ("strict", "lenient"):
            n += 1
            if not orc.ejecutar_caso(caso)[0]:
                f += 1
    salida["oraculo"] = {"total": n, "pasan": n - f}
    return salida


def paso_js_al_dia() -> Dict[str, Any]:
    if not _node():
        return {"estado": "no_disponible", "motivo": "node no está instalado"}
    a = _ejecutar([_node() or "node", "--no-warnings", "tools/build_js.mjs", "--check"])
    b = _ejecutar([_node() or "node", "--no-warnings", "tests/test_js_port.mjs"])
    m = re.search(r"(\d+)/(\d+) checks passed", b.stdout)
    return {"estado": "ejecutado", "build_js_check": {"codigo_salida": a.returncode, "salida": (a.stdout + a.stderr).strip()[-200:]},
            "test_js_port": {"codigo_salida": b.returncode, "pasan": int(m.group(1)) if m else None, "total": int(m.group(2)) if m else None}}


def paso_typecheck() -> Dict[str, Any]:
    if not _npm() or not (RAIZ / "ts" / "node_modules" / "typescript").is_dir():
        return {"estado": "no_disponible", "motivo": "npm o las dependencias de ts/ no están instalados (npm ci --prefix ts)"}
    p = _ejecutar([_npm() or "npm", "run", "typecheck", "--prefix", "ts"])
    return {"estado": "ejecutado", "codigo_salida": p.returncode, "salida": (p.stdout + p.stderr).strip()[-400:]}


def paso_fuzz(presupuesto: float) -> Dict[str, Any]:
    if not _node():
        return {"estado": "no_disponible", "motivo": "node no está instalado"}
    r = fuzz_diferencial.ejecutar(min(presupuesto, fuzz_diferencial.PRESUPUESTO_MAXIMO), None, fuzz_diferencial.SEMILLA_POR_OMISION)
    r["estado"] = "ejecutado"
    return r


def paso_instalacion_limpia() -> Dict[str, Any]:
    tmp = Path(tempfile.mkdtemp(prefix="mini-v5-dist-"))
    try:
        dist = tmp / "dist"
        b = _ejecutar([sys.executable, "tools/build_release.py", "--output", str(dist)], timeout=900)
        if b.returncode != 0:
            return {"estado": "error", "motivo": "build_release.py falló", "salida": (b.stdout + b.stderr)[-800:]}
        manifiesto = json.loads((dist / "manifest.json").read_text(encoding="utf-8"))
        s = _ejecutar([sys.executable, "tools/smoke_release.py", "--directory", str(dist)], timeout=1200,
                      entorno={"PYTHONPATH": ""})
        return {"estado": "ejecutado", "version": manifiesto.get("version"),
                "archivos": [{"nombre": f["name"], "bytes": f["bytes"], "sha256": f["sha256"]} for f in manifiesto["files"]],
                "smoke": {"codigo_salida": s.returncode, "salida": (s.stdout + s.stderr).strip()[-600:]},
                "sdist": any(f["name"].endswith(".tar.gz") and "core" not in f["name"] for f in manifiesto["files"])}
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def paso_adaptadores() -> Dict[str, Any]:
    p = _ejecutar([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", "tests/test_nucleo_adaptadores.py",
                   "experiments/generativo/tests/test_adapters.py", "-v"], timeout=600)
    pruebas = [l for l in p.stdout.splitlines() if "::" in l and ("PASSED" in l or "FAILED" in l)]
    resumen = cobertura._resumen_pytest(p.stdout)
    texto = "\n".join(pruebas).lower()
    proveedores = sorted(x for x in ("openai", "anthropic", "groq", "deepseek", "simulado", "simulated") if x in texto)
    salida: Dict[str, Any] = {"estado": "ejecutado", "python": {"pytest": resumen, "codigo_salida": p.returncode, "proveedores": proveedores}}
    if _node():
        t = _ejecutar([_node() or "node", "--experimental-strip-types", "--no-warnings", "--test", "test/adapters.test.ts"], cwd=RAIZ / "ts")
        conteo = {k: int(v) for k, v in re.findall(r"^[ℹi#] (tests|pass|fail) (\d+)", t.stdout, re.M)}
        salida["typescript"] = {"pruebas": conteo, "codigo_salida": t.returncode}
    return salida


# ----------------------------------------------------------------------------------------------- evaluación
def _pct(a: int, b: int) -> Optional[float]:
    return None if not b else round(100.0 * a / b, 2)


def evaluar_ci(ruta: Optional[str], commit: Optional[str]) -> Dict[str, Any]:
    if not ruta:
        return {"estado": "sin_evidencia", "motivo": "CI en Linux, Windows y macOS: no verificable desde esta máquina (Actions del repositorio privado)"}
    try:
        datos = json.loads(Path(ruta).read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        return {"estado": "sin_evidencia", "motivo": f"no se pudo leer {ruta}: {e}"}
    sistemas = datos.get("sistemas") or {}
    falta = [s for s in SISTEMAS_CI if s not in sistemas]
    if datos.get("commit") != commit:
        return {"estado": "sin_evidencia", "motivo": f"la evidencia de CI es del commit {datos.get('commit')}, no del código ejecutado ({commit})", "url": datos.get("url")}
    if falta:
        return {"estado": "sin_evidencia", "motivo": f"faltan sistemas en la evidencia de CI: {falta}", "url": datos.get("url")}
    verde = all(sistemas[s] == "success" for s in SISTEMAS_CI)
    return {"estado": "verde" if verde else "rojo", "sistemas": {s: sistemas[s] for s in SISTEMAS_CI}, "url": datos.get("url")}


def derivar(pasos: Dict[str, Dict[str, Any]], ci: Dict[str, Any]) -> Dict[str, Any]:
    """Cifras derivadas y cumplimiento local de cada criterio (todo sale de los resultados de los pasos)."""
    py = pasos["pytest_cobertura_python"]
    ts = pasos["ts_cobertura"]
    conf = pasos["conformidad"]
    ok_py = conf["python"]
    js = conf.get("js", {})
    tsc = conf.get("typescript", {})
    resumen: Dict[str, Any] = {
        "pytest": py.get("pytest"),
        "cobertura_python": {"lineas": py.get("lineas"), "ramas": py.get("ramas")} if py.get("estado") == "ejecutado" else None,
        "cobertura_typescript": {"lineas": ts.get("lineas"), "ramas": ts.get("ramas"), "funciones": ts.get("funciones")} if ts.get("estado") == "ejecutado" else None,
        "pruebas_typescript": ts.get("pruebas"),
        "conformidad": {
            "python": {"pasan": ok_py["pasan"], "total": ok_py["total"]},
            "js": {"pasan": js.get("pasan"), "total": js.get("total")} if "pasan" in js else js,
            "typescript": {"pasan": tsc.get("pasan"), "total": tsc.get("total"), "ejecutados": tsc.get("ejecutados")} if "pasan" in tsc else tsc,
            "oraculo_independiente": conf["oraculo"],
            "por_familia_python": {k: f"{v['pass']}/{v['pass'] + v['fail']}" for k, v in sorted(ok_py["por_familia"].items())},
            "por_categoria_python": {k: f"{v['pass']}/{v['pass'] + v['fail']}" for k, v in sorted(ok_py["por_categoria"].items())},
        },
        "js_al_dia": pasos["js_al_dia"],
        "typecheck": pasos["typecheck"],
        "fuzz": {k: pasos["fuzz"].get(k) for k in ("semilla", "documentos", "segundos", "divergencias", "inesperadas", "estado")},
        "instalacion_limpia": {k: pasos["instalacion_limpia"].get(k) for k in ("estado", "version", "smoke", "sdist")},
        "adaptadores": pasos["adaptadores"],
        "ci": ci,
    }
    # --- criterios locales (umbral fijado arriba, no se ajusta a las cifras)
    def cien(x: Dict[str, Any]) -> Optional[bool]:
        if not x or x.get("pasan") is None or not x.get("total"):
            return None
        return x["pasan"] == x["total"]

    criterios = {
        "conformidad_100_python": cien(ok_py),
        "conformidad_100_js": cien(js),
        "conformidad_100_typescript": (tsc.get("pasan") == tsc.get("total") == tsc.get("ejecutados")) if "pasan" in tsc else None,
        "lineas_python_ge_90": (py["lineas"]["porcentaje"] >= UMBRAL_LINEAS) if py.get("estado") == "ejecutado" else None,
        "lineas_typescript_ge_90": (ts["lineas"]["porcentaje"] >= UMBRAL_LINEAS) if ts.get("estado") == "ejecutado" else None,
        "ci_linux_windows_macos": {"verde": True, "rojo": False}.get(ci["estado"]),
    }
    soporte = {
        "pytest_sin_fallos": (py.get("pytest", {}).get("failed") in (0, None) and py.get("codigo_salida_pytest") == 0) if py.get("estado") == "ejecutado" else None,
        "js_al_dia_y_test_js_port": (pasos["js_al_dia"].get("build_js_check", {}).get("codigo_salida") == 0
                                     and pasos["js_al_dia"].get("test_js_port", {}).get("codigo_salida") == 0) if pasos["js_al_dia"].get("estado") == "ejecutado" else None,
        "typecheck": (pasos["typecheck"].get("codigo_salida") == 0) if pasos["typecheck"].get("estado") == "ejecutado" else None,
        "pruebas_typescript_sin_fallos": (ts.get("pruebas", {}).get("fail") == 0) if ts.get("estado") == "ejecutado" else None,
        "fuzz_sin_divergencias_inesperadas": (not pasos["fuzz"].get("inesperadas")) if pasos["fuzz"].get("estado") == "ejecutado" else None,
        "instalacion_limpia": (pasos["instalacion_limpia"].get("smoke", {}).get("codigo_salida") == 0) if pasos["instalacion_limpia"].get("estado") == "ejecutado" else None,
        "adaptadores_mock_mas_de_tres_proveedores": (len(pasos["adaptadores"].get("python", {}).get("proveedores", [])) > 3
                                                      and pasos["adaptadores"]["python"].get("codigo_salida") == 0) if pasos["adaptadores"].get("estado") == "ejecutado" else None,
    }
    resumen["criterios"] = criterios
    resumen["verificaciones_de_soporte"] = soporte
    return resumen


def manifiesto(resumen: Dict[str, Any], pasos: Dict[str, Dict[str, Any]], comando: str, run_id: Optional[str]) -> Dict[str, Any]:
    criterios = resumen["criterios"]
    ci_estado = resumen["ci"]["estado"]
    sin_ejecutar = [k for k, v in pasos.items() if v.get("estado") != "ejecutado"]
    completo = ci_estado in ("verde", "rojo") and not sin_ejecutar and all(v is not None for v in criterios.values())
    if completo:
        estado, resultado = "ejecutado", ("cumple" if all(criterios.values()) else "no_cumple")
    else:
        estado, resultado = "parcial", "no_evaluable"
    limitaciones = []
    if ci_estado not in ("verde", "rojo"):
        limitaciones.append("CI en Linux, Windows y macOS no verificado: " + resumen["ci"].get("motivo", ""))
    if sin_ejecutar:
        limitaciones.append("pasos no ejecutados o con error: " + ", ".join(sin_ejecutar))
    limitaciones.append("ejecutado en un solo sistema operativo y una versión de Python; las cifras de otros sistemas no se infieren")
    m = evidencia_lib.nueva_corrida(
        "V5", "reproducido_local", comando, run_id=run_id,
        entorno=evidencia_lib.info_entorno(PAQUETES),
        contratos=[{"prefijo": p.parent.name, "ruta": evidencia_lib.ruta_relativa(p), "sha256": evidencia_lib.sha256_archivo(p)}
                   for p in sorted((RAIZ / "forks").glob("*/contract.json"))],
        conjuntos=[{"nombre": f"conformance/cases/{p.name}", "ruta": evidencia_lib.ruta_relativa(p), "sha256": evidencia_lib.sha256_archivo(p), "sintetico": False}
                   for p in sorted((RAIZ / "conformance" / "cases").glob("*.json"))],
        resumen=resumen,
        criterio={
            "definicion": "conformidad 100 % en Python, TypeScript y js/mini.js; cobertura de líneas >= 90 % en Python y en TypeScript; CI verde en Linux, Windows y macOS",
            "interpretacion_fijada": ("Conformidad = todos los casos de conformance/cases pasan en cada ejecutor. Cobertura = líneas ejecutables cubiertas / "
                                      "líneas ejecutables de minifmt y de ts/src (tools/cobertura.py); las ramas se reportan aparte con objetivo 90 % y no deciden. "
                                      "CI = conclusión 'success' de los tres sistemas operativos para el mismo commit; sin esa evidencia el resultado no es evaluable."),
            "umbrales": {"conformidad": 1.0, "lineas_python_min": UMBRAL_LINEAS, "lineas_typescript_min": UMBRAL_LINEAS, "ramas_objetivo": cobertura.OBJETIVO_RAMAS},
            "cumplimiento_local": criterios,
        },
        estado_ejecucion=estado, resultado=resultado, limitaciones=limitaciones, gasto_usd=0,
        notas="Verificación V5 local: sin red, sin claves y sin gasto. Las cifras se derivan de los resultados de cada paso; ninguna se escribió a mano.",
    )
    return m


# ----------------------------------------------------------------------------------------------- principal
def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="Verificaciones V5 del árbol actual", formatter_class=argparse.RawDescriptionHelpFormatter,
                                 epilog="Véase el docstring del módulo para el detalle de los pasos y del criterio.")
    ap.add_argument("--sin-corrida", action="store_true", help="no escribe evidencia/corridas/")
    ap.add_argument("--rapido", action="store_true", help="fuzz de 15 s y sin instalación limpia (ensayo)")
    ap.add_argument("--profundo", action="store_true", help="cortes en todas las posiciones y 500 ejemplos por propiedad")
    ap.add_argument("--fuzz-presupuesto", type=float, default=None, help="segundos de fuzz (por omisión 100; máximo 120)")
    ap.add_argument("--evidencia-ci", default=None, help="JSON con la conclusión de Actions en los tres sistemas para este commit")
    ap.add_argument("--run-id", default=None, help="identificador de la corrida (por omisión v5-<sello UTC>)")
    ap.add_argument("--salida", default=None, help="directorio de la corrida (por omisión evidencia/corridas/<run_id>)")
    args = ap.parse_args(argv)

    comando = "python tools/ejecutar_v5.py" + "".join(f" {a}" for a in (argv if argv is not None else sys.argv[1:]))
    presupuesto = args.fuzz_presupuesto if args.fuzz_presupuesto is not None else (15.0 if args.rapido else 100.0)
    pasos: Dict[str, Dict[str, Any]] = {}
    plan: List[Any] = [
        ("pytest_cobertura_python", lambda: paso_pytest_y_cobertura_python(args.profundo)),
        ("conformidad", paso_conformidad),
        ("js_al_dia", paso_js_al_dia),
        ("typecheck", paso_typecheck),
        ("ts_cobertura", cobertura.medir_ts),
        ("fuzz", lambda: paso_fuzz(presupuesto)),
        ("instalacion_limpia", (lambda: {"estado": "omitido", "motivo": "--rapido"}) if args.rapido else paso_instalacion_limpia),
        ("adaptadores", paso_adaptadores),
    ]
    for nombre, fn in plan:
        t0 = time.monotonic()
        print(f"[V5] {nombre} ...", flush=True)
        try:
            resultado = fn()
        except Exception as e:  # un paso roto no impide los demás, pero queda registrado como error
            resultado = {"estado": "error", "motivo": f"{type(e).__name__}: {e}"}
        resultado.setdefault("segundos", round(time.monotonic() - t0, 1))
        pasos[nombre] = resultado
        print(f"[V5] {nombre}: {resultado.get('estado')} ({resultado['segundos']} s)", flush=True)

    codigo = evidencia_lib.info_codigo()
    ci = evaluar_ci(args.evidencia_ci, codigo.get("commit"))
    resumen = derivar(pasos, ci)
    m = manifiesto(resumen, pasos, comando, args.run_id)
    print(json.dumps({"estado_ejecucion": m["estado_ejecucion"], "resultado": m["resultado"], "criterios": resumen["criterios"],
                      "verificaciones_de_soporte": resumen["verificaciones_de_soporte"]}, ensure_ascii=False, indent=2))
    if not args.sin_corrida:
        directorio = Path(args.salida) if args.salida else evidencia_lib.directorio_corridas() / m["run_id"]
        directorio.mkdir(parents=True, exist_ok=True)
        (directorio / "logs").mkdir(exist_ok=True)
        archivos = []
        evidencia_lib.escribir_json(directorio / "resumen_v5.json", {"resumen": resumen, "pasos": pasos})
        archivos.append(directorio / "resumen_v5.json")
        for nombre, datos in pasos.items():
            texto = datos.pop("salida_pytest", None) if isinstance(datos, dict) else None
            ruta = directorio / "logs" / f"{nombre}.json"
            evidencia_lib.escribir_json(ruta, {"paso": nombre, "datos": datos, "cola_de_salida": texto})
            archivos.append(ruta)
        ruta = evidencia_lib.guardar_corrida(m, archivos, directorio)
        print(f"[V5] corrida escrita en {ruta.parent}")
    locales = [v for v in resumen["criterios"].values() if v is not None and not isinstance(v, dict)]
    soporte = [v for v in resumen["verificaciones_de_soporte"].values() if v is not None]
    fallo_local = any(v is False for k, v in resumen["criterios"].items() if k != "ci_linux_windows_macos") or any(v is False for v in soporte)
    del locales
    return 1 if fallo_local else 0


if __name__ == "__main__":
    sys.exit(main())
