"""Definición de los tres dominios del estudio: esquema de aplicación, generador y espacio de diseño.

El ESQUEMA es el que tendría la aplicación (nombres naturales, enumeraciones con etiquetas legibles):
de él sale el perfil general (``mini from-schema``) y la instrucción JSON. El ESPACIO DE DISEÑO lista
los tratamientos que ``disenar.py`` puede probar para la configuración especializada.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List

import datos
from especializacion import Campo

RAIZ = Path(__file__).resolve().parents[2]
ESQUEMA_TICKETS = RAIZ / "examples" / "mesa-de-ayuda" / "ticket.schema.json"


@dataclass
class Dominio:
    id: str
    titulo: str
    etiqueta: str                       # representativo | favorable | sin_ahorro
    sintetico: bool
    fuente: str
    clave_json: str
    prefijo_general: str
    prefijo_especializado: str
    esquema: Dict[str, Any]
    generar: Callable[[int, int, int], List[Dict[str, Any]]]
    lotes_maximos: Callable[[int], int]
    descripcion_especializada: str = ""
    notas: List[str] = field(default_factory=list)

    def campos_base(self) -> List[Campo]:
        """Un ``Campo`` 'pasa' por propiedad del esquema, en su orden (tipos y rangos de la aplicación)."""
        req = set(self.esquema.get("required", []))
        out = []
        for nombre, p in self.esquema["properties"].items():
            if nombre not in req:
                raise ValueError("el estudio solo usa campos obligatorios")
            t = p["type"]
            if "enum" in p:
                c = Campo(nombre, tipo="enum", valores=list(p["enum"]), desc=p.get("description", ""))
            elif t == "string" and p.get("format") == "date":
                c = Campo(nombre, tipo="date", desc=p.get("description", ""))
            elif t == "string":
                c = Campo(nombre, tipo="str", desc=p.get("description", ""))
            elif t == "integer":
                c = Campo(nombre, tipo="int", minimo=p.get("minimum"), maximo=p.get("maximum"), desc=p.get("description", ""))
            elif t == "number":
                c = Campo(nombre, tipo="float", minimo=p.get("minimum"), maximo=p.get("maximum"), desc=p.get("description", ""))
            elif t == "boolean":
                c = Campo(nombre, tipo="bool", desc=p.get("description", ""))
            else:
                raise ValueError(f"tipo no soportado: {t}")
            out.append(c)
        return out


def _esquema_tickets() -> Dict[str, Any]:
    return json.loads(ESQUEMA_TICKETS.read_text(encoding="utf-8"))


ESQUEMA_EVENTOS = {
    "title": "Eventos de planta",
    "type": "object",
    "properties": {
        "id_equipo": {"type": "string", "description": "código del equipo (EQ- y cuatro dígitos)"},
        "planta": {"type": "string", "enum": datos.EV_PLANTAS},
        "tipo_evento": {"type": "string", "enum": datos.EV_TIPOS},
        "severidad": {"type": "string", "enum": datos.EV_SEVERIDAD},
        "estado": {"type": "string", "enum": datos.EV_ESTADO},
        "fecha": {"type": "string", "format": "date", "description": "día del reporte"},
        "hora": {"type": "string", "description": "hora local HH:MM"},
        "valor": {"type": "number", "minimum": -50, "maximum": 200, "description": "lectura del sensor con un decimal"},
        "confirmado": {"type": "boolean"},
    },
    "required": ["id_equipo", "planta", "tipo_evento", "severidad", "estado", "fecha", "hora", "valor", "confirmado"],
}

ESQUEMA_COMENTARIOS = {
    "title": "Comentarios",
    "type": "object",
    "properties": {
        "postId": {"type": "integer", "minimum": 1, "description": "publicación comentada"},
        "id": {"type": "integer", "minimum": 1, "description": "identificador del comentario"},
        "name": {"type": "string", "description": "título del comentario"},
        "email": {"type": "string", "description": "correo de quien comenta"},
        "body": {"type": "string", "description": "texto del comentario"},
    },
    "required": ["postId", "id", "name", "email", "body"],
}


def _lotes_sinteticos(n: int) -> int:
    return 5


def _lotes_comentarios(n: int) -> int:
    return max(1, min(5, len(datos.cargar_comentarios()[datos.COM_PRUEBA]) // n))


def dominios() -> Dict[str, Dominio]:
    return {
        "tickets": Dominio(
            id="tickets", titulo="Tickets de soporte (hilo de «Cómo funciona»)", etiqueta="representativo",
            sintetico=True, fuente="sintético determinista: experiments/optimizacion/datos.py::generar_tickets",
            clave_json="tickets", prefijo_general="tk", prefijo_especializado="tke",
            esquema=_esquema_tickets(), generar=datos.generar_tickets, lotes_maximos=_lotes_sinteticos,
            descripcion_especializada="Tickets de soporte.",
            notas=["Dos enumeraciones cortas, un identificador con prefijo constante, un resumen de texto libre y un entero acotado."]),
        "eventos": Dominio(
            id="eventos", titulo="Eventos de planta (muchos campos cortos y enumerados)", etiqueta="favorable",
            sintetico=True, fuente="sintético determinista: experiments/optimizacion/datos.py::generar_eventos",
            clave_json="eventos", prefijo_general="ev", prefijo_especializado="eve",
            esquema=ESQUEMA_EVENTOS, generar=datos.generar_eventos, lotes_maximos=_lotes_sinteticos,
            descripcion_especializada="Eventos de planta de un día.",
            notas=["CASO FAVORABLE: diseñado con esa forma (cuatro enumeraciones de etiqueta larga, fecha constante por lote, "
                   "hora, decimal de un dígito y booleano). El ahorro observado aquí NO es una promesa general."]),
        "comentarios": Dominio(
            id="comentarios", titulo="Comentarios con texto libre largo (JSONPlaceholder)", etiqueta="sin_ahorro",
            sintetico=False, fuente="benchmark/public/data/comments.json (JSONPlaceholder, MIT; datos públicos de prueba)",
            clave_json="comments", prefijo_general="cm", prefijo_especializado="cme",
            esquema=ESQUEMA_COMENTARIOS, generar=datos.generar_comentarios, lotes_maximos=_lotes_comentarios,
            descripcion_especializada="Comentarios.",
            notas=["Texto libre largo: no hay enumeraciones ni constantes que abreviar; se publica aunque no haya ahorro."]),
    }
