# -*- coding: utf-8 -*-
"""Tablas de V7: tokens y dinero por registro, y desde qué tamaño de lote la respuesta sale mal.

    python experiments/v7_escalamiento/analizar.py --resultados experiments/v7_escalamiento/results/deepseek

Escribe en el mismo directorio:
  por_lote.csv     una fila por (formato, tamaño de lote): mediana de tokens, aprovechamiento y cortes
  resumen.csv      una fila por formato: tokens por registro y costo por 1 000 y por 20 000 registros
y muestra el punto de quiebre: el primer tamaño de lote en el que no se aprovechan todos los registros.
"""
from __future__ import annotations

import argparse
import csv
import json
import statistics
from pathlib import Path
from typing import Any, Dict, List

AQUI = Path(__file__).resolve().parent


def leer(directorio: Path) -> List[Dict[str, Any]]:
    filas = []
    for linea in (directorio / "llamadas.jsonl").read_text(encoding="utf-8").splitlines():
        if linea.strip():
            filas.append(json.loads(linea))
    return [f for f in filas if not f.get("error")]


def mediana(valores: List[float]) -> float:
    return statistics.median(valores) if valores else 0.0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--resultados", default=str(AQUI / "results" / "deepseek"))
    ap.add_argument("--objetivo", type=int, default=20000, help="registros de referencia para el costo")
    a = ap.parse_args()
    d = Path(a.resultados)
    filas = leer(d)
    meta = json.loads((d / "meta.json").read_text(encoding="utf-8"))
    precios = meta["precios"]
    if not filas:
        print("sin llamadas válidas")
        return 1

    formatos = sorted({f["formato"] for f in filas})
    lotes = sorted({f["lote"] for f in filas})

    # ------------------------------------------------------------ por tamaño de lote
    por_lote = []
    for formato in formatos:
        for L in lotes:
            g = [f for f in filas if f["formato"] == formato and f["lote"] == L]
            if not g:
                continue
            solicitados = sum(f["solicitados"] for f in g)
            aprovechados = sum(f["aprovechados"] for f in g)
            completos = sum(f["completos"] for f in g)
            cortes = sum(1 for f in g if f.get("motivo_parada") == "length")
            por_lote.append({
                "formato": formato, "lote": L, "llamadas": len(g),
                "registros_solicitados": solicitados,
                "registros_completos": completos,
                "registros_aprovechados": aprovechados,
                "aprovechamiento_pct": round(100 * aprovechados / solicitados, 1),
                "llamadas_cortadas": cortes,
                "tokens_salida_mediana": round(mediana([f["tokens_salida"] or 0 for f in g])),
                "tokens_por_registro": round(mediana([(f["tokens_salida"] or 0) / f["solicitados"] for f in g]), 2),
                "ms_mediana": round(mediana([f["ms"] for f in g])),
                "lecturas": ";".join(sorted({f["lectura"] for f in g})),
            })

    with (d / "por_lote.csv").open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(por_lote[0].keys()))
        w.writeheader()
        w.writerows(por_lote)

    # ------------------------------------------------------------ resumen por formato y dinero
    resumen = []
    for formato in formatos:
        g = [f for f in filas if f["formato"] == formato]
        # el costo por registro se calcula solo con los lotes que se aprovechan del todo
        buenos = [f for f in g if f["aprovechados"] == f["solicitados"]]
        base = buenos or g
        tpr_salida = mediana([(f["tokens_salida"] or 0) / f["solicitados"] for f in base])
        tpr_entrada = mediana([(f["tokens_entrada"] or 0) / f["solicitados"] for f in base])
        usd_salida = (tpr_salida * a.objetivo / 1e6) * (precios["salida"] or 0)
        usd_entrada = (tpr_entrada * a.objetivo / 1e6) * (precios["entrada"] or 0)
        resumen.append({
            "formato": formato,
            "llamadas": len(g),
            "registros": sum(f["solicitados"] for f in g),
            "tokens_salida_por_registro": round(tpr_salida, 2),
            "tokens_entrada_por_registro": round(tpr_entrada, 2),
            f"usd_por_{a.objetivo}_registros_salida": round(usd_salida, 4),
            f"usd_por_{a.objetivo}_registros_total": round(usd_salida + usd_entrada, 4),
            "lote_maximo_sin_perdida": max([f["lote"] for f in buenos], default=0),
        })
    with (d / "resumen.csv").open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(resumen[0].keys()))
        w.writeheader()
        w.writerows(resumen)

    # ------------------------------------------------------------ salida legible
    print(f"modelo {meta['modelo']} ({meta['proveedor']}) · límite de salida {meta['max_tokens']} tokens · "
          f"precios {precios['modelo_precio']} {precios['entrada']}/{precios['salida']} USD por 1M ({precios['fecha']})\n")
    print(f"{'formato':7} {'lote':>5} {'llam':>5} {'tok/reg':>8} {'tok salida':>11} {'aprovech.':>10} {'cortadas':>9}  lectura")
    for f in por_lote:
        print(f"{f['formato']:7} {f['lote']:>5} {f['llamadas']:>5} {f['tokens_por_registro']:>8} "
              f"{f['tokens_salida_mediana']:>11} {f['aprovechamiento_pct']:>9}% {f['llamadas_cortadas']:>9}  {f['lecturas'][:44]}")

    print("\npunto de quiebre (primer tamaño de lote que ya no se aprovecha del todo):")
    for formato in formatos:
        fallos = [f for f in por_lote if f["formato"] == formato and f["aprovechamiento_pct"] < 100]
        buenos = [f for f in por_lote if f["formato"] == formato and f["aprovechamiento_pct"] == 100]
        tope = max([f["lote"] for f in buenos], default=0)
        if fallos:
            primero = min(f["lote"] for f in fallos)
            print(f"  {formato:5} falla desde {primero} registros por llamada; el mayor lote sin pérdida es {tope}")
        else:
            print(f"  {formato:5} sin pérdidas hasta {tope} registros por llamada")

    print(f"\ncosto de procesar {a.objetivo:,} registros:")
    for r in resumen:
        print(f"  {r['formato']:5} {r['tokens_salida_por_registro']:>6} tokens de salida por registro · "
              f"{r[f'usd_por_{a.objetivo}_registros_salida']:>7.4f} USD de salida · "
              f"{r[f'usd_por_{a.objetivo}_registros_total']:>7.4f} USD con la entrada")
    if len(resumen) == 2:
        j = next(r for r in resumen if r["formato"] == "json")
        m = next(r for r in resumen if r["formato"] == "mini")
        ahorro = 100 * (1 - m["tokens_salida_por_registro"] / j["tokens_salida_por_registro"])
        dif = j[f"usd_por_{a.objetivo}_registros_total"] - m[f"usd_por_{a.objetivo}_registros_total"]
        print(f"\n  .mini ahorra {ahorro:.0f} % de los tokens de salida: {dif:.4f} USD menos por cada "
              f"{a.objetivo:,} registros con este modelo.")
    print(f"\ntablas en {d/'por_lote.csv'} y {d/'resumen.csv'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
