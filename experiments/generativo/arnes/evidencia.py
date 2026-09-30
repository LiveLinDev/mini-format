"""Emisión de las corridas V2, V3b y V4 con ``tools/evidencia_lib`` (contrato ``mini-format/corrida/1``).

Regla: toda cifra del manifiesto sale de los archivos de resultados YA escritos y validados (se relee el CSV del
análisis); nada se teclea a mano.  Una corrida simulada o asistida por IA es siempre ``no_evaluable``.  Sin tarifa
verificada el costo queda como «tarifa no verificada» (vacío), nunca como un precio supuesto.
"""
from __future__ import annotations

import csv
import json
import shutil
import sys
from decimal import Decimal
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

RAIZ = Path(__file__).resolve().parents[3]
if str(RAIZ / "tools") not in sys.path:
    sys.path.insert(0, str(RAIZ / "tools"))
import evidencia_lib as EV  # noqa: E402

from .ejecucion import leer_muestras  # noqa: E402

ESTUDIOS = ("V2", "V3b", "V4")


def _csv(ruta: Path) -> List[Dict[str, str]]:
    if not ruta.exists():
        return []
    with open(ruta, newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def _num(x: Any) -> Optional[float]:
    try:
        return float(x) if x not in (None, "") else None
    except ValueError:
        return None


def _filtrar_csv(origen: Path, destino: Path, experimento: str) -> int:
    filas = [f for f in _csv(origen) if f.get("experimento") == experimento]
    if not filas:
        return 0
    with open(destino, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(filas[0].keys()))
        w.writeheader()
        w.writerows(filas)
    return len(filas)


def _filtrar_jsonl(origen: Path, destino: Path, experimento: str) -> int:
    n = 0
    with open(origen, encoding="utf-8") as fh, open(destino, "w", encoding="utf-8", newline="\n") as out:
        for linea in fh:
            if json.loads(linea).get("experimento") == experimento:
                out.write(linea.rstrip("\r\n") + "\n")
                n += 1
    return n


def _tokenizadores() -> List[Dict[str, Any]]:
    vocab = RAIZ / "benchmark" / "vocab" / "o200k_base.tiktoken"
    return [{"nombre": "o200k_base", "paquete": "tiktoken", "version": EV._version_paquete("tiktoken"),
             "vocabulario_sha256": EV.sha256_archivo(vocab) if vocab.exists() else None, "tipo": "aproximacion"}]


def _conjuntos_y_contratos(man: Dict[str, Any]) -> Dict[str, Any]:
    h = man.get("hashes") or {}
    return {"conjuntos": [dict(c) for c in h.get("conjuntos", [])], "contratos": [dict(c) for c in h.get("contratos", [])]}


def _conteos(muestras: List[Dict[str, Any]], experimento: str) -> Dict[str, Any]:
    prim = [s for s in muestras if s["experimento"] == experimento and not s["brazo"].endswith("+1")]
    sol = sum(s["metricas"].get("solicitados", 0) for s in prim)
    return {"registros_solicitados": sol or None,
            "registros_recibidos": sum(s["metricas"].get("aceptados", 0) for s in prim) if prim else None,
            "registros_validos": sum(s["metricas"].get("validos_contrato", 0) for s in prim) if prim else None,
            "registros_reparados": None, "registros_validos_finales": None}


def emitir_corridas(res_dir: Path, *, procedencia: str, comando: str, etiqueta: str, codigo: Optional[Dict[str, Any]] = None,
                    estudios: Sequence[str] = ESTUDIOS, directorio_corridas: Optional[Path] = None,
                    tarifas_info: Optional[Dict[str, Any]] = None) -> List[Path]:
    """Escribe ``evidencia/corridas/<estudio>-<etiqueta>/`` para cada estudio con datos en ``res_dir``."""
    res_dir = Path(res_dir)
    an = res_dir / "analisis"
    man = json.loads((res_dir / "manifiesto.json").read_text(encoding="utf-8"))
    muestras = leer_muestras(res_dir / "muestras.jsonl")
    estado = json.loads((res_dir / "estado_estudio.json").read_text(encoding="utf-8")) if (res_dir / "estado_estudio.json").exists() else {}
    base_dir = Path(directorio_corridas) if directorio_corridas else EV.directorio_corridas()
    cfg = man.get("config") or {}
    salidas: List[Path] = []
    meta_v2 = json.loads((an / "meta_v2.json").read_text(encoding="utf-8")) if (an / "meta_v2.json").exists() else None
    v2_dir: Optional[Path] = None
    for est in estudios:
        exp = "v2" if est in ("V2", "V4") else "v3b"
        if not any(s["experimento"] == exp for s in muestras):
            continue
        run_id = EV.nuevo_run_id(est, etiqueta)
        d = base_dir / run_id
        d.mkdir(parents=True, exist_ok=True)
        archivos: List[Path] = []
        if est == "V2":
            for nombre in ("resumen_brazos.csv", "resumen_brazo_modelo.csv", "comparaciones_pareadas.csv", "reparacion.csv",
                           "desenlaces.csv"):
                if (an / nombre).exists() and _filtrar_csv(an / nombre, d / nombre, "v2"):
                    archivos.append(d / nombre)
            _filtrar_jsonl(an / "solicitudes.jsonl", d / "solicitudes.jsonl", "v2")
            archivos.append(d / "solicitudes.jsonl")
            if meta_v2 is not None:
                shutil.copyfile(an / "meta_v2.json", d / "meta_v2.json")
                archivos.append(d / "meta_v2.json")
            v2_dir = d
        elif est == "V3b":
            for nombre in ("resumen_brazos.csv", "resumen_brazo_modelo.csv", "reparacion.csv", "desenlaces.csv"):
                if (an / nombre).exists() and _filtrar_csv(an / nombre, d / f"v3b_{nombre}", "v3b"):
                    archivos.append(d / f"v3b_{nombre}")
            with open(d / "v3b_muestras.jsonl", "w", encoding="utf-8", newline="\n") as fh:
                for s in muestras:
                    if s["experimento"] == "v3b":
                        v = s.get("v3b") or {}
                        fh.write(json.dumps({"id": s["id"], "brazo": s["brazo"], "tarea": s["tarea"], "modelo": f"{s['proveedor']}:{s['modelo']}",
                                             "limite_salida": v.get("limite_salida"), "stop_reason": v.get("stop_reason"),
                                             "truncada": v.get("truncada"), "usage": v.get("usage"), "desenlace": s.get("desenlace"),
                                             "validos_finales": s["metricas"].get("validos_finales"),
                                             "solicitados": s["metricas"].get("solicitados")}, ensure_ascii=False, sort_keys=True) + "\n")
            archivos.append(d / "v3b_muestras.jsonl")
            _filtrar_jsonl(an / "solicitudes.jsonl", d / "v3b_solicitudes.jsonl", "v3b")
            archivos.append(d / "v3b_solicitudes.jsonl")
        else:  # V4
            nombre = "latencia_costo.csv"
            if (an / nombre).exists() and _filtrar_csv(an / nombre, d / nombre, "v2"):
                archivos.append(d / nombre)
        if not archivos:
            shutil.rmtree(d, ignore_errors=True)
            continue
        simul = procedencia == "simulado"
        limit = [
            ("Procedencia api_real: usage y latencia vienen del proveedor; la decisión cumple/no_cumple de la meta queda para quien "
             "analiza (meta_v2.json), el arnés no la declara." if procedencia == "api_real" else
             "Procedencia " + procedencia + ": " + ("las tasas de falla, los tokens y las latencias son supuestos del simulador; "
                                                   "valida el arnés, no dice nada de modelos reales." if simul else
                                                   "respuestas de una IA en sesión, sin usage ni factura de API; los tokens locales son una aproximación.")),
            "Costo: sin tarifa verificada es «tarifa no verificada» (vacío); no se usa ningún precio supuesto.",
            "El diseño completo del estudio NO se ha ejecutado ni está autorizado (presupuesto sin autorizar).",
        ]
        if est == "V3b":
            limit.append("Política y fracción del límite de salida PROVISIONALES: se fijan con el piloto real. Es distinto de V3a "
                         "(cortar un texto existente), que vive en experiments/truncamiento.")
        if est == "V4":
            limit.append("Latencia: " + ("sintética (marcada como simulada)" if simul else "no medida") + "; la mediana y el p95 "
                         "solo sirven para verificar el cálculo. Condiciones de red y concurrencia: " +
                         ("simuladas; concurrencia 1." if simul else "no registradas."))
        m = EV.nueva_corrida(est, procedencia, comando, run_id=run_id, **({"codigo": codigo} if codigo else {}))
        m.update(_conjuntos_y_contratos(man))
        m["tokenizadores"] = _tokenizadores()
        m["modelo"] = None
        gasto = 0.0
        ejecucion = "ejecutado"
        if procedencia == "api_real":
            provs = sorted({x["proveedor"] for x in cfg.get("modelos", [])})
            mods = sorted({x["modelo"] for x in cfg.get("modelos", [])})
            devueltos = sorted({s["respuesta"].get("model") for s in muestras if s.get("respuesta") and s["respuesta"].get("model")})
            m["modelo"] = {"proveedor": ", ".join(provs), "modelo_pedido": ", ".join(mods),
                           "modelo_devuelto": ", ".join(devueltos) or None, "endpoint": None}
            g = estado.get("gasto") or {}
            # gasto real = lo facturado según el usage + el peor caso de las llamadas inciertas (cota superior)
            gasto = float(Decimal(str(g.get("gastado_usd") or 0)) + Decimal(str(g.get("incierto_usd") or 0)))
            ejecucion = "ejecutado" if estado.get("estado") == "completo" else "parcial"
        m["parametros"] = {"adaptador": man.get("adaptador"), "semilla": cfg.get("semilla"), "idioma": cfg.get("idioma"),
                           "temperatura": cfg.get("temperatura"), "repeticiones": cfg.get("repeticiones"),
                           "brazos": cfg.get("brazos"), "modelos": [f"{x.get('proveedor')}:{x.get('modelo')}" for x in cfg.get("modelos", [])],
                           "orden_semilla": estado.get("orden_semilla"), "experimento": exp,
                           "v3b": (cfg.get("experimentos") or {}).get("v3b") if est == "V3b" else None}
        m["prompts"] = [{"id": k, "sha256": v} for k, v in sorted(((man.get("hashes") or {}).get("prompts") or {}).items())]
        m["tarifas"] = tarifas_info
        m["conteos"] = _conteos(muestras, exp)
        filas_brazo = _csv(an / "resumen_brazos.csv")
        resumen: Dict[str, Any] = {"muestras": sum(1 for s in muestras if s["experimento"] == exp),
                                   "celdas": estado.get("celdas"),
                                   "validez_final_pct_por_brazo_y_tipo": {
                                       f"{f['tipo_tarea']}/{f['brazo']}": _num(f.get("validez_final_pct"))
                                       for f in filas_brazo if f["experimento"] == exp}}
        if est == "V4":
            resumen = {"latencia_flujo_mediana_s_por_brazo_y_modelo": {
                f"{f['brazo']}|{f['modelo_completo']}": {"mediana_s": _num(f["latencia_flujo_mediana_s"]), "p95_s": _num(f["latencia_flujo_p95_s"]),
                                                          "n": _num(f["latencia_n"]), "costo_por_1000_validos_usd": _num(f["costo_por_1000_validos_usd"])}
                for f in _csv(d / "latencia_costo.csv")}, "origen_latencia": "simulada" if simul else "medida"}
        m["resumen"] = resumen
        m["criterio"] = ({"meta": meta_v2["criterio"], "resultado_del_criterio": meta_v2["resultado"], "motivo": meta_v2["motivo"]}
                         if (est == "V2" and meta_v2) else None)
        m["estado_ejecucion"] = ejecucion
        m["resultado"] = "no_evaluable"      # cumple/no_cumple lo decide quien analiza con meta_v2.json; el arnés nunca lo declara solo
        m["limitaciones"] = limit
        m["gasto_usd"] = gasto
        m["notas"] = ("registros_validos_finales queda null: depende del brazo (ver resumen_brazos.csv) y no se puede sumar entre "
                      "brazos sin contar dos veces una solicitud y su reparación. " +
                      ("V4 reutiliza solicitudes.jsonl de la corrida V2 (mismas solicitudes)." if est == "V4" and v2_dir else ""))
        EV.guardar_corrida(m, archivos, d)
        salidas.append(d / "manifiesto.json")
    return salidas
