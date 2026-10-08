"""V7 · Escala con modelo real: reanálisis local de las respuestas archivadas de la corrida de volumen.

Lee las llamadas registradas con DeepSeek el 17/09/2026 (experiments/v7_escalamiento/results/deepseek_volumen
y el barrido por lote de experiments/v7_escalamiento/results/deepseek), recalcula por formato los registros
solicitados, válidos y aprovechables, los tokens que informó el proveedor y los cortes, y registra la corrida
como ``reproducido_local`` (componente ``reanalisis_volumen``). No llama a ninguna API.

Uso: python tools/ejecutar_v7.py
"""
import csv
import json
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import evidencia_lib as ev  # noqa: E402

RAIZ = ev.raiz_repo()
VOLUMEN = RAIZ / "experiments" / "v7_escalamiento" / "results" / "deepseek_volumen" / "llamadas.jsonl"
BARRIDO = RAIZ / "experiments" / "v7_escalamiento" / "results" / "deepseek" / "por_lote.csv"


def resumir(ruta):
    acc = defaultdict(lambda: defaultdict(float))
    lotes = defaultdict(set)
    for linea in ruta.read_text(encoding="utf-8").splitlines():
        if not linea.strip():
            continue
        d = json.loads(linea)
        a = acc[d["formato"]]
        lotes[d["formato"]].add(d["lote"])
        a["llamadas"] += 1
        for k in ("solicitados", "validos", "aprovechados", "tokens_entrada", "tokens_salida"):
            a[k] += d.get(k) or 0
        a["cortes"] += 1 if d.get("motivo_parada") == "length" else 0
        a["usd_estimado"] += d.get("usd") or 0
    out = {}
    for f, a in acc.items():
        out[f] = {
            "lote": sorted(lotes[f]),
            "llamadas": int(a["llamadas"]),
            "registros_solicitados": int(a["solicitados"]),
            "registros_validos": int(a["validos"]),
            "registros_aprovechables": int(a["aprovechados"]),
            "aprovechables_pct": round(100 * a["aprovechados"] / a["solicitados"], 3),
            "tokens_entrada": int(a["tokens_entrada"]),
            "tokens_salida": int(a["tokens_salida"]),
            "tokens_salida_por_registro": round(a["tokens_salida"] / a["solicitados"], 3),
            "respuestas_cortadas": int(a["cortes"]),
            "usd_estimado_tarifas_archivadas": round(a["usd_estimado"], 4),
        }
    return out


def barrido():
    """Aprovechamiento por formato y tamaño de lote, y mayor lote sin pérdida (todos los registros aprovechables)."""
    with BARRIDO.open(encoding="utf-8") as f:
        filas = list(csv.DictReader(f))
    por_lote, maximo = {}, {}
    for fila in filas:
        fmt, lote, pct = fila["formato"], int(fila["lote"]), float(fila["aprovechamiento_pct"])
        por_lote.setdefault(fmt, {})[str(lote)] = {"aprovechamiento_pct": pct, "llamadas_cortadas": int(fila["llamadas_cortadas"]),
                                                    "tokens_por_registro": float(fila["tokens_por_registro"])}
    for fmt, lotes in por_lote.items():
        sin_perdida = [int(l) for l, v in lotes.items() if v["aprovechamiento_pct"] >= 100.0]
        maximo[fmt] = max(sin_perdida) if sin_perdida else None
    return por_lote, maximo


def main():
    por_formato = resumir(VOLUMEN)
    mini, js = por_formato["mini"], por_formato["json"]
    resumen = {
        "por_formato": por_formato,
        "registros_minimo_por_formato": min(mini["registros_solicitados"], js["registros_solicitados"]),
        "registros_totales": mini["registros_solicitados"] + js["registros_solicitados"],
        "aprovechables_pct_mini": mini["aprovechables_pct"],
        "aprovechables_pct_json": js["aprovechables_pct"],
        "reduccion_tokens_salida_pct": round(100 * (1 - mini["tokens_salida_por_registro"] / js["tokens_salida_por_registro"]), 2),
        "reduccion_costo_estimado_pct": round(100 * (1 - mini["usd_estimado_tarifas_archivadas"] / js["usd_estimado_tarifas_archivadas"]), 2),
        "llamadas_por_formato": {"mini": mini["llamadas"], "json": js["llamadas"]},
    }
    por_lote, maximo = barrido()
    resumen["barrido_por_lote"] = por_lote
    resumen["lote_maximo_sin_perdida"] = maximo
    cortados = [l for l, v in por_lote["json"].items() if v["llamadas_cortadas"] > 0]
    with BARRIDO.open(encoding="utf-8") as f:
        filas = [r for r in csv.DictReader(f) if r["lote"] in cortados]
    sol = sum(int(r["registros_solicitados"]) for r in filas if r["formato"] == "json")
    apr = {fmt: sum(int(r["registros_aprovechados"]) for r in filas if r["formato"] == fmt) for fmt in ("json", "mini")}
    resumen["lotes_con_corte_json"] = sorted(int(l) for l in cortados)
    resumen["registros_solicitados_con_corte"] = sol
    resumen["aprovechables_con_corte"] = apr
    resumen["aprovechables_con_corte_pct_mini"] = round(100 * apr["mini"] / sol, 2)
    m = ev.nueva_corrida(
        "V7", "reproducido_local", "python tools/ejecutar_v7.py",
        modelo={"proveedor": "DeepSeek", "modelo_pedido": "deepseek-chat", "nota": "respuestas archivadas del 17/09/2026; no se llamó a la API"},
        parametros={"componente": "reanalisis_volumen", "fuente": ev.ruta_relativa(VOLUMEN)},
        conjuntos=[ev.referencia_archivo(VOLUMEN), ev.referencia_archivo(BARRIDO)],
        resumen=resumen,
        limitaciones=[
            "Reanálisis de respuestas archivadas: las llamadas son anteriores a los manifiestos de corrida.",
            "Un solo proveedor y un solo modelo (deepseek-chat); un dominio (tickets de soporte).",
            "Lotes distintos por formato: JSON en lotes de 100 y .mini en lotes de 200 (el mayor lote sin pérdida de cada uno en el barrido).",
            "El costo es una estimación con las tarifas archivadas; el consumo real informado (0,78 USD) no se concilia con ellas.",
        ],
        notas="Formaliza V7 como estudio de escala. La replicación confirmatoria con API (componente replicacion_volumen_api) queda pendiente de autorización de gasto.",
    )
    d = ev.directorio_corridas() / m["run_id"]
    d.mkdir(parents=True, exist_ok=True)
    salida = d / "resumen_v7.json"
    ev.escribir_json(salida, resumen)
    destino = ev.guardar_corrida(m, [salida], d)
    print(destino)
    print(json.dumps(resumen, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
