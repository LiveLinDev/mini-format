"""Resumen de la corrida V2 con las CLI (Claude Code y Kimi Code): validez por modelo y condición, tokens de salida
informados por cada CLI y costo de salida (tokens de salida × tarifa de salida).

Lee las muestras importadas por ``run.py importar`` (carpeta ``import_todos``) y los JSONL de respuestas, que traen el uso.
Escribe ``resumen_cli.json`` y ``resumen_cli.csv`` en la carpeta de resultados.
Uso: python experiments/generativo/cli/resumir_cli.py experiments/generativo/resultados/cli_2026-11
"""
from __future__ import annotations

import collections
import csv
import json
import statistics
import sys
from decimal import Decimal
from pathlib import Path

NOMBRES = {"claude-opus-5-5": "Claude Opus 5.5", "claude-haiku-5-5": "Claude Haiku 5.5", "kimi-k3.1-pro": "Kimi K3.1 Pro"}
PROVEEDOR = {"claude-opus-5-5": "Anthropic", "claude-haiku-5-5": "Anthropic", "kimi-k3.1-pro": "Moonshot AI (Kimi)"}


def main(R: Path) -> None:
    uso = {}
    for f in sorted(R.glob("respuestas_*.jsonl")):
        for l in f.read_text(encoding="utf-8").splitlines():
            if l.strip():
                x = json.loads(l)
                uso[x["celda_id"]] = x
    muestras = [json.loads(l) for l in (R / "import_todos" / "muestras.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
    g = collections.defaultdict(list)
    for s in muestras:
        g[(s["modelo"], s["brazo"])].append(s)
    # X+1 cuya reparación no se pudo ejecutar (p. ej., límite de uso de la suscripción): cuenta como NO reparada,
    # con las métricas de su respuesta base; no se excluye del denominador
    sin_reparar = collections.Counter()
    ids = {s["id"] for s in muestras}
    for (modelo, brazo), ss in list(g.items()):
        if brazo not in ("A", "B", "D"):
            continue
        for s0 in ss:
            sid = s0["id"].replace(f"/{brazo}/", f"/{brazo}+1/")
            if sid not in ids:
                g[(modelo, brazo + "+1")].append({**s0, "id": sid, "brazo": brazo + "+1"})
                sin_reparar[(modelo, brazo + "+1")] += 1
    filas = []
    for (modelo, brazo), ss in sorted(g.items()):
        sol = sum(s["metricas"]["solicitados"] for s in ss)
        val = sum(s["metricas"]["validos_finales"] for s in ss)
        ext = [s for s in ss if s["tipo_tarea"] == "extraccion"]
        exa = sum(s["metricas"].get("exactos_contenido") or 0 for s in ext)
        sol_ext = sum(s["metricas"]["solicitados"] for s in ext)
        base = brazo.replace("+1", "")
        tokens, costo, reparadas, razon = [], Decimal(0), 0, []
        for s in ss:
            celda_base = s["id"].replace(f"/{brazo}/", f"/{base}/")
            u = uso.get(celda_base)
            if u and u.get("uso_cli", {}).get("salida") is not None:
                t = u["uso_cli"]["salida"]
                if u["uso_cli"].get("razonamiento") is not None:
                    razon.append(u["uso_cli"]["razonamiento"])
                c = Decimal(u["costo_salida_usd"])
                if brazo.endswith("+1"):
                    r = uso.get(s["id"])
                    if r and r.get("uso_cli", {}).get("salida") is not None:
                        t += r["uso_cli"]["salida"]
                        c += Decimal(r["costo_salida_usd"])
                        reparadas += 1
                tokens.append(t)
                costo += c
        filas.append({
            "modelo": modelo, "nombre": NOMBRES.get(modelo, modelo), "proveedor": PROVEEDOR.get(modelo, "?"),
            "condicion": brazo, "muestras": len(ss), "solicitados": sol, "validos": val,
            "validez": round(val / sol, 4) if sol else None,
            "exactitud_extraccion": round(exa / sol_ext, 4) if sol_ext else None,
            "sintaxis_ok": sum(1 for s in ss if s["metricas"]["sintaxis_ok"]),
            "tokens_salida_media": round(statistics.mean(tokens), 1) if tokens else None,
            "costo_salida_usd": float(round(costo, 6)),
            "costo_por_1000_validos_usd": float(round(costo / val * 1000, 4)) if val else None,
            "reparaciones_con_llamada": reparadas,
            "reparaciones_no_ejecutadas": sin_reparar[(modelo, brazo)],
            "razonamiento_media": round(statistics.mean(razon), 1) if razon else None,
        })
    (R / "resumen_cli.json").write_text(json.dumps(filas, ensure_ascii=False, indent=1), encoding="utf-8")
    with open(R / "resumen_cli.csv", "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(filas[0]))
        w.writeheader()
        w.writerows(filas)
    # V3a sobre las salidas reales (cortes en 20 puntos de cada respuesta; analyze.py)
    v3 = {}
    ruta = R / "import_todos" / "analisis" / "v3a_truncamiento.csv"
    if ruta.exists():
        with open(ruta, encoding="utf-8") as fh:
            t = {r["brazo"]: r for r in csv.DictReader(fh)}
        if "D" in t and "B" in t:
            v3 = {"salidas": int(t["D"]["muestras"]), "cortes": int(t["D"]["cortes"]),
                  "mini_recuperacion": float(t["D"]["recuperados_sobre_ideal_pct"]) / 100,
                  "json_estricto_recuperacion": float(t["B"]["recuperados_sobre_ideal_pct"]) / 100,
                  "mini_incorrectos": int(t["D"]["incorrectos_sin_aviso_total"]),
                  "salidas_json": int(t["B"]["muestras"])}
            (R / "resumen_v3a_real.json").write_text(json.dumps(v3, ensure_ascii=False, indent=1), encoding="utf-8")
            print("V3a sobre salidas reales:", v3)
    for f in filas:
        print(f"{f['nombre']:17} {f['condicion']:4} n={f['muestras']:3} validez={f['validez']} exact={f['exactitud_extraccion']} "
              f"tok={f['tokens_salida_media']} costo={f['costo_salida_usd']} por1000={f['costo_por_1000_validos_usd']}")


if __name__ == "__main__":
    main(Path(sys.argv[1]))
