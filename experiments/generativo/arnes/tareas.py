"""Catálogo de tareas del experimento generativo (V2/V3).

Cada tarea se construye a partir de un fork registrado en ``forks/<prefijo>/``
(contrato + ``fixtures/canonical.json``), de modo que el dominio, el contrato y
los datos de referencia son públicos y reproducibles.

Tipos de tarea
--------------
* ``extraccion`` (``ext-<prefijo>``): el modelo recibe un documento de origen en
  texto (bloques «campo: valor», listas con viñetas, textos multilínea) y debe
  transformarlo en la salida estructurada.  La salida esperada se conoce
  registro a registro.
* ``generativa`` (``gen-<prefijo>``): el modelo genera N registros nuevos del
  dominio; la salida se evalúa contra el contrato (tipos, enumeraciones,
  rangos, aridades, marcadores, unicidad), no contra valores concretos.

Estrés controlado
-----------------
Los textos de los fixtures casi no contienen caracteres conflictivos, así que
cada tarea aplica una transformación determinista que añade fragmentos
realistas con comillas, comas, barras verticales, barras invertidas, saltos de
línea y asteriscos finales a campos de texto natural y a elementos de lista.
Solo se modifican campos ``str`` cuyo valor original contiene un espacio
(texto natural, no identificadores ni fechas) y nunca el primer campo; cada
registro modificado se valida con ida y vuelta (dumps -> parse) contra el
contrato.
"""
from __future__ import annotations

import copy
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from minifmt import Contract, Registry, canonical_equal, dumps, parse
from minifmt.values import format_number

ROOT = Path(__file__).resolve().parents[3]
FORKS = ROOT / "forks"

FRAGMENTOS_TEXTO = [
    ' (ver "Anexo B", sección 2)',
    " | ref. A|B",
    "\nDetalle: segunda línea, con coma",
    " — ruta C:\\datos\\nuevo",
    " *importante*",
]
FRAGMENTOS_LISTA = [', incl. "beta"', " | alt", " (a, b)", "*"]

GENERATIVAS = ["a", "card", "q", "tc", "us", "s", "r", "code"]
TEMAS = {
    "a": "fotosíntesis y respiración celular", "card": "biología celular", "q": "estadística descriptiva",
    "tc": "registro e inicio de sesión de una aplicación web", "us": "plataforma de cursos en línea",
    "s": "satisfacción con una plataforma de estudio", "r": "ensayo argumentativo",
    "code": "listas y bucles en Python",
}


@dataclass
class Tarea:
    id: str
    tipo: str                       # extraccion | generativa
    prefijo: str
    dominio: str
    contrato: Contract
    registros: List[Dict[str, Any]]           # esperados (extracción) o contenido simulado (generativa)
    cabecera: Dict[str, Any]                  # valores de cabecera (sin n)
    ejemplo: Dict[str, Any]                   # registro de ejemplo común a todos los brazos
    texto_entrada: str = ""                   # documento de origen (extracción)
    instruccion: str = ""
    n_solicitados: int = 0
    estres: List[str] = field(default_factory=list)   # trazabilidad de fragmentos insertados

    @property
    def n(self) -> int:
        return self.n_solicitados if self.tipo == "generativa" else len(self.registros)


# --------------------------------------------------------------------------
def _s(v: Any) -> str:
    if v is None:
        return "(vacío)"
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, float):
        return format_number(v)
    return str(v)


def _valido(rec: Dict[str, Any], c: Contract, cabecera: Dict[str, Any]) -> bool:
    try:
        text = dumps({"header": cabecera, c.records_key: [rec]}, c)
        back = parse(text, c).records[0]
    except Exception:  # noqa: BLE001
        return False
    return canonical_equal(back, rec)


def estresar(registros: List[Dict[str, Any]], c: Contract, cabecera: Dict[str, Any]) -> (List[Dict[str, Any]], List[str]):
    out, traza = [], []
    kt = kl = 0
    for i, rec in enumerate(registros):
        r = copy.deepcopy(rec)
        if i % 2 == 0:
            cands = [f for f in c.fields[1:] if f.type == "str" and isinstance(r.get(f.name), str) and " " in r[f.name]]
            if cands:
                f = cands[kt % len(cands)]
                frag = FRAGMENTOS_TEXTO[kt % len(FRAGMENTOS_TEXTO)]
                prueba = copy.deepcopy(r)
                prueba[f.name] = prueba[f.name] + frag
                if _valido(prueba, c, cabecera):
                    r = prueba
                    traza.append(f"{i}:{f.name}:{frag!r}")
                kt += 1
        if i % 3 == 1:
            for f in c.fields:
                key = f.json_items if f.type == "mlist" else f.name
                if f.type in ("list", "mlist") and f.item == "str" and r.get(key):
                    frag = FRAGMENTOS_LISTA[kl % len(FRAGMENTOS_LISTA)]
                    prueba = copy.deepcopy(r)
                    prueba[key][0] = str(prueba[key][0]) + frag
                    if _valido(prueba, c, cabecera):
                        r = prueba
                        traza.append(f"{i}:{key}[0]:{frag!r}")
                    kl += 1
                    break
        out.append(r)
    return out, traza


def _bloque_valor(nombre: str, v: Any) -> List[str]:
    if isinstance(v, str) and "\n" in v:
        return [f"{nombre}: <<<", *v.split("\n"), ">>>"]
    return [f"{nombre}: {_s(v)}"]


def renderizar_entrada(c: Contract, registros: List[Dict[str, Any]]) -> str:
    """Documento de origen legible y sin ambigüedad (no usa la sintaxis de ningún brazo)."""
    L = [f"DOCUMENTO DE ORIGEN — {c.name} ({len(registros)} registros)",
         "Convenciones: los textos de varias líneas van entre <<< y >>>; cada elemento de lista va en su propia "
         "línea tras un guion; en listas con selección, [x] marca los elementos seleccionados; (vacío) indica nulo."]
    for k, r in enumerate(registros, 1):
        L.append("")
        L.append(f"--- registro {k} ---")
        for f in c.fields:
            if f.type == "mlist":
                items = r.get(f.json_items) or []
                sel = r.get(f.json_selected)
                sels = set(sel if isinstance(sel, list) else ([sel] if sel is not None else []))
                L.append(f"{f.name} ({len(items)} elementos; [x] = seleccionado):")
                for j, it in enumerate(items):
                    L.append(f"  - [{'x' if j in sels else ' '}] {_s(it)}")
            elif f.type == "list":
                vals = r.get(f.name) or []
                if not vals:
                    L.append(f"{f.name}: (lista vacía)")
                else:
                    L.append(f"{f.name} ({len(vals)} elementos):")
                    for it in vals:
                        L.append(f"  - {_s(it)}")
            elif f.type == "tuple":
                t = r.get(f.name) or {}
                L.append(f"{f.name}: " + "; ".join(f"{cmp.name}={_s(t.get(cmp.name))}" for cmp in f.items))
            else:
                L.extend(_bloque_valor(f.name, r.get(f.name)))
    return "\n".join(L)


def _cargar_fork(prefijo: str, reg: Registry):
    c = reg.get(prefijo)
    canon = json.loads((FORKS / prefijo / "fixtures" / "canonical.json").read_text(encoding="utf-8"))
    cabecera = {k: v for k, v in canon.get("header", {}).items() if k not in ("n", "v")}
    return c, canon[c.records_key], cabecera


_REG: Optional[Registry] = None


def registro_forks() -> Registry:
    global _REG
    if _REG is None:
        _REG = Registry.load(FORKS)
    return _REG


def construir(tarea_id: str) -> Tarea:
    tipo_corto, _, prefijo = tarea_id.partition("-")
    reg = registro_forks()
    c, recs, cabecera = _cargar_fork(prefijo, reg)
    ejemplo = recs[0]
    registros, traza = estresar(recs[1:], c, cabecera)
    dominio = f"{c.domain} — {c.name}" if c.domain else c.name
    if tipo_corto == "ext":
        entrada = renderizar_entrada(c, registros)
        instr = ("Transforma el documento de origen en la salida estructurada pedida. Copia los textos literalmente "
                 "(incluidas comillas, barras, comas, asteriscos y saltos de línea), conserva el orden de registros y "
                 "de elementos, no omitas ni inventes registros.")
        return Tarea(id=tarea_id, tipo="extraccion", prefijo=prefijo, dominio=dominio, contrato=c,
                     registros=registros, cabecera=cabecera, ejemplo=ejemplo, texto_entrada=entrada,
                     instruccion=instr, n_solicitados=len(registros), estres=traza)
    if tipo_corto == "gen":
        tema = TEMAS.get(prefijo, c.name)
        n = len(registros)
        instr = (f"Genera {n} registros nuevos, variados y realistas, para el dominio «{c.name}» ({c.description}) "
                 f"sobre el tema: {tema}. Usa textos naturales; pueden contener comas, comillas o saltos de línea "
                 "cuando haga falta. No repitas el registro de ejemplo.")
        return Tarea(id=tarea_id, tipo="generativa", prefijo=prefijo, dominio=dominio, contrato=c,
                     registros=registros, cabecera=cabecera, ejemplo=ejemplo, instruccion=instr,
                     n_solicitados=n, estres=traza)
    raise ValueError(f"id de tarea desconocido: {tarea_id} (use ext-<prefijo> o gen-<prefijo>)")


def catalogo() -> List[str]:
    reg = registro_forks()
    ids = [f"ext-{c.prefix}" for c in reg]
    ids += [f"gen-{p}" for p in GENERATIVAS if p in reg]
    return ids


def cargar(ids: List[str]) -> Dict[str, Tarea]:
    return {i: construir(i) for i in ids}
