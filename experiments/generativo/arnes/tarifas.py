"""Tarifas por modelo y costo por categorías de usage.

Este módulo CONSUME la estructura acordada con el flujo de infraestructura
(``evidencia/tarifas/tarifas.json``)::

    {"proveedor", "modelo_api_id", "moneda": "USD",
     "entrada_sin_cache_por_millon": "decimal"|null, "entrada_cache_lectura_por_millon",
     "entrada_cache_escritura_por_millon", "salida_por_millon",
     "estado": "verificada"|"no_verificada", "fecha_consulta_utc", "url_oficial"}

Regla dura: si una tarifa es ``no_verificada`` o no existe, el costo es ``None``
("tarifa no verificada"); NUNCA se usa un precio supuesto.  No hay precios por
defecto en el código ni en el repositorio del arnés.

La fórmula monetaria OFICIAL de los informes vive en ``experiments/economia``
(flujo de infraestructura).  La de este módulo solo sirve para los controles de
gasto del arnés (proyección antes de cada llamada, dry-run y costo por solicitud
del análisis); usa ``Decimal`` y la misma estructura ``usage``, de modo que sus
resultados se puedan contrastar con los de aquella.
"""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional

MILLON = Decimal(1_000_000)
TARIFAS_POR_DEFECTO = Path(__file__).resolve().parents[3] / "evidencia" / "tarifas" / "tarifas.json"
NO_VERIFICADA = "tarifa no verificada"


def _dec(v: Any) -> Optional[Decimal]:
    if v is None or v == "":
        return None
    return Decimal(str(v))


@dataclass(frozen=True)
class Tarifa:
    proveedor: str
    modelo_api_id: str
    moneda: str
    entrada_sin_cache: Optional[Decimal]
    entrada_cache_lectura: Optional[Decimal]
    entrada_cache_escritura: Optional[Decimal]
    salida: Optional[Decimal]
    estado: str
    fecha_consulta_utc: Optional[str]
    url_oficial: Optional[str]

    @property
    def verificada(self) -> bool:
        return self.estado == "verificada"

    @property
    def utilizable(self) -> bool:
        """Verificada y con los dos precios que toda llamada necesita (entrada sin caché y salida)."""
        return self.verificada and self.entrada_sin_cache is not None and self.salida is not None

    @classmethod
    def desde_dict(cls, d: Mapping[str, Any]) -> "Tarifa":
        return cls(
            proveedor=str(d["proveedor"]).strip().lower(),
            modelo_api_id=str(d["modelo_api_id"]).strip(),
            moneda=str(d.get("moneda", "USD")),
            entrada_sin_cache=_dec(d.get("entrada_sin_cache_por_millon")),
            entrada_cache_lectura=_dec(d.get("entrada_cache_lectura_por_millon")),
            entrada_cache_escritura=_dec(d.get("entrada_cache_escritura_por_millon")),
            salida=_dec(d.get("salida_por_millon")),
            estado=str(d.get("estado", "no_verificada")),
            fecha_consulta_utc=d.get("fecha_consulta_utc") or d.get("consultado_utc"),
            url_oficial=d.get("url_oficial"))

    def resumen(self) -> Dict[str, Any]:
        return {"proveedor": self.proveedor, "modelo_api_id": self.modelo_api_id, "estado": self.estado,
                "fecha_consulta_utc": self.fecha_consulta_utc, "url_oficial": self.url_oficial}


def _ids_de(d: Mapping[str, Any]) -> List[str]:
    """Identificadores con los que se puede pedir el modelo: el id, el alias en paréntesis y ``alias``."""
    bruto = str(d["modelo_api_id"]).strip()
    ids = []
    m = re.match(r"^(\S+)\s*\(alias:\s*([^)]+)\)\s*$", bruto)
    if m:
        ids += [m.group(1), m.group(2).strip()]
    else:
        ids.append(bruto)
    alias = d.get("alias") or []
    ids += [alias] if isinstance(alias, str) else list(alias)
    return ids


class Tarifas:
    def __init__(self, tarifas: Optional[List[Tarifa]] = None, *, origen: Optional[str] = None,
                 sha256: Optional[str] = None, consultado_utc: Optional[str] = None):
        self._por_clave: Dict[tuple, Tarifa] = {}
        for t in tarifas or []:
            self._por_clave[(t.proveedor, t.modelo_api_id)] = t
        self.origen = origen
        self.sha256 = sha256
        self.consultado_utc = consultado_utc

    @classmethod
    def cargar(cls, ruta: Optional[Path] = None) -> "Tarifas":
        """Carga el archivo de tarifas; si no existe devuelve un conjunto vacío (todo 'tarifa no verificada')."""
        p = Path(ruta) if ruta else TARIFAS_POR_DEFECTO
        if not p.exists():
            return cls(origen=None)
        crudo = p.read_bytes()
        data = json.loads(crudo.decode("utf-8"))
        filas = data.get("tarifas", []) if isinstance(data, dict) else data
        lista: List[Tarifa] = []
        for d in filas:
            t = Tarifa.desde_dict(d)
            for ident in _ids_de(d):
                lista.append(Tarifa(**{**t.__dict__, "modelo_api_id": ident}))
        consultado = (data.get("consultado_utc") or data.get("consulta_utc")) if isinstance(data, dict) else None
        try:
            origen = p.resolve().relative_to(Path(__file__).resolve().parents[3]).as_posix()
        except ValueError:
            origen = p.as_posix()
        return cls(lista, origen=origen, sha256=hashlib.sha256(crudo).hexdigest(), consultado_utc=consultado)

    def obtener(self, proveedor: str, modelo: str) -> Optional[Tarifa]:
        return self._por_clave.get((proveedor.strip().lower(), modelo.strip()))

    def estado(self, proveedor: str, modelo: str) -> str:
        t = self.obtener(proveedor, modelo)
        if t is None:
            return "ausente"
        return "verificada" if t.utilizable else "no_verificada"

    def utilizable(self, proveedor: str, modelo: str) -> Optional[Tarifa]:
        t = self.obtener(proveedor, modelo)
        return t if t is not None and t.utilizable else None


# --------------------------------------------------------------------------
# Costo
# --------------------------------------------------------------------------
def _n(v: Any) -> int:
    return int(v or 0)


def costo_usage(tarifa: Optional[Tarifa], usage: Optional[Mapping[str, Any]]) -> Optional[Decimal]:
    """Costo en USD de UN intento a partir de su ``usage`` por categorías.

    ``None`` (= "tarifa no verificada") si la tarifa falta o no es verificada, si
    no hay usage, o si alguna categoría con tokens no tiene precio.  El
    razonamiento se suma aparte solo cuando NO viene incluido en la salida
    (``razonamiento_incluido_en_salida`` falso): así no hay doble conteo.
    """
    if tarifa is None or not tarifa.utilizable or usage is None:
        return None
    partes = [(_n(usage.get("entrada_sin_cache")), tarifa.entrada_sin_cache),
              (_n(usage.get("entrada_cache_lectura")), tarifa.entrada_cache_lectura),
              (_n(usage.get("entrada_cache_escritura")), tarifa.entrada_cache_escritura),
              (_n(usage.get("salida")), tarifa.salida)]
    if usage.get("razonamiento") is not None and not usage.get("razonamiento_incluido_en_salida", True):
        partes.append((_n(usage["razonamiento"]), tarifa.salida))
    total = Decimal(0)
    for tokens, precio in partes:
        if tokens and precio is None:
            return None
        if tokens:
            total += Decimal(tokens) * precio / MILLON
    for v in (usage.get("otros_usd") or {}).values():
        total += Decimal(str(v))
    return total


def costo_peor_caso(tarifa: Optional[Tarifa], tokens_entrada: int, max_salida: int) -> Optional[Decimal]:
    """Cota superior del costo de una llamada: toda la entrada al precio más alto de entrada y la salida agotando el límite.

    ``max_salida`` es el ``max_tokens`` enviado; el razonamiento de los modelos que razonan cuenta dentro de ese límite.
    """
    if tarifa is None or not tarifa.utilizable:
        return None
    p_in = max(tarifa.entrada_sin_cache, tarifa.entrada_cache_escritura or Decimal(0))
    return (Decimal(int(tokens_entrada)) * p_in + Decimal(int(max_salida)) * tarifa.salida) / MILLON


def decimal_a_texto(v: Optional[Decimal]) -> Optional[str]:
    return None if v is None else format(v.normalize() if v != 0 else Decimal(0), "f")
