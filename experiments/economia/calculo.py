"""Economía de .mini frente a JSON: razón de tokens, ahorro, costo por categorías,
costo por mil registros válidos, escenarios A y B y punto de equilibrio.

Solo biblioteca estándar y funciones puras (sin red, sin reloj, sin archivos).
Su espejo es ``sitio/economia-calculo.js``: ambos deben dar EXACTAMENTE las mismas
cadenas para las mismas entradas (lo prueban los vectores de
``evidencia/vectores/economia.json``).

Política numérica (fija y documentada)
--------------------------------------
* Aritmética RACIONAL EXACTA con enteros (``fractions.Fraction``): no hay ``float``
  en ninguna cuenta. Los decimales entran como CADENAS (``"0.075"``) o enteros; un
  ``float`` se rechaza con ``TypeError`` (``0.1`` no es representable y daría
  resultados distintos en cada lenguaje).
* El redondeo ocurre UNA sola vez por cifra de salida, sobre el valor exacto, con
  ROUND_HALF_UP (los empates se van al valor de mayor magnitud: 0.5 -> 1, -0.5 -> -1).
  Decimales de salida: USD 6 (USD 9 para los diferenciales por registro del punto de
  equilibrio), porcentajes 4, razones 6, lotes fraccionarios 4, tokens y registros
  contables 0. Las cantidades contables (lotes posibles, registros útiles, tokens de
  capacidad) se redondean hacia ABAJO: no se prometen lotes ni registros parciales.
* Los lotes posibles se calculan con el costo exacto por lote, no con el costo ya
  redondeado que se muestra.
* Nada se inventa: sin tarifa verificada, o con un precio ausente para una categoría
  que sí se usó, el costo es ``None`` con ``estado`` y ``motivo`` explícitos; un dato
  de usage ausente es ``None`` ("no informado"), nunca 0.

Las salidas son diccionarios de cadenas decimales, ``None``, booleanos y listas; los
grupos van en LISTA (orden de primera aparición) para que el orden sea el mismo en
Python y en JavaScript.
"""
from __future__ import annotations

import re
from decimal import Decimal
from fractions import Fraction
from typing import Any, Dict, List, Optional, Tuple

MILLON = 1_000_000

DEC_USD = 6
DEC_USD_FINO = 9
DEC_PCT = 4
DEC_RAZON = 6
DEC_LOTES = 4

POLITICA = {
    "aritmetica": "racional exacta (enteros); sin float",
    "redondeo": "ROUND_HALF_UP (empates hacia la mayor magnitud), una vez por cifra de salida",
    "decimales": {"usd": DEC_USD, "usd_fino": DEC_USD_FINO, "porcentaje": DEC_PCT,
                  "razon": DEC_RAZON, "lotes": DEC_LOTES, "tokens": 0},
    "cantidades_contables": "hacia abajo (floor)",
}

AVISO_PROYECCION_ES = ("Proyección aritmética según la proporción medida; no es la respuesta real "
                       "de un modelo con un millón de tokens.")
AVISO_PROYECCION_EN = ("Arithmetic projection from the measured ratio; it is not the real response "
                       "of a model producing one million tokens.")
AVISO_PRESUPUESTO_ES = ("El presupuesto es un valor ilustrativo de la interfaz: no autoriza gastar nada "
                        "ni implica que exista ese dinero.")
AVISO_PRESUPUESTO_EN = ("The budget is an illustrative interface value: it does not authorize spending "
                        "anything nor imply that the money exists.")

_DEC = re.compile(r"^[+-]?\d+(?:\.\d+)?$")
_ENT = re.compile(r"^\d+$")


# ------------------------------------------------------------------ números
def a_fraccion(x: Any, campo: str = "valor") -> Fraction:
    """Convierte una entrada decimal exacta (int, cadena decimal, Decimal o Fraction)."""
    if isinstance(x, bool) or isinstance(x, float):
        raise TypeError(f"{campo}: no se admite float ni bool; use una cadena decimal (p. ej. \"0.075\")")
    if isinstance(x, int):
        return Fraction(x)
    if isinstance(x, Fraction):
        return x
    if isinstance(x, Decimal):
        if not x.is_finite():
            raise ValueError(f"{campo}: no finito")
        return Fraction(x)
    if isinstance(x, str):
        s = x.strip()
        if not _DEC.match(s):
            raise ValueError(f"{campo}: cadena decimal inválida {x!r}")
        return Fraction(s)
    raise TypeError(f"{campo}: tipo no admitido {type(x).__name__}")


def _no_neg(x: Any, campo: str) -> Fraction:
    v = a_fraccion(x, campo)
    if v < 0:
        raise ValueError(f"{campo}: no puede ser negativo")
    return v


def _tokens(x: Any, campo: str) -> int:
    """Conteo entero de tokens o registros (int o cadena de dígitos)."""
    if isinstance(x, bool) or isinstance(x, float):
        raise TypeError(f"{campo}: use un entero")
    if isinstance(x, int):
        v = x
    elif isinstance(x, str) and _ENT.match(x.strip()):
        v = int(x.strip())
    else:
        raise ValueError(f"{campo}: se esperaba un entero no negativo, llegó {x!r}")
    if v < 0:
        raise ValueError(f"{campo}: no puede ser negativo")
    return v


def redondear(fr: Fraction, decimales: int) -> int:
    """Entero escalado por 10**decimales, ROUND_HALF_UP (empate hacia la mayor magnitud)."""
    n = fr.numerator * (10 ** decimales)
    d = fr.denominator
    q, r = divmod(abs(n), d)
    if 2 * r >= d:
        q += 1
    return -q if n < 0 else q


def fmt(fr: Fraction, decimales: int) -> str:
    """Cadena decimal con exactamente ``decimales`` cifras (sin '-0')."""
    q = redondear(fr, decimales)
    signo = "-" if q < 0 else ""
    q = abs(q)
    if decimales == 0:
        return signo + str(q)
    s = str(q).rjust(decimales + 1, "0")
    return signo + s[:-decimales] + "." + s[-decimales:]


def _piso(fr: Fraction) -> int:
    return fr.numerator // fr.denominator


def _techo(fr: Fraction) -> int:
    return -((-fr.numerator) // fr.denominator)


def _usd(fr: Optional[Fraction]) -> Optional[str]:
    return None if fr is None else fmt(fr, DEC_USD)


# ------------------------------------------------------------------- tarifas
def buscar_tarifa(tarifas: Any, proveedor: str, modelo_api_id: str) -> Optional[Dict[str, Any]]:
    """Consulta de tarifas por (proveedor, modelo_api_id). El proveedor no distingue
    mayúsculas; el modelo debe coincidir con ``modelo_api_id`` o con un ``alias``."""
    if isinstance(tarifas, dict):
        tarifas = [tarifas]
    p = (proveedor or "").strip().lower()
    for t in tarifas or []:
        if (t.get("proveedor") or "").strip().lower() != p:
            continue
        if t.get("modelo_api_id") == modelo_api_id or modelo_api_id in (t.get("alias") or []):
            return t
    return None


def _precio(tarifa: Dict[str, Any], campo: str) -> Optional[Fraction]:
    v = tarifa.get(campo)
    return None if v is None else _no_neg(v, campo)


def _tarifa_utilizable(tarifa: Optional[Dict[str, Any]], proveedor: str, modelo: str
                       ) -> Optional[Tuple[str, str]]:
    """None si la tarifa sirve; si no, (estado, motivo)."""
    if tarifa is None:
        return ("tarifa_no_verificada", f"tarifa no verificada: no hay tarifa para {proveedor}/{modelo}")
    if tarifa.get("estado") != "verificada":
        return ("tarifa_no_verificada",
                f"tarifa no verificada: {proveedor}/{modelo} figura como {tarifa.get('estado')}")
    if tarifa.get("moneda", "USD") != "USD":
        raise ValueError("solo se admite moneda USD")
    return None


# -------------------------------------------------------------- razón y ahorro
def razon_y_ahorro(t_mini: Any, t_json: Any) -> Dict[str, Any]:
    """r = T_MINI / T_JSON ; ahorro_salida_pct = 100 x (1 - r)."""
    if t_mini is None or t_json is None:
        return {"estado": "no_definido", "motivo": "falta T_MINI o T_JSON", "razon": None,
                "ahorro_salida_pct": None, "hay_ahorro": None}
    tm = _tokens(t_mini, "t_mini")
    tj = _tokens(t_json, "t_json")
    if tj == 0:
        return {"estado": "no_definido", "motivo": "T_JSON = 0: la razón no está definida", "razon": None,
                "ahorro_salida_pct": None, "hay_ahorro": None}
    r = Fraction(tm, tj)
    ahorro = 100 * (1 - r)
    return {"estado": "calculado", "motivo": None, "razon": fmt(r, DEC_RAZON),
            "ahorro_salida_pct": fmt(ahorro, DEC_PCT), "hay_ahorro": ahorro > 0}


def _razon_exacta(entrada: Dict[str, Any]) -> Tuple[Optional[Fraction], Optional[str]]:
    if entrada.get("razon") is not None:
        r = _no_neg(entrada["razon"], "razon")
        return r, None
    res = razon_y_ahorro(entrada.get("t_mini"), entrada.get("t_json"))
    if res["estado"] != "calculado":
        return None, res["motivo"]
    return Fraction(_tokens(entrada["t_mini"], "t_mini"), _tokens(entrada["t_json"], "t_json")), None


# ------------------------------------------------------ costo por solicitud
_CATEGORIAS_TOKENS = (
    ("entrada_sin_cache", "entrada_sin_cache", "entrada_sin_cache_por_millon"),
    ("entrada_cache_lectura", "entrada_cache_lectura", "entrada_cache_lectura_por_millon"),
    ("entrada_cache_escritura", "entrada_cache_escritura", "entrada_cache_escritura_por_millon"),
    ("salida", "salida", "salida_por_millon"),
)
CATEGORIAS = ("entrada_sin_cache", "entrada_cache_lectura", "entrada_cache_escritura",
              "salida", "razonamiento", "otros")


def _costo_uso(usage: Optional[Dict[str, Any]], tarifa: Dict[str, Any]
               ) -> Tuple[Optional[Dict[str, Fraction]], Optional[Tuple[str, str]]]:
    """Costo por categorías NO solapadas de un usage. (categorias, None) o (None, (estado, motivo))."""
    if not isinstance(usage, dict):
        return None, ("usage_no_informado", "usage no informado: el intento no trae usage")
    cats: Dict[str, Fraction] = {}
    p_salida = _precio(tarifa, "salida_por_millon")
    for cat, campo, pcampo in _CATEGORIAS_TOKENS:
        tokens = usage.get(campo)
        if tokens is not None:
            tokens = _tokens(tokens, campo)
        precio = _precio(tarifa, pcampo)
        if precio is None:
            if tokens is None or tokens == 0:
                cats[cat] = Fraction(0)
                continue
            return None, ("tarifa_no_verificada",
                          f"tarifa no verificada: falta el precio de {pcampo} y el intento usó {tokens} tokens")
        if tokens is None:
            return None, ("usage_no_informado", f"usage no informado: {campo}")
        cats[cat] = Fraction(tokens) * precio / MILLON
    # Razonamiento: si ya viene dentro de 'salida' NO se cobra otra vez (sin doble conteo).
    incl = usage.get("razonamiento_incluido_en_salida")
    raz = usage.get("razonamiento")
    if raz is not None:
        raz = _tokens(raz, "razonamiento")
    if incl is True:
        if raz is not None and usage.get("salida") is not None and raz > _tokens(usage["salida"], "salida"):
            raise ValueError("razonamiento mayor que salida con razonamiento_incluido_en_salida = true")
        cats["razonamiento"] = Fraction(0)
    elif incl is False:
        if raz is None:
            return None, ("usage_no_informado", "usage no informado: razonamiento")
        if raz == 0:
            cats["razonamiento"] = Fraction(0)
        elif p_salida is None:
            return None, ("tarifa_no_verificada",
                          f"tarifa no verificada: falta el precio de salida_por_millon y el intento usó {raz} tokens de razonamiento")
        else:
            cats["razonamiento"] = Fraction(raz) * p_salida / MILLON
    else:
        if raz in (None, 0):
            cats["razonamiento"] = Fraction(0)
        else:
            return None, ("usage_no_informado",
                          "usage no informado: razonamiento_incluido_en_salida (hay tokens de razonamiento y no se sabe si ya están en salida)")
    otros = usage.get("otros_usd") or {}
    suma = Fraction(0)
    for nombre in sorted(otros):
        suma += _no_neg(otros[nombre], f"otros_usd.{nombre}")
    cats["otros"] = suma
    return cats, None


def _fmt_cats(cats: Optional[Dict[str, Fraction]]) -> Optional[Dict[str, str]]:
    if cats is None:
        return None
    return {c: fmt(cats[c], DEC_USD) for c in CATEGORIAS}


def _costo_intento(intento: Dict[str, Any], tarifas: Any
                   ) -> Tuple[Optional[Dict[str, Fraction]], Optional[Tuple[str, str]]]:
    prov = intento.get("proveedor") or ""
    mod = intento.get("modelo") or ""
    t = buscar_tarifa(tarifas, prov, mod)
    bloqueo = _tarifa_utilizable(t, prov, mod)
    if bloqueo:
        return None, bloqueo
    return _costo_uso(intento.get("usage"), t)


def _sumar(cats_lista: List[Dict[str, Fraction]]) -> Dict[str, Fraction]:
    tot = {c: Fraction(0) for c in CATEGORIAS}
    for cats in cats_lista:
        for c in CATEGORIAS:
            tot[c] += cats[c]
    return tot


def _total_cats(cats: Dict[str, Fraction]) -> Fraction:
    return sum((cats[c] for c in CATEGORIAS), Fraction(0))


def _id_grupo(s: Dict[str, Any]) -> str:
    if s.get("id") is None or str(s.get("id")) == "":
        raise ValueError("toda solicitud necesita un id")
    g = s.get("grupo")
    return str(s["id"]) if g is None else str(g)


def _solicitud_exacta(solicitud: Dict[str, Any], tarifas: Any
                      ) -> Tuple[Dict[str, Any], List[Dict[str, Fraction]], Optional[Tuple[str, str]]]:
    """Resultado presentable de una solicitud + las categorías EXACTAS de sus intentos calculables
    (así los totales no acumulan redondeos) + el primer fallo, si lo hubo."""
    intentos_out: List[Dict[str, Any]] = []
    ok: List[Dict[str, Fraction]] = []
    falla: Optional[Tuple[str, str]] = None
    for it in solicitud.get("intentos") or []:
        cats, err = _costo_intento(it, tarifas)
        intentos_out.append({"fase": it.get("fase"), "modelo": it.get("modelo"), "proveedor": it.get("proveedor"),
                             "estado": "calculado" if err is None else err[0],
                             "motivo": None if err is None else err[1],
                             "costo_usd": None if cats is None else fmt(_total_cats(cats), DEC_USD),
                             "categorias": _fmt_cats(cats)})
        if err is None:
            ok.append(cats)
        elif falla is None:
            falla = err
    base: Dict[str, Any] = {"id": str(solicitud.get("id")), "grupo": _id_grupo(solicitud),
                            "n_intentos": len(intentos_out), "intentos": intentos_out}
    if falla is None:
        tot = _sumar(ok)
        base.update({"estado": "calculado", "motivo": None, "costo_usd": fmt(_total_cats(tot), DEC_USD),
                     "categorias": _fmt_cats(tot), "costo_parcial_verificado_usd": None})
    else:
        base.update({"estado": falla[0], "motivo": falla[1], "costo_usd": None, "categorias": None,
                     "costo_parcial_verificado_usd": fmt(_total_cats(_sumar(ok)), DEC_USD) if ok else None})
    return base, ok, falla


def costo_solicitud(solicitud: Dict[str, Any], tarifas: Any) -> Dict[str, Any]:
    """Costo de UNA solicitud con todos sus intentos (generación, reparación...)."""
    return _solicitud_exacta(solicitud, tarifas)[0]


def _valor_de_grupo(solicitudes: List[Dict[str, Any]], grupo: str, campo: str) -> Optional[int]:
    """Valor del grupo: manda la solicitud ORIGINAL (id == grupo); si no hay original, todas
    las solicitudes que lo declaran deben coincidir (así no se cuenta dos veces)."""
    for s in solicitudes:
        if str(s.get("id")) == grupo:
            v = s.get(campo)
            return None if v is None else _tokens(v, campo)
    vistos = {_tokens(s[campo], campo) for s in solicitudes if s.get(campo) is not None}
    if len(vistos) > 1:
        raise ValueError(f"grupo {grupo}: {campo} inconsistente entre solicitudes ({sorted(vistos)}); "
                         "declárelo solo en la solicitud original")
    return next(iter(vistos)) if vistos else None


def costo_por_1000_validos(costo_total_usd: Any, registros_validos_finales: Optional[int]) -> Dict[str, Any]:
    """1000 x costo_total / registros_validos_finales; 0 válidos => 'no definido' (None) e
    informa el costo incurrido (nunca 0)."""
    if costo_total_usd is None:
        return {"estado": "no_definido", "motivo": "el costo total no está calculado",
                "costo_por_1000_validos_usd": None, "costo_incurrido_usd": None}
    costo = _no_neg(costo_total_usd, "costo_total_usd")
    if registros_validos_finales is None:
        return {"estado": "no_definido", "motivo": "registros_validos_finales no informado",
                "costo_por_1000_validos_usd": None, "costo_incurrido_usd": fmt(costo, DEC_USD)}
    v = _tokens(registros_validos_finales, "registros_validos_finales")
    if v == 0:
        return {"estado": "no_definido", "motivo": "0 registros válidos finales: el costo por 1000 válidos no está definido",
                "costo_por_1000_validos_usd": None, "costo_incurrido_usd": fmt(costo, DEC_USD)}
    return {"estado": "calculado", "motivo": None,
            "costo_por_1000_validos_usd": fmt(1000 * costo / v, DEC_USD),
            "costo_incurrido_usd": fmt(costo, DEC_USD)}


def costo_total(solicitudes: List[Dict[str, Any]], tarifas: Any) -> Dict[str, Any]:
    """Costo total de TODAS las solicitudes (incluidas las reparaciones), agrupado por la
    solicitud ORIGINAL (campo ``grupo``), por categorías no solapadas, y costo por 1000 válidos."""
    orden: List[str] = []
    por_grupo: Dict[str, List[Dict[str, Any]]] = {}
    for s in solicitudes:
        g = _id_grupo(s)
        if g not in por_grupo:
            por_grupo[g] = []
            orden.append(g)
        por_grupo[g].append(s)
    grupos_out: List[Dict[str, Any]] = []
    cats_ok_total: List[Dict[str, Fraction]] = []   # solo de intentos calculables
    falla: Optional[Tuple[str, str]] = None
    n_int = 0
    sol_total: Optional[int] = 0
    val_total: Optional[int] = 0
    for g in orden:
        ss = por_grupo[g]
        cats_g: List[Dict[str, Fraction]] = []
        falla_g: Optional[Tuple[str, str]] = None
        n_int_g = 0
        for s in ss:
            res, ok, f = _solicitud_exacta(s, tarifas)
            n_int_g += res["n_intentos"]
            cats_g.extend(ok)
            if f is not None and falla_g is None:
                falla_g = f
        n_int += n_int_g
        cats_ok_total.extend(cats_g)
        if falla_g is not None and falla is None:
            falla = falla_g
        pedidos = _valor_de_grupo(ss, g, "registros_solicitados")
        validos = _valor_de_grupo(ss, g, "registros_validos_finales")
        sol_total = None if (sol_total is None or pedidos is None) else sol_total + pedidos
        val_total = None if (val_total is None or validos is None) else val_total + validos
        grupos_out.append({
            "grupo": g, "n_solicitudes": len(ss), "n_intentos": n_int_g,
            "estado": "calculado" if falla_g is None else falla_g[0],
            "costo_usd": fmt(_total_cats(_sumar(cats_g)), DEC_USD) if falla_g is None else None,
            "registros_solicitados": None if pedidos is None else str(pedidos),
            "registros_validos_finales": None if validos is None else str(validos),
        })
    salida: Dict[str, Any] = {
        "moneda": "USD", "n_solicitudes": len(solicitudes), "n_intentos": n_int, "grupos": grupos_out,
        "registros_solicitados": None if sol_total is None else str(sol_total),
        "registros_validos_finales": None if val_total is None else str(val_total),
    }
    tot = _sumar(cats_ok_total)
    if falla is None:
        total = _total_cats(tot)
        salida.update({"estado": "calculado", "motivo": None, "costo_total_usd": fmt(total, DEC_USD),
                       "categorias": _fmt_cats(tot), "costo_parcial_verificado_usd": None})
        p1000 = costo_por_1000_validos(total, val_total)
    else:
        salida.update({"estado": falla[0], "motivo": falla[1], "costo_total_usd": None, "categorias": None,
                       "costo_parcial_verificado_usd": fmt(_total_cats(tot), DEC_USD) if cats_ok_total else None})
        p1000 = {"estado": "no_definido", "motivo": "el costo total no está calculado (" + falla[1] + ")",
                 "costo_por_1000_validos_usd": None, "costo_incurrido_usd": None}
    salida["costo_por_1000_validos"] = p1000
    return salida


# ------------------------------------------------------------------ perfiles
def _perfil(p: Dict[str, Any]) -> Dict[str, Any]:
    f_valid = _no_neg(p.get("fraccion_validos", "1"), "fraccion_validos")
    fr = _no_neg(p.get("fraccion_reparada", "1"), "fraccion_reparada")
    if f_valid > 1 or fr > 1:
        raise ValueError("fraccion_validos y fraccion_reparada deben estar entre 0 y 1")
    return {
        "nombre": p.get("nombre"),
        "I": Fraction(_tokens(p.get("tokens_instruccion", 0), "tokens_instruccion")),
        "en_cache": bool(p.get("instruccion_en_cache", False)),
        "e": _no_neg(p.get("tokens_entrada_por_registro", 0), "tokens_entrada_por_registro"),
        "o": _no_neg(p.get("tokens_salida_por_registro", 0), "tokens_salida_por_registro"),
        "c": _no_neg(p.get("tokens_salida_fijos", 0), "tokens_salida_fijos"),
        "f_valid": f_valid,
        "R": _no_neg(p.get("reintentos_por_lote", 0), "reintentos_por_lote"),
        "fr": fr,
    }


class _SinPrecio(Exception):
    pass


def _costo_lote(p: Dict[str, Any], tarifa: Dict[str, Any], k: Fraction
                ) -> Tuple[Optional[Dict[str, Fraction]], Optional[Tuple[str, str]]]:
    """Costo exacto de un lote de k registros:
    entrada = (I x p_instr + k x e x p_in)/1e6 ; salida = (o x k + c) x p_out/1e6 ;
    reintentos = R x (entrada + fr x salida)."""
    p_in = _precio(tarifa, "entrada_sin_cache_por_millon")
    p_ca = _precio(tarifa, "entrada_cache_lectura_por_millon")
    p_out = _precio(tarifa, "salida_por_millon")

    def req(precio: Optional[Fraction], campo: str, tokens: Fraction) -> Fraction:
        if tokens == 0:
            return Fraction(0)
        if precio is None:
            raise _SinPrecio(campo)
        return tokens * precio / MILLON

    try:
        if p["en_cache"]:
            instr = req(p_ca, "entrada_cache_lectura_por_millon", p["I"])
        else:
            instr = req(p_in, "entrada_sin_cache_por_millon", p["I"])
        entrada = instr + req(p_in, "entrada_sin_cache_por_millon", k * p["e"])
        tok_sal = p["o"] * k + p["c"]
        salida = req(p_out, "salida_por_millon", tok_sal)
    except _SinPrecio as ex:
        return None, ("tarifa_no_verificada", f"tarifa no verificada: falta el precio de {ex.args[0]}")
    reint = p["R"] * (entrada + p["fr"] * salida)
    return ({"entrada": entrada, "salida": salida, "reintentos": reint, "total": entrada + salida + reint,
             "tokens_salida": tok_sal, "registros_validos": k * p["f_valid"]}, None)


def _tarifa_de(entrada: Dict[str, Any], alt: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    t = (alt or {}).get("tarifa") or entrada.get("tarifa")
    if not isinstance(t, dict):
        raise ValueError("falta la tarifa")
    return t


def costo_lote(entrada: Dict[str, Any]) -> Dict[str, Any]:
    """Costo POR LOTE de un perfil: entrada + salida + reintentos."""
    tarifa = _tarifa_de(entrada)
    bloqueo = _tarifa_utilizable(tarifa, tarifa.get("proveedor"), tarifa.get("modelo_api_id"))
    k = _no_neg(entrada.get("k"), "k")
    if k == 0:
        raise ValueError("k debe ser mayor que 0")
    if bloqueo:
        return {"estado": bloqueo[0], "motivo": bloqueo[1], "costo_lote_usd": None}
    c, err = _costo_lote(_perfil(entrada["perfil"]), tarifa, k)
    if err:
        return {"estado": err[0], "motivo": err[1], "costo_lote_usd": None}
    return {"estado": "calculado", "motivo": None, "costo_lote_usd": fmt(c["total"], DEC_USD),
            "entrada_usd": fmt(c["entrada"], DEC_USD), "salida_usd": fmt(c["salida"], DEC_USD),
            "reintentos_usd": fmt(c["reintentos"], DEC_USD),
            "tokens_salida_por_lote": fmt(c["tokens_salida"], DEC_LOTES),
            "registros_validos_por_lote": fmt(c["registros_validos"], DEC_LOTES)}


# ---------------------------------------------------------------- escenario A
def escenario_a(entrada: Dict[str, Any]) -> Dict[str, Any]:
    """Con ``tokens_json_referencia`` (por defecto 1.000.000) de salida JSON: ¿cuánto costaría el
    equivalente según la proporción medida? Es una PROYECCIÓN aritmética."""
    tarifa = _tarifa_de(entrada)
    bloqueo = _tarifa_utilizable(tarifa, tarifa.get("proveedor"), tarifa.get("modelo_api_id"))
    ref = _no_neg(entrada.get("tokens_json_referencia", MILLON), "tokens_json_referencia")
    out: Dict[str, Any] = {
        "tipo": "proyeccion", "aviso_es": AVISO_PROYECCION_ES, "aviso_en": AVISO_PROYECCION_EN,
        "tokens_json_referencia": fmt(ref, 0), "politica_redondeo": "ROUND_HALF_UP",
    }
    r, motivo_r = _razon_exacta(entrada)
    out["razon"] = None if r is None else fmt(r, DEC_RAZON)
    out["tokens_mini_equivalentes"] = None if r is None else fmt(ref * r, 0)
    # Variante 1: solo salida
    so: Dict[str, Any] = {"estado": None, "motivo": None, "costo_json_usd": None, "costo_mini_usd": None,
                          "ahorro_usd": None, "ahorro_pct": None, "hay_ahorro": None}
    if r is None:
        so.update({"estado": "no_definido", "motivo": motivo_r})
    elif bloqueo:
        so.update({"estado": bloqueo[0], "motivo": bloqueo[1]})
    else:
        p_out = _precio(tarifa, "salida_por_millon")
        if p_out is None:
            so.update({"estado": "tarifa_no_verificada", "motivo": "tarifa no verificada: falta el precio de salida_por_millon"})
        else:
            cj = ref * p_out / MILLON
            cm = ref * r * p_out / MILLON
            so.update({"estado": "calculado", "costo_json_usd": fmt(cj, DEC_USD), "costo_mini_usd": fmt(cm, DEC_USD),
                       "ahorro_usd": fmt(cj - cm, DEC_USD),
                       "ahorro_pct": None if cj == 0 else fmt(100 * (cj - cm) / cj, DEC_PCT),
                       "hay_ahorro": cj > cm})
    out["solo_salida"] = so
    # Variante 2: total con instrucciones y reintentos (mismo trabajo: mismos lotes y registros)
    tot = entrada.get("total")
    if tot is None:
        out["total"] = None
    else:
        k = _no_neg(tot.get("k"), "total.k")
        if k == 0:
            raise ValueError("total.k debe ser mayor que 0")
        t: Dict[str, Any] = {"estado": None, "motivo": None, "lotes_equivalentes": None, "costo_json_usd": None,
                             "costo_mini_usd": None, "ahorro_usd": None, "ahorro_pct": None, "hay_ahorro": None,
                             "razon_salida_implicita": None, "k": fmt(k, DEC_LOTES)}
        if bloqueo:
            t.update({"estado": bloqueo[0], "motivo": bloqueo[1]})
        else:
            cj, ej = _costo_lote(_perfil(tot["perfil_json"]), tarifa, k)
            cm, em = _costo_lote(_perfil(tot["perfil_mini"]), tarifa, k)
            if ej or em:
                e = ej or em
                t.update({"estado": e[0], "motivo": e[1]})
            elif cj["tokens_salida"] == 0:
                t.update({"estado": "no_definido", "motivo": "el perfil JSON no tiene tokens de salida por lote"})
            else:
                n_lotes = ref / cj["tokens_salida"]
                tj_ = n_lotes * cj["total"]
                tm_ = n_lotes * cm["total"]
                t.update({"estado": "calculado", "lotes_equivalentes": fmt(n_lotes, DEC_LOTES),
                          "costo_json_usd": fmt(tj_, DEC_USD), "costo_mini_usd": fmt(tm_, DEC_USD),
                          "ahorro_usd": fmt(tj_ - tm_, DEC_USD),
                          "ahorro_pct": None if tj_ == 0 else fmt(100 * (tj_ - tm_) / tj_, DEC_PCT),
                          "hay_ahorro": tj_ > tm_,
                          "razon_salida_implicita": fmt(cm["tokens_salida"] / cj["tokens_salida"], DEC_RAZON)})
        out["total"] = t
    out["supuestos"] = {
        "misma_tarifa_ambos_formatos": True,
        "total_incluye": "entrada (instrucción y tarea), salida y reintentos por lote",
        "solo_salida_incluye": "únicamente tokens de salida x precio de salida",
        "mismo_trabajo": "los dos formatos producen los mismos registros (mismos lotes)",
        "tarifa_estado": tarifa.get("estado"), "tarifa_fecha_consulta_utc": tarifa.get("fecha_consulta_utc"),
    }
    return out


# ---------------------------------------------------------------- escenario B
def escenario_b(entrada: Dict[str, Any]) -> Dict[str, Any]:
    """Con un presupuesto ILUSTRATIVO (p. ej. US$ 1.000): ¿cuántos lotes y registros útiles permite
    cada alternativa? Usa el costo POR LOTE (entrada + salida + reintentos) y los registros válidos
    por lote; no compara tokens de formatos distintos como si fueran el mismo trabajo."""
    presupuesto = _no_neg(entrada.get("presupuesto_usd", "1000"), "presupuesto_usd")
    variante = entrada.get("variante", "total")
    if variante not in ("total", "solo_salida"):
        raise ValueError("variante debe ser 'total' o 'solo_salida'")
    k_def = entrada.get("k")
    alts_out: List[Dict[str, Any]] = []
    calculados: List[Optional[int]] = []
    for alt in entrada.get("alternativas") or []:
        fila: Dict[str, Any] = {"nombre": alt.get("nombre"), "estado": None, "motivo": None, "k": None,
                                "costo_lote_usd": None, "tokens_salida_por_lote": None,
                                "registros_validos_por_lote": None, "lotes": None, "registros_utiles": None,
                                "tokens_salida_capacidad": None, "gasto_usd": None, "sobrante_usd": None}
        costo = tok = rv = None
        if alt.get("perfil") is not None:
            tarifa = _tarifa_de(entrada, alt)
            bloqueo = _tarifa_utilizable(tarifa, tarifa.get("proveedor"), tarifa.get("modelo_api_id"))
            k = _no_neg(alt.get("k", k_def), "k")
            if k == 0:
                raise ValueError("k debe ser mayor que 0")
            fila["k"] = fmt(k, DEC_LOTES)
            if bloqueo:
                fila.update({"estado": bloqueo[0], "motivo": bloqueo[1]})
            else:
                perfil_alt = _perfil(alt["perfil"])
                if variante == "solo_salida":
                    perfil_alt = _solo_salida(perfil_alt)
                c, err = _costo_lote(perfil_alt, tarifa, k)
                if err:
                    fila.update({"estado": err[0], "motivo": err[1]})
                else:
                    costo, tok, rv = c["total"], c["tokens_salida"], c["registros_validos"]
        else:
            if variante == "solo_salida":
                raise ValueError("la variante solo_salida exige alternativas con perfil (un costo por lote medido no se puede separar)")
            costo = _no_neg(alt["costo_lote_usd"], "costo_lote_usd")
            tok = None if alt.get("tokens_salida_por_lote") is None else _no_neg(alt["tokens_salida_por_lote"], "tokens_salida_por_lote")
            rv = None if alt.get("registros_validos_por_lote") is None else _no_neg(alt["registros_validos_por_lote"], "registros_validos_por_lote")
        if costo is not None:
            fila["costo_lote_usd"] = fmt(costo, DEC_USD)
            fila["tokens_salida_por_lote"] = None if tok is None else fmt(tok, DEC_LOTES)
            fila["registros_validos_por_lote"] = None if rv is None else fmt(rv, DEC_LOTES)
            if costo == 0:
                fila.update({"estado": "costo_lote_cero", "motivo": "el costo por lote es 0: no se puede dividir el presupuesto"})
            else:
                lotes = _piso(presupuesto / costo)
                gasto = lotes * costo
                fila.update({"estado": "calculado", "lotes": str(lotes), "gasto_usd": fmt(gasto, DEC_USD),
                             "sobrante_usd": fmt(presupuesto - gasto, DEC_USD)})
                fila["registros_utiles"] = None if rv is None else str(_piso(lotes * rv))
                fila["tokens_salida_capacidad"] = None if tok is None else str(_piso(lotes * tok))
        calculados.append(int(fila["registros_utiles"]) if fila["registros_utiles"] is not None else None)
        alts_out.append(fila)
    comparacion: List[Dict[str, Any]] = []
    if alts_out:
        ref_nombre = alts_out[0]["nombre"]
        ref_ru = calculados[0]
        for fila, ru in zip(alts_out[1:], calculados[1:]):
            d = None if (ru is None or ref_ru is None) else str(ru - ref_ru)
            pct = None if (ru is None or not ref_ru) else fmt(100 * (Fraction(ru, ref_ru) - 1), DEC_PCT)
            comparacion.append({"nombre": fila["nombre"], "referencia": ref_nombre,
                                "diferencia_registros_utiles": d, "registros_utiles_vs_referencia_pct": pct})
    return {
        "tipo": "capacidad", "presupuesto_usd": fmt(presupuesto, 2) if (presupuesto * 100).denominator == 1 else fmt(presupuesto, DEC_USD),
        "presupuesto_ilustrativo": True, "aviso_es": AVISO_PRESUPUESTO_ES, "aviso_en": AVISO_PRESUPUESTO_EN,
        "variante": variante, "politica_redondeo": "ROUND_HALF_UP",
        "alternativas": alts_out, "comparacion": comparacion,
        "supuestos": {"lotes": "floor(presupuesto / costo exacto por lote)",
                      "registros_utiles": "floor(lotes x registros válidos por lote)",
                      "costo_lote": ("entrada (instrucción y tarea) + salida + reintentos" if variante == "total"
                                     else "únicamente tokens de salida x precio de salida (sin instrucción, entrada ni reintentos)")},
    }


# ---------------------------------------------------- punto de equilibrio
def _recta(p: Dict[str, Any], tarifa: Dict[str, Any]
           ) -> Tuple[Optional[Tuple[Fraction, Fraction]], Optional[Tuple[str, str]]]:
    """El costo por lote es lineal en k: costo(k) = A + B k (se obtiene evaluando k=0 y k=1)."""
    c0, e0 = _costo_lote(p, tarifa, Fraction(0))
    c1, e1 = _costo_lote(p, tarifa, Fraction(1))
    if e0 or e1:
        return None, (e0 or e1)
    return (c0["total"], c1["total"] - c0["total"]), None


def _solo_salida(p: Dict[str, Any]) -> Dict[str, Any]:
    q = dict(p)
    q.update({"I": Fraction(0), "e": Fraction(0), "R": Fraction(0)})
    return q


def _equilibrio(pj: Dict[str, Any], pm: Dict[str, Any], tarifa: Dict[str, Any], k_ref: Optional[Fraction]
                ) -> Dict[str, Any]:
    rj, ej = _recta(pj, tarifa)
    rm, em = _recta(pm, tarifa)
    vacio = {"estado": None, "motivo": None, "k_minimo": None, "k_maximo": None, "k_equilibrio_exacto": None,
             "delta_fijo_usd": None, "delta_por_registro_usd": None, "delta_en_k_referencia_usd": None,
             "ahorro_en_k_referencia_pct": None, "mensaje_es": None, "mensaje_en": None}
    if ej or em:
        e = ej or em
        vacio.update({"estado": e[0], "motivo": e[1]})
        return vacio
    b = rj[0] - rm[0]          # diferencia del costo fijo por lote (JSON - mini)
    a = rj[1] - rm[1]          # diferencia del costo por registro (JSON - mini)
    d1 = a + b
    kmin: Optional[int] = None
    kmax: Optional[int] = None
    if a > 0:
        if d1 > 0:
            estado, kmin = "siempre_ahorra", 1
        else:
            estado, kmin = "desde_k", _piso(-b / a) + 1
    elif a == 0:
        estado, kmin = ("siempre_ahorra", 1) if b > 0 else ("sin_ahorro_neto", None)
    else:
        if d1 > 0:
            estado, kmin, kmax = "solo_hasta_k", 1, _techo(b / (-a)) - 1
        else:
            estado = "sin_ahorro_neto"
    if estado == "siempre_ahorra":
        es, en = ("Hay ahorro neto para cualquier tamaño de lote desde 1 registro.",
                  "There is a net saving for any batch size from 1 record.")
    elif estado == "desde_k":
        es = f"Hay ahorro neto desde {kmin} registros por lote; con lotes menores no compensa el costo fijo adicional."
        en = f"There is a net saving from {kmin} records per batch; smaller batches do not offset the extra fixed cost."
    elif estado == "solo_hasta_k":
        es = f"Hay ahorro neto solo hasta {kmax} registros por lote; con lotes mayores .mini cuesta más que JSON."
        en = f"There is a net saving only up to {kmax} records per batch; with larger batches .mini costs more than JSON."
    else:
        es = "No hay ahorro neto para ningún tamaño de lote: con estos supuestos .mini cuesta igual o más que JSON."
        en = "There is no net saving for any batch size: under these assumptions .mini costs the same or more than JSON."
    res = dict(vacio)
    res.update({"estado": estado, "k_minimo": None if kmin is None else str(kmin),
                "k_maximo": None if kmax is None else str(kmax),
                "k_equilibrio_exacto": fmt(-b / a, DEC_LOTES) if (a != 0 and -b / a > 0) else None,
                "delta_fijo_usd": fmt(b, DEC_USD_FINO), "delta_por_registro_usd": fmt(a, DEC_USD_FINO),
                "mensaje_es": es, "mensaje_en": en})
    if k_ref is not None:
        delta = a * k_ref + b
        base = rj[0] + rj[1] * k_ref
        res["delta_en_k_referencia_usd"] = fmt(delta, DEC_USD)
        res["ahorro_en_k_referencia_pct"] = None if base == 0 else fmt(100 * delta / base, DEC_PCT)
    return res


def punto_equilibrio(entrada: Dict[str, Any]) -> Dict[str, Any]:
    """Tamaño de lote (registros) desde el que .mini ahorra frente a JSON, en dos variantes:
    'solo_salida' y 'total' (instrucción + entrada + salida + reintentos). Si no hay ahorro neto, lo dice."""
    tarifa = _tarifa_de(entrada)
    bloqueo = _tarifa_utilizable(tarifa, tarifa.get("proveedor"), tarifa.get("modelo_api_id"))
    k_ref = None if entrada.get("k_referencia") is None else _no_neg(entrada["k_referencia"], "k_referencia")
    if k_ref is not None and k_ref == 0:
        raise ValueError("k_referencia debe ser mayor que 0")
    pj, pm = _perfil(entrada["perfil_json"]), _perfil(entrada["perfil_mini"])
    if bloqueo:
        bl = {"estado": bloqueo[0], "motivo": bloqueo[1]}
        res = {"solo_salida": dict(bl), "total": dict(bl)}
    else:
        res = {"solo_salida": _equilibrio(_solo_salida(pj), _solo_salida(pm), tarifa, k_ref),
               "total": _equilibrio(pj, pm, tarifa, k_ref)}
    res["k_referencia"] = None if k_ref is None else fmt(k_ref, DEC_LOTES)
    res["politica_redondeo"] = "ROUND_HALF_UP"
    res["supuestos"] = {
        "modelo": "costo por lote lineal en k: costo(k) = A + B x k",
        "ahorro_neto": "costo_json(k) - costo_mini(k) > 0 (un empate no cuenta como ahorro)",
        "k": "registros por lote, enteros desde 1",
        "tarifa_estado": tarifa.get("estado"), "tarifa_fecha_consulta_utc": tarifa.get("fecha_consulta_utc"),
    }
    return res


# ------------------------------------------------------------------ despacho
def ejecutar(operacion: str, entrada: Dict[str, Any]) -> Any:
    """Punto único de entrada (lo usan los vectores dorados y las pruebas)."""
    if operacion == "redondear":
        return fmt(a_fraccion(entrada["valor"]), int(entrada["decimales"]))
    if operacion == "razon_y_ahorro":
        return razon_y_ahorro(entrada.get("t_mini"), entrada.get("t_json"))
    if operacion == "costo_solicitud":
        return costo_solicitud(entrada["solicitud"], entrada["tarifas"])
    if operacion == "costo_total":
        return costo_total(entrada["solicitudes"], entrada["tarifas"])
    if operacion == "costo_por_1000_validos":
        return costo_por_1000_validos(entrada.get("costo_total_usd"), entrada.get("registros_validos_finales"))
    if operacion == "costo_lote":
        return costo_lote(entrada)
    if operacion == "escenario_a":
        return escenario_a(entrada)
    if operacion == "escenario_b":
        return escenario_b(entrada)
    if operacion == "punto_equilibrio":
        return punto_equilibrio(entrada)
    if operacion == "buscar_tarifa":
        t = buscar_tarifa(entrada["tarifas"], entrada["proveedor"], entrada["modelo_api_id"])
        return {"encontrada": t is not None,
                "modelo_api_id": None if t is None else t.get("modelo_api_id"),
                "estado": None if t is None else t.get("estado")}
    raise ValueError(f"operación desconocida: {operacion}")
