"""Runner del experimento generativo V2 / V3b / V4.

Subcomandos (sin subcomando se entiende ``ejecutar``, como en versiones anteriores)::

    # 1. LOCAL, sin API, sin gasto: adaptador simulado (valida el arnés; nunca son resultados del estudio)
    python experiments/generativo/run.py ejecutar --config configs/piloto.yaml --adapter simulado

    # 2. CON API: exige config explícita con presupuesto AUTORIZADO, tope, tarifas verificadas y claves; si falta algo
    #    se rechaza con un error claro y SIN ninguna llamada
    python experiments/generativo/run.py ejecutar --config configs/piloto.yaml --adapter real \\
           --confirmar-real --max-costo-usd 5 --tarifas evidencia/tarifas/tarifas.json

    # recuento de llamadas y costo SIN ejecutar nada
    python experiments/generativo/run.py dry-run --config configs/estudio.yaml

    # material asistido por IA (respuestas ya generadas): prompts -> respuestas -> importar
    python experiments/generativo/run.py preparar --tareas ext-cls --brazos A,B,D --repeticiones 3 \\
           --modelo-declarado MODELO --salida prompts.jsonl
    python experiments/generativo/run.py importar respuestas.jsonl --salida resultados/asistido_ia/piloto

Códigos de salida: 0 correcto; 2 rechazado antes de empezar (configuración, autorización, presupuesto, claves,
diseño distinto al del manifiesto o directorio en uso); 3 abortado durante la ejecución (presupuesto o fallos
seguidos); 4 interrumpido (SIGINT/SIGTERM) con el estado guardado.
"""
from __future__ import annotations

import argparse
import datetime as _dt
import json
import logging
import platform
import sys
from decimal import Decimal
from pathlib import Path
from typing import Any, Dict, List, Optional

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parents[1] / "tools"))         # evidencia_lib

import arnes  # noqa: E402,F401  (añade src/ al path)
from arnes import brazos as B  # noqa: E402
from arnes import ejecucion as X  # noqa: E402
from arnes import importacion as IM  # noqa: E402
from arnes import plan as PL  # noqa: E402
from arnes.costos import estimar  # noqa: E402
from arnes.presupuesto import ErrorAutorizacion, Presupuesto, validar_autorizacion  # noqa: E402
from arnes.tarifas import Tarifas  # noqa: E402
from minifmt.ai.adapters import redact  # noqa: E402

SUBCOMANDOS = ("ejecutar", "dry-run", "importar", "preparar", "preparar-reparacion", "evidencia")
RAIZ = HERE.parents[1]


class _FormatoRedactado(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        return redact(super().format(record))


def _config_logging(salida: Path, verboso: bool) -> None:
    root = logging.getLogger()
    root.setLevel(logging.DEBUG if verboso else logging.INFO)
    for h in list(root.handlers):
        root.removeHandler(h)
    fmt = _FormatoRedactado("%(asctime)s %(levelname)s %(name)s: %(message)s")
    sh = logging.StreamHandler()
    sh.setFormatter(fmt)
    root.addHandler(sh)
    salida.mkdir(parents=True, exist_ok=True)
    fh = logging.FileHandler(salida / "ejecucion.log", encoding="utf-8")
    fh.setFormatter(fmt)
    root.addHandler(fh)
    for ruidoso in ("httpx", "openai", "httpcore"):
        logging.getLogger(ruidoso).setLevel(logging.WARNING)


def _cerrar_logging() -> None:
    for h in list(logging.getLogger().handlers):
        logging.getLogger().removeHandler(h)
        h.close()


def _resolver(path: str) -> Path:
    p = Path(path)
    if p.exists():
        return p
    if (HERE / p).exists():
        return HERE / p
    raise SystemExit(f"no existe la configuración: {path}")


def _ahora() -> str:
    return _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds")


def _usd(v: Optional[Decimal]) -> Optional[str]:
    return None if v is None else format(v, "f")


# --------------------------------------------------------------------------
# Argumentos
# --------------------------------------------------------------------------
def _ap_ejecutar(ap: argparse.ArgumentParser) -> None:
    ap.add_argument("--config", required=True)
    ap.add_argument("--adapter", choices=["simulado", "real"], required=True,
                    help="simulado: sin red, respuestas deterministas con fallas inyectadas; real: APIs (exige autorización)")
    ap.add_argument("--dry-run", action="store_true", help="solo cuenta llamadas y estima costo; no ejecuta ni escribe nada")
    ap.add_argument("--max-costo-usd", type=float, default=None,
                    help="tope de gasto. OBLIGATORIO con --adapter real (y no puede superar presupuesto.autorizado_usd); "
                         "se comprueba por proyección ANTES de cada llamada")
    ap.add_argument("--confirmar-real", action="store_true", help="obligatorio para ejecutar con --adapter real")
    ap.add_argument("--salida", default=None, help="directorio de resultados (por defecto resultados/<adaptador>/<nombre>)")
    ap.add_argument("--tarifas", default=None, help="archivo de tarifas (por defecto evidencia/tarifas/tarifas.json)")
    ap.add_argument("--limite", type=int, default=None, help="ejecuta como mucho N celdas pendientes")
    ap.add_argument("--verboso", action="store_true")
    ap.add_argument("--nueva-version", default=None, metavar="MOTIVO",
                    help="permite reanudar con un diseño distinto al del manifiesto; el motivo queda en versiones.jsonl")
    ap.add_argument("--forzar-candado", action="store_true", help="ignora un ejecucion.lock huérfano")
    ap.add_argument("--emitir-evidencia", nargs="?", const="", default=None, metavar="ETIQUETA",
                    help="al terminar, analiza y emite las corridas V2/V3b/V4 en evidencia/corridas/ (etiqueta por defecto "
                         "<adaptador>-<nombre>)")


def _ap_dry(ap: argparse.ArgumentParser) -> None:
    ap.add_argument("--config", required=True)
    ap.add_argument("--adapter", choices=["simulado", "real"], default="real")
    ap.add_argument("--tarifas", default=None)
    ap.add_argument("--json", default=None, help="escribe el recuento y la estimación en este archivo JSON")


# --------------------------------------------------------------------------
# dry-run
# --------------------------------------------------------------------------
def _texto_recuento(cfg, en, est, adaptador, tarifas) -> List[str]:
    L = [f"Configuración: {cfg['nombre']} | adaptador: {adaptador} | tareas: {len(cfg['tareas'])} | modelos: {len(cfg['modelos'])} | "
         f"celdas ejecutables: {len(en.unidades)} | no aplicables: {len(en.no_aplicables)}"]
    L.append("")
    L.append("Recuento de llamadas (no se ejecuta nada):")
    for linea in est.recuento["explicacion"]:
        L.append("  " + linea)
    t = est.recuento["totales"]
    L.append(f"  TOTAL: {t['primarias_a_ejecutar']} llamadas primarias (nominal {t['primarias_nominales']}, "
             f"{t['no_aplicables']} celdas no aplicables) + hasta {t['reparaciones_maximas']} llamadas de reparación "
             f"= máximo {t['llamadas_maximas']}")
    L.append("")
    L.append("Estimación previa (entrada = conteo local o200k_base × factor supuesto por proveedor: una APROXIMACIÓN; "
             "costo solo con tarifas verificadas):")
    L.append(est.tabla())
    sin = [f"{f.proveedor}:{f.modelo}" for f in est.filas if f.costo_esperado is None]
    parcial = sum((f.costo_esperado for f in est.filas if f.costo_esperado is not None), Decimal(0))
    parcial_max = sum((f.costo_maximo for f in est.filas if f.costo_maximo is not None), Decimal(0))
    if sin:
        L.append(f"Costo parcial con tarifas verificadas: esperado {parcial:,.2f} USD, máximo {parcial_max:,.2f} USD; "
                 f"«tarifa no verificada» para: {', '.join(sin)}")
    if tarifas.origen is None:
        L.append("No hay archivo de tarifas (evidencia/tarifas/tarifas.json): todo costo es «tarifa no verificada».")
    if adaptador == "simulado":
        L.append("Nota: con --adapter simulado no se llama a ninguna API y el gasto es 0.")
    return L


def cmd_dry_run(args: argparse.Namespace) -> int:
    try:
        cfg = X.cargar_config(_resolver(args.config))
        ctx = X.Contexto(cfg)
        en = X.enumerar_completo(cfg, ctx)
    except (X.ErrorConfig, FileNotFoundError) as e:
        print(f"configuración inválida: {e}", file=sys.stderr)
        return 2
    tarifas = Tarifas.cargar(Path(args.tarifas) if args.tarifas else None)
    est = estimar(en, ctx, tarifas, cfg)
    for linea in _texto_recuento(cfg, en, est, args.adapter, tarifas):
        print(linea)
    if args.json:
        Path(args.json).write_text(json.dumps({
            "config": cfg["nombre"], "recuento": est.recuento, "tarifas": {"archivo": tarifas.origen, "sha256": tarifas.sha256},
            "costo_esperado_usd": _usd(est.costo_esperado), "costo_maximo_usd": _usd(est.costo_maximo),
            "por_modelo": [{"proveedor": f.proveedor, "modelo": f.modelo, "llamadas_generacion": f.llamadas_generacion,
                            "costo_esperado_usd": _usd(f.costo_esperado), "costo_maximo_usd": _usd(f.costo_maximo),
                            "tarifa": f.tarifa_estado} for f in est.filas]}, ensure_ascii=False, indent=2), encoding="utf-8")
    return 0


# --------------------------------------------------------------------------
# ejecutar
# --------------------------------------------------------------------------
def ejecutar(args: argparse.Namespace, argv_original: List[str]) -> int:
    import evidencia_lib as EV
    codigo0 = EV.info_codigo()              # el código que ejecuta, ANTES de escribir ningún resultado
    try:
        cfg = X.cargar_config(_resolver(args.config))
        ctx = X.Contexto(cfg)
        en = X.enumerar_completo(cfg, ctx)
    except (X.ErrorConfig, FileNotFoundError) as e:
        print(f"configuración inválida: {e}", file=sys.stderr)
        return 2
    salida = Path(args.salida) if args.salida else HERE / "resultados" / args.adapter / cfg["nombre"]
    tarifas = Tarifas.cargar(Path(args.tarifas) if args.tarifas else None)
    est = estimar(en, ctx, tarifas, cfg)
    for linea in _texto_recuento(cfg, en, est, args.adapter, tarifas):
        print(linea)
    if args.dry_run:
        return 0

    presupuesto = Presupuesto.desde_config(cfg)
    autorizacion = None
    if args.adapter == "real":
        if not args.confirmar_real:
            print("abortado: la ejecución real requiere --confirmar-real (use dry-run para estimar)", file=sys.stderr)
            return 2
        try:
            autorizacion = validar_autorizacion(presupuesto, args.max_costo_usd, tarifas, cfg["modelos"],
                                                costo_esperado=est.costo_esperado, costo_maximo=est.costo_maximo,
                                                claves_faltantes=X.verificar_claves(cfg))
        except ErrorAutorizacion as e:
            print("abortado: ejecución real NO autorizada, no se hizo ninguna llamada:", file=sys.stderr)
            for m in e.errores:
                print(f"  - {m}", file=sys.stderr)
            return 2
    elif args.max_costo_usd is not None:
        if est.costo_esperado is None:
            print("abortado: con --max-costo-usd hacen falta tarifas verificadas de todos los modelos (use --tarifas)", file=sys.stderr)
            return 2
        if est.costo_esperado > Decimal(str(args.max_costo_usd)):
            print(f"abortado: costo esperado {est.costo_esperado:.2f} USD supera --max-costo-usd {args.max_costo_usd}", file=sys.stderr)
            return 2

    hashes = PL.hashes_diseno(cfg, ctx, en.unidades, en.no_aplicables, tarifas, RAIZ)
    try:
        hash_previo = PL.verificar_reanudacion(salida, args.adapter, hashes, args.nueva_version)
    except PL.ErrorReanudacion as e:
        print(f"abortado: {e}", file=sys.stderr)
        return 2
    try:
        candado = PL.Candado(salida, forzar=args.forzar_candado)
        candado.__enter__()
    except PL.ErrorCandado as e:
        print(f"abortado: {e}", file=sys.stderr)
        return 2
    res: Dict[str, Any] = {}
    try:
        _config_logging(salida, args.verboso)
        manifiesto = {"nombre": cfg["nombre"], "adaptador": args.adapter, "simulado": args.adapter == "simulado",
                      "procedencia": "simulado" if args.adapter == "simulado" else "api_real",
                      "advertencia": ("RESULTADOS SIMULADOS: solo validan el arnés; no son resultados del estudio"
                                      if args.adapter == "simulado" else ""),
                      "config": cfg, "hashes": hashes, "commit": codigo0.get("commit"), "codigo": codigo0,
                      "python": platform.python_version(), "unidades": len(en.unidades),
                      "no_aplicables": len(en.no_aplicables),
                      "omitidas": X.enumerar(cfg, ctx)[1],
                      "orden": {"aleatorizado": en.aleatorizado, "semilla": en.orden_semilla},
                      "presupuesto": presupuesto.como_dict(), "max_costo_usd": args.max_costo_usd,
                      "nueva_version": args.nueva_version,
                      "condiciones_ejecucion": {"concurrencia": 1, "reintentos_por_llamada": int((cfg.get("controles") or {}).get("reintentos_por_llamada", 2)),
                                                "red": "simulada" if args.adapter == "simulado" else "no medida",
                                                "latencia_api": "simulada" if args.adapter == "simulado" else "medida por el cliente (incluye red y colas)"},
                      "estimacion": {"recuento": est.recuento, "costo_esperado_usd": _usd(est.costo_esperado),
                                     "costo_maximo_usd": _usd(est.costo_maximo)}}
        PL.escribir_manifiesto(salida, manifiesto, hash_previo, args.nueva_version, _ahora())
        if not (salida / "plan.jsonl").exists() or hash_previo is not None:
            with open(salida / "plan.jsonl", "w", encoding="utf-8", newline="\n") as fh:
                for i, u in enumerate(en.unidades):
                    fh.write(json.dumps({"orden": i, "id": u.id, "estado": "pendiente", "experimento": u.experimento, "tarea": u.tarea,
                                         "brazo": u.brazo, "proveedor": u.proveedor, "modelo": u.modelo, "repeticion": u.rep,
                                         "max_tokens": u.max_tokens}, ensure_ascii=False) + "\n")
                for x in en.no_aplicables:
                    fh.write(json.dumps({"orden": None, "id": x["id"], "estado": "no_aplicable", "motivo": x["motivo"],
                                         "experimento": x["experimento"], "tarea": x["tarea"], "brazo": x["brazo"],
                                         "proveedor": x["proveedor"], "modelo": x["modelo"], "repeticion": x["repeticion"]},
                                        ensure_ascii=False) + "\n")
        ej = X.Ejecutor(cfg, ctx, args.adapter, salida, tarifas, max_costo=args.max_costo_usd, autorizacion=autorizacion)
        if ej.almacen.lineas_corruptas:
            logging.warning("%d líneas ilegibles en muestras.jsonl; esas muestras se repetirán", ej.almacen.lineas_corruptas)
        if ej.libro.huerfanas:
            logging.warning("%d llamadas del libro quedaron sin terminar (proceso interrumpido): se cuentan al peor caso como gasto incierto",
                            ej.libro.huerfanas)
        res = ej.ejecutar_estudio(en, limite=args.limite)
        logging.info("resultado: %s", res)
    finally:
        _cerrar_logging()
        candado.__exit__(None, None, None)
    print(json.dumps(res, ensure_ascii=False, default=str))
    if res.get("interrumpido"):
        return 4
    if res.get("abortado"):
        return 3
    if args.emitir_evidencia is not None:
        return _analizar_y_emitir(salida, args.emitir_evidencia or f"{args.adapter}-{cfg['nombre']}",
                                  "simulado" if args.adapter == "simulado" else "api_real", argv_original, codigo0, args.tarifas)
    return 0


def _analizar_y_emitir(salida: Path, etiqueta: str, procedencia: str, argv_original: List[str], codigo: Optional[Dict[str, Any]],
                       tarifas_arg: Optional[str]) -> int:
    import analyze
    from arnes import evidencia as EVI
    argv_an = ["--resultados", str(salida)] + (["--tarifas", tarifas_arg] if tarifas_arg else [])
    if analyze.main(argv_an) != 0:
        return 2
    tarifas = Tarifas.cargar(Path(tarifas_arg) if tarifas_arg else None)
    info = ({"archivo": tarifas.origen, "sha256": tarifas.sha256, "consultado_utc": tarifas.consultado_utc}
            if tarifas.origen else None)
    comando = "python experiments/generativo/run.py " + " ".join(a for a in argv_original)
    rutas = EVI.emitir_corridas(salida, procedencia=procedencia, comando=comando, etiqueta=etiqueta, codigo=codigo,
                                tarifas_info=info)
    for r in rutas:
        print("corrida emitida:", r)
    return 0


# --------------------------------------------------------------------------
# preparar / importar / evidencia
# --------------------------------------------------------------------------
def cmd_preparar(argv: List[str]) -> int:
    ap = argparse.ArgumentParser(prog="run.py preparar", description="Prompts exactos para quien genera respuestas asistidas por IA")
    ap.add_argument("--config", default=None, help="toma tareas, brazos y repeticiones de esta configuración")
    ap.add_argument("--tareas", default=None, help="ids separados por comas (p. ej. ext-cls,gen-card)")
    ap.add_argument("--brazos", default="A,B,D", help="brazos primarios (el C no aplica a material asistido por IA)")
    ap.add_argument("--repeticiones", type=int, default=1)
    ap.add_argument("--modelo-declarado", required=True, help="nombre del modelo/IA que generará las respuestas")
    ap.add_argument("--experimento", default="v2")
    ap.add_argument("--salida", required=True)
    a = ap.parse_args(argv)
    if a.config:
        cfg = X.cargar_config(_resolver(a.config))
        tareas, brazos, reps = list(cfg["tareas"]), [b for b in cfg["brazos"] if not B.es_reparacion(b)], int(cfg["repeticiones"])
    else:
        if not a.tareas:
            print("indique --tareas o --config", file=sys.stderr)
            return 2
        tareas, brazos, reps = a.tareas.split(","), a.brazos.split(","), a.repeticiones
    filas, omitidas = IM.preparar_prompts(tareas, brazos, reps, a.modelo_declarado, a.experimento)
    Path(a.salida).write_text("".join(json.dumps(f, ensure_ascii=False) + "\n" for f in filas), encoding="utf-8", newline="\n")
    print(f"{len(filas)} celdas preparadas en {a.salida}; {len(omitidas)} no aplicables")
    for o in omitidas[:5]:
        print("  no aplicable:", o["celda_id"], "-", o["motivo"])
    return 0


def cmd_preparar_reparacion(argv: List[str]) -> int:
    ap = argparse.ArgumentParser(prog="run.py preparar-reparacion", description="Solicitudes de reparación para respuestas ya importables")
    ap.add_argument("respuestas")
    ap.add_argument("--salida", required=True)
    ap.add_argument("--idioma", default="es")
    a = ap.parse_args(argv)
    filas = IM.leer_filas(Path(a.respuestas))
    out = IM.preparar_reparaciones(filas, a.idioma)
    Path(a.salida).write_text("".join(json.dumps(f, ensure_ascii=False) + "\n" for f in out), encoding="utf-8", newline="\n")
    print(f"{len(out)} solicitudes de reparación en {a.salida}")
    return 0


def cmd_importar(argv: List[str], argv_original: List[str]) -> int:
    ap = argparse.ArgumentParser(prog="run.py importar", description="Importa respuestas ya generadas (procedencia asistido_ia; sin gasto)")
    ap.add_argument("ruta", help="JSONL o directorio con *.jsonl")
    ap.add_argument("--salida", default=None)
    ap.add_argument("--idioma", default="es")
    ap.add_argument("--permitir-sin-prompt-id", action="store_true")
    ap.add_argument("--sin-reparacion", action="store_true", help="no crea las muestras X+1")
    ap.add_argument("--analizar", action="store_true")
    ap.add_argument("--emitir-evidencia", nargs="?", const="", default=None, metavar="ETIQUETA")
    a = ap.parse_args(argv)
    import evidencia_lib as EV
    codigo0 = EV.info_codigo()
    ruta = Path(a.ruta)
    if not ruta.exists():
        print(f"no existe {ruta}", file=sys.stderr)
        return 2
    salida = Path(a.salida) if a.salida else HERE / "resultados" / "asistido_ia" / ruta.stem
    inf = IM.importar(ruta, salida, idioma=a.idioma, permitir_sin_prompt_id=a.permitir_sin_prompt_id, reparacion=not a.sin_reparacion)
    IM.escribir_resultados_importacion(salida, ruta, inf, idioma=a.idioma, raiz=RAIZ)
    print(f"importadas {inf.aceptadas} muestras en {salida}; rechazadas {len(inf.rechazadas)}; no aplicables {len(inf.no_aplicables)}; "
          f"reparaciones pendientes {len(inf.reparaciones_pendientes)} (detalle en importacion.json)")
    if a.analizar or a.emitir_evidencia is not None:
        import analyze
        if analyze.main(["--resultados", str(salida)]) != 0:
            return 2
    if a.emitir_evidencia is not None:
        return _analizar_y_emitir(salida, a.emitir_evidencia or f"asistido-{ruta.stem}".lower(), "asistido_ia",
                                  ["importar"] + argv_original, codigo0, None)
    return 0


def cmd_evidencia(argv: List[str]) -> int:
    ap = argparse.ArgumentParser(prog="run.py evidencia", description="Emite las corridas V2/V3b/V4 de un directorio de resultados")
    ap.add_argument("--resultados", required=True)
    ap.add_argument("--etiqueta", required=True)
    ap.add_argument("--procedencia", default=None, choices=["simulado", "asistido_ia", "api_real"])
    ap.add_argument("--tarifas", default=None)
    a = ap.parse_args(argv)
    res = Path(a.resultados)
    man = json.loads((res / "manifiesto.json").read_text(encoding="utf-8"))
    proc = a.procedencia or man.get("procedencia") or ("simulado" if man.get("simulado") else "api_real")
    import analyze
    if analyze.main(["--resultados", str(res)] + (["--tarifas", a.tarifas] if a.tarifas else [])) != 0:
        return 2
    return _analizar_y_emitir(res, a.etiqueta, proc, ["evidencia"] + sys.argv[2:], None, a.tarifas)


# --------------------------------------------------------------------------
def main(argv: Optional[List[str]] = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    sub = "ejecutar"
    if argv and argv[0] in SUBCOMANDOS:
        sub = argv.pop(0)
    original = list(argv)
    if sub == "preparar":
        return cmd_preparar(argv)
    if sub == "preparar-reparacion":
        return cmd_preparar_reparacion(argv)
    if sub == "importar":
        return cmd_importar(argv, original)
    if sub == "evidencia":
        return cmd_evidencia(argv)
    ap = argparse.ArgumentParser(prog=f"run.py {sub}", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    if sub == "dry-run":
        _ap_dry(ap)
        return cmd_dry_run(ap.parse_args(argv))
    _ap_ejecutar(ap)
    return ejecutar(ap.parse_args(argv), ["ejecutar"] + original)


if __name__ == "__main__":
    sys.exit(main())
