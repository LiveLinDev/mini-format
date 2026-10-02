"""Construye el repositorio de tareas T1-T4 de V6b con respuestas CONGELADAS.

Uso (desde la raíz del repositorio, con PYTHONPATH=src):

    python evidencia/v6/tareas/construir_tareas.py            # regenera participante/ y observador/
    python evidencia/v6/tareas/construir_tareas.py --verificar # no escribe: falla si el disco difiere

Qué sale de archivos REALES del repositorio y qué se redactó aquí:

* Variante A de T1: ``examples/mesa-de-ayuda/ticket.schema.json`` y las grabaciones
  ``grabaciones/{json,mini}/error.*`` se copian byte a byte (su SHA-256 queda en
  ``respuestas_congeladas.json``).
* Contrato ``tk`` y contrato ``inc``: se generan con ``minifmt.from_json_schema`` (el mismo código
  de ``mini from-schema``), no se escriben a mano.
* Variante B de T1, T2 y T3: DATASETS SINTÉTICOS redactados por el equipo (sin datos de ningún
  sistema real ni personales). No son salida de ningún modelo. Sus textos .mini se serializan con
  ``minifmt.dumps`` a partir de las listas de registros de este archivo; los defectos se introducen
  a propósito y se documentan en ``observador/*.referencia.json``.
* T4 parte de ``forks/cat/contract.json`` (contrato real de otro dominio: catálogo de productos).
* ``participante/guia_mini.md`` usa la copia congelada de la guía pública guardada en
  ``fuentes/quickstart.es.md``. Su commit de origen y SHA-256 quedan fijados aquí: editar la
  documentación pública no cambia los materiales del estudio.

Las respuestas "esperadas" son las LISTAS de registros escritas aquí a mano: son el oráculo
independiente contra el que se comprueba después el analizador de minifmt (ver
``tests/test_v6_tareas.py``).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Tuple

RAIZ = Path(__file__).resolve().parents[3]
AQUI = Path(__file__).resolve().parent
sys.path.insert(0, str(RAIZ / "src"))

from minifmt import Contract, dumps  # noqa: E402
from minifmt.schema import from_json_schema  # noqa: E402

EJ = RAIZ / "examples" / "mesa-de-ayuda"
GUIA_ORIGEN = {
    "ruta": "sitio/content/quickstart.es.md",
    "commit": "67d99eb5372719e8d83580f5ed74cb3d977a4220",
    "copia": "fuentes/quickstart.es.md",
    "sha256": "204e6d5cc83279ad8ae9105687fe5ae6ad93b4372c0195c9eaaf7055be540e8b",
}

# Topes en minutos (Plan de Validación v3, tabla T10): 30 + 30 + 15 + 10 + 15 = 100.
TOPES_MIN = {"T1_json": 30, "T1_mini": 30, "T2": 15, "T3": 10, "T4": 15}
INTRO_MIN, CIERRE_MIN, SESION_MAX_MIN = 10, 10, 120

# ---------------------------------------------------------------------------------------------
# Datos sintéticos (variante B de T1, T2, T3) y dominio de T4
# ---------------------------------------------------------------------------------------------
# Variante B de T1: «incidencias de infraestructura». Misma forma que los tickets de la variante A:
# cadena, enum de 3, enum de 4, cadena y entero acotado; 10 registros; UN registro con valor fuera
# de la enumeración (E10). Cambian nombres, valores y posición del defecto para que no se pueda
# reutilizar el código de la otra condición tal cual.
ESQUEMA_B = {
    "title": "Incidencias de infraestructura",
    "type": "object",
    "properties": {
        "codigo": {"type": "string", "description": "código de la incidencia"},
        "severidad": {"type": "string", "enum": ["menor", "mayor", "critica"]},
        "sistema": {"type": "string", "enum": ["red", "correo", "vpn", "impresion"]},
        "descripcion": {"type": "string", "description": "descripción breve de la incidencia"},
        "minutos": {"type": "integer", "minimum": 0, "maximum": 480,
                    "description": "minutos estimados de atención"},
    },
    "required": ["codigo", "severidad", "sistema", "descripcion", "minutos"],
}
REGISTROS_B: List[Dict[str, Any]] = [
    {"codigo": "INC-301", "severidad": "mayor", "sistema": "vpn", "descripcion": "Las conexiones VPN se caen cada diez minutos", "minutos": 90},
    {"codigo": "INC-302", "severidad": "menor", "sistema": "impresion", "descripcion": "Atasco de papel en la impresora del piso 3", "minutos": 30},
    {"codigo": "INC-303", "severidad": "critica", "sistema": "red", "descripcion": "Sin conectividad en el laboratorio de cómputo", "minutos": 180},
    {"codigo": "INC-304", "severidad": "menor", "sistema": "correo", "descripcion": "El buzón compartido no muestra los mensajes nuevos", "minutos": 45},
    {"codigo": "INC-305", "severidad": "mayor", "sistema": "correo", "descripcion": "Rebote de mensajes hacia dominios externos", "minutos": 120},
    {"codigo": "INC-306", "severidad": "critica", "sistema": "vpn", "descripcion": "Nadie puede autenticarse en la VPN de la sede norte", "minutos": 240},
    {"codigo": "INC-307", "severidad": "menor", "sistema": "red", "descripcion": "Puerto de red del aula 204 sin enlace", "minutos": 60},
    {"codigo": "INC-308", "severidad": "mayor", "sistema": "impresion", "descripcion": "La cola de impresión se bloquea al enviar PDF grandes", "minutos": 75},
    {"codigo": "INC-309", "severidad": "menor", "sistema": "correo", "descripcion": "Firma institucional con el logotipo desactualizado", "minutos": 20},
    {"codigo": "INC-310", "severidad": "mayor", "sistema": "red", "descripcion": "Latencia alta en el wifi de la biblioteca", "minutos": 150},
]
POSICION_DEFECTO_B = 7           # 1-based: INC-307 lleva sistema «telefonia»
VALOR_DEFECTO_B = ("sistema", "telefonia")

# T2: 12 tickets del contrato tk; el registro 7 lleva un «|» sin escapar dentro del resumen.
TICKETS_T2: List[Dict[str, Any]] = [
    {"id": "T-2201", "prioridad": "alta", "categoria": "acceso", "resumen": "No puedo entrar al portal con el segundo factor", "horas": 2},
    {"id": "T-2202", "prioridad": "media", "categoria": "pago", "resumen": "El comprobante de pago llegó sin el número de operación", "horas": 1},
    {"id": "T-2203", "prioridad": "baja", "categoria": "consulta", "resumen": "Dónde descargo la factura del mes anterior", "horas": 1},
    {"id": "T-2204", "prioridad": "alta", "categoria": "error", "resumen": "La aplicación móvil se congela al abrir el perfil", "horas": 6},
    {"id": "T-2205", "prioridad": "media", "categoria": "acceso", "resumen": "El enlace de restablecimiento caduca de inmediato", "horas": 2},
    {"id": "T-2206", "prioridad": "alta", "categoria": "pago", "resumen": "Doble cargo por la misma orden de compra", "horas": 3},
    {"id": "T-2207", "prioridad": "media", "categoria": "error", "resumen": "El exportador falla con nombres como A|B en la columna cliente", "horas": 4},
    {"id": "T-2208", "prioridad": "baja", "categoria": "consulta", "resumen": "Horario de atención del soporte telefónico", "horas": 1},
    {"id": "T-2209", "prioridad": "media", "categoria": "error", "resumen": "Los filtros del reporte no recuerdan la última selección", "horas": 5},
    {"id": "T-2210", "prioridad": "alta", "categoria": "acceso", "resumen": "Cuenta bloqueada tras tres intentos fallidos", "horas": 1},
    {"id": "T-2211", "prioridad": "baja", "categoria": "pago", "resumen": "Solicitud de factura a nombre de otra empresa", "horas": 2},
    {"id": "T-2212", "prioridad": "media", "categoria": "consulta", "resumen": "Diferencia entre el plan básico y el plan profesional", "horas": 1},
]
POSICION_DEFECTO_T2 = 7

# T3: 15 tickets declarados; la respuesta se corta dentro del resumen del registro 12.
TICKETS_T3: List[Dict[str, Any]] = [
    {"id": "T-3301", "prioridad": "alta", "categoria": "acceso", "resumen": "No llega el correo de confirmación de la cuenta", "horas": 2},
    {"id": "T-3302", "prioridad": "media", "categoria": "pago", "resumen": "El cupón de descuento no se aplica al carrito", "horas": 2},
    {"id": "T-3303", "prioridad": "baja", "categoria": "consulta", "resumen": "Cómo cambiar el idioma de la interfaz", "horas": 1},
    {"id": "T-3304", "prioridad": "alta", "categoria": "error", "resumen": "Pantalla en blanco al iniciar la aplicación de escritorio", "horas": 7},
    {"id": "T-3305", "prioridad": "media", "categoria": "acceso", "resumen": "El token de sesión expira antes de terminar el trámite", "horas": 3},
    {"id": "T-3306", "prioridad": "alta", "categoria": "pago", "resumen": "Pago rechazado con tarjeta aceptada en otra tienda", "horas": 4},
    {"id": "T-3307", "prioridad": "media", "categoria": "error", "resumen": "Las tildes aparecen rotas en el reporte exportado", "horas": 3},
    {"id": "T-3308", "prioridad": "baja", "categoria": "consulta", "resumen": "Requisitos mínimos para instalar el cliente", "horas": 1},
    {"id": "T-3309", "prioridad": "alta", "categoria": "error", "resumen": "Fallo 502 intermitente al guardar el formulario", "horas": 8},
    {"id": "T-3310", "prioridad": "media", "categoria": "acceso", "resumen": "No se puede vincular la cuenta con el proveedor externo", "horas": 3},
    {"id": "T-3311", "prioridad": "baja", "categoria": "pago", "resumen": "Consulta sobre el ciclo de facturación anual", "horas": 1},
    {"id": "T-3312", "prioridad": "media", "categoria": "error", "resumen": "El corrector ortográfico subraya palabras correctas", "horas": 2},
    {"id": "T-3313", "prioridad": "alta", "categoria": "acceso", "resumen": "Cuenta suspendida sin aviso previo", "horas": 2},
    {"id": "T-3314", "prioridad": "media", "categoria": "consulta", "resumen": "Límite de archivos adjuntos por mensaje", "horas": 1},
    {"id": "T-3315", "prioridad": "baja", "categoria": "error", "resumen": "El modo oscuro no recuerda la preferencia", "horas": 2},
]
REGISTROS_COMPLETOS_T3 = 11       # los registros 1-11 llegan enteros
CORTE_T3_CARACTERES = len("T-3312|media|error|El corrector ortográfico subraya palab")

# T4: dominio destino «solicitudes de cambio». Contrato de partida: forks/cat (catálogo de productos).
ESPECIFICACION_T4 = [
    ("codigo", "cadena", "único en el documento"),
    ("titulo", "cadena", "texto libre"),
    ("tipo", "enumeración", "estandar | normal | emergencia"),
    ("riesgo", "enumeración", "bajo | medio | alto"),
    ("ventana_min", "entero", "de 15 a 480 (minutos de la ventana de cambio)"),
    ("sistemas", "lista de cadenas", "de 1 a 5 elementos"),
    ("puntaje", "decimal, opcional", "de 0 a 10 (puntaje de riesgo; puede faltar)"),
]
PREFIJO_T4 = "chg"
CASO_POSITIVO_T4 = [
    {"codigo": "CHG-201", "titulo": "Actualizar el firmware del switch de la sede norte", "tipo": "normal", "riesgo": "medio", "ventana_min": 120, "sistemas": ["red", "switch"], "puntaje": 3.5},
    {"codigo": "CHG-202", "titulo": "Rotar los certificados del portal de autoservicio", "tipo": "estandar", "riesgo": "bajo", "ventana_min": 45, "sistemas": ["portal"], "puntaje": None},
    {"codigo": "CHG-203", "titulo": "Migrar el relé de correo a la nueva subred", "tipo": "emergencia", "riesgo": "alto", "ventana_min": 240, "sistemas": ["correo", "dns", "firewall"], "puntaje": 8.0},
]
# Caso negativo: idéntico en forma; el registro 2 trae una ventana de 600 min (> 480): debe dar E13.
CASO_NEGATIVO_T4 = [
    {"codigo": "CHG-301", "titulo": "Reiniciar el balanceador del portal", "tipo": "normal", "riesgo": "medio", "ventana_min": 30, "sistemas": ["portal"], "puntaje": 2.0},
    {"codigo": "CHG-302", "titulo": "Reemplazar el arreglo de discos del servidor de archivos", "tipo": "normal", "riesgo": "alto", "ventana_min": 600, "sistemas": ["almacenamiento"], "puntaje": 7.5},
    {"codigo": "CHG-303", "titulo": "Activar la regla de filtrado del firewall perimetral", "tipo": "estandar", "riesgo": "bajo", "ventana_min": 15, "sistemas": ["firewall"], "puntaje": None},
]
LINEA_DEFECTO_T4 = 3              # línea física (cabecera = 1): segundo registro


# ---------------------------------------------------------------------------------------------
# Utilidades
# ---------------------------------------------------------------------------------------------
def sha(datos: bytes) -> str:
    return hashlib.sha256(datos).hexdigest()


def compacto(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False, separators=(",", ":"))


def bonito(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False, indent=2) + "\n"


def contrato_de(esquema: Dict[str, Any], prefijo: str) -> Contract:
    return from_json_schema(esquema, prefijo)


def texto_mini(contrato: Contract, registros: List[Dict[str, Any]]) -> str:
    return dumps({"header": {"n": len(registros)}, "records": registros}, contrato) + "\n"


def tk_y_b() -> Tuple[Contract, Contract, Dict[str, Any]]:
    esquema_a = json.loads((EJ / "ticket.schema.json").read_text(encoding="utf-8"))
    return contrato_de(esquema_a, "tk"), contrato_de(ESQUEMA_B, "inc"), esquema_a


# ---------------------------------------------------------------------------------------------
# Textos de los enunciados (español; los mismos pasos para ambas condiciones de T1)
# ---------------------------------------------------------------------------------------------
def enunciado_t1(variante: str, condicion: str) -> str:
    a = variante == "A"
    entidad = "ticket de soporte" if a else "incidencia de infraestructura"
    plural = "tickets" if a else "incidencias"
    clave = "tickets" if a else "incidencias"
    json_c = condicion == "json"
    if json_c:
        archivo, contrato = "respuesta.json", "ticket.schema.json" if a else "esquema_inc.json"
        herramientas = ("Python estándar (`json`) y la biblioteca `jsonschema`, ya instalada. "
                        "Puedes usar la documentación que quieras.")
        formato = (f"Una respuesta de un modelo: un objeto JSON con la clave `{clave}` que contiene una lista de "
                   f"{plural}.")
    else:
        archivo, contrato = "respuesta.mini", "contrato_tk.json" if a else "contrato_inc.json"
        herramientas = ("La biblioteca `minifmt` (ya instalada) y la guía `../guia_mini.md`. "
                        "Puedes usar la documentación que quieras.")
        formato = (f"Una respuesta de un modelo en formato `.mini`: una línea de cabecera y un {entidad} por línea.")
    return f"""# T1 ({'JSON' if json_c else '.mini'}) · variante {variante} · tope {TOPES_MIN['T1_json' if json_c else 'T1_mini']} minutos

**Situación.** Una aplicación de mesa de ayuda recibe la respuesta de un modelo de lenguaje con {plural} y debe
usarla. Tu trabajo es completar un cliente pequeño que lea la respuesta, la valide contra el contrato y
entregue los registros buenos aunque alguno venga mal.

**Qué recibes**

- `{archivo}`: {formato}
- `{contrato}`: el contrato que la aplicación ya tenía.
- `cliente.py`: esqueleto con la función `procesar(texto)` por completar. Puedes escribir tu cliente en Python
  o en TypeScript; lo único que se comprueba es el archivo de salida.

**Qué debe hacer `procesar`**

1. Leer la respuesta y validar **cada registro** contra el contrato.
2. Devolver `{{"validos": [...], "rechazados": [...]}}`.
3. `validos`: los registros que cumplen el contrato, **tal como vienen** (mismos valores, mismos tipos, mismo
   orden). No se corrige ni se adivina ningún valor.
4. `rechazados`: un elemento `{{"posicion": N, "motivo": "..."}}` por cada registro que incumple el contrato.
   `posicion` es el número de orden del registro dentro de la respuesta, empezando en 1. El motivo es texto libre.
5. Un registro inválido **no** debe tumbar ni alterar a los válidos.

**Entrega.** Ejecuta tu cliente sobre `{archivo}` y guarda el resultado en `entrega/salida_T1.json`.

**Herramientas.** {herramientas}

**Terminas** cuando el observador confirme que tu entrega cumple el criterio, o cuando se acabe el tope.
No hay puntos por estilo: importa que el resultado sea correcto.
"""


def enunciado_t2() -> str:
    return f"""# T2 · diagnosticar y reparar un registro inválido · tope {TOPES_MIN['T2']} minutos

**Situación.** El modelo devolvió una respuesta `.mini` con 12 tickets (contrato `contrato_tk.json`) y el
validador la rechaza. Hay **un** registro defectuoso.

**Qué recibes**

- `respuesta.mini`: la respuesta del modelo.
- `contrato_tk.json`: el contrato.
- `correccion_modelo.mini`: lo que respondió el modelo cuando se le pidió corregir solo la línea defectuosa
  (respuesta ya obtenida; no hay que volver a llamar a ningún modelo).
- `../guia_mini.md`: la guía.

**Qué debes hacer**

1. **Diagnosticar**: indica el código de error y el número de línea del registro defectuoso
   (la cabecera es la línea 1).
2. **Reparar**: produce un documento `.mini` corregido que valide contra el contrato. Los otros 11 registros
   deben quedar exactamente como estaban. Puedes corregir a mano o usar la corrección del modelo, pero no
   inventes valores.

**Entrega**

- `entrega/T2_diagnostico.json` con la forma `{{"codigo_error": "E00", "linea": 0}}` (con tus valores).
- `entrega/T2_corregido.mini`.
"""


def enunciado_t3() -> str:
    return f"""# T3 · tratar una respuesta incompleta · tope {TOPES_MIN['T3']} minutos

**Situación.** El modelo llegó al límite de salida y la respuesta `.mini` se cortó. La aplicación no debe
descartar todo: debe quedarse con lo que llegó completo y saber qué falta.

**Qué recibes**

- `respuesta_cortada.mini`: la respuesta truncada (contrato `contrato_tk.json`).
- `../guia_mini.md`: la guía.

**Qué debes hacer**

1. Recupera los registros que llegaron **completos** y válidos.
2. Indica cuántos de los registros declarados en la cabecera **no** pudiste recuperar y cuál es la posición
   del primero (posición = número de orden del registro, empezando en 1).

**Entrega.** `entrega/T3_recuperado.json` con la forma
`{{"recuperados": [ ...registros como objetos... ], "sin_recuperar": 0, "primer_no_recuperado": 0}}`
(con tus valores). Un registro cortado a medias **no** cuenta como recuperado.
"""


def enunciado_t4() -> str:
    filas = "\n".join(f"| {i + 1} | `{n}` | {t} | {d} |" for i, (n, t, d) in enumerate(ESPECIFICACION_T4))
    return f"""# T4 · adaptar un contrato de otro dominio · tope {TOPES_MIN['T4']} minutos

**Situación.** Tienes el contrato de un dominio distinto (catálogo de productos, `contrato_origen_cat.json`)
y necesitas el de **solicitudes de cambio** de TI, con el prefijo `{PREFIJO_T4}`. Adáptalo: los nombres,
el orden y las reglas de los campos son los de esta tabla.

| # | Campo | Tipo | Regla |
|---|---|---|---|
{filas}

La cabecera solo necesita `n`.

**Qué recibes**

- `contrato_origen_cat.json`: el contrato de partida.
- `caso_positivo.mini`: un documento que tu contrato debe **aceptar**.
- `caso_negativo.mini`: un documento que tu contrato debe **rechazar** (tiene un valor que rompe una regla).
- `../guia_mini.md`: la guía (incluye cómo generar un contrato desde un JSON Schema).

**Qué debes hacer.** Produce el contrato de solicitudes de cambio. Compruébalo con los dos documentos.

**Entrega.** `entrega/contrato_cambios.json`.
"""


STUB_CLIENTE = '''"""T1: completa procesar(texto). Puedes usar este archivo o escribir tu cliente en TypeScript."""
import json
import os

RESPUESTA = "{archivo}"
SALIDA = os.path.join("entrega", "salida_T1.json")


def procesar(texto: str) -> dict:
    """Devuelve {{"validos": [...], "rechazados": [{{"posicion": int, "motivo": str}}]}}."""
    raise NotImplementedError


if __name__ == "__main__":
    with open(RESPUESTA, encoding="utf-8") as fh:
        resultado = procesar(fh.read())
    os.makedirs("entrega", exist_ok=True)
    with open(SALIDA, "w", encoding="utf-8") as fh:
        json.dump(resultado, fh, ensure_ascii=False, indent=2)
'''


# ---------------------------------------------------------------------------------------------
# Soluciones de referencia (solo observador): prueban que cada tarea es resoluble y que el
# verificador acepta una entrega correcta. NO se entregan al participante.
# ---------------------------------------------------------------------------------------------
SOL_T1_JSON = '''"""Solución de referencia T1 (condición JSON). Solo observador."""
import json
import sys

from jsonschema import Draft7Validator


def procesar(texto: str, esquema: dict, clave: str) -> dict:
    datos = json.loads(texto)
    validador = Draft7Validator(esquema)
    validos, rechazados = [], []
    for i, registro in enumerate(datos[clave], start=1):
        errores = sorted(validador.iter_errors(registro), key=lambda e: list(e.path))
        if errores:
            rechazados.append({"posicion": i, "motivo": errores[0].message})
        else:
            validos.append(registro)
    return {"validos": validos, "rechazados": rechazados}


if __name__ == "__main__":
    respuesta, esquema, clave = sys.argv[1:4]
    with open(respuesta, encoding="utf-8") as fh:
        texto = fh.read()
    with open(esquema, encoding="utf-8") as fh:
        esq = json.load(fh)
    print(json.dumps(procesar(texto, esq, clave), ensure_ascii=False))
'''

SOL_T1_MINI = '''"""Solución de referencia T1 (condición .mini). Solo observador."""
import json
import sys

from minifmt import Contract, parse


def procesar(texto: str, contrato: Contract) -> dict:
    doc = parse(texto, contrato, strict=False)
    malas = sorted({e.line for e in doc.errors if e.line > 1})
    return {
        "validos": list(doc.records),
        "rechazados": [{"posicion": ln - 1, "motivo": "; ".join(e.code + " " + e.message for e in doc.errors if e.line == ln)}
                       for ln in malas],
    }


if __name__ == "__main__":
    respuesta, contrato = sys.argv[1:3]
    with open(respuesta, encoding="utf-8") as fh:
        texto = fh.read()
    print(json.dumps(procesar(texto, Contract.load(contrato)), ensure_ascii=False))
'''


# ---------------------------------------------------------------------------------------------
# Construcción
# ---------------------------------------------------------------------------------------------
def construir() -> Dict[str, bytes]:
    """Devuelve {ruta relativa a tareas/: contenido} de TODOS los archivos generados."""
    tk, inc, esquema_a = tk_y_b()
    out: Dict[str, bytes] = {}

    def poner(ruta: str, texto: str) -> None:
        out[ruta] = texto.encode("utf-8")

    def copiar(ruta: str, origen: Path) -> bytes:
        datos = origen.read_bytes()
        out[ruta] = datos
        return datos

    contrato_tk_txt = bonito(tk.to_dict())
    contrato_inc_txt = bonito(inc.to_dict())

    # La guía del estudio conserva los bytes del commit congelado.
    guia = copiar("participante/guia_mini.md", AQUI / GUIA_ORIGEN["copia"])
    if sha(guia) != GUIA_ORIGEN["sha256"]:
        raise ValueError("La guía congelada de V6b no coincide con su SHA-256 de origen")

    # --- T1 variante A: archivos reales del repositorio -----------------------------------
    resp_a_json = (EJ / "grabaciones" / "json" / "error.json").read_bytes()
    resp_a_mini = (EJ / "grabaciones" / "mini" / "error.mini").read_bytes()
    ok_a = json.loads((EJ / "grabaciones" / "json" / "ok.json").read_text(encoding="utf-8"))["tickets"]
    registros_a_ok = ok_a                                     # 10 registros correctos (oráculo)
    pos_a = 5                                                  # T-1045 con categoría «facturacion»
    # Cuerpo de las carpetas de T1
    for cond, resp_nombre, resp_bytes, contrato_nombre, contrato_txt in (
        ("json", "respuesta.json", resp_a_json, "ticket.schema.json", None),
        ("mini", "respuesta.mini", resp_a_mini, "contrato_tk.json", contrato_tk_txt),
    ):
        d = f"participante/T1A_{cond}"
        out[f"{d}/{resp_nombre}"] = resp_bytes
        if contrato_txt is None:
            out[f"{d}/{contrato_nombre}"] = (EJ / "ticket.schema.json").read_bytes()
        else:
            poner(f"{d}/{contrato_nombre}", contrato_txt)
        poner(f"{d}/enunciado.md", enunciado_t1("A", cond))
        poner(f"{d}/cliente.py", STUB_CLIENTE.format(archivo=resp_nombre))

    # --- T1 variante B: sintética -----------------------------------------------------------
    registros_b_mal = [dict(r) for r in REGISTROS_B]
    registros_b_mal[POSICION_DEFECTO_B - 1][VALOR_DEFECTO_B[0]] = VALOR_DEFECTO_B[1]
    resp_b_json = compacto({"incidencias": registros_b_mal})
    # .mini con defecto: se serializa la versión correcta y se cambia el valor en la línea del defecto.
    mini_b_ok = texto_mini(inc, REGISTROS_B)
    lineas = mini_b_ok.rstrip("\n").split("\n")
    idx = POSICION_DEFECTO_B + 1 - 1                              # línea (0-based) del registro 7 = índice 7
    original = REGISTROS_B[POSICION_DEFECTO_B - 1]["sistema"]
    assert f"|{original}|" in lineas[idx]
    lineas[idx] = lineas[idx].replace(f"|{original}|", f"|{VALOR_DEFECTO_B[1]}|", 1)
    resp_b_mini = "\n".join(lineas)
    for cond, resp_nombre, resp_txt, contrato_nombre, contrato_txt in (
        ("json", "respuesta.json", resp_b_json, "esquema_inc.json", bonito(ESQUEMA_B)),
        ("mini", "respuesta.mini", resp_b_mini, "contrato_inc.json", contrato_inc_txt),
    ):
        d = f"participante/T1B_{cond}"
        poner(f"{d}/{resp_nombre}", resp_txt)
        poner(f"{d}/{contrato_nombre}", contrato_txt)
        poner(f"{d}/enunciado.md", enunciado_t1("B", cond))
        poner(f"{d}/cliente.py", STUB_CLIENTE.format(archivo=resp_nombre))

    ref_a = {"tarea": "T1", "variante": "A", "contrato": "tk",
             "validos": [r for i, r in enumerate(registros_a_ok, 1) if i != pos_a],
             "rechazados_posiciones": [pos_a], "codigo_error": "E10",
             "nota": "Respuesta = grabaciones/{json,mini}/error.* del repositorio (copia literal)."}
    ref_b = {"tarea": "T1", "variante": "B", "contrato": "inc",
             "validos": [r for i, r in enumerate(REGISTROS_B, 1) if i != POSICION_DEFECTO_B],
             "rechazados_posiciones": [POSICION_DEFECTO_B], "codigo_error": "E10",
             "nota": "Dataset sintético redactado por el equipo; defecto: sistema = 'telefonia'."}
    poner("observador/T1A.referencia.json", bonito(ref_a))
    poner("observador/T1B.referencia.json", bonito(ref_b))

    # --- T2 ----------------------------------------------------------------------------------
    mini_t2_ok = texto_mini(tk, TICKETS_T2)
    lineas = mini_t2_ok.rstrip("\n").split("\n")
    i_def = POSICION_DEFECTO_T2 + 1 - 1
    assert "A\\|B" in lineas[i_def]
    lineas[i_def] = lineas[i_def].replace("A\\|B", "A|B")      # quita el escape: el «|» se vuelve separador
    resp_t2 = "\n".join(lineas) + "\n"
    correccion = "tk|n=1\n" + texto_mini(tk, [TICKETS_T2[POSICION_DEFECTO_T2 - 1]]).split("\n")[1] + "\n"
    poner("participante/T2/respuesta.mini", resp_t2)
    poner("participante/T2/contrato_tk.json", contrato_tk_txt)
    poner("participante/T2/correccion_modelo.mini", correccion)
    poner("participante/T2/enunciado.md", enunciado_t2())
    poner("observador/T2.referencia.json", bonito({
        "tarea": "T2", "contrato": "tk", "linea_defecto": POSICION_DEFECTO_T2 + 1, "codigo_error": "E05",
        "registros_esperados": TICKETS_T2,
        "nota": "Dataset sintético; el defecto es un '|' sin escapar en el resumen del registro 7 (6 campos). "
                "correccion_modelo.mini es una respuesta de reparación redactada por el equipo, no de un modelo real."}))
    poner("observador/T2.corregido_esperado.mini", mini_t2_ok)

    # --- T3 ----------------------------------------------------------------------------------
    completo_t3 = texto_mini(tk, TICKETS_T3)
    lineas = completo_t3.rstrip("\n").split("\n")
    cortada = "\n".join(lineas[: 1 + REGISTROS_COMPLETOS_T3]) + "\n" + lineas[1 + REGISTROS_COMPLETOS_T3][:CORTE_T3_CARACTERES]
    poner("participante/T3/respuesta_cortada.mini", cortada)
    poner("participante/T3/contrato_tk.json", contrato_tk_txt)
    poner("participante/T3/enunciado.md", enunciado_t3())
    poner("observador/T3.referencia.json", bonito({
        "tarea": "T3", "contrato": "tk", "declarados": len(TICKETS_T3),
        "recuperados": TICKETS_T3[:REGISTROS_COMPLETOS_T3],
        "sin_recuperar": len(TICKETS_T3) - REGISTROS_COMPLETOS_T3,
        "primer_no_recuperado": REGISTROS_COMPLETOS_T3 + 1,
        "nota": "Dataset sintético; la respuesta se corta dentro del resumen del registro 12."}))
    poner("observador/T3.completo_esperado.mini", completo_t3)

    # --- T4 ----------------------------------------------------------------------------------
    cat_bytes = copiar("participante/T4/contrato_origen_cat.json", RAIZ / "forks" / "cat" / "contract.json")
    solucion = {
        "prefix": PREFIJO_T4, "version": 1, "name": "Solicitudes de cambio", "description": "", "parent": None,
        "domain": "", "list_separator": ",", "records_key": "cambios",
        "header": {"required": ["n"], "keys": {"n": {"type": "int", "desc": "number of records"},
                                                "v": {"type": "int", "default": 1, "desc": "contract version"}}},
        "core": [
            {"name": "codigo", "type": "str", "unique": True},
            {"name": "titulo", "type": "str"},
            {"name": "tipo", "type": "enum", "values": ["estandar", "normal", "emergencia"]},
            {"name": "riesgo", "type": "enum", "values": ["bajo", "medio", "alto"]},
            {"name": "ventana_min", "type": "int", "min": 15, "max": 480},
            {"name": "sistemas", "type": "list", "item": "str", "min": 1, "max": 5},
            {"name": "puntaje", "type": "float", "optional": True, "min": 0, "max": 10},
        ],
        "extensions": [], "author": "", "license": "MIT", "source": "",
    }
    contrato_t4 = Contract.from_dict(solucion)
    pos_txt = texto_mini(contrato_t4, CASO_POSITIVO_T4)
    neg_txt = texto_mini(contrato_t4, [dict(r, ventana_min=(r["ventana_min"] if r["codigo"] != "CHG-302" else 400))
                                        for r in CASO_NEGATIVO_T4])
    # El negativo se construye válido y se edita el valor: dumps no serializa un valor fuera de rango.
    lin = neg_txt.rstrip("\n").split("\n")
    assert "|400|" in lin[LINEA_DEFECTO_T4 - 1]
    lin[LINEA_DEFECTO_T4 - 1] = lin[LINEA_DEFECTO_T4 - 1].replace("|400|", "|600|", 1)
    neg_txt = "\n".join(lin) + "\n"
    poner("participante/T4/caso_positivo.mini", pos_txt)
    poner("participante/T4/caso_negativo.mini", neg_txt)
    poner("participante/T4/enunciado.md", enunciado_t4())
    poner("observador/T4.contrato_solucion.json", bonito(contrato_t4.to_dict()))
    poner("observador/T4.referencia.json", bonito({
        "tarea": "T4", "prefijo": PREFIJO_T4, "registros_positivo": CASO_POSITIVO_T4,
        "negativo": {"codigo_error": "E13", "linea": LINEA_DEFECTO_T4},
        "campos": [n for n, _, _ in ESPECIFICACION_T4],
        "nota": "Casos sintéticos; contrato de partida = forks/cat/contract.json (copia literal)."}))

    # --- soluciones de referencia ---------------------------------------------------------
    poner("observador/soluciones/T1_json.py", SOL_T1_JSON)
    poner("observador/soluciones/T1_mini.py", SOL_T1_MINI)

    # --- manifiesto con hashes ---------------------------------------------------------------
    manifiesto = {
        "esquema": "mini-format/v6b-tareas-congeladas/1",
        "aviso": "Materiales de tareas para el estudio V6b. No contienen datos de participantes ni resultados.",
        "topes_min": TOPES_MIN,
        "suma_topes_min": sum(TOPES_MIN.values()),
        "sesion_max_min": SESION_MAX_MIN,
        "procedencia_de_datos": {
            "T1 variante A": "archivos reales del repositorio (examples/mesa-de-ayuda), copia literal",
            "T1 variante B, T2, T3, T4 (casos)": "dataset sintético redactado por el equipo (no es salida de un modelo)",
            "contratos tk e inc": "generados con minifmt.from_json_schema",
            "T4 contrato de partida": "forks/cat/contract.json, copia literal",
            "guia_mini.md": "copia literal de la guía pública en el commit fijado en guia_congelada",
        },
        "origen_real": {
            "examples/mesa-de-ayuda/grabaciones/json/error.json": sha(resp_a_json),
            "examples/mesa-de-ayuda/grabaciones/mini/error.mini": sha(resp_a_mini),
            "examples/mesa-de-ayuda/ticket.schema.json": sha((EJ / "ticket.schema.json").read_bytes()),
            "forks/cat/contract.json": sha(cat_bytes),
        },
        "guia_congelada": GUIA_ORIGEN,
        "archivos": {ruta: sha(datos) for ruta, datos in sorted(out.items())},
    }
    poner("respuestas_congeladas.json", bonito(manifiesto))
    return out


def main(argv: List[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--verificar", action="store_true", help="no escribe; falla si el disco difiere de lo generado")
    args = ap.parse_args(argv)
    generado = construir()
    if args.verificar:
        malos = []
        for ruta, datos in generado.items():
            p = AQUI / ruta
            if not p.exists() or p.read_bytes() != datos:
                malos.append(ruta)
        if malos:
            print("difieren del disco:", *malos, sep="\n  ")
            return 1
        print(f"OK: {len(generado)} archivos coinciden")
        return 0
    for ruta, datos in generado.items():
        p = AQUI / ruta
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(datos)
    print(f"escritos {len(generado)} archivos en {AQUI}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
