# -*- coding: utf-8 -*-
"""V7 · Escalamiento por lote: cuántos registros caben en una respuesta y qué cuesta cada formato.

Pide a un modelo real convertir N mensajes de clientes en N tickets, con la misma tarea leída de dos
maneras: JSON (con su JSON Schema en la instrucción) y .mini (con el bloque de prompt del contrato).
Barre el tamaño de lote hasta que la respuesta deja de caber en el límite de salida del modelo, que es
el mecanismo por el que un lote grande «sale mal».

Mide por llamada: tokens de entrada y salida informados por el proveedor, motivo de parada, registros
completos recibidos, registros válidos, registros aprovechados sin volver a pedir, y latencia.

    python experiments/v7_escalamiento/correr.py --dry-run
    python experiments/v7_escalamiento/correr.py --proveedor deepseek --confirmar-real --max-costo-usd 1
    python experiments/v7_escalamiento/correr.py --proveedor deepseek --confirmar-real \
           --tamanos 200 --objetivo-registros 20000 --max-costo-usd 4

Las claves se leen solo del entorno (DEEPSEEK_API_KEY, GROQ_API_KEY). Cada llamada se escribe en
llamadas.jsonl en cuanto termina, así que la ejecución se puede reanudar con el mismo comando.
"""
from __future__ import annotations

import argparse
import json
import os
import random
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

AQUI = Path(__file__).resolve().parent
RAIZ = AQUI.parents[1]
sys.path.insert(0, str(RAIZ / "src"))

from minifmt import Contract, from_json_schema, parse, spec_block          # noqa: E402
from minifmt.ai.adapters import get_adapter                                 # noqa: E402
from minifmt.errors import MiniValidationError                              # noqa: E402

ESQUEMA = RAIZ / "examples" / "mesa-de-ayuda" / "ticket.schema.json"
PRECIOS = RAIZ / "experiments" / "v4_costos" / "precios.json"
SEMILLA = 20260917
TAMANOS = [10, 25, 50, 100, 150, 200, 300, 400]

MODELO_POR_DEFECTO = {"deepseek": "deepseek-chat", "groq": "openai/gpt-oss-20b"}
# límite de salida que se pide al proveedor (el máximo publicado del modelo)
MAX_TOKENS = {"deepseek": 8192, "groq": 8192}

# ---------------------------------------------------------------- entrada sintética reproducible
sys.path.insert(0, str(AQUI))
from entrada import ENTRADA_VERSION, combinaciones, mensajes  # noqa: E402


def pedido(lote: List[Dict[str, str]]) -> str:
    return ("Convierte cada mensaje de cliente en un ticket de soporte:\n" +
            "\n".join(f"{m['id']}: {m['mensaje']}" for m in lote))


def instruccion(formato: str, contrato: Contract) -> str:
    if formato == "mini":
        return spec_block(contrato, "es")
    return ('Eres el asistente de una mesa de ayuda. Responde únicamente con un objeto JSON de la forma '
            '{"tickets": [...]}, donde cada ticket cumple este JSON Schema:\n' + ESQUEMA.read_text(encoding="utf-8"))


# ---------------------------------------------------------------- lectura de la respuesta
def objetos_completos(texto: str) -> int:
    prof, en_texto, escape, n = 0, False, False, 0
    for c in texto:
        if escape:
            escape = False
        elif c == "\\":
            escape = True
        elif c == '"':
            en_texto = not en_texto
        elif not en_texto:
            if c == "{":
                prof += 1
            elif c == "}":
                prof -= 1
                if prof == 1:
                    n += 1
    return n


def valida(registro: Dict[str, Any], contrato: Contract) -> bool:
    for f in contrato.core:
        v = registro.get(f.name)
        if v is None or v == "":
            return False
        if f.type == "enum" and v not in (f.values or []):
            return False
        if f.type == "int":
            if not isinstance(v, int) or isinstance(v, bool):
                return False
            if f.min is not None and v < f.min or f.max is not None and v > f.max:
                return False
    return True


def leer(formato: str, texto: str, lote: List[Dict[str, str]], contrato: Contract) -> Dict[str, Any]:
    """Registros completos recibidos, válidos y aprovechables sin volver a pedir nada."""
    ids = {m["id"] for m in lote}
    if formato == "mini":
        completos = sum(1 for l in texto.split("\n")[1:] if l.strip() and len(l.split("|")) >= len(contrato.core))
        try:
            doc = parse(texto, contrato, strict=False)
        except MiniValidationError as e:
            return {"completos": completos, "validos": 0, "aprovechados": 0, "lectura": f"sin documento ({e.errors[0].code})"}
        validos = [r for r in doc.records if valida(r, contrato) and r.get("id") in ids]
        return {"completos": completos, "validos": len(validos), "aprovechados": len(validos),
                "lectura": "ok" if len(validos) == len(lote) else "parcial"}
    completos = objetos_completos(texto)
    try:
        datos = json.loads(texto)
    except json.JSONDecodeError as e:
        return {"completos": completos, "validos": 0, "aprovechados": 0, "lectura": f"json ilegible ({e.msg})"}
    tickets = datos.get("tickets") or []
    validos = [t for t in tickets if isinstance(t, dict) and valida(t, contrato) and t.get("id") in ids]
    if len(validos) != len(tickets):
        # un solo valor fuera del esquema invalida el lote: así lo trata una aplicación con json.loads
        return {"completos": completos, "validos": len(validos), "aprovechados": 0, "lectura": "registro inválido"}
    return {"completos": completos, "validos": len(validos), "aprovechados": len(validos),
            "lectura": "ok" if len(validos) == len(lote) else "parcial"}


# ---------------------------------------------------------------- precios
def precio(proveedor: str, modelo: str) -> Dict[str, Optional[float]]:
    datos = json.loads(PRECIOS.read_text(encoding="utf-8"))
    for m in datos["modelos"]:
        if m["proveedor"].lower().startswith(proveedor[:4]) and (m["id_api"] == modelo or modelo in m["modelo"]):
            return {"entrada": m["entrada"], "salida": m["salida"], "modelo_precio": m["modelo"],
                    "fuente": m["fuente_url"], "fecha": m["fecha_consulta"]}
    # sin precio publicado para ese id: se usa el más barato del proveedor como referencia declarada
    del_prov = [m for m in datos["modelos"] if m["proveedor"].lower().startswith(proveedor[:4]) and m["salida"]]
    if del_prov:
        m = min(del_prov, key=lambda x: x["salida"])
        return {"entrada": m["entrada"], "salida": m["salida"], "modelo_precio": m["modelo"] + " (referencia)",
                "fuente": m["fuente_url"], "fecha": m["fecha_consulta"]}
    return {"entrada": None, "salida": None, "modelo_precio": None, "fuente": None, "fecha": None}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--proveedor", default="deepseek", choices=sorted(MODELO_POR_DEFECTO))
    ap.add_argument("--modelo", default=None)
    ap.add_argument("--tamanos", default=",".join(str(t) for t in TAMANOS),
                    help="registros por llamada, separados por coma")
    ap.add_argument("--repeticiones", type=int, default=3)
    ap.add_argument("--objetivo-registros", type=int, default=0,
                    help="registros por formato: repite lotes del tamaño indicado hasta alcanzarlo")
    ap.add_argument("--formatos", default="mini,json")
    ap.add_argument("--paralelo", type=int, default=4)
    ap.add_argument("--max-costo-usd", type=float, default=1.0)
    ap.add_argument("--confirmar-real", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--semilla", type=int, default=SEMILLA)
    ap.add_argument("--salida", default=None)
    a = ap.parse_args()

    modelo = a.modelo or MODELO_POR_DEFECTO[a.proveedor]
    tamanos = [int(x) for x in a.tamanos.split(",") if x.strip()]
    formatos = [f.strip() for f in a.formatos.split(",") if f.strip()]
    contrato = from_json_schema(json.loads(ESQUEMA.read_text(encoding="utf-8")), "tk")
    pr = precio(a.proveedor, modelo)
    salida = Path(a.salida) if a.salida else AQUI / "results" / f"{a.proveedor}"
    salida.mkdir(parents=True, exist_ok=True)
    archivo = salida / "llamadas.jsonl"

    # ---------------------------------------------------------- matriz de llamadas
    plan: List[Dict[str, Any]] = []
    desde = 1
    for formato in formatos:
        for t in tamanos:
            reps = a.repeticiones if not a.objetivo_registros else max(1, -(-a.objetivo_registros // t))
            for rep in range(1, reps + 1):
                plan.append({"id": f"{formato}/L{t}/r{rep}", "formato": formato, "lote": t, "rep": rep,
                             "desde": desde})
                desde += t

    hechos = set()
    if archivo.exists():
        for linea in archivo.read_text(encoding="utf-8").splitlines():
            try:
                hechos.add(json.loads(linea)["id"])
            except Exception:
                pass
    pendientes = [p for p in plan if p["id"] not in hechos]

    # tokens por registro observados en las mediciones previas, solo para estimar
    POR_REG = {"mini": 25, "json": 62}
    ENTRADA_POR_REG = 26
    est_salida = sum(p["lote"] * POR_REG[p["formato"]] for p in pendientes)
    est_entrada = sum(p["lote"] * ENTRADA_POR_REG + 700 for p in pendientes)
    costo = ((est_entrada / 1e6) * (pr["entrada"] or 0)) + ((est_salida / 1e6) * (pr["salida"] or 0))
    registros = sum(p["lote"] for p in pendientes)

    print(f"proveedor {a.proveedor} · modelo {modelo} · precios de {pr['modelo_precio']} "
          f"({pr['entrada']} entrada / {pr['salida']} salida USD por 1M, {pr['fecha']})")
    print(f"llamadas pendientes {len(pendientes)} de {len(plan)} · registros {registros:,} · "
          f"tokens estimados {est_entrada:,} entrada + {est_salida:,} salida")
    print(f"costo estimado {costo:.2f} USD · tope {a.max_costo_usd} USD")
    if a.dry_run:
        print("(dry-run: no se llamó a nada)")
        return 0
    if not a.confirmar_real:
        print("falta --confirmar-real: no se llama a ningún proveedor", file=sys.stderr)
        return 2
    if costo > a.max_costo_usd:
        print(f"abortado: el costo estimado supera el tope", file=sys.stderr)
        return 2
    if not os.environ.get({"deepseek": "DEEPSEEK_API_KEY", "groq": "GROQ_API_KEY"}[a.proveedor]):
        print("falta la clave del proveedor en el entorno", file=sys.stderr)
        return 2

    adaptador = get_adapter(a.proveedor, modelo)
    candado = threading.Lock()
    gastado = {"usd": 0.0}
    detener = threading.Event()

    def una(p: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        if detener.is_set():
            return None
        lote = mensajes(p["lote"], p["desde"], a.semilla)
        sistema = instruccion(p["formato"], contrato)
        t0 = time.time()
        try:
            r = adaptador.generate(sistema, pedido(lote), max_tokens=MAX_TOKENS[a.proveedor], temperature=0)
        except Exception as e:                                    # noqa: BLE001 - se registra y sigue
            return {**p, "error": f"{type(e).__name__}: {str(e)[:200]}", "ms": round((time.time() - t0) * 1000)}
        lectura = leer(p["formato"], r["text"], lote, contrato)
        fila = {**p, "modelo": modelo, "proveedor": a.proveedor,
                "solicitados": p["lote"], "tokens_entrada": r.get("input_tokens"), "tokens_salida": r.get("output_tokens"),
                "motivo_parada": r.get("stop_reason"), "ms": round((time.time() - t0) * 1000),
                "caracteres": len(r["text"]), **lectura}
        usd = ((fila["tokens_entrada"] or 0) / 1e6) * (pr["entrada"] or 0) + \
              ((fila["tokens_salida"] or 0) / 1e6) * (pr["salida"] or 0)
        with candado:
            gastado["usd"] += usd
            if gastado["usd"] > a.max_costo_usd:
                detener.set()
        fila["usd"] = round(usd, 6)
        return fila

    inicio = datetime.now(timezone.utc)
    escritas = 0
    with archivo.open("a", encoding="utf-8") as fh, ThreadPoolExecutor(max_workers=a.paralelo) as pool:
        futuros = {pool.submit(una, p): p for p in pendientes}
        for fut in as_completed(futuros):
            fila = fut.result()
            if fila is None:
                continue
            fh.write(json.dumps(fila, ensure_ascii=False) + "\n")
            fh.flush()
            os.fsync(fh.fileno())
            escritas += 1
            estado = fila.get("error") or f"{fila['aprovechados']}/{fila['solicitados']} · {fila['tokens_salida']} tok · {fila['motivo_parada']}"
            print(f"  [{escritas}/{len(pendientes)}] {fila['id']:22} {estado}")
    (salida / "meta.json").write_text(json.dumps({
        "experimento": "v7_escalamiento", "proveedor": a.proveedor, "modelo": modelo,
        "precios": pr, "tamanos": tamanos, "formatos": formatos, "semilla": a.semilla,
        "max_tokens": MAX_TOKENS[a.proveedor], "temperatura": 0,
        "entrada": ENTRADA_VERSION, "combinaciones_entrada": combinaciones(),
        "inicio": inicio.isoformat(timespec="seconds"), "fin": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "llamadas": escritas, "usd_gastado": round(gastado["usd"], 4),
        "detenido_por_presupuesto": detener.is_set(),
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"\n{escritas} llamadas · {gastado['usd']:.4f} USD · resultados en {archivo}")
    return 3 if detener.is_set() else 0


if __name__ == "__main__":
    raise SystemExit(main())
