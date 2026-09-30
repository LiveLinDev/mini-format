"""Ejecuta V3a (truncamiento y recuperación) y registra la corrida con el contrato mini-format/corrida/1.

    python tools/ejecutar_v3a.py                 # corrida completa: 18 documentos × 20 cortes × 6 lectores
    python tools/ejecutar_v3a.py --rapido        # humo: 3 documentos × 5 cortes; NO escribe evidencia

Todo es local (procedencia ``reproducido_local``, gasto 0 USD): sin red, sin claves, sin modelos. El diseño y
el criterio están fijados en ``experiments/truncamiento/PROTOCOLO.md``; este script no los cambia.

La corrida completa escribe ``evidencia/corridas/<run_id>/`` con ``manifiesto.json``, ``cortes.csv``,
``resumen_lectores.csv``, ``curvas.csv``, ``por_documento.csv``, ``resultados.json``, ``documentos.json``,
``documentos/<id>.json`` (la referencia exacta de cada documento), ``contratos/<id>.contract.json`` (los
contratos ``mini-domain/1`` inferidos) y ``figura_v3a.png``.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Dict, List

RAIZ = Path(__file__).resolve().parent.parent
for p in (RAIZ / "tools", RAIZ / "experiments", RAIZ / "src", RAIZ / "benchmark"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

import comun as C  # noqa: E402
import evidencia_lib as ev  # noqa: E402
from truncamiento import analisis as A  # noqa: E402
from truncamiento import corte as K  # noqa: E402
from truncamiento import documentos as D  # noqa: E402
from truncamiento import figura as F  # noqa: E402
from truncamiento import lectores as R  # noqa: E402
from truncamiento import nucleo as N  # noqa: E402

SEMILLA_DATOS = C.SEMILLA
PROTOCOLO = RAIZ / "experiments" / "truncamiento" / "PROTOCOLO.md"
RAPIDO_DOCS = (["cat", "a"], ["products"])       # (dominios, snapshots)
RAPIDO_KS = (2, 6, 10, 14, 18)

LIMITACIONES = [
    "Datos sintéticos (14 dominios) y de prueba públicos ficticios (products, users, comments); solo earthquakes (USGS) son observaciones reales.",
    "Los cortes son deterministas y los hace el tokenizador o200k_base (aproximación para Anthropic, Google o DeepSeek); no son los de ningún proveedor.",
    "Los resultados valen para estas implementaciones de lector (json.loads, jiter, JSON Lines estándar, minifmt, escáner propio), no para JSON o .mini en abstracto.",
    "Se mide minifmt en Python; el puerto TypeScript no se ejecuta.",
    "Un lector que acepta un registro final cortado pero válido (.mini tal cual, jiter) emite registros espurios: se miden, no se corrigen.",
    "Los 20 cortes son una malla uniforme, no una muestra de dónde cortan los modelos reales; no hay modelos en el bucle.",
    "La meta ≥ 90 % sobre registros disponibles es casi trivial para cualquier lector capaz; no separa formatos por recall (ver resumen).",
]


def _csv(ruta: Path, filas: List[Dict[str, Any]]) -> None:
    C.escribir_csv(ruta, filas)


def _aplanar(r: Dict[str, Any]) -> Dict[str, Any]:
    def g(k, sub):
        return (r.get(k) or {}).get(sub)
    return {
        "condicion": r["condicion"], "estrato": r["estrato"], "n_documentos": r["n_documentos"], "n_cortes": r["n_cortes"],
        "n_cortes_disponibles_cero": r["n_cortes_disponibles_cero"], "n_cortes_truncados": r["n_cortes_truncados"],
        "recall_disponibles": g("recall_disponibles", "punto"), "recall_ic95_inf": g("recall_disponibles", "ic95_inf"),
        "recall_ic95_sup": g("recall_disponibles", "ic95_sup"),
        "recall_solo_truncados": g("recall_disponibles_solo_truncados", "punto"),
        "recall_trunc_ic95_inf": g("recall_disponibles_solo_truncados", "ic95_inf"),
        "recall_trunc_ic95_sup": g("recall_disponibles_solo_truncados", "ic95_sup"),
        "minimo_por_documento": g("minimo_por_documento", "minimo"), "documento_minimo": g("minimo_por_documento", "documento"),
        "recuperados_sobre_solicitados": g("recuperados_sobre_solicitados", "media"),
        "rs_ic95_inf": g("recuperados_sobre_solicitados", "ic95_inf"), "rs_ic95_sup": g("recuperados_sobre_solicitados", "ic95_sup"),
        "disponibles_sobre_solicitados": g("disponibles_sobre_solicitados", "media"),
        "ds_ic95_inf": g("disponibles_sobre_solicitados", "ic95_inf"), "ds_ic95_sup": g("disponibles_sobre_solicitados", "ic95_sup"),
        "precision": g("precision", "punto"), "precision_ic95_inf": g("precision", "ic95_inf"),
        "precision_ic95_sup": g("precision", "ic95_sup"), "cortes_sin_emitidos_precision_null": g("precision", "n_cortes_sin_emitidos_null"),
        "registros_emitidos": r["registros_emitidos"], "registros_recuperados": r["registros_recuperados"],
        "registros_disponibles": r["registros_disponibles"], "espurios": r["espurios"], "duplicados": r["duplicados"],
        "completados_heuristicamente": r["completados_heuristicamente"], "cortes_con_espurios": r["cortes_con_espurios"],
        "fraccion_cortes_con_espurios": r["fraccion_cortes_con_espurios"], "fallos_lector": r["fallos_lector"],
    }


def _git(*args: str) -> str:
    r = subprocess.run(["git", *args], cwd=str(RAIZ), capture_output=True, text=True, encoding="utf-8")
    return r.stdout.strip() if r.returncode == 0 else ""


def _mostrar(resumen: List[Dict[str, Any]], crit: Dict[str, Any]) -> None:
    def pct(x):
        return "  n/d " if x is None else f"{x * 100:5.1f}%".replace(".", ",")
    print("\nResumen (todos los documentos)   recall/disp  solo truncados  rec/solicit  disp/solicit  precisión  cortes con espurio")
    for r in resumen:
        if r["estrato"] != "todos":
            continue
        print(f"  {r['condicion']:<26} {pct(r['recall_disponibles']['punto'])}     {pct(r['recall_disponibles_solo_truncados']['punto'])}        "
              f"{pct(r['recuperados_sobre_solicitados']['media'])}      {pct(r['disponibles_sobre_solicitados']['media'])}     "
              f"{pct(r['precision']['punto'])}     {pct(r['fraccion_cortes_con_espurios'])}")
    print(f"\nCriterio primario ({crit['condicion']}): {pct(crit['punto'])}  IC95 [{pct(crit['ic95_inf'])}, {pct(crit['ic95_sup'])}]  "
          f"umbral {crit['umbral'] * 100:.0f} %  ->  {crit['veredicto_regla_fijada']}  (aprobación del asesor: {crit['aprobacion_asesor']})")


def main(argv: List[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--rapido", action="store_true", help="humo: 3 documentos, 5 cortes, sin evidencia")
    ap.add_argument("--salida", help="directorio de salida en modo --rapido (por defecto output/v3a-rapido)")
    args = ap.parse_args(argv)

    t0 = time.time()
    comando = "python tools/ejecutar_v3a.py" + (" --rapido" if args.rapido else "")
    manifiesto = None
    if not args.rapido:
        manifiesto = ev.nueva_corrida("V3a", "reproducido_local", comando, run_id=ev.nuevo_run_id("V3a"))
        if manifiesto["codigo"]["arbol_limpio"] is not True:
            print("AVISO: el árbol de trabajo no está limpio; el manifiesto guardará snapshot_sha256.", flush=True)
        salida = ev.directorio_corridas() / manifiesto["run_id"]
        if salida.exists():
            raise SystemExit(f"{salida} ya existe")
    else:
        salida = Path(args.salida) if args.salida else RAIZ / "output" / "v3a-rapido"

    dominios, snaps = (D.DOMINIOS, D.SNAPSHOTS) if not args.rapido else RAPIDO_DOCS
    ks = N.KS if not args.rapido else RAPIDO_KS
    print(f"Construyendo {len(dominios) + len(snaps)} documentos de referencia…", flush=True)
    docs = D.construir_todos(dominios, snaps)
    enc = K.cargar_o200k()
    filas: List[Dict[str, Any]] = []
    infos: List[Dict[str, Any]] = []
    exclusiones: List[Dict[str, str]] = []
    for d in docs:
        f, info, ex = N.evaluar_documento(d, enc, ks)
        filas += f
        infos.append(info)
        exclusiones += ex
        print(f"  {d.id:<11} T_ref={info['tokens_ref_json']:>6}  tokens json/jsonl/mini = "
              f"{info['tokens_por_formato']['json']}/{info['tokens_por_formato']['jsonl']}/{info['tokens_por_formato']['mini']}", flush=True)
    for ex in exclusiones:
        print("  EXCLUIDO:", ex, flush=True)

    resumen = A.resumen_lectores(filas)
    curv = A.curvas(filas)
    pdoc = A.por_documento(filas)
    crit = A.criterio_primario(filas)
    _mostrar(resumen, crit)

    if args.rapido:
        salida.mkdir(parents=True, exist_ok=True)
        _csv(salida / "cortes.csv", filas)
        F.dibujar(curv, resumen, salida / "figura_v3a.png", len(docs))
        print(f"\nModo rápido ({time.time() - t0:.1f} s): salida en {salida} (no se registró evidencia).")
        return 0

    # ------------------------------------------------------------ escritura de resultados
    salida.mkdir(parents=True, exist_ok=True)
    (salida / "documentos").mkdir()
    (salida / "contratos").mkdir()
    _csv(salida / "cortes.csv", filas)
    _csv(salida / "resumen_lectores.csv", [_aplanar(r) for r in resumen])
    _csv(salida / "curvas.csv", curv)
    _csv(salida / "por_documento.csv", pdoc)
    indice = []
    conjuntos: List[Dict[str, Any]] = []
    contratos: List[Dict[str, Any]] = []
    for d, info in zip(docs, infos):
        ruta_doc = salida / "documentos" / f"{d.id}.json"
        ruta_doc.write_bytes(d.textos["json"].texto.encode("utf-8"))   # la referencia exacta: JSON compacto de los 50 registros
        rel = ev.ruta_relativa(ruta_doc)
        sha = ev.sha256_archivo(ruta_doc)
        indice.append({
            "documento": d.id, "tipo": d.tipo, "sintetico": d.sintetico, "registros_solicitados": d.n, "clave_registros": d.clave,
            "archivo_referencia": rel, "sha256_referencia": sha,
            "tokens_ref_json_o200k": info["tokens_ref_json"], "tokens_por_formato": info["tokens_por_formato"],
            "bytes_por_formato": info["bytes_por_formato"],
            "sha256_texto_por_formato": {f: ev.sha256_texto(t.texto) for f, t in d.textos.items()},
            "exclusiones": d.exclusiones, "meta": d.meta,
        })
        if d.perfil_mini == "academico":
            contratos.append({"prefijo": d.id, "ruta": d.meta["contrato_ruta"], "sha256": d.meta["contrato_sha256"],
                              "version": d.meta.get("contrato_version")})
            conjuntos.append({"nombre": f"dominio:{d.id}", "ruta": rel, "sha256": sha, "sintetico": True, "licencia": None,
                              "fuente": d.meta["generador"], "registros": d.n, "semilla": d.meta["semilla"]})
        else:
            rc = salida / "contratos" / f"{d.id}.contract.json"
            ev.escribir_json(rc, d.contrato)
            contratos.append({"prefijo": d.id, "ruta": ev.ruta_relativa(rc), "sha256": ev.sha256_archivo(rc), "version": 1})
            conjuntos.append({"nombre": f"snapshot:{d.id}", "ruta": "benchmark/public/" + d.meta["archivo"],
                              "sha256": d.meta["archivo_sha256"], "sintetico": d.sintetico,
                              "licencia": "ver benchmark/public/THIRD_PARTY.md", "fuente": d.meta["fuente_url"],
                              "registros": d.meta["archivo_registros"], "semilla": None})
            conjuntos.append({"nombre": f"snapshot:{d.id} (primeros {d.n} registros: referencia de la corrida)", "ruta": rel, "sha256": sha,
                              "sintetico": d.sintetico, "licencia": "ver benchmark/public/THIRD_PARTY.md", "fuente": d.meta["fuente_url"],
                              "registros": d.n, "semilla": None})
    ev.escribir_json(salida / "documentos.json", {"esquema": "mini-format/v3a-documentos/1", "documentos": indice})
    resultados = {
        "esquema": "mini-format/v3a-resultados/1",
        "protocolo": {"ruta": ev.ruta_relativa(PROTOCOLO), "sha256": ev.sha256_archivo(PROTOCOLO)},
        "condiciones": [c._asdict() for c in N.CONDICIONES],
        "cortes_por_documento": list(ks),
        "criterio_primario": crit,
        "resumen_lectores": resumen,
        "exclusiones": exclusiones,
    }
    ev.escribir_json(salida / "resultados.json", resultados)
    F.dibujar(curv, resumen, salida / "figura_v3a.png", len(docs))

    # ------------------------------------------------------------ manifiesto
    commit_protocolo = _git("log", "-1", "--format=%H", "--", ev.ruta_relativa(PROTOCOLO))
    protocolo_limpio = _git("status", "--porcelain", "--", ev.ruta_relativa(PROTOCOLO)) == ""
    tk = {"nombre": "o200k_base", "paquete": "tiktoken", "version": ev._version_paquete("tiktoken"),
          "vocabulario_sha256": K.O200K_SHA256, "tipo": "aproximacion"}
    manifiesto.update({
        "conjuntos": conjuntos,
        "contratos": contratos,
        "tokenizadores": [tk],
        "parametros": {
            "registros_por_documento": D.N_REGISTROS, "cortes_por_documento": list(ks),
            "limite_k": "round(k/20 * T_ref), T_ref = tokens o200k del JSON compacto; mitad hacia arriba con enteros",
            "semilla_datos_dominios": SEMILLA_DATOS,
            "bootstrap": {"tipo": "conglomerados por documento", "B": A.B_REPLICAS, "semilla": A.SEMILLA_BOOTSTRAP, "ic": 0.95},
            "lectores": {"json_estricto": f"json.loads (Python {sys.version.split()[0]})",
                         "json_parcial_jiter": f"jiter {R.version_jiter()}, partial_mode='on'",
                         "jsonl": "JSON Lines estándar (json.loads por línea)",
                         "mini_tolerante": "minifmt Reader(strict=False) / aislamiento por línea de minifmt.domain.diagnose",
                         "json_objetos_completos": "implementación propia (experiments/truncamiento/lectores.py)"},
            "condiciones": [c.nombre for c in N.CONDICIONES],
        },
        "conteos": None,
        "resumen": {
            "documentos": len(docs), "cortes_evaluados": len(filas), "condiciones": len(N.CONDICIONES),
            "criterio_primario": {k: crit[k] for k in ("condicion", "punto", "ic95_inf", "ic95_sup", "veredicto_regla_fijada")},
            "por_condicion_todos": {r["condicion"]: {"recall_disponibles": r["recall_disponibles"]["punto"],
                                                     "recall_solo_truncados": r["recall_disponibles_solo_truncados"]["punto"],
                                                     "recuperados_sobre_solicitados": r["recuperados_sobre_solicitados"]["media"],
                                                     "precision": r["precision"]["punto"],
                                                     "espurios": r["espurios"]}
                                    for r in resumen if r["estrato"] == "todos"},
            "exclusiones": len(exclusiones),
            "duracion_s": round(time.time() - t0, 1),
        },
        "criterio": {
            "meta": "recuperar >= 90 % de los registros completos disponibles",
            "estadistico": crit["estadistico"], "condicion_primaria": crit["condicion"], "umbral": A.UMBRAL,
            "regla_de_decision": "cumple si el punto >= 0,90; no_cumple si no (el IC se informa, no decide)",
            "fijado_antes_del_analisis": True,
            "protocolo": {"ruta": ev.ruta_relativa(PROTOCOLO), "sha256": ev.sha256_archivo(PROTOCOLO),
                          "ultimo_commit": commit_protocolo or None, "sin_cambios_locales": protocolo_limpio},
            "aprobacion_asesor": "pendiente",
            "no_afirma": "nada universal sobre JSON ni .mini; el caso historico 38/40 de CIMA no se sustituye",
        },
        "estado_ejecucion": "ejecutado",
        "resultado": crit["veredicto_regla_fijada"],
        "limitaciones": LIMITACIONES,
        "gasto_usd": 0,
        "notas": ("Corrida local sin modelos ni claves. La interpretación del criterio está sujeta a aprobación del asesor; el veredicto "
                  "aplica la regla fijada en PROTOCOLO.md y no la sustituye. El recall sobre disponibles es casi trivial para los lectores "
                  "capaces: léase junto con recuperados/solicitados, precisión y el análisis solo-truncados."),
    })
    archivos = [salida / n for n in ("cortes.csv", "resumen_lectores.csv", "curvas.csv", "por_documento.csv",
                                     "resultados.json", "documentos.json", "figura_v3a.png")]
    destino = ev.guardar_corrida(manifiesto, archivos=archivos, directorio=salida)
    print(f"\nCorrida registrada: {destino}  ({time.time() - t0:.1f} s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
