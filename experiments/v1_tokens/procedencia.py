"""Procedencia de los datos de V1: fuente, licencia, fecha de captura, hash y carácter sintético.

* Los 14 dominios (``benchmark/domains.py``) son conjuntos ESCRITOS A MANO por los autores
  (sintéticos): 12 registros base por dominio, 168 en total; ``q`` amplía a ``a`` con tres campos
  sobre los mismos 12 ítems. Para n > 12 esos 12 registros se REPITEN con identificadores
  nuevos (``replicacion_de_base``): no son muestras independientes.
* Los 4 snapshots públicos (``benchmark/public/data``) son datos archivados con SHA-256 en
  ``sources.json``: DummyJSON y JSONPlaceholder son datos de prueba sintéticos (MIT);
  USGS son observaciones reales (crédito USGS). Licencias: ``benchmark/public/THIRD_PARTY.md``.
* La muestra independiente de V1 son los 1.902 objetos públicos únicos y los 12 registros base
  de cada dominio, no las series de replicación.
"""
from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
from typing import Any, Dict, List

import comun as C
import domains

ROOT = C.ROOT
LICENCIAS_PUBLICAS = {
    "products": "MIT (DummyJSON, Muhammad Ovi); ver benchmark/public/THIRD_PARTY.md",
    "users": "MIT (DummyJSON, Muhammad Ovi); identidades y credenciales ficticias; ver benchmark/public/THIRD_PARTY.md",
    "comments": "MIT (JSONPlaceholder, typicode); ver benchmark/public/THIRD_PARTY.md",
    "earthquakes": "Crédito U.S. Geological Survey (política de copyright y crédito de USGS); ver benchmark/public/THIRD_PARTY.md",
}


def _sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def _sin_ids(rec: Dict[str, Any], claves: List[str]) -> str:
    r = {k: v for k, v in rec.items() if k not in claves}
    return json.dumps(r, sort_keys=True, ensure_ascii=False)


def dominios_info(n_replica: int = 100) -> Dict[str, Any]:
    """Hash del contenido base, registros únicos y réplica a ``n_replica`` de cada dominio."""
    base = {p: {"header": b["header"], "records": b["records"]} for p, b in domains.BASE.items()}
    sha_contenido = hashlib.sha256(json.dumps(base, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()
    por_dominio = {}
    for p, b in domains.BASE.items():
        ids = C.claves_id(p)
        unicos_base = len({_sin_ids(r, ids) for r in b["records"]})
        doc = C.generar(p, n_replica, "muestreo")
        distintos = len({_sin_ids(r, ids) for r in doc[b["records_key"]]})
        por_dominio[p] = {"registros_base": len(b["records"]), "registros_base_distintos_sin_id": unicos_base,
                          f"n{n_replica}_registros": n_replica, f"n{n_replica}_contenidos_distintos_sin_id": distintos,
                          "independientes": unicos_base}
    return {
        "archivo": "benchmark/domains.py", "sha256_archivo": _sha(ROOT / "benchmark" / "domains.py"),
        "sha256_contenido_base": sha_contenido,
        "sintetico": True, "fuente": "escrito a mano por los autores (benchmark/domains.py)", "licencia": "MIT (licencia del repositorio)",
        "semilla_muestreo": C.SEMILLA, "semilla_ciclo": None,
        "dominios": len(base), "registros_base_por_dominio": 12, "registros_base_total": sum(v["registros_base"] for v in por_dominio.values()),
        "nota_q_extiende_a": "q contiene los mismos 12 ítems que a con tres campos más: a lo sumo 13 dominios independientes",
        "replicacion_de_base": {"n_mayor_que": 12, "descripcion": "para n > 12 se repiten los 12 registros base con identificadores nuevos; no son muestras independientes"},
        "por_dominio": por_dominio,
    }


def contratos_info() -> List[Dict[str, Any]]:
    out = []
    for p in sorted(domains.BASE):
        ruta = ROOT / "forks" / p / "contract.json"
        d = json.loads(ruta.read_text(encoding="utf-8"))
        out.append({"prefijo": p, "ruta": f"forks/{p}/contract.json", "sha256": _sha(ruta), "version": d.get("version"),
                    "generador": "minifmt.dumps (contrato del fork; no inferido)"})
    return out


def publicos_info() -> List[Dict[str, Any]]:
    """Los 4 snapshots públicos: hash recalculado y comparado con sources.json."""
    fuentes = json.loads((ROOT / "benchmark" / "public" / "sources.json").read_text(encoding="utf-8"))
    out = []
    for s in fuentes:
        ruta = ROOT / "benchmark" / "public" / s["file"]
        h = _sha(ruta)
        out.append({
            "nombre": f"public/{s['id']}", "ruta": f"benchmark/public/{s['file']}", "sha256": h, "sha256_coincide_con_sources_json": h == s["sha256"],
            "sintetico": s["id"] != "earthquakes", "tipo": s["kind"], "licencia": LICENCIAS_PUBLICAS[s["id"]], "fuente": s["url"],
            "documentacion": s.get("documentation"), "fecha_captura_utc": s["fetched_at_utc"], "registros": s["records"],
            "registros_unicos": s["unique_ids"], "bytes": s["bytes"], "semilla": None, "replicacion_de_base": False,
            "seleccion": s["selection"],
        })
    return out


def conjuntos_manifiesto(incluir_dominios: bool = True, incluir_publicos: bool = True) -> List[Dict[str, Any]]:
    """Lista ``conjuntos`` del manifiesto mini-format/corrida/1."""
    c: List[Dict[str, Any]] = []
    if incluir_dominios:
        d = dominios_info()
        c.append({"nombre": "dominios_14x12 (benchmark/domains.py)", "ruta": d["archivo"], "sha256": d["sha256_archivo"],
                  "sintetico": True, "licencia": d["licencia"], "fuente": d["fuente"], "registros": d["registros_base_total"],
                  "semilla": d["semilla_muestreo"], "replicacion_de_base": True,
                  "sha256_contenido_base": d["sha256_contenido_base"],
                  "nota": "168 registros base; n > 12 replica esos 12 registros por dominio (no son muestras independientes)"})
    if incluir_publicos:
        for p in publicos_info():
            c.append({k: p[k] for k in ("nombre", "ruta", "sha256", "sintetico", "licencia", "fuente", "registros", "semilla",
                                        "fecha_captura_utc", "replicacion_de_base", "registros_unicos", "tipo")})
    return c
