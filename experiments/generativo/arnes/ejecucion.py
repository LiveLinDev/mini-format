"""Matriz experimental, almacén JSONL reanudable y ejecución de muestras."""
from __future__ import annotations

import datetime as _dt
import hashlib
import json
import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import yaml

from minifmt.ai import merge_repair, repair_request
from minifmt.ai.adapters import Adapter, AdapterError, MissingKeyError, SimTarget, SimulatedAdapter, get_adapter, redact
from minifmt.ai.adapters.base import api_key
from minifmt.tokens import count_tokens

from . import brazos as B
from . import metricas as M
from . import tareas as T
from .costos import Precios

log = logging.getLogger("exp.generativo")

EXPERIMENTOS = ("v2", "v3b")
ENV_PROVEEDOR = {"openai": "OPENAI_API_KEY", "anthropic": "ANTHROPIC_API_KEY", "groq": "GROQ_API_KEY"}
STOP_TRUNCADO = {"max_tokens", "length"}


# --------------------------------------------------------------------------
# Configuración
# --------------------------------------------------------------------------
class ErrorConfig(ValueError):
    pass


def cargar_config(path: Path) -> Dict[str, Any]:
    cfg = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
    cfg.setdefault("nombre", Path(path).stem)
    cfg.setdefault("semilla", 0)
    cfg.setdefault("idioma", "es")
    cfg.setdefault("temperatura", 0.7)
    cfg.setdefault("max_tokens", 4096)
    cfg.setdefault("repeticiones", 1)
    cfg.setdefault("brazos", list(B.BRAZOS))
    cfg.setdefault("experimentos", {"v2": {"activo": True}})
    cfg.setdefault("reparacion", {})
    validar_config(cfg)
    return cfg


def validar_config(cfg: Dict[str, Any]) -> None:
    if not cfg.get("tareas"):
        raise ErrorConfig("la configuración no declara tareas")
    if not cfg.get("modelos"):
        raise ErrorConfig("la configuración no declara modelos")
    for b in cfg["brazos"]:
        if b not in B.BRAZOS:
            raise ErrorConfig(f"brazo desconocido: {b}")
    for m in cfg["modelos"]:
        if "proveedor" not in m or "modelo" not in m:
            raise ErrorConfig(f"modelo sin proveedor/modelo: {m}")
    for e in cfg["experimentos"]:
        if e not in EXPERIMENTOS + ("v3a",):
            raise ErrorConfig(f"experimento desconocido: {e}")
    catalogo = set(T.catalogo())
    for t in cfg["tareas"]:
        if t not in catalogo:
            raise ErrorConfig(f"tarea desconocida: {t}")
    if int(cfg["repeticiones"]) < 1:
        raise ErrorConfig("repeticiones debe ser >= 1")


# --------------------------------------------------------------------------
# Matriz
# --------------------------------------------------------------------------
@dataclass(frozen=True)
class Unidad:
    experimento: str
    tarea: str
    brazo: str
    proveedor: str
    modelo: str
    rep: int
    max_tokens: int

    @property
    def id(self) -> str:
        return f"{self.experimento}/{self.tarea}/{self.brazo}/{self.proveedor}:{self.modelo}/r{self.rep:03d}"

    def id_brazo(self, brazo: str) -> str:
        return f"{self.experimento}/{self.tarea}/{brazo}/{self.proveedor}:{self.modelo}/r{self.rep:03d}"


class Contexto:
    def __init__(self, cfg: Dict[str, Any], tareas: Optional[Dict[str, T.Tarea]] = None):
        self.cfg = cfg
        self.idioma = cfg.get("idioma", "es")
        self.tareas = tareas if tareas is not None else T.cargar(cfg["tareas"])
        self._prompts: Dict[Tuple[str, str], B.Prompt] = {}
        self._refs: Dict[Tuple[str, str], str] = {}
        self._reftok: Dict[Tuple[str, str], int] = {}

    def prompt(self, t: T.Tarea, brazo: str) -> B.Prompt:
        k = (t.id, "D" if brazo == "D+R" else brazo)
        if k not in self._prompts:
            self._prompts[k] = B.construir_prompt(t, k[1], self.idioma)
        return self._prompts[k]

    def salida_ref(self, t: T.Tarea, brazo: str) -> str:
        k = (t.id, "D" if brazo == "D+R" else brazo)
        if k not in self._refs:
            self._refs[k] = B.salida_referencia(t, k[1])
        return self._refs[k]

    def tokens_ref(self, t: T.Tarea, brazo: str) -> int:
        k = (t.id, "D" if brazo == "D+R" else brazo)
        if k not in self._reftok:
            self._reftok[k] = count_tokens(self.salida_ref(t, brazo))
        return self._reftok[k]


def enumerar(cfg: Dict[str, Any], ctx: Contexto) -> Tuple[List[Unidad], List[str]]:
    unidades: List[Unidad] = []
    omitidas: List[str] = []
    exps = cfg.get("experimentos", {})
    for exp in EXPERIMENTOS:
        ecfg = exps.get(exp)
        if not ecfg or not ecfg.get("activo", True):
            continue
        brazos = list(ecfg.get("brazos", cfg["brazos"]))
        reps = int(ecfg.get("repeticiones", cfg["repeticiones"]))
        tareas = list(ecfg.get("tareas", cfg["tareas"]))
        if "D+R" in brazos and "D" not in brazos:
            raise ErrorConfig(f"{exp}: el brazo D+R requiere el brazo D")
        for tid in tareas:
            t = ctx.tareas[tid]
            for m in cfg["modelos"]:
                prov, mod = m["proveedor"], m["modelo"]
                if "C" in brazos and not m.get("estructurado", False):
                    omitidas.append(f"{exp}: brazo C omitido para {prov}:{mod} (sin modo estructurado declarado) "
                                    f"en {len(tareas)} tarea(s)")
                for rep in range(1, reps + 1):
                    for b in brazos:
                        if b == "C" and not m.get("estructurado", False):
                            continue
                        if exp == "v3b":
                            frac = float(ecfg.get("fraccion_max_tokens", 0.5))
                            mt = max(16, int(frac * ctx.tokens_ref(t, b)))
                        else:
                            mt = int(m.get("max_tokens", cfg["max_tokens"]))
                        unidades.append(Unidad(exp, tid, b, prov, mod, rep, mt))
    # sin duplicar mensajes de omisión por repetición
    return unidades, sorted(set(omitidas))


# --------------------------------------------------------------------------
# Almacén JSONL reanudable
# --------------------------------------------------------------------------
class Almacen:
    def __init__(self, directorio: Path):
        self.dir = Path(directorio)
        self.dir.mkdir(parents=True, exist_ok=True)
        self.muestras = self.dir / "muestras.jsonl"
        self.fallos = self.dir / "fallos.jsonl"
        self.ids: set = set()
        self.generaciones_d: Dict[str, Dict[str, Any]] = {}
        self.costo_incremental = 0.0
        self.lineas_corruptas = 0
        self._cargar()

    def _cargar(self) -> None:
        if not self.muestras.exists():
            return
        with open(self.muestras, "rb+") as fh:
            fh.seek(0, os.SEEK_END)
            if fh.tell() > 0:
                fh.seek(-1, os.SEEK_END)
                if fh.read(1) != b"\n":       # escritura interrumpida: aislar la línea parcial
                    fh.write(b"\n")
        with open(self.muestras, "r", encoding="utf-8") as fh:
            for linea in fh:
                if not linea.strip():
                    continue
                try:
                    s = json.loads(linea)
                except ValueError:
                    self.lineas_corruptas += 1   # p. ej. escritura interrumpida; esa muestra se repetirá
                    continue
                self._registrar(s)

    def _registrar(self, s: Dict[str, Any]) -> None:
        self.ids.add(s["id"])
        if s.get("brazo") == "D":
            self.generaciones_d[s["id"]] = {"respuesta": s["respuesta"], "prompt": s.get("prompt"), "semilla": s.get("semilla")}
        self.costo_incremental += float(s.get("costo_incremental_usd") or 0.0)

    def agregar(self, s: Dict[str, Any]) -> None:
        with open(self.muestras, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(s, ensure_ascii=False) + "\n")
            fh.flush()
            os.fsync(fh.fileno())
        self._registrar(s)

    def fallo(self, d: Dict[str, Any]) -> None:
        with open(self.fallos, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(d, ensure_ascii=False) + "\n")

    def leer(self) -> List[Dict[str, Any]]:
        return leer_muestras(self.muestras)


def leer_muestras(path: Path) -> List[Dict[str, Any]]:
    out = []
    if not Path(path).exists():
        return out
    with open(path, "r", encoding="utf-8") as fh:
        for linea in fh:
            try:
                out.append(json.loads(linea))
            except ValueError:
                continue
    return out


# --------------------------------------------------------------------------
# Oráculo del adaptador simulado
# --------------------------------------------------------------------------
class Oraculo:
    def __init__(self):
        self._d: Dict[str, SimTarget] = {}

    @staticmethod
    def _k(system: str, user: str) -> str:
        return hashlib.sha256((system + "\x00" + user).encode("utf-8")).hexdigest()

    def registrar(self, system: str, user: str, target: SimTarget) -> None:
        self._d[self._k(system, user)] = target

    def __call__(self, system: str, user: str) -> Optional[SimTarget]:
        return self._d.get(self._k(system, user))


def crear_adaptador(m: Dict[str, Any], modo: str, oraculo: Optional[Oraculo], semilla: int) -> Adapter:
    estructurado = bool(m.get("estructurado", False))
    if modo == "simulado":
        return SimulatedAdapter(model=m["modelo"], oracle=oraculo, profile=m.get("perfil_simulado", "medio"),
                                seed=semilla, structured=estructurado)
    return get_adapter(m["proveedor"], m["modelo"], structured=estructurado,
                       send_temperature=bool(m.get("enviar_temperatura", True)), extra_body=m.get("extra_body"))


def verificar_claves(cfg: Dict[str, Any]) -> List[str]:
    """Nombres de variables de entorno ausentes (nunca devuelve valores)."""
    faltan = []
    for prov in sorted({m["proveedor"] for m in cfg["modelos"]}):
        var = ENV_PROVEEDOR.get(prov)
        if var is None:
            faltan.append(f"proveedor sin variable conocida: {prov}")
            continue
        try:
            api_key(var)
        except MissingKeyError:
            faltan.append(var)
    return faltan


def semilla_muestra(semilla: int, uid: str) -> int:
    return int(hashlib.sha256(f"{semilla}|{uid}".encode("utf-8")).hexdigest()[:8], 16)


# --------------------------------------------------------------------------
# Ejecución
# --------------------------------------------------------------------------
class PresupuestoExcedido(RuntimeError):
    pass


def _ahora() -> str:
    return _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds")


def _respuesta_serializable(r: Dict[str, Any]) -> Dict[str, Any]:
    return {k: r.get(k) for k in ("text", "input_tokens", "output_tokens", "latency_ms", "stop_reason", "model", "provider", "raw")}


class Ejecutor:
    def __init__(self, cfg: Dict[str, Any], ctx: Contexto, modo: str, salida: Path, precios: Precios,
                 max_costo: Optional[float] = None, adaptadores: Optional[Dict[Tuple[str, str], Adapter]] = None):
        self.cfg, self.ctx, self.modo, self.precios, self.max_costo = cfg, ctx, modo, precios, max_costo
        self.almacen = Almacen(salida)
        self.oraculo = Oraculo() if modo == "simulado" else None
        self.adaptadores = adaptadores or {}
        self.rep_cfg = cfg.get("reparacion", {})
        self.fallos_seguidos = 0

    def adaptador(self, prov: str, mod: str) -> Adapter:
        k = (prov, mod)
        if k not in self.adaptadores:
            m = next(x for x in self.cfg["modelos"] if x["proveedor"] == prov and x["modelo"] == mod)
            self.adaptadores[k] = crear_adaptador(m, self.modo, self.oraculo, int(self.cfg["semilla"]))
        return self.adaptadores[k]

    def _modelo_cfg(self, u: Unidad) -> Dict[str, Any]:
        return next(x for x in self.cfg["modelos"] if x["proveedor"] == u.proveedor and x["modelo"] == u.modelo)

    def _temperatura(self, u: Unidad) -> Optional[float]:
        m = self._modelo_cfg(u)
        return m["temperatura"] if "temperatura" in m else self.cfg.get("temperatura")

    def _costo(self, u: Unidad, tin: Optional[int], tout: Optional[int]) -> Optional[float]:
        return self.precios.costo(u.proveedor, u.modelo, tin, tout)

    # --------------------------------------------------------------
    def correr(self, unidades: List[Unidad], limite: Optional[int] = None) -> Dict[str, Any]:
        res = {"ejecutadas": 0, "saltadas": 0, "fallos": 0, "abortado": None}
        for u in unidades:
            if u.id in self.almacen.ids:
                res["saltadas"] += 1
                continue
            if limite is not None and res["ejecutadas"] >= limite:
                break
            try:
                s = self.ejecutar(u)
            except MissingKeyError as e:
                res["abortado"] = f"clave ausente: {e}"
                break
            except AdapterError as e:
                res["fallos"] += 1
                self.fallos_seguidos += 1
                self.almacen.fallo({"id": u.id, "fecha": _ahora(), "error": redact(e), "status": e.status})
                log.warning("fallo en %s: %s", u.id, redact(e))
                if self.fallos_seguidos >= int(self.cfg.get("max_fallos_seguidos", 5)):
                    res["abortado"] = f"{self.fallos_seguidos} fallos seguidos"
                    break
                continue
            self.fallos_seguidos = 0
            self.almacen.agregar(s)
            res["ejecutadas"] += 1
            if self.max_costo is not None and self.almacen.costo_incremental > self.max_costo:
                res["abortado"] = (f"costo acumulado {self.almacen.costo_incremental:.4f} USD supera "
                                   f"--max-costo-usd {self.max_costo}")
                break
        res["costo_acumulado_usd"] = round(self.almacen.costo_incremental, 6)
        return res

    # --------------------------------------------------------------
    def _registrar_objetivo(self, t: T.Tarea, brazo: str, p: B.Prompt) -> None:
        if self.oraculo is None:
            return
        self.oraculo.registrar(p.system, p.user, SimTarget(kind=B.tipo_objetivo_simulado(brazo), contract=t.contrato,
                                                           records=t.registros, header=t.cabecera))

    def ejecutar(self, u: Unidad) -> Dict[str, Any]:
        t = self.ctx.tareas[u.tarea]
        semilla = semilla_muestra(int(self.cfg["semilla"]), u.id)
        temp = self._temperatura(u)
        base = {"id": u.id, "experimento": u.experimento, "tarea": u.tarea, "tipo_tarea": t.tipo, "prefijo": t.prefijo,
                "dominio": t.dominio, "brazo": u.brazo, "proveedor": u.proveedor, "modelo": u.modelo,
                "repeticion": u.rep, "adaptador": self.modo, "simulado": self.modo == "simulado",
                "semilla": semilla, "temperatura": temp, "max_tokens": u.max_tokens, "fecha": _ahora()}
        if u.brazo == "D+R":
            return self._ejecutar_reparacion(u, t, base, temp)
        ad = self.adaptador(u.proveedor, u.modelo)
        p = self.ctx.prompt(t, u.brazo)
        self._registrar_objetivo(t, u.brazo, p)
        r = ad.generate(p.system, p.user, max_tokens=u.max_tokens, temperature=temp,
                        response_format=p.response_format, seed=semilla)
        lectura = B.leer(u.brazo, r["text"], t)
        met = M.evaluar(lectura, t)
        costo = self._costo(u, r["input_tokens"], r["output_tokens"])
        met.update({"tokens_entrada": r["input_tokens"], "tokens_salida": r["output_tokens"],
                    "latencia_ms": r["latency_ms"], "truncado": r.get("stop_reason") in STOP_TRUNCADO,
                    "llamadas": 1, "llamadas_reparacion": 0, "tokens_reparacion_entrada": 0,
                    "tokens_reparacion_salida": 0})
        return {**base, "prompt": {"system": p.system, "user": p.user, "response_format": p.response_format},
                "respuesta": _respuesta_serializable(r), "reparacion": None,
                "lectura": {"avisos": lectura.avisos[:50], "n_declarado": lectura.n_declarado},
                "metricas": met, "costo_usd": costo, "costo_incremental_usd": costo,
                "costo_nocional": self.modo == "simulado"}

    def _ejecutar_reparacion(self, u: Unidad, t: T.Tarea, base: Dict[str, Any], temp: Optional[float]) -> Dict[str, Any]:
        gen = self.almacen.generaciones_d.get(u.id_brazo("D"))
        if gen is None:
            raise AdapterError(f"la muestra D de {u.id} no está disponible (se reintentará)")
        r0 = gen["respuesta"]
        c = t.contrato
        ad = self.adaptador(u.proveedor, u.modelo)
        max_rondas = int(self.rep_cfg.get("max_rondas", 1))
        factor = float(self.rep_cfg.get("max_tokens_factor", 2.0))
        temp_rep = self.rep_cfg.get("temperatura", 0.0)
        if not self._modelo_cfg(u).get("enviar_temperatura", True):
            temp_rep = None
        contexto = t.texto_entrada if (self.rep_cfg.get("incluir_entrada", False) and t.tipo == "extraccion") else None
        texto = r0["text"] or ""
        rondas = []
        tin = tout = 0
        lat = 0.0
        for k in range(max_rondas):
            req = repair_request(texto, c, self.ctx.idioma, context=contexto)
            if not req.needed:
                break
            if self.oraculo is not None:
                self.oraculo.registrar(req.system, req.user, SimTarget(
                    kind="repair", contract=c, records=t.registros, header=t.cabecera,
                    repair_items=[(it.text, it.is_header) for it in req.items],
                    repair_context=contexto is not None))
            mt = max(256, int(req.max_tokens_hint * factor))
            rr = ad.generate(req.system, req.user, max_tokens=mt, temperature=temp_rep,
                             seed=semilla_muestra(base["semilla"], f"reparacion{k}"))
            merged = merge_repair(texto, rr["text"], c, req)
            tin += rr["input_tokens"] or 0
            tout += rr["output_tokens"] or 0
            lat += rr["latency_ms"] or 0.0
            rondas.append({"prompt": {"system": req.system, "user": req.user}, "max_tokens": mt,
                           "respuesta": _respuesta_serializable(rr), "lineas_solicitadas": req.lines,
                           "reemplazadas": merged.replaced, "eliminadas": merged.dropped,
                           "sin_resolver": merged.unresolved, "notas": merged.notes})
            progreso = bool(merged.replaced or merged.dropped)
            texto = merged.text
            if merged.ok or not progreso:
                break
        lectura = B.leer_D(texto, t)
        met = M.evaluar(lectura, t)
        costo_rep = self._costo(u, tin, tout) if rondas else 0.0
        costo_gen = self._costo(u, r0.get("input_tokens"), r0.get("output_tokens"))
        met.update({"tokens_entrada": (r0.get("input_tokens") or 0) + tin,
                    "tokens_salida": (r0.get("output_tokens") or 0) + tout,
                    "latencia_ms": round((r0.get("latency_ms") or 0.0) + lat, 1),
                    "truncado": r0.get("stop_reason") in STOP_TRUNCADO,
                    "llamadas": 1 + len(rondas), "llamadas_reparacion": len(rondas),
                    "tokens_reparacion_entrada": tin, "tokens_reparacion_salida": tout})
        total = None if (costo_gen is None or costo_rep is None) else costo_gen + costo_rep
        return {**base, "prompt": None, "generacion_de": u.id_brazo("D"),
                "respuesta": {"text": r0.get("text"), "input_tokens": r0.get("input_tokens"),
                              "output_tokens": r0.get("output_tokens"), "latency_ms": r0.get("latency_ms"),
                              "stop_reason": r0.get("stop_reason")},
                "reparacion": {"rondas": rondas, "documento_final": texto},
                "lectura": {"avisos": lectura.avisos[:50], "n_declarado": lectura.n_declarado},
                "metricas": met, "costo_usd": total, "costo_incremental_usd": costo_rep,
                "costo_nocional": self.modo == "simulado"}
