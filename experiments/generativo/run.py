"""Runner del experimento generativo V2/V3.

Ejemplos::

    python experiments/generativo/run.py --config configs/piloto.yaml --adapter simulado
    python experiments/generativo/run.py --config configs/estudio.yaml --adapter real --dry-run
    python experiments/generativo/run.py --config configs/estudio.yaml --adapter real --confirmar-real --max-costo-usd 40

Códigos de salida: 0 correcto, 2 abortado antes de empezar (configuración,
presupuesto o claves), 3 abortado durante la ejecución (presupuesto o fallos).
"""
from __future__ import annotations

import argparse
import json
import logging
import platform
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import arnes  # noqa: E402,F401  (añade src/ al path)
from arnes import ejecucion as X  # noqa: E402
from arnes.costos import Precios, estimar  # noqa: E402
from minifmt.ai.adapters import redact  # noqa: E402


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


def _resolver(path: str) -> Path:
    p = Path(path)
    if p.exists():
        return p
    if (HERE / p).exists():
        return HERE / p
    raise SystemExit(f"no existe la configuración: {path}")


def _git_commit() -> str:
    try:
        return subprocess.run(["git", "rev-parse", "HEAD"], cwd=HERE, capture_output=True, text=True,
                              timeout=10).stdout.strip()
    except Exception:  # noqa: BLE001
        return ""


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--config", required=True)
    ap.add_argument("--adapter", choices=["simulado", "real"], required=True,
                    help="simulado: sin red, respuestas deterministas con fallas inyectadas; real: APIs de los proveedores")
    ap.add_argument("--dry-run", action="store_true", help="solo estima llamadas y costo; no ejecuta")
    ap.add_argument("--max-costo-usd", type=float, default=None,
                    help="aborta antes de empezar si el costo esperado lo supera y durante la ejecución si el acumulado lo supera")
    ap.add_argument("--confirmar-real", action="store_true", help="obligatorio para ejecutar con --adapter real")
    ap.add_argument("--salida", default=None, help="directorio de resultados (por defecto resultados/<adaptador>/<nombre>)")
    ap.add_argument("--precios", default=None)
    ap.add_argument("--limite", type=int, default=None, help="ejecuta como mucho N muestras pendientes")
    ap.add_argument("--verboso", action="store_true")
    args = ap.parse_args(argv)

    try:
        cfg = X.cargar_config(_resolver(args.config))
    except X.ErrorConfig as e:
        print(f"configuración inválida: {e}", file=sys.stderr)
        return 2
    salida = Path(args.salida) if args.salida else HERE / "resultados" / args.adapter / cfg["nombre"]
    precios = Precios.cargar(Path(args.precios) if args.precios else None)
    ctx = X.Contexto(cfg)
    try:
        unidades, omitidas = X.enumerar(cfg, ctx)
    except X.ErrorConfig as e:
        print(f"configuración inválida: {e}", file=sys.stderr)
        return 2
    est = estimar(unidades, ctx, precios, cfg)

    print(f"Configuración: {cfg['nombre']} | adaptador: {args.adapter} | tareas: {len(cfg['tareas'])} | "
          f"modelos: {len(cfg['modelos'])} | unidades (incluye D+R): {len(unidades)}")
    for o in omitidas:
        print(f"  omitido: {o}")
    print()
    print("Estimación previa (tokens de entrada contados sobre los prompts reales; precios PROVISIONALES salvo que se indique):")
    print(est.tabla())
    if args.adapter == "simulado":
        print("\nNota: con --adapter simulado no se llama a ninguna API; los costos son nocionales.")
    if args.dry_run:
        return 0

    if args.max_costo_usd is not None:
        if est.costo_esperado is None:
            print("abortado: hay modelos sin precio en precios.json y se pidió --max-costo-usd", file=sys.stderr)
            return 2
        if est.costo_esperado > args.max_costo_usd:
            print(f"abortado: costo esperado {est.costo_esperado:.2f} USD supera --max-costo-usd {args.max_costo_usd}",
                  file=sys.stderr)
            return 2
    if args.adapter == "real":
        if not args.confirmar_real:
            print("abortado: la ejecución real requiere --confirmar-real (use --dry-run para estimar)", file=sys.stderr)
            return 2
        faltan = X.verificar_claves(cfg)
        if faltan:
            print("abortado: faltan variables de entorno: " + ", ".join(faltan), file=sys.stderr)
            return 2

    _config_logging(salida, args.verboso)
    manifiesto = {"nombre": cfg["nombre"], "adaptador": args.adapter, "simulado": args.adapter == "simulado",
                  "advertencia": ("RESULTADOS SIMULADOS: solo validan el arnés; no son resultados del estudio"
                                  if args.adapter == "simulado" else ""),
                  "config": cfg, "commit": _git_commit(), "python": platform.python_version(),
                  "unidades": len(unidades), "omitidas": omitidas,
                  "estimacion": {"llamadas": est.llamadas, "costo_esperado_usd": est.costo_esperado,
                                 "costo_maximo_usd": est.costo_maximo}}
    (salida / "manifiesto.json").write_text(json.dumps(manifiesto, ensure_ascii=False, indent=2), encoding="utf-8")

    try:
        ej = X.Ejecutor(cfg, ctx, args.adapter, salida, precios, max_costo=args.max_costo_usd)
        if ej.almacen.lineas_corruptas:
            logging.warning("%d líneas ilegibles en muestras.jsonl; esas muestras se repetirán", ej.almacen.lineas_corruptas)
        res = ej.correr(unidades, limite=args.limite)
        logging.info("resultado: %s", res)
    finally:
        for h in list(logging.getLogger().handlers):
            logging.getLogger().removeHandler(h)
            h.close()
    print(json.dumps(res, ensure_ascii=False))
    return 3 if res.get("abortado") else 0


if __name__ == "__main__":
    sys.exit(main())
