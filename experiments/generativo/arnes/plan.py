"""Plan de celdas, manifiesto con hashes, estado del estudio y candado de directorio.

* ``orden_aleatorizado``: el orden de ejecución se baraja con una semilla
  REGISTRADA (evita que el sesgo por caché automática o por deriva temporal del
  proveedor coincida con un brazo); cada brazo de reparación va justo detrás de
  su base.
* ``Manifiesto``: congela config, prompts, contratos, referencias, tarifas y
  código del arnés con hashes SHA-256.  Reanudar con un diseño distinto se
  rechaza salvo ``--nueva-version MOTIVO`` (queda registrado en ``versiones.jsonl``).
* ``EstadoEstudio``: ``estado_estudio.json`` (en_curso / completo / interrumpido /
  abortado) y ``celdas_faltantes.jsonl`` con el motivo de cada celda no hecha
  (pendiente / bloqueado / no_aplicable).
* ``Candado``: un solo proceso por directorio de resultados.
"""
from __future__ import annotations

import hashlib
import json
import os
import random
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence

from . import brazos as B

VERSION_ESQUEMA_MUESTRA = 2
ESTADOS_CELDA = ("hecha", "pendiente", "bloqueado", "no_aplicable", "error_tecnico")


def sha256_texto(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def json_estable(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


# --------------------------------------------------------------------------
# Orden aleatorizado
# --------------------------------------------------------------------------
def semilla_orden(cfg: Dict[str, Any]) -> int:
    ctl = cfg.get("controles") or {}
    if ctl.get("semilla_orden") is not None:
        return int(ctl["semilla_orden"])
    return int(sha256_texto(f"{cfg.get('semilla', 0)}|orden")[:8], 16)


def orden_aleatorizado(unidades: Sequence[Any], semilla: int, barajar: bool = True) -> List[Any]:
    """Baraja las celdas de generación; cada brazo de reparación sigue a su base (mismo experimento, tarea, modelo y repetición)."""
    bases = [u for u in unidades if not B.es_reparacion(u.brazo)]
    reparaciones: Dict[str, List[Any]] = {}
    for u in unidades:
        if B.es_reparacion(u.brazo):
            reparaciones.setdefault(u.id_brazo(B.base_de(u.brazo)), []).append(u)
    if barajar:
        random.Random(semilla).shuffle(bases)
    out: List[Any] = []
    for b in bases:
        out.append(b)
        out.extend(reparaciones.pop(b.id, []))
    for resto in reparaciones.values():       # reparaciones cuya base no está en la matriz (no debería ocurrir)
        out.extend(resto)
    return out


# --------------------------------------------------------------------------
# Hashes del diseño
# --------------------------------------------------------------------------
def _hash_prompt(p: B.Prompt) -> str:
    return sha256_texto(p.system + "\x00" + p.user + "\x00" + json_estable(p.response_format))


def hashes_diseno(cfg: Dict[str, Any], ctx: Any, unidades: Sequence[Any], no_aplicables: Sequence[Dict[str, Any]],
                  tarifas: Any, raiz: Path) -> Dict[str, Any]:
    """Hashes que identifican el diseño: si cambian, los resultados anteriores ya no son comparables."""
    cfg_sin_presupuesto = {k: v for k, v in cfg.items() if k != "presupuesto"}
    prompts: Dict[str, str] = {}
    for t_id in sorted({u.tarea for u in unidades}):
        t = ctx.tareas[t_id]
        for b in sorted({B.base_de(u.brazo) for u in unidades if u.tarea == t_id}):
            prompts[f"{t_id}/{b}"] = _hash_prompt(ctx.prompt(t, b))
    contratos, conjuntos = [], []
    for t_id in sorted({u.tarea for u in unidades}):
        t = ctx.tareas[t_id]
        fork = raiz / "forks" / t.prefijo
        for nombre, ruta, lista in (("contract.json", fork / "contract.json", contratos),
                                    ("canonical.json", fork / "fixtures" / "canonical.json", conjuntos)):
            if ruta.exists():
                rel = ruta.resolve().relative_to(raiz.resolve()).as_posix()
                entrada = {"ruta": rel, "sha256": hashlib.sha256(ruta.read_bytes()).hexdigest()}
                if lista is contratos:
                    entrada["prefijo"] = t.prefijo
                else:
                    entrada.update({"nombre": f"{t.prefijo}/canonical.json", "sintetico": True,
                                    "fuente": "fixtures del fork publicado en forks/ (datos de referencia versionados)"})
                if entrada not in lista:
                    lista.append(entrada)
    codigo = {}
    for nombre in ("brazos.py", "json_tolerante.py", "metricas.py", "ejecucion.py", "tareas.py", "usage.py", "tarifas.py"):
        p = Path(__file__).resolve().parent / nombre
        if p.exists():
            codigo[nombre] = hashlib.sha256(p.read_bytes().replace(b"\r\n", b"\n")).hexdigest()
    nucleo = {}
    for nombre in ("parser.py", "values.py", "codec.py", "serializer.py", "contract.py", "prompt.py", "ai/repair.py"):
        p = raiz / "src" / "minifmt" / nombre
        if p.exists():
            nucleo[nombre] = hashlib.sha256(p.read_bytes().replace(b"\r\n", b"\n")).hexdigest()
    orden_ids = [u.id for u in unidades]
    tarifas_usadas = {}
    for m in cfg.get("modelos", []):
        t = tarifas.obtener(m["proveedor"], m["modelo"]) if tarifas is not None else None
        tarifas_usadas[f"{m['proveedor']}:{m['modelo']}"] = (t.resumen() if t else {"estado": "ausente"})
    limites = {u.id: u.max_tokens for u in unidades}
    diseno = {"config": cfg_sin_presupuesto, "prompts": prompts, "contratos": contratos, "conjuntos": conjuntos,
              "celdas": sorted(orden_ids), "limites": limites, "no_aplicables": sorted(x["id"] for x in no_aplicables),
              "codigo_arnes": codigo, "nucleo": nucleo}
    return {"config_sha256": sha256_texto(json_estable(cfg_sin_presupuesto)),
            "prompts_sha256": sha256_texto(json_estable(prompts)), "prompts": prompts,
            "contratos": contratos, "conjuntos": conjuntos,
            "celdas_sha256": sha256_texto(json_estable(sorted(orden_ids))),
            "limites_sha256": sha256_texto(json_estable(limites)),
            "orden_sha256": sha256_texto(json_estable(orden_ids)),
            "codigo_arnes_sha256": codigo, "nucleo_minifmt_sha256": nucleo,
            "tarifas": {"archivo": getattr(tarifas, "origen", None), "sha256": getattr(tarifas, "sha256", None),
                        "por_modelo": tarifas_usadas},
            "diseno_sha256": sha256_texto(json_estable(diseno))}


class ErrorReanudacion(RuntimeError):
    pass


def verificar_reanudacion(dir_salida: Path, adaptador: str, hashes: Dict[str, Any], nueva_version: Optional[str]) -> Optional[str]:
    """Compara con el manifiesto previo. Devuelve el hash previo si hubo cambio autorizado; lanza ErrorReanudacion si no."""
    previo = dir_salida / "manifiesto.json"
    if not previo.exists():
        return None
    try:
        m = json.loads(previo.read_text(encoding="utf-8"))
    except ValueError as e:
        raise ErrorReanudacion(f"manifiesto.json ilegible en {dir_salida}: {e}") from None
    if m.get("adaptador") != adaptador:
        raise ErrorReanudacion(f"el directorio contiene resultados de otro adaptador ({m.get('adaptador')!r}); "
                               f"no se mezclan con {adaptador!r}: use otro --salida")
    viejo = (m.get("hashes") or {}).get("diseno_sha256")
    if viejo and viejo != hashes["diseno_sha256"]:
        if not nueva_version:
            raise ErrorReanudacion("el diseño cambió respecto al manifiesto existente (config, prompts, contratos, celdas o "
                                   "código del arnés); para continuar declare el motivo con --nueva-version \"...\"")
        return viejo
    return None


def escribir_manifiesto(dir_salida: Path, manifiesto: Dict[str, Any], hash_previo: Optional[str],
                        nueva_version: Optional[str], fecha: str) -> None:
    dir_salida.mkdir(parents=True, exist_ok=True)
    destino = dir_salida / "manifiesto.json"
    if hash_previo is not None and destino.exists():
        k = 1
        while (dir_salida / f"manifiesto.v{k}.json").exists():
            k += 1
        (dir_salida / f"manifiesto.v{k}.json").write_text(destino.read_text(encoding="utf-8"), encoding="utf-8")
        with open(dir_salida / "versiones.jsonl", "a", encoding="utf-8") as fh:
            fh.write(json.dumps({"fecha_utc": fecha, "motivo": nueva_version, "diseno_previo_sha256": hash_previo,
                                 "diseno_nuevo_sha256": manifiesto["hashes"]["diseno_sha256"],
                                 "manifiesto_previo": f"manifiesto.v{k}.json"}, ensure_ascii=False) + "\n")
    elif destino.exists():
        return                                     # mismo diseño: el manifiesto no se toca (inmutable)
    destino.write_text(json.dumps(manifiesto, ensure_ascii=False, indent=2), encoding="utf-8")


# --------------------------------------------------------------------------
# Estado y celdas faltantes
# --------------------------------------------------------------------------
class EstadoEstudio:
    def __init__(self, directorio: Path):
        self.dir = Path(directorio)
        self.ruta = self.dir / "estado_estudio.json"
        self.faltantes = self.dir / "celdas_faltantes.jsonl"
        self.reanudaciones = 0
        if self.ruta.exists():
            try:
                self.reanudaciones = int(json.loads(self.ruta.read_text(encoding="utf-8")).get("reanudaciones", 0)) + 1
            except (ValueError, TypeError):
                pass

    def escribir(self, *, estado: str, motivo: str, fecha_inicio: str, fecha: str, contadores: Dict[str, int],
                 gasto: Dict[str, Any], orden_semilla: int, modo: str, interrupcion: Optional[Dict[str, Any]],
                 faltantes: Iterable[Dict[str, Any]] = ()) -> None:
        self.dir.mkdir(parents=True, exist_ok=True)
        datos = {"estado": estado, "motivo": motivo, "adaptador": modo, "inicio_utc": fecha_inicio,
                 "actualizado_utc": fecha, "celdas": contadores, "gasto": gasto, "orden_semilla": orden_semilla,
                 "reanudaciones": self.reanudaciones, "interrupcion": interrupcion}
        tmp = self.ruta.with_suffix(".tmp")
        tmp.write_text(json.dumps(datos, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(tmp, self.ruta)
        with open(self.faltantes, "w", encoding="utf-8") as fh:
            for f in faltantes:
                fh.write(json.dumps(f, ensure_ascii=False) + "\n")


# --------------------------------------------------------------------------
# Candado
# --------------------------------------------------------------------------
class ErrorCandado(RuntimeError):
    pass


class Candado:
    """Un único proceso por directorio de resultados (archivo ``ejecucion.lock`` creado de forma exclusiva)."""

    def __init__(self, directorio: Path, forzar: bool = False):
        self.ruta = Path(directorio) / "ejecucion.lock"
        self.forzar = forzar
        self._fd: Optional[int] = None

    def __enter__(self) -> "Candado":
        self.ruta.parent.mkdir(parents=True, exist_ok=True)
        if self.forzar and self.ruta.exists():
            self.ruta.unlink()
        try:
            self._fd = os.open(str(self.ruta), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            raise ErrorCandado(f"{self.ruta} existe: otro proceso usa este directorio (o terminó sin liberarlo; si está "
                               "seguro de que no hay otro proceso, use --forzar-candado)") from None
        os.write(self._fd, f"pid={os.getpid()}\n".encode("ascii"))
        return self

    def __exit__(self, *exc: Any) -> None:
        if self._fd is not None:
            os.close(self._fd)
            self._fd = None
        try:
            self.ruta.unlink()
        except FileNotFoundError:
            pass
