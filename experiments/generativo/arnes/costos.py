"""Precios (``precios.json``) y estimación de llamadas, tokens y costo."""
from __future__ import annotations

import json
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from minifmt.tokens import count_tokens

HERE = Path(__file__).resolve().parents[1]
PRECIOS_POR_DEFECTO = HERE / "precios.json"


class Precios:
    def __init__(self, data: Dict[str, Any]):
        self.data = data
        self.modelos = data.get("modelos", {})
        self.factores = {k: v for k, v in data.get("factor_tokenizador", {}).items() if not k.startswith("_")}

    @classmethod
    def cargar(cls, path: Optional[Path] = None) -> "Precios":
        p = Path(path) if path else PRECIOS_POR_DEFECTO
        return cls(json.loads(p.read_text(encoding="utf-8")))

    def get(self, proveedor: str, modelo: str) -> Optional[Dict[str, Any]]:
        return self.modelos.get(f"{proveedor}:{modelo}")

    def factor(self, proveedor: str) -> float:
        return float(self.factores.get(proveedor, 1.0))

    def costo(self, proveedor: str, modelo: str, tokens_entrada: Optional[int], tokens_salida: Optional[int]) -> Optional[float]:
        p = self.get(proveedor, modelo)
        if p is None:
            return None
        return ((tokens_entrada or 0) * p["entrada"] + (tokens_salida or 0) * p["salida"]) / 1_000_000

    def verificado(self, proveedor: str, modelo: str) -> bool:
        p = self.get(proveedor, modelo)
        return bool(p and p.get("verificado"))


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
    costo_esperado: Optional[float] = 0.0
    costo_maximo: Optional[float] = 0.0
    precio_verificado: bool = False


@dataclass
class Estimacion:
    filas: List[FilaEstimacion] = field(default_factory=list)
    omitidas: List[str] = field(default_factory=list)

    @property
    def llamadas(self) -> int:
        return sum(f.llamadas_generacion for f in self.filas)

    @property
    def costo_esperado(self) -> Optional[float]:
        vals = [f.costo_esperado for f in self.filas]
        return None if any(v is None for v in vals) else sum(vals)

    @property
    def costo_maximo(self) -> Optional[float]:
        vals = [f.costo_maximo for f in self.filas]
        return None if any(v is None for v in vals) else sum(vals)

    def tabla(self) -> str:
        cab = ("proveedor", "modelo", "llamadas gen.", "reparación esp./máx.", "tokens entrada", "tokens salida esp.",
               "costo esperado USD", "costo máximo USD", "precio verificado")
        filas = [cab]
        for f in self.filas:
            filas.append((f.proveedor, f.modelo, str(f.llamadas_generacion),
                          f"{f.llamadas_reparacion_esperadas:.0f}/{f.llamadas_reparacion_max}",
                          f"{f.tokens_entrada:,.0f}", f"{f.tokens_salida_esperados:,.0f}",
                          "SIN PRECIO" if f.costo_esperado is None else f"{f.costo_esperado:,.2f}",
                          "SIN PRECIO" if f.costo_maximo is None else f"{f.costo_maximo:,.2f}",
                          "sí" if f.precio_verificado else "NO (provisional)"))
        ce, cm = self.costo_esperado, self.costo_maximo
        filas.append(("TOTAL", "", str(self.llamadas),
                      f"{sum(f.llamadas_reparacion_esperadas for f in self.filas):.0f}/{sum(f.llamadas_reparacion_max for f in self.filas)}",
                      f"{sum(f.tokens_entrada for f in self.filas):,.0f}",
                      f"{sum(f.tokens_salida_esperados for f in self.filas):,.0f}",
                      "SIN PRECIO" if ce is None else f"{ce:,.2f}", "SIN PRECIO" if cm is None else f"{cm:,.2f}", ""))
        anchos = [max(len(r[i]) for r in filas) for i in range(len(cab))]
        lineas = []
        for j, r in enumerate(filas):
            lineas.append(" | ".join(x.ljust(anchos[i]) for i, x in enumerate(r)))
            if j == 0:
                lineas.append("-+-".join("-" * a for a in anchos))
        return "\n".join(lineas)


class ContadorTokens:
    """Cuenta tokens de textos repetidos una sola vez (los prompts se repiten por repetición)."""

    def __init__(self):
        self._cache: Dict[str, int] = {}

    def __call__(self, texto: str) -> int:
        if texto not in self._cache:
            self._cache[texto] = count_tokens(texto)
        return self._cache[texto]


def estimar(unidades, contexto, precios: Precios, cfg: Dict[str, Any]) -> Estimacion:
    """Estimación previa a ejecutar.

    * tokens de entrada: prompts reales contados con o200k_base × factor del proveedor;
    * salida esperada: tokens de la salida de referencia del brazo × ``factor_salida``
      (acotada por max_tokens); salida máxima: ``max_tokens`` de la unidad;
    * reparación (D+R): llamadas esperadas = tasa_reparacion_esperada × muestras; máximas =
      ``max_rondas`` por muestra, con entrada = bloque de especificación + todo el documento
      y salida = documento completo (cota superior).
    """
    est_cfg = cfg.get("estimacion", {})
    f_sal = float(est_cfg.get("factor_salida", 1.15))
    tasa_rep = float(est_cfg.get("tasa_reparacion_esperada", 0.35))
    frac_rep = float(est_cfg.get("fraccion_lineas_reparadas", 0.2))
    rondas = int(cfg.get("reparacion", {}).get("max_rondas", 1))
    tok = ContadorTokens()
    filas: Dict[tuple, FilaEstimacion] = {}
    for u in unidades:
        key = (u.proveedor, u.modelo)
        fila = filas.setdefault(key, FilaEstimacion(u.proveedor, u.modelo,
                                                    precio_verificado=precios.verificado(u.proveedor, u.modelo)))
        factor = precios.factor(u.proveedor)
        t = contexto.tareas[u.tarea]
        ref_tokens = tok(contexto.salida_ref(t, u.brazo))
        if u.brazo == "D+R":
            p = contexto.prompt(t, "D")
            spec = tok(p.system) * factor
            doc = ref_tokens * factor
            esperado_in = tasa_rep * rondas * (spec + frac_rep * doc + 150)
            esperado_out = tasa_rep * rondas * frac_rep * ref_tokens * f_sal
            max_in = rondas * (spec + doc + 150)
            max_out = rondas * ref_tokens * 2
            fila.llamadas_reparacion_esperadas += tasa_rep * rondas
            fila.llamadas_reparacion_max += rondas
            fila.tokens_entrada += esperado_in
            fila.tokens_salida_esperados += esperado_out
            fila.tokens_entrada_max += max_in
            fila.tokens_salida_max += max_out
            continue
        p = contexto.prompt(t, u.brazo)
        tin = (tok(p.system) + tok(p.user) + 10) * factor
        tout = min(u.max_tokens, ref_tokens * f_sal)
        fila.llamadas_generacion += 1
        fila.tokens_entrada += tin
        fila.tokens_entrada_max += tin
        fila.tokens_salida_esperados += tout
        fila.tokens_salida_max += u.max_tokens
    for fila in filas.values():
        ce = precios.costo(fila.proveedor, fila.modelo, fila.tokens_entrada, fila.tokens_salida_esperados)
        cm = precios.costo(fila.proveedor, fila.modelo, fila.tokens_entrada_max, fila.tokens_salida_max)
        fila.costo_esperado, fila.costo_maximo = ce, cm
    return Estimacion(filas=sorted(filas.values(), key=lambda f: (f.proveedor, f.modelo)))
