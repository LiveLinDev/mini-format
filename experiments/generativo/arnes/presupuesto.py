"""Presupuesto, autorización y libro de gasto.

Reglas (todas con prueba):

* El bloque ``presupuesto`` del YAML declara ``autorizado_usd``, ``por_celda_max_usd``,
  ``firmado_por`` y ``fecha``.  Por defecto NADA está autorizado (0).
* El adaptador real se RECHAZA, con un error claro y sin llamada, si
  ``autorizado_usd <= 0``, si falta ``firmado_por`` o ``fecha``, si falta
  ``--max-costo-usd``, si este supera lo autorizado, si alguna tarifa necesaria
  no está verificada o si el costo esperado no cabe en el tope.
* Antes de CADA llamada se comprueba por PROYECCIÓN ``gastado + incierto + peor
  caso de esa llamada <= tope`` (y el peor caso de la celda contra
  ``por_celda_max_usd``): nunca se descubre el exceso después de gastar.
* El libro (``libro.jsonl``) anota el inicio y el fin de cada llamada; una
  llamada iniciada y nunca terminada (proceso matado) se cuenta al peor caso
  como gasto incierto al reanudar.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional

from .tarifas import Tarifas


class ErrorAutorizacion(RuntimeError):
    """La ejecución real no está autorizada (se lanza antes de cualquier llamada)."""

    def __init__(self, errores: List[str]):
        super().__init__("ejecución real NO autorizada: " + "; ".join(errores))
        self.errores = errores


@dataclass(frozen=True)
class Presupuesto:
    autorizado_usd: Decimal = Decimal(0)
    por_celda_max_usd: Optional[Decimal] = None
    firmado_por: str = ""
    fecha: str = ""

    @classmethod
    def desde_config(cls, cfg: Mapping[str, Any]) -> "Presupuesto":
        b = cfg.get("presupuesto") or {}
        pc = b.get("por_celda_max_usd")
        return cls(autorizado_usd=Decimal(str(b.get("autorizado_usd") or 0)),
                   por_celda_max_usd=None if pc in (None, "") else Decimal(str(pc)),
                   firmado_por=str(b.get("firmado_por") or "").strip(), fecha=str(b.get("fecha") or "").strip())

    def como_dict(self) -> Dict[str, Any]:
        return {"autorizado_usd": format(self.autorizado_usd, "f"),
                "por_celda_max_usd": None if self.por_celda_max_usd is None else format(self.por_celda_max_usd, "f"),
                "firmado_por": self.firmado_por, "fecha": self.fecha}


@dataclass(frozen=True)
class Autorizacion:
    """Prueba de que la ejecución real pasó todas las comprobaciones. Solo la crea ``validar_autorizacion``."""
    tope_usd: Decimal
    presupuesto: Presupuesto
    _sello: object = None

    def __post_init__(self):
        if self._sello is not _SELLO:
            raise ErrorAutorizacion(["la autorización solo se obtiene con validar_autorizacion()"])


_SELLO = object()


def validar_autorizacion(presupuesto: Presupuesto, max_costo_usd: Optional[float], tarifas: Tarifas,
                         modelos: Iterable[Mapping[str, Any]], *, costo_esperado: Optional[Decimal],
                         costo_maximo: Optional[Decimal], claves_faltantes: Iterable[str] = ()) -> Autorizacion:
    """Devuelve la ``Autorizacion`` o lanza ``ErrorAutorizacion`` con TODOS los motivos de rechazo."""
    e: List[str] = []
    if presupuesto.autorizado_usd <= 0:
        e.append("presupuesto.autorizado_usd es 0 (sin autorización): el YAML debe declararlo, con firmado_por y fecha")
    else:
        if not presupuesto.firmado_por:
            e.append("presupuesto.firmado_por está vacío")
        if not presupuesto.fecha:
            e.append("presupuesto.fecha está vacía")
    tope: Optional[Decimal] = None
    if max_costo_usd is None:
        e.append("falta --max-costo-usd (es obligatorio con el adaptador real)")
    else:
        tope = Decimal(str(max_costo_usd))
        if tope <= 0:
            e.append("--max-costo-usd debe ser mayor que 0")
        elif presupuesto.autorizado_usd > 0 and tope > presupuesto.autorizado_usd:
            e.append(f"--max-costo-usd {tope} supera lo autorizado ({presupuesto.autorizado_usd})")
    for m in modelos:
        est = tarifas.estado(m["proveedor"], m["modelo"])
        if est != "verificada":
            e.append(f"tarifa no verificada para {m['proveedor']}:{m['modelo']} ({est}): no se puede proyectar el gasto")
    if costo_esperado is None or costo_maximo is None:
        e.append("no se pudo calcular el costo esperado/máximo (faltan tarifas)")
    elif tope is not None and tope > 0 and costo_esperado > min(tope, presupuesto.autorizado_usd or tope):
        e.append(f"el costo esperado {costo_esperado:.2f} USD no cabe en el tope")
    for v in claves_faltantes:
        e.append(f"falta la variable de entorno {v}")
    if e:
        raise ErrorAutorizacion(e)
    return Autorizacion(tope_usd=min(tope, presupuesto.autorizado_usd), presupuesto=presupuesto, _sello=_SELLO)


def autorizacion_de_prueba(tope_usd: float = 1000.0) -> Autorizacion:
    """Autorización ficticia para pruebas con adaptadores inyectados (nunca se usa en run.py)."""
    p = Presupuesto(Decimal(str(tope_usd)), None, "prueba", "2000-01-01")
    return Autorizacion(tope_usd=Decimal(str(tope_usd)), presupuesto=p, _sello=_SELLO)


# --------------------------------------------------------------------------
# Libro de gasto
# --------------------------------------------------------------------------
class Libro:
    """Registro append-only de llamadas y proyección contra el tope.

    Sin ``tope`` no bloquea (modo simulado sin ``--max-costo-usd``), pero sigue anotando.
    """

    def __init__(self, ruta: Path, tope: Optional[Decimal] = None, por_celda_max: Optional[Decimal] = None):
        self.ruta = Path(ruta)
        self.tope = tope
        self.por_celda_max = por_celda_max
        self.gastado = Decimal(0)
        self.incierto = Decimal(0)
        self.llamadas = 0
        self.huerfanas = 0               # llamadas iniciadas que nunca terminaron (contadas al peor caso)
        self._abiertas: Dict[str, Decimal] = {}
        self._n = 0
        self._cargar()

    def _cargar(self) -> None:
        if not self.ruta.exists():
            return
        abiertas: Dict[str, Decimal] = {}
        with open(self.ruta, "r", encoding="utf-8") as fh:
            for linea in fh:
                try:
                    ev = json.loads(linea)
                except ValueError:
                    continue
                lid = ev.get("llamada")
                if ev.get("evt") == "inicio":
                    abiertas[lid] = Decimal(str(ev.get("peor_caso_usd") or 0))
                    self.llamadas += 1
                elif ev.get("evt") == "fin":
                    abiertas.pop(lid, None)
                    if ev.get("costo_usd") is not None:
                        self.gastado += Decimal(str(ev["costo_usd"]))
                    if ev.get("incierto_usd"):
                        self.incierto += Decimal(str(ev["incierto_usd"]))
                self._n += 1
        for peor in abiertas.values():
            self.incierto += peor
            self.huerfanas += 1

    # -- proyección ---------------------------------------------------------
    @property
    def comprometido(self) -> Decimal:
        return self.gastado + self.incierto + sum(self._abiertas.values(), Decimal(0))

    def proyectar(self, peor_caso: Optional[Decimal], gasto_celda: Decimal = Decimal(0)) -> Optional[str]:
        """``None`` si la llamada cabe; si no, el motivo (sin haber gastado nada)."""
        if peor_caso is None:
            return "no se puede proyectar el costo de la llamada: tarifa no verificada"
        if self.tope is not None and self.comprometido + peor_caso > self.tope:
            return (f"proyección {self.comprometido + peor_caso:.6f} USD (gastado+incierto {self.comprometido:.6f} + "
                    f"peor caso {peor_caso:.6f}) supera el tope {self.tope}")
        if self.por_celda_max is not None and gasto_celda + peor_caso > self.por_celda_max:
            return (f"proyección de la celda {gasto_celda + peor_caso:.6f} USD supera por_celda_max_usd "
                    f"{self.por_celda_max}")
        return None

    # -- eventos ------------------------------------------------------------
    def _escribir(self, ev: Dict[str, Any]) -> None:
        self.ruta.parent.mkdir(parents=True, exist_ok=True)
        with open(self.ruta, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(ev, ensure_ascii=False) + "\n")
            fh.flush()
            os.fsync(fh.fileno())

    def iniciar(self, celda: str, fase: str, peor_caso: Optional[Decimal]) -> str:
        self._n += 1
        lid = f"{os.getpid()}-{self._n}"
        peor = peor_caso if peor_caso is not None else Decimal(0)
        self._abiertas[lid] = peor
        self.llamadas += 1
        self._escribir({"evt": "inicio", "llamada": lid, "celda": celda, "fase": fase, "peor_caso_usd": format(peor, "f")})
        return lid

    def terminar(self, lid: str, *, ok: bool, costo: Optional[Decimal], incierto: Decimal = Decimal(0),
                 nota: str = "") -> None:
        self._abiertas.pop(lid, None)
        if costo is not None:
            self.gastado += costo
        if incierto:
            self.incierto += incierto
        self._escribir({"evt": "fin", "llamada": lid, "ok": ok, "costo_usd": None if costo is None else format(costo, "f"),
                        "incierto_usd": format(incierto, "f") if incierto else None, "nota": nota})

    def resumen(self) -> Dict[str, Any]:
        return {"gastado_usd": format(self.gastado, "f"), "incierto_usd": format(self.incierto, "f"),
                "llamadas": self.llamadas, "llamadas_huerfanas": self.huerfanas,
                "tope_usd": None if self.tope is None else format(self.tope, "f")}
