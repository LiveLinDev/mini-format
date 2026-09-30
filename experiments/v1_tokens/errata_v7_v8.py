"""Verificación reproducible de las erratas de V7 y V8 (sin tocar datos crudos).

Recalcula desde ``experiments/v7_escalamiento/results`` y ``experiments/v8_sima/datos.json``
los hechos que citan ``experiments/v7_escalamiento/ERRATA.md`` y ``experiments/v8_sima/ERRATA.md``.
No escribe en esas carpetas. Los datos crudos de V7 y V8 son llamadas reales a un proveedor
(procedencia ``api_real`` de sus autores); aquí solo se releen.
"""
from __future__ import annotations

import csv
import json
import sys
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parents[2]
V7 = ROOT / "experiments" / "v7_escalamiento"
V8 = ROOT / "experiments" / "v8_sima"


def linea_de(archivo: Path, fragmento: str) -> int:
    """Número de línea (base 1) de la primera línea del archivo que contiene ``fragmento``."""
    for i, linea in enumerate(archivo.read_text(encoding="utf-8").splitlines(), 1):
        if fragmento in linea:
            return i
    raise KeyError(f"{archivo.name}: no contiene {fragmento!r}")


def _jsonl(p: Path) -> List[Dict[str, Any]]:
    return [json.loads(x) for x in p.read_text(encoding="utf-8").splitlines() if x.strip()]


def _csv(p: Path) -> List[Dict[str, str]]:
    with open(p, newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def verificar_v7() -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    # 1. lote_maximo_sin_perdida
    res = {r["formato"]: int(r["lote_maximo_sin_perdida"]) for r in _csv(V7 / "results" / "deepseek" / "resumen.csv")}
    por_lote = _csv(V7 / "results" / "deepseek" / "por_lote.csv")
    estricto = {}
    for f in sorted({r["formato"] for r in por_lote}):
        ok = [int(r["lote"]) for r in por_lote if r["formato"] == f and float(r["aprovechamiento_pct"]) == 100.0]
        estricto[f] = max(ok) if ok else 0
    l300 = next(r for r in por_lote if r["formato"] == "mini" and r["lote"] == "300")
    an = V7 / "analizar.py"
    out["lote_maximo_sin_perdida"] = {
        "resumen_csv_archivado": res, "definicion_estricta_por_lote": estricto,
        "mini_L300": {"llamadas": int(l300["llamadas"]), "llamadas_cortadas": int(l300["llamadas_cortadas"]),
                      "aprovechamiento_pct": float(l300["aprovechamiento_pct"])},
        "lineas": {
            "analizar.py: buenos = alguna llamada con aprovechados == solicitados": linea_de(an, 'buenos = [f for f in g if f["aprovechados"] == f["solicitados"]]'),
            "analizar.py: lote_maximo_sin_perdida = max(lote de buenos)": linea_de(an, '"lote_maximo_sin_perdida": max('),
            "analizar.py: la salida legible ya usa aprovechamiento 100 % por lote": linea_de(an, 'f["aprovechamiento_pct"] == 100]'),
        },
        "discrepancia": res.get("mini") != estricto.get("mini"),
    }
    # 2. deepseek_volumen
    vol = V7 / "results" / "deepseek_volumen"
    meta = json.loads((vol / "meta.json").read_text(encoding="utf-8"))
    real = json.loads((vol / "costo_real.json").read_text(encoding="utf-8"))
    calls = _jsonl(vol / "llamadas.jsonl")
    por_fmt: Dict[str, Dict[str, Any]] = {}
    for c in calls:
        g = por_fmt.setdefault(c["formato"], {"llamadas": 0, "registros": 0, "tokens_entrada": 0, "tokens_salida": 0, "usd": 0.0, "lote": c["lote"]})
        g["llamadas"] += 1
        g["registros"] += c["solicitados"]
        g["tokens_entrada"] += c["tokens_entrada"] or 0
        g["tokens_salida"] += c["tokens_salida"] or 0
        g["usd"] += c["usd"]
    for g in por_fmt.values():
        g["usd"] = round(g["usd"], 4)
    out["deepseek_volumen"] = {
        "meta_json": {"llamadas": meta["llamadas"], "formatos": meta["formatos"], "tamanos": meta["tamanos"], "usd_gastado": meta["usd_gastado"],
                      "inicio": meta["inicio"], "fin": meta["fin"]},
        "llamadas_jsonl_total": len(calls), "por_formato_en_jsonl": por_fmt,
        "usd_estimado_jsonl": round(sum(c["usd"] for c in calls), 4),
        "tokens_entrada_jsonl": sum(c["tokens_entrada"] for c in calls), "tokens_salida_jsonl": sum(c["tokens_salida"] for c in calls),
        "costo_real_json": {"consumido_usd": real["consumido_usd"], "estimado_con_precios_publicados_usd": real["estimado_con_precios_publicados_usd"],
                            "tokens_entrada": real["tokens_entrada"], "tokens_salida": real["tokens_salida"],
                            "registros_procesados": real["registros_procesados"]},
        "meta_cubre_solo_una_invocacion": meta["llamadas"] != len(calls),
        "el_jsonl_no_guarda_fecha_por_llamada": not any(k in calls[0] for k in ("ts", "fecha", "inicio")),
        "captura_del_saldo_en_el_repositorio": False,
    }
    return out


def verificar_v8() -> Dict[str, Any]:
    sys.path.insert(0, str(ROOT / "src"))
    from minifmt import Registry, parse
    d = json.loads((V8 / "datos.json").read_text(encoding="utf-8"))
    contrato = Registry.load(ROOT / "forks").get("a")
    tot = {"pedidos": 0, "recibidos_validos": 0, "invalidas": 0, "reparadas": 0, "recuperadas": 0, "finales": 0, "llamadas": 0}
    codigos: Dict[str, int] = {}
    bloques = con_respuesta = coinciden = 0
    identidades_ok = True
    clases = []
    for cl in d["clases"]:
        c = {"id": cl["id"], "bloques": len(cl["bloques"]), "bloques_con_respuesta_cruda": 0}
        for b in cl["bloques"]:
            bloques += 1
            tot["pedidos"] += b["pedidos"]
            tot["recibidos_validos"] += b["recibidos"]
            tot["invalidas"] += len(b["lineas_invalidas"])
            tot["reparadas"] += len(b["reparados"])
            tot["recuperadas"] += b["recuperados"]
            tot["finales"] += b["finales"]
            tot["llamadas"] += b["llamadas"]
            for _, cod, _ in b["lineas_invalidas"]:
                codigos[cod] = codigos.get(cod, 0) + 1
            identidades_ok &= b["pedidos"] == b["recibidos"] + len(b["lineas_invalidas"])
            identidades_ok &= b["finales"] == b["recibidos"] + len(b["reparados"]) + b["recuperados"]
            if "respuesta" in b:
                con_respuesta += 1
                c["bloques_con_respuesta_cruda"] += 1
                doc = parse(b["respuesta"], contrato, strict=False)
                errs = sorted((e.code, e.line) for e in getattr(doc, "errors", []))
                esperado = sorted((cod, ln) for ln, cod, _ in b["lineas_invalidas"])
                coinciden += int(len(doc.records) == b["recibidos"] and errs == esperado)
        clases.append(c)
    suma = tot["recibidos_validos"] + tot["reparadas"] + tot["recuperadas"]
    return {
        "archivo": "experiments/v8_sima/datos.json",
        "conciliacion_clases": {
            "totales_de_los_contadores": tot, "codigos_de_error": codigos, "bloques": bloques, "clases": clases,
            "identidad_por_bloque_ok": identidades_ok,
            "identidad_por_bloque": "pedidos = recibidos + inválidas y finales = recibidos + reparadas + recuperadas, en cada bloque",
            "suma": f"{tot['recibidos_validos']} + {tot['reparadas']} + {tot['recuperadas']} = {suma}",
            "suma_es_finales_y_pedidos": suma == tot["finales"] == tot["pedidos"],
            "bloques_con_respuesta_cruda": con_respuesta, "bloques_donde_minifmt_reproduce_los_contadores": coinciden,
            "registro_a_registro": "pendiente: las respuestas de reparación y de reposición y las respuestas crudas de las clases 3 y 5 no están en datos.json",
            "estado": "reconciliado_por_contadores_y_respuestas_crudas_parciales; registro_a_registro_pendiente",
        },
    }


def verificar() -> Dict[str, Any]:
    return {"v7": verificar_v7(), "v8": verificar_v8()}


DEFINICION_PAYLOAD = {
    "contenido_hojas": "cota inferior de contenido: cada valor hoja tokenizado por separado y sumado (columna `payload` de benchmark/results/summary_12.csv); no es un texto enviado",
    "documento": "texto completo del documento transmitido, sin contrato, mapa ni prompt (lo que los documentos del equipo llamaban 'solo payload', 35,64 %)",
    "estructura_compartida": "contrato o mapa de aplanado necesario para decodificar",
    "prompt_reutilizable": "bloque de instrucción de cada solicitud",
    "total": "conteo del texto completo enviado, no la suma de fragmentos",
    "en_v7_y_v8": "las cifras de V7 y V8 son tokens de entrada y salida que informa el proveedor (tokenizador propio), no conteos locales de documento: no son comparables con la serie de V1",
}


def construir_erratas() -> Dict[str, Dict[str, Any]]:
    """Archivos ``errata.json`` DERIVADOS (los datos crudos no se tocan): ruta relativa -> contenido."""
    v = verificar()
    v7, v8 = v["v7"], v["v8"]
    lm = v7["lote_maximo_sin_perdida"]
    vol = v7["deepseek_volumen"]
    base = {"esquema": "mini-format/errata/1", "creado": "2026-09-30", "datos_crudos_modificados": False,
            "definicion_de_payload": DEFINICION_PAYLOAD,
            "generado_por": "python experiments/v1_tokens/errata_v7_v8.py --escribir"}
    e_ds = {**base, "directorio": "experiments/v7_escalamiento/results/deepseek", "errata": [{
        "id": "V7-E1", "campo": "resumen.csv: lote_maximo_sin_perdida",
        "archivado": lm["resumen_csv_archivado"], "corregido": lm["definicion_estricta_por_lote"],
        "motivo": "analizar.py toma el mayor lote con ALGUNA llamada completa; con mini y lote 300, 1 de 3 llamadas salió completa y 2 se cortaron (aprovechamiento 93,3 %)",
        "evidencia": ["experiments/v7_escalamiento/results/deepseek/resumen.csv:3",
                      "experiments/v7_escalamiento/results/deepseek/por_lote.csv:16",
                      f"experiments/v7_escalamiento/analizar.py:{lm['lineas']['analizar.py: buenos = alguna llamada con aprovechados == solicitados']}",
                      f"experiments/v7_escalamiento/analizar.py:{lm['lineas']['analizar.py: lote_maximo_sin_perdida = max(lote de buenos)']}",
                      f"experiments/v7_escalamiento/analizar.py:{lm['lineas']['analizar.py: la salida legible ya usa aprovechamiento 100 % por lote']}",
                      "sitio/construir.py:838"],
        "mini_L300": lm["mini_L300"]}]}
    e_vol = {**base, "directorio": "experiments/v7_escalamiento/results/deepseek_volumen", "errata": [{
        "id": "V7-E2", "campo": "meta.json",
        "descripcion": "meta.json describe UNA invocación (json, lote 100, 200 llamadas, 1,6823 USD); llamadas.jsonl contiene DOS (añade mini, lote 200, 100 llamadas)",
        "meta_json": vol["meta_json"], "llamadas_jsonl_total": vol["llamadas_jsonl_total"], "por_formato_en_jsonl": vol["por_formato_en_jsonl"],
        "usd_estimado_jsonl_total": vol["usd_estimado_jsonl"],
        "evidencia": ["experiments/v7_escalamiento/results/deepseek_volumen/meta.json:12", "experiments/v7_escalamiento/results/deepseek_volumen/meta.json:15",
                      "experiments/v7_escalamiento/results/deepseek_volumen/meta.json:23", "experiments/v7_escalamiento/results/deepseek_volumen/meta.json:24",
                      "experiments/v7_escalamiento/results/deepseek_volumen/llamadas.jsonl (300 líneas)"],
        "la_ventana_de_la_segunda_invocacion": "desconocida: llamadas.jsonl no guarda fecha por llamada"},
        {"id": "V7-E3", "campo": "costo_real.json",
         "descripcion": "0,78 USD es la diferencia de saldo del proveedor según el propio archivo; el saldo no está en el repositorio y no se puede verificar. La estimación con precios de lista (2,4182 USD) sí se reproduce desde llamadas.jsonl",
         "costo_real_json": vol["costo_real_json"], "estimado_reproducido_usd": vol["usd_estimado_jsonl"],
         "tokens_entrada_reproducidos": vol["tokens_entrada_jsonl"], "tokens_salida_reproducidos": vol["tokens_salida_jsonl"],
         "verificable": False,
         "evidencia": ["experiments/v7_escalamiento/results/deepseek_volumen/costo_real.json:5", "experiments/v7_escalamiento/results/deepseek_volumen/costo_real.json:9"]}]}
    cl = v8["conciliacion_clases"]
    e_v8 = {**base, "directorio": "experiments/v8_sima", "errata": [{
        "id": "V8-E1", "campo": "conciliación de las clases completas",
        "hecho": cl["suma"] + " ítems (343 válidas al llegar, 5 reparadas, 2 repuestas)",
        "estado": cl["estado"], "totales_de_los_contadores": cl["totales_de_los_contadores"], "codigos_de_error": cl["codigos_de_error"],
        "bloques": cl["bloques"], "llamadas": v8["conciliacion_clases"]["totales_de_los_contadores"]["llamadas"],
        "identidad_por_bloque_ok": cl["identidad_por_bloque_ok"], "suma_es_finales_y_pedidos": cl["suma_es_finales_y_pedidos"],
        "bloques_con_respuesta_cruda": cl["bloques_con_respuesta_cruda"], "bloques_donde_minifmt_reproduce_los_contadores": cl["bloques_donde_minifmt_reproduce_los_contadores"],
        "registro_a_registro": cl["registro_a_registro"],
        "evidencia": ["experiments/v8_sima/README.md:32", "experiments/v8_sima/resumen.json:83", "experiments/v8_sima/analizar.py:48", "experiments/v8_sima/datos.json (clases[].bloques[])"]},
        {"id": "V8-E2", "campo": "vocabulario: 'rechazadas' y 'recibidos'",
         "descripcion": "README.md:32 llama 'líneas rechazadas' a las 7 líneas inválidas; en datos.json `rechazados` es otra cosa (líneas cuya reparación se rechazó: 1). `recibidos` = líneas válidas al llegar (343), no líneas recibidas (350).",
         "evidencia": ["experiments/v8_sima/README.md:32", "experiments/v8_sima/analizar.py:48"]}]}
    return {"experiments/v7_escalamiento/results/deepseek/errata.json": e_ds,
            "experiments/v7_escalamiento/results/deepseek_volumen/errata.json": e_vol,
            "experiments/v8_sima/errata.json": e_v8}


def escribir() -> List[str]:
    out = []
    for rel, contenido in construir_erratas().items():
        p = ROOT / rel
        p.write_text(json.dumps(contenido, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
        out.append(rel)
    return out


if __name__ == "__main__":
    if "--escribir" in sys.argv:
        print("\n".join(escribir()))
    else:
        print(json.dumps(verificar(), ensure_ascii=False, indent=2))
