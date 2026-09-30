#!/usr/bin/env python3
"""Análisis de V6b (estudio controlado con personas) y generador de contrabalanceo.

Solo biblioteca estándar. No contiene datos: lee las sesiones que exporta la herramienta
``evidencia/v6/herramienta/sesion.html`` (JSON o CSV) y calcula, con las reglas del Plan de
Validación v3 (§9-10), lo que el plan fija. Subcomandos:

    contrabalanceo  --participantes N --semilla S [--pilotos 2] [--formato json|csv|tabla]
    puntuar-sus     ARCHIVO...            SUS por participante (2,5 x [Σ impares-1 + Σ 5-pares]) y resumen
    t1              ARCHIVO...            mediana y cuantiles de T1, tiempo agotado como CENSURADO
    exito           ARCHIVO...            tasa de éxito por tarea (Wilson 95 %)
    resumen         ARCHIVO...            todo lo anterior + exclusiones + metas, por estudio
    manifiesto      ARCHIVO... [--escribir]   manifiesto de corrida (mini-format/corrida/1); ver abajo

``ARCHIVO`` puede ser un .json (una sesión, una lista o {"sesiones": [...]}), un .csv plano o un
directorio con ambos. Los pilotos (tipo = piloto) y las sesiones marcadas valido = false NUNCA
entran en las cifras del estudio; se cuentan aparte.

Reglas fijadas ANTES de analizar (protocolo.md §9):
* Una tarea cuenta como lograda solo si el resultado es ``completa_sin_ayuda`` o ``completa_con_ayuda``.
  ``tiempo_agotado``, ``no_completa`` y ``abandono`` NO son éxito.
* Para medianas y cuantiles de tiempo, toda tarea no lograda se trata como CENSURADA: su tiempo es
  "mayor que el tope" (se ordena por encima de todos los tiempos observados). No se trunca al tope
  ni se descarta. Si un cuantil cae en una posición censurada, NO está determinado y la meta
  correspondiente no queda demostrada (se informa la cota inferior).
* Cuantiles con interpolación lineal (tipo 7: posición (n-1)·p), solo entre valores observados.
* SUS: formularios incompletos no se puntúan; IC 95 % con la t de Student.
* Metas del plan: SUS >= 70 (sobre la media), mediana de T1 .mini <= 30 min y >= 80 % de tareas
  logradas sin ayuda (criterio operativo adicional propuesto), con >= 8 participantes válidos.

``manifiesto`` NO ejecuta el estudio: solo convierte el análisis de datos REALES en un manifiesto
``participantes``; se niega con fixtures de prueba y con menos de una sesión válida de estudio.
"""
from __future__ import annotations

import argparse
import csv
import io
import json
import math
import os
import sys
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

# ------------------------------------------------------------------------------------------
# Constantes del protocolo (Plan v3, tabla T10: 30 + 30 + 15 + 10 + 15 = 100 min; sesión <= 120)
# ------------------------------------------------------------------------------------------
TAREAS = ("T1_json", "T1_mini", "T2", "T3", "T4")
TOPES_MIN = {"T1_json": 30, "T1_mini": 30, "T2": 15, "T3": 10, "T4": 15}
TOPES_S = {k: v * 60 for k, v in TOPES_MIN.items()}
RESULTADOS = ("completa_sin_ayuda", "completa_con_ayuda", "tiempo_agotado", "no_completa", "abandono")
LOGRADOS = ("completa_sin_ayuda", "completa_con_ayuda")
TIPOS = ("estudio", "piloto")
TIPOS_DATOS = ("participantes", "fixture_de_prueba")
MIN_VALIDOS = 8
META_SUS = 70.0
META_T1_MINI_MIN = 30.0
META_SIN_AYUDA = 0.80
TOLERANCIA_TOPE_S = 1.0

ESQUEMA_SESION = "mini-format/v6b-sesion/1"

# t de Student, dos colas 95 % (0,975), grados de libertad 1..30; después 40, 60, 120 y z.
T975 = {1: 12.706, 2: 4.303, 3: 3.182, 4: 2.776, 5: 2.571, 6: 2.447, 7: 2.365, 8: 2.306, 9: 2.262,
        10: 2.228, 11: 2.201, 12: 2.179, 13: 2.160, 14: 2.145, 15: 2.131, 16: 2.120, 17: 2.110,
        18: 2.101, 19: 2.093, 20: 2.086, 21: 2.080, 22: 2.074, 23: 2.069, 24: 2.064, 25: 2.060,
        26: 2.056, 27: 2.052, 28: 2.048, 29: 2.045, 30: 2.042}


class ErrorDatos(ValueError):
    """Datos de entrada inválidos (código de salida 2)."""


# ------------------------------------------------------------------------------------------
# Contrabalanceo determinista
# ------------------------------------------------------------------------------------------
# Cuatro secuencias = orden de condición (JSON primero / .mini primero) x qué variante de T1 (A o B)
# se resuelve con cada formato. Cada bloque de 4 participantes recibe las cuatro en orden aleatorio
# sembrado; un bloque parcial final conserva el equilibrio de orden y de variante en ±1.
SECUENCIAS = {
    "S1": {"orden_t1": "json_mini", "variante_json": "A", "variante_mini": "B"},
    "S2": {"orden_t1": "json_mini", "variante_json": "B", "variante_mini": "A"},
    "S3": {"orden_t1": "mini_json", "variante_json": "B", "variante_mini": "A"},
    "S4": {"orden_t1": "mini_json", "variante_json": "A", "variante_mini": "B"},
}
_M32 = 0xFFFFFFFF


def _imul(a: int, b: int) -> int:
    return (a * b) & _M32


def mulberry32(semilla: int):
    """Generador mulberry32 de 32 bits; devuelve una función que da floats en [0, 1).

    Es el mismo algoritmo que implementa ``sesion.html`` (``Math.imul`` y ``>>> 0``), de modo que
    Python y el navegador producen la misma asignación para la misma semilla."""
    estado = [semilla & _M32]

    def siguiente() -> float:
        a = (estado[0] + 0x6D2B79F5) & _M32
        estado[0] = a
        t = _imul(a ^ (a >> 15), a | 1)
        t = ((t + _imul(t ^ (t >> 7), t | 61)) & _M32) ^ t
        return ((t ^ (t >> 14)) & _M32) / 4294967296.0

    return siguiente


def _barajar(lista: Sequence[str], rnd) -> List[str]:
    a = list(lista)
    for i in range(len(a) - 1, 0, -1):
        j = int(rnd() * (i + 1))
        a[i], a[j] = a[j], a[i]
    return a


def _grupos(rnd) -> Tuple[List[str], List[str]]:
    """Dos parejas de secuencias (JSON primero, .mini primero) emparejadas para que, en cada par,
    los dos participantes resuelvan el JSON con variantes DISTINTAS: así cualquier prefijo del plan
    queda equilibrado tanto en orden como en variante (±1)."""
    g1 = _barajar(["S1", "S2"], rnd)                                   # JSON primero
    g2 = ["S3", "S4"] if SECUENCIAS["S3"]["variante_json"] != SECUENCIAS[g1[0]]["variante_json"] else ["S4", "S3"]
    return g1, g2


def _bloque(semilla: int, b: int) -> List[str]:
    rnd = mulberry32((semilla + 1000003 * (b + 1)) & _M32)
    g1, g2 = _grupos(rnd)
    if rnd() < 0.5:
        return [g1[0], g2[0], g1[1], g2[1]]
    return [g2[0], g1[0], g2[1], g1[1]]


def _pilotos(semilla: int, n: int) -> List[str]:
    rnd = mulberry32((semilla ^ 0x50494C4F) & _M32)
    g1, g2 = _grupos(rnd)
    base = [g1[0], g2[0]] if rnd() < 0.5 else [g2[0], g1[0]]
    return [base[i % 2] for i in range(n)]


def contrabalanceo(participantes: int, semilla: int, pilotos: int = 2) -> List[Dict[str, Any]]:
    """Plan de asignación: pilotos primero (PIL-xx) y luego los participantes del estudio (EST-xx)."""
    if not (1 <= participantes <= 200):
        raise ErrorDatos("--participantes debe estar entre 1 y 200")
    if not (0 <= pilotos <= 10):
        raise ErrorDatos("--pilotos debe estar entre 0 y 10")
    if not (0 <= semilla <= _M32):
        raise ErrorDatos("--semilla debe estar entre 0 y 4294967295")
    filas: List[Dict[str, Any]] = []
    for i, s in enumerate(_pilotos(semilla, pilotos), 1):
        filas.append({"codigo": f"PIL-{i:02d}", "tipo": "piloto", "bloque": None, "secuencia": s, **SECUENCIAS[s]})
    i = 0
    b = 0
    while i < participantes:
        for s in _bloque(semilla, b):
            if i >= participantes:
                break
            i += 1
            filas.append({"codigo": f"EST-{i:02d}", "tipo": "estudio", "bloque": b + 1, "secuencia": s, **SECUENCIAS[s]})
        b += 1
    return filas


# ------------------------------------------------------------------------------------------
# Estadística básica
# ------------------------------------------------------------------------------------------
def media(xs: Sequence[float]) -> Optional[float]:
    return sum(xs) / len(xs) if xs else None


def desv_muestral(xs: Sequence[float]) -> Optional[float]:
    if len(xs) < 2:
        return None
    m = sum(xs) / len(xs)
    return math.sqrt(sum((x - m) ** 2 for x in xs) / (len(xs) - 1))


def t_critico(gl: int) -> float:
    if gl < 1:
        raise ValueError("gl < 1")
    if gl in T975:
        return T975[gl]
    if gl <= 40:
        return 2.021
    if gl <= 60:
        return 2.000
    if gl <= 120:
        return 1.980
    return 1.960


def ic95_media(xs: Sequence[float]) -> Optional[Tuple[float, float]]:
    if len(xs) < 2:
        return None
    m = sum(xs) / len(xs)
    h = t_critico(len(xs) - 1) * desv_muestral(xs) / math.sqrt(len(xs))
    return (m - h, m + h)


def wilson(k: int, n: int, z: float = 1.959964) -> Optional[Tuple[float, float]]:
    if n <= 0:
        return None
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (max(0.0, c - h), min(1.0, c + h))


def cuantil_censurado(valores: Sequence[Optional[float]], p: float) -> Tuple[Optional[float], bool]:
    """Cuantil tipo 7 con observaciones censuradas (``None`` = mayor que todo lo observado).

    Devuelve (valor, determinado). Si alguno de los valores que intervienen es censurado, el cuantil
    no está determinado y el valor es ``None``."""
    n = len(valores)
    if n == 0:
        return None, False
    xs = sorted(valores, key=lambda v: (v is None, v if v is not None else 0.0))
    h = (n - 1) * p
    lo, hi = int(math.floor(h)), int(math.ceil(h))
    frac = h - lo
    if frac == 0 or lo == hi:
        v = xs[lo]
        return (v, True) if v is not None else (None, False)
    if xs[lo] is None or xs[hi] is None:
        return None, False
    return xs[lo] + frac * (xs[hi] - xs[lo]), True


# ------------------------------------------------------------------------------------------
# SUS
# ------------------------------------------------------------------------------------------
def puntuar_sus(respuestas: Sequence[Any]) -> Tuple[Optional[float], Optional[str]]:
    """(puntuación 0-100, motivo). Brooke (1996): impares (r-1), pares (5-r), suma x 2,5.

    Devuelve (None, motivo) si el formulario está incompleto o tiene valores fuera de 1-5."""
    if respuestas is None:
        return None, "sin respuestas"
    if len(respuestas) != 10:
        return None, f"se esperaban 10 respuestas y hay {len(respuestas)}"
    total = 0
    for i, r in enumerate(respuestas, 1):
        if r is None or r == "":
            return None, f"falta el ítem {i}"
        if isinstance(r, bool) or not isinstance(r, (int, float)) or int(r) != r or not 1 <= int(r) <= 5:
            return None, f"el ítem {i} debe ser un entero de 1 a 5"
        total += (int(r) - 1) if i % 2 == 1 else (5 - int(r))
    return total * 2.5, None


# ------------------------------------------------------------------------------------------
# Carga y validación de sesiones
# ------------------------------------------------------------------------------------------
def _num(x: Any) -> Optional[float]:
    if x is None or x == "":
        return None
    if isinstance(x, bool):
        raise ErrorDatos(f"valor numérico inválido: {x!r}")
    try:
        v = float(x)
    except (TypeError, ValueError):
        raise ErrorDatos(f"valor numérico inválido: {x!r}") from None
    if math.isnan(v) or math.isinf(v):
        raise ErrorDatos(f"valor numérico inválido: {x!r}")
    return v


def _bool(x: Any, defecto: bool = True) -> bool:
    if x is None or x == "":
        return defecto
    if isinstance(x, bool):
        return x
    s = str(x).strip().lower()
    if s in ("true", "1", "si", "sí", "yes"):
        return True
    if s in ("false", "0", "no"):
        return False
    raise ErrorDatos(f"valor booleano inválido: {x!r}")


def normalizar_sesion(d: Dict[str, Any], origen: str = "") -> Dict[str, Any]:
    """Lleva una sesión (forma JSON de la herramienta) a la forma interna y la valida."""
    e = lambda msg: ErrorDatos(f"{origen}: {msg}" if origen else msg)  # noqa: E731
    if not isinstance(d, dict):
        raise e("la sesión no es un objeto")
    p = d.get("participante") if isinstance(d.get("participante"), dict) else d
    codigo = p.get("codigo")
    if not isinstance(codigo, str) or not (2 <= len(codigo) <= 24) or any(c.isspace() or c == "@" for c in codigo):
        raise e("codigo de participante inválido (seudónimo de 2-24 caracteres, sin espacios ni '@')")
    tipo = p.get("tipo", "estudio")
    if tipo not in TIPOS:
        raise e(f"tipo debe ser uno de {TIPOS}")
    tipo_datos = d.get("tipo_datos", p.get("tipo_datos"))
    if tipo_datos not in TIPOS_DATOS:
        raise e(f"tipo_datos debe ser uno de {TIPOS_DATOS} (declara si son datos de participantes o un fixture de prueba)")
    plan = d.get("plan") if isinstance(d.get("plan"), dict) else d
    tareas_in = d.get("tareas") or {}
    if not isinstance(tareas_in, dict):
        raise e("'tareas' debe ser un objeto")
    tareas: Dict[str, Dict[str, Any]] = {}
    avisos: List[str] = []
    for t, reg in tareas_in.items():
        if t not in TAREAS:
            raise e(f"tarea desconocida: {t}")
        if not isinstance(reg, dict) or reg.get("resultado") in (None, ""):
            continue                                   # tarea sin registrar: no cuenta ni como éxito ni como fallo
        res = reg["resultado"]
        if res not in RESULTADOS:
            raise e(f"{t}: resultado debe ser uno de {RESULTADOS}")
        seg = _num(reg.get("segundos_activos", reg.get("segundos")))
        tope = _num(reg.get("tope_s"))
        if tope is not None and tope != TOPES_S[t]:
            raise e(f"{t}: tope_s={tope:g} no coincide con el del plan ({TOPES_S[t]} s)")
        ayudas = reg.get("ayudas", 0)
        n_ay = len(ayudas) if isinstance(ayudas, list) else int(_num(ayudas) or 0)
        if res in LOGRADOS:
            if seg is None or seg < 0:
                raise e(f"{t}: una tarea lograda necesita 'segundos' >= 0")
            if seg > TOPES_S[t] + TOLERANCIA_TOPE_S:
                raise e(f"{t}: {seg:g} s supera el tope de {TOPES_S[t]} s; una tarea que lo excede no es un éxito")
        if res == "completa_sin_ayuda" and n_ay > 0:
            raise e(f"{t}: marcada sin ayuda pero hay {n_ay} ayuda(s) registrada(s)")
        if res == "completa_con_ayuda" and n_ay == 0:
            avisos.append(f"{t}: marcada con ayuda pero sin ayudas registradas")
        tareas[t] = {"resultado": res, "segundos": seg if res in LOGRADOS else None, "ayudas": n_ay}
    sus_in = d.get("sus")
    if isinstance(sus_in, dict):
        resp, version = sus_in.get("respuestas"), sus_in.get("version_linguistica", sus_in.get("version"))
    else:
        resp, version = sus_in, None
    if resp is not None and not isinstance(resp, list):
        raise e("sus.respuestas debe ser una lista de 10 valores o null")
    return {
        "codigo": codigo, "tipo": tipo, "valido": _bool(d.get("valido", p.get("valido"))),
        "motivo_exclusion": d.get("motivo_exclusion", p.get("motivo_exclusion")) or None,
        "tipo_datos": tipo_datos, "perfil": p.get("perfil") or None, "lenguaje": p.get("lenguaje") or None,
        "orden_t1": plan.get("orden_t1") or None, "variante_json": plan.get("variante_json") or None,
        "variante_mini": plan.get("variante_mini") or None,
        "tareas": tareas, "sus": {"respuestas": resp, "version": version}, "avisos": avisos,
    }


def _fila_csv_a_sesion(fila: Dict[str, str]) -> Dict[str, Any]:
    tareas: Dict[str, Any] = {}
    for t in TAREAS:
        res = (fila.get(f"{t}_resultado") or "").strip()
        if res:
            tareas[t] = {"resultado": res, "segundos": fila.get(f"{t}_segundos"), "ayudas": fila.get(f"{t}_ayudas") or 0}
    q = [(fila.get(f"sus_q{i}") or "").strip() for i in range(1, 11)]
    if all(x == "" for x in q):
        resp = None
    else:
        resp = []
        for x in q:
            if x == "":
                resp.append(None)
            else:
                try:
                    resp.append(int(x) if float(x) == int(float(x)) else float(x))
                except ValueError:
                    resp.append(x)
    return {
        "participante": {"codigo": (fila.get("codigo") or "").strip(), "tipo": (fila.get("tipo") or "estudio").strip(),
                         "perfil": fila.get("perfil"), "lenguaje": fila.get("lenguaje")},
        "tipo_datos": (fila.get("tipo_datos") or "").strip(),
        "valido": fila.get("valido"), "motivo_exclusion": fila.get("motivo_exclusion"),
        "plan": {"orden_t1": fila.get("orden_t1"), "variante_json": fila.get("variante_json"),
                 "variante_mini": fila.get("variante_mini")},
        "tareas": tareas, "sus": {"respuestas": resp, "version_linguistica": fila.get("sus_version")},
    }


def _archivos(rutas: Iterable[os.PathLike]) -> List[Path]:
    out: List[Path] = []
    for r in rutas:
        p = Path(r)
        if p.is_dir():
            out += sorted(x for x in p.rglob("*") if x.suffix.lower() in (".json", ".csv") and x.is_file())
        elif p.is_file():
            out.append(p)
        else:
            raise ErrorDatos(f"no existe: {p}")
    if not out:
        raise ErrorDatos("no se encontró ningún archivo .json o .csv de sesiones")
    return out


def cargar_sesiones(rutas: Iterable[os.PathLike]) -> List[Dict[str, Any]]:
    sesiones: List[Dict[str, Any]] = []
    for p in _archivos(rutas):
        if p.suffix.lower() == ".csv":
            with open(p, encoding="utf-8-sig", newline="") as fh:
                for i, fila in enumerate(csv.DictReader(fh), 2):
                    sesiones.append(normalizar_sesion(_fila_csv_a_sesion(fila), f"{p.name} fila {i}"))
        else:
            try:
                obj = json.loads(p.read_text(encoding="utf-8-sig"))
            except ValueError as e:
                raise ErrorDatos(f"{p.name}: JSON inválido ({e})") from None
            lista = obj["sesiones"] if isinstance(obj, dict) and "sesiones" in obj else (obj if isinstance(obj, list) else [obj])
            for k, s in enumerate(lista, 1):
                sesiones.append(normalizar_sesion(s, f"{p.name}[{k}]"))
    codigos = [s["codigo"] for s in sesiones]
    dup = sorted({c for c in codigos if codigos.count(c) > 1})
    if dup:
        raise ErrorDatos(f"códigos de participante repetidos: {', '.join(dup)}")
    tipos = {s["tipo_datos"] for s in sesiones}
    if len(tipos) > 1:
        raise ErrorDatos("no se pueden mezclar fixtures de prueba con datos de participantes en un mismo análisis")
    return sesiones


# ------------------------------------------------------------------------------------------
# Análisis
# ------------------------------------------------------------------------------------------
def particion(sesiones: Sequence[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
    """Separa las sesiones: estudio válido, pilotos (excluidos) e inválidas (excluidas)."""
    out: Dict[str, List[Dict[str, Any]]] = {"estudio": [], "pilotos": [], "invalidos": []}
    for s in sesiones:
        if s["tipo"] == "piloto":
            out["pilotos"].append(s)
        elif not s["valido"]:
            out["invalidos"].append(s)
        else:
            out["estudio"].append(s)
    return out


def analizar_sus(estudio: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    filas, punt = [], []
    for s in estudio:
        v, motivo = puntuar_sus(s["sus"]["respuestas"])
        filas.append({"codigo": s["codigo"], "sus": v, "motivo_no_puntuado": motivo})
        if v is not None:
            punt.append(v)
    n = len(punt)
    ic = ic95_media(punt)
    m = media(punt)
    if n == 0:
        decision = "sin_datos"
    elif n < MIN_VALIDOS:
        decision = "muestra_insuficiente"
    else:
        decision = "meta_observada" if m >= META_SUS else "meta_no_observada"
    return {
        "n_puntuados": n, "n_estudio": len(estudio), "media": m, "desv_muestral": desv_muestral(punt),
        "ic95": list(ic) if ic else None, "minimo": min(punt) if punt else None, "maximo": max(punt) if punt else None,
        "meta": META_SUS, "regla_meta": "media >= 70 con >= 8 formularios completos de participantes válidos",
        "limite_inferior_supera_meta": (ic[0] >= META_SUS) if ic else None,
        "decision": decision, "participantes": filas,
    }


def _tiempos_min(estudio: Sequence[Dict[str, Any]], tarea: str, estricto: bool = False) -> List[Optional[float]]:
    """Minutos de cada participante que intentó la tarea; ``None`` = no lograda (censurada)."""
    v: List[Optional[float]] = []
    for s in estudio:
        r = s["tareas"].get(tarea)
        if r is None:
            continue
        ok = r["resultado"] in LOGRADOS and not (estricto and r["resultado"] == "completa_con_ayuda")
        v.append(r["segundos"] / 60.0 if ok else None)
    return v


def _resumen_tiempos(vals: Sequence[Optional[float]], tope_min: float) -> Dict[str, Any]:
    fin = sorted(v for v in vals if v is not None)
    med, det = cuantil_censurado(vals, 0.5)
    q1, d1 = cuantil_censurado(vals, 0.25)
    q3, d3 = cuantil_censurado(vals, 0.75)
    sust = [tope_min if v is None else v for v in vals]       # cota inferior: lo no logrado vale al menos el tope
    cota_med, _ = cuantil_censurado(sust, 0.5)
    return {
        "n": len(vals), "n_logradas": len(fin), "n_censuradas": len(vals) - len(fin), "tope_min": tope_min,
        "mediana_min": med, "mediana_determinada": det if vals else False,
        "mediana_cota_inferior_min": cota_med if vals else None,
        "q1_min": q1, "q1_determinado": d1 if vals else False, "q3_min": q3, "q3_determinado": d3 if vals else False,
        "minimo_logrado_min": fin[0] if fin else None, "maximo_logrado_min": fin[-1] if fin else None,
    }


def analizar_t1(estudio: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    out: Dict[str, Any] = {"regla_censura": "tarea no lograda (tiempo agotado, no completa, abandono) = censurada: "
                                            "tiempo > tope; ni se trunca al tope ni se descarta"}
    for cond in ("T1_json", "T1_mini"):
        out[cond] = _resumen_tiempos(_tiempos_min(estudio, cond), TOPES_MIN[cond])
        out[cond]["sensibilidad_ayuda_cuenta_como_fallo"] = _resumen_tiempos(_tiempos_min(estudio, cond, True), TOPES_MIN[cond])
    m = out["T1_mini"]
    if m["n"] == 0:
        meta = "sin_datos"
    elif m["n"] < MIN_VALIDOS:
        meta = "muestra_insuficiente"
    elif not m["mediana_determinada"]:
        meta = "no_demostrada_por_censura"
    else:
        meta = "meta_observada" if m["mediana_min"] <= META_T1_MINI_MIN else "meta_no_observada"
    out["meta_mediana_mini"] = {"umbral_min": META_T1_MINI_MIN, "estado": meta,
                                "regla": "mediana (promedio de los dos centrales si n es par) <= 30 min; indeterminada = no demostrada"}
    pares, con_cens = [], 0
    for s in estudio:
        a, b = s["tareas"].get("T1_json"), s["tareas"].get("T1_mini")
        if a is None or b is None:
            continue
        if a["resultado"] in LOGRADOS and b["resultado"] in LOGRADOS:
            pares.append((b["segundos"] - a["segundos"]) / 60.0)
        else:
            con_cens += 1
    pares.sort()
    n = len(pares)
    med = None if n == 0 else (pares[n // 2] if n % 2 else (pares[n // 2 - 1] + pares[n // 2]) / 2)
    out["diferencias_pareadas"] = {
        "definicion": "minutos(.mini) - minutos(JSON) solo en participantes que lograron ambas condiciones",
        "n_pares": n, "n_pares_con_censura_excluidos_de_este_calculo": con_cens,
        "mediana_diferencia_min": med, "minimo": pares[0] if pares else None, "maximo": pares[-1] if pares else None,
        "nota": "descriptivo; los pares con una condición censurada no se imputan y se cuentan aparte",
    }
    return out


def analizar_exito(estudio: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    por: Dict[str, Any] = {}
    tot_n = tot_sin = tot_log = 0
    for t in TAREAS:
        regs = [s["tareas"][t] for s in estudio if t in s["tareas"]]
        n = len(regs)
        log = sum(1 for r in regs if r["resultado"] in LOGRADOS)
        sin = sum(1 for r in regs if r["resultado"] == "completa_sin_ayuda")
        por[t] = {
            "n_intentos": n, "sin_registro": len(estudio) - n, "logradas": log, "sin_ayuda": sin,
            "tasa_exito": (log / n) if n else None, "tasa_exito_ic95_wilson": list(wilson(log, n)) if n else None,
            "tasa_sin_ayuda": (sin / n) if n else None, "tasa_sin_ayuda_ic95_wilson": list(wilson(sin, n)) if n else None,
            "por_resultado": {r: sum(1 for x in regs if x["resultado"] == r) for r in RESULTADOS},
        }
        tot_n += n
        tot_sin += sin
        tot_log += log
    tasa = (tot_sin / tot_n) if tot_n else None
    return {
        "por_tarea": por,
        "global": {"n_intentos": tot_n, "logradas": tot_log, "sin_ayuda": tot_sin, "tasa_sin_ayuda": tasa,
                   "tasa_sin_ayuda_ic95_wilson": list(wilson(tot_sin, tot_n)) if tot_n else None,
                   "meta": META_SIN_AYUDA, "meta_estado": ("sin_datos" if tasa is None else ("meta_observada" if tasa >= META_SIN_AYUDA else "meta_no_observada")),
                   "nota": "criterio operativo adicional propuesto en el Plan v3 (P93), no un resultado observado"},
    }


def resumen(sesiones: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    p = particion(sesiones)
    est = p["estudio"]
    fixture = bool(sesiones) and sesiones[0]["tipo_datos"] == "fixture_de_prueba"
    sus, t1, ex = analizar_sus(est), analizar_t1(est), analizar_exito(est)
    metas = {"sus": sus["decision"], "mediana_t1_mini": t1["meta_mediana_mini"]["estado"], "sin_ayuda": ex["global"]["meta_estado"]}
    suficiente = len(est) >= MIN_VALIDOS
    avisos = [a for s in sesiones for a in s["avisos"]]
    if fixture:
        avisos.insert(0, "FIXTURE DE PRUEBA: estos números NO son resultados de participantes")
    return {
        "esquema": "mini-format/v6b-resumen/1", "estudio": "V6b",
        "es_fixture": fixture, "tipo_datos": sesiones[0]["tipo_datos"] if sesiones else None,
        "exclusiones": {
            "pilotos_excluidos": [s["codigo"] for s in p["pilotos"]], "n_pilotos_excluidos": len(p["pilotos"]),
            "invalidos_excluidos": [{"codigo": s["codigo"], "motivo": s["motivo_exclusion"]} for s in p["invalidos"]],
        },
        "n_validos_estudio": len(est), "minimo_requerido": MIN_VALIDOS, "muestra_suficiente": suficiente,
        "sus": sus, "t1": t1, "exito": ex, "metas": metas,
        "todas_las_metas_observadas": suficiente and all(v in ("meta_observada",) for v in metas.values()),
        "avisos": avisos,
    }


# ------------------------------------------------------------------------------------------
# Manifiesto de corrida (evidencia_lib)
# ------------------------------------------------------------------------------------------
CRITERIO_V6B = ("SUS (media) >= 70; mediana de T1 .mini <= 30 min con las tareas no logradas como censuradas "
                "(indeterminada = no demostrada); >= 80 % de tareas logradas sin ayuda; >= 8 participantes "
                "válidos de estudio, sin pilotos. Interpretación fijada en evidencia/v6/protocolo.md §9 antes de analizar.")


def construir_manifiesto(sesiones: Sequence[Dict[str, Any]], rutas: Sequence[Path], comando: str) -> Dict[str, Any]:
    r = resumen(sesiones)
    if r["es_fixture"]:
        raise ErrorDatos("los fixtures de prueba no se registran como corrida")
    if r["n_validos_estudio"] < 1:
        raise ErrorDatos("no hay ninguna sesión válida de estudio que registrar")
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import evidencia_lib as ev  # noqa: E402
    suficiente = r["muestra_suficiente"]
    metas = r["metas"]
    if not suficiente:
        resultado = "no_evaluable"
    elif r["todas_las_metas_observadas"]:
        resultado = "cumple"
    else:
        resultado = "no_cumple"
    m = ev.nueva_corrida(
        "V6b", "participantes", comando,
        conjuntos=[ev.referencia_archivo(p) for p in rutas if p.is_file()],
        resumen={k: r[k] for k in ("n_validos_estudio", "muestra_suficiente", "metas", "exclusiones")},
        criterio=CRITERIO_V6B,
        estado_ejecucion="ejecutado" if suficiente else "parcial", resultado=resultado,
        limitaciones=["muestra por conveniencia; predominio de estudiantes", "contrabalanceo reduce pero no elimina el aprendizaje",
                      "los datos de sesión viven en evidencia/restringida/ (no se publican)"],
        notas="Generado por tools/analizar_v6.py manifiesto; los datos individuales no forman parte del manifiesto.",
    )
    return m


# ------------------------------------------------------------------------------------------
# CLI
# ------------------------------------------------------------------------------------------
def _json(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False, indent=2, sort_keys=False) + "\n"


def _csv(filas: Sequence[Dict[str, Any]]) -> str:
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=list(filas[0].keys()), lineterminator="\n")
    w.writeheader()
    for f in filas:
        w.writerow({k: ("" if v is None else v) for k, v in f.items()})
    return buf.getvalue()


def _tabla(filas: Sequence[Dict[str, Any]]) -> str:
    cols = list(filas[0].keys())
    ancho = {c: max(len(c), *(len(str("" if f[c] is None else f[c])) for f in filas)) for c in cols}
    lin = ["  ".join(c.ljust(ancho[c]) for c in cols), "  ".join("-" * ancho[c] for c in cols)]
    lin += ["  ".join(str("" if f[c] is None else f[c]).ljust(ancho[c]) for c in cols) for f in filas]
    return "\n".join(lin) + "\n"


def _salida(texto: str, destino: Optional[str]) -> None:
    if destino:
        with open(destino, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(texto)
    else:
        sys.stdout.write(texto)


def main(argv: Optional[Sequence[str]] = None) -> int:
    for flujo in (sys.stdout, sys.stderr):                     # UTF-8 también en consolas de Windows
        if hasattr(flujo, "reconfigure"):
            flujo.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(prog="analizar_v6", description="Análisis de V6b y contrabalanceo")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("contrabalanceo", help="asignación determinista de orden y variante de T1")
    p.add_argument("--participantes", type=int, required=True, help="participantes del estudio (sin contar pilotos)")
    p.add_argument("--semilla", type=int, required=True)
    p.add_argument("--pilotos", type=int, default=2)
    p.add_argument("--formato", choices=("json", "csv", "tabla"), default="tabla")
    p.add_argument("--salida")
    for nombre in ("puntuar-sus", "t1", "exito", "resumen", "manifiesto"):
        q = sub.add_parser(nombre)
        q.add_argument("archivos", nargs="+")
        q.add_argument("--salida")
        if nombre == "puntuar-sus":
            q.add_argument("--formato", choices=("json", "csv"), default="json")
        if nombre == "manifiesto":
            q.add_argument("--escribir", action="store_true", help="guardar en evidencia/corridas/<run_id>/")
    args = ap.parse_args(argv)
    try:
        if args.cmd == "contrabalanceo":
            filas = contrabalanceo(args.participantes, args.semilla, args.pilotos)
            texto = {"json": lambda: _json({"semilla": args.semilla, "participantes": args.participantes,
                                             "pilotos": args.pilotos, "asignaciones": filas}),
                     "csv": lambda: _csv(filas), "tabla": lambda: _tabla(filas)}[args.formato]()
            _salida(texto, args.salida)
            return 0
        sesiones = cargar_sesiones(args.archivos)
        est = particion(sesiones)["estudio"]
        if args.cmd == "puntuar-sus":
            r = analizar_sus(est)
            if args.formato == "csv":
                _salida(_csv(r["participantes"]) if r["participantes"] else "", args.salida)
            else:
                _salida(_json(r), args.salida)
        elif args.cmd == "t1":
            _salida(_json(analizar_t1(est)), args.salida)
        elif args.cmd == "exito":
            _salida(_json(analizar_exito(est)), args.salida)
        elif args.cmd == "resumen":
            _salida(_json(resumen(sesiones)), args.salida)
        elif args.cmd == "manifiesto":
            rutas = _archivos(args.archivos)
            m = construir_manifiesto(sesiones, rutas, "python tools/analizar_v6.py manifiesto " + " ".join(args.archivos))
            if args.escribir:
                import evidencia_lib as ev
                ruta = ev.guardar_corrida(m)
                sys.stdout.write(f"escrito {ruta}\n")
            else:
                _salida(_json(m), args.salida)
        return 0
    except ErrorDatos as e:
        print(f"error de datos: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
