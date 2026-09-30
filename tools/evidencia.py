#!/usr/bin/env python3
"""Maquinaria de evidencia: validar corridas, comprobar el registro de estudios, regenerar y verificar
los derivados. Solo biblioteca estándar.

Uso (desde la raíz del repositorio):
    python tools/evidencia.py validar        manifiestos de evidencia/corridas/*/manifiesto.json
    python tools/evidencia.py estudios       evidencia/estudios.json: los DOS EJES y la honestidad
    python tools/evidencia.py regenerar      escribe evidencia/derivados/*.json y *.csv (determinista)
    python tools/evidencia.py verificar      validar + estudios + derivados al día (falla si difieren)

Las cifras que se publican (sitio, informes, calculadora) salen de evidencia/derivados/, que este
programa genera SOLO desde los manifiestos de las corridas, el registro de estudios y las tarifas.
Como ``verificar`` regenera en memoria y compara byte a byte con lo versionado, ninguna cifra se
puede editar a mano sin que falle.

Reglas de honestidad que comprueba ``estudios``:
  * ``ejecutado`` exige, para TODOS los componentes requeridos, corridas ejecutadas de procedencia
    real (reproducido_local, api_real o participantes): lo simulado, asistido_ia o reportado_historico
    no acredita ejecución. Si falta algún componente el estudio es ``parcial`` o ``pendiente``.
  * ``cumple`` / ``no_cumple`` solo con estado ``ejecutado`` y se RECALCULAN desde los predicados
    del criterio sobre el ``resumen`` de esas corridas; un resultado declarado distinto es un error.
    El criterio debe estar fijado (``fijado_utc``) ANTES de la primera corrida que lo evalúa.
  * Un dato que falta es ``null`` (no evaluable), nunca cero.
"""
from __future__ import annotations

import argparse
import csv
import glob as _glob
import io
import json
import re
import sys
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent))
import evidencia_lib as ev  # noqa: E402

ESQUEMA_ESTUDIOS = "mini-format/estudios/1"
ESQUEMA_DERIVADO = "mini-format/estudios-derivado/1"
ESQUEMA_TARIFAS_DERIVADO = "mini-format/tarifas-derivado/1"
ESTUDIOS_REQUERIDOS = ("V1", "V2", "V3a", "V3b", "V4", "V5", "V6a", "V6b", "V7", "V8")
TIPO_POR_ESTUDIO = {"V1": "controlado", "V2": "controlado", "V3a": "controlado", "V3b": "controlado", "V4": "controlado",
                    "V5": "controlado", "V6a": "naturalista", "V6b": "controlado", "V7": "exploratorio", "V8": "exploratorio"}
ESTUDIOS_DE_APOYO = ("OPT", "CF")
PROCEDENCIAS_REALES = ("reproducido_local", "api_real", "participantes")
PROCEDENCIAS_NO_ADMISIBLES = ("reportado_historico", "simulado", "asistido_ia")
AGREGACIONES = ("min", "max", "suma", "unico", "conteo_distintos", "conteo_distintos_familia")
OPERADORES = (">=", "<=", ">", "<", "==")
VERIFICACIONES = ("json", "suma_longitudes")
CLAVES_ESTUDIO = {"id", "nombre", "objetivo", "clasificacion", "pregunta", "procedimiento", "muestra", "comparadores", "criterio",
                  "meta_documental", "componentes", "cifras", "limitaciones", "reproduccion", "hu_relacionadas",
                  "estado_ejecucion", "resultado", "bloqueo", "antecedentes"}
_FECHA = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")
_ID = re.compile(r"^[a-z][a-z0-9_]{1,60}$")
_HU = re.compile(r"^HU\d{3}$")
_SECRETOS = [
    (re.compile(r"(?<![A-Za-z0-9])sk-[A-Za-z0-9_-]{20,}"), "clave tipo sk-"),
    (re.compile(r"AKIA[0-9A-Z]{16}"), "clave de acceso de AWS"),
    (re.compile(r"AIza[0-9A-Za-z_-]{35}"), "clave de API de Google"),
    (re.compile(r"gsk_[A-Za-z0-9]{20,}"), "clave de Groq"),
    (re.compile(r"xox[bpas]-[A-Za-z0-9-]{10,}"), "token de Slack"),
    (re.compile(r"(?i)bearer\s+[A-Za-z0-9._~+/=-]{24,}"), "cabecera Authorization"),
    (re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"), "clave privada"),
    (re.compile(r"(?i)\"?(?:api[_-]?key|secret|password|token)\"?\s*[:=]\s*\"[A-Za-z0-9._~+/=-]{20,}\""), "campo de credencial con valor"),
]


# ------------------------------------------------------------------ utilidades
def _dec(x: Any) -> Optional[Decimal]:
    """Número JSON -> Decimal exacto (los float pasan por su repr más corto); otro tipo -> None."""
    if isinstance(x, bool) or x is None:
        return None
    if isinstance(x, int):
        return Decimal(x)
    if isinstance(x, float):
        return Decimal(repr(x))
    if isinstance(x, Decimal):
        return x
    return None


def _num_json(d: Optional[Decimal]) -> Any:
    if d is None:
        return None
    if d == d.to_integral_value():
        return int(d)
    return float(d)


def _ruta(obj: Any, ruta: str) -> Any:
    for parte in ruta.split("."):
        if not isinstance(obj, dict) or parte not in obj:
            return None
        obj = obj[parte]
    return obj


def _csv(filas: List[List[Any]]) -> str:
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    for f in filas:
        w.writerow(["" if v is None else ("true" if v is True else "false" if v is False else v) for v in f])
    return buf.getvalue()


def _leer(p: Path) -> Any:
    with open(p, encoding="utf-8") as fh:
        return json.load(fh)


def _familia_so(so: Any) -> Optional[str]:
    if not isinstance(so, str) or not so.strip():
        return None
    return so.split()[0].lower()


# ------------------------------------------------------------------ corridas
class Corrida:
    def __init__(self, directorio: Path, m: Any, errores: List[str]):
        self.dir = directorio
        self.m = m if isinstance(m, dict) else {}
        self.errores = errores

    @property
    def run_id(self) -> str:
        return str(self.m.get("run_id") or self.dir.name)

    @property
    def valida(self) -> bool:
        return not self.errores


def _texto_a_revisar(p: Path) -> Optional[str]:
    if p.suffix.lower() not in (".json", ".jsonl", ".csv", ".txt", ".md", ".log", ".yaml", ".yml", ".tsv"):
        return None
    try:
        if p.stat().st_size > 8 * 1024 * 1024:
            return None
        return p.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None


def cargar_corridas(raiz: Path) -> List[Corrida]:
    """Carga y valida cada evidencia/corridas/<run_id>/manifiesto.json."""
    base = Path(raiz) / "evidencia" / "corridas"
    out: List[Corrida] = []
    if not base.exists():
        return out
    for d in sorted(p for p in base.iterdir() if p.is_dir()):
        mf = d / "manifiesto.json"
        if not mf.exists():
            out.append(Corrida(d, {}, [f"{d.name}: falta manifiesto.json"]))
            continue
        try:
            m = _leer(mf)
        except ValueError as e:
            out.append(Corrida(d, {}, [f"{d.name}: manifiesto.json no es JSON válido ({e})"]))
            continue
        errores: List[str] = []
        if isinstance(m, dict) and m.get("run_id") != d.name:
            errores.append(f"{d.name}: el run_id ({m.get('run_id')!r}) debe coincidir con el nombre de la carpeta")
        errores += [f"{d.name}: {x}" for x in ev.validar_corrida(m, d)]
        if isinstance(m, dict):
            if m.get("estudio") not in ev.ESTUDIOS_CONOCIDOS:
                errores.append(f"{d.name}: estudio {m.get('estudio')!r} desconocido")
            for r in m.get("resultados") or []:
                ruta = str((r or {}).get("ruta", "")) if isinstance(r, dict) else ""
                if ruta.replace("\\", "/").startswith("evidencia/restringida"):
                    errores.append(f"{d.name}: un resultado publicable no puede vivir en evidencia/restringida ({ruta})")
            # secretos en el manifiesto y en los resultados de texto
            revisar = [(mf, mf.read_text(encoding="utf-8", errors="replace"))]
            for r in m.get("resultados") or []:
                if isinstance(r, dict) and r.get("ruta"):
                    for cand in (Path(raiz) / r["ruta"], d / Path(r["ruta"]).name):
                        if cand.exists():
                            t = _texto_a_revisar(cand)
                            if t is not None:
                                revisar.append((cand, t))
                            break
            for ruta_arch, t in revisar:
                for rx, que in _SECRETOS:
                    if rx.search(t):
                        errores.append(f"{d.name}: posible secreto ({que}) en {ruta_arch.name}")
        out.append(Corrida(d, m, errores))
    return out


def validar(raiz: Path) -> Tuple[List[str], List[str], List[Corrida]]:
    corridas = cargar_corridas(raiz)
    errores: List[str] = []
    avisos: List[str] = []
    for c in corridas:
        errores += c.errores
        if c.m.get("estudio") == "V3":
            avisos.append(f"{c.run_id}: estudio 'V3' genérico; el registro distingue V3a y V3b y no la contará")
    return errores, avisos, corridas


# ------------------------------------------------------------- registro de estudios
def cargar_estudios(raiz: Path) -> Dict[str, Any]:
    return _leer(Path(raiz) / "evidencia" / "estudios.json")


def _err_estudio(e: Dict[str, Any]) -> List[str]:
    """Estructura de UN estudio (lo que describe estudio.schema.json más las reglas de coherencia)."""
    id_ = e.get("id")
    p = f"{id_}: "
    r: List[str] = []
    desconocidas = set(e) - CLAVES_ESTUDIO
    if desconocidas:
        r.append(p + f"claves desconocidas {sorted(desconocidas)}")
    for k in ("nombre", "pregunta", "procedimiento", "meta_documental"):
        if not isinstance(e.get(k), str) or not e[k].strip():
            r.append(p + f"falta {k}")
    if e.get("objetivo") != "OE4":
        r.append(p + "objetivo debe ser OE4")
    cl = e.get("clasificacion")
    if not isinstance(cl, dict) or cl.get("tipo") not in ("controlado", "naturalista", "exploratorio"):
        r.append(p + "clasificacion.tipo debe ser controlado, naturalista o exploratorio")
    elif TIPO_POR_ESTUDIO.get(id_) and cl["tipo"] != TIPO_POR_ESTUDIO[id_]:
        r.append(p + f"clasificacion.tipo debe ser {TIPO_POR_ESTUDIO[id_]} (Plan v3)")
    if isinstance(cl, dict) and not cl.get("formativo_sumativo"):
        r.append(p + "falta clasificacion.formativo_sumativo (es otra dimensión)")
    mu = e.get("muestra")
    if not isinstance(mu, dict) or not mu.get("unidad") or not mu.get("descripcion"):
        r.append(p + "muestra necesita unidad y descripcion")
    if not isinstance(e.get("comparadores"), list):
        r.append(p + "comparadores debe ser una lista")
    if not isinstance(e.get("limitaciones"), list) or not e.get("limitaciones"):
        r.append(p + "limitaciones debe ser una lista no vacía")
    rep = e.get("reproduccion")
    if not isinstance(rep, dict) or "comando" not in rep or not rep.get("nota"):
        r.append(p + "reproduccion necesita comando (o null) y nota")
    hu = e.get("hu_relacionadas")
    if not isinstance(hu, list) or not hu or not all(isinstance(x, str) and _HU.match(x) for x in hu):
        r.append(p + "hu_relacionadas debe ser una lista de HUnnn")
    if e.get("estado_ejecucion") not in ev.ESTADOS_EJECUCION:
        r.append(p + f"estado_ejecucion debe ser uno de {ev.ESTADOS_EJECUCION}")
    if e.get("resultado") not in ev.RESULTADOS:
        r.append(p + f"resultado debe ser uno de {ev.RESULTADOS}")
    bl = e.get("bloqueo")
    if bl is not None and (not isinstance(bl, dict) or not bl.get("causa")):
        r.append(p + "bloqueo debe ser null o un objeto con causa")
    # criterio
    cr = e.get("criterio")
    if isinstance(cl, dict) and cl.get("tipo") == "exploratorio" and cr is not None:
        r.append(p + "un estudio exploratorio no tiene criterio de cumplimiento")
    if cr is not None:
        if not isinstance(cr, dict):
            r.append(p + "criterio debe ser null o un objeto")
        else:
            for k in ("texto", "interpretacion"):
                if not isinstance(cr.get(k), str) or not cr[k].strip():
                    r.append(p + f"criterio.{k} es obligatorio (la interpretación se fija ANTES del análisis)")
            if not isinstance(cr.get("fijado_utc"), str) or not _FECHA.match(cr["fijado_utc"]):
                r.append(p + "criterio.fijado_utc debe ser AAAA-MM-DDThh:mm:ssZ")
            if not isinstance(cr.get("aprobado_por_equipo"), bool):
                r.append(p + "criterio.aprobado_por_equipo debe ser booleano")
            ps = cr.get("predicados")
            if not isinstance(ps, list) or not ps:
                r.append(p + "criterio.predicados debe ser una lista no vacía")
            else:
                vistos = set()
                for q in ps:
                    q = q if isinstance(q, dict) else {}
                    pid = q.get("id")
                    if not isinstance(pid, str) or not _ID.match(pid) or pid in vistos:
                        r.append(p + f"predicado con id inválido o repetido ({pid!r})")
                    vistos.add(pid)
                    if q.get("fuente") not in ("resumen", "corridas"):
                        r.append(p + f"predicado {pid}: fuente debe ser resumen o corridas")
                    if not isinstance(q.get("ruta"), str) or not q.get("ruta"):
                        r.append(p + f"predicado {pid}: falta ruta")
                    if q.get("agregacion") not in AGREGACIONES:
                        r.append(p + f"predicado {pid}: agregacion debe ser una de {AGREGACIONES}")
                    if q.get("op") not in OPERADORES:
                        r.append(p + f"predicado {pid}: op debe ser una de {OPERADORES}")
                    if _dec(q.get("valor")) is None:
                        r.append(p + f"predicado {pid}: valor debe ser un número")
                    if q.get("fuente") == "resumen" and q.get("agregacion") in ("conteo_distintos", "conteo_distintos_familia"):
                        pass  # un conteo sobre el resumen es legítimo si el resumen trae una lista de cadenas
    # componentes
    comps = e.get("componentes")
    if not isinstance(comps, list) or not comps:
        r.append(p + "componentes debe ser una lista no vacía (qué hace falta para 'ejecutado')")
    else:
        vistos = set()
        for c in comps:
            c = c if isinstance(c, dict) else {}
            cid = c.get("id")
            if not isinstance(cid, str) or not _ID.match(cid) or cid in vistos:
                r.append(p + f"componente con id inválido o repetido ({cid!r})")
            vistos.add(cid)
            if not c.get("descripcion"):
                r.append(p + f"componente {cid}: falta descripcion")
            pa = c.get("procedencias_admitidas")
            if not isinstance(pa, list) or not pa or any(x not in PROCEDENCIAS_REALES for x in pa):
                r.append(p + f"componente {cid}: procedencias_admitidas debe ser un subconjunto no vacío de {PROCEDENCIAS_REALES}")
            if not isinstance(c.get("minimo_corridas"), int) or isinstance(c.get("minimo_corridas"), bool) or c["minimo_corridas"] < 1:
                r.append(p + f"componente {cid}: minimo_corridas debe ser un entero >= 1")
    for ci in e.get("cifras") or []:
        if not isinstance(ci, dict) or not all(ci.get(k) for k in ("id", "etiqueta", "ruta", "agregacion", "unidad")) or ci.get("agregacion") not in AGREGACIONES:
            r.append(p + f"cifra mal formada: {ci!r}")
    for a in e.get("antecedentes") or []:
        a = a if isinstance(a, dict) else {}
        if not a.get("id") or not a.get("descripcion") or not a.get("fuente"):
            r.append(p + f"antecedente sin id, descripcion o fuente: {a.get('id')!r}")
        if a.get("procedencia") not in PROCEDENCIAS_NO_ADMISIBLES:
            r.append(p + f"antecedente {a.get('id')}: procedencia debe ser una de {PROCEDENCIAS_NO_ADMISIBLES} (lo reproducido va en corridas)")
        for c in a.get("cifras") or []:
            c = c if isinstance(c, dict) else {}
            if not c.get("etiqueta") or _dec(c.get("valor")) is None or not c.get("unidad"):
                r.append(p + f"antecedente {a.get('id')}: cifra sin etiqueta, valor numérico o unidad")
            v = c.get("verificacion")
            if v is not None and (not isinstance(v, dict) or v.get("tipo") not in VERIFICACIONES or not isinstance(v.get("estricta"), bool)):
                r.append(p + f"antecedente {a.get('id')}: verificacion inválida")
    return r


def validar_estructura_estudios(doc: Dict[str, Any]) -> List[str]:
    errores: List[str] = []
    if doc.get("esquema") != ESQUEMA_ESTUDIOS:
        errores.append(f"esquema debe ser {ESQUEMA_ESTUDIOS!r}")
    if doc.get("objetivo") != "OE4":
        errores.append("objetivo debe ser OE4")
    estudios = doc.get("estudios")
    if not isinstance(estudios, list):
        return errores + ["estudios debe ser una lista"]
    ids = [e.get("id") for e in estudios if isinstance(e, dict)]
    if len(ids) != len(set(ids)):
        errores.append("hay ids de estudio repetidos")
    for req in ESTUDIOS_REQUERIDOS:
        if req not in ids:
            errores.append(f"falta el estudio {req}")
    for e in estudios:
        if not isinstance(e, dict):
            errores.append("un estudio no es un objeto")
            continue
        if e.get("id") not in ESTUDIOS_REQUERIDOS:
            errores.append(f"{e.get('id')}: estudio desconocido")
        errores += _err_estudio(e)
    return errores


# ---------------------------------------------------------------- evaluación
def _agregar(valores: List[Any], agregacion: str) -> Any:
    """Agrega los valores observados. Sin datos (o con un tipo inesperado) => None: no evaluable."""
    if agregacion in ("conteo_distintos", "conteo_distintos_familia"):
        if agregacion == "conteo_distintos_familia":
            valores = [_familia_so(v) for v in valores]
        distintos = {v for v in valores if isinstance(v, str) and v}
        return Decimal(len(distintos)) if distintos else None
    nums = [_dec(v) for v in valores]
    if not nums or any(n is None for n in nums):
        return None
    if agregacion == "min":
        return min(nums)
    if agregacion == "max":
        return max(nums)
    if agregacion == "suma":
        return sum(nums, Decimal(0))
    if agregacion == "unico":
        return nums[0] if len(nums) == 1 else None
    return None


def _comparar(obs: Optional[Decimal], op: str, umbral: Decimal) -> Optional[bool]:
    if obs is None:
        return None
    return {">=": obs >= umbral, "<=": obs <= umbral, ">": obs > umbral, "<": obs < umbral, "==": obs == umbral}[op]


def _observado(c: Dict[str, Any], corridas_que_cuentan: List[Corrida]) -> Optional[Decimal]:
    if c["fuente"] == "resumen":
        valores = [_ruta(k.m.get("resumen"), c["ruta"]) for k in corridas_que_cuentan]
    else:
        valores = [_ruta(k.m, c["ruta"]) for k in corridas_que_cuentan]
    valores = [v for v in valores if v is not None]
    return _agregar(valores, c["agregacion"])


def _cuenta_para_componente(k: Corrida, comp: Dict[str, Any], n_comps: int) -> Tuple[bool, Optional[str]]:
    m = k.m
    if m.get("estado_ejecucion") != "ejecutado":
        return False, f"estado_ejecucion = {m.get('estado_ejecucion')}"
    if m.get("procedencia") not in comp["procedencias_admitidas"]:
        return False, f"procedencia {m.get('procedencia')} no admitida para el componente {comp['id']}"
    declarado = _ruta(m.get("parametros"), "componente")
    if declarado is None:
        if n_comps == 1:
            return True, None
        return False, "no declara parametros.componente y el estudio tiene varios componentes"
    if declarado != comp["id"]:
        return False, "es de otro componente"
    return True, None


def evaluar_estudio(e: Dict[str, Any], todas: List[Corrida]) -> Dict[str, Any]:
    """Estado y resultado CALCULADOS desde las corridas. No lee lo declarado."""
    comps = e["componentes"]
    propias = [k for k in todas if k.m.get("estudio") == e["id"]]
    cuenta: Dict[str, Tuple[bool, str]] = {}
    por_comp: Dict[str, List[Corrida]] = {c["id"]: [] for c in comps}
    for k in propias:
        if not k.valida:
            cuenta[k.run_id] = (False, "manifiesto inválido")
            continue
        if k.m.get("procedencia") in PROCEDENCIAS_NO_ADMISIBLES:
            cuenta[k.run_id] = (False, f"procedencia {k.m.get('procedencia')}: no acredita ejecución")
            continue
        declarado = _ruta(k.m.get("parametros"), "componente")
        if declarado is not None and declarado not in por_comp:
            cuenta[k.run_id] = (False, f"componente desconocido: {declarado}")
            continue
        motivos = []
        ok_alguno = False
        for c in comps:
            ok, why = _cuenta_para_componente(k, c, len(comps))
            if ok:
                por_comp[c["id"]].append(k)
                ok_alguno = True
            elif declarado is None or declarado == c["id"]:
                motivos.append(why)
        cuenta[k.run_id] = (True, "") if ok_alguno else (False, "; ".join(m for m in motivos if m) or "no corresponde a ningún componente")
    componentes = []
    for c in comps:
        ks = por_comp[c["id"]]
        componentes.append({"id": c["id"], "descripcion": c["descripcion"], "minimo_corridas": c["minimo_corridas"],
                            "corridas_que_cuentan": [k.run_id for k in ks], "satisfecho": len(ks) >= c["minimo_corridas"]})
    n_sat = sum(1 for c in componentes if c["satisfecho"])
    hay_parcial_real = any(k.valida and k.m.get("procedencia") in PROCEDENCIAS_REALES and k.m.get("estado_ejecucion") == "parcial" for k in propias)
    hay_que_cuenta = any(ks for ks in por_comp.values())
    que_cuentan = []
    vistos = set()
    for ks in por_comp.values():
        for k in ks:
            if k.run_id not in vistos:
                vistos.add(k.run_id)
                que_cuentan.append(k)
    que_cuentan.sort(key=lambda k: (k.m.get("fecha_utc", ""), k.run_id))
    if n_sat == len(componentes):
        estado = "ejecutado"
    elif n_sat > 0 or hay_que_cuenta or hay_parcial_real:
        estado = "parcial"
    else:
        estado = "pendiente"
    cr = e.get("criterio")
    predicados = []
    if cr:
        for q in cr["predicados"]:
            obs = _observado(q, que_cuentan)
            predicados.append({"id": q["id"], "descripcion": q["descripcion"], "valor_observado": _num_json(obs), "op": q["op"],
                               "umbral": q["valor"], "cumple": _comparar(obs, q["op"], _dec(q["valor"]))})
    if estado != "ejecutado":
        resultado, motivo = "no_evaluable", f"el estudio no está ejecutado (estado calculado: {estado})"
    elif not cr:
        resultado, motivo = "no_evaluable", "el estudio no tiene criterio de cumplimiento"
    elif que_cuentan and cr["fijado_utc"] > min(k.m.get("fecha_utc", "9999") for k in que_cuentan):
        resultado, motivo = "no_evaluable", "el criterio se fijó DESPUÉS de la primera corrida que lo evalúa"
    elif any(p["cumple"] is None for p in predicados):
        falta = [p["id"] for p in predicados if p["cumple"] is None]
        resultado, motivo = "no_evaluable", f"faltan datos para evaluar: {', '.join(falta)}"
    elif all(p["cumple"] for p in predicados):
        resultado, motivo = "cumple", "todos los predicados se cumplen sobre los datos de las corridas"
    else:
        resultado, motivo = "no_cumple", "incumple: " + ", ".join(p["id"] for p in predicados if not p["cumple"])
    # cifras principales (declaradas en el registro) con su procedencia
    cifras = []
    for ci in e.get("cifras") or []:
        valores = [(k, _ruta(k.m.get("resumen"), ci["ruta"])) for k in que_cuentan]
        valores = [(k, v) for k, v in valores if v is not None]
        obs = _agregar([v for _, v in valores], ci["agregacion"])
        cifras.append({"id": ci["id"], "etiqueta": ci["etiqueta"], "unidad": ci["unidad"], "valor": _num_json(obs),
                       "procedencias": sorted({k.m.get("procedencia") for k, _ in valores}), "run_ids": [k.run_id for k, _ in valores]})
    return {"estado_calculado": estado, "resultado_calculado": resultado, "motivo_resultado": motivo, "componentes": componentes,
            "predicados": predicados, "cifras_principales": cifras, "propias": propias, "que_cuentan": que_cuentan, "cuenta": cuenta}


def _verificar_cifra(raiz: Path, cifra: Dict[str, Any]) -> Tuple[str, Any]:
    """Recalcula desde el repositorio una cifra histórica. -> (estado, valor_actual)."""
    v = cifra.get("verificacion")
    if not v:
        return "no_verificable", None
    try:
        if v["tipo"] == "json":
            obs = _dec(_ruta(_leer(Path(raiz) / v["archivo"]), v["ruta"]))
        else:
            archivos = sorted(_glob.glob(str(Path(raiz) / v["glob"])))
            if not archivos:
                return "no_verificable", None
            tot = 0
            for a in archivos:
                lista = _ruta(_leer(Path(a)), v["ruta"])
                if not isinstance(lista, list):
                    return "no_verificable", None
                tot += len(lista)
            obs = Decimal(tot)
    except (OSError, ValueError, KeyError):
        return "no_verificable", None
    if obs is None:
        return "no_verificable", None
    return ("coincide" if obs == _dec(cifra["valor"]) else "difiere"), _num_json(obs)


def comprobar_estudios(raiz: Path, corridas: Optional[List[Corrida]] = None) -> Tuple[List[str], List[str], Dict[str, Dict[str, Any]]]:
    """Reglas de honestidad del registro. Devuelve (errores, advertencias, evaluación por estudio)."""
    raiz = Path(raiz)
    errores: List[str] = []
    avisos: List[str] = []
    try:
        doc = cargar_estudios(raiz)
    except (OSError, ValueError) as ex:
        return [f"no se puede leer evidencia/estudios.json: {ex}"], [], {}
    errores += validar_estructura_estudios(doc)
    if errores:
        return errores, avisos, {}
    if corridas is None:
        corridas = cargar_corridas(raiz)
    ids = {e["id"] for e in doc["estudios"]}
    for k in corridas:
        est = k.m.get("estudio")
        if k.valida and est and est not in ids and est not in ESTUDIOS_DE_APOYO:
            avisos.append(f"{k.run_id}: el estudio {est} no está en el registro y no se cuenta")
    evals: Dict[str, Dict[str, Any]] = {}
    for e in doc["estudios"]:
        ev_ = evaluar_estudio(e, corridas)
        evals[e["id"]] = ev_
        p = f"{e['id']}: "
        dec_e, cal_e = e["estado_ejecucion"], ev_["estado_calculado"]
        rango = {"pendiente": 0, "bloqueado": 0, "parcial": 1, "ejecutado": 2}
        hay_basis = any(a.get("procedencia") == "reportado_historico" for a in e.get("antecedentes") or [])
        if dec_e == "ejecutado":
            if cal_e != "ejecutado":
                faltan = [c["id"] for c in ev_["componentes"] if not c["satisfecho"]]
                errores.append(p + f"declara ejecutado pero las corridas solo lo dejan en {cal_e}; faltan componentes: {', '.join(faltan)}")
            if e.get("bloqueo"):
                errores.append(p + "un estudio ejecutado no puede tener bloqueo")
        elif dec_e == "parcial":
            if cal_e == "pendiente" and not hay_basis:
                errores.append(p + "declara parcial pero no hay corridas que lo sostengan ni antecedentes reportados")
            elif cal_e == "ejecutado":
                avisos.append(p + "registro desactualizado: las corridas ya lo dejan ejecutado; actualice estado_ejecucion")
        elif dec_e in ("pendiente", "bloqueado"):
            if rango[cal_e] > 0:
                avisos.append(p + f"registro desactualizado: declara {dec_e} pero las corridas lo dejan {cal_e}")
            if dec_e == "bloqueado" and not e.get("bloqueo"):
                errores.append(p + "bloqueado exige bloqueo con causa y desbloqueo")
            if dec_e == "pendiente" and e.get("bloqueo"):
                errores.append(p + "pendiente no lleva bloqueo (use bloqueado)")
        dec_r, cal_r = e["resultado"], ev_["resultado_calculado"]
        if dec_r != "no_evaluable":
            if dec_e != "ejecutado":
                errores.append(p + f"resultado {dec_r} exige estado ejecutado")
            if not e.get("criterio"):
                errores.append(p + f"resultado {dec_r} exige un criterio con interpretación fijada")
            if dec_r != cal_r:
                errores.append(p + f"declara {dec_r} pero el recálculo desde los predicados da {cal_r} ({ev_['motivo_resultado']})")
        elif cal_r in ("cumple", "no_cumple"):
            avisos.append(p + f"registro desactualizado: el recálculo da {cal_r}; actualice resultado")
        for k in ev_["propias"]:
            if k.valida:
                c = _ruta(k.m.get("parametros"), "componente")
                if c is not None and c not in {x["id"] for x in ev_["componentes"]}:
                    errores.append(f"{k.run_id}: parametros.componente {c!r} no existe en el estudio {e['id']}")
        for a in e.get("antecedentes") or []:
            for ci in a.get("cifras") or []:
                estado, actual = _verificar_cifra(raiz, ci)
                v = ci.get("verificacion") or {}
                if estado == "difiere":
                    msg = p + f"antecedente {a['id']}: «{ci['etiqueta']}» dice {ci['valor']} y el archivo da {actual}"
                    (errores if v.get("estricta") else avisos).append(msg)
                elif estado == "no_verificable" and v.get("estricta"):
                    errores.append(p + f"antecedente {a['id']}: «{ci['etiqueta']}» no se puede verificar desde {v.get('archivo') or v.get('glob')}")
    return errores, avisos, evals


# ------------------------------------------------------------------ derivados
def _resumen_corrida(k: Corrida, cuenta: Tuple[bool, str], raiz: Path) -> Dict[str, Any]:
    m = k.m
    cod = m.get("codigo") or {}
    return {
        "run_id": k.run_id, "procedencia": m.get("procedencia"), "fecha_utc": m.get("fecha_utc"),
        "commit": cod.get("commit"), "arbol_limpio": cod.get("arbol_limpio"), "snapshot_sha256": cod.get("snapshot_sha256"),
        "estado_ejecucion": m.get("estado_ejecucion"), "resultado": m.get("resultado"),
        "cuenta": bool(cuenta[0]), "motivo": cuenta[1] or None, "gasto_usd": m.get("gasto_usd"),
        "modelo": m.get("modelo"), "componente": _ruta(m.get("parametros"), "componente"),
        "manifiesto": f"evidencia/corridas/{k.dir.name}/manifiesto.json",
        "datos": [{"ruta": r.get("ruta"), "sha256": r.get("sha256")} for r in (m.get("resultados") or []) if isinstance(r, dict)],
    }


def derivar(raiz: Path) -> Dict[str, str]:
    """Contenido (texto) de cada archivo derivado, por ruta relativa. Sin marcas de tiempo de ejecución:
    solo datos de los manifiestos y de los registros."""
    raiz = Path(raiz)
    corridas = cargar_corridas(raiz)
    doc = cargar_estudios(raiz)
    errores, _, evals = comprobar_estudios(raiz, corridas)
    if not evals:
        raise SystemExit("no se puede derivar: " + "; ".join(errores[:5]))
    estudios_out: List[Dict[str, Any]] = []
    filas_estudios: List[List[Any]] = [["id", "nombre", "tipo", "estado_ejecucion", "estado_calculado", "resultado", "resultado_calculado",
                                        "n_corridas", "n_corridas_que_cuentan", "procedencias_que_cuentan", "fecha_ultima_corrida",
                                        "commit_ultima_corrida", "hu_relacionadas"]]
    por_estado: Dict[str, int] = {}
    por_resultado: Dict[str, int] = {}
    for e in doc["estudios"]:
        x = evals[e["id"]]
        propias = sorted(x["propias"], key=lambda k: (k.m.get("fecha_utc", ""), k.run_id))
        res_corridas = [_resumen_corrida(k, x["cuenta"].get(k.run_id, (False, "manifiesto inválido")), raiz) for k in propias]
        cuentan = [r for r in res_corridas if r["cuenta"]]
        procs = {}
        for r in cuentan:
            procs[r["procedencia"]] = procs.get(r["procedencia"], 0) + 1
        todas_procs = {}
        for r in res_corridas:
            todas_procs[r["procedencia"]] = todas_procs.get(r["procedencia"], 0) + 1
        ultima = cuentan[-1] if cuentan else None
        antecedentes = []
        for a in e.get("antecedentes") or []:
            cifras = []
            for ci in a.get("cifras") or []:
                estado, actual = _verificar_cifra(raiz, ci)
                cifras.append({"etiqueta": ci["etiqueta"], "valor": ci["valor"], "unidad": ci["unidad"], "verificacion": estado, "valor_actual": actual})
            antecedentes.append({"id": a["id"], "descripcion": a["descripcion"], "procedencia": a["procedencia"], "fuente": a["fuente"],
                                 "cifras": cifras, "cuenta_como_evidencia": False})
        cr = e.get("criterio")
        estudios_out.append({
            "id": e["id"], "nombre": e["nombre"], "objetivo": e["objetivo"], "clasificacion": e["clasificacion"], "pregunta": e["pregunta"],
            "muestra": e["muestra"], "comparadores": e["comparadores"],
            "criterio": None if not cr else {"texto": cr["texto"], "interpretacion": cr["interpretacion"], "fijado_utc": cr["fijado_utc"],
                                              "aprobado_por_equipo": cr["aprobado_por_equipo"]},
            "meta_documental": e["meta_documental"], "limitaciones": e["limitaciones"], "reproduccion": e["reproduccion"],
            "hu_relacionadas": e["hu_relacionadas"], "bloqueo": e.get("bloqueo"),
            "estado_ejecucion": e["estado_ejecucion"], "estado_calculado": x["estado_calculado"],
            "resultado": e["resultado"], "resultado_calculado": x["resultado_calculado"], "motivo_resultado": x["motivo_resultado"],
            "componentes": x["componentes"], "predicados": x["predicados"], "cifras_principales": x["cifras_principales"],
            "procedencias_que_cuentan": procs, "procedencias_todas": todas_procs,
            "hay_simulado_o_asistido": any(p in todas_procs for p in ("simulado", "asistido_ia")),
            "n_corridas": len(res_corridas), "n_corridas_que_cuentan": len(cuentan),
            "fecha_ultima_corrida": None if not ultima else ultima["fecha_utc"],
            "commit_ultima_corrida": None if not ultima else (ultima["commit"] if ultima["arbol_limpio"] else None),
            "snapshot_ultima_corrida": None if not ultima else ultima["snapshot_sha256"],
            "corridas": res_corridas, "antecedentes": antecedentes,
        })
        por_estado[e["estado_ejecucion"]] = por_estado.get(e["estado_ejecucion"], 0) + 1
        por_resultado[e["resultado"]] = por_resultado.get(e["resultado"], 0) + 1
        filas_estudios.append([e["id"], e["nombre"], e["clasificacion"]["tipo"], e["estado_ejecucion"], x["estado_calculado"], e["resultado"],
                               x["resultado_calculado"], len(res_corridas), len(cuentan), " ".join(f"{p}:{n}" for p, n in sorted(procs.items())),
                               None if not ultima else ultima["fecha_utc"], None if not ultima else ultima["commit"], " ".join(e["hu_relacionadas"])])
    derivado = {
        "esquema": ESQUEMA_DERIVADO, "objetivo": doc["objetivo"],
        "nota": "Derivado por tools/evidencia.py regenerar desde evidencia/estudios.json y evidencia/corridas/*/manifiesto.json. No editar a mano: python tools/evidencia.py verificar falla si difiere.",
        "totales": {"estudios": len(estudios_out), "por_estado_ejecucion": por_estado, "por_resultado": por_resultado,
                    "corridas": len(corridas), "corridas_invalidas": sum(1 for k in corridas if not k.valida)},
        "estudios": estudios_out,
    }
    archivos: Dict[str, str] = {
        "evidencia/derivados/estudios.json": ev.json_canonico(derivado),
        "evidencia/derivados/estudios.csv": _csv(filas_estudios),
    }
    filas_corridas: List[List[Any]] = [["run_id", "estudio", "procedencia", "fecha_utc", "commit", "arbol_limpio", "snapshot_sha256",
                                        "estado_ejecucion", "resultado", "cuenta", "motivo", "gasto_usd", "manifiesto"]]
    for k in sorted(corridas, key=lambda k: (k.m.get("fecha_utc", ""), k.run_id)):
        est = k.m.get("estudio")
        cu = evals[est]["cuenta"].get(k.run_id, (False, "manifiesto inválido" if not k.valida else "estudio fuera del registro")) if est in evals else (False, "estudio fuera del registro")
        r = _resumen_corrida(k, cu, raiz)
        filas_corridas.append([r["run_id"], est, r["procedencia"], r["fecha_utc"], r["commit"], r["arbol_limpio"], r["snapshot_sha256"],
                               r["estado_ejecucion"], r["resultado"], r["cuenta"], r["motivo"], r["gasto_usd"], r["manifiesto"]])
    archivos["evidencia/derivados/corridas.csv"] = _csv(filas_corridas)
    tarifas_p = raiz / "evidencia" / "tarifas" / "tarifas.json"
    if tarifas_p.exists():
        t = _leer(tarifas_p)
        campos = ["entrada_sin_cache_por_millon", "entrada_cache_lectura_por_millon", "entrada_cache_escritura_por_millon", "salida_por_millon"]
        lista = [{"proveedor": x["proveedor"], "modelo_api_id": x["modelo_api_id"], "alias": x.get("alias") or [], "estado": x["estado"],
                  **{c: x.get(c) for c in campos}, "moneda": x.get("moneda"), "fecha_consulta_utc": x.get("fecha_consulta_utc"),
                  "url_oficial": x.get("url_oficial"), "extracto_sha256": x.get("extracto_sha256"),
                  "motivo_no_verificada": x.get("motivo_no_verificada")} for x in t["tarifas"]]
        archivos["evidencia/derivados/tarifas.json"] = ev.json_canonico({
            "esquema": ESQUEMA_TARIFAS_DERIVADO, "moneda": t.get("moneda"), "unidad": t.get("unidad"), "consulta_utc": t.get("consulta_utc"),
            "nota_tokenizadores": t.get("nota_tokenizadores"), "tarifas": lista})
        archivos["evidencia/derivados/tarifas.csv"] = _csv([["proveedor", "modelo_api_id", "estado", *campos, "fecha_consulta_utc", "url_oficial"]] +
                                                          [[x["proveedor"], x["modelo_api_id"], x["estado"], *[x[c] for c in campos], x["fecha_consulta_utc"], x["url_oficial"]] for x in lista])
    return archivos


def regenerar(raiz: Path) -> List[str]:
    raiz = Path(raiz)
    escritos = []
    for rel, texto in derivar(raiz).items():
        p = raiz / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        with open(p, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(texto)
        escritos.append(rel)
    return escritos


def comprobar_derivados(raiz: Path) -> Tuple[List[str], List[str]]:
    raiz = Path(raiz)
    errores: List[str] = []
    avisos: List[str] = []
    esperado = derivar(raiz)
    for rel, texto in esperado.items():
        p = raiz / rel
        if not p.exists():
            errores.append(f"falta {rel}: ejecute python tools/evidencia.py regenerar")
        elif p.read_bytes().decode("utf-8") != texto:
            errores.append(f"{rel} difiere de lo que se deriva de los datos (¿editado a mano?): ejecute python tools/evidencia.py regenerar y revise el cambio")
    carpeta = raiz / "evidencia" / "derivados"
    if carpeta.exists():
        conocidos = {Path(r).name for r in esperado}
        for p in sorted(carpeta.iterdir()):
            if p.is_file() and p.name not in conocidos and p.name.lower() != "readme.md":
                avisos.append(f"evidencia/derivados/{p.name} no lo genera tools/evidencia.py")
    return errores, avisos


def verificar(raiz: Path) -> Tuple[List[str], List[str]]:
    errores, avisos, corridas = validar(raiz)
    e2, a2, _ = comprobar_estudios(raiz, corridas)
    errores += e2
    avisos += a2
    if not e2:
        e3, a3 = comprobar_derivados(raiz)
        errores += e3
        avisos += a3
    return errores, avisos


# ------------------------------------------------------------------------ CLI
def _tabla_estudios(raiz: Path, evals: Dict[str, Dict[str, Any]]) -> str:
    doc = cargar_estudios(raiz)
    filas = [["estudio", "estado declarado", "calculado", "resultado", "recalculado", "corridas (cuentan)", "tipo"]]
    for e in doc["estudios"]:
        x = evals[e["id"]]
        filas.append([e["id"], e["estado_ejecucion"], x["estado_calculado"], e["resultado"], x["resultado_calculado"],
                      f"{len(x['propias'])} ({len(x['que_cuentan'])})", e["clasificacion"]["tipo"]])
    anchos = [max(len(str(f[i])) for f in filas) for i in range(len(filas[0]))]
    return "\n".join("  ".join(str(c).ljust(anchos[i]) for i, c in enumerate(f)) for f in filas)


def _contrato(raiz: Path) -> str:
    doc = cargar_estudios(raiz)
    out = []
    for e in doc["estudios"]:
        out.append(f"{e['id']} - {e['nombre']}")
        for c in e["componentes"]:
            out.append(f"   componente {c['id']}: procedencias {', '.join(c['procedencias_admitidas'])}; mínimo {c['minimo_corridas']} corrida(s); "
                       "parametros.componente = " + c["id"] + (" (opcional: es el único)" if len(e["componentes"]) == 1 else ""))
        for q in (e.get("criterio") or {}).get("predicados", []):
            donde = f"resumen.{q['ruta']}" if q["fuente"] == "resumen" else f"manifiesto.{q['ruta']}"
            out.append(f"   predicado {q['id']}: {q['agregacion']}({donde}) {q['op']} {q['valor']}")
        for ci in e.get("cifras") or []:
            out.append(f"   cifra {ci['id']}: {ci['agregacion']}(resumen.{ci['ruta']}) [{ci['unidad']}]")
    return "\n".join(out)


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(prog="evidencia", description="Maquinaria de evidencia reproducible")
    ap.add_argument("--raiz", type=Path, default=None, help="raíz del repositorio (por defecto la de este archivo)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("validar", help="valida los manifiestos de evidencia/corridas")
    s = sub.add_parser("estudios", help="valida el registro de estudios (dos ejes y honestidad)")
    s.add_argument("--estricto", action="store_true", help="las advertencias también fallan")
    s.add_argument("--contrato", action="store_true", help="imprime qué debe registrar cada corrida (componentes y campos del resumen)")
    sub.add_parser("regenerar", help="escribe evidencia/derivados/ de forma determinista")
    v = sub.add_parser("verificar", help="validar + estudios + derivados al día")
    v.add_argument("--estricto", action="store_true")
    a = ap.parse_args(argv)
    raiz = Path(a.raiz) if a.raiz else ev.raiz_repo()

    def informar(errores: List[str], avisos: List[str]) -> None:
        for x in errores:
            print("ERROR", x)
        for x in avisos:
            print("ADVERTENCIA", x)

    if a.cmd == "validar":
        errores, avisos, corridas = validar(raiz)
        informar(errores, avisos)
        print(f"corridas: {len(corridas)} manifiesto(s), {sum(1 for k in corridas if not k.valida)} inválido(s)")
        return 1 if errores else 0
    if a.cmd == "estudios":
        if a.contrato:
            print(_contrato(raiz))
            return 0
        errores, avisos, evals = comprobar_estudios(raiz)
        if evals:
            print(_tabla_estudios(raiz, evals))
        informar(errores, avisos)
        return 1 if errores or (a.estricto and avisos) else 0
    if a.cmd == "regenerar":
        errores, avisos, _ = validar(raiz)
        e2, a2, _ = comprobar_estudios(raiz)
        if errores or e2:
            informar(errores + e2, avisos + a2)
            print("No se regenera con errores en las corridas o en el registro.")
            return 1
        for rel in regenerar(raiz):
            print("escrito", rel)
        return 0
    if a.cmd == "verificar":
        errores, avisos = verificar(raiz)
        informar(errores, avisos)
        if not errores:
            print("evidencia verificada: corridas válidas, registro de estudios coherente y derivados al día")
        return 1 if errores or (a.estricto and avisos) else 0
    return 2


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(main())
