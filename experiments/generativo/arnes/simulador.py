"""Extensión del adaptador simulado para las condiciones del Plan v3.

``minifmt.ai.adapters.SimulatedAdapter`` (propiedad del núcleo) renderiza .mini,
JSON, JSON con esquema y pipe, y repara líneas .mini.  Este subclase añade, SOLO
para el arnés:

* ``json_minimo`` (brazo A): como ``json`` pero sin contrato en el prompt, con
  deriva de tipos (un número escrito como texto) y, rara vez, una clave
  envolvente distinta;
* ``repair_json`` (A+1, B+1, C+1): corrige los objetos rechazados;
* identidades cambiadas en reparaciones (.mini y JSON), para ejercitar la
  auditoría de identidad duplicada/inventada.

Todas las tasas son SUPUESTOS del simulador (no mediciones): los resultados
simulados validan el arnés y no dicen nada sobre modelos reales.
"""
from __future__ import annotations

import copy
import difflib
import hashlib
import json
import random
from typing import Any, Dict, List, Optional

from minifmt.ai.adapters.simulated import PROFILES, SimTarget, SimulatedAdapter, _count_tokens
from minifmt.ai.adapters.base import result

TASAS_ARNES: Dict[str, float] = {
    "json_minimo_type_drift": 0.06,     # por registro: un campo numérico/booleano llega como texto
    "json_minimo_key_drift": 0.04,      # por documento: clave envolvente distinta de la pedida
    "repair_identity_swap": 0.04,       # por objeto/línea reparada: se devuelve la identidad de otro registro
    "repair_json_success": 0.85,
}


class SimuladorArnes(SimulatedAdapter):
    provider = "simulado"

    def __init__(self, model: str = "sim", *, profile: Any = "medio", **kw: Any):
        super().__init__(model, profile=profile, **kw)
        self._mult = PROFILES.get(profile, 1.0) if isinstance(profile, str) else float((profile or {}).get("multiplier", 1.0))
        self.tasas = {k: (max(0.0, min(1.0, 1 - (1 - v) * self._mult)) if k == "repair_json_success"
                          else max(0.0, min(1.0, v * self._mult))) for k, v in TASAS_ARNES.items()}

    def _rng(self, system: str, user: str, seed: Optional[int], sal: str) -> random.Random:
        h = hashlib.sha256(f"{self.seed}\x00{seed}\x00{self.model}\x00{sal}\x00{system}\x00{user}".encode("utf-8")).hexdigest()
        return random.Random(int(h[:16], 16))

    # ------------------------------------------------------------------ api
    def generate(self, system: str, user: str, *, max_tokens: int, temperature: Optional[float],
                 response_format: Optional[Dict[str, Any]] = None, seed: Optional[int] = None) -> Dict[str, Any]:
        objetivo = self.oracle(system, user) if self.oracle else None
        kind = objetivo.kind if objetivo is not None else None
        if kind == "json_minimo":
            return self._generar_json_minimo(objetivo, system, user, max_tokens, temperature, response_format, seed)
        if kind == "repair_json":
            return self._generar_reparacion_json(objetivo, system, user, max_tokens, response_format, seed)
        r = super().generate(system, user, max_tokens=max_tokens, temperature=temperature,
                             response_format=response_format, seed=seed)
        if kind == "repair":
            rng = self._rng(system, user, seed, "swap_mini")
            r = self._permutar_identidad_mini(r, objetivo, rng)
        return r

    # -------------------------------------------------------------- json A
    def _generar_json_minimo(self, t: SimTarget, system: str, user: str, max_tokens: int, temperature: Optional[float],
                             response_format: Optional[Dict[str, Any]], seed: Optional[int]) -> Dict[str, Any]:
        rng = self._rng(system, user, seed, "json_minimo")
        c = t.contract
        recs = copy.deepcopy(t.records)
        fallas: List[str] = []
        for i, rec in enumerate(recs):
            if rng.random() < self.tasas["json_minimo_type_drift"]:
                numericos = [f for f in (c.fields if c else []) if f.type in ("int", "float", "bool") and rec.get(f.name) is not None]
                if numericos:
                    f = rng.choice(numericos)
                    rec[f.name] = str(rec[f.name]).lower() if isinstance(rec[f.name], bool) else str(rec[f.name])
                    fallas.append(f"type_drift:{i}:{f.name}")
        t2 = SimTarget(kind="json", contract=c, records=recs, header=t.header)
        original = self.oracle
        self.oracle = lambda s, u: t2          # solo durante esta llamada
        try:
            r = super().generate(system, user, max_tokens=max_tokens, temperature=temperature,
                                 response_format=response_format, seed=seed)
        finally:
            self.oracle = original
        if c is not None and rng.random() < self.tasas["json_minimo_key_drift"] and r["stop_reason"] != "max_tokens":
            r["text"] = r["text"].replace(f'"{c.records_key}"', '"registros"', 1)
            fallas.append("key_drift")
        r["raw"]["fallas"] = list(r["raw"].get("fallas", [])) + fallas
        return r

    # ------------------------------------------------------- reparar JSON
    def _generar_reparacion_json(self, t: SimTarget, system: str, user: str, max_tokens: int,
                                 response_format: Optional[Dict[str, Any]], seed: Optional[int]) -> Dict[str, Any]:
        rng = self._rng(system, user, seed, "repair_json")
        c = t.contract
        limpios = [dict(r) for r in t.records]
        crudos = [json.dumps(r, ensure_ascii=False) for r in limpios]
        salida: List[Any] = []
        fallas: List[str] = []
        for j, (texto, _) in enumerate(t.repair_items):
            if texto.strip() == "null":
                salida.append(None)
                fallas.append(f"repair_drop:{j}")
                continue
            incompleto = not texto.rstrip().endswith("}")
            if incompleto and not t.repair_context:
                salida.append({})                      # sin el texto de origen no hay de dónde recuperar los valores
                fallas.append(f"repair_no_information:{j}")
                continue
            puntajes = [difflib.SequenceMatcher(None, texto, cr).ratio() for cr in crudos]
            mejor = max(range(len(limpios)), key=lambda k: puntajes[k]) if limpios else None
            if mejor is None:
                salida.append({})
                continue
            if rng.random() < self.tasas["repair_identity_swap"] and len(limpios) > 1:
                otro = rng.choice([k for k in range(len(limpios)) if k != mejor])
                salida.append(copy.deepcopy(limpios[otro]))
                fallas.append(f"repair_identity_swap:{j}")
            elif rng.random() < self.tasas["repair_json_success"]:
                salida.append(copy.deepcopy(limpios[mejor]))
                fallas.append(f"repair_ok:{j}")
            else:
                rec = copy.deepcopy(limpios[mejor])
                numericos = [f for f in (c.fields if c else []) if f.type in ("int", "float") and rec.get(f.name) is not None]
                if numericos:
                    rec[numericos[0].name] = str(rec[numericos[0].name])
                else:
                    rec[next(iter(rec))] = None
                salida.append(rec)
                fallas.append(f"repair_failed:{j}")
        clave = c.records_key if c else "registros"
        texto = json.dumps({clave: salida}, ensure_ascii=False)
        stop = "end_turn"
        n_sal = _count_tokens(texto)
        if n_sal > max_tokens:
            texto = texto[: max_tokens * 4]
            n_sal = max_tokens
            stop = "max_tokens"
            fallas.append("max_tokens")
        n_ent = _count_tokens(system) + _count_tokens(user) + 8
        lat = 180.0 + 0.02 * n_ent + 11.0 * n_sal + rng.uniform(0, 120)
        return result(texto, n_ent, n_sal, lat, {"simulado": True, "fallas": fallas}, stop_reason=stop,
                      model=self.model, provider=self.provider)

    # -------------------------------------------------- identidad en .mini
    def _permutar_identidad_mini(self, r: Dict[str, Any], t: SimTarget, rng: random.Random) -> Dict[str, Any]:
        """Con cierta probabilidad una línea corregida toma el contenido de otro registro (identidad repetida)."""
        c = t.contract
        if c is None or len(t.records) < 2 or r["stop_reason"] == "max_tokens":
            return r
        lineas = r["text"].split("\n")
        if len(lineas) < 2:
            return r
        from minifmt.serializer import encode_record
        cambios = []
        for k in range(1, len(lineas)):
            if lineas[k].strip() in ("-", "") or not any(f.unique for f in c.fields):
                continue
            if rng.random() < self.tasas["repair_identity_swap"]:
                candidatos = [rec for rec in t.records]
                ajeno = rng.choice(candidatos)
                try:
                    nueva = encode_record(ajeno, c)
                except Exception:  # noqa: BLE001
                    continue
                if nueva != lineas[k]:
                    lineas[k] = nueva
                    cambios.append(k)
        if cambios:
            r = dict(r)
            r["text"] = "\n".join(lineas)
            r["raw"] = dict(r["raw"])
            r["raw"]["fallas"] = list(r["raw"].get("fallas", [])) + [f"repair_identity_swap:{k - 1}" for k in cambios]
        return r
