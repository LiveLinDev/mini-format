"""Resultados del estudio de formatos a partir de las corridas grabadas (no llama a ningún modelo).

    python experiments/estudio_formatos/ver.py tokens
    python experiments/estudio_formatos/ver.py validez
    python experiments/estudio_formatos/ver.py reparacion
    python experiments/estudio_formatos/ver.py latencia
    python experiments/estudio_formatos/ver.py costo
    python experiments/estudio_formatos/ver.py todo --json

Opciones comunes: ``--resultados`` (por defecto ``corridas/resultados.json``), ``--tarifas`` (por defecto
``tarifas/tarifas.json``, el resultado de ``tools/tarifas.py consultar``) y ``--proveedores``.

Definiciones:

* tokens: tokens de salida que informa el proveedor (incluyen el razonamiento cuando el modelo razona).
* validez: registros válidos de la primera respuesta, tras los ajustes locales deterministas y sin pedir nada más al
  modelo, dividido entre los registros solicitados (20 por corrida); intervalo de confianza de Wilson al 95 %.
* reparación: validez antes y después de la única ronda de corrección (selectiva en .mini; respuesta completa en JSON).
* latencia: tiempo de reloj de la llamada de generación, medido alrededor del cliente (incluye su arranque).
* costo: USD de salida por mil registros válidos = tokens de salida de todas las llamadas × tarifa de salida
  verificada / registros válidos finales × 1000. Sin tarifa verificada no se calcula.
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from decimal import Decimal
from pathlib import Path

AQUI = Path(__file__).resolve().parent
Z95 = 1.959963984540054


def wilson(exitos: int, total: int, z: float = Z95) -> tuple:
    """Intervalo de Wilson (proporción entre 0 y 1)."""
    if total <= 0:
        return (0.0, 0.0)
    p = exitos / total
    den = 1 + z * z / total
    centro = (p + z * z / (2 * total)) / den
    margen = z * math.sqrt(p * (1 - p) / total + z * z / (4 * total * total)) / den
    return (max(0.0, centro - margen), min(1.0, centro + margen))


def percentil(valores, q: float):
    """Percentil por rango más cercano (con n = 3, el p95 es el máximo)."""
    xs = sorted(v for v in valores if v is not None)
    if not xs:
        return None
    k = max(1, math.ceil(q / 100 * len(xs)))
    return xs[k - 1]


def media(valores):
    xs = [v for v in valores if v is not None]
    return sum(xs) / len(xs) if xs else None


def cargar(resultados: Path) -> list:
    doc = json.loads(Path(resultados).read_text(encoding="utf-8"))
    return [c for c in doc["corridas"] if c.get("estado") == "completa"]


def grupos(corridas: list) -> dict:
    """{(proveedor, formato): [corridas]} en orden estable."""
    out: dict = {}
    for c in sorted(corridas, key=lambda c: (c["proveedor"], c["formato"], c["repeticion"])):
        out.setdefault((c["proveedor"], c["formato"]), []).append(c)
    return out


def _generacion(c):
    return next((l for l in c["llamadas"] if l["etapa"] == "generacion"), {})


def tokens(corridas):
    filas = []
    for (prov, fmt), cs in grupos(corridas).items():
        filas.append({"proveedor": prov, "formato": fmt, "corridas": len(cs),
                      "salida_generacion_media": media([_generacion(c).get("tokens_salida") for c in cs]),
                      "razonamiento_medio": media([_generacion(c).get("tokens_razonamiento") for c in cs]),
                      "salida_total_media": media([sum(l.get("tokens_salida") or 0 for l in c["llamadas"]) for c in cs])})
    por = {(f["proveedor"], f["formato"]): f for f in filas}
    for f in filas:
        base = por.get((f["proveedor"], "json"))
        if f["formato"] == "mini" and base and base["salida_generacion_media"]:
            f["cambio_vs_json_pct"] = 100 * (f["salida_generacion_media"] / base["salida_generacion_media"] - 1)
    return filas


def validez(corridas):
    filas = []
    for (prov, fmt), cs in grupos(corridas).items():
        sol = sum(c["solicitados"] for c in cs)
        val = sum(c["validos_inicial"] for c in cs)
        lo, hi = wilson(val, sol)
        filas.append({"proveedor": prov, "formato": fmt, "corridas": len(cs), "solicitados": sol, "validos": val,
                      "validez_pct": 100 * val / sol if sol else None, "ic95_pct": [100 * lo, 100 * hi],
                      "respuestas_completas": sum(1 for c in cs if c["validos_inicial"] == c["solicitados"])})
    return filas


def reparacion(corridas):
    filas = []
    for (prov, fmt), cs in grupos(corridas).items():
        sol = sum(c["solicitados"] for c in cs)
        antes = sum(c["validos_inicial"] for c in cs)
        despues = sum(c["validos_final"] for c in cs)
        filas.append({"proveedor": prov, "formato": fmt, "corridas": len(cs), "solicitados": sol,
                      "validez_antes_pct": 100 * antes / sol if sol else None,
                      "validez_despues_pct": 100 * despues / sol if sol else None,
                      "corridas_con_correccion": sum(1 for c in cs if any(l["etapa"] == "correccion" for l in c["llamadas"])),
                      "tokens_correccion": sum(l.get("tokens_salida") or 0 for c in cs for l in c["llamadas"]
                                               if l["etapa"] == "correccion")})
    return filas


def latencia(corridas):
    filas = []
    for (prov, fmt), cs in grupos(corridas).items():
        gen = [_generacion(c).get("latencia_s") for c in cs]
        filas.append({"proveedor": prov, "formato": fmt, "corridas": len(cs), "media_s": media(gen),
                      "p95_s": percentil(gen, 95),
                      "corrida_completa_media_s": media([sum(l.get("latencia_s") or 0 for l in c["llamadas"]) for c in cs])})
    return filas


def tarifas_por_proveedor(tarifas: Path, proveedores: Path) -> dict:
    """{id de proveedor: (salida USD por millón como Decimal o None, estado, fecha)}."""
    doc = json.loads(Path(tarifas).read_text(encoding="utf-8")) if Path(tarifas).is_file() else {"tarifas": []}
    idx = {(t["proveedor"], t["modelo_api_id"]): t for t in doc["tarifas"]}
    provs = json.loads(Path(proveedores).read_text(encoding="utf-8"))["proveedores"]
    out = {}
    for p in provs:
        ref = p.get("tarifa") or {}
        t = idx.get((ref.get("proveedor"), ref.get("modelo_api_id")))
        if t and t.get("estado") == "verificada" and t.get("salida_por_millon") is not None:
            out[p["id"]] = (Decimal(t["salida_por_millon"]), "verificada", t.get("fecha_consulta_utc"))
        else:
            out[p["id"]] = (None, t.get("estado") if t else "sin entrada", t.get("fecha_consulta_utc") if t else None)
    return out


def costo(corridas, tarifas: dict):
    filas = []
    for (prov, fmt), cs in grupos(corridas).items():
        salida = sum(l.get("tokens_salida") or 0 for c in cs for l in c["llamadas"])
        validos = sum(c["validos_final"] for c in cs)
        precio, estado, fecha = tarifas.get(prov, (None, "sin entrada", None))
        usd = None
        if precio is not None and validos:
            usd = float(Decimal(salida) * precio / Decimal(10 ** 6) / Decimal(validos) * 1000)
        filas.append({"proveedor": prov, "formato": fmt, "tokens_salida": salida, "validos_finales": validos,
                      "tarifa_salida_usd_millon": None if precio is None else float(precio), "tarifa_estado": estado,
                      "tarifa_fecha_utc": fecha, "usd_por_mil_validos": usd})
    por = {(f["proveedor"], f["formato"]): f for f in filas}
    for f in filas:
        base = por.get((f["proveedor"], "json"))
        if f["formato"] == "mini" and base and base["usd_por_mil_validos"] and f["usd_por_mil_validos"] is not None:
            f["cambio_vs_json_pct"] = 100 * (f["usd_por_mil_validos"] / base["usd_por_mil_validos"] - 1)
    return filas


def _fmt(v, dec=1):
    if v is None:
        return "—"
    if isinstance(v, float):
        return f"{v:,.{dec}f}".replace(",", " ")
    if isinstance(v, list):
        return "[" + ", ".join(_fmt(x, dec) for x in v) + "]"
    return str(v)


def tabla(filas, columnas) -> str:
    cab = [c[1] for c in columnas]
    datos = [[_fmt(f.get(c[0]), c[2] if len(c) > 2 else 1) for c in columnas] for f in filas]
    anchos = [max(len(x) for x in [cab[i]] + [d[i] for d in datos]) for i in range(len(cab))]
    lineas = ["  ".join(cab[i].ljust(anchos[i]) for i in range(len(cab)))]
    lineas.append("  ".join("-" * a for a in anchos))
    lineas += ["  ".join(d[i].ljust(anchos[i]) for i in range(len(cab))) for d in datos]
    return "\n".join(lineas)


COLUMNAS = {
    "tokens": [("proveedor", "proveedor"), ("formato", "formato"), ("corridas", "n"),
               ("salida_generacion_media", "salida (gen.)"), ("razonamiento_medio", "razonamiento"),
               ("salida_total_media", "salida total"), ("cambio_vs_json_pct", ".mini vs JSON %")],
    "validez": [("proveedor", "proveedor"), ("formato", "formato"), ("validos", "válidos"),
                ("solicitados", "solicitados"), ("validez_pct", "validez %"), ("ic95_pct", "IC 95 % (Wilson)"),
                ("respuestas_completas", "respuestas 20/20")],
    "reparacion": [("proveedor", "proveedor"), ("formato", "formato"), ("validez_antes_pct", "antes %"),
                   ("validez_despues_pct", "después %"), ("corridas_con_correccion", "correcciones"),
                   ("tokens_correccion", "tokens de corrección")],
    "latencia": [("proveedor", "proveedor"), ("formato", "formato"), ("media_s", "media s", 2),
                 ("p95_s", "p95 s", 2), ("corrida_completa_media_s", "corrida completa s", 2)],
    "costo": [("proveedor", "proveedor"), ("formato", "formato"), ("tokens_salida", "tokens de salida"),
              ("validos_finales", "válidos"), ("tarifa_salida_usd_millon", "USD/M salida", 2),
              ("tarifa_estado", "tarifa"), ("usd_por_mil_validos", "USD por 1 000 válidos", 4),
              ("cambio_vs_json_pct", ".mini vs JSON %")],
}


def calcular(cmd, corridas, tarifas):
    return {"tokens": tokens, "validez": validez, "reparacion": reparacion, "latencia": latencia}[cmd](corridas) \
        if cmd != "costo" else costo(corridas, tarifas)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("comando", choices=list(COLUMNAS) + ["todo"])
    ap.add_argument("--resultados", default=str(AQUI / "corridas" / "resultados.json"))
    ap.add_argument("--tarifas", default=str(AQUI / "tarifas" / "tarifas.json"))
    ap.add_argument("--proveedores", default=str(AQUI / "proveedores.json"))
    ap.add_argument("--json", action="store_true", help="salida en JSON")
    a = ap.parse_args(argv)
    corridas = cargar(Path(a.resultados))
    if not corridas:
        print("No hay corridas completas en " + a.resultados, file=sys.stderr)
        return 1
    tarifas = tarifas_por_proveedor(Path(a.tarifas), Path(a.proveedores))
    cmds = list(COLUMNAS) if a.comando == "todo" else [a.comando]
    salida = {c: calcular(c, corridas, tarifas) for c in cmds}
    if a.json:
        print(json.dumps(salida if a.comando == "todo" else salida[a.comando], ensure_ascii=False, indent=2))
        return 0
    for c in cmds:
        if len(cmds) > 1:
            print(f"\n== {c}")
        print(tabla(salida[c], COLUMNAS[c]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
