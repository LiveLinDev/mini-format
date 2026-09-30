"""Importación de respuestas YA generadas (material ``asistido_ia``) al mismo analizador.

Flujo con otro proceso que genera las respuestas (p. ej. una IA en sesión, sin llamar a ninguna API):

1. ``run.py preparar --tareas ... --modelo-declarado M --salida prompts.jsonl`` emite, por celda, el prompt EXACTO del
   arnés (``system``, ``user``) y su ``prompt_id``.
2. Quien genera devuelve un JSONL con las mismas celdas y su ``respuesta_bruta`` (formato en el README del arnés).
3. ``run.py importar respuestas.jsonl --salida DIR`` lee cada respuesta con el lector de su brazo, calcula las mismas
   métricas y deja ``muestras.jsonl`` + ``manifiesto.json`` con procedencia ``asistido_ia``.
4. Para los brazos X+1: ``run.py preparar-reparacion respuestas.jsonl --salida reparaciones.jsonl`` emite las solicitudes
   de reparación que hagan falta; sus respuestas se importan en una segunda pasada con ``condicion`` ``X+1``.

Sin usage de API: ``usage`` y los tokens son ``null`` (nunca inventados); el costo queda vacío (no hay factura de API).
El conteo LOCAL de tokens (``o200k_base``) se guarda aparte como ``tokens_locales_aprox`` y es solo una aproximación.
Las filas inválidas NO se descartan en silencio: quedan en ``importacion.json`` con su motivo.
"""
from __future__ import annotations

import datetime as _dt
import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

from minifmt.tokens import count_tokens

from . import brazos as B
from . import metricas as M
from . import reparar as RP
from . import tareas as T
from .archivos import escribir_texto
from .ejecucion import STOP_TRUNCADO, Almacen, Contexto, clasificar_desenlace
from .plan import VERSION_ESQUEMA_MUESTRA, EstadoEstudio, hashes_diseno, json_estable

CAMPOS = ("celda_id", "dominio", "condicion", "repeticion", "prompt_id", "respuesta_bruta", "modelo_declarado",
          "parametros", "fecha_utc")
PROVEEDOR = "asistido_ia"
EXPERIMENTO_POR_DEFECTO = "v2"


def _sha12(*partes: str) -> str:
    return hashlib.sha256("\x00".join(partes).encode("utf-8")).hexdigest()[:12]


def prompt_id_generacion(tarea_id: str, brazo: str, p: B.Prompt) -> str:
    return f"{tarea_id}/{B.base_de(brazo)}/{_sha12(p.system, p.user, json.dumps(p.response_format, sort_keys=True))}"


def prompt_id_reparacion(tarea_id: str, brazo: str, system: str, user: str) -> str:
    return f"{tarea_id}/{brazo}/{_sha12(system, user)}"


def id_celda(experimento: str, tarea: str, brazo: str, modelo: str, rep: int) -> str:
    return f"{experimento}/{tarea}/{brazo}/{PROVEEDOR}:{modelo}/r{int(rep):03d}"


def leer_filas(ruta: Path) -> List[Dict[str, Any]]:
    """Filas de un JSONL o de todos los ``*.jsonl`` de un directorio (las líneas ilegibles se cuentan como error, no se omiten)."""
    ruta = Path(ruta)
    archivos = sorted(ruta.glob("*.jsonl")) if ruta.is_dir() else [ruta]
    filas: List[Dict[str, Any]] = []
    for a in archivos:
        with open(a, "r", encoding="utf-8") as fh:
            for n, linea in enumerate(fh, 1):
                if not linea.strip():
                    continue
                try:
                    d = json.loads(linea)
                    if not isinstance(d, dict):
                        raise ValueError("no es un objeto")
                except ValueError as e:
                    filas.append({"_error": f"{a.name}:{n}: línea ilegible ({e})"})
                    continue
                d["_origen"] = f"{a.name}:{n}"
                filas.append(d)
    return filas


# --------------------------------------------------------------------------
# Preparar
# --------------------------------------------------------------------------
def preparar_prompts(tareas: List[str], brazos: List[str], repeticiones: int, modelo_declarado: str,
                     experimento: str = EXPERIMENTO_POR_DEFECTO, idioma: str = "es") -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """Filas de prompts para quien va a generar las respuestas; y las celdas que NO se preparan (con motivo)."""
    ctx = Contexto({"tareas": tareas, "idioma": idioma})
    filas, omitidas = [], []
    for tid in tareas:
        t = ctx.tareas[tid]
        for b in brazos:
            if B.es_reparacion(b):
                continue
            for rep in range(1, int(repeticiones) + 1):
                cid = id_celda(experimento, tid, b, modelo_declarado, rep)
                if b == "C":
                    omitidas.append({"celda_id": cid, "motivo": "no_aplicable: el material asistido_ia no tiene restricción "
                                                              "nativa del proveedor (brazo C)"})
                    continue
                p = ctx.prompt(t, b)
                filas.append({"celda_id": cid, "dominio": tid, "condicion": b, "repeticion": rep,
                              "prompt_id": prompt_id_generacion(tid, b, p), "system": p.system, "user": p.user,
                              "modelo_declarado": modelo_declarado, "tipo_tarea": t.tipo, "registros_solicitados": t.n})
    return filas, omitidas


def _prompt_y_tarea(ctx: Contexto, dominio: str, brazo: str) -> Tuple[T.Tarea, B.Prompt]:
    t = ctx.tareas[dominio]
    return t, ctx.prompt(t, brazo)


def preparar_reparaciones(filas: List[Dict[str, Any]], idioma: str = "es", incluir_entrada: bool = False) -> List[Dict[str, Any]]:
    """Solicitudes de reparación para las respuestas importables que tengan algo que reparar (brazos A, B, D; C no aplica)."""
    dominios = sorted({f["dominio"] for f in filas if "dominio" in f})
    ctx = Contexto({"tareas": dominios, "idioma": idioma})
    out = []
    for f in filas:
        b = f.get("condicion")
        if "_error" in f or b not in ("A", "B", "D", "A0") or b == "A0":
            continue
        t, p = _prompt_y_tarea(ctx, f["dominio"], b)
        contexto = t.texto_entrada if (incluir_entrada and t.tipo == "extraccion") else None
        sol = RP.solicitar(B.formato_de(b), f.get("respuesta_bruta") or "", t, p, idioma, contexto, b)
        if not sol.needed:
            continue
        bmas = f"{b}+1"
        cid = id_celda(f.get("experimento") or EXPERIMENTO_POR_DEFECTO, f["dominio"], bmas, f["modelo_declarado"], f["repeticion"])
        out.append({"celda_id": cid, "celda_base": f.get("celda_id"), "dominio": f["dominio"], "condicion": bmas,
                    "repeticion": f["repeticion"], "prompt_id": prompt_id_reparacion(f["dominio"], bmas, sol.system, sol.user),
                    "system": sol.system, "user": sol.user, "modelo_declarado": f["modelo_declarado"]})
    return out


# --------------------------------------------------------------------------
# Importar
# --------------------------------------------------------------------------
@dataclass
class Informe:
    aceptadas: int = 0
    rechazadas: List[Dict[str, Any]] = field(default_factory=list)
    reparaciones_pendientes: List[Dict[str, Any]] = field(default_factory=list)
    no_aplicables: List[Dict[str, Any]] = field(default_factory=list)


def _validar_fila(f: Dict[str, Any], permitir_sin_prompt_id: bool) -> Optional[str]:
    if "_error" in f:
        return f["_error"]
    faltan = [c for c in CAMPOS if c not in f or (f[c] is None and c not in ("parametros", "fecha_utc", "prompt_id"))]
    if permitir_sin_prompt_id:
        faltan = [c for c in faltan if c != "prompt_id"]
    if faltan:
        return "faltan campos: " + ", ".join(faltan)
    if f["condicion"] not in B.BRAZOS:
        return f"condición desconocida: {f['condicion']}"
    if not isinstance(f["respuesta_bruta"], str):
        return "respuesta_bruta debe ser texto"
    try:
        int(f["repeticion"])
    except (TypeError, ValueError):
        return "repeticion debe ser un entero"
    return None


def _token_local(texto: Optional[str]) -> Optional[int]:
    return None if texto is None else count_tokens(texto)


def _intento(fase: str, modelo: str) -> Dict[str, Any]:
    return {"fase": fase, "modelo": modelo, "proveedor": PROVEEDOR, "latencia_s": None, "usage": None, "estado": "ok",
            "error": None, "status": None, "stop_reason": None, "costo_usd": None, "llamada": None}


def _base_muestra(f: Dict[str, Any], t: T.Tarea, sid: str, exp: str, brazo: str) -> Dict[str, Any]:
    par = f.get("parametros") or {}
    return {"id": sid, "esquema_muestra": VERSION_ESQUEMA_MUESTRA, "experimento": exp, "tarea": t.id, "tipo_tarea": t.tipo,
            "prefijo": t.prefijo, "dominio": t.dominio, "brazo": brazo, "proveedor": PROVEEDOR, "modelo": f["modelo_declarado"],
            "repeticion": int(f["repeticion"]), "adaptador": "importado", "procedencia": "asistido_ia", "simulado": False,
            "asistido_ia": True, "semilla": None, "temperatura": par.get("temperatura", par.get("temperature")),
            "max_tokens": par.get("max_tokens"), "fecha": f.get("fecha_utc"), "parametros_declarados": par,
            "celda_id_origen": f.get("celda_id"), "prompt_id": f.get("prompt_id")}


def _latencia_vacia() -> Dict[str, Any]:
    return {"generacion_s": None, "validacion_s": None, "reparacion_s": None, "entrega_s": None, "flujo_s": None,
            "origen_api": "no_medida", "concurrencia": None}


def importar(ruta: Path, salida: Path, *, idioma: str = "es", permitir_sin_prompt_id: bool = False,
             incluir_entrada: bool = False, reparacion: bool = True) -> Informe:
    """Importa las respuestas de ``ruta`` a ``salida``. Idempotente: una celda ya importada no se repite.

    Con ``reparacion`` se crea la muestra X+1 (A+1, B+1, D+1) de cada primaria importada: sin reparación si no hay nada
    que reparar; si hay, solo cuando se ha importado la respuesta de reparación (si no, queda como pendiente).
    """
    filas = leer_filas(ruta)
    inf = Informe()
    dominios = sorted({f["dominio"] for f in filas if isinstance(f.get("dominio"), str)})
    catalogo = set(T.catalogo())
    dominios_ok = [d for d in dominios if d in catalogo]
    ctx = Contexto({"tareas": dominios_ok, "idioma": idioma})
    almacen = Almacen(Path(salida))
    primarias: Dict[str, Dict[str, Any]] = {}
    reparaciones: List[Tuple[Dict[str, Any], str]] = []
    vistos: Dict[str, str] = {}
    for f in filas:
        err = _validar_fila(f, permitir_sin_prompt_id)
        if err is None and f["dominio"] not in catalogo:
            err = f"dominio desconocido: {f['dominio']} (use el id de tarea, p. ej. ext-cls)"
        if err is None and B.base_de(f["condicion"]) == "C":
            inf.no_aplicables.append({"celda_id": f.get("celda_id"), "motivo": "brazo C: sin restricción nativa en material asistido_ia"})
            continue
        if err is not None:
            inf.rechazadas.append({"origen": f.get("_origen"), "celda_id": f.get("celda_id"), "motivo": err})
            continue
        exp = f.get("experimento") or EXPERIMENTO_POR_DEFECTO
        sid = id_celda(exp, f["dominio"], f["condicion"], f["modelo_declarado"], f["repeticion"])
        if sid in vistos:
            inf.rechazadas.append({"origen": f.get("_origen"), "celda_id": f.get("celda_id"),
                                   "motivo": f"celda duplicada (ya vista en {vistos[sid]})"})
            continue
        vistos[sid] = f.get("_origen", "?")
        if B.es_reparacion(f["condicion"]):
            reparaciones.append((f, sid))
        else:
            primarias[sid] = dict(f, _id=sid, _exp=exp)
    # --- primarias
    for sid, f in primarias.items():
        t, p = _prompt_y_tarea(ctx, f["dominio"], f["condicion"])
        esperado = prompt_id_generacion(f["dominio"], f["condicion"], p)
        if f.get("prompt_id") is not None and f["prompt_id"] != esperado:
            inf.rechazadas.append({"origen": f.get("_origen"), "celda_id": f.get("celda_id"),
                                   "motivo": f"prompt_id {f['prompt_id']} no corresponde al prompt vigente ({esperado}): la "
                                             "respuesta se generó para otro prompt"})
            continue
        if sid in almacen.ids:
            continue
        texto = f["respuesta_bruta"]
        lectura = B.leer(f["condicion"], texto, t)
        met = M.evaluar(lectura, t)
        r = {"text": texto, "stop_reason": None, "raw": None}
        desenlace = clasificar_desenlace(PROVEEDOR, r, lectura, False)
        met.update({"tokens_entrada": None, "tokens_salida": None, "latencia_ms": None, "truncado": False, "llamadas": 1,
                    "llamadas_reparacion": 0, "tokens_reparacion_entrada": 0, "tokens_reparacion_salida": 0})
        base = _base_muestra(f, t, sid, f["_exp"], f["condicion"])
        s = {**base, "prompt": {"system": p.system, "user": p.user, "response_format": None},
             "respuesta": {"text": texto, "input_tokens": None, "output_tokens": None, "latency_ms": None, "stop_reason": None,
                           "model": f["modelo_declarado"], "provider": PROVEEDOR, "raw": None},
             "reparacion": None, "lectura": {"avisos": lectura.avisos[:50], "n_declarado": lectura.n_declarado},
             "desenlace": desenlace, "metricas": met,
             "solicitud": {"id": sid, "grupo": sid, "brazo": f["condicion"], "celda": sid, "registros_solicitados": met["solicitados"],
                           "registros_validos_finales": met["validos_finales"], "intentos": [_intento("generacion", f["modelo_declarado"])]},
             "latencia": _latencia_vacia(), "costo_usd": None, "costo_estado": "sin_usage", "costo_incremental_usd": None,
             "costo_nocional": False, "reintentable": False,
             "tokens_locales_aprox": {"entrada": _token_local(p.system + p.user), "salida": _token_local(texto),
                                      "tipo": "aproximacion_local_o200k_base"}}
        almacen.agregar(s)
        inf.aceptadas += 1
    # --- reparaciones X+1 (respuesta de reparación importada) y X+1 sin nada que reparar
    for f, sid in reparaciones:
        b = f["condicion"]
        bb = B.base_de(b)
        exp = f.get("experimento") or EXPERIMENTO_POR_DEFECTO
        base_id = id_celda(exp, f["dominio"], bb, f["modelo_declarado"], f["repeticion"])
        if sid in almacen.ids:
            continue
        if base_id not in almacen.bases:
            inf.rechazadas.append({"origen": f.get("_origen"), "celda_id": f.get("celda_id"),
                                   "motivo": f"la celda base {base_id} no está importada"})
            continue
        t, p = _prompt_y_tarea(ctx, f["dominio"], bb)
        gen = almacen.bases[base_id]
        texto0 = gen["text"] or ""
        contexto = t.texto_entrada if (incluir_entrada and t.tipo == "extraccion") else None
        formato = B.formato_de(b)
        sol = RP.solicitar(formato, texto0, t, p, idioma, contexto, bb)
        if not sol.needed:
            inf.rechazadas.append({"origen": f.get("_origen"), "celda_id": f.get("celda_id"),
                                   "motivo": "la respuesta base no necesita reparación; se genera la muestra X+1 sin ella"})
            continue
        esperado = prompt_id_reparacion(f["dominio"], b, sol.system, sol.user)
        if f.get("prompt_id") is not None and f["prompt_id"] != esperado:
            inf.rechazadas.append({"origen": f.get("_origen"), "celda_id": f.get("celda_id"),
                                   "motivo": f"prompt_id {f['prompt_id']} no corresponde a la solicitud de reparación vigente ({esperado})"})
            continue
        rr = {"text": f["respuesta_bruta"]}
        res = RP.fusionar(sol, texto0, rr, t, {"text": f["respuesta_bruta"], "model": f["modelo_declarado"]}, 0)
        _escribir_muestra_reparacion(almacen, f, sid, exp, t, b, formato, base_id, gen, sol, res, texto0, inf)
    # X+1 sin reparación necesaria: se crean automáticamente para cada primaria importada cuyo X+1 no se haya importado
    for bid, gen in list(almacen.bases.items()):
        partes = bid.split("/")
        exp, dominio, brazo = partes[0], partes[1], partes[2]
        bmas = f"{brazo}+1"
        modelo = partes[3].split(":", 1)[1]
        rep = int(partes[4][1:])
        sid = id_celda(exp, dominio, bmas, modelo, rep)
        if bmas not in B.BASE_REPARACION or sid in almacen.ids or brazo not in ("A", "B", "D"):
            continue
        if not reparacion:
            continue
        t, p = _prompt_y_tarea(ctx, dominio, brazo)
        sol = RP.solicitar(B.formato_de(bmas), gen["text"] or "", t, p, idioma,
                           t.texto_entrada if (incluir_entrada and t.tipo == "extraccion") else None, brazo)
        if sol.needed:
            inf.reparaciones_pendientes.append({"celda_id": sid, "motivo": "necesita reparación: falta importar su respuesta de reparación"})
            continue
        f0 = {"modelo_declarado": modelo, "repeticion": rep, "parametros": {}, "fecha_utc": None, "celda_id": sid, "prompt_id": None}
        _escribir_muestra_reparacion(almacen, f0, sid, exp, t, bmas, B.formato_de(bmas), bid, gen, sol, None, gen["text"] or "", inf)
    return inf


def _escribir_muestra_reparacion(almacen: Almacen, f: Dict[str, Any], sid: str, exp: str, t: T.Tarea, brazo: str, formato: str,
                                 base_id: str, gen: Dict[str, Any], sol: RP.Solicitud, res: Optional[RP.Resultado],
                                 texto0: str, inf: Informe) -> None:
    texto = res.texto if res is not None else texto0
    rondas = [res.ronda] if res is not None else []
    lectura = B.leer(brazo, texto, t)
    if res is not None and formato == "json" and res.sin_resolver_json:
        lectura.avisos = list(lectura.avisos) + [f"objeto {p_} sin resolver" for p_ in res.sin_resolver_json]
    met = M.evaluar(lectura, t)
    auditoria = RP.auditar(sol, texto0, texto, t, res.rechazos_identidad if res else 0,
                           lectura.registros if lectura.parseable else []) if res is not None else None
    met.update({"tokens_entrada": None, "tokens_salida": None, "latencia_ms": None, "truncado": False,
                "llamadas": 1 + len(rondas), "llamadas_reparacion": len(rondas), "tokens_reparacion_entrada": 0,
                "tokens_reparacion_salida": 0})
    intentos = [dict(i, compartido_con=base_id) for i in gen["intentos"]]
    if res is not None:
        intentos.append(_intento("reparacion", f["modelo_declarado"]))
    estado = RP.estado_reparacion(rondas, False)
    base = _base_muestra(f, t, sid, exp, brazo)
    s = {**base, "prompt": None, "generacion_de": base_id,
         "respuesta": {"text": gen["text"], "input_tokens": None, "output_tokens": None, "latency_ms": None, "stop_reason": None,
                       "model": f["modelo_declarado"]},
         "reparacion": {"rondas": rondas, "documento_final": texto, "formato": formato, "estado": estado, "auditoria": auditoria},
         "reparacion_estado": estado, "lectura": {"avisos": lectura.avisos[:50], "n_declarado": lectura.n_declarado},
         "desenlace": gen.get("desenlace"), "metricas": met,
         "solicitud": {"id": sid, "grupo": base_id, "brazo": brazo, "celda": sid, "registros_solicitados": met["solicitados"],
                       "registros_validos_finales": met["validos_finales"], "intentos": intentos},
         "latencia": _latencia_vacia(), "costo_usd": None, "costo_estado": "sin_usage", "costo_incremental_usd": None,
         "costo_nocional": False, "reintentable": False}
    almacen.agregar(s)
    inf.aceptadas += 1


# --------------------------------------------------------------------------
# Manifiesto de la importación
# --------------------------------------------------------------------------
def escribir_resultados_importacion(salida: Path, origen: Path, inf: Informe, *, idioma: str, raiz: Path) -> Dict[str, Any]:
    """``manifiesto.json`` (procedencia asistido_ia), ``estado_estudio.json`` e ``importacion.json``."""
    salida = Path(salida)
    almacen = Almacen(salida)
    muestras = almacen.leer()
    tareas = sorted({m["tarea"] for m in muestras})
    modelos = sorted({m["modelo"] for m in muestras})
    brazos = sorted({m["brazo"] for m in muestras}, key=lambda b: B.ORDEN_BRAZOS.index(b) if b in B.ORDEN_BRAZOS else 99)
    cfg = {"nombre": salida.name, "semilla": None, "idioma": idioma, "tareas": tareas, "brazos": brazos,
           "modelos": [{"proveedor": PROVEEDOR, "modelo": m} for m in modelos], "experimentos": {"v2": {"activo": True}},
           "importado_de": Path(origen).name}
    ctx = Contexto({"tareas": tareas, "idioma": idioma})
    from .ejecucion import Unidad
    unidades = [Unidad(m["experimento"], m["tarea"], m["brazo"], PROVEEDOR, m["modelo"], m["repeticion"], m.get("max_tokens") or 0)
                for m in muestras]
    hashes = hashes_diseno(cfg, ctx, unidades, [], None, raiz)
    manifiesto = {"nombre": salida.name, "adaptador": "importado", "procedencia": "asistido_ia", "simulado": False,
                  "advertencia": ("MATERIAL ASISTIDO POR IA: respuestas generadas por una IA en sesión, sin llamada a ninguna "
                                  "API, sin usage ni factura; no es una corrida de API"),
                  "config": cfg, "hashes": hashes, "origen": {"archivo": Path(origen).name,
                                                               "sha256": hashlib.sha256(Path(origen).read_bytes()).hexdigest()
                                                               if Path(origen).is_file() else None},
                  "gasto_usd": 0, "muestras": len(muestras)}
    escribir_texto(salida / "manifiesto.json", json.dumps(manifiesto, ensure_ascii=False, indent=2))
    ahora = _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds")
    EstadoEstudio(salida).escribir(estado="completo" if not inf.reparaciones_pendientes else "parcial", motivo="importación",
                                   fecha_inicio=ahora, fecha=ahora,
                                   contadores={"hecha": len(muestras), "pendiente": len(inf.reparaciones_pendientes), "bloqueado": 0,
                                               "no_aplicable": len(inf.no_aplicables), "error_tecnico": 0},
                                   gasto={"gastado_usd": "0", "incierto_usd": "0", "llamadas": 0}, orden_semilla=0,
                                   modo="importado", interrupcion=None,
                                   faltantes=[{"estado": "pendiente", "id": x["celda_id"], "motivo": x["motivo"]} for x in inf.reparaciones_pendientes]
                                   + [{"estado": "no_aplicable", "id": x.get("celda_id"), "motivo": x["motivo"]} for x in inf.no_aplicables])
    escribir_texto(salida / "importacion.json", json.dumps(
        {"aceptadas": inf.aceptadas, "rechazadas": inf.rechazadas, "reparaciones_pendientes": inf.reparaciones_pendientes,
         "no_aplicables": inf.no_aplicables}, ensure_ascii=False, indent=2))
    return manifiesto
