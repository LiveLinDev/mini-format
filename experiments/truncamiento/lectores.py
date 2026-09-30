"""Lectores de salida truncada, uno por formato.

Cada lector recibe el **prefijo** (texto ya cortado en frontera de token y de carácter) y devuelve los
registros que logra leer. Ninguno completa ni adivina datos; lo que cada uno hace y por qué es razonable
está en ``PROTOCOLO.md`` §5. Aquí solo se implementa.

* ``leer_json_estricto``        json.loads del prefijo.
* ``leer_json_parcial_jiter``   jiter en modo parcial ("on"); entrega también el último elemento incompleto.
* ``leer_jsonl``                JSON Lines: una línea = un objeto; se descarta toda línea que no sea objeto completo.
* ``leer_mini_tolerante``       lector tolerante de .mini (``minifmt.Reader`` o, para ``mini-domain/1``, el
                                aislamiento línea a línea de ``minifmt.domain.diagnose``).
* ``leer_json_objetos_completos`` escáner de implementación PROPIA de este estudio: emite cada elemento
                                completo del arreglo de registros y nunca uno parcial.
"""
from __future__ import annotations

import json
import re
from typing import Any, Dict, List, NamedTuple, Optional, Sequence, Tuple

__all__ = ["Lectura", "leer_json_estricto", "leer_json_parcial_jiter", "leer_jsonl", "leer_mini_tolerante",
           "leer_json_objetos_completos", "escanear_elementos", "version_jiter"]


class Lectura(NamedTuple):
    registros: List[Any]
    nota: Optional[str] = None     # causa legible si el lector no pudo leer nada (información, no error)
    fallo: bool = False            # True si el lector lanzó una excepción inesperada (no un JSON truncado normal)


def version_jiter() -> Optional[str]:
    try:
        from importlib import metadata
        return metadata.version("jiter")
    except Exception:
        return None


def _extraer(valor: Any, clave: Optional[str]) -> List[Any]:
    """Elementos-objeto del arreglo de registros de un documento ya analizado."""
    if clave is None:
        arreglo = valor
    elif isinstance(valor, dict):
        arreglo = valor.get(clave)
    else:
        return []
    if not isinstance(arreglo, list):
        return []
    return [e for e in arreglo if isinstance(e, dict)]


# ------------------------------------------------------------------ 1. JSON estricto
def leer_json_estricto(prefijo: str, clave: Optional[str]) -> Lectura:
    try:
        valor = json.loads(prefijo)
    except ValueError as e:
        return Lectura([], f"json.loads: {type(e).__name__}")
    return Lectura(_extraer(valor, clave))


# ------------------------------------------------------------------ 2. JSON parcial (jiter)
def leer_json_parcial_jiter(prefijo: str, clave: Optional[str], modo: str = "on") -> Lectura:
    import jiter
    try:
        valor = jiter.from_json(prefijo.encode("utf-8"), partial_mode=modo)
    except ValueError as e:          # jiter lanza ValueError para JSON irrecuperable
        return Lectura([], f"jiter: {str(e)[:60]}", True)
    return Lectura(_extraer(valor, clave))


# ------------------------------------------------------------------ 3. JSON Lines
def leer_jsonl(prefijo: str, con_envoltura: bool) -> Lectura:
    registros: List[Any] = []
    for i, linea in enumerate(prefijo.split("\n")):
        if con_envoltura and i == 0:
            continue                         # la línea 1 es la envoltura, no un registro
        if not linea.strip():
            continue
        try:
            valor = json.loads(linea)
        except ValueError:
            continue                         # línea incompleta (la final, típicamente): se descarta
        if isinstance(valor, dict):
            registros.append(valor)
    return Lectura(registros)


# ------------------------------------------------------------------ 4. .mini tolerante
def _sin_cola(prefijo: str) -> str:
    """Quita la última línea si el prefijo no termina en LF."""
    if prefijo.endswith("\n"):
        return prefijo
    return prefijo[: prefijo.rfind("\n") + 1]


def _leer_mini_academico(prefijo: str, contrato: Any) -> Lectura:
    from minifmt import Reader
    lector = Reader(contrato, strict=False)
    lector.push(prefijo)
    resultado = lector.end()
    return Lectura(list(resultado.records))


def _registros_de(valor: Any, ruta: Optional[Sequence[str]]) -> List[Any]:
    """Filas de un documento ``mini-domain/1`` decodificado con n=1."""
    if ruta is None:            # raíz escalar/objeto: el propio valor es el registro
        return [valor]
    actual = valor
    for clave in ruta:
        actual = actual[clave]
    return list(actual)


def _leer_mini_dominio(prefijo: str, contrato: Dict[str, Any]) -> Lectura:
    """Aislamiento línea a línea como ``minifmt.domain.diagnose``: cabecera completa + cada línea sola con n=1."""
    from minifmt import domain as dom
    lineas = prefijo.split("\n")
    if lineas and lineas[-1] == "":
        lineas.pop()
    if not lineas or not lineas[0]:
        return Lectura([], "sin cabecera")
    try:
        celdas = dom._split(lineas[0], 1)
    except dom.DomainError as e:
        return Lectura([], f"cabecera: {e.code}")
    cab1 = "|".join(dom._escape("n=1" if c.startswith("n=") else c) for c in celdas)
    registros: List[Any] = []
    for linea in lineas[1:]:
        try:
            valor = dom.decode(cab1 + "\n" + linea, contrato)
        except dom.DomainError as e:
            if e.line in (0, 2):
                continue                     # línea inválida (p. ej. aridad de una línea cortada): se descarta
            return Lectura([], f"cabecera: {e.code}")   # cabecera inválida: nada es fiable
        registros.extend(_registros_de(valor, contrato["record_path"]))
    return Lectura(registros)


def leer_mini_tolerante(prefijo: str, contrato: Any, truncado: bool, sin_cola: bool = False) -> Lectura:
    """Lector tolerante de .mini tal cual. ``sin_cola`` (variante declarada): si el consumidor sabe que el
    límite cortó la salida, descarta la última línea sin LF."""
    if sin_cola and truncado:
        prefijo = _sin_cola(prefijo)
    if isinstance(contrato, dict) and contrato.get("profile") == "mini-domain/1":
        return _leer_mini_dominio(prefijo, contrato)
    return _leer_mini_academico(prefijo, contrato)


# ------------------------------------------------------------------ 5. JSON, objetos completos (PROPIO)
# Una cadena cerrada, una cadena sin cerrar hasta el final del texto (aquí se detiene el escáner) o un
# delimitador estructural. Todo lo demás (números, literales, espacio) no contiene comillas ni delimitadores.
_TOKEN = re.compile(
    r'(?P<cad>"[^"\\]*(?:\\.[^"\\]*)*")'
    r'|(?P<inc>"[^"\\]*(?:\\.[^"\\]*)*\\?\Z)'
    r'|(?P<pun>[{}\[\],:])',
    re.S,
)


def escanear_elementos(texto: str, clave: Optional[str]) -> List[Tuple[int, int]]:
    """Posiciones ``(inicio, fin)`` (índices de ``str``, fin exclusivo) de cada elemento-contenedor COMPLETO
    del arreglo de registros: el del nivel superior si ``clave`` es None, o el valor de ``clave`` en el
    objeto de nivel superior. Es un escáner causal: lo que emite para un prefijo es un prefijo de lo que
    emite para el texto completo. No completa nada: un elemento sin su cierre no se emite."""
    pila: List[str] = []
    espera_clave = False
    clave_actual: Optional[str] = None
    nivel: Optional[int] = None      # tamaño de la pila cuando se está directamente dentro del arreglo de registros
    inicio: Optional[int] = None
    salida: List[Tuple[int, int]] = []
    for m in _TOKEN.finditer(texto):
        g = m.lastgroup
        if g == "inc":
            break                     # cadena sin cerrar: el texto termina aquí
        if g == "cad":
            if espera_clave and len(pila) == 1 and pila[0] == "{":
                clave_actual = json.loads(m.group())
                espera_clave = False
            continue
        p = m.group()
        if p == "{" or p == "[":
            if nivel is None:
                if clave is None and not pila and p == "[":
                    nivel = 1
                elif (clave is not None and len(pila) == 1 and pila[0] == "{" and p == "["
                      and clave_actual == clave):
                    nivel = 2
            elif len(pila) == nivel:
                inicio = m.start()
            pila.append(p)
            if p == "{" and len(pila) == 1:
                espera_clave = True
        elif p == "}" or p == "]":
            if not pila:
                break                 # cierre sin apertura: texto malformado, se detiene
            pila.pop()
            if nivel is not None:
                if len(pila) == nivel and inicio is not None:
                    salida.append((inicio, m.end()))
                    inicio = None
                elif len(pila) < nivel:
                    break             # se cerró el arreglo de registros
        elif p == "," and len(pila) == 1 and pila[0] == "{":
            espera_clave = True
    return salida


def leer_json_objetos_completos(prefijo: str, clave: Optional[str]) -> Lectura:
    registros: List[Any] = []
    for a, b in escanear_elementos(prefijo, clave):
        try:
            valor = json.loads(prefijo[a:b])
        except ValueError:
            return Lectura(registros, "elemento completo que no es JSON válido", True)
        if isinstance(valor, dict):
            registros.append(valor)
    return Lectura(registros)
