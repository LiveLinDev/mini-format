# -*- coding: utf-8 -*-
"""Entrada sintética de la mesa de ayuda: mensajes de clientes variados y reproducibles.

El generador es combinatorio, no una lista de plantillas repetidas: cada mensaje combina saludo,
producto, problema, una referencia variable (pedido, factura, monto o fecha), un detalle y un cierre.
El espacio supera los 10^9 mensajes distintos, así que en una corrida de 200 000 prácticamente no
hay repeticiones y la longitud varía como en un caso real.

Usa mulberry32, el mismo generador pseudoaleatorio que la página del sitio, de modo que una semilla
produce exactamente los mismos mensajes en Python y en el navegador.

    python experiments/v7_escalamiento/entrada.py --n 20000     # diagnóstico de variedad
"""
from __future__ import annotations

from typing import Dict, List

SEMILLA = 20260917
ENTRADA_VERSION = "v2: combinatoria (saludo × problema × producto por categoría × referencia × detalle × cierre)"

SALUDOS = ["Hola,", "Buen día,", "Buenas tardes,", "Estimados,", "Hola, equipo de soporte:",
           "Buenas,", "Hola de nuevo,", "Escribo porque"]

# Productos plausibles para cada categoría: la combinación es libre dentro de la categoría, no entre todas,
# para que no salgan mensajes absurdos como un reembolso en la agenda de citas.
PRODUCTOS_POR_CATEGORIA = {
    "acceso": ["el portal web", "la aplicación móvil", "la app de escritorio", "el panel de administración",
               "el inicio de sesión único", "el chat de atención"],
    "pago": ["la pasarela de pagos", "la facturación electrónica", "el carrito de compras", "el portal web",
             "la aplicación móvil", "el módulo de cobranzas"],
    "error": ["la aplicación móvil", "el portal web", "la app de escritorio", "el buscador del catálogo",
              "la exportación a Excel", "la sincronización con el ERP", "la firma digital",
              "el seguimiento de envíos", "la agenda de citas", "el módulo de reportes"],
    "consulta": ["el módulo de reportes", "la exportación a Excel", "la agenda de citas", "el portal web",
                 "la aplicación móvil", "el catálogo de productos", "el seguimiento de envíos"],
}

# (plantilla del problema, categoría sugerida). {p} es el producto.
PROBLEMAS = [
    ("no puedo entrar a mi cuenta desde que cambié la contraseña en {p}", "acceso"),
    ("no me llega el código de verificación al usar {p}", "acceso"),
    ("mi usuario quedó bloqueado tras varios intentos en {p}", "acceso"),
    ("el acceso con Google dejó de funcionar en {p}", "acceso"),
    ("me cobraron dos veces la suscripción en {p}", "pago"),
    ("la transferencia no se refleja en {p}", "pago"),
    ("el pago con tarjeta fue rechazado sin motivo en {p}", "pago"),
    ("me devolvieron menos de lo acordado en {p}", "pago"),
    ("no aparece el comprobante de mi pago en {p}", "pago"),
    ("{p} se cierra sola al adjuntar un archivo", "error"),
    ("aparece un error 500 al generar documentos en {p}", "error"),
    ("{p} ignora las palabras con tilde al buscar", "error"),
    ("los datos se guardan duplicados en {p}", "error"),
    ("{p} se queda cargando y nunca termina", "error"),
    ("la pantalla queda en blanco al abrir {p}", "error"),
    ("quisiera saber cómo exportar mi historial desde {p}", "consulta"),
    ("necesito cambiar el correo asociado en {p}", "consulta"),
    ("pido capacitación para mi equipo sobre {p}", "consulta"),
    ("quiero saber si {p} permite varios usuarios a la vez", "consulta"),
    ("cómo solicito una copia de mis datos en {p}", "consulta"),
]

REFERENCIAS = ["(pedido {n})", "(factura F-{n})", "(caso {n})", "(orden {n})", "(contrato {n})", ""]

DETALLES = ["Ya reinicié la aplicación.", "Es urgente para hoy.", "Me pasa desde el martes.",
            "Tengo capturas del problema.", "Nadie me ha respondido aún.", "Solo ocurre en el celular.",
            "Le pasa a todo mi equipo.", "Perdí trabajo por esto.", "Probé con otro navegador y sigue igual.",
            "Mi conexión funciona bien.", "Me ocurre desde la última actualización.",
            "Es la segunda vez que escribo.", "Un compañero reportó lo mismo.", "Ya limpié la caché."]

CIERRES = ["Agradezco su ayuda.", "Quedo atento.", "Espero su respuesta.", "Gracias de antemano.",
           "Necesito una solución pronto.", "", "Por favor confírmenme.", "Gracias."]


def mulberry32(semilla: int):
    """Mismo generador pseudoaleatorio que usa la página, para que la entrada sea idéntica."""
    estado = semilla & 0xFFFFFFFF

    def siguiente() -> float:
        nonlocal estado
        estado = (estado + 0x6D2B79F5) & 0xFFFFFFFF
        x = estado
        x = ((x ^ (x >> 15)) * (1 | x)) & 0xFFFFFFFF
        x = (x + (((x ^ (x >> 7)) * (61 | x)) & 0xFFFFFFFF)) & 0xFFFFFFFF
        x ^= x >> 14
        return (x & 0xFFFFFFFF) / 4294967296

    return siguiente


def mensajes(n: int, desde: int = 1, semilla: int = SEMILLA) -> List[Dict[str, str]]:
    """n mensajes de clientes con id correlativo; la misma semilla da siempre los mismos textos.

    Cada mensaje trae además la categoría del problema y el asunto sin saludo ni cierre, de modo que
    otras piezas (por ejemplo la página de ejemplo del sitio) puedan derivar un lote coherente.
    """
    r = mulberry32(semilla + desde)
    out = []
    for i in range(n):
        saludo = SALUDOS[int(r() * len(SALUDOS))]
        problema, categoria = PROBLEMAS[int(r() * len(PROBLEMAS))]
        catalogo = PRODUCTOS_POR_CATEGORIA[categoria]
        producto = catalogo[int(r() * len(catalogo))]
        plantilla_ref = REFERENCIAS[int(r() * len(REFERENCIAS))]
        referencia = plantilla_ref.replace("{n}", str(10000 + int(r() * 89999)))
        detalle = DETALLES[int(r() * len(DETALLES))]
        cierre = CIERRES[int(r() * len(CIERRES))]
        cuerpo = problema.replace("{p}", producto)
        texto = " ".join(x for x in [saludo, cuerpo + (" " + referencia if referencia else "") + ".",
                                     detalle, cierre] if x)
        out.append({"id": f"T-{desde + i:05d}", "mensaje": texto, "categoria": categoria,
                    "asunto": cuerpo.replace("{p}", producto)})
    return out


def combinaciones() -> int:
    por_problema = sum(len(PRODUCTOS_POR_CATEGORIA[c]) for _, c in PROBLEMAS)
    return len(SALUDOS) * por_problema * len(REFERENCIAS) * 89999 * len(DETALLES) * len(CIERRES)


if __name__ == "__main__":
    import argparse
    import statistics

    ap = argparse.ArgumentParser(description="Diagnóstico de variedad de la entrada sintética")
    ap.add_argument("--n", type=int, default=20000)
    a = ap.parse_args()
    ms = mensajes(a.n)
    textos = [m["mensaje"] for m in ms]
    unicos = len(set(textos))
    largos = [len(t) for t in textos]
    print(f"combinaciones posibles: {combinaciones():,}")
    print(f"mensajes generados: {len(textos):,} · únicos: {unicos:,} ({100 * unicos / len(textos):.2f} %)")
    print(f"longitud en caracteres: mediana {statistics.median(largos):.0f}, "
          f"mín {min(largos)}, máx {max(largos)}")
    print("\nejemplos:")
    for m in ms[:4]:
        print(f"  {m['id']}: {m['mensaje']}")
