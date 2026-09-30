"""Diseño de la configuración especializada sobre el conjunto de DESARROLLO.

Búsqueda local, fijada en ``criterio.json`` (``diseno_de_la_configuracion``):

* objetivo J = suma, sobre los tres tokenizadores, de los tokens del texto completo
  (instrucción compacta sin ejemplo + salida) con n=50 del lote 0 de desarrollo;
* movimientos: cambiar el tratamiento de UN campo (código, id numérico, constante en la cabecera,
  entero escalado, hora en minutos) o mover un campo de posición;
* un movimiento solo se acepta si reduce J en al menos 1 % y reconstruye todos los registros del
  lote (``comprobar_equivalencia``); se aplica el mejor en cada ronda;
* todo lo evaluado, aceptado o no, se guarda en ``diseno/<dominio>.json`` (qué se probó).

La evaluación NO toca el conjunto de prueba.
"""
from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from . import datos, tokenizadores
from .dominios import Dominio, dominios
from .especializacion import (Campo, Especializacion, NoEquivalente, comprobar_equivalencia, con_codigos,
                             esquemas_de_codigos, instruccion_compacta)
from .perfiles import salida_especializada

AQUI = Path(__file__).resolve().parent
DIRECTORIO = AQUI / "diseno"
N_DISENO = 50
MEJORA_MINIMA = 0.01

# Tratamientos especiales que cada dominio permite probar (además de los esquemas de código de los enum).
ESPECIALES: Dict[str, Dict[str, List[Dict[str, Any]]]] = {
    "tickets": {"id": [{"tratamiento": "id_prefijo", "prefijo": "T-", "ancho": 0, "minimo": 0}]},
    "eventos": {
        "id_equipo": [{"tratamiento": "id_prefijo", "prefijo": "EQ-", "ancho": 4, "minimo": 0}],
        "fecha": [{"tratamiento": "constante", "clave_cabecera": "f"}],
        "hora": [{"tratamiento": "hhmm"}],
        "valor": [{"tratamiento": "escalado", "factor": 10}],
    },
    "comentarios": {},
}


def _aplicar(base: Campo, decision: Dict[str, Any]) -> Campo:
    t = decision.get("tratamiento", "pasa")
    if t == "pasa":
        return base
    if t == "codigos":
        return con_codigos(base, decision["esquema"])
    if t == "id_prefijo":
        return replace(base, tratamiento="id_prefijo", prefijo=decision["prefijo"], ancho=decision["ancho"],
                       minimo=decision.get("minimo"), maximo=decision.get("maximo"), mini=decision.get("mini", ""))
    if t == "escalado":
        return replace(base, tratamiento="escalado", factor=decision["factor"])
    if t == "hhmm":
        return replace(base, tratamiento="hhmm")
    if t == "constante":
        return replace(base, tratamiento="constante", clave_cabecera=decision["clave_cabecera"])
    raise ValueError(t)


def construir(dom: Dominio, decisiones: Dict[str, Dict[str, Any]], orden: Optional[List[str]] = None) -> Especializacion:
    """Especialización a partir de {campo: decisión} (los campos sin decisión pasan tal cual)."""
    campos = [_aplicar(b, decisiones.get(b.orig, {"tratamiento": "pasa"})) for b in dom.campos_base()]
    return Especializacion(prefijo=dom.prefijo_especializado, nombre=dom.titulo, descripcion=dom.descripcion_especializada,
                           clave_json=dom.clave_json, campos=campos, orden=orden)


def _opciones(dom: Dominio, campo: Campo) -> List[Dict[str, Any]]:
    ops: List[Dict[str, Any]] = [{"tratamiento": "pasa"}]
    if campo.tipo == "enum":
        ops += [{"tratamiento": "codigos", "esquema": e} for e in esquemas_de_codigos(campo.valores) if e != "etiqueta"]
    ops += ESPECIALES.get(dom.id, {}).get(campo.orig, [])
    return ops


def objetivo(dom: Dominio, esp: Especializacion, registros) -> Tuple[int, Dict[str, int]]:
    """J del diseño: tokens (instrucción compacta sin ejemplo + salida), sumados sobre los 3 tokenizadores."""
    instr = instruccion_compacta(esp)
    salida = salida_especializada(esp, registros)
    por = {n: t.contar(instr + "\n\n" + salida) for n, t in tokenizadores.todos().items()}
    return sum(por.values()), por


def _evaluar(dom: Dominio, decisiones, orden, registros):
    esp = construir(dom, decisiones, orden)
    try:
        comprobar_equivalencia(esp, registros)
    except NoEquivalente as e:
        return None, str(e)
    return objetivo(dom, esp, registros), None


def disenar(dom: Dominio) -> Dict[str, Any]:
    reg = dom.generar(datos.SEMILLA_DESARROLLO, 0, N_DISENO)
    base = dom.campos_base()
    decisiones: Dict[str, Dict[str, Any]] = {c.orig: {"tratamiento": "pasa"} for c in base}
    orden = None
    (j0, por0), err = _evaluar(dom, decisiones, orden, reg)
    actual = j0
    registro: Dict[str, Any] = {"dominio": dom.id, "semilla": datos.SEMILLA_DESARROLLO, "n": N_DISENO,
                                "J_inicial": j0, "J_inicial_por_tokenizador": por0, "rondas": [], "aceptadas": []}
    ronda = 0
    while True:
        ronda += 1
        candidatos = []
        for c in base:
            if decisiones[c.orig].get("tratamiento") != "pasa":
                continue
            for op in _opciones(dom, c):
                if op["tratamiento"] == "pasa":
                    continue
                prueba = dict(decisiones)
                prueba[c.orig] = op
                res, err = _evaluar(dom, prueba, orden, reg)
                cand = {"campo": c.orig, "decision": op}
                if res is None:
                    cand.update(estado="descartada_por_equivalencia", motivo=err)
                else:
                    j, por = res
                    cand.update(estado="evaluada", J=j, J_por_tokenizador=por, mejora_pct=round(100 * (actual - j) / actual, 3))
                candidatos.append(cand)
        ok = [c for c in candidatos if c["estado"] == "evaluada" and c["mejora_pct"] >= 100 * MEJORA_MINIMA]
        registro["rondas"].append({"ronda": ronda, "tipo": "tratamiento", "J_antes": actual, "candidatos": candidatos})
        if not ok:
            break
        mejor = max(ok, key=lambda c: c["mejora_pct"])
        decisiones[mejor["campo"]] = mejor["decision"]
        actual = mejor["J"]
        registro["aceptadas"].append({"ronda": ronda, "campo": mejor["campo"], "decision": mejor["decision"],
                                      "J_despues": actual, "mejora_pct": mejor["mejora_pct"]})
    # --- orden contractual: búsqueda local moviendo un campo de posición
    esp_actual = construir(dom, decisiones, orden)
    nombres = [c.nombre() for c in esp_actual.campos_registro()]
    orden = list(nombres)
    while len(nombres) > 1:
        ronda += 1
        candidatos = []
        for i, nom in enumerate(orden):
            for j in range(len(orden)):
                if j == i:
                    continue
                nuevo = list(orden)
                nuevo.insert(j, nuevo.pop(i))
                res, err = _evaluar(dom, decisiones, nuevo, reg)
                cand = {"mover": nom, "a_posicion": j}
                if res is None:
                    cand.update(estado="descartada_por_equivalencia", motivo=err)
                else:
                    jj, por = res
                    cand.update(estado="evaluada", J=jj, mejora_pct=round(100 * (actual - jj) / actual, 3), orden=nuevo)
                candidatos.append(cand)
        ok = [c for c in candidatos if c["estado"] == "evaluada" and c["mejora_pct"] >= 100 * MEJORA_MINIMA]
        registro["rondas"].append({"ronda": ronda, "tipo": "orden", "J_antes": actual, "candidatos": candidatos})
        if not ok:
            break
        mejor = max(ok, key=lambda c: c["mejora_pct"])
        orden = mejor["orden"]
        actual = actual * (1 - mejor["mejora_pct"] / 100)
        registro["aceptadas"].append({"ronda": ronda, "mover": mejor["mover"], "a_posicion": mejor["a_posicion"],
                                      "orden": orden, "mejora_pct": mejor["mejora_pct"]})
    orden_final = orden if orden != nombres else None
    (jf, porf), _ = _evaluar(dom, decisiones, orden_final, reg)
    registro.update(decisiones=decisiones, orden=orden_final, J_final=jf, J_final_por_tokenizador=porf,
                    mejora_total_pct=round(100 * (j0 - jf) / j0, 3))
    return registro


def guardar(reg: Dict[str, Any]) -> Path:
    DIRECTORIO.mkdir(exist_ok=True)
    ruta = DIRECTORIO / f"{reg['dominio']}.json"
    ruta.write_text(json.dumps(reg, ensure_ascii=False, indent=1) + "\n", encoding="utf-8", newline="\n")
    return ruta


def cargar(dom: Dominio) -> Especializacion:
    reg = json.loads((DIRECTORIO / f"{dom.id}.json").read_text(encoding="utf-8"))
    return construir(dom, reg["decisiones"], reg["orden"])


def especializacion_de(dom_id: str) -> Especializacion:
    return cargar(dominios()[dom_id])


if __name__ == "__main__":
    import sys
    for did, d in dominios().items():
        if len(sys.argv) > 1 and did not in sys.argv[1:]:
            continue
        r = disenar(d)
        ruta = guardar(r)
        print(did, "J", r["J_inicial"], "->", r["J_final"], f"({r['mejora_total_pct']} %)", "aceptadas:",
              [(a.get("campo") or a.get("mover"), (a.get("decision") or {}).get("esquema") or (a.get("decision") or {}).get("tratamiento")) for a in r["aceptadas"]],
              "->", ruta.name)
