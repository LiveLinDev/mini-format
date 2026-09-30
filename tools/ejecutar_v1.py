#!/usr/bin/env python3
"""Reproduce V1 (tokens y fidelidad) sin red y sin API, y escribe una corrida por serie.

    python tools/ejecutar_v1.py            # completo: 14 dominios, n=1..250, tres tokenizadores, 4 snapshots públicos
    python tools/ejecutar_v1.py --rapido   # subconjunto (3 dominios, n=1,12,100, público solo con o200k_base) para pruebas

Corridas (``evidencia/corridas/<run_id>/``, una por serie, con ``manifiesto.json``):

* ``v1-linea_base_n12-<sello>``  benchmark/run_benchmark.py + línea base de experiments/v1_tokens/run.py,
                                 n=12 con tres tokenizadores y reversibilidad verificada.
* ``v1-serie_n-<sello>``         serie n=1,5,10,25,50,100,250 (variantes 'muestreo' y 'ciclo'), tres tokenizadores,
                                 ocho formatos archivados + tres comparadores reversibles, criterio documental.
* ``v1-publicos-<sello>``        benchmark/public/run.py con los 4 snapshots y los tres vocabularios.
* ``v1-conciliacion-<sello>``    las cuatro cifras (33,8 / 34,8 / 34,99 / 35,64 %) y el desglose
                                 contenido / documento / estructura / prompt / total; verificación de la errata V7/V8.
* ``v5-ancho-<sello>``           (solo con --con-v5) V5 con los tres tokenizadores, comparada con lo archivado.

Todo se ejecuta con los vocabularios de benchmark/vocab (hash verificado) y con la red bloqueada: un intento
de descarga rompe la corrida. Las salidas archivadas (experiments/v1_tokens/results, benchmark/results,
benchmark/public/results.json) NO se tocan: se comparan fila a fila y las diferencias se registran.
El tiempo de cada paso y el total se guardan en ``resumen.tiempos_s`` de cada manifiesto.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

ROOT = Path(__file__).resolve().parent.parent
for _p in (ROOT / "tools", ROOT / "experiments", ROOT / "experiments" / "v1_tokens", ROOT / "benchmark", ROOT / "src"):
    sys.path.insert(0, str(_p))

import evidencia_lib as ev  # noqa: E402
import vocab_local  # noqa: E402

TOKENIZADORES = ["o200k_base", "cl100k_base", "r50k_base"]
TAMANOS_SERIE = [1, 5, 10, 25, 50, 100, 250]
TAMANOS_RAPIDO = [1, 12, 100]
DOMINIOS_RAPIDO = ["a", "log", "cls"]
PYTHON = sys.executable


# ---------------------------------------------------------------- utilidades
def sha_texto_lf(p: Path) -> str:
    return hashlib.sha256(p.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def leer_csv(p: Path) -> List[Dict[str, str]]:
    with open(p, newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def _num(x: str) -> Any:
    try:
        return float(x)
    except (TypeError, ValueError):
        return x


def comparar_tablas(nuevo: Path, archivado: Path, claves: Sequence[str], tol: float = 5e-7) -> Dict[str, Any]:
    """Compara dos CSV fila a fila por ``claves``; los valores numéricos con tolerancia ``tol``."""
    a = {tuple(r[k] for k in claves): r for r in leer_csv(archivado)}
    n = {tuple(r[k] for k in claves): r for r in leer_csv(nuevo)}
    comunes = [k for k in n if k in a]
    difieren: List[Dict[str, Any]] = []
    for k in comunes:
        for col, v in n[k].items():
            w = a[k].get(col)
            if v == w:
                continue
            x, y = _num(v), _num(w)
            if isinstance(x, float) and isinstance(y, float) and abs(x - y) <= tol:
                continue
            difieren.append({"clave": list(k), "columna": col, "archivado": w, "reproducido": v})
    return {
        "archivo_archivado": ev.ruta_relativa(archivado), "filas_archivadas": len(a), "filas_reproducidas": len(n),
        "filas_comparadas": len(comunes), "filas_identicas": len(comunes) - len({tuple(d["clave"]) for d in difieren}),
        "celdas_distintas": len(difieren), "solo_en_archivado": len(a) - len(comunes), "solo_en_reproducido": len(n) - len(comunes),
        "primeras_diferencias": difieren[:20],
        "coincide_en_filas_comunes": not difieren and len(comunes) > 0,
        "coincide_totalmente": not difieren and len(a) == len(n) == len(comunes),
    }


def aplanar_json(o: Any, ruta: str = "") -> Dict[str, Any]:
    if isinstance(o, dict):
        out: Dict[str, Any] = {}
        for k, v in o.items():
            out.update(aplanar_json(v, f"{ruta}/{k}"))
        return out
    if isinstance(o, list):
        out = {}
        for i, v in enumerate(o):
            out.update(aplanar_json(v, f"{ruta}/{i}"))
        return out
    return {ruta: o}


DIFERENCIAS_DE_PROCEDENCIA = ("/tiktoken", "/python", "/implementation_sha256/")


def comparar_json_publico(nuevo: Path, archivado: Path) -> Dict[str, Any]:
    a = aplanar_json(json.loads(archivado.read_text(encoding="utf-8")))
    n = aplanar_json(json.loads(nuevo.read_text(encoding="utf-8")))
    difs = [{"ruta": k, "archivado": a.get(k), "reproducido": n.get(k)} for k in sorted(set(a) | set(n)) if a.get(k) != n.get(k)]
    prov = [d for d in difs if any(d["ruta"] == s or d["ruta"].startswith(s) for s in DIFERENCIAS_DE_PROCEDENCIA)]
    datos = [d for d in difs if d not in prov]
    return {"archivo_archivado": ev.ruta_relativa(archivado), "campos_archivados": len(a), "campos_reproducidos": len(n),
            "campos_distintos": len(difs), "diferencias_de_procedencia": prov, "diferencias_de_datos": datos,
            "coincide_en_datos": not datos}


def ejecutar(cmd: Sequence[str], log: Path, env: Dict[str, str]) -> Tuple[float, str]:
    """Ejecuta un comando; falla si el código de salida no es 0. Devuelve (segundos, stdout)."""
    t0 = time.time()
    r = subprocess.run(list(cmd), cwd=str(ROOT), env=env, capture_output=True, text=True, encoding="utf-8", errors="replace")
    dt = time.time() - t0
    with open(log, "a", encoding="utf-8", newline="\n") as fh:
        fh.write(f"$ {' '.join(cmd)}\n{r.stdout}\n")
        if r.stderr.strip():
            fh.write(f"[stderr]\n{r.stderr}\n")
    if r.returncode != 0:
        raise RuntimeError(f"{' '.join(cmd)} terminó con código {r.returncode}:\n{r.stderr[-2000:]}")
    return dt, r.stdout


def copiar(origen: Path, destino: Path) -> Path:
    destino.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(origen, destino)
    return destino


def escribir_csv(ruta: Path, filas: List[Dict[str, Any]]) -> Path:
    import comun as C
    C.escribir_csv(ruta, filas)
    return ruta


def info_tokenizadores(toks: Dict[str, Any]) -> List[Dict[str, Any]]:
    return [vocab_local.info_tokenizador(n, t) for n, t in toks.items()]


# ---------------------------------------------------------------- pasos
def paso_publicos(d: Path, env: Dict[str, str], tokenizadores: Sequence[str], log: Path) -> Dict[str, Any]:
    res: Dict[str, Any] = {"comparacion": {}, "archivos": [], "tiempos_s": {}}
    for t in tokenizadores:
        salida = d / f"publico_{t}"
        dt, _ = ejecutar([PYTHON, "benchmark/public/run.py", "--tokenizer", t, "--out-dir", str(salida)], log, env)
        res["tiempos_s"][t] = round(dt, 1)
        for ext in ("json", "csv"):
            res["archivos"].append(copiar(salida / f"results.{ext}", d / f"results_{t}.{ext}"))
        shutil.rmtree(salida)
        if t == "o200k_base":
            res["comparacion"]["results.json"] = comparar_json_publico(d / "results_o200k_base.json", ROOT / "benchmark" / "public" / "results.json")
            res["comparacion"]["results.csv"] = comparar_tablas(d / "results_o200k_base.csv", ROOT / "benchmark" / "public" / "results.csv", ["dataset", "format"])
    # ahorro por snapshot y tokenizador (sin agregar entre tokenizadores)
    filas = []
    for t in tokenizadores:
        rep = json.loads((d / f"results_{t}.json").read_text(encoding="utf-8"))
        for ds in rep["datasets"]:
            f = ds["formats"]
            filas.append({"tokenizador": t, "backend": rep["tokenizer_backend"], "tiktoken": rep["tiktoken"], "dataset": ds["id"], "registros": ds["records"],
                          "sintetico": ds["id"] != "earthquakes", "tokens_json_compacto": f["json_compact"]["tokens"], "tokens_mini": f["mini"]["tokens"],
                          "ahorro_documento_pct": round(100 * (1 - f["mini"]["tokens"] / f["json_compact"]["tokens"]), 2),
                          "tokens_mini_documento_mas_contrato": f["mini"]["payload_plus_schema_tokens"],
                          "ahorro_documento_mas_contrato_pct": round(100 * (1 - f["mini"]["payload_plus_schema_tokens"] / f["json_compact"]["tokens"]), 2),
                          "estructura_compartida_mini": f["mini"]["shared_schema_tokens"], "prompt_mini_en": f["mini"]["prompt_tokens"],
                          "ida_y_vuelta_todos": all(x["roundtrip"] for x in f.values()),
                          "formato_toon_plano_elegido": ds["flattening"]["selected_toon"], "formato_csv_elegido": ds["flattening"]["selected_csv"]})
        tot = rep["summary"]
        filas.append({"tokenizador": t, "backend": rep["tokenizer_backend"], "tiktoken": rep["tiktoken"], "dataset": "TOTAL_4_snapshots", "registros": tot["records"],
                      "sintetico": None, "tokens_json_compacto": tot["tokens"]["json_compact"], "tokens_mini": tot["tokens"]["mini"],
                      "ahorro_documento_pct": tot["weighted_savings_pct"]["json_compact"],
                      "tokens_mini_documento_mas_contrato": sum(ds["formats"]["mini"]["payload_plus_schema_tokens"] for ds in rep["datasets"]),
                      "ahorro_documento_mas_contrato_pct": round(100 * (1 - sum(ds["formats"]["mini"]["payload_plus_schema_tokens"] for ds in rep["datasets"]) / tot["tokens"]["json_compact"]), 2),
                      "estructura_compartida_mini": sum(ds["formats"]["mini"]["shared_schema_tokens"] for ds in rep["datasets"]),
                      "prompt_mini_en": sum(ds["formats"]["mini"]["prompt_tokens"] for ds in rep["datasets"]),
                      "ida_y_vuelta_todos": tot["all_roundtrips_passed"], "formato_toon_plano_elegido": "", "formato_csv_elegido": ""})
    res["archivos"].append(escribir_csv(d / "ahorro_publicos_por_tokenizador.csv", filas))
    res["filas_ahorro"] = filas
    return res


def paso_linea_base(d: Path, env: Dict[str, str], rapido: bool, log: Path, tmp: Path) -> Dict[str, Any]:
    res: Dict[str, Any] = {"comparacion": {}, "archivos": [], "tiempos_s": {}}
    # 1. benchmark/run_benchmark.py (o200k_base y cl100k_base, como está archivado)
    salida_b = tmp / "benchmark_results"
    tam = "12,100" if rapido else "12,25,50,100,250,500"
    dt, _ = ejecutar([PYTHON, "benchmark/run_benchmark.py", "--sizes", tam, "--out-dir", str(salida_b)], log, env)
    res["tiempos_s"]["run_benchmark"] = round(dt, 1)
    for nombre in ("tokens.csv", "summary_12.csv", "roundtrip.csv"):
        res["archivos"].append(copiar(salida_b / nombre, d / "benchmark_results" / nombre))
    arch = ROOT / "benchmark" / "results"
    res["comparacion"]["benchmark/results/tokens.csv"] = comparar_tablas(d / "benchmark_results" / "tokens.csv", arch / "tokens.csv", ["prefix", "n", "tokenizer", "format"])
    res["comparacion"]["benchmark/results/summary_12.csv"] = comparar_tablas(d / "benchmark_results" / "summary_12.csv", arch / "summary_12.csv", ["prefix"])
    res["comparacion"]["benchmark/results/roundtrip.csv"] = comparar_tablas(d / "benchmark_results" / "roundtrip.csv", arch / "roundtrip.csv", ["prefix", "n"])
    docs = {}
    difs = 0
    for f in sorted((salida_b / "docs").rglob("dataset_12.*")):
        rel = f.relative_to(salida_b / "docs").as_posix()
        h = sha_texto_lf(f)
        a = arch / "docs" / rel
        docs[rel] = {"sha256_lf": h, "coincide_con_archivado": a.exists() and sha_texto_lf(a) == h}
        difs += not docs[rel]["coincide_con_archivado"]
    ev.escribir_json(d / "benchmark_results" / "docs_hashes.json", docs)
    res["archivos"].append(d / "benchmark_results" / "docs_hashes.json")
    res["comparacion"]["benchmark/results/docs"] = {"archivos": len(docs), "distintos": difs, "coincide_totalmente": difs == 0,
                                                     "nota": "hash SHA-256 sobre el texto normalizado a LF (en Windows se escriben con CRLF)"}
    return res


def paso_v1_run(d_base: Path, d_serie: Path, env: Dict[str, str], rapido: bool, log: Path, tmp: Path) -> Dict[str, Any]:
    """experiments/v1_tokens/run.py: la línea base va a la corrida de n=12, el resto a la de la serie."""
    salida = tmp / "v1_results"
    cmd = [PYTHON, "experiments/v1_tokens/run.py", "--salida", str(salida), "--sin-figuras", "--tokenizadores", ",".join(TOKENIZADORES)]
    if rapido:
        cmd += ["--dominios", ",".join(DOMINIOS_RAPIDO), "--tamanos", ",".join(str(n) for n in TAMANOS_RAPIDO)]
    dt, _ = ejecutar(cmd, log, env)
    arch = ROOT / "experiments" / "v1_tokens" / "results"
    res: Dict[str, Any] = {"tiempo_s": round(dt, 1), "archivos_linea_base": [], "archivos_serie": [], "comparacion_linea_base": {}, "comparacion_serie": {}}
    for nombre in ("linea_base_n12.csv", "linea_base_n12_agregado.csv"):
        res["archivos_linea_base"].append(copiar(salida / nombre, d_base / nombre))
    res["comparacion_linea_base"]["linea_base_n12.csv"] = comparar_tablas(d_base / "linea_base_n12.csv", arch / "linea_base_n12.csv", ["dominio", "metrica"])
    res["comparacion_linea_base"]["linea_base_n12_agregado.csv"] = comparar_tablas(d_base / "linea_base_n12_agregado.csv", arch / "linea_base_n12_agregado.csv", ["referencia"])
    lb = leer_csv(d_base / "linea_base_n12.csv")
    res["celdas_linea_base"] = len(lb)
    res["celdas_linea_base_que_no_coinciden_con_summary_12"] = sum(1 for r in lb if r["coincide"] != "True")
    tablas = {"tokens.csv": ["tokenizador", "variante", "dominio", "n", "formato"],
              "ahorro_por_dominio.csv": ["tokenizador", "variante", "dominio", "n", "referencia"],
              "ahorro_resumen.csv": ["tokenizador", "variante", "n", "referencia"],
              "ajuste_lineal.csv": ["tokenizador", "variante", "dominio", "formato"],
              "equilibrio_tokens.csv": ["tokenizador", "idioma", "instr_mini", "instr_json", "dominio"],
              "equilibrio_tokens_resumen.csv": ["tokenizador", "idioma", "instr_mini", "instr_json"],
              "instruccion_tokens.csv": ["tokenizador", "dominio", "idioma", "instruccion"]}
    for nombre, claves in tablas.items():
        res["archivos_serie"].append(copiar(salida / nombre, d_serie / "archivado_pipeline" / nombre))
        res["comparacion_serie"][f"experiments/v1_tokens/results/{nombre}"] = comparar_tablas(d_serie / "archivado_pipeline" / nombre, arch / nombre, claves)
    muestras = {}
    for f in sorted((salida / "instrucciones_muestra").glob("*.txt")):
        a = arch / "instrucciones_muestra" / f.name
        muestras[f.name] = a.exists() and sha_texto_lf(a) == sha_texto_lf(f)
    res["comparacion_serie"]["instrucciones_muestra"] = {"archivos": len(muestras), "distintos": sum(not v for v in muestras.values()),
                                                         "coincide_totalmente": all(muestras.values())}
    return res


def paso_serie(d: Path, toks: Dict[str, Any], rapido: bool, log: Path) -> Dict[str, Any]:
    import comun as C  # noqa: F401
    import serie as S
    tamanos = TAMANOS_RAPIDO if rapido else sorted(set(TAMANOS_SERIE) | {12})
    dominios = DOMINIOS_RAPIDO if rapido else None
    t0 = time.time()
    filas, filas_rev = S.medir_serie(toks, ["muestreo", "ciclo"], tamanos, dominios, log=lambda s: print(s, flush=True))
    dt = time.time() - t0
    res: Dict[str, Any] = {"tiempo_s": round(dt, 1), "archivos": [], "filas": filas, "filas_rev": filas_rev}
    res["archivos"].append(escribir_csv(d / "tokens_largo.csv", filas))
    res["archivos"].append(escribir_csv(d / "reversibilidad.csv", filas_rev))
    return res


def paso_criterio(d: Path, filas: List[Dict[str, Any]], filas_rev: List[Dict[str, Any]], rapido: bool) -> Dict[str, Any]:
    import criterio as K
    t0 = time.time()
    crit = K.cargar_criterio()
    e = K.evaluar(filas, crit, B=2000 if rapido else 10000)
    ev.escribir_json(d / "criterio_v1_resultado.json", e)
    refs = K.tabla_referencias(filas, filas_rev, float(crit["interpretacion_primaria"]["umbral_pct"]), B=500 if rapido else 2000)
    escribir_csv(d / "ahorro_por_referencia.csv", refs)
    (d / "criterio_v1_resultado.md").write_text(K.informe_md(e), encoding="utf-8", newline="\n")
    return {"evaluacion": e, "archivos": [d / "criterio_v1_resultado.json", d / "criterio_v1_resultado.md", d / "ahorro_por_referencia.csv"], "tiempo_s": round(time.time() - t0, 1)}


def consistencia_serie(filas: List[Dict[str, Any]], d_serie: Path) -> Dict[str, Any]:
    """La serie con reversibilidad debe dar los mismos tokens que la tabla archivada (mismos 8 formatos, mismos n)."""
    p = d_serie / "archivado_pipeline" / "tokens.csv"
    arch = {(r["tokenizador"], r["variante"], r["dominio"], r["n"], r["formato"]): int(r["tokens"]) for r in leer_csv(p)}
    comparadas = distintas = 0
    for f in filas:
        k = (f["tokenizador"], f["variante"], f["dominio"], str(f["n"]), f["formato"])
        if k in arch:
            comparadas += 1
            distintas += arch[k] != f["tokens"]
    return {"celdas_comparadas": comparadas, "celdas_distintas": distintas, "coincide": comparadas > 0 and distintas == 0}


def paso_conciliacion(d: Path, toks: Dict[str, Any], dirs: Dict[str, Path], rapido: bool) -> Dict[str, Any]:
    import conciliacion as Q
    import errata_v7_v8 as E
    t0 = time.time()
    rutas = {"summary_12": ev.ruta_relativa(dirs["base"] / "benchmark_results" / "summary_12.csv"),
             "tokens_benchmark": ev.ruta_relativa(dirs["base"] / "benchmark_results" / "tokens.csv"),
             "ahorro_resumen": ev.ruta_relativa(dirs["serie"] / "archivado_pipeline" / "ahorro_resumen.csv"),
             "tokens_serie": ev.ruta_relativa(dirs["serie"] / "archivado_pipeline" / "tokens.csv"),
             "publico": ev.ruta_relativa(dirs["pub"] / "results_o200k_base.json")}
    cifras = Q.cifras(dirs["base"] / "benchmark_results" / "summary_12.csv", dirs["base"] / "benchmark_results" / "tokens.csv",
                      dirs["serie"] / "archivado_pipeline" / "ahorro_resumen.csv", dirs["serie"] / "archivado_pipeline" / "tokens.csv",
                      dirs["pub"] / "results_o200k_base.json", rutas)
    desg = Q.desglose(toks, DOMINIOS_RAPIDO if rapido else None)
    resumen_unidades = {}
    for variante, n in (("ciclo", 12), ("muestreo", 100)):
        resumen_unidades[f"n{n}_{variante}"] = {t: Q.ahorros_desglose(desg, variante, n, t) for t in toks}
    doc = {"definiciones": Q.DEFINICIONES, "cifras": cifras, "ahorro_por_unidad": resumen_unidades,
           "alcance": "rapido (subconjunto de dominios: las cifras NO son las publicadas)" if rapido else "completo"}
    ev.escribir_json(d / "conciliacion_cifras.json", doc)
    (d / "conciliacion_cifras.md").write_text(Q.informe_md(cifras, resumen_unidades), encoding="utf-8", newline="\n")
    archivos = [d / "conciliacion_cifras.json", d / "conciliacion_cifras.md", escribir_csv(d / "desglose_dominio_tokenizador.csv", desg)]
    errata = E.verificar()
    ev.escribir_json(d / "errata_v7_v8_verificacion.json", errata)
    archivos.append(d / "errata_v7_v8_verificacion.json")
    return {"cifras": cifras, "archivos": archivos, "tiempo_s": round(time.time() - t0, 1), "errata": errata, "ahorro_por_unidad": resumen_unidades}


def paso_v5(d: Path, env: Dict[str, str], log: Path, tmp: Path) -> Dict[str, Any]:
    """experiments/v5_ancho/correr.py con los tres tokenizadores; se compara con lo archivado."""
    salida = tmp / "v5_results"
    dt, _ = ejecutar([PYTHON, "experiments/v5_ancho/correr.py", "--salida", str(salida)], log, env)
    arch = ROOT / "experiments" / "v5_ancho" / "results"
    archivos = [copiar(salida / n, d / n) for n in ("ancho_largo.csv", "ancho_resumen.csv", "meta.json")]
    cmp = {"ancho_largo.csv": comparar_tablas(d / "ancho_largo.csv", arch / "ancho_largo.csv", ["tokenizador", "ancho", "lote", "rep", "formato"]),
           "ancho_resumen.csv": comparar_tablas(d / "ancho_resumen.csv", arch / "ancho_resumen.csv", ["tokenizador", "formato", "ancho", "lote"]),
           "meta.json": {"coincide_totalmente": json.loads((d / "meta.json").read_text(encoding="utf-8")) == json.loads((arch / "meta.json").read_text(encoding="utf-8"))}}
    return {"tiempo_s": round(dt, 1), "archivos": archivos, "comparacion": cmp}


# ---------------------------------------------------------------- manifiestos
def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--rapido", action="store_true", help="subconjunto para pruebas (3 dominios, n=1,12,100, público solo con o200k_base)")
    ap.add_argument("--sello", default=None, help="sello de los run_id (por defecto, fecha y hora UTC)")
    ap.add_argument("--salida-base", default=None, help="directorio base de las corridas (por defecto evidencia/corridas)")
    ap.add_argument("--con-v5", action="store_true", help="reproduce también V5 (ancho del registro, +2 min) en v5-ancho-<sello>")
    a = ap.parse_args(argv)
    t_total = time.time()
    sello = (a.sello or datetime.now(timezone.utc).strftime("%Y%m%dt%H%M%Sz")).lower()
    base = Path(a.salida_base) if a.salida_base else ev.directorio_corridas()
    ids = {k: f"v1-{k}-{sello}" for k in ("linea_base_n12", "serie_n", "publicos", "conciliacion")}
    dirs = {"base": base / ids["linea_base_n12"], "serie": base / ids["serie_n"], "pub": base / ids["publicos"], "conc": base / ids["conciliacion"]}
    for p in dirs.values():
        p.mkdir(parents=True, exist_ok=True)
    codigo = ev.info_codigo()  # antes de escribir nada: describe el código ejecutado
    entorno = ev.info_entorno()
    cmd_txt = "python tools/ejecutar_v1.py" + (" --rapido" if a.rapido else "") + (" --con-v5" if a.con_v5 else "") + f" --sello {sello}"

    vocab_local.modo_sin_red()
    vocab_local.preparar_cache()
    env = dict(os.environ, PYTHONIOENCODING="utf-8", PYTHONPATH=str(ROOT / "src"))
    tmp = Path(tempfile.mkdtemp(prefix="v1-ejecucion-"))
    log = tmp / "log.txt"
    tiempos: Dict[str, float] = {}

    import comun as C
    import procedencia as P
    toks = C.tokenizadores(TOKENIZADORES)
    fichas = info_tokenizadores(toks)

    print("== benchmark público", flush=True)
    t = time.time()
    pub = paso_publicos(dirs["pub"], env, ["o200k_base"] if a.rapido else TOKENIZADORES, log)
    tiempos["publicos"] = round(time.time() - t, 1)

    print("== línea base n=12 (benchmark/run_benchmark.py)", flush=True)
    t = time.time()
    base_res = paso_linea_base(dirs["base"], env, a.rapido, log, tmp)
    tiempos["linea_base_benchmark"] = round(time.time() - t, 1)

    print("== experiments/v1_tokens/run.py", flush=True)
    t = time.time()
    v1 = paso_v1_run(dirs["base"], dirs["serie"], env, a.rapido, log, tmp)
    tiempos["v1_run"] = round(time.time() - t, 1)

    print("== serie con reversibilidad", flush=True)
    t = time.time()
    serie = paso_serie(dirs["serie"], toks, a.rapido, log)
    tiempos["serie_reversibilidad"] = round(time.time() - t, 1)
    cons = consistencia_serie(serie["filas"], dirs["serie"])

    print("== criterio", flush=True)
    crit = paso_criterio(dirs["serie"], serie["filas"], serie["filas_rev"], a.rapido)
    tiempos["criterio"] = crit["tiempo_s"]

    # n=12 con tres tokenizadores: tabla propia de la corrida de línea base
    n12 = [f for f in serie["filas"] if int(f["n"]) == 12]
    base_res["archivos"].append(escribir_csv(dirs["base"] / "tokens_n12_tres_tokenizadores.csv", n12))
    rev12 = [r for r in serie["filas_rev"] if int(r["n"]) == 12]
    base_res["archivos"].append(escribir_csv(dirs["base"] / "reversibilidad_n12.csv", rev12))

    print("== conciliación", flush=True)
    conc = paso_conciliacion(dirs["conc"], toks, dirs, a.rapido)
    tiempos["conciliacion"] = conc["tiempo_s"]

    # procedencia de datos en cada corrida
    proc = {"dominios": P.dominios_info(), "publicos": P.publicos_info(), "contratos": P.contratos_info(),
            "muestra_independiente": "los 4 snapshots públicos (1.902 objetos únicos) y los 12 registros base de cada dominio (168); las series n > 12 son replicación de base"}
    for d in dirs.values():
        ev.escribir_json(d / "procedencia_datos.json", proc)
    v5 = None
    if a.con_v5 and not a.rapido:
        print("== V5 (ancho)", flush=True)
        t = time.time()
        dirs["v5"] = base / f"v5-ancho-{sello}"
        dirs["v5"].mkdir(parents=True, exist_ok=True)
        v5 = paso_v5(dirs["v5"], env, log, tmp)
        tiempos["v5"] = round(time.time() - t, 1)
    shutil.copyfile(log, dirs["conc"] / "log.txt")
    tiempos["total"] = round(time.time() - t_total, 1)
    estado = "parcial" if a.rapido else "ejecutado"

    # ---------------------------------------------------------- manifiestos
    ev_crit = crit["evaluacion"]
    resumen_tok = ev_crit["primario"]["resumen_por_tokenizador"]
    comunes = dict(codigo=codigo, entorno=entorno, tokenizadores=fichas, gasto_usd=0,
                   estado_ejecucion=estado,
                   limitaciones=[
                       "Los tres tokenizadores son de la misma familia BPE de OpenAI: no sustituyen a un tokenizador independiente; para Anthropic, Google o DeepSeek son una aproximación.",
                       "n > 12 replica los 12 registros base de cada dominio (replicacion_de_base): mide longitud de serialización, no diversidad semántica.",
                       "Los 14 dominios son conjuntos escritos a mano (sintéticos); q extiende a a.",
                       "Conteo local de texto: no es el conteo de solicitud ni el usage de ningún proveedor."] + (["Corrida --rapido: subconjunto de dominios y tamaños; sus cifras NO son las publicadas."] if a.rapido else []))

    def guardar(clave: str, archivos: List[Path], **campos: Any) -> Path:
        m = ev.nueva_corrida("V1", "reproducido_local", cmd_txt, run_id=ids[clave], **comunes, **campos)
        m["codigo"] = codigo
        return ev.guardar_corrida(m, archivos=archivos, directorio=dirs[{"linea_base_n12": "base", "serie_n": "serie", "publicos": "pub", "conciliacion": "conc"}[clave]])

    conj_dom = P.conjuntos_manifiesto(True, False)
    conj_pub = P.conjuntos_manifiesto(False, True)
    contratos = [{k: c[k] for k in ("prefijo", "ruta", "sha256", "version")} for c in P.contratos_info()]

    res_lb = {"comparacion_con_archivado": {**base_res["comparacion"], **v1["comparacion_linea_base"]}, "tiempos_s": {**tiempos},
              "celdas_linea_base_v1_run": v1["celdas_linea_base"], "celdas_linea_base_que_no_coinciden_con_summary_12": v1["celdas_linea_base_que_no_coinciden_con_summary_12"],
              "n12_filas_tres_tokenizadores": len(n12), "reversibilidad_n12": _contar_rev(rev12)}
    guardar("linea_base_n12", base_res["archivos"] + v1["archivos_linea_base"], conjuntos=conj_dom, contratos=contratos,
            parametros={"n": 12, "protocolo": "ciclo (benchmark) y ciclo+muestreo (serie)", "semilla_muestreo": C.SEMILLA, "sin_red": True, "sin_api": True},
            resumen=res_lb, resultado="no_evaluable",
            notas="Reproduce la línea base de 12 registros x 14 dominios y la compara fila a fila con lo archivado. r50k_base no estaba archivado para n=12: se mide ahora.")

    res_se = {"comparacion_con_archivado": v1["comparacion_serie"], "consistencia_con_pipeline_archivado": cons, "tiempos_s": {**tiempos},
              "criterio": {"veredicto": ev_crit["primario"]["veredicto"],
                           "dominios_ge_30_por_tokenizador": {t: r["dominios_ge_umbral"] for t, r in resumen_tok.items()},
                           "media_por_dominio_pct": {t: round(r["media_por_dominio_pct"], 2) for t, r in resumen_tok.items()},
                           "agregado_suma_pct": {t: round(r["agregado_suma_pct"], 2) for t, r in resumen_tok.items()}},
              "reversibilidad": _contar_rev(serie["filas_rev"]), "filas_tokens": len(serie["filas"])}
    criterio_manifiesto = {**json.loads((ROOT / "experiments" / "v1_tokens" / "criterio_v1.json").read_text(encoding="utf-8")),
                           "archivo": "experiments/v1_tokens/criterio_v1.json",
                           "sha256_archivo": ev.sha256_archivo(ROOT / "experiments" / "v1_tokens" / "criterio_v1.json"),
                           "evaluacion": "criterio_v1_resultado.json"}
    resultado = ev_crit["primario"]["veredicto"]  # "no_evaluable" si el alcance no es completo
    guardar("serie_n", serie["archivos"] + crit["archivos"] + v1["archivos_serie"], conjuntos=conj_dom, contratos=contratos,
            parametros={"tamanos": sorted({int(f['n']) for f in serie["filas"]}), "variantes": ["muestreo", "ciclo"], "semilla_muestreo": C.SEMILLA,
                        "bootstrap": {"B": 2000 if a.rapido else 10000, "semilla": 20260914, "nivel": "dominio"}, "sin_red": True, "sin_api": True},
            resumen=res_se, criterio=criterio_manifiesto, resultado=resultado,
            notas="Veredicto según la interpretación primaria fijada el 2026-09-30 ANTES del análisis y SUJETA A APROBACIÓN del asesor; las lecturas alternativas están en criterio_v1_resultado.json.")

    res_pu = {"comparacion_con_archivado": pub["comparacion"], "tiempos_s": pub["tiempos_s"], "ahorro": pub["filas_ahorro"]}
    guardar("publicos", pub["archivos"], conjuntos=conj_pub, contratos=[],
            parametros={"tokenizadores": [f["nombre"] for f in fichas if f["nombre"] in {x["tokenizador"] for x in pub["filas_ahorro"]}],
                        "contrato_mini": "inferido del snapshot completo (mini-domain/1): medición de serialización, no de generalización", "sin_red": True, "sin_api": True},
            resumen=res_pu, resultado="no_evaluable",
            notas="Los 4 snapshots se verifican contra su SHA-256 de sources.json antes de medir (run.py aborta si difiere). Con 4 conjuntos no se evalúa el criterio de 14 dominios.")

    res_co = {"cifras": [{k: c[k] for k in ("cifra_citada", "cifra_id", "valor_recalculado_pct", "tokenizador", "estadistico")} for c in conc["cifras"]],
              "errata_v7_v8": {"conciliacion_cima": conc["errata"]["v8"]["conciliacion_clases"]["estado"],
                               "v7_lote_maximo_sin_perdida": conc["errata"]["v7"]["lote_maximo_sin_perdida"]["definicion_estricta_por_lote"]},
              "tiempos_s": tiempos}
    guardar("conciliacion", conc["archivos"] + [dirs["conc"] / "log.txt"], conjuntos=conj_dom + conj_pub, contratos=contratos,
            parametros={"sin_red": True, "sin_api": True}, resumen=res_co, resultado="no_evaluable",
            notas="Las cuatro cifras se derivan de los archivos de las otras tres corridas de este sello.")
    if v5 is not None:
        m5 = ev.nueva_corrida("V5", "reproducido_local", cmd_txt, run_id=f"v5-ancho-{sello}", codigo=codigo, entorno=entorno, tokenizadores=fichas, gasto_usd=0,
                              estado_ejecucion="ejecutado", resultado="no_evaluable",
                              conjuntos=[{"nombre": "v5_sintetico (repertorio POOL de correr.py)", "ruta": "experiments/v5_ancho/correr.py",
                                          "sha256": ev.sha256_archivo(ROOT / "experiments" / "v5_ancho" / "correr.py"), "sintetico": True,
                                          "licencia": "MIT (licencia del repositorio)", "fuente": "generado por correr.py", "registros": None,
                                          "semilla": 20260915, "replicacion_de_base": False}],
                              parametros={"anchos": [3, 5, 8, 12, 20, 32, 50], "lotes": [1, 10, 100, 1000], "repeticiones": 5, "semilla": 20260915, "sin_red": True, "sin_api": True},
                              resumen={"comparacion_con_archivado": v5["comparacion"], "tiempo_s": v5["tiempo_s"]},
                              limitaciones=["Sintético a propósito (barre el ancho); no es un estudio poblacional.",
                                            "Los tres tokenizadores son de la misma familia BPE de OpenAI."],
                              notas="Reproducción de V5 con r50k_base incluido, sin red: r50k_base sale ahora de benchmark/vocab.")
        ev.guardar_corrida(m5, archivos=v5["archivos"], directorio=dirs["v5"])
    shutil.rmtree(tmp, ignore_errors=True)
    print(json.dumps({"sello": sello, "tiempos_s": tiempos, "veredicto": ev_crit["primario"]["veredicto"], "estado": estado}, ensure_ascii=False))
    return 0


def _contar_rev(filas: List[Dict[str, Any]]) -> Dict[str, Any]:
    por: Dict[str, Dict[str, int]] = {}
    for f in filas:
        por.setdefault(f["formato"], {}).setdefault(f["estado"], 0)
        por[f["formato"]][f["estado"]] += 1
    return {"documentos_verificados_por_formato_y_estado": por, "no_reversibles": sorted({f["formato"] for f in filas if f["estado"] == "no_reversible"})}


if __name__ == "__main__":
    raise SystemExit(main())
