"""Perfiles que se comparan, cada uno con SU salida y SU instrucción completa.

* ``json_compacto``        línea base: JSON sin espacios del objeto de la aplicación envuelto en {clave:[...]}.
* ``json_legible``         el mismo JSON con sangría de 2 (aparte).
* ``json_abreviado``       AUXILIAR de control: JSON compacto con las MISMAS abreviaturas de la configuración
                           especializada (códigos, enteros escalados, constantes una sola vez). Aísla cuánto del
                           ahorro viene del formato y cuánto de las abreviaturas, que también servirían a JSON.
* ``general_fromschema``   flujo estándar: ``mini from-schema`` + ``spec_block`` (idioma es).
* ``general_dominio``      flujo estándar alternativo: ``mini build`` (perfil mini-domain/1) desde muestras.
* ``especializado``        contrato diseñado a mano (ver ``especializacion``), con mapa explícito.

Toda ida y vuelta se verifica con ``verificar``: si el perfil no reconstruye el objeto original
(valores, tipos, orden de claves), lanza ``NoEquivalente`` y el perfil se descarta.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

RAIZ = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RAIZ / "src"))

from minifmt import dumps, from_json_schema, parse, spec_block  # noqa: E402
from minifmt import domain as dominio_mini  # noqa: E402
from minifmt.contract import Contract  # noqa: E402

from dominios import Dominio  # noqa: E402
from especializacion import (Especializacion, NoEquivalente, instruccion_compacta,  # noqa: E402
                             instruccion_spec_block, serializar_objeto)

PERFILES = ("json_compacto", "json_legible", "json_abreviado", "general_fromschema", "general_dominio", "especializado")
MUESTRAS_DOMINIO = 100        # registros de DESARROLLO con los que mini build infiere el contrato
EJEMPLO_REGISTROS = 2         # registros del ejemplo de las variantes «con ejemplo» (de DESARROLLO)


# ----------------------------------------------------------------------------- JSON
def json_compacto(dom: Dominio, registros: Sequence[Dict[str, Any]]) -> str:
    return json.dumps({dom.clave_json: list(registros)}, ensure_ascii=False, separators=(",", ":"))


def json_legible(dom: Dominio, registros: Sequence[Dict[str, Any]]) -> str:
    return json.dumps({dom.clave_json: list(registros)}, ensure_ascii=False, indent=2)


def esquema_json_envuelto(dom: Dominio) -> Dict[str, Any]:
    return {"type": "object", "properties": {dom.clave_json: {"type": "array", "items": dom.esquema}},
            "required": [dom.clave_json]}


def instruccion_json(dom: Dominio, ejemplo: Optional[Sequence[Dict[str, Any]]] = None) -> str:
    """Frase + JSON Schema compacto del objeto envuelto (cota favorable a JSON: sin additionalProperties)."""
    esq = json.dumps(esquema_json_envuelto(dom), ensure_ascii=False, separators=(",", ":"))
    t = ("Responde SOLO con un objeto JSON válido conforme a este JSON Schema, sin Markdown ni texto adicional:\n" + esq)
    if ejemplo:
        t += "\nEjemplo válido:\n" + json_compacto(dom, ejemplo)
    return t


def json_abreviado(esp: Especializacion, registros: Sequence[Dict[str, Any]]) -> str:
    obj = esp.codificar(registros)
    env: Dict[str, Any] = dict(obj["header"])
    env[esp.clave_json] = obj["records"]
    return json.dumps(env, ensure_ascii=False, separators=(",", ":"))


def verificar_json_abreviado(esp: Especializacion, registros: Sequence[Dict[str, Any]]) -> None:
    env = json.loads(json_abreviado(esp, registros))
    recs = env.pop(esp.clave_json)
    vuelta = esp.reconstruir({"header": env, "records": recs})
    if serializar_objeto(vuelta) != serializar_objeto(list(registros)):
        raise NoEquivalente("json_abreviado: la ida y vuelta no reproduce los registros")


# ----------------------------------------------------------------------------- general (from-schema)
def contrato_general(dom: Dominio) -> Contract:
    return from_json_schema(dom.esquema, dom.prefijo_general)


def salida_general(dom: Dominio, registros: Sequence[Dict[str, Any]]) -> str:
    return dumps({"header": {}, "records": list(registros)}, contrato_general(dom))


def instruccion_general(dom: Dominio, ejemplo: Optional[Sequence[Dict[str, Any]]] = None) -> str:
    """Lo que imprime ``mini prompt --contract C --lang es``; con ejemplo, como ``mini prompt PREFIX``
    para una familia registrada (cabecera con n = nº de registros del ejemplo)."""
    c = contrato_general(dom)
    return spec_block(c, "es", dumps({"header": {}, "records": list(ejemplo)}, c) if ejemplo else None)


def verificar_general(dom: Dominio, registros: Sequence[Dict[str, Any]]) -> None:
    c = contrato_general(dom)
    doc = parse(salida_general(dom, registros), c, strict=True)
    if serializar_objeto(doc.to_canonical()["records"]) != serializar_objeto(list(registros)):
        raise NoEquivalente("general_fromschema: la ida y vuelta no reproduce los registros")


# ----------------------------------------------------------------------------- general (mini build)
def contrato_dominio(dom: Dominio, muestras: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    return dominio_mini.infer_contract([{dom.clave_json: list(muestras)}], dom.prefijo_general + "d",
                                       record_path=[dom.clave_json])


def salida_dominio(dom: Dominio, contrato: Dict[str, Any], registros: Sequence[Dict[str, Any]]) -> str:
    return dominio_mini.encode({dom.clave_json: list(registros)}, contrato)


def instruccion_dominio(dom: Dominio, contrato: Dict[str, Any], ejemplo: Optional[Sequence[Dict[str, Any]]] = None) -> str:
    """``make_prompt`` del perfil mini-domain/1, en español; con ejemplo, como el ``prompt.es.md`` de ``mini build``."""
    ej = {dom.clave_json: list(ejemplo)} if ejemplo else None
    return dominio_mini.make_prompt(contrato, "es", ej)


def verificar_dominio(dom: Dominio, contrato: Dict[str, Any], registros: Sequence[Dict[str, Any]]) -> None:
    texto = salida_dominio(dom, contrato, registros)
    vuelta = dominio_mini.decode(texto, contrato)
    if serializar_objeto(vuelta) != serializar_objeto({dom.clave_json: list(registros)}):
        raise NoEquivalente("general_dominio: la ida y vuelta no reproduce los registros")


# ----------------------------------------------------------------------------- especializado
def salida_especializada(esp: Especializacion, registros: Sequence[Dict[str, Any]]) -> str:
    return dumps(esp.codificar(registros), esp.contrato())


def ejemplo_especializado(esp: Especializacion, ejemplo: Sequence[Dict[str, Any]]) -> str:
    return salida_especializada(esp, ejemplo)


# ----------------------------------------------------------------------------- instrucciones por variante
def instrucciones(dom: Dominio, esp: Especializacion, contrato_dom: Dict[str, Any],
                  ejemplo: Sequence[Dict[str, Any]]) -> Dict[str, Dict[str, str]]:
    """Todas las variantes de instrucción, agrupadas por perfil. ``ejemplo`` son registros de DESARROLLO."""
    ej = list(ejemplo)[:EJEMPLO_REGISTROS]
    return {
        "json": {"sin_ejemplo": instruccion_json(dom), "con_ejemplo": instruccion_json(dom, ej)},
        "general_fromschema": {"sin_ejemplo": instruccion_general(dom), "con_ejemplo": instruccion_general(dom, ej)},
        "general_dominio": {"sin_ejemplo": instruccion_dominio(dom, contrato_dom),
                            "con_ejemplo": instruccion_dominio(dom, contrato_dom, ej)},
        "especializado": {
            "compacta_sin_ejemplo": instruccion_compacta(esp),
            "compacta_con_ejemplo": instruccion_compacta(esp, ejemplo_especializado(esp, ej)),
            "spec_block_sin_ejemplo": instruccion_spec_block(esp),
            "spec_block_con_ejemplo": instruccion_spec_block(esp, ejemplo_especializado(esp, ej)),
        },
    }
