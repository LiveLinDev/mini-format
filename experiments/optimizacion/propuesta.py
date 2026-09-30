"""SIMULACIÓN de una ampliación del formato: diccionario por documento en la cabecera (propuesta, NO implementada).

Hoy el núcleo de .mini 1.1 no tiene diccionarios ni alias: la equivalencia código<->etiqueta la mantiene la
aplicación (``mapa.json``). Lo único parecido vive en el perfil ``mini-domain/1`` (solo Python, cabecera ``e=``).

Aquí se mide, sin tocar ``src/`` ni ``ts/``, cuántos tokens de SALIDA ahorraría declarar en la cabecera de un
documento del perfil GENERAL (contrato de ``mini from-schema``) un diccionario por documento para sus columnas de
texto o enumeración repetidas, con la regla de ``mini build`` (columna ``str`` o ``enum``, 2..64 valores
distintos, al menos 3 filas por valor, al menos 6 filas y ahorro neto en bytes). El diccionario viaja completo
en cada documento y su coste se cuenta. La pregunta es cuánto de lo que hoy se consigue diseñando a mano códigos
y mapas lo daría una regla automática del formato.

El resultado es un TECHO para estos conjuntos de datos, no una predicción: no incluye el coste de instruir al
modelo sobre la sintaxis del diccionario y depende de que los valores se repitan. No se presenta como una
optimización existente.
"""
from __future__ import annotations

import json
from typing import Any, Dict, List, Sequence, Tuple

from . import perfiles, tokenizadores
from .dominios import Dominio
from minifmt import codec
from minifmt.serializer import encode_field


def _celdas(dom: Dominio, registros: Sequence[Dict[str, Any]]) -> List[List[str]]:
    c = perfiles.contrato_general(dom)
    return [[encode_field(r.get(f.name), f, c.list_separator, r) for f in c.core] for r in registros]


def simular(dom: Dominio, registros: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    c = perfiles.contrato_general(dom)
    filas = _celdas(dom, registros)
    n = len(filas)
    cab = f"{c.prefix}|n={n}"
    elegidas: List[Tuple[int, List[str]]] = []
    if n >= 6:
        for i, f in enumerate(c.core):
            if f.type not in ("str", "enum"):
                continue
            vals = list(dict.fromkeys(fila[i] for fila in filas))
            if not 2 <= len(vals) <= 64 or len(vals) * 3 > n:
                continue
            tabla = {v: k for k, v in enumerate(vals)}
            antes = sum(len(fila[i].encode("utf-8")) for fila in filas)
            sobrecosto = len(json.dumps([i, vals], ensure_ascii=False, separators=(",", ":")).encode("utf-8")) + 4
            despues = sum(len(str(tabla[fila[i]])) for fila in filas) + sobrecosto
            if antes - despues > max(32, sobrecosto // 3):
                elegidas.append((i, vals))
    if not elegidas:
        return {"aplica": False, "motivo": "ninguna columna cumple la regla (se repite poco o ahorra menos de lo que cuesta declararla)",
                "texto": None, "columnas": []}
    tablas = {i: {v: k for k, v in enumerate(vals)} for i, vals in elegidas}
    decl = json.dumps([[i, vals] for i, vals in elegidas], ensure_ascii=False, separators=(",", ":"))
    lineas = [cab + "|e=" + codec.escape_scalar(decl)]
    for fila in filas:
        lineas.append("|".join(str(tablas[i][cel]) if i in tablas else cel for i, cel in enumerate(fila)))
    # ida y vuelta de la simulación: expandir cada índice y comparar con las celdas originales
    vals_por = {i: vals for i, vals in elegidas}
    ok = True
    for lin, fila in zip(lineas[1:], filas):
        cel = codec.split_fields(lin, c.list_separator, 0, strict=False)
        partes = [codec.text_of(t) for t in cel]
        # las celdas con escapes se comparan por su forma escapada: se reconstruyen de la misma manera
        exp = [vals_por[i][int(x)] if i in vals_por else None for i, x in enumerate(partes)]
        if any(e is not None and e != fila[i] for i, e in enumerate(exp)) or len(partes) != len(fila):
            ok = False
            break
    return {"aplica": True, "texto": "\n".join(lineas), "ida_y_vuelta_de_la_simulacion": ok,
            "columnas": [{"indice": i, "nombre": c.core[i].name, "valores_distintos": len(v)} for i, v in elegidas]}


def medir(dom: Dominio, registros: Sequence[Dict[str, Any]], salida_general: str, salida_especializada: str) -> List[Dict[str, Any]]:
    s = simular(dom, registros)
    filas = []
    for nombre, t in tokenizadores.todos().items():
        g, e = t.contar(salida_general), t.contar(salida_especializada)
        fila: Dict[str, Any] = {"tokenizador": nombre, "tokens_salida_general": g,
                                "tokens_salida_especializado_a_mano": e, "aplica": bool(s["aplica"])}
        if s["aplica"] and s.get("ida_y_vuelta_de_la_simulacion"):
            sim = t.contar(s["texto"])
            fila.update(tokens_salida_general_con_diccionario_simulado=sim,
                        ahorro_potencial_vs_general_pct=round(100 * (1 - sim / g), 2),
                        distancia_a_lo_hecho_a_mano_tokens=sim - e,
                        columnas=[x["nombre"] for x in s["columnas"]])
        else:
            fila.update(tokens_salida_general_con_diccionario_simulado=None, ahorro_potencial_vs_general_pct=None,
                        distancia_a_lo_hecho_a_mano_tokens=None, columnas=[],
                        motivo=s.get("motivo") or "la simulación no reconstruye las celdas originales")
        filas.append(fila)
    return filas
