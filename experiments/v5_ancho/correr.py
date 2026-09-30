"""V5 — Ahorro de tokens en función del ANCHO del registro (campos por objeto).

Motivación
----------
El arnés de `benchmark/` barre el número de registros (n) pero mantiene fijo el
esquema de cada fork. La hipótesis "a más campos por objeto, más gana .mini"
queda por tanto sin medir. Este experimento barre las dos dimensiones:

    ancho W  = campos por registro   ∈ {3, 5, 8, 12, 20, 32, 50}
    lote  N  = registros por documento ∈ {1, 10, 100, 1000}

Mecanismo que se pone a prueba: .mini declara los nombres de campo una sola vez
en la cabecera; JSON los repite en cada objeto. El coste de los nombres crece
como O(W·N) en JSON y como O(W) en .mini, así que el ahorro debería crecer con
W y saturar con N. Esto es una PREDICCIÓN, no un resultado: el script la
confirma o la refuta, y ambas salidas se publican.

Datos
-----
Sintéticos, deterministas (semilla fija), con tipos y longitudes de cadena
declarados en POOL. Son sintéticos a propósito: para barrer el ancho hace falta
controlarlo, y ningún corpus real ofrece el mismo contenido a 3 y a 50 campos.
La validez externa con cargas reales de APIs públicas está pendiente.

Uso
---
    python experiments/v5_ancho/correr.py
    python experiments/v5_ancho/correr.py --anchos 3,12,50 --lotes 1,100
"""
from __future__ import annotations

import argparse
import csv
import json
import random
import statistics
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "benchmark"))

import formats  # noqa: E402
from minifmt import Contract  # noqa: E402
from minifmt.tokens import get_tokenizer  # noqa: E402
import vocab_local  # noqa: E402  (vocabularios de benchmark/vocab, sin red y con hash verificado)

RESULTS = Path(__file__).resolve().parent / "results"
SEMILLA = 20260915

# --------------------------------------------------------------------------
# Repertorio de campos. Orden fijo: el ancho W toma los W primeros, de modo que
# un documento de 12 campos es un superconjunto estricto del de 8. Así la curva
# mide el efecto del ancho y no un cambio de contenido.
# --------------------------------------------------------------------------
POOL = [
    ("id",            "str",   lambda r: f"SKU-{r.randrange(10**6):06d}"),
    ("cantidad",      "int",   lambda r: r.randrange(0, 5000)),
    ("precio",        "float", lambda r: round(r.uniform(1, 9999), 2)),
    ("moneda",        "enum",  lambda r: r.choice(["PEN", "USD", "EUR"]), ["PEN", "USD", "EUR"]),
    ("almacen",       "enum",  lambda r: r.choice(["LIM", "ARE", "TRU", "CUZ"]), ["LIM", "ARE", "TRU", "CUZ"]),
    ("actualizado",   "str",   lambda r: f"2026-{r.randrange(1,13):02d}-{r.randrange(1,29):02d}"),
    ("activo",        "bool",  lambda r: r.choice([True, False])),
    ("categoria",     "str",   lambda r: r.choice(["herramientas", "hogar", "oficina", "jardin", "deporte"])),
    ("proveedor_id",  "int",   lambda r: r.randrange(1, 900)),
    ("peso_kg",       "float", lambda r: round(r.uniform(.05, 40), 3)),
    ("alto_cm",       "float", lambda r: round(r.uniform(1, 200), 1)),
    ("ancho_cm",      "float", lambda r: round(r.uniform(1, 200), 1)),
    ("profundo_cm",   "float", lambda r: round(r.uniform(1, 200), 1)),
    ("stock_minimo",  "int",   lambda r: r.randrange(0, 100)),
    ("stock_maximo",  "int",   lambda r: r.randrange(100, 9000)),
    ("descuento_pct", "float", lambda r: round(r.uniform(0, 60), 1)),
    ("impuesto_pct",  "float", lambda r: r.choice([0.0, 10.0, 18.0])),
    ("codigo_barras", "str",   lambda r: f"{r.randrange(10**12):013d}"),
    ("lote",          "str",   lambda r: f"L{r.randrange(10**5):05d}"),
    ("vence",         "str",   lambda r: f"2027-{r.randrange(1,13):02d}-{r.randrange(1,29):02d}"),
    ("pasillo",       "str",   lambda r: f"{r.choice('ABCDEFGH')}{r.randrange(1,40):02d}"),
    ("nivel",         "int",   lambda r: r.randrange(1, 9)),
    ("rotacion",      "enum",  lambda r: r.choice(["alta", "media", "baja"]), ["alta", "media", "baja"]),
    ("devoluciones",  "int",   lambda r: r.randrange(0, 60)),
    ("calificacion",  "float", lambda r: round(r.uniform(1, 5), 1)),
    ("resenas",       "int",   lambda r: r.randrange(0, 4000)),
    ("envio_gratis",  "bool",  lambda r: r.choice([True, False])),
    ("dias_entrega",  "int",   lambda r: r.randrange(1, 30)),
    ("origen",        "enum",  lambda r: r.choice(["PE", "CN", "US", "BR", "DE"]), ["PE", "CN", "US", "BR", "DE"]),
    ("garantia_mes",  "int",   lambda r: r.choice([0, 6, 12, 24, 36])),
    ("serie",         "str",   lambda r: f"{r.randrange(10**8):08d}"),
    ("ubicacion_ext", "str",   lambda r: f"Z{r.randrange(1,9)}-{r.randrange(1,99):02d}"),
    ("color",         "str",   lambda r: r.choice(["negro", "blanco", "azul", "rojo", "gris"])),
    ("material",      "str",   lambda r: r.choice(["acero", "plastico", "madera", "aluminio"])),
    ("marca",         "str",   lambda r: r.choice(["Acme", "Norte", "Vega", "Lumen", "Orion"])),
    ("modelo",        "str",   lambda r: f"M{r.randrange(1000, 9999)}"),
    ("unidad",        "enum",  lambda r: r.choice(["u", "kg", "l", "m"]), ["u", "kg", "l", "m"]),
    ("iva_incluido",  "bool",  lambda r: r.choice([True, False])),
    ("costo",         "float", lambda r: round(r.uniform(1, 7000), 2)),
    ("margen_pct",    "float", lambda r: round(r.uniform(2, 70), 1)),
    ("ultimo_conteo", "str",   lambda r: f"2026-{r.randrange(1,13):02d}-{r.randrange(1,29):02d}"),
    ("responsable",   "str",   lambda r: r.choice(["apalma", "epalomino", "jmayta", "rmejia"])),
    ("notas_cod",     "str",   lambda r: f"N{r.randrange(100, 999)}"),
    ("prioridad",     "int",   lambda r: r.randrange(1, 6)),
    ("bloqueado",     "bool",  lambda r: r.choice([True, False])),
    ("canal",         "enum",  lambda r: r.choice(["web", "tienda", "mayor"]), ["web", "tienda", "mayor"]),
    ("region",        "enum",  lambda r: r.choice(["norte", "centro", "sur", "oriente"]), ["norte", "centro", "sur", "oriente"]),
    ("temporada",     "str",   lambda r: r.choice(["verano", "otono", "invierno", "primavera"])),
    ("reposicion",    "int",   lambda r: r.randrange(0, 500)),
    ("codigo_interno", "str",  lambda r: f"IN-{r.randrange(10**5):05d}"),
]


def contrato(w: int) -> Contract:
    """Contrato plano de W campos, tomando los W primeros del repertorio."""
    core = []
    for spec in POOL[:w]:
        nombre, tipo = spec[0], spec[1]
        campo = {"name": nombre, "type": tipo}
        if tipo == "enum":
            campo["values"] = spec[3]
        core.append(campo)
    return Contract.from_dict({
        "prefix": f"w{w}",
        "version": 1,
        "name": f"inventario de {w} campos",
        "records_key": "records",
        "header": {"required": ["n"], "keys": {"n": {"type": "int"}}},
        "core": core,
    })


def documento(w: int, n: int, semilla: int) -> dict:
    r = random.Random(semilla)
    regs = []
    for _ in range(n):
        regs.append({spec[0]: spec[2](r) for spec in POOL[:w]})
    return {"header": {"n": n, "v": 1}, "records": regs}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--anchos", default="3,5,8,12,20,32,50")
    ap.add_argument("--lotes", default="1,10,100,1000")
    ap.add_argument("--tokenizadores", default="o200k_base,cl100k_base,r50k_base")
    ap.add_argument("--repeticiones", type=int, default=5,
                    help="documentos independientes por celda, para dar variabilidad")
    ap.add_argument("--salida", default=None, help="directorio de salida (por defecto experiments/v5_ancho/results)")
    args = ap.parse_args()
    global RESULTS
    if args.salida:
        RESULTS = Path(args.salida)

    anchos = [int(x) for x in args.anchos.split(",")]
    lotes = [int(x) for x in args.lotes.split(",")]
    vocab_local.preparar_cache([n for n in args.tokenizadores.split(",") if n in vocab_local.VOCABULARIOS])
    toks = {nom: get_tokenizer(nom) for nom in args.tokenizadores.split(",")}
    for nom, tk in toks.items():  # un tokenizador que cayera al respaldo no equivale a tiktoken: error, no omisión
        if tk.backend != "tiktoken":
            raise SystemExit(f"tokenizador {nom}: backend {tk.backend!r}, se esperaba tiktoken")
    RESULTS.mkdir(parents=True, exist_ok=True)

    filas = []
    for w in anchos:
        c = contrato(w)
        for n in lotes:
            for rep in range(args.repeticiones):
                doc = documento(w, n, SEMILLA + rep * 1009 + w * 31 + n)
                textos = {}
                for fmt, fn in formats.FORMATS.items():
                    try:
                        textos[fmt] = fn(doc, c)
                    except Exception as exc:              # formato no aplicable
                        print(f"  aviso: {fmt} falló en W={w} N={n}: {exc}", file=sys.stderr)
                for tname, tk in toks.items():
                    cuenta = tk.count if hasattr(tk, "count") else tk
                    base = cuenta(textos["mini"])
                    for fmt, txt in textos.items():
                        t = cuenta(txt)
                        filas.append({
                            "tokenizador": tname, "ancho": w, "lote": n, "rep": rep,
                            "formato": fmt, "tokens": t, "bytes": len(txt.encode("utf-8")),
                            "tokens_mini": base,
                            "ahorro_pct": (t - base) / t * 100 if t else 0.0,
                        })
        print(f"  W={w:>3} listo")

    largo = RESULTS / "ancho_largo.csv"
    with open(largo, "w", newline="", encoding="utf-8") as fh:
        wr = csv.DictWriter(fh, fieldnames=list(filas[0].keys()))
        wr.writeheader()
        wr.writerows(filas)

    # ---- resumen: mediana del ahorro por (tokenizador, formato, ancho, lote)
    res = []
    clave = lambda f: (f["tokenizador"], f["formato"], f["ancho"], f["lote"])
    grupos = {}
    for f in filas:
        grupos.setdefault(clave(f), []).append(f["ahorro_pct"])
    for (tn, fmt, w, n), vals in sorted(grupos.items()):
        res.append({
            "tokenizador": tn, "formato": fmt, "ancho": w, "lote": n,
            "k": len(vals),
            "media": round(statistics.mean(vals), 3),
            "mediana": round(statistics.median(vals), 3),
            "min": round(min(vals), 3), "max": round(max(vals), 3),
        })
    resumen = RESULTS / "ancho_resumen.csv"
    with open(resumen, "w", newline="", encoding="utf-8") as fh:
        wr = csv.DictWriter(fh, fieldnames=list(res[0].keys()))
        wr.writeheader()
        wr.writerows(res)

    meta = {
        "semilla": SEMILLA, "anchos": anchos, "lotes": lotes,
        "tokenizadores": list(toks), "repeticiones": args.repeticiones,
        "datos": "sintéticos deterministas; repertorio POOL en este archivo",
        "nota": "los campos se toman en orden fijo: W=12 es superconjunto de W=8",
    }
    (RESULTS / "meta.json").write_text(json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\n{len(filas)} filas -> {largo}\n{len(res)} filas -> {resumen}")


if __name__ == "__main__":
    main()
