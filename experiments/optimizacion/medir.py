"""Medición de tokens por dominio, perfil, tokenizador y tamaño de lote.

Cada texto se tokeniza ENTERO. El total de una respuesta con su instrucción es el conteo del texto
``instruccion + "\\n\\n" + salida`` (un solo texto), nunca la suma de dos conteos. Antes de contar
nada se verifica la ida y vuelta exacta del perfil sobre el lote: si falla, el perfil se descarta
para ese lote y se anota (``fallos``), no se compara.
"""
from __future__ import annotations

import statistics
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from . import datos, diseno, perfiles, tokenizadores
from .dominios import Dominio, dominios
from .especializacion import Especializacion, NoEquivalente, comprobar_equivalencia

TAMANOS = (1, 5, 10, 25, 50, 100, 250)
NMAX_EQUILIBRIO = 250
SEPARADOR = "\n\n"

# (perfil, variante de instrucción) que se miden. La clave 'ninguna' = instrucción de 0 tokens.
COMBINACIONES: List[Tuple[str, str]] = [
    ("json_compacto", "ninguna"), ("json_compacto", "schema_sin_ejemplo"), ("json_compacto", "schema_con_ejemplo"),
    ("json_legible", "ninguna"), ("json_abreviado", "ninguna"),
    ("general_fromschema", "sin_ejemplo"), ("general_fromschema", "con_ejemplo"),
    ("general_dominio", "sin_ejemplo"), ("general_dominio", "con_ejemplo"),
    ("especializado", "compacta_sin_ejemplo"), ("especializado", "compacta_con_ejemplo"),
    ("especializado", "spec_block_sin_ejemplo"), ("especializado", "spec_block_con_ejemplo"),
]
PRIMARIO_ESPECIALIZADO = ("especializado", "compacta_con_ejemplo")
PRIMARIO_GENERAL = ("general_fromschema", "con_ejemplo")
PRIMARIO_JSON = ("json_compacto", "ninguna")


@dataclass
class Preparado:
    dom: Dominio
    esp: Especializacion
    contrato_dom: Dict[str, Any]
    instr: Dict[str, Dict[str, str]]          # perfil -> variante -> texto
    muestras_dom: int

    def instruccion(self, perfil: str, variante: str) -> str:
        if perfil.startswith("json"):
            return "" if variante == "ninguna" else self.instr["json"][variante.replace("schema_", "")]
        return self.instr[perfil][variante]

    def salida(self, perfil: str, registros: Sequence[Dict[str, Any]]) -> str:
        d = self.dom
        if perfil == "json_compacto":
            return perfiles.json_compacto(d, registros)
        if perfil == "json_legible":
            return perfiles.json_legible(d, registros)
        if perfil == "json_abreviado":
            return perfiles.json_abreviado(self.esp, registros)
        if perfil == "general_fromschema":
            return perfiles.salida_general(d, registros)
        if perfil == "general_dominio":
            return perfiles.salida_dominio(d, self.contrato_dom, registros)
        if perfil == "especializado":
            return perfiles.salida_especializada(self.esp, registros)
        raise ValueError(perfil)

    def verificar(self, perfil: str, registros: Sequence[Dict[str, Any]]) -> None:
        d = self.dom
        if perfil == "json_abreviado":
            perfiles.verificar_json_abreviado(self.esp, registros)
            return
        if perfil.startswith("json"):
            return
        if perfil == "general_fromschema":
            perfiles.verificar_general(d, registros)
        elif perfil == "general_dominio":
            perfiles.verificar_dominio(d, self.contrato_dom, registros)
        elif perfil == "especializado":
            comprobar_equivalencia(self.esp, registros)
        else:
            raise ValueError(perfil)


def preparar(dom_id: str) -> Preparado:
    dom = dominios()[dom_id]
    esp = diseno.especializacion_de(dom_id)
    dev = dom.generar(datos.SEMILLA_DESARROLLO, 0, perfiles.MUESTRAS_DOMINIO)
    cd = perfiles.contrato_dominio(dom, dev)
    instr = perfiles.instrucciones(dom, esp, cd, dev)
    return Preparado(dom, esp, cd, instr, len(dev))


def _verificados(prep: Preparado, registros, fallos: List[Dict[str, Any]], contexto: Dict[str, Any]) -> Dict[str, bool]:
    """Perfiles que reconstruyen el lote; los que no, se anotan en ``fallos`` y se excluyen."""
    ok: Dict[str, bool] = {}
    for perfil in perfiles.PERFILES:
        try:
            prep.verificar(perfil, registros)
            ok[perfil] = True
        except Exception as e:          # noqa: BLE001 - se registra el motivo, no se oculta
            ok[perfil] = False
            fallos.append({**contexto, "perfil": perfil, "tipo": type(e).__name__, "motivo": str(e)[:300]})
    return ok


def medir_lote(prep: Preparado, registros: Sequence[Dict[str, Any]], fallos: List[Dict[str, Any]],
               contexto: Dict[str, Any], tok: Optional[Dict[str, Any]] = None,
               combinaciones: Sequence[Tuple[str, str]] = COMBINACIONES) -> List[Dict[str, Any]]:
    """Filas (una por tokenizador × combinación) de un lote."""
    tok = tok or tokenizadores.todos()
    ok = _verificados(prep, registros, fallos, contexto)
    filas: List[Dict[str, Any]] = []
    salidas: Dict[str, str] = {}
    for perfil, var in combinaciones:
        if not ok.get(perfil):
            continue
        if perfil not in salidas:
            salidas[perfil] = prep.salida(perfil, registros)
        s = salidas[perfil]
        instr = prep.instruccion(perfil, var)
        for nombre, t in tok.items():
            t_salida = t.contar(s)
            t_instr = t.contar(instr) if instr else 0
            t_total = t.contar(instr + SEPARADOR + s) if instr else t_salida
            filas.append({**contexto, "tokenizador": nombre, "perfil": perfil, "instruccion": var,
                          "tokens_salida": t_salida, "tokens_instruccion": t_instr, "tokens_total": t_total,
                          "caracteres_salida": len(s), "bytes_salida": len(s.encode("utf-8"))})
    return filas


def medir_dominio(dom_id: str, tamanos: Iterable[int] = TAMANOS, semilla: int = datos.SEMILLA_PRUEBA,
                  prep: Optional[Preparado] = None) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], Preparado]:
    prep = prep or preparar(dom_id)
    filas: List[Dict[str, Any]] = []
    fallos: List[Dict[str, Any]] = []
    tok = tokenizadores.todos()
    for n in tamanos:
        for lote in range(prep.dom.lotes_maximos(n)):
            regs = prep.dom.generar(semilla, lote, n)
            ctx = {"dominio": dom_id, "n": n, "lote": lote}
            filas += medir_lote(prep, regs, fallos, ctx, tok)
    return filas, fallos, prep


# ---------------------------------------------------------------------------- agregación
def agregar(filas: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Media (y mín/máx del total) sobre los lotes de cada (dominio, tokenizador, n, perfil, instrucción)."""
    grupos: Dict[tuple, List[Dict[str, Any]]] = {}
    for f in filas:
        grupos.setdefault((f["dominio"], f["tokenizador"], f["n"], f["perfil"], f["instruccion"]), []).append(f)
    out = []
    for (dom, tk, n, perfil, instr), fs in sorted(grupos.items()):
        m = lambda k: statistics.fmean(x[k] for x in fs)
        out.append({"dominio": dom, "tokenizador": tk, "n": n, "perfil": perfil, "instruccion": instr, "lotes": len(fs),
                    "salida": m("tokens_salida"), "instruccion_tokens": m("tokens_instruccion"), "total": m("tokens_total"),
                    "total_min": min(x["tokens_total"] for x in fs), "total_max": max(x["tokens_total"] for x in fs),
                    "caracteres_salida": m("caracteres_salida")})
    return out


def _indice(agr: List[Dict[str, Any]]) -> Dict[tuple, Dict[str, Any]]:
    return {(a["dominio"], a["tokenizador"], a["n"], a["perfil"], a["instruccion"]): a for a in agr}


def comparar(agr: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Ahorros frente a JSON compacto, por combinación.

    * ahorro_salida_pct: 1 - salida(mini) / salida(json compacto).
    * ahorro_total_pct (lectura primaria): 1 - total(mini con su instrucción) / total(json compacto, instrucción 0).
    * ahorro_total_con_esquema_pct: frente a JSON con instrucción (JSON Schema compacto) de la misma variante
      (con/sin ejemplo) que la del perfil mini.
    * ahorro_salida_vs_json_abreviado_pct (solo especializado): el mismo cálculo frente a JSON con las mismas abreviaturas.
    * costo_instruccion_extra: tokens de la instrucción mini menos los de la instrucción JSON de esa variante.
    Positivo = .mini usa menos tokens.
    """
    ix = _indice(agr)
    out = []
    for a in agr:
        if a["perfil"].startswith("json"):
            continue
        k0 = (a["dominio"], a["tokenizador"], a["n"])
        ab = ix.get(k0 + ("json_abreviado", "ninguna")) if a["perfil"] == "especializado" else None
        base = ix.get(k0 + PRIMARIO_JSON)
        if base is None:
            continue
        con_ej = a["instruccion"].endswith("con_ejemplo")
        jes = ix.get(k0 + ("json_compacto", "schema_con_ejemplo" if con_ej else "schema_sin_ejemplo"))
        out.append({
            "dominio": a["dominio"], "tokenizador": a["tokenizador"], "n": a["n"], "perfil": a["perfil"],
            "instruccion": a["instruccion"], "lotes": a["lotes"],
            "json_compacto_salida": base["salida"], "mini_salida": a["salida"],
            "ahorro_salida_pct": 100 * (1 - a["salida"] / base["salida"]),
            "json_compacto_total_sin_instruccion": base["total"], "mini_instruccion": a["instruccion_tokens"],
            "mini_total": a["total"],
            "ahorro_total_pct": 100 * (1 - a["total"] / base["total"]),
            "json_instruccion_esquema": jes["instruccion_tokens"] if jes else None,
            "json_total_con_esquema": jes["total"] if jes else None,
            "ahorro_total_con_esquema_pct": 100 * (1 - a["total"] / jes["total"]) if jes else None,
            "costo_instruccion_extra": a["instruccion_tokens"] - (jes["instruccion_tokens"] if jes else 0),
            "json_abreviado_salida": ab["salida"] if ab else None,
            "ahorro_salida_vs_json_abreviado_pct": 100 * (1 - a["salida"] / ab["salida"]) if ab else None,
        })
    return out


# ---------------------------------------------------------------------------- punto de equilibrio
def curva(dom_id: str, prep: Preparado, nmax: int = NMAX_EQUILIBRIO, semilla: int = datos.SEMILLA_PRUEBA,
          fallos: Optional[List[Dict[str, Any]]] = None) -> List[Dict[str, Any]]:
    """Filas de n = 1..nmax del lote 0 (lotes anidados: el de n es prefijo del de n+1)."""
    tok = tokenizadores.todos()
    todos = prep.dom.generar(semilla, 0, nmax)
    fallos = fallos if fallos is not None else []
    filas: List[Dict[str, Any]] = []
    combos = [c for c in COMBINACIONES if c[0] != "json_legible"]
    for n in range(1, nmax + 1):
        filas += medir_lote(prep, todos[:n], fallos, {"dominio": dom_id, "n": n, "lote": 0}, tok, combos)
    return filas


def equilibrios(filas_curva: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """n* por (dominio, tokenizador, perfil, instrucción, comparador).

    n* = menor n tal que el .mini gasta MENOS que el JSON para TODO lote m en [n, nmax] (cruce persistente).
    ``null`` si no existe en ese rango; en ese caso se da la pendiente medida entre n=100 y n=nmax y, solo si
    el ahorro por registro es positivo, el n extrapolado (marcado como extrapolación, no medido).
    Comparadores: ``salida`` (payload frente a JSON compacto), ``total`` (instrucción + salida frente a JSON con
    instrucción 0), ``total_con_esquema`` (frente a JSON con esquema de la misma variante de ejemplo).
    """
    ix = {(f["dominio"], f["tokenizador"], f["n"], f["perfil"], f["instruccion"]): f for f in filas_curva}
    doms = sorted({f["dominio"] for f in filas_curva})
    toks = sorted({f["tokenizador"] for f in filas_curva})
    nmax = max(f["n"] for f in filas_curva)
    out = []
    for dom in doms:
        for tk in toks:
            salida_hecha = set()
            for (perfil, var) in [c for c in COMBINACIONES if not c[0].startswith("json")]:
                for comp in ("salida", "total", "total_con_esquema"):
                    if comp == "salida":
                        if perfil in salida_hecha:
                            continue                     # la salida no depende de la instrucción: una sola fila por perfil
                        salida_hecha.add(perfil)
                    con_ej = var.endswith("con_ejemplo")
                    diffs = []
                    for n in range(1, nmax + 1):
                        m = ix.get((dom, tk, n, perfil, var))
                        if m is None:
                            diffs = []
                            break
                        if comp == "salida":
                            j = ix[(dom, tk, n, "json_compacto", "ninguna")]["tokens_salida"]
                            diffs.append(j - m["tokens_salida"])
                        elif comp == "total":
                            j = ix[(dom, tk, n, "json_compacto", "ninguna")]["tokens_total"]
                            diffs.append(j - m["tokens_total"])
                        else:
                            j = ix[(dom, tk, n, "json_compacto", "schema_con_ejemplo" if con_ej else "schema_sin_ejemplo")]["tokens_total"]
                            diffs.append(j - m["tokens_total"])
                    if not diffs:
                        continue
                    n_estrella = None
                    for i in range(len(diffs) - 1, -1, -1):
                        if diffs[i] > 0:
                            n_estrella = i + 1
                        else:
                            break
                    primer = next((i + 1 for i, d in enumerate(diffs) if d > 0), None)
                    pend = (diffs[-1] - diffs[99]) / (nmax - 100) if nmax > 100 else None
                    extr = None
                    if n_estrella is None and pend is not None and pend > 0 and diffs[-1] <= 0:
                        extr = round(nmax + (-diffs[-1]) / pend, 1)
                    out.append({"dominio": dom, "tokenizador": tk, "perfil": perfil,
                                "instruccion": "no_aplica" if comp == "salida" else var, "comparador": comp,
                                "n_estrella": n_estrella, "primer_n_con_ahorro": primer,
                                "ahorro_tokens_en_nmax": diffs[-1], "pendiente_ahorro_por_registro": None if pend is None else round(pend, 3),
                                "n_extrapolado_no_medido": extr, "nmax_medido": nmax,
                                "existe": n_estrella is not None})
    return out
