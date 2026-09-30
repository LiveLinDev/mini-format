#!/usr/bin/env python3
"""Ejecuta el estudio de optimización (OPT) y registra la corrida en evidencia/corridas/opt-*.

Mide, para tres dominios (tickets = representativo, eventos = favorable, comentarios = sin ahorro), los tokens
de la SALIDA, de la INSTRUCCIÓN completa y del TOTAL de JSON compacto, del perfil general (mini from-schema y
mini build) y de la configuración especializada, con tres tokenizadores locales (o200k_base, cl100k_base,
r50k_base) y lotes n = 1, 5, 10, 25, 50, 100, 250. Verifica la ida y vuelta exacta ANTES de contar, calcula
el punto de equilibrio n*, genera el ejemplo de «Cómo funciona» y las carpetas de examples/optimizacion/, y
evalúa el criterio fijado de antemano en experiments/optimizacion/criterio.json.

Todo local: sin red, sin claves, sin llamadas a APIs de modelos. Procedencia: reproducido_local.

    python tools/ejecutar_opt.py                       # corrida completa (≈ 1-3 min)
    python tools/ejecutar_opt.py --rapido --salida /tmp/opt   # prueba de humo; no registra evidencia oficial
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "src"))
sys.path.insert(0, str(RAIZ / "tools"))
sys.path.insert(0, str(RAIZ / "experiments" / "optimizacion"))

import evidencia_lib as ev  # noqa: E402

import carpeta_ejemplos  # noqa: E402
import datos  # noqa: E402
import diseno  # noqa: E402
import ejemplo  # noqa: E402
import medir  # noqa: E402
import perfiles  # noqa: E402
import propuesta  # noqa: E402
import tokenizadores  # noqa: E402
from dominios import dominios  # noqa: E402

CRITERIO = RAIZ / "experiments" / "optimizacion" / "criterio.json"
ESPECIALIZADO = medir.PRIMARIO_ESPECIALIZADO
DOMINIOS = ("tickets", "eventos", "comentarios")


# ----------------------------------------------------------------------------- utilidades
def _redondear(v: Any) -> Any:
    return round(v, 4) if isinstance(v, float) else v


def escribir_csv(ruta: Path, filas: List[Dict[str, Any]], columnas: Optional[List[str]] = None) -> Path:
    ruta.parent.mkdir(parents=True, exist_ok=True)
    columnas = columnas or list(filas[0].keys())
    with open(ruta, "w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh, lineterminator="\n")
        w.writerow(columnas)
        for f in filas:
            w.writerow(["" if f.get(c) is None else _redondear(f.get(c)) for c in columnas])
    return ruta


def _curva_ancha(filas_curva: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Una fila por (dominio, tokenizador, n): salida y total de las combinaciones, para graficar el equilibrio."""
    claves = ["json_compacto.ninguna", "json_compacto.schema_con_ejemplo", "general_fromschema.con_ejemplo",
              "general_dominio.con_ejemplo", "especializado.compacta_sin_ejemplo", "especializado.compacta_con_ejemplo"]
    por: Dict[tuple, Dict[str, Any]] = {}
    for f in filas_curva:
        k = (f["dominio"], f["tokenizador"], f["n"])
        fila = por.setdefault(k, {"dominio": k[0], "tokenizador": k[1], "n": k[2]})
        etiqueta = f"{f['perfil']}.{f['instruccion']}"
        if etiqueta in claves:
            fila[f"{etiqueta}.salida"] = f["tokens_salida"]
            fila[f"{etiqueta}.total"] = f["tokens_total"]
    return [por[k] for k in sorted(por)]


def registros_verificados(filas: List[Dict[str, Any]]) -> Dict[str, Dict[str, int]]:
    """Registros con ida y vuelta exacta comprobada, por dominio y perfil (lotes de la tabla principal)."""
    vistos = set()
    out: Dict[str, Dict[str, int]] = {}
    for f in filas:
        k = (f["dominio"], f["perfil"], f["n"], f["lote"])
        if k in vistos:
            continue
        vistos.add(k)
        d = out.setdefault(f["dominio"], {})
        d[f["perfil"]] = d.get(f["perfil"], 0) + f["n"]
    return out


def escribir_json_ordenado(ruta: Path, obj: Any) -> None:
    """JSON legible que CONSERVA el orden de claves (el de los objetos de la aplicación importa)."""
    ruta.parent.mkdir(parents=True, exist_ok=True)
    ruta.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")


def evaluar_criterio(comparacion: List[Dict[str, Any]], fallos: List[Dict[str, Any]], n: int = 100) -> Dict[str, Any]:
    """Aplica criterio.json tal como se fijó: C1 (salida >= 30 %), C2 (total < JSON sin instrucción), C3 (0 fallos)."""
    crit = json.loads(CRITERIO.read_text(encoding="utf-8"))
    umbral = crit["criterios"][0]["umbral_pct"]
    out: Dict[str, Any] = {"archivo": CRITERIO.relative_to(RAIZ).as_posix(), "sha256": ev.sha256_archivo(CRITERIO),
                           "fijado_en_los_commits": ["c196ec9", "42b3c91"], "n": n, "detalle": {}}
    c1: Dict[str, bool] = {}
    c2: Dict[str, bool] = {}
    for tk in tokenizadores.NOMBRES:
        fila = next((c for c in comparacion if c["dominio"] == "tickets" and c["tokenizador"] == tk and c["n"] == n
                     and (c["perfil"], c["instruccion"]) == ESPECIALIZADO), None)
        if fila is None:
            c1[tk] = c2[tk] = False
            out["detalle"][tk] = {"error": "no hay fila de comparación para tickets, n y especializado"}
            continue
        c1[tk] = bool(fila["ahorro_salida_pct"] >= umbral)
        c2[tk] = bool(fila["mini_total"] < fila["json_compacto_total_sin_instruccion"])
        out["detalle"][tk] = {"ahorro_salida_pct": round(fila["ahorro_salida_pct"], 3), "mini_total": fila["mini_total"],
                              "json_compacto_total_sin_instruccion": fila["json_compacto_total_sin_instruccion"],
                              "ahorro_total_pct": round(fila["ahorro_total_pct"], 3)}
    # C3: lectura estricta (solo puede endurecer el criterio): cualquier fallo de equivalencia en los perfiles
    # que el criterio evalúa (json_abreviado, general_fromschema, especializado) lo incumple. Los fallos del
    # perfil mini build (general_dominio) se publican aparte como descriptivos.
    en_alcance = [f for f in fallos if f["perfil"] in ("json_abreviado", "general_fromschema", "especializado", "json_compacto", "json_legible")]
    fuera = [f for f in fallos if f["perfil"] == "general_dominio"]
    out.update(C1_ahorro_salida_ge_30_en_los_tres_tokenizadores=all(c1.values()), C1_por_tokenizador=c1,
               C2_total_menor_que_json_en_los_tres_tokenizadores=all(c2.values()), C2_por_tokenizador=c2,
               C3_equivalencia_exacta_sin_fallos=not en_alcance, C3_fallos_en_alcance=len(en_alcance),
               fallos_general_dominio_descriptivos=len(fuera))
    ok = out["C1_ahorro_salida_ge_30_en_los_tres_tokenizadores"] and out["C2_total_menor_que_json_en_los_tres_tokenizadores"] \
        and out["C3_equivalencia_exacta_sin_fallos"]
    out["resultado"] = "cumple" if ok else "no_cumple"
    return out


# ----------------------------------------------------------------------------- corrida
def correr(salida: Path, run_id: str, tamanos, nmax: int, con_ejemplos: bool, oficial: bool) -> Path:
    t0 = time.time()
    comando = "python tools/ejecutar_opt.py" + ("" if oficial else " --rapido")
    # el manifiesto se crea ANTES de escribir nada para que info_codigo describa el código ejecutado
    m = ev.nueva_corrida("OPT", "reproducido_local", comando, run_id=run_id)
    salida.mkdir(parents=True, exist_ok=True)

    filas: List[Dict[str, Any]] = []
    fallos: List[Dict[str, Any]] = []
    curva_filas: List[Dict[str, Any]] = []
    equil: List[Dict[str, Any]] = []
    prop: List[Dict[str, Any]] = []
    hashes_datos: Dict[str, str] = {}
    for d in DOMINIOS:
        print(f"[{d}] lotes {list(tamanos)} ...", flush=True)
        f, fl, prep = medir.medir_dominio(d, tamanos)
        filas += f
        fallos += fl
        cur = medir.curva(d, prep, nmax, fallos=fallos)
        curva_filas += cur
        equil += medir.equilibrios(cur)
        regs250 = prep.dom.generar(datos.SEMILLA_PRUEBA, 0, max(tamanos))
        hashes_datos[d] = ev.sha256_texto(json.dumps(regs250, ensure_ascii=False, sort_keys=False, separators=(",", ":")))
        for n in tamanos:
            regs = prep.dom.generar(datos.SEMILLA_PRUEBA, 0, n)
            for r in propuesta.medir(prep.dom, regs, perfiles.salida_general(prep.dom, regs),
                                     perfiles.salida_especializada(prep.esp, regs)):
                prop.append({"dominio": d, "n": n, **r})

    agr = medir.agregar(filas)
    comp = medir.comparar(agr)
    ancha = _curva_ancha(curva_filas)

    archivos: List[Path] = []
    archivos.append(escribir_csv(salida / "resultados_por_lote.csv", filas))
    archivos.append(escribir_csv(salida / "resultados_resumen.csv", agr))
    archivos.append(escribir_csv(salida / "comparacion.csv", comp))
    archivos.append(escribir_csv(salida / "equilibrio.csv", equil))
    archivos.append(escribir_csv(salida / "curva_equilibrio.csv", ancha))
    archivos.append(escribir_csv(salida / "propuesta_simulacion.csv", prop))
    escribir_json_ordenado(salida / "fallos_de_equivalencia.json", fallos)
    archivos.append(salida / "fallos_de_equivalencia.json")

    crit = evaluar_criterio(comp, fallos, 100 if 100 in tamanos else max(tamanos))
    escribir_json_ordenado(salida / "criterio_evaluado.json", crit)
    archivos.append(salida / "criterio_evaluado.json")

    ej = ejemplo.construir(comp, equil)
    escribir_json_ordenado(salida / "ejemplo_tickets.json", ej)
    archivos.append(salida / "ejemplo_tickets.json")

    contratos = []
    prompts = []
    if con_ejemplos:
        carpeta_ejemplos.escribir()
        for d in DOMINIOS:
            dom = dominios()[d]
            base = carpeta_ejemplos.DESTINO / d
            contratos.append({**ev.referencia_archivo(base / "contrato_general.json"), "prefijo": dom.prefijo_general, "version": 1})
            contratos.append({**ev.referencia_archivo(base / "contrato_especializado.json"), "prefijo": dom.prefijo_especializado, "version": 1})
            contratos.append({**ev.referencia_archivo(base / "mapa.json"), "prefijo": dom.prefijo_especializado, "version": 1})
            o200 = tokenizadores.obtener("o200k_base")
            for arch in ("instruccion_general_con_ejemplo.es.txt", "instruccion_especializada_compacta_con_ejemplo.es.txt",
                         "instruccion_json_con_ejemplo.txt"):
                p = base / arch
                prompts.append({"id": f"{d}/{arch}", "ruta": ev.ruta_relativa(p), "sha256": ev.sha256_archivo(p),
                                "tokens": o200.contar(p.read_text(encoding="utf-8").rstrip("\n"))})

    conjuntos = []
    for d in DOMINIOS:
        dom = dominios()[d]
        if dom.sintetico:
            fuente = datos.RAIZ / "experiments" / "optimizacion" / "datos.py"
            conjuntos.append({"nombre": f"{d} (sintético determinista)", "ruta": ev.ruta_relativa(fuente), "sha256": ev.sha256_archivo(fuente),
                              "sintetico": True, "licencia": "MIT (este repositorio)", "fuente": "generador determinista con semilla registrada",
                              "registros": max(tamanos), "semilla": datos.SEMILLA_PRUEBA,
                              "sha256_registros_lote0": hashes_datos[d], "semilla_desarrollo": datos.SEMILLA_DESARROLLO})
        else:
            conjuntos.append({"nombre": f"{d} (JSONPlaceholder, datos públicos de prueba)", "ruta": ev.ruta_relativa(datos.COMENTARIOS),
                              "sha256": ev.sha256_archivo(datos.COMENTARIOS), "sintetico": False, "licencia": "MIT (typicode)",
                              "fuente": "https://jsonplaceholder.typicode.com/comments (snapshot archivado en benchmark/public/data)",
                              "registros": 500, "semilla": None, "sha256_registros_lote0": hashes_datos[d],
                              "particion": "desarrollo = registros 0..149; prueba = 150..499"})
    for d in DOMINIOS:
        p = diseno.DIRECTORIO / f"{d}.json"
        contratos.append({**ev.referencia_archivo(p), "prefijo": dominios()[d].prefijo_especializado, "version": 1,
                          "nota": "registro de la búsqueda de diseño sobre el conjunto de desarrollo"})

    tk = tokenizadores.todos()
    m["conjuntos"] = conjuntos
    m["contratos"] = contratos
    m["prompts"] = prompts
    m["tokenizadores"] = [t.describir() | {"tipo": "exacto_local"} for t in tk.values()]
    m["parametros"] = {"tamanos_de_lote": list(tamanos), "nmax_equilibrio": nmax, "lotes_por_tamano": "hasta 5 lotes disjuntos (comentarios: los que caben en el tramo de prueba)",
                       "separador_del_total": "salto de línea doble", "idioma_instrucciones": "es",
                       "muestras_de_mini_build": perfiles.MUESTRAS_DOMINIO, "registros_del_ejemplo_de_instruccion": perfiles.EJEMPLO_REGISTROS,
                       "semilla_prueba": datos.SEMILLA_PRUEBA, "semilla_desarrollo": datos.SEMILLA_DESARROLLO,
                       "json_linea_base": "compacto (separadores , y :), UTF-8 sin escapes, envuelto en {clave:[...]}; instrucción 0 en la lectura primaria",
                       "tokens_de_prompts": "o200k_base sobre el texto del archivo sin salto final",
                       "gasto": "sin llamadas de API ni claves"}
    resumen = resumen_cifras(comp, equil, crit)
    resumen["registros_con_ida_y_vuelta_verificada"] = registros_verificados(filas)
    resumen["fallos_de_equivalencia"] = len(fallos)
    m["resumen"] = resumen
    m["criterio"] = crit
    m["resultado"] = crit["resultado"] if oficial else "no_evaluable"
    m["estado_ejecucion"] = "ejecutado" if oficial else "parcial"
    m["gasto_usd"] = 0
    m["conteos"] = {"registros_solicitados": None, "registros_recibidos": None, "registros_validos": None,
                    "registros_reparados": None, "registros_validos_finales": None}
    m["limitaciones"] = [
        "Sin llamadas a modelos: no se midió si un modelo real sigue la instrucción compacta ni con qué tasa de validez; solo se midió texto.",
        "Los tokenizadores son tres BPE de OpenAI con vocabulario local: aproximan, no son usage ni conteo de solicitud de ningún proveedor, y son una aproximación para Anthropic, Google o DeepSeek.",
        "El total suma tokens de entrada y de salida sin ponderar por precio; el costo en dinero depende de la tarifa de cada proveedor (no se calcula aquí).",
        "Dos de los tres dominios son sintéticos; el de eventos es un caso FAVORABLE por diseño y su ahorro no es una promesa general.",
        "El perfil mini build (mini-domain/1) infiere el contrato de 100 registros de desarrollo; con otra muestra puede cambiar.",
        "La configuración especializada se diseñó con un conjunto de desarrollo y se midió con otro, pero ambos vienen del mismo generador.",
        "Los registros de ejemplo de «Cómo funciona» provienen de grabaciones de procedencia no verificable (asistido_ia).",
    ]
    m["notas"] = ("Estudio OPT: optimización especializada, reversible y medible. Mapas explícitos y contabilizados en la instrucción; "
                  "equivalencia exacta verificada antes de contar. Criterio fijado antes de medir en los commits c196ec9 y 42b3c91.")
    m["duracion_s"] = round(time.time() - t0, 1)
    destino = ev.guardar_corrida(m, archivos=archivos, directorio=salida)
    print(f"manifiesto: {destino}  ({m['duracion_s']} s)  resultado={m['resultado']}", flush=True)
    return destino


def resumen_cifras(comp, equil, crit) -> Dict[str, Any]:
    """Cifras clave derivadas de los resultados (se regeneran con el comando; nunca se editan a mano)."""
    out: Dict[str, Any] = {"lectura_primaria": "salida y total frente a JSON compacto con instrucción 0; n=100; media de lotes", "dominios": {}}
    for d in DOMINIOS:
        out["dominios"][d] = {"etiqueta": dominios()[d].etiqueta, "tokenizadores": {}}
        for tk in tokenizadores.NOMBRES:
            def fila(perfil, instr, n=100):
                return next((c for c in comp if c["dominio"] == d and c["tokenizador"] == tk and c["n"] == n
                             and c["perfil"] == perfil and c["instruccion"] == instr), None)
            e = fila(*ESPECIALIZADO)
            g = fila(*medir.PRIMARIO_GENERAL)
            if e is None or g is None:
                continue
            ne = next((x for x in equil if x["dominio"] == d and x["tokenizador"] == tk and (x["perfil"], x["instruccion"], x["comparador"]) == (*ESPECIALIZADO, "total")), None)
            ng = next((x for x in equil if x["dominio"] == d and x["tokenizador"] == tk and (x["perfil"], x["instruccion"], x["comparador"]) == (*medir.PRIMARIO_GENERAL, "total")), None)
            out["dominios"][d]["tokenizadores"][tk] = {
                "n": 100,
                "ahorro_salida_especializado_pct": round(e["ahorro_salida_pct"], 2),
                "ahorro_salida_general_pct": round(g["ahorro_salida_pct"], 2),
                "ahorro_total_especializado_pct": round(e["ahorro_total_pct"], 2),
                "ahorro_total_general_pct": round(g["ahorro_total_pct"], 2),
                "instruccion_especializado_tokens": e["mini_instruccion"], "instruccion_general_tokens": g["mini_instruccion"],
                "n_estrella_total_especializado": ne["n_estrella"] if ne else None,
                "n_estrella_total_general": ng["n_estrella"] if ng else None,
            }
    out["resultado_del_criterio"] = crit["resultado"]
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--run-id", help="identificador de la corrida (por omisión opt-<fecha UTC>)")
    ap.add_argument("--salida", help="directorio de salida (por omisión evidencia/corridas/<run_id>)")
    ap.add_argument("--rapido", action="store_true", help="prueba de humo: lotes 1, 10 y 50 y curva hasta n=60; no es evidencia oficial")
    ap.add_argument("--sin-ejemplos", action="store_true", help="no regenerar examples/optimizacion/")
    a = ap.parse_args(argv)
    oficial = not a.rapido
    tamanos = medir.TAMANOS if oficial else (1, 10, 50)
    nmax = medir.NMAX_EQUILIBRIO if oficial else 60
    run_id = a.run_id or ev.nuevo_run_id("opt")
    salida = Path(a.salida) if a.salida else ev.directorio_corridas() / run_id
    if not oficial and not a.salida:
        sys.exit("--rapido exige --salida (no se escribe evidencia oficial con una prueba de humo)")
    correr(salida, run_id, tamanos, nmax, not a.sin_ejemplos and oficial, oficial)
    return 0


if __name__ == "__main__":
    sys.exit(main())
