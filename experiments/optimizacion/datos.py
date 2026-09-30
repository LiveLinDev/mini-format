"""Conjuntos de datos del estudio de optimización.

Dos de los tres dominios son SINTÉTICOS y deterministas (semilla registrada, sin datos personales):

* ``tickets``  — mesa de ayuda: el hilo de «Cómo funciona». Caso REPRESENTATIVO.
* ``eventos``  — registro de eventos de planta: muchos campos cortos y enumerados. Caso FAVORABLE,
  diseñado a propósito con esa forma; su ahorro NO es una promesa general.

El tercero es una muestra PÚBLICA archivada (no sintética, pero de prueba y con licencia MIT):

* ``comentarios`` — los comentarios de JSONPlaceholder de ``benchmark/public/data/comments.json``
  (texto libre largo). Caso de AHORRO PEQUEÑO (con lotes pequeños no ahorra en el total).

Los generadores usan una sola fuente aleatoria por lote y consumen el flujo registro a registro, de
modo que el lote de ``n`` registros es siempre el prefijo del lote de ``m > n`` para el mismo
(semilla, índice de lote). Las plantillas de texto fueron redactadas con asistencia de IA
(procedencia ``asistido_ia`` del material de partida); los registros los produce el guion.
"""
from __future__ import annotations

import datetime as dt
import json
import random
from pathlib import Path
from typing import Any, Dict, List

RAIZ = Path(__file__).resolve().parents[2]
COMENTARIOS = RAIZ / "benchmark" / "public" / "data" / "comments.json"

# Semillas registradas. «desarrollo» sirve para diseñar la configuración especializada
# (orden de campos, esquema de códigos); «prueba» para medirla. No se mezclan.
SEMILLA_DESARROLLO = 20260930
SEMILLA_PRUEBA = 20261001

# ----------------------------------------------------------------------------- tickets
TICKETS_ENUM_PRIORIDAD = ["baja", "media", "alta"]
TICKETS_ENUM_CATEGORIA = ["acceso", "pago", "error", "consulta"]

_PROD = ["el portal web", "la aplicación móvil", "la app de escritorio", "el panel de administración",
         "el módulo de reportes", "la pasarela de pagos", "la facturación electrónica", "el buscador",
         "la exportación a Excel", "la sincronización con el ERP", "la agenda de citas", "el chat de atención"]
_PROB = {
    "acceso": ["No puede iniciar sesión en {p}", "No llega el código de verificación de {p}",
               "Usuario bloqueado tras varios intentos en {p}", "Acceso con Google caído en {p}",
               "Contraseña restablecida no funciona en {p}"],
    "pago": ["Cobro duplicado en {p}", "Transferencia no reflejada en {p}", "Pago con tarjeta rechazado en {p}",
             "Reembolso incompleto en {p}", "No aparece el comprobante de pago en {p}"],
    "error": ["Error 500 al generar documentos en {p}", "{p} se cierra al adjuntar un archivo",
              "{p} ignora las palabras con tilde", "Datos duplicados al guardar en {p}",
              "La pantalla queda en blanco al abrir {p}", "{p} se queda cargando sin terminar"],
    "consulta": ["Cómo exportar el historial desde {p}", "Cambio del correo asociado en {p}",
                 "Capacitación para el equipo sobre {p}", "Consulta sobre varios usuarios simultáneos en {p}",
                 "Solicitud de copia de datos desde {p}"],
}
_DETALLE = ["", "", "", " (desde el martes)", " (afecta a todo el equipo)", " (urgente para hoy)",
            " (solo en el celular)", " (tras la última actualización)", " (segunda vez que escribe)"]
_PESO_CAT = [("acceso", 25), ("pago", 20), ("error", 35), ("consulta", 20)]
_PESO_PRIO = {"acceso": (20, 50, 30), "pago": (10, 40, 50), "error": (10, 35, 55), "consulta": (70, 25, 5)}


def _elegir(r: random.Random, pesos):
    total = sum(p for _, p in pesos)
    x = r.random() * total
    for v, p in pesos:
        x -= p
        if x < 0:
            return v
    return pesos[-1][0]


def generar_tickets(semilla: int, lote: int, n: int) -> List[Dict[str, Any]]:
    """n tickets de un lote. Identificadores correlativos T-<4 dígitos> (sin ceros a la izquierda)."""
    r = random.Random(f"tickets:{semilla}:{lote}")
    base = 1100 + 1000 * lote
    out = []
    for i in range(n):
        cat = _elegir(r, _PESO_CAT)
        prio = TICKETS_ENUM_PRIORIDAD[_elegir(r, list(zip(range(3), _PESO_PRIO[cat])))]
        prob = _PROB[cat][int(r.random() * len(_PROB[cat]))]
        prod = _PROD[int(r.random() * len(_PROD))]
        resumen = prob.replace("{p}", prod) + _DETALLE[int(r.random() * len(_DETALLE))]
        if prio == "alta":
            horas = 2 + int(r.random() * 11)
        elif prio == "media":
            horas = 1 + int(r.random() * 8)
        else:
            horas = 1 + int(r.random() * 4)
        if r.random() < 0.05:
            horas = 12 + int(r.random() * 29)        # valores atípicos hasta 40
        out.append({"id": f"T-{base + i}", "prioridad": prio, "categoria": cat, "resumen": resumen, "horas": horas})
    return out


# ----------------------------------------------------------------------------- eventos
EV_PLANTAS = ["almacen_norte", "almacen_sur", "planta_ensamblaje", "planta_pintura", "patio_exterior",
              "sala_de_control", "taller_mecanico", "muelle_de_carga"]
EV_TIPOS = ["temperatura_fuera_de_rango", "vibracion_excesiva", "apertura_no_autorizada", "falla_de_comunicacion",
            "mantenimiento_programado", "lectura_normal", "bateria_baja"]
EV_SEVERIDAD = ["informativa", "advertencia", "critica"]
EV_ESTADO = ["abierto", "en_progreso", "resuelto", "descartado"]
_PESO_TIPO = [("lectura_normal", 30), ("temperatura_fuera_de_rango", 18), ("vibracion_excesiva", 14),
              ("bateria_baja", 12), ("falla_de_comunicacion", 10), ("apertura_no_autorizada", 6),
              ("mantenimiento_programado", 10)]
_SEV_POR_TIPO = {"lectura_normal": (85, 13, 2), "temperatura_fuera_de_rango": (10, 50, 40),
                 "vibracion_excesiva": (10, 55, 35), "bateria_baja": (40, 55, 5),
                 "falla_de_comunicacion": (20, 55, 25), "apertura_no_autorizada": (5, 30, 65),
                 "mantenimiento_programado": (90, 10, 0)}
_RANGO_VALOR = {"lectura_normal": (15.0, 35.0), "temperatura_fuera_de_rango": (60.0, 150.0),
                "vibracion_excesiva": (8.0, 45.0), "bateria_baja": (1.0, 15.0),
                "falla_de_comunicacion": (0.0, 5.0), "apertura_no_autorizada": (0.0, 1.0),
                "mantenimiento_programado": (0.0, 2.0)}
EV_FECHA_BASE = dt.date(2026, 10, 1)


def generar_eventos(semilla: int, lote: int, n: int) -> List[Dict[str, Any]]:
    """n eventos de UN MISMO DÍA (el lote es el reporte de un día): ``fecha`` es constante en el lote.

    Los eventos salen en orden cronológico. ``valor`` tiene un decimal; ``hora`` es HH:MM.
    """
    r = random.Random(f"eventos:{semilla}:{lote}")
    fecha = (EV_FECHA_BASE + dt.timedelta(days=lote)).isoformat()
    minutos = 0
    out = []
    for i in range(n):
        tipo = _elegir(r, _PESO_TIPO)
        sev = EV_SEVERIDAD[_elegir(r, list(zip(range(3), _SEV_POR_TIPO[tipo])))]
        if sev == "critica":
            est = _elegir(r, [("abierto", 45), ("en_progreso", 40), ("resuelto", 15)])
        elif sev == "advertencia":
            est = _elegir(r, [("abierto", 25), ("en_progreso", 25), ("resuelto", 40), ("descartado", 10)])
        else:
            est = _elegir(r, [("abierto", 5), ("resuelto", 55), ("descartado", 40)])
        lo, hi = _RANGO_VALOR[tipo]
        valor = round(lo + r.random() * (hi - lo), 1)
        minutos = min(1439, minutos + int(r.random() * 12))
        out.append({
            "id_equipo": f"EQ-{1 + int(r.random() * 240):04d}",
            "planta": EV_PLANTAS[int(r.random() * len(EV_PLANTAS))],
            "tipo_evento": tipo, "severidad": sev, "estado": est,
            "fecha": fecha, "hora": f"{minutos // 60:02d}:{minutos % 60:02d}",
            "valor": valor, "confirmado": r.random() < (0.85 if sev != "informativa" else 0.3)})
    return out


# ----------------------------------------------------------------------------- comentarios
# Partición fija del snapshot: los primeros 150 para diseñar, los 350 restantes para medir.
COM_DESARROLLO = slice(0, 150)
COM_PRUEBA = slice(150, 500)


def cargar_comentarios() -> List[Dict[str, Any]]:
    with open(COMENTARIOS, encoding="utf-8") as fh:
        return json.load(fh)


def generar_comentarios(semilla: int, lote: int, n: int) -> List[Dict[str, Any]]:
    """Fragmento consecutivo del snapshot público. ``semilla`` decide el tramo (desarrollo/prueba);
    ``lote`` desplaza el inicio de n en n dentro del tramo (envolviendo si hace falta)."""
    todos = cargar_comentarios()
    tramo = todos[COM_DESARROLLO] if semilla == SEMILLA_DESARROLLO else todos[COM_PRUEBA]
    ini = (lote * n) % len(tramo)
    sel = (tramo + tramo)[ini:ini + n]
    return [dict(x) for x in sel]
