"""Dry-run: recuento de llamadas y costo esperado/máximo SIN ejecutar nada.

* El recuento separa, por experimento, las llamadas primarias NOMINALES del
  diseño (tareas × modelos × repeticiones × brazos primarios), las celdas
  ``no_aplicable`` (brazo C en modelos sin modo estructurado) y las que se
  ejecutarían, más las reparaciones (máximo: una por celda de reparación y ronda).
* El costo usa SOLO tarifas verificadas (``tarifas.py``): donde falta o no está
  verificada, la cifra es ``None`` y se imprime «tarifa no verificada».
* Los tokens de entrada son un conteo LOCAL de texto (``o200k_base``) multiplicado
  por un factor supuesto por proveedor: una aproximación, no el conteo del
  proveedor ni el usage de una llamada.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, Dict, List, Optional

from minifmt.tokens import count_tokens

from . import brazos as B
from .ejecucion import FACTOR_TOKENIZADOR, Contexto, Enumeracion, Unidad, enumerar_completo
from .tarifas import Tarifas, NO_VERIFICADA, costo_peor_caso

MILLON = Decimal(1_000_000)


class ContadorTokens:
    """Cuenta tokens de textos repetidos una sola vez (los prompts se repiten por repetición)."""

    def __init__(self):
        self._cache: Dict[str, int] = {}

    def __call__(self, texto: str) -> int:
        if texto not in self._cache:
            self._cache[texto] = count_tokens(texto)
        return self._cache[texto]


@dataclass
class FilaEstimacion:
    proveedor: str
    modelo: str
    llamadas_generacion: int = 0
    llamadas_reparacion_esperadas: float = 0.0
    llamadas_reparacion_max: int = 0
    tokens_entrada: float = 0.0
    tokens_salida_esperados: float = 0.0
    tokens_entrada_max: float = 0.0
    tokens_salida_max: float = 0.0
    costo_esperado: Optional[Decimal] = None
    costo_maximo: Optional[Decimal] = None
    tarifa_estado: str = "ausente"


@dataclass
class Estimacion:
    filas: List[FilaEstimacion] = field(default_factory=list)
    recuento: Dict[str, Any] = field(default_factory=dict)

    @property
    def llamadas(self) -> int:
        return sum(f.llamadas_generacion for f in self.filas)

    @property
    def costo_esperado(self) -> Optional[Decimal]:
        vals = [f.costo_esperado for f in self.filas]
        return None if (not vals or any(v is None for v in vals)) else sum(vals, Decimal(0))

    @property
    def costo_maximo(self) -> Optional[Decimal]:
        vals = [f.costo_maximo for f in self.filas]
        return None if (not vals or any(v is None for v in vals)) else sum(vals, Decimal(0))

    def tabla(self) -> str:
        def usd(v: Optional[Decimal]) -> str:
            return NO_VERIFICADA if v is None else f"{v:,.2f}"
        cab = ("proveedor", "modelo", "llamadas gen.", "reparación esp./máx.", "tokens entrada (aprox.)",
               "tokens salida esp.", "costo esperado USD", "costo máximo USD", "tarifa")
        filas = [cab]
        for f in self.filas:
            filas.append((f.proveedor, f.modelo, str(f.llamadas_generacion),
                          f"{f.llamadas_reparacion_esperadas:.0f}/{f.llamadas_reparacion_max}",
                          f"{f.tokens_entrada:,.0f}", f"{f.tokens_salida_esperados:,.0f}",
                          usd(f.costo_esperado), usd(f.costo_maximo), f.tarifa_estado))
        filas.append(("TOTAL", "", str(self.llamadas),
                      f"{sum(f.llamadas_reparacion_esperadas for f in self.filas):.0f}/{sum(f.llamadas_reparacion_max for f in self.filas)}",
                      f"{sum(f.tokens_entrada for f in self.filas):,.0f}",
                      f"{sum(f.tokens_salida_esperados for f in self.filas):,.0f}",
                      usd(self.costo_esperado), usd(self.costo_maximo), ""))
        anchos = [max(len(r[i]) for r in filas) for i in range(len(cab))]
        lineas = []
        for j, r in enumerate(filas):
            lineas.append(" | ".join(x.ljust(anchos[i]) for i, x in enumerate(r)))
            if j == 0:
                lineas.append("-+-".join("-" * a for a in anchos))
        return "\n".join(lineas)


def recuento(cfg: Dict[str, Any], en: Enumeracion) -> Dict[str, Any]:
    """Cuenta las celdas del diseño y explica cada diferencia respecto al recuento nominal."""
    rondas = int((cfg.get("reparacion") or {}).get("max_rondas", 1))
    por_exp: Dict[str, Dict[str, Any]] = {}
    explicacion: List[str] = []
    n_tareas_def, n_modelos = len(cfg["tareas"]), len(cfg["modelos"])
    for exp, nom in en.nominal.items():
        ecfg = cfg["experimentos"].get(exp) or {}
        brazos = list(ecfg.get("brazos", cfg["brazos"]))
        prim = [b for b in brazos if not B.es_reparacion(b)]
        rep = [b for b in brazos if B.es_reparacion(b)]
        reps = int(ecfg.get("repeticiones", cfg["repeticiones"]))
        tareas = len(ecfg.get("tareas", cfg["tareas"]))
        na_p = [x for x in en.no_aplicables if x["experimento"] == exp and not B.es_reparacion(x["brazo"])]
        na_r = [x for x in en.no_aplicables if x["experimento"] == exp and B.es_reparacion(x["brazo"])]
        ejec_p = [u for u in en.unidades if u.experimento == exp and not B.es_reparacion(u.brazo)]
        ejec_r = [u for u in en.unidades if u.experimento == exp and B.es_reparacion(u.brazo)]
        por_exp[exp] = {"primarias_nominales": nom["primarias"], "no_aplicables_primarias": len(na_p),
                        "primarias_a_ejecutar": len(ejec_p), "reparaciones_nominales": nom["reparaciones"],
                        "no_aplicables_reparaciones": len(na_r), "celdas_reparacion_a_ejecutar": len(ejec_r),
                        "reparaciones_maximas": len(ejec_r) * rondas,
                        "llamadas_maximas": len(ejec_p) + len(ejec_r) * rondas}
        explicacion.append(f"{exp}: nominal = {tareas} tareas × {n_modelos} modelos × {reps} repeticiones × {len(prim)} brazos "
                           f"primarios ({', '.join(prim)}) = {nom['primarias']} llamadas primarias")
        if na_p:
            por_mod: Dict[str, int] = defaultdict(int)
            for x in na_p:
                por_mod[f"{x['proveedor']}:{x['modelo']}"] += 1
            det = "; ".join(f"{k}: {v}" for k, v in sorted(por_mod.items()))
            explicacion.append(f"{exp}: menos {len(na_p)} celdas del brazo C no aplicables ({det}; el modelo no declara modo "
                               f"estructurado) = {len(ejec_p)} llamadas primarias a ejecutar")
        if rep:
            explicacion.append(f"{exp}: además {len(ejec_r)} celdas de reparación ({', '.join(rep)}), de {nom['reparaciones']} "
                               f"nominales; cada una añade como máximo {rondas} llamada(s) de reparación y solo si la respuesta "
                               f"base tiene algo que reparar")
    tot = {"primarias_nominales": sum(v["primarias_nominales"] for v in por_exp.values()),
           "primarias_a_ejecutar": sum(v["primarias_a_ejecutar"] for v in por_exp.values()),
           "no_aplicables": len(en.no_aplicables),
           "reparaciones_maximas": sum(v["reparaciones_maximas"] for v in por_exp.values()),
           "llamadas_maximas": sum(v["llamadas_maximas"] for v in por_exp.values())}
    if len(por_exp) > 1:
        explicacion.append("total de llamadas primarias a ejecutar = " + " + ".join(
            f"{v['primarias_a_ejecutar']} ({k})" for k, v in por_exp.items()) + f" = {tot['primarias_a_ejecutar']}")
    return {"experimentos": por_exp, "totales": tot, "explicacion": explicacion}


def _tasa(est_cfg: Dict[str, Any], brazo: str) -> float:
    t = est_cfg.get("tasa_reparacion_esperada", 0.35)
    if isinstance(t, dict):
        return float(t.get(brazo, t.get("por_defecto", 0.35)))
    return float(t)


def estimar(en: Enumeracion, contexto: Contexto, tarifas: Tarifas, cfg: Dict[str, Any]) -> Estimacion:
    """Estimación previa a ejecutar.

    * tokens de entrada: prompts reales contados con ``o200k_base`` × factor supuesto del proveedor;
    * salida esperada: tokens de la salida de referencia del brazo × ``factor_salida`` (acotada por
      ``max_tokens``); salida máxima: ``max_tokens`` de la celda;
    * reparación: llamadas esperadas = tasa × celdas de reparación; máximas = ``max_rondas`` por celda,
      con entrada = prompt del brazo + todo el documento y salida = documento completo × 2 (cota).
    """
    est_cfg = cfg.get("estimacion", {})
    f_sal = float(est_cfg.get("factor_salida", 1.15))
    frac_rep = float(est_cfg.get("fraccion_lineas_reparadas", 0.2))
    rondas = int(cfg.get("reparacion", {}).get("max_rondas", 1))
    factores = {**FACTOR_TOKENIZADOR, **{k: float(v) for k, v in (est_cfg.get("factor_tokenizador") or {}).items()}}
    tok = ContadorTokens()
    filas: Dict[tuple, FilaEstimacion] = {}
    for u in en.unidades:
        fila = filas.setdefault((u.proveedor, u.modelo),
                                FilaEstimacion(u.proveedor, u.modelo, tarifa_estado=tarifas.estado(u.proveedor, u.modelo)))
        factor = factores.get(u.proveedor, 1.3)
        t = contexto.tareas[u.tarea]
        ref_tokens = tok(contexto.salida_ref(t, u.brazo))
        if B.es_reparacion(u.brazo):
            p = contexto.prompt(t, u.brazo)
            spec = tok(p.system) * factor
            doc = ref_tokens * factor
            tasa = _tasa(est_cfg, u.brazo)
            fila.llamadas_reparacion_esperadas += tasa * rondas
            fila.llamadas_reparacion_max += rondas
            fila.tokens_entrada += tasa * rondas * (spec + frac_rep * doc + 150)
            fila.tokens_salida_esperados += tasa * rondas * frac_rep * ref_tokens * f_sal
            fila.tokens_entrada_max += rondas * (spec + doc + 150)
            fila.tokens_salida_max += rondas * ref_tokens * 2
            continue
        p = contexto.prompt(t, u.brazo)
        tin = (tok(p.system) + tok(p.user) + 10) * factor
        fila.llamadas_generacion += 1
        fila.tokens_entrada += tin
        fila.tokens_entrada_max += tin
        fila.tokens_salida_esperados += min(u.max_tokens, ref_tokens * f_sal)
        fila.tokens_salida_max += u.max_tokens
    for fila in filas.values():
        t = tarifas.utilizable(fila.proveedor, fila.modelo)
        if t is not None:
            fila.costo_esperado = (Decimal(str(fila.tokens_entrada)) * t.entrada_sin_cache
                                   + Decimal(str(fila.tokens_salida_esperados)) * t.salida) / MILLON
            fila.costo_maximo = (Decimal(str(fila.tokens_entrada_max)) * t.entrada_sin_cache
                                 + Decimal(str(fila.tokens_salida_max)) * t.salida) / MILLON
    return Estimacion(filas=sorted(filas.values(), key=lambda f: (f.proveedor, f.modelo)), recuento=recuento(cfg, en))


def informe_dry_run(cfg: Dict[str, Any], contexto: Contexto, tarifas: Tarifas) -> Dict[str, Any]:
    """Todo lo que imprime el dry-run, como estructura (no ejecuta ni escribe nada)."""
    en = enumerar_completo(cfg, contexto)
    est = estimar(en, contexto, tarifas, cfg)
    return {"enumeracion": en, "estimacion": est}
