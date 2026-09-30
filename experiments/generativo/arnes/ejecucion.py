"""Matriz experimental, almacén JSONL reanudable y ejecución de muestras.

Una CELDA es (experimento, tarea, brazo, modelo, repetición).  Cada celda produce
una muestra en ``muestras.jsonl`` con la estructura ``solicitud`` acordada con el
flujo de infraestructura (``intentos`` por fase, usage por categorías, latencia).

Controles de gasto (ver ``presupuesto.py``): toda llamada pasa por
``Ejecutor._llamar``, que proyecta el peor caso contra el tope ANTES de llamar,
anota el inicio y el fin en el libro, registra cada reintento y NO llama si no hay
autorización (``modo='real'`` exige una ``Autorizacion`` válida).
"""
from __future__ import annotations

import datetime as _dt
import hashlib
import json
import logging
import os
import random
import signal
import statistics
import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path
from typing import Any, Callable, Dict, Iterator, List, Optional, Tuple

import yaml

from minifmt.ai.adapters import Adapter, AdapterError, MissingKeyError, SimTarget, get_adapter, redact
from minifmt.ai.adapters.base import api_key
from minifmt.tokens import count_tokens

from . import brazos as B
from . import json_tolerante as J
from . import metricas as M
from . import reparar as RP
from . import tareas as T
from .plan import (ESTADOS_CELDA, VERSION_ESQUEMA_MUESTRA, EstadoEstudio, orden_aleatorizado, semilla_orden)
from .presupuesto import Autorizacion, ErrorAutorizacion, Libro, Presupuesto
from .simulador import SimuladorArnes
from .tarifas import Tarifas, costo_peor_caso, costo_usage, decimal_a_texto
from .usage import es_negativa, usage_de_respuesta

log = logging.getLogger("exp.generativo")

EXPERIMENTOS = ("v2", "v3b")
ENV_PROVEEDOR = {"openai": "OPENAI_API_KEY", "anthropic": "ANTHROPIC_API_KEY", "groq": "GROQ_API_KEY"}
STOP_TRUNCADO = {"max_tokens", "length"}
BRAZOS_POR_DEFECTO = ["A", "B", "C", "D", "B+1", "C+1", "D+1"]
# Supuestos CONSERVADORES (no medidos) para convertir el conteo local o200k_base en una cota de tokens de cada proveedor.
FACTOR_TOKENIZADOR = {"openai": 1.0, "anthropic": 1.3, "groq": 1.15, "deepseek": 1.3, "simulado": 1.0}
POLITICAS_LIMITE = ("comun_por_tarea", "fraccion_por_brazo", "fijo")


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
    cfg.setdefault("brazos", list(BRAZOS_POR_DEFECTO))
    cfg.setdefault("experimentos", {"v2": {"activo": True}})
    cfg.setdefault("reparacion", {})
    cfg.setdefault("controles", {})
    cfg.setdefault("presupuesto", {})
    validar_config(cfg)
    return cfg


def _validar_brazos(brazos: List[str], donde: str) -> None:
    for b in brazos:
        if b == "D+R":
            raise ErrorConfig(f"{donde}: el brazo 'D+R' se llama ahora 'D+1' (Plan de Validación v3)")
        if b not in B.BRAZOS:
            raise ErrorConfig(f"{donde}: brazo desconocido: {b}")
        if B.es_reparacion(b) and B.base_de(b) not in brazos:
            raise ErrorConfig(f"{donde}: el brazo {b} requiere el brazo {B.base_de(b)}")


def validar_config(cfg: Dict[str, Any]) -> None:
    if not cfg.get("tareas"):
        raise ErrorConfig("la configuración no declara tareas")
    if not cfg.get("modelos"):
        raise ErrorConfig("la configuración no declara modelos")
    _validar_brazos(list(cfg["brazos"]), "brazos")
    for m in cfg["modelos"]:
        if "proveedor" not in m or "modelo" not in m:
            raise ErrorConfig(f"modelo sin proveedor/modelo: {m}")
    for e, ecfg in cfg["experimentos"].items():
        if e not in EXPERIMENTOS + ("v3a",):
            raise ErrorConfig(f"experimento desconocido: {e}")
        if isinstance(ecfg, dict) and ecfg.get("brazos"):
            _validar_brazos(list(ecfg["brazos"]), e)
        if e == "v3b" and isinstance(ecfg, dict) and ecfg.get("politica_limite", "comun_por_tarea") not in POLITICAS_LIMITE:
            raise ErrorConfig(f"v3b.politica_limite debe ser una de {POLITICAS_LIMITE}")
    catalogo = set(T.catalogo())
    for t in cfg["tareas"]:
        if t not in catalogo:
            raise ErrorConfig(f"tarea desconocida: {t}")
    if int(cfg["repeticiones"]) < 1:
        raise ErrorConfig("repeticiones debe ser >= 1")
    try:
        Presupuesto.desde_config(cfg)
    except Exception as e:  # noqa: BLE001
        raise ErrorConfig(f"presupuesto inválido: {e}") from None


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
        k = (t.id, B.base_de(brazo))
        if k not in self._prompts:
            self._prompts[k] = B.construir_prompt(t, k[1], self.idioma)
        return self._prompts[k]

    def salida_ref(self, t: T.Tarea, brazo: str) -> str:
        k = (t.id, B.base_de(brazo))
        if k not in self._refs:
            self._refs[k] = B.salida_referencia(t, k[1])
        return self._refs[k]

    def tokens_ref(self, t: T.Tarea, brazo: str) -> int:
        k = (t.id, B.base_de(brazo))
        if k not in self._reftok:
            self._reftok[k] = count_tokens(self.salida_ref(t, brazo))
        return self._reftok[k]


@dataclass
class Enumeracion:
    unidades: List[Unidad]                     # celdas ejecutables, en orden de ejecución
    no_aplicables: List[Dict[str, Any]]        # celdas que el diseño nominal incluye pero que no aplican (con motivo)
    nominal: Dict[str, Dict[str, int]]         # recuento nominal por experimento: primarias / reparaciones
    orden_semilla: int = 0
    aleatorizado: bool = True


def limite_v3b(ecfg: Dict[str, Any], ctx: Contexto, t: T.Tarea, brazos: List[str], brazo: str) -> int:
    """Límite de salida (tokens) de una celda de V3b.

    * ``comun_por_tarea`` (por defecto): el MISMO límite para todos los brazos de la
      tarea, ``fraccion × mediana`` de las salidas de referencia de los brazos
      presentes; así el límite no se escoge para favorecer a un formato.
    * ``fraccion_por_brazo``: cada brazo se corta a ``fraccion`` de su propia salida.
    * ``fijo``: ``limite_tokens`` para todas las celdas.
    La política y la fracción se fijan con el piloto real, antes del estudio.
    """
    politica = ecfg.get("politica_limite", "comun_por_tarea")
    frac = float(ecfg.get("fraccion_max_tokens", 0.5))
    if politica == "fijo":
        return int(ecfg["limite_tokens"])
    if politica == "fraccion_por_brazo":
        return max(16, int(frac * ctx.tokens_ref(t, brazo)))
    bases = sorted({B.base_de(b) for b in brazos})
    return max(16, int(frac * statistics.median([ctx.tokens_ref(t, b) for b in bases])))


def enumerar_completo(cfg: Dict[str, Any], ctx: Contexto) -> Enumeracion:
    exps = cfg.get("experimentos", {})
    candidatas: List[Unidad] = []
    no_ap: List[Dict[str, Any]] = []
    nominal: Dict[str, Dict[str, int]] = {}
    for exp in EXPERIMENTOS:
        ecfg = exps.get(exp)
        if not ecfg or not ecfg.get("activo", True):
            continue
        brazos = list(ecfg.get("brazos", cfg["brazos"]))
        reps = int(ecfg.get("repeticiones", cfg["repeticiones"]))
        tareas = list(ecfg.get("tareas", cfg["tareas"]))
        nominal[exp] = {"primarias": 0, "reparaciones": 0}
        for tid in tareas:
            t = ctx.tareas[tid]
            for m in cfg["modelos"]:
                prov, mod = m["proveedor"], m["modelo"]
                estructurado = bool(m.get("estructurado", False))
                for rep in range(1, reps + 1):
                    for b in brazos:
                        if exp == "v3b":
                            mt = limite_v3b(ecfg, ctx, t, brazos, b)
                        else:
                            mt = int(m.get("max_tokens", cfg["max_tokens"]))
                        u = Unidad(exp, tid, b, prov, mod, rep, mt)
                        nominal[exp]["reparaciones" if B.es_reparacion(b) else "primarias"] += 1
                        if B.base_de(b) == "C" and not estructurado:
                            no_ap.append({"id": u.id, "experimento": exp, "tarea": tid, "brazo": b, "proveedor": prov,
                                          "modelo": mod, "repeticion": rep,
                                          "motivo": "el modelo no declara modo estructurado nativo (estructurado: false)"})
                            continue
                        candidatas.append(u)
    ctl = cfg.get("controles") or {}
    barajar = bool(ctl.get("aleatorizar", True))
    semilla = semilla_orden(cfg)
    return Enumeracion(orden_aleatorizado(candidatas, semilla, barajar), no_ap, nominal, semilla, barajar)


def enumerar(cfg: Dict[str, Any], ctx: Contexto) -> Tuple[List[Unidad], List[str]]:
    """Interfaz compacta: (celdas ejecutables, mensajes de omisión)."""
    en = enumerar_completo(cfg, ctx)
    grupos: Dict[Tuple[str, str, str], List[Dict[str, Any]]] = {}
    for x in en.no_aplicables:
        grupos.setdefault((x["experimento"], x["proveedor"], x["modelo"]), []).append(x)
    omitidas = []
    for (exp, prov, mod), xs in sorted(grupos.items()):
        tareas = len({x["tarea"] for x in xs})
        extra = " (y C+1)" if any(x["brazo"] == "C+1" for x in xs) else ""
        omitidas.append(f"{exp}: brazo C omitido{extra} para {prov}:{mod} (sin modo estructurado declarado) en {tareas} tarea(s)")
    return en.unidades, omitidas


# --------------------------------------------------------------------------
# Almacén JSONL reanudable
# --------------------------------------------------------------------------
class Almacen:
    """``muestras.jsonl`` append-only.

    Una celda queda HECHA cuando su muestra no es reintentable.  Las muestras de
    error reintentable (fallo de red/HTTP tras agotar los reintentos) se conservan
    en el archivo, pero la celda se vuelve a intentar al reanudar y sus intentos
    fallidos se arrastran a la muestra nueva (nada se borra ni se oculta).
    """

    def __init__(self, directorio: Path):
        self.dir = Path(directorio)
        self.dir.mkdir(parents=True, exist_ok=True)
        self.muestras = self.dir / "muestras.jsonl"
        self.fallos = self.dir / "fallos.jsonl"
        self.ids: set = set()
        self.errores_finales: set = set()      # celdas cuya muestra es un error técnico definitivo (no reintentable)
        self.bases: Dict[str, Dict[str, Any]] = {}
        self.previos: Dict[str, List[Dict[str, Any]]] = {}
        self.costo_incremental = Decimal(0)
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
        sid = s["id"]
        intentos = (s.get("solicitud") or {}).get("intentos") or []
        if s.get("reintentable"):
            self.previos[sid] = [i for i in intentos if not i.get("compartido_con")]
            self.ids.discard(sid)
            return
        self.ids.add(sid)
        self.previos.pop(sid, None)
        if s.get("desenlace") == "error_tecnico":
            self.errores_finales.add(sid)
        else:
            self.errores_finales.discard(sid)
        if s.get("brazo") in B.GENERADORES:
            r = s.get("respuesta") or {}
            self.bases[sid] = {"text": r.get("text"), "stop_reason": r.get("stop_reason"), "model": r.get("model"),
                               "intentos": intentos, "latencia": s.get("latencia") or {},
                               "desenlace": s.get("desenlace"), "costo_usd": s.get("costo_usd"),
                               "input_tokens": r.get("input_tokens"), "output_tokens": r.get("output_tokens"),
                               "latency_ms": r.get("latency_ms")}
        self.costo_incremental += Decimal(str(s.get("costo_incremental_usd") or 0))

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
    """Muestras del archivo; si una celda aparece varias veces (reintentos) queda la última."""
    por_id: Dict[str, Dict[str, Any]] = {}
    if not Path(path).exists():
        return []
    with open(path, "r", encoding="utf-8") as fh:
        for linea in fh:
            try:
                s = json.loads(linea)
            except ValueError:
                continue
            por_id.pop(s.get("id"), None)       # la versión nueva pasa al final, conservando el orden de ejecución
            por_id[s.get("id")] = s
    return list(por_id.values())


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
        return SimuladorArnes(model=m["modelo"], oracle=oraculo, profile=m.get("perfil_simulado", "medio"),
                              seed=semilla, structured=estructurado)
    # Los reintentos los hace el arnés (cada uno se anota y se proyecta contra el tope): se desactivan los del adaptador.
    return get_adapter(m["proveedor"], m["modelo"], structured=estructurado, retries=0, max_retries=0,
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


def clasificar_desenlace(proveedor: str, r: Optional[Dict[str, Any]], lectura: Optional[B.Lectura], truncado: bool) -> str:
    """ok | formato_invalido | vacia | truncada | negativa | error_tecnico (en este orden de prioridad)."""
    if r is None:
        return "error_tecnico"
    if es_negativa(proveedor, r):
        return "negativa"
    if not (r.get("text") or "").strip():
        return "vacia"
    if truncado:
        return "truncada"
    if lectura is None or not lectura.parseable or lectura.avisos:
        return "formato_invalido"
    return "ok"


def sumar_costos(intentos: List[Dict[str, Any]]) -> Tuple[Optional[Decimal], str]:
    """Costo total (USD) de una lista de intentos y su estado.

    Un intento fallido sin usage cuesta 0 (el proveedor no lo facturó) salvo que su
    costo sea incierto; uno con respuesta pero sin tarifa verificada hace el total
    ``None`` ("tarifa no verificada").
    """
    total = Decimal(0)
    estado = "calculado"
    for i in intentos:
        if i.get("estado") == "error":
            if i.get("costo_incierto"):
                estado = "incierto"
            continue
        if i.get("costo_usd") is None:
            return None, ("sin_usage" if i.get("usage") is None else "tarifa no verificada")
        total += Decimal(i["costo_usd"])
    return total, estado


class Ejecutor:
    def __init__(self, cfg: Dict[str, Any], ctx: Contexto, modo: str, salida: Path, tarifas: Optional[Tarifas] = None,
                 max_costo: Optional[float] = None, adaptadores: Optional[Dict[Tuple[str, str], Adapter]] = None,
                 autorizacion: Optional[Autorizacion] = None, dormir: Callable[[float], None] = time.sleep,
                 reloj: Optional[Callable[[], float]] = None):
        if modo not in ("simulado", "real"):
            raise ValueError(f"modo desconocido: {modo}")
        if modo == "real" and autorizacion is None:
            raise ErrorAutorizacion(["el adaptador real exige una Autorizacion (presupuesto autorizado, tope, tarifas "
                                     "verificadas y claves); ninguna llamada se hace sin ella"])
        self.cfg, self.ctx, self.modo = cfg, ctx, modo
        self.tarifas = tarifas if tarifas is not None else Tarifas()
        self.autorizacion = autorizacion
        pres = Presupuesto.desde_config(cfg)
        tope = autorizacion.tope_usd if autorizacion is not None else (Decimal(str(max_costo)) if max_costo is not None else None)
        self.almacen = Almacen(salida)
        self.libro = Libro(Path(salida) / "libro.jsonl", tope, pres.por_celda_max_usd)
        self.proyecta = tope is not None or pres.por_celda_max_usd is not None
        self.oraculo = Oraculo() if modo == "simulado" else None
        self.adaptadores = adaptadores or {}
        self.rep_cfg = cfg.get("reparacion", {})
        self.ctl = cfg.get("controles") or {}
        self.fallos_seguidos = 0
        self.detener: Optional[str] = None
        self._dormir = dormir
        # En simulado los tiempos locales (validación, entrega) no se miden: el reloj es constante para que el piloto sea
        # reproducible bit a bit; la latencia de API ya es sintética y va marcada como simulada.
        self._reloj = reloj if reloj is not None else (time.perf_counter if modo == "real" else (lambda: 0.0))

    # -- adaptadores ---------------------------------------------------------
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

    # -- detención -------------------------------------------------------------
    def solicitar_detencion(self, senal: str = "SIGINT") -> None:
        """Pide parar al terminar la llamada en curso (la segunda petición interrumpe de inmediato)."""
        if self.detener is not None:
            raise KeyboardInterrupt
        self.detener = senal

    @contextmanager
    def manejar_senales(self) -> Iterator[None]:
        """SIGINT/SIGTERM: la primera pide parada ordenada; la segunda interrumpe la llamada en vuelo."""
        previos: Dict[int, Any] = {}

        def _h(signum, frame):  # noqa: ANN001
            self.solicitar_detencion(signal.Signals(signum).name)
            log.warning("señal %s: se detendrá al terminar la llamada en curso (otra señal interrumpe ya)",
                        signal.Signals(signum).name)
        try:
            for s in (signal.SIGINT, signal.SIGTERM):
                previos[s] = signal.signal(s, _h)
        except ValueError:          # no es el hilo principal
            previos = {}
        try:
            yield
        finally:
            for s, h in previos.items():
                signal.signal(s, h)

    # -- llamada con controles -----------------------------------------------------
    def _cota_tokens_entrada(self, prov: str, system: str, user: str) -> int:
        factor = float((self.cfg.get("estimacion") or {}).get("factor_tokenizador", {}).get(prov, FACTOR_TOKENIZADOR.get(prov, 1.3)))
        return int((count_tokens(system) + count_tokens(user) + 10) * factor) + 1

    def _llamar(self, u: Unidad, celda: str, fase: str, system: str, user: str, max_tokens: int,
                temperatura: Optional[float], response_format: Optional[Dict[str, Any]], semilla: Optional[int],
                gasto_celda: Decimal) -> Tuple[Optional[Dict[str, Any]], List[Dict[str, Any]], Optional[AdapterError]]:
        """Una llamada con proyección previa, libro, reintentos y registro de cada intento.

        Devuelve ``(respuesta | None, intentos, error_final | None)``.  Lanza ``PresupuestoExcedido`` si la
        proyección supera el tope ANTES de llamar, y ``MissingKeyError`` si falta la clave.
        """
        ad = self.adaptador(u.proveedor, u.modelo)
        tarifa = self.tarifas.obtener(u.proveedor, u.modelo)
        # la cota solo se calcula cuando se usa (proyección o modo real): tokenizar cada prompt no es gratis
        peor = (costo_peor_caso(tarifa, self._cota_tokens_entrada(u.proveedor, system, user), max_tokens)
                if (self.proyecta or self.modo == "real") else None)
        proveedor_usage = "simulado" if self.modo == "simulado" else u.proveedor
        reintentos = int(self.ctl.get("reintentos_por_llamada", 2))
        intentos: List[Dict[str, Any]] = []
        for k in range(reintentos + 1):
            if self.proyecta:
                motivo = self.libro.proyectar(peor, gasto_celda)
                if motivo:
                    raise PresupuestoExcedido(motivo)
            lid = self.libro.iniciar(celda, fase, peor)
            t0 = self._reloj()
            try:
                r = ad.generate(system, user, max_tokens=max_tokens, temperature=temperatura,
                                response_format=response_format, seed=semilla)
            except MissingKeyError:
                self.libro.terminar(lid, ok=False, costo=None, nota="clave ausente")
                raise
            except KeyboardInterrupt:
                self.libro.terminar(lid, ok=False, costo=None, incierto=peor or Decimal(0), nota="interrumpida en vuelo")
                raise
            except AdapterError as e:
                lat = self._reloj() - t0
                incierto = peor if (e.status is None and peor is not None) else Decimal(0)
                self.libro.terminar(lid, ok=False, costo=None, incierto=incierto, nota=redact(e)[:200])
                gasto_celda += incierto
                intentos.append({"fase": fase, "modelo": u.modelo, "proveedor": u.proveedor, "latencia_s": round(lat, 4),
                                 "usage": None, "estado": "error", "error": redact(e)[:300], "status": e.status,
                                 "costo_usd": None, "costo_incierto": bool(incierto), "llamada": lid})
                self.almacen.fallo({"id": celda, "fecha": _ahora(), "fase": fase, "error": redact(e)[:300], "status": e.status})
                log.warning("fallo en %s (%s, intento %d): %s", celda, fase, k + 1, redact(e)[:200])
                if e.retryable and k < reintentos:
                    self._dormir(min(30.0, 2.0 ** k))
                    continue
                return None, intentos, e
            usage = usage_de_respuesta(proveedor_usage, r)
            costo = costo_usage(tarifa, usage)
            incierto = Decimal(0)
            if costo is None and self.modo == "real":
                incierto = peor or Decimal(0)        # respuesta sin usage utilizable: se cuenta el peor caso
            self.libro.terminar(lid, ok=True, costo=costo, incierto=incierto)
            gasto_celda += costo or incierto
            intentos.append({"fase": fase, "modelo": u.modelo, "proveedor": u.proveedor,
                             "latencia_s": round(float(r["latency_ms"] or 0.0) / 1000.0, 4), "usage": usage,
                             "estado": "ok", "error": None, "status": None, "stop_reason": r.get("stop_reason"),
                             "costo_usd": decimal_a_texto(costo), "llamada": lid})
            return r, intentos, None
        raise AssertionError("inalcanzable")  # pragma: no cover

    # -- bucle de celdas ----------------------------------------------------------
    def correr(self, unidades: List[Unidad], limite: Optional[int] = None) -> Dict[str, Any]:
        res: Dict[str, Any] = {"ejecutadas": 0, "saltadas": 0, "fallos": 0, "abortado": None, "interrumpido": None,
                               "bloqueadas": 0}
        try:
            with self.manejar_senales():
                for u in unidades:
                    if self.detener:
                        res["interrumpido"] = self.detener
                        break
                    if u.id in self.almacen.ids:
                        res["saltadas"] += 1
                        continue
                    if limite is not None and res["ejecutadas"] >= limite:
                        break
                    if B.es_reparacion(u.brazo):
                        base = self.almacen.bases.get(u.id_brazo(B.base_de(u.brazo)))
                        if base is None or base.get("text") is None:
                            res["bloqueadas"] += 1           # su base no tiene respuesta: se reintentará junto con ella
                            continue
                    try:
                        s = self.ejecutar(u)
                    except MissingKeyError as e:
                        res["abortado"] = f"clave ausente: {e}"
                        break
                    except PresupuestoExcedido as e:
                        res["abortado"] = f"presupuesto: {e}"
                        break
                    self.almacen.agregar(s)
                    res["ejecutadas"] += 1
                    if s.get("desenlace") == "error_tecnico" or s.get("reparacion_estado") == "error_tecnico":
                        res["fallos"] += 1
                        self.fallos_seguidos += 1
                        if self.fallos_seguidos >= int(self.cfg.get("max_fallos_seguidos", self.ctl.get("max_fallos_seguidos", 5))):
                            res["abortado"] = f"{self.fallos_seguidos} fallos seguidos"
                            break
                    else:
                        self.fallos_seguidos = 0
        except KeyboardInterrupt:
            res["interrumpido"] = self.detener or "SIGINT"
        if self.detener and not res["interrumpido"]:
            res["interrumpido"] = self.detener
        res["costo_acumulado_usd"] = float(self.libro.gastado)
        res["gasto"] = self.libro.resumen()
        return res

    # -- estudio completo: estado persistido ---------------------------------------------
    def _contadores(self, en: "Enumeracion", res: Optional[Dict[str, Any]], limite: Optional[int]) -> Tuple[Dict[str, int], List[Dict[str, Any]]]:
        """Recuento de celdas por estado y lista de celdas faltantes con su motivo."""
        res = res or {}
        inicial = bool(res.get("inicial"))
        faltantes: List[Dict[str, Any]] = [dict(estado="no_aplicable", id=x["id"], motivo=x["motivo"]) for x in en.no_aplicables]
        c = {k: 0 for k in ESTADOS_CELDA}
        c["no_aplicable"] = len(en.no_aplicables)
        for u in en.unidades:
            if u.id in self.almacen.ids:
                if u.id in self.almacen.errores_finales:
                    c["error_tecnico"] += 1
                else:
                    c["hecha"] += 1
                continue
            base_sin_texto = (B.es_reparacion(u.brazo)
                              and self.almacen.bases.get(u.id_brazo(B.base_de(u.brazo)), {}).get("text") is None)
            if base_sin_texto and not res.get("interrumpido"):
                estado, motivo = "bloqueado", "su celda base no tiene respuesta (se reintentará con ella)"
            elif inicial:
                estado, motivo = "pendiente", "aún no ejecutada"
            elif res.get("abortado"):
                estado, motivo = "bloqueado", str(res["abortado"])
            elif res.get("interrumpido"):
                estado, motivo = "pendiente", f"interrupción ({res['interrumpido']})"
            elif limite is not None:
                estado, motivo = "pendiente", f"no se llegó a ejecutar (--limite {limite})"
            else:
                estado, motivo = "pendiente", "error reintentable: se reintenta al reanudar"
            c[estado] += 1
            faltantes.append({"estado": estado, "id": u.id, "motivo": motivo})
        return c, faltantes

    def ejecutar_estudio(self, en: "Enumeracion", limite: Optional[int] = None,
                         estado_obj: Optional[EstadoEstudio] = None) -> Dict[str, Any]:
        """Ejecuta las celdas y persiste ``estado_estudio.json`` y ``celdas_faltantes.jsonl`` (también si se interrumpe o aborta)."""
        estado_obj = estado_obj or EstadoEstudio(self.almacen.dir)
        inicio = _ahora()
        c0, f0 = self._contadores(en, {"inicial": True}, None)
        estado_obj.escribir(estado="en_curso", motivo="", fecha_inicio=inicio, fecha=_ahora(), contadores=c0,
                            gasto=self.libro.resumen(), orden_semilla=en.orden_semilla, modo=self.modo,
                            interrupcion=None, faltantes=f0)
        res: Dict[str, Any] = {}
        try:
            res = self.correr(en.unidades, limite=limite)
        finally:
            c, faltantes = self._contadores(en, res, limite)
            if res.get("interrumpido"):
                estado = "interrumpido"
            elif res.get("abortado"):
                estado = "abortado"
            elif c["pendiente"] or c["bloqueado"]:
                estado = "parcial"
            else:
                estado = "completo"
            res["estado"] = estado
            res["celdas"] = c
            estado_obj.escribir(estado=estado, motivo=str(res.get("abortado") or res.get("interrumpido") or ""),
                                fecha_inicio=inicio, fecha=_ahora(), contadores=c, gasto=self.libro.resumen(),
                                orden_semilla=en.orden_semilla, modo=self.modo,
                                interrupcion=({"senal": res["interrumpido"], "fecha_utc": _ahora()} if res.get("interrumpido") else None),
                                faltantes=faltantes)
        return res

    # -- una celda --------------------------------------------------------------
    def _registrar_objetivo(self, t: T.Tarea, brazo: str, p: B.Prompt) -> None:
        if self.oraculo is None:
            return
        self.oraculo.registrar(p.system, p.user, SimTarget(kind=B.tipo_objetivo_simulado(brazo), contract=t.contrato,
                                                           records=t.registros, header=t.cabecera))

    def _base_muestra(self, u: Unidad, t: T.Tarea) -> Dict[str, Any]:
        semilla = semilla_muestra(int(self.cfg["semilla"]), u.id)
        return {"id": u.id, "esquema_muestra": VERSION_ESQUEMA_MUESTRA, "experimento": u.experimento, "tarea": u.tarea,
                "tipo_tarea": t.tipo, "prefijo": t.prefijo, "dominio": t.dominio, "brazo": u.brazo,
                "proveedor": u.proveedor, "modelo": u.modelo, "repeticion": u.rep, "adaptador": self.modo,
                "procedencia": "simulado" if self.modo == "simulado" else "api_real",
                "simulado": self.modo == "simulado", "semilla": semilla, "temperatura": self._temperatura(u),
                "max_tokens": u.max_tokens, "fecha": _ahora()}

    def ejecutar(self, u: Unidad) -> Dict[str, Any]:
        t = self.ctx.tareas[u.tarea]
        base = self._base_muestra(u, t)
        if B.es_reparacion(u.brazo):
            return self._ejecutar_reparacion(u, t, base)
        p = self.ctx.prompt(t, u.brazo)
        self._registrar_objetivo(t, u.brazo, p)
        previos = list(self.almacen.previos.get(u.id, []))
        r, intentos, err = self._llamar(u, u.id, "generacion", p.system, p.user, u.max_tokens, base["temperatura"],
                                        p.response_format, base["semilla"], Decimal(0))
        todos = previos + intentos
        if r is None:
            return self._muestra_error(u, t, base, p, todos, err)
        t0 = self._reloj()
        lectura = B.leer(u.brazo, r["text"], t)
        met = M.evaluar(lectura, t)
        t_val = self._reloj() - t0
        t0 = self._reloj()
        json.dumps(lectura.registros, ensure_ascii=False, default=str)       # «entrega»: materializar lo que recibe el consumidor
        t_ent = self._reloj() - t0
        truncado = r.get("stop_reason") in STOP_TRUNCADO
        proveedor_u = "simulado" if self.modo == "simulado" else u.proveedor
        desenlace = clasificar_desenlace(proveedor_u, r, lectura, truncado)
        costo, est_costo = sumar_costos(todos)
        met.update({"tokens_entrada": r["input_tokens"], "tokens_salida": r["output_tokens"],
                    "latencia_ms": r["latency_ms"], "truncado": truncado,
                    "llamadas": 1, "llamadas_reparacion": 0, "tokens_reparacion_entrada": 0,
                    "tokens_reparacion_salida": 0})
        lat_gen = sum(i["latencia_s"] or 0.0 for i in todos if i["fase"] == "generacion")
        s = {**base, "prompt": {"system": p.system, "user": p.user, "response_format": p.response_format},
             "respuesta": _respuesta_serializable(r), "reparacion": None,
             "lectura": {"avisos": lectura.avisos[:50], "n_declarado": lectura.n_declarado},
             "desenlace": desenlace, "metricas": met,
             "solicitud": self._solicitud(u, t, u.id, met, todos),
             "latencia": self._latencia(lat_gen, t_val, 0.0, t_ent),
             "costo_usd": decimal_a_texto(costo), "costo_estado": self._estado_costo(est_costo),
             "costo_incremental_usd": decimal_a_texto(costo), "costo_nocional": self.modo == "simulado",
             "reintentable": False}
        if u.experimento == "v3b":
            s["v3b"] = {"limite_salida": u.max_tokens, "stop_reason": r.get("stop_reason"), "truncada": truncado,
                        "usage": intentos[-1]["usage"], "respuesta_bruta": r.get("text")}
        return s

    def _estado_costo(self, est: str) -> str:
        return "nocional" if (self.modo == "simulado" and est == "calculado") else est

    def _solicitud(self, u: Unidad, t: T.Tarea, grupo: str, met: Dict[str, Any], intentos: List[Dict[str, Any]],
                   finales: Optional[int] = None) -> Dict[str, Any]:
        return {"id": u.id, "grupo": grupo, "brazo": u.brazo, "celda": u.id,
                "registros_solicitados": met["solicitados"],
                "registros_validos_finales": met["validos_finales"] if finales is None else finales,
                "intentos": intentos}

    def _latencia(self, gen_s: float, val_s: float, rep_s: float, ent_s: float) -> Dict[str, Any]:
        return {"generacion_s": round(gen_s, 4), "validacion_s": round(val_s, 6), "reparacion_s": round(rep_s, 4),
                "entrega_s": round(ent_s, 6), "flujo_s": round(gen_s + val_s + rep_s + ent_s, 4),
                "origen_api": "simulada" if self.modo == "simulado" else "medida", "concurrencia": 1}

    def _muestra_error(self, u: Unidad, t: T.Tarea, base: Dict[str, Any], p: Optional[B.Prompt],
                       intentos: List[Dict[str, Any]], err: Optional[AdapterError], fase_reparacion: bool = False) -> Dict[str, Any]:
        """Muestra de una celda cuya llamada falló tras agotar los reintentos: se CONSERVA con su clasificación."""
        n = t.n
        met = {"parseable": False, "avisos": 0, "detectado": True, "aceptados": 0, "sintaxis_ok": False, "esperados": n,
               "correctos": 0, "incorrectos_emparejados": 0, "espurios": 0, "incorrectos_sin_aviso": 0, "perdidos": n,
               "perdidos_detectados": n, "perdidos_sin_aviso": 0, "campos_correctos": 0 if t.tipo == "extraccion" else None,
               "campos_totales": None, "exacto": False, "solicitados": n, "validos_contrato": 0, "validos_finales": 0,
               "excedentes": 0, "identidades_duplicadas": 0, "exactos_contenido": 0 if t.tipo == "extraccion" else None,
               "tokens_entrada": None, "tokens_salida": None, "latencia_ms": None, "truncado": False, "llamadas": 0,
               "llamadas_reparacion": 0, "tokens_reparacion_entrada": 0, "tokens_reparacion_salida": 0}
        costo, est = sumar_costos(intentos)
        reintentable = bool(err is not None and err.retryable)
        posible_na = bool(B.base_de(u.brazo) == "C" and err is not None and err.status in (400, 422))
        lat = sum(i["latencia_s"] or 0.0 for i in intentos)
        return {**base, "prompt": None if p is None else {"system": p.system, "user": p.user, "response_format": p.response_format},
                "respuesta": {"text": None, "input_tokens": None, "output_tokens": None, "latency_ms": None,
                              "stop_reason": None, "model": None, "provider": u.proveedor, "raw": None,
                              "error": redact(err)[:300] if err else None, "status": err.status if err else None},
                "reparacion": None, "lectura": {"avisos": [], "n_declarado": None}, "desenlace": "error_tecnico",
                "metricas": met, "solicitud": self._solicitud(u, t, u.id, met, intentos, finales=0),
                "latencia": self._latencia(lat, 0.0, 0.0, 0.0), "costo_usd": decimal_a_texto(costo),
                "costo_estado": self._estado_costo(est), "costo_incremental_usd": decimal_a_texto(costo),
                "costo_nocional": self.modo == "simulado", "reintentable": reintentable,
                "posible_no_aplicable": posible_na}

    # -- reparación (X+1) ---------------------------------------------------------------
    def _ejecutar_reparacion(self, u: Unidad, t: T.Tarea, base: Dict[str, Any]) -> Dict[str, Any]:
        brazo_base = B.base_de(u.brazo)
        base_id = u.id_brazo(brazo_base)
        gen = self.almacen.bases[base_id]
        formato = B.formato_de(u.brazo)
        p = self.ctx.prompt(t, brazo_base)
        max_rondas = int(self.rep_cfg.get("max_rondas", 1))
        factor = float(self.rep_cfg.get("max_tokens_factor", 2.0))
        temp_rep = self.rep_cfg.get("temperatura", 0.0)
        if not self._modelo_cfg(u).get("enviar_temperatura", True):
            temp_rep = None
        contexto = t.texto_entrada if (self.rep_cfg.get("incluir_entrada", False) and t.tipo == "extraccion") else None
        texto0 = gen["text"] or ""
        texto = texto0
        rondas: List[Dict[str, Any]] = []
        intentos: List[Dict[str, Any]] = [dict(i, compartido_con=base_id) for i in gen["intentos"]]
        intentos_rep: List[Dict[str, Any]] = list(self.almacen.previos.get(u.id, []))
        tin = tout = 0
        t_rep = 0.0
        gasto_celda = Decimal(0)
        err: Optional[AdapterError] = None
        items_json: Optional[List[J.ItemJSON]] = None
        sol_inicial: Optional[RP.Solicitud] = None
        res_final: Optional[RP.Resultado] = None
        rechazos = 0
        for k in range(max_rondas):
            t0 = self._reloj()
            sol = RP.solicitar(formato, texto, t, p, self.ctx.idioma, contexto, brazo_base, items_json)
            t_rep += self._reloj() - t0
            if not sol.needed:
                break
            if sol_inicial is None:
                sol_inicial = sol
            if self.oraculo is not None:
                if formato == "mini":
                    self.oraculo.registrar(sol.system, sol.user, SimTarget(
                        kind="repair", contract=t.contrato, records=t.registros, header=t.cabecera,
                        repair_items=[(it.text, it.is_header) for it in sol.raw.items], repair_context=contexto is not None))
                else:
                    self.oraculo.registrar(sol.system, sol.user, SimTarget(
                        kind="repair_json", contract=t.contrato, records=t.registros, header=t.cabecera,
                        repair_items=[(x, False) for x in sol.textos], repair_context=contexto is not None))
            mt = max(256, int(sol.max_tokens_hint * factor))
            rr, nuevos, err = self._llamar(u, u.id, "reparacion", sol.system, sol.user, mt, temp_rep,
                                           sol.response_format if formato == "json" else None,
                                           semilla_muestra(base["semilla"], f"reparacion{k}"), gasto_celda)
            for i in nuevos:
                gasto_celda += Decimal(i["costo_usd"] or 0)
            intentos_rep += nuevos
            if rr is None:
                break
            t0 = self._reloj()
            res = RP.fusionar(sol, texto, rr, t, _respuesta_serializable(rr), mt)
            t_rep += self._reloj() - t0
            rondas.append(res.ronda)
            texto, res_final, items_json = res.texto, res, res.items_json
            rechazos += res.rechazos_identidad
            tin += rr["input_tokens"] or 0
            tout += rr["output_tokens"] or 0
            if res.ok or not res.progreso:
                break
        t0 = self._reloj()
        lectura = B.leer(u.brazo, texto, t)
        if formato == "json" and res_final is not None and res_final.sin_resolver_json:
            lectura.avisos = list(lectura.avisos) + [f"objeto {p_} sin resolver" for p_ in res_final.sin_resolver_json]
        met = M.evaluar(lectura, t)
        t_val = self._reloj() - t0
        t0 = self._reloj()
        json.dumps(lectura.registros, ensure_ascii=False, default=str)
        t_ent = self._reloj() - t0
        auditoria = None
        if sol_inicial is not None and rondas:
            auditoria = RP.auditar(sol_inicial, texto0, texto, t, rechazos, lectura.registros if lectura.parseable else [])
        todos_intentos = intentos + intentos_rep
        costo_total, est_total = sumar_costos(todos_intentos)
        costo_rep, _ = sumar_costos(intentos_rep)
        truncado = gen["stop_reason"] in STOP_TRUNCADO
        met.update({"tokens_entrada": (gen.get("input_tokens") or 0) + tin, "tokens_salida": (gen.get("output_tokens") or 0) + tout,
                    "latencia_ms": round((gen.get("latency_ms") or 0.0) + sum((i["latencia_s"] or 0) * 1000 for i in intentos_rep if i["estado"] == "ok"), 1),
                    "truncado": truncado, "llamadas": 1 + len(rondas), "llamadas_reparacion": len(rondas),
                    "tokens_reparacion_entrada": tin, "tokens_reparacion_salida": tout})
        lat_gen = sum(i["latencia_s"] or 0.0 for i in intentos if i["fase"] == "generacion")
        lat_rep = sum(i["latencia_s"] or 0.0 for i in intentos_rep) + t_rep
        lat_val = (gen.get("latencia") or {}).get("validacion_s", 0.0) + t_val
        estado_rep = RP.estado_reparacion(rondas, err is not None)
        reintentable = bool(err is not None and err.retryable)
        s = {**base, "prompt": None, "generacion_de": base_id,
             "respuesta": {"text": gen["text"], "input_tokens": gen.get("input_tokens"), "output_tokens": gen.get("output_tokens"),
                           "latency_ms": gen.get("latency_ms"), "stop_reason": gen["stop_reason"], "model": gen.get("model")},
             "reparacion": {"rondas": rondas, "documento_final": texto, "formato": formato, "estado": estado_rep,
                            "auditoria": auditoria},
             "reparacion_estado": estado_rep,
             "lectura": {"avisos": lectura.avisos[:50], "n_declarado": lectura.n_declarado},
             "desenlace": gen.get("desenlace"), "metricas": met,
             "solicitud": self._solicitud(u, t, base_id, met, todos_intentos),
             "latencia": self._latencia(lat_gen, lat_val, lat_rep, t_ent),
             "costo_usd": decimal_a_texto(costo_total), "costo_estado": self._estado_costo(est_total),
             "costo_incremental_usd": decimal_a_texto(costo_rep), "costo_nocional": self.modo == "simulado",
             "reintentable": reintentable}
        if u.experimento == "v3b":
            s["v3b"] = {"limite_salida": u.max_tokens, "stop_reason": gen["stop_reason"], "truncada": truncado,
                        "usage": next((i["usage"] for i in intentos if i["fase"] == "generacion" and i["estado"] == "ok"), None),
                        "respuesta_bruta": gen["text"]}
        return s
